"""Non-blocking Moonraker HTTP API client with automatic local/remote failover.

Attempts 127.0.0.1:7125 (on-Pi local) and 192.168.0.99:7125 (Pi 4 over LAN),
polling live temperatures and printer connection state on a background thread.
"""

import json
import threading
import urllib.parse
import urllib.request
from typing import Optional

from .qt import QtCore, Signal

DEFAULT_HOSTS = [
    "127.0.0.1:7125",
    "192.168.0.99:7125",
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

            query_path = "/printer/objects/query?extruder&heater_bed&webhooks&toolhead&gcode_move&load_cell_probe&load_cell&probe"
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

                        # If connected and config not yet fetched, fetch Klipper config in background
                        if not self._config_fetched and k_state == "ready":
                            self._config_fetched = True
                            threading.Thread(target=self._fetch_config_and_objects, args=(host,), daemon=True).start()

                        self.connection_changed.emit(True, host, k_state)
                        self.temps_updated.emit(n_cur, n_tgt, b_cur, b_tgt)
                        self.coords_updated.emit(x_pos, y_pos, z_pos, homed)
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
                cfg_found = cfg_data["result"].get("status", {}).get("configfile", {}).get("settings", {})
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

