"""Non-blocking Moonraker HTTP API client for local Klipper instances.

Connects to 127.0.0.1:7125 (local Moonraker instance),
polling live temperatures and printer connection state on a background thread.
"""

import json
import os
import re
import threading
import urllib.parse
import urllib.request
import uuid
from typing import Optional

from .qt import QtCore, Signal

DEFAULT_HOSTS = [
    os.environ.get("MOONRAKER_HOST", "127.0.0.1:7125"),
]


class MoonrakerClient(QtCore.QObject):
    # (connected: bool, host: str, klippy_state: str)
    connection_changed = Signal(bool, str, str)
    # (nozzle_current: float, nozzle_target: float, bed_current: float, bed_target: float)
    temps_updated = Signal(float, float, float, float)
    # (x: float, y: float, z: float, homed_axes: str)
    coords_updated = Signal(float, float, float, str)
    # (force_g: float) - corresponds to {% set grams = printer.load_cell.force_g %}
    load_cell_updated = Signal(float)
    # (config_settings: dict, objects_list: list) - emitted when Klipper config is loaded
    config_loaded = Signal(dict, list)
    # (firmware_info: dict) - emitted when firmware, MCU, and Moonraker versions are loaded
    firmware_info_updated = Signal(dict)
    # (print_stats: dict) - live printing state, progress, durations, layers, and factors
    print_stats_updated = Signal(dict)
    # (bed_mesh: dict) - live bed mesh profile_name, mesh matrices, and profiles
    bed_mesh_updated = Signal(dict)
    # Internal cross-thread dispatcher to execute callbacks safely on Qt GUI thread
    _dispatch_signal = Signal(object)

    def __init__(self, hosts=None, poll_interval_ms: int = 1000, parent=None):
        super().__init__(parent)
        self.hosts = list(hosts or DEFAULT_HOSTS)
        self.active_host: Optional[str] = None
        self.connected: bool = False
        self.klippy_state: str = "disconnected"
        self.homed_axes: str = ""
        self.live_load_cell_g: float = 0.0
        self.config: dict = {}
        self.objects: list = []
        self._config_fetched: bool = False
        self.firmware_info: dict = {
            "klipper_version": "v0.13.0",
            "mcu_chip": "stm32f072xb",
            "mcu_freq": "48 MHz",
            "mcu_version": "v0.13.0",
            "mcu_compiler": "gcc / binutils",
            "moonraker_version": "v0.10.0",
            "moonraker_api": "API 1.5.0",
            "hostname": "pi4",
            "config_file": "/home/pi/printer_data/config/printer.cfg",
            "python_path": "/home/pi/klippy-env",
            "state": "ready"
        }
        self.last_print_stats: dict = {}
        self.last_bed_mesh: dict = {}
        self._busy = False
        self._dispatch_signal.connect(lambda fn: fn())

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll_once)

    def start(self):
        self._poll_once()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll_now(self):
        """Trigger an immediate background poll."""
        self._poll_once()

    def _poll_once(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._worker_query, daemon=True).start()

    def _fetch_json(self, host: str, path: str, timeout: float = 1.2) -> Optional[dict]:
        url = f"http://{host}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
        return None

    def _worker_query(self):
        try:
            # Try active host first for fast polling, then fall back to candidate list
            candidates = []
            if self.active_host:
                candidates.append(self.active_host)
            for h in self.hosts:
                if h not in candidates:
                    candidates.append(h)

            query_path = "/printer/objects/query?extruder&heater_bed&webhooks&toolhead&gcode_move&load_cell_probe&load_cell&probe&print_stats&virtual_sdcard&display_status&fan&bed_mesh"
            for host in candidates:
                try:
                    data = self._fetch_json(host, query_path, timeout=1.2)
                    if data and "result" in data:
                        status = data["result"].get("status", {})
                        ext = status.get("extruder", {})
                        bed = status.get("heater_bed", {})
                        wh = status.get("webhooks", {})
                        toolhead = status.get("toolhead", {})
                        gcode_move = status.get("gcode_move", {})

                        n_cur = float(ext.get("temperature", 0.0))
                        n_tgt = float(ext.get("target", 0.0))
                        b_cur = float(bed.get("temperature", 0.0))
                        b_tgt = float(bed.get("target", 0.0))
                        k_state = str(wh.get("state", "ready"))

                        # Coordinates & homed axes
                        pos = gcode_move.get("gcode_position") or toolhead.get("position") or [0.0, 0.0, 0.0, 0.0]
                        x_pos = float(pos[0]) if len(pos) > 0 else 0.0
                        y_pos = float(pos[1]) if len(pos) > 1 else 0.0
                        z_pos = float(pos[2]) if len(pos) > 2 else 0.0
                        homed = str(toolhead.get("homed_axes", "")).lower()
                        self.homed_axes = homed

                        # Live load cell probe force ({% set grams = printer.load_cell.force_g %})
                        lc_obj = status.get("load_cell_probe") or status.get("load_cell") or status.get("probe") or {}
                        force_val = None
                        if "force_g" in lc_obj and lc_obj["force_g"] is not None:
                            try:
                                force_val = float(lc_obj["force_g"])
                                self.live_load_cell_g = force_val
                            except (ValueError, TypeError):
                                pass

                        self.active_host = host
                        self.connected = True
                        self.klippy_state = k_state

                        if k_state != "ready":
                            self._config_fetched = False

                        # If connected and config not yet fetched, fetch Klipper config in background
                        if not self._config_fetched and k_state == "ready":
                            self._config_fetched = True
                            threading.Thread(target=self._fetch_config_and_objects, args=(host,), daemon=True).start()

                        self.connection_changed.emit(True, host, k_state)
                        self.temps_updated.emit(n_cur, n_tgt, b_cur, b_tgt)
                        self.coords_updated.emit(x_pos, y_pos, z_pos, homed)

                        # Print stats & virtual sdcard parsing
                        p_stats = status.get("print_stats", {})
                        v_sd = status.get("virtual_sdcard", {})
                        d_status = status.get("display_status", {})
                        fan_obj = status.get("fan", {})

                        progress = float(d_status.get("progress") or v_sd.get("progress") or 0.0)
                        p_state = str(p_stats.get("state", "standby")).lower()
                        filename = str(p_stats.get("filename", ""))
                        print_dur = float(p_stats.get("print_duration", 0.0))
                        total_dur = float(p_stats.get("total_duration", 0.0))
                        filament = float(p_stats.get("filament_used", 0.0))

                        info = p_stats.get("info") or {}
                        cur_layer = info.get("current_layer")
                        tot_layer = info.get("total_layer")

                        spd_fac = float(gcode_move.get("speed_factor", 1.0))
                        ext_fac = float(gcode_move.get("extrude_factor", 1.0))
                        fan_spd = float(fan_obj.get("speed", 0.0))

                        homing_origin = gcode_move.get("homing_origin", [0.0, 0.0, 0.0, 0.0])
                        z_offset = float(homing_origin[2]) if len(homing_origin) > 2 else 0.0

                        stats_dict = {
                            "state": p_state,
                            "filename": filename,
                            "progress": progress,
                            "print_duration": print_dur,
                            "total_duration": total_dur,
                            "filament_used": filament,
                            "current_layer": cur_layer,
                            "total_layer": tot_layer,
                            "speed_factor": spd_fac,
                            "extrude_factor": ext_fac,
                            "fan_speed": fan_spd,
                            "z_offset": z_offset,
                            "nozzle_cur": n_cur,
                            "nozzle_tgt": n_tgt,
                            "bed_cur": b_cur,
                            "bed_tgt": b_tgt,
                            "z_pos": z_pos,
                            "message": str(p_stats.get("message") or d_status.get("message") or "")
                        }
                        self.last_print_stats = stats_dict
                        self.print_stats_updated.emit(stats_dict)

                        bm_obj = status.get("bed_mesh")
                        if bm_obj is not None:
                            self.last_bed_mesh = bm_obj
                            self.bed_mesh_updated.emit(bm_obj)
                        if force_val is not None:
                            self.load_cell_updated.emit(force_val)
                        return
                except Exception:
                    continue

            # If printer/objects/query failed on all hosts, check /server/info in case klippy is starting
            for host in candidates:
                try:
                    info = self._fetch_json(host, "/server/info", timeout=1.0)
                    if info and "result" in info:
                        k_state = str(info["result"].get("klippy_state", "startup"))
                        self.active_host = host
                        self.connected = True
                        self.klippy_state = k_state
                        self._config_fetched = False
                        self.connection_changed.emit(True, host, k_state)
                        return
                except Exception:
                    continue

            self.active_host = None
            self.connected = False
            self.klippy_state = "disconnected"
            self._config_fetched = False
            self.connection_changed.emit(False, "", "disconnected")
        finally:
            self._busy = False

    def _fetch_config_and_objects(self, host: str):
        """Fetch Klipper settings, registered objects, and firmware info once per connection session."""
        cfg_found = {}
        objs_found = []
        fw_info = dict(self.firmware_info)

        try:
            cfg_data = self._fetch_json(host, "/printer/objects/query?configfile", timeout=2.5)
            if cfg_data and "result" in cfg_data:
                res_cf = cfg_data["result"].get("status", {}).get("configfile", {})
                cfg_found = res_cf.get("settings", {})
                self.raw_config = res_cf.get("config", {})
        except Exception:
            pass

        try:
            obj_data = self._fetch_json(host, "/printer/objects/list", timeout=2.0)
            if obj_data and "result" in obj_data:
                objs_found = obj_data["result"].get("objects", [])
        except Exception:
            pass

        try:
            pinfo = self._fetch_json(host, "/printer/info", timeout=2.0)
            if pinfo and "result" in pinfo:
                res = pinfo["result"]
                fw_info["klipper_version"] = res.get("software_version", fw_info["klipper_version"])
                fw_info["hostname"] = res.get("hostname", fw_info["hostname"])
                fw_info["config_file"] = res.get("config_file", fw_info["config_file"])
                fw_info["python_path"] = res.get("python_path", fw_info["python_path"])
                fw_info["state"] = res.get("state", fw_info["state"])
        except Exception:
            pass

        try:
            mcu_data = self._fetch_json(host, "/printer/objects/query?mcu", timeout=2.0)
            if mcu_data and "result" in mcu_data:
                mcu_stat = mcu_data["result"].get("status", {}).get("mcu", {})
                fw_info["mcu_version"] = mcu_stat.get("mcu_version", fw_info["mcu_version"])
                fw_info["mcu_compiler"] = mcu_stat.get("mcu_build_versions", fw_info["mcu_compiler"])
                consts = mcu_stat.get("mcu_constants", {})
                fw_info["mcu_chip"] = consts.get("MCU", fw_info["mcu_chip"])
                freq = consts.get("CLOCK_FREQ")
                if freq:
                    fw_info["mcu_freq"] = f"{round(freq / 1000000)} MHz"
        except Exception:
            pass

        try:
            sinfo = self._fetch_json(host, "/server/info", timeout=2.0)
            if sinfo and "result" in sinfo:
                sres = sinfo["result"]
                fw_info["moonraker_version"] = sres.get("moonraker_version", fw_info["moonraker_version"])
                api_ver = sres.get("api_version_string")
                if api_ver:
                    fw_info["moonraker_api"] = f"API {api_ver}"
        except Exception:
            pass

        def _apply():
            self.config = cfg_found
            self.objects = objs_found
            self.firmware_info = fw_info
            self.config_loaded.emit(self.config, self.objects)
            self.firmware_info_updated.emit(self.firmware_info)

        self._dispatch_signal.emit(_apply)

    def has_load_cell(self, config: dict = None, objects: list = None) -> bool:
        """Returns True if the printer has a load cell sensor or probe configured."""
        cfg = config if config is not None else self.config
        objs = objects if objects is not None else self.objects
        if not cfg and not objs:
            return False
        return any(k in cfg for k in ["load_cell", "load_cell_probe", "load_cell_sensor", "hx711", "ads1220"]) or any("load_cell" in o for o in objs)

    def is_delta(self) -> bool:
        """Returns True if kinematics is delta."""
        return str(self.config.get("printer", {}).get("kinematics", "")).lower() == "delta"

    def send_gcode(self, script: str, on_done=None, timeout: float = 45.0):
        """Send a G-code command asynchronously to the active Moonraker host."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            ok = False
            try:
                url = f"http://{host}/printer/gcode/script"
                payload = json.dumps({"script": script}).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ok = (resp.status == 200)
            except Exception:
                ok = False
            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def post_endpoint(self, endpoint: str, on_done=None, timeout: float = 15.0):
        """Send an asynchronous POST request to Moonraker (e.g. /machine/reboot, /machine/shutdown)."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            ok = False
            try:
                url = f"http://{host}{endpoint}"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ok = (resp.status == 200)
            except Exception:
                ok = False
            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def emergency_stop(self, on_done=None):
        """Trigger immediate emergency stop via Moonraker /printer/emergency_stop with M112 fallback."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            ok = False
            try:
                url = f"http://{host}/printer/emergency_stop"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    ok = (resp.status == 200)
            except Exception:
                ok = False

            if not ok:
                try:
                    url = f"http://{host}/printer/gcode/script"
                    body = json.dumps({"script": "M112"}).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        ok = (resp.status == 200)
                except Exception:
                    ok = False

            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def firmware_restart(self, on_done=None):
        """Restart Klipper firmware via /printer/firmware_restart with FIRMWARE_RESTART fallback."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            ok = False
            try:
                url = f"http://{host}/printer/firmware_restart"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    ok = (resp.status == 200)
            except Exception:
                try:
                    self.send_gcode("FIRMWARE_RESTART")
                    ok = True
                except Exception:
                    ok = False
            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def jog(self, axis: str, distance: float, on_done=None):
        """Relative jog for X, Y, or Z."""
        speed = 600 if axis.upper() == "Z" else 3000
        cmd = f"SAVE_GCODE_STATE NAME=_ui_jog\nG91\nG1 {axis.upper()}{distance:+f} F{speed}\nRESTORE_GCODE_STATE NAME=_ui_jog"
        self.send_gcode(cmd, on_done, timeout=15.0)

    def home(self, axes: str = "", on_done=None):
        """Home specified axes (e.g. 'X Y', 'Z') or all axes if empty."""
        cmd = f"G28 {axes.strip().upper()}" if axes.strip() else "G28"
        self.send_gcode(cmd, on_done, timeout=60.0)

    def motors_off(self, on_done=None):
        """Turn off steppers (M84)."""
        self.send_gcode("M84", on_done)

    def set_temperature(self, heater: str, target: float, on_done=None):
        """Set target temperature for a heater ('extruder' or 'heater_bed'). 0 disables heater."""
        cmd = f"SET_HEATER_TEMPERATURE HEATER={heater} TARGET={target:.1f}"
        self.send_gcode(cmd, on_done)

    def read_load_cell(self, on_done=None):
        """Execute LOAD_CELL_READ to measure attached weight."""
        self.send_gcode("LOAD_CELL_READ", on_done=on_done, timeout=15.0)

    def tare_load_cell(self, on_done=None):
        """Execute LOAD_CELL_TARE to zero load cell."""
        self.send_gcode("LOAD_CELL_TARE", on_done=on_done, timeout=10.0)

    def load_bed_mesh(self, profile: str = "default", on_done=None):
        """Load a saved bed mesh profile."""
        self.send_gcode(f"BED_MESH_PROFILE LOAD={profile}", on_done=on_done, timeout=15.0)

    def save_bed_mesh(self, profile: str = "default", on_done=None):
        """Save active bed mesh profile."""
        self.send_gcode(f"BED_MESH_PROFILE SAVE={profile}", on_done=on_done, timeout=15.0)

    def clear_bed_mesh(self, on_done=None):
        """Clear active bed mesh."""
        self.send_gcode("BED_MESH_CLEAR", on_done=on_done, timeout=10.0)

    def calibrate_bed_mesh(self, profile: str = "default", on_done=None):
        """Run bed mesh calibration."""
        self.send_gcode(f"BED_MESH_CALIBRATE PROFILE={profile}", on_done=on_done, timeout=240.0)


    def list_files(self, directory: str = "gcodes", on_done=None):
        """Fetch list of files and subdirectories from Moonraker."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")
        def _run():
            res = {"files": [], "dirs": [], "disk_usage": {}}
            try:
                enc_path = urllib.parse.quote(directory)
                url = f"http://{host}/server/files/directory?path={enc_path}"
                with urllib.request.urlopen(url, timeout=3.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        res = data.get("result", res)
            except Exception:
                pass
            if on_done:
                self._dispatch_signal.emit(lambda: on_done(res))
        threading.Thread(target=_run, daemon=True).start()

    def get_file_metadata(self, filename: str, on_done=None):
        """Fetch slicer metadata and thumbnails for a gcode file."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")
        def _run():
            res = {}
            try:
                enc_fn = urllib.parse.quote(filename)
                url = f"http://{host}/server/files/metadata?filename={enc_fn}"
                with urllib.request.urlopen(url, timeout=3.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        res = data.get("result", {})
            except Exception:
                pass
            if on_done:
                self._dispatch_signal.emit(lambda: on_done(res))
        threading.Thread(target=_run, daemon=True).start()

    def start_print(self, filename: str, on_done=None):
        """Start printing a gcode file immediately via G-code and Moonraker API."""
        clean_fn = filename.replace("gcodes/", "").lstrip("/")

        # 1. Immediate direct Klipper G-code command
        self.send_gcode(f'SDCARD_PRINT_FILE FILENAME="{clean_fn}"')

        # 2. Moonraker API call in background
        target_hosts = []
        if self.active_host:
            target_hosts.append(self.active_host)
        for h in self.hosts:
            if h and h not in target_hosts:
                target_hosts.append(h)

        def _run():
            ok = False
            for target_host in target_hosts:
                try:
                    enc_fn = urllib.parse.quote(clean_fn)
                    body = json.dumps({"filename": clean_fn}).encode("utf-8")
                    url = f"http://{target_host}/printer/print/start?filename={enc_fn}"
                    req = urllib.request.Request(
                        url,
                        data=body,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=5.0) as resp:
                        if resp.status == 200:
                            ok = True
                            break
                except Exception as e:
                    print(f"[Moonraker] start_print error for {target_host}: {e}")

            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def pause_print(self, on_done=None):
        """Pause active print."""
        self.post_endpoint("/printer/print/pause", on_done=on_done, timeout=10.0)

    def resume_print(self, on_done=None):
        """Resume paused print."""
        self.post_endpoint("/printer/print/resume", on_done=on_done, timeout=10.0)

    def cooldown(self, on_done=None):
        """Immediately turn off all heaters and fans."""
        cmd = "TURN_OFF_HEATERS\nM104 S0\nM140 S0\nM106 S0\nSET_HEATER_TEMPERATURE HEATER=extruder TARGET=0\nSET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0"
        self.send_gcode(cmd, on_done=on_done, timeout=5.0)

    def cancel_print(self, on_done=None):
        """Cancel active print immediately and set cooldown straight away."""
        cmd = "TURN_OFF_HEATERS\nM104 S0\nM140 S0\nM106 S0\nCANCEL_PRINT"
        self.send_gcode(cmd)
        self.post_endpoint("/printer/print/cancel", on_done=on_done, timeout=5.0)
        self.cooldown()

    def set_speed_factor(self, percent: int, on_done=None):
        """Set speed factor feedrate override (e.g. 100)."""
        self.send_gcode(f"M220 S{int(percent)}", on_done=on_done)

    def set_flow_factor(self, percent: int, on_done=None):
        """Set extrusion flow rate override (e.g. 100)."""
        self.send_gcode(f"M221 S{int(percent)}", on_done=on_done)

    def set_fan_speed(self, percent: int, on_done=None):
        """Set part cooling fan speed (0 to 100%)."""
        pwm = max(0, min(255, round(percent * 2.55)))
        self.send_gcode(f"M106 S{pwm}", on_done=on_done)

    def adjust_z_offset(self, delta: float, on_done=None):
        """Babystep live Z offset by delta mm."""
        self.send_gcode(f"SET_GCODE_OFFSET Z_ADJUST={delta:+.4f} MOVE=1 MOVE_SPEED=5", on_done=on_done)

    def save_z_offset(self, on_done=None):
        """Apply babystepped Z offset and persist to printer.cfg via SAVE_CONFIG."""
        has_probe = any(k in self.objects for k in ["probe", "bltouch", "load_cell_probe", "smart_effector"])
        if has_probe:
            cmd = "Z_OFFSET_APPLY_PROBE\\nSAVE_CONFIG"
        else:
            cmd = "Z_OFFSET_APPLY_ENDSTOP\\nSAVE_CONFIG"
        self.send_gcode(cmd, on_done=on_done, timeout=20.0)

    def get_printer_cfg(self, on_done=None):
        """Fetch raw printer.cfg content from Moonraker or local filesystem."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            content = ""
            # 1. Try Moonraker API first (single source of truth for config files)
            try:
                url = f"http://{host}/server/files/config/printer.cfg"
                req = urllib.request.Request(url, headers={"User-Agent": "KlipperDisplay"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        content = resp.read().decode("utf-8")
            except Exception:
                pass

            # 2. Fallback to direct local files
            if not content:
                local_paths = [
                    self.firmware_info.get("config_file", ""),
                    os.path.expanduser("~/printer_data/config/printer.cfg"),
                    "/home/pi/printer_data/config/printer.cfg",
                    "/root/printer_data/config/printer.cfg",
                ]
                for lp in local_paths:
                    if lp and os.path.exists(lp):
                        try:
                            with open(lp, "r", encoding="utf-8") as f:
                                content = f.read()
                                if content:
                                    break
                        except Exception:
                            pass

            if on_done:
                self._dispatch_signal.emit(lambda: on_done(content))

        threading.Thread(target=_run, daemon=True).start()

    def save_printer_cfg(self, content: str, on_done=None):
        """Save printer.cfg to Moonraker and local filesystem."""
        host = self.active_host or (self.hosts[0] if self.hosts else "127.0.0.1:7125")

        def _run():
            ok = False
            # 1. Direct local file write if on Linux / Pi
            local_paths = [
                self.firmware_info.get("config_file", ""),
                os.path.expanduser("~/printer_data/config/printer.cfg"),
                "/home/pi/printer_data/config/printer.cfg",
                "/root/printer_data/config/printer.cfg",
            ]
            for lp in local_paths:
                if lp and os.path.exists(lp):
                    try:
                        with open(lp, "w", encoding="utf-8") as f:
                            f.write(content)
                        ok = True
                    except Exception:
                        pass

            # 2. Upload via Moonraker multipart form-data to /server/files/upload
            try:
                boundary = "----KlipperDisplayBoundary" + uuid.uuid4().hex
                raw_bytes = content.encode("utf-8")
                body = bytearray()
                # Field: root=config
                body.extend(f"--{boundary}\r\n".encode("utf-8"))
                body.extend(b'Content-Disposition: form-data; name="root"\r\n\r\n')
                body.extend(b"config\r\n")
                # Field: file=printer.cfg
                body.extend(f"--{boundary}\r\n".encode("utf-8"))
                body.extend(b'Content-Disposition: form-data; name="file"; filename="printer.cfg"\r\n')
                body.extend(b"Content-Type: text/plain\r\n\r\n")
                body.extend(raw_bytes)
                body.extend(b"\r\n")
                body.extend(f"--{boundary}--\r\n".encode("utf-8"))

                req = urllib.request.Request(
                    f"http://{host}/server/files/upload",
                    data=bytes(body),
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Content-Length": str(len(body))
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    if resp.status in (200, 201):
                        ok = True
            except Exception as e:
                print(f"[Moonraker] save_printer_cfg error: {e}")

            if on_done:
                self._dispatch_signal.emit(lambda: on_done(ok))

        threading.Thread(target=_run, daemon=True).start()

    def check_start_gcode_mesh(self, on_done=None):
        """Check if bed mesh is active/unhashed or hashed out in printer.cfg start gcode macro."""
        def _on_cfg(content: str):
            if not content:
                if on_done:
                    on_done(False, False)
                return

            is_configured = "[bed_mesh" in content
            m = re.search(r"\[gcode_macro\s+(?:PRINT_START|START_PRINT)\].*?(?=\n\[|\Z)", content, re.DOTALL | re.IGNORECASE)
            if not m:
                if on_done:
                    on_done(False, is_configured)
                return

            macro_lines = m.group(0).splitlines()
            is_enabled = False
            pattern = re.compile(r"^\s*(#*)\s*(BED_MESH_(?:PROFILE\s+LOAD|CALIBRATE)[^\r\n]*)", re.IGNORECASE)
            for line in macro_lines:
                match = pattern.search(line)
                if match:
                    is_hashed = bool(match.group(1))
                    if not is_hashed:
                        is_enabled = True
                    break

            if on_done:
                on_done(is_enabled, is_configured)

        self.get_printer_cfg(on_done=_on_cfg)

    def toggle_start_gcode_mesh(self, on_done=None):
        """Hash or unhash the bed mesh command in the start gcode macro, save printer.cfg, and restart firmware."""
        def _on_cfg(content: str):
            if not content:
                if on_done:
                    on_done(False)
                return

            m = re.search(r"(\[gcode_macro\s+(?:PRINT_START|START_PRINT)\].*?)(?=\n\[|\Z)", content, re.DOTALL | re.IGNORECASE)
            if not m:
                if on_done:
                    on_done(False)
                return

            macro_full = m.group(1)
            lines = macro_full.splitlines()

            # Find existing bed_mesh line in start macro
            found_idx = -1
            for i, line in enumerate(lines):
                clean = line.strip()
                if re.search(r"bed_mesh_(?:profile\s+load|calibrate)", clean, re.IGNORECASE):
                    found_idx = i
                    break

            if found_idx != -1:
                old_line = lines[found_idx]
                is_currently_hashed = old_line.strip().startswith("#")
                new_state = is_currently_hashed # If hashed -> enable (True), if unhashed -> disable (False)

                if new_state: # Enable -> Unhash
                    clean_cmd = re.sub(r"^\s*#+\s*", "", old_line)
                    lines[found_idx] = f"    {clean_cmd}"
                else: # Disable -> Hash out
                    clean_cmd = re.sub(r"^\s*#*\s*", "", old_line)
                    lines[found_idx] = f"    # {clean_cmd}"
            else:
                # Line wasn't present at all -> insert it enabled
                new_state = True
                insert_idx = -1
                for i, line in enumerate(lines):
                    if re.search(r"G1\s+Z15", line, re.IGNORECASE) or re.search(r"G28\s+Z", line, re.IGNORECASE):
                        insert_idx = i + 1
                if insert_idx == -1:
                    insert_idx = len(lines) - 2
                lines.insert(insert_idx, "    BED_MESH_PROFILE LOAD=default")

            new_macro = "\n".join(lines)
            new_content = content[:m.start(1)] + new_macro + content[m.end(1):]

            def _on_saved(saved_ok: bool):
                if saved_ok:
                    self.firmware_restart()
                if on_done:
                    on_done(new_state)

            self.save_printer_cfg(new_content, on_done=_on_saved)

        self.get_printer_cfg(on_done=_on_cfg)
