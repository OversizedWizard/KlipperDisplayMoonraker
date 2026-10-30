"""Calibration Page: cards for Klipper hardware calibration commands.

Cards are directly touchable (no separate Run button). Touching any card
opens an informative procedural popup explaining prerequisites and steps.
"""

import json
import math
import re
import threading
import time
import urllib.request
from . import icons
from .qt import QtWidgets, QtCore, QtGui, Qt, Signal

def _s(v: float, s: float) -> int:
    return max(1, round(v * s))

CALIBRATION_DETAILS = {
    "probe_cal": {
        "id": "probe_cal",
        "icon": "probe",
        "title": "Probe Calibrate",
        "cmd": "PROBE_CALIBRATE",
        "desc": "Manual paper test for Z offset.",
        "prereqs": "Clean nozzle with no plastic residue. Bed at room or print temperature.",
        "steps": [
            "1. Toolhead moves to bed center and lowers probe.",
            "2. Place a sheet of standard paper under nozzle.",
            "3. Jog Z down with TESTZ Z=-0.1 until slight paper drag is felt.",
            "4. Send ACCEPT and SAVE_CONFIG to store new probe offset."
        ],
        "target_cmd": "PROBE_CALIBRATE"
    },
    "load_cell_cal": {
        "id": "load_cell_cal",
        "icon": "calibrate",
        "title": "Load Cell Calibrate",
        "cmd": "LOAD_CELL_CALIBRATE",
        "desc": "Scale weight calibration & trigger force.",
        "prereqs": "Clean, cold nozzle. Use a known hanging weight (e.g. 100g) OR place a digital scale on the bed under the nozzle.",
        "steps": [
            "1. Run LOAD_CELL_CALIBRATE (ensuring nozzle/sensor is empty).",
            "2. Send ACCEPT to capture zero baseline tare.",
            "3. Hang known weight OR place scale on bed & jog Z to touch scale.",
            "4. Report scale reading / weight in grams (e.g. 100g) and send ACCEPT.",
            "5. Run SAVE_CONFIG to permanently store multiplier in printer.cfg."
        ],
        "target_cmd": "LOAD_CELL_CALIBRATE"
    },
    "load_cell_weight_test": {
        "id": "load_cell_weight_test",
        "icon": "probe",
        "title": "Load Cell Weight Test",
        "cmd": "LOAD_CELL_READ",
        "desc": "Test & read weight attached to probe.",
        "prereqs": "Clean, cold nozzle. Hang test weight or place weight on bed scale.",
        "steps": [
            "1. Probe streams real-time sensor force from printer.load_cell.force_g.",
            "2. Optional: Tap Tare Zero (LOAD_CELL_TARE) to zero empty sensor.",
            "3. Attach known weight or object to probe.",
            "4. Tap Read Attached Weight (LOAD_CELL_READ) to capture static reading."
        ],
        "target_cmd": "LOAD_CELL_READ"
    },
    "bed_mesh": {
        "id": "bed_mesh",
        "icon": "mesh",
        "title": "Bed Mesh Calibrate",
        "cmd": "BED_MESH_CALIBRATE",
        "desc": "Multi-point surface mesh scan.",
        "prereqs": "Pre-heat bed to typical print temp (e.g. 60°C or 100°C) for thermal expansion.",
        "steps": [
            "1. Printer homes all axes (G28).",
            "2. Toolhead probes a calibrated grid across bed surface.",
            "3. Generates 3D topology map to compensate for bed warp.",
            "4. Automatically saves profile to active mesh default."
        ],
        "target_cmd": "BED_MESH_CALIBRATE PROFILE=default"
    },
    "z_offset": {
        "id": "z_offset",
        "icon": "zoffset",
        "title": "Z-Offset Adjust",
        "cmd": "Z_OFFSET_APPLY_PROBE",
        "desc": "Tune first layer nozzle squish.",
        "prereqs": "Babystep adjustments must have been made during an active first layer.",
        "steps": [
            "1. Calculates cumulative live babystep distance.",
            "2. Applies offset permanently to probe Z calibration.",
            "3. Saves to config file without losing physical zero.",
            "4. Run SAVE_CONFIG to persist across reboots."
        ],
        "target_cmd": "Z_OFFSET_APPLY_PROBE"
    },
    "screws_tilt": {
        "id": "screws_tilt",
        "icon": "screws",
        "title": "Screws Tilt Calculate",
        "cmd": "SCREWS_TILT_CALCULATE",
        "desc": "Probe bed thumbscrew levels.",
        "prereqs": "Printer has [screws_tilt_adjust] configured with screw coordinates.",
        "steps": [
            "1. Homes axes and probes reference screw (usually Front-Left).",
            "2. Probes points directly above all remaining bed screws.",
            "3. Calculates clockwise (CW) / counter-clockwise (CCW) knob turns.",
            "4. Example: 'CW 01:15' means rotate knob clockwise 1 hour 15 mins."
        ],
        "target_cmd": "SCREWS_TILT_CALCULATE"
    },
    "z_tilt": {
        "id": "z_tilt",
        "icon": "gantry",
        "title": "Z-Tilt Adjust",
        "cmd": "Z_TILT_ADJUST",
        "desc": "Tram dual/triple independent Z steppers.",
        "prereqs": "Printer has [z_tilt] with 2 or 3 Z stepper motors configured.",
        "steps": [
            "1. Toolhead homes all axes (G28).",
            "2. Probes bed at defined Z-tilt pivot positions.",
            "3. Calculates angular bed tilt between Z leadscrews.",
            "4. Microsteps independent Z steppers until bed is level."
        ],
        "target_cmd": "Z_TILT_ADJUST"
    },
    "quad_gantry_level": {
        "id": "quad_gantry_level",
        "icon": "gantry",
        "title": "Quad Gantry Level",
        "cmd": "QUAD_GANTRY_LEVEL",
        "desc": "Tram 4-corner Voron gantry square.",
        "prereqs": "Voron V2 or 4-motor Z printer. Build surface cleared.",
        "steps": [
            "1. Toolhead probes 4 gantry corners.",
            "2. Measures tilt of gantry frame relative to bed plane.",
            "3. Independently steps each of the 4 Z motors to level frame.",
            "4. Repeats loop until gantry is square within 0.005mm."
        ],
        "target_cmd": "QUAD_GANTRY_LEVEL"
    },
    "qgl_ztilt": {
        "id": "qgl_ztilt",
        "icon": "gantry",
        "title": "Quad Gantry / Z-Tilt",
        "cmd": "QUAD_GANTRY_LEVEL",
        "desc": "Tram multi-Z steppers square.",
        "prereqs": "Ensure build surface is cleared of any printed items or debris.",
        "steps": [
            "1. Probes corners or pivot points across bed.",
            "2. Measures tilt of gantry frame relative to bed plane.",
            "3. Independently steps each Z motor to level the frame.",
            "4. Loops until gantry is square within tolerance."
        ],
        "target_cmd": "QUAD_GANTRY_LEVEL"
    },
    "bed_screws": {
        "id": "bed_screws",
        "icon": "screws",
        "title": "Bed Screws Adjust",
        "cmd": "BED_SCREWS_ADJUST",
        "desc": "Manual corner thumbscrew leveling wizard.",
        "prereqs": "Printer has [bed_screws] configured. Clean nozzle and paper sheet.",
        "steps": [
            "1. Toolhead moves above corner bed adjustment screw.",
            "2. Place paper under nozzle to check friction drag.",
            "3. Adjust thumbscrew knob and send ADJUSTED or ACCEPT.",
            "4. Repeat for all screws until bed is mechanically level."
        ],
        "target_cmd": "BED_SCREWS_ADJUST"
    },
    "probe_acc": {
        "id": "probe_acc",
        "icon": "calibrate",
        "title": "Probe Accuracy Test",
        "cmd": "PROBE_ACCURACY",
        "desc": "Repeatability & deviation test.",
        "prereqs": "Toolhead stationary at desired test position over bed.",
        "steps": [
            "1. Performs 10 consecutive probe samples at current XY.",
            "2. Records trigger height for each individual sample.",
            "3. Calculates maximum difference (range) and standard deviation.",
            "4. A good probe should have a standard deviation below 0.003mm."
        ],
        "target_cmd": "PROBE_ACCURACY SAMPLES=10"
    },
    "input_shaper": {
        "id": "input_shaper",
        "icon": "shaper",
        "title": "Input Shaper (ADXL345)",
        "cmd": "SHAPER_CALIBRATE",
        "desc": "Resonance frequency tuning.",
        "prereqs": "ADXL345 accelerometer connected and securely mounted to toolhead/bed.",
        "steps": [
            "1. Excites motors with frequency sweep vibrations (1Hz to 133Hz).",
            "2. Measures resonance peaks on X axis, then Y axis.",
            "3. Calculates optimal shaper algorithms (MZV, EI, 2HUMP_EI).",
            "4. Generates frequency graphs and suggested shaper settings."
        ],
        "target_cmd": "SHAPER_CALIBRATE"
    },
    "pid_tune": {
        "id": "pid_tune",
        "icon": "nozzle",
        "title": "PID Heater Autotune",
        "cmd": "PID_CALIBRATE",
        "desc": "Heater loop stability tune.",
        "prereqs": "Part cooling fan should be running at 25-50% for realistic load.",
        "steps": [
            "1. Cycles heater on/off around 210°C (extruder) or 60°C (bed).",
            "2. Measures thermal rise time, overshoot, and cooling decay.",
            "3. Calculates optimal Proportional, Integral, Derivative gains.",
            "4. Eliminates temperature fluctuations during printing."
        ],
        "target_cmd": "PID_CALIBRATE HEATER=extruder TARGET=210"
    },
    "axis_twist": {
        "id": "axis_twist",
        "icon": "twist",
        "title": "Axis Twist Compensation",
        "cmd": "AXIS_TWIST_COMPENSATION_CALIBRATE",
        "desc": "Correct X-rail twist skew.",
        "prereqs": "Prepare paper test sheet. Nozzle must be clean.",
        "steps": [
            "1. Guides manual paper test at 3 to 5 points across X axis.",
            "2. Probes the same points using the Z probe.",
            "3. Maps mechanical twist along X extrusion causing probe error.",
            "4. Applies correction curve to all future bed mesh probe points."
        ],
        "target_cmd": "AXIS_TWIST_COMPENSATION_CALIBRATE"
    },
    "endstop_phase": {
        "id": "endstop_phase",
        "icon": "endstop",
        "title": "Endstop Phase Calibrate",
        "cmd": "ENDSTOP_PHASE_CALIBRATE",
        "desc": "Microstep endstop align.",
        "prereqs": "TMC stepper drivers with endstop_phase support in printer.cfg.",
        "steps": [
            "1. Moves axes to endstop triggers across multiple sample homes.",
            "2. Identifies exact stepper full-step phase angle at trigger.",
            "3. Stores offset so future homing always stops on full motor steps.",
            "4. Guarantees 100% layer alignment repeatability across reboots."
        ],
        "target_cmd": "ENDSTOP_PHASE_CALIBRATE"
    },
    "delta_cal": {
        "id": "delta_cal",
        "icon": "delta",
        "title": "Delta Geometry Calibrate",
        "cmd": "DELTA_CALIBRATE",
        "desc": "Calibrate tower geometry.",
        "prereqs": "Delta printer with probe attached. Bed clear of obstructions.",
        "steps": [
            "1. Probes points directly under towers A, B, C.",
            "2. Probes opposite tower positions and center.",
            "3. Numerically solves for tower trim, delta radius, and angles.",
            "4. Ensures flat, level planar travel across entire circular bed."
        ],
        "target_cmd": "DELTA_CALIBRATE"
    },
}

CALIBRATION_LIST = [
    CALIBRATION_DETAILS["probe_cal"],
    CALIBRATION_DETAILS["load_cell_cal"],
    CALIBRATION_DETAILS["z_tilt"],
    CALIBRATION_DETAILS["quad_gantry_level"],
    CALIBRATION_DETAILS["screws_tilt"],
    CALIBRATION_DETAILS["bed_screws"],
    CALIBRATION_DETAILS["bed_mesh"],
    CALIBRATION_DETAILS["input_shaper"],
    CALIBRATION_DETAILS["pid_tune"],
    CALIBRATION_DETAILS["axis_twist"],
    CALIBRATION_DETAILS["endstop_phase"],
    CALIBRATION_DETAILS["delta_cal"],
]

def is_calibration_supported(item_id: str, config: dict = None, objects: list = None) -> bool:
    """Returns True if the calibration or feature is supported by the printer's Klipper config."""
    cfg = config or {}
    objs = objects or []
    kinematics = str(cfg.get("printer", {}).get("kinematics", "")).lower()

    # Delta Geometry Calibration: ONLY show if kinematics is delta
    if item_id == "delta_cal":
        return kinematics == "delta"

    # Load Cell Calibration & Weight Test: ONLY show if printer has load cell probe/sensor
    if item_id in ("load_cell_cal", "load_cell_weight_test"):
        if not cfg and not objs:
            return False
        return any(k in cfg for k in ["load_cell", "load_cell_probe", "load_cell_sensor", "hx711", "ads1220"]) or any("load_cell" in o for o in objs)

    # Quad Gantry Level: ONLY show if printer has quad_gantry_level (e.g. Voron 2.4 4 Z motors)
    if item_id == "quad_gantry_level":
        if not cfg and not objs:
            return False
        return "quad_gantry_level" in cfg or "quad_gantry_level" in objs

    # Z-Tilt: ONLY show if printer has z_tilt (multiple Z motors)
    if item_id == "z_tilt":
        if not cfg and not objs:
            return False
        return "z_tilt" in cfg or "z_tilt" in objs

    if item_id == "qgl_ztilt":
        if not cfg and not objs:
            return False
        return "z_tilt" in cfg or "z_tilt" in objs or "quad_gantry_level" in cfg or "quad_gantry_level" in objs

    # Input Shaper: ONLY show if accelerometer or shaper configured
    if item_id == "input_shaper":
        if not cfg and not objs:
            return False
        return any(k in cfg for k in ["input_shaper", "resonance_tester", "adxl345", "lis2dw", "mpu9250", "bno085"]) or "resonance_tester" in objs

    # Bed Mesh
    if item_id == "bed_mesh":
        if not cfg and not objs:
            return True
        return "bed_mesh" in cfg or "bed_mesh" in objs

    # Screws Tilt Adjust (screws_tilt_adjust)
    if item_id == "screws_tilt":
        if not cfg and not objs:
            return False
        return "screws_tilt_adjust" in cfg or "screws_tilt_adjust" in objs

    # Bed Screws Adjust (bed_screws)
    if item_id == "bed_screws":
        if not cfg and not objs:
            return False
        return "bed_screws" in cfg or "bed_screws" in objs

    # Probe Calibrate / Accuracy / Z-Offset
    if item_id in ("probe_cal", "probe_acc", "z_offset"):
        if not cfg and not objs:
            return True
        return any(k in cfg for k in ["probe", "bltouch", "smart_effector", "beacon", "load_cell_probe"]) or any("probe" in o for o in objs)

    # Axis Twist Compensation
    if item_id == "axis_twist":
        if not cfg and not objs:
            return False
        return "axis_twist_compensation" in cfg or "axis_twist_compensation" in objs

    # Endstop Phase
    if item_id == "endstop_phase":
        if not cfg and not objs:
            return False
        return "endstop_phase" in cfg or "endstop_phase" in objs

    # PID Tune
    if item_id == "pid_tune":
        if not cfg and not objs:
            return True
        return "extruder" in cfg or "heater_bed" in cfg

    return True


class DualRodGantryAnimation(QtWidgets.QWidget):
    """3D Isometric animated printer canvas for Input Shaper resonance frequency test.
    
    Toolhead sweeps on X-axis during X test (±30% from center).
    Heated bed/gantry sweeps on Y-axis during Y test (±30% from center).
    Animation strictly runs ONLY during active calibration and stops when finished.
    """

    def __init__(self, mode: str = "input_shaper", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self._mode = mode     # "input_shaper", "probe_cal", or "load_cell_cal"
        self._axis = "X"      # Active axis: "X" or "Y" (for input shaper)
        self._freq = 15.0     # Live Hz sequence from Klipper terminal
        self._probe_z = 2.0   # Live nozzle Z distance above paper (for probe_cal)
        self._force_g = 0.0   # Live load cell force reading (for load_cell_cal)
        self._target_force = 60 # Stored trigger force in grams (for load_cell_cal)
        self._is_calibrating_weight = False
        self._weight_hanging = False
        self._cal_grams = 100.0
        self._counts_per_gram = 572.3
        self._jog_z_offset = 0.0
        self._phase = 0.0
        self._fan_angle = 0.0
        self._is_running = False
        self._is_paused = False
        self._has_completed = False
        self._sim_mode = False

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(20)  # ~50 FPS
        self._timer.timeout.connect(self._step_animation)

    def set_force(self, force_g: float, target_force: int = None):
        self._force_g = force_g
        if target_force is not None:
            self._target_force = target_force
        self.update()

    def set_weight_calibration(self, is_calibrating: bool, weight_hanging: bool = False, grams: float = 100.0, counts_per_gram: float = 572.3):
        self._is_calibrating_weight = is_calibrating
        self._weight_hanging = weight_hanging
        self._cal_grams = grams
        self._counts_per_gram = counts_per_gram
        self.update()

    def set_jog_z(self, z: float):
        self._jog_z_offset = z
        self.update()

    def set_probe_z(self, z: float):
        self._probe_z = z
        self.update()

    def set_axis(self, axis: str):
        ax = axis.upper()
        if self._axis != ax:
            self._axis = ax
            self.update()

    def set_frequency(self, freq: float):
        self._freq = freq
        self.update()

    def pause_between_axes(self, axis: str = "X"):
        self._is_paused = True
        self._axis = axis.upper()
        self.update()

    def resume_for_axis(self, axis: str = "Y"):
        self._is_paused = False
        self._axis = axis.upper()
        self._phase = 0.0
        self.update()

    def start(self, sim_mode: bool = False):
        self._axis = "X"
        self._freq = 5.0
        self._phase = 0.0
        self._is_running = True
        self._is_paused = False
        self._has_completed = False
        self._sim_mode = sim_mode
        self._timer.start()
        self.update()

    def stop(self, completed: bool = False):
        self._is_running = False
        self._is_paused = False
        self._has_completed = completed
        self._timer.stop()
        self.update()

    def _step_animation(self):
        if self._is_paused:
            return

        self._phase += 0.068
        self._fan_angle = (self._fan_angle + 20) % 360

        if self._sim_mode:
            self._freq += 0.42
            if self._freq > 134.0:
                self._freq = 134.0

        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Dark Chamber Background with subtle radial vignette
        bg_rect = QtCore.QRectF(0, 0, w, h)
        bg_grad = QtGui.QRadialGradient(w * 0.5, h * 0.50, w * 0.75)
        bg_grad.setColorAt(0.0, QtGui.QColor("#131D2E"))
        bg_grad.setColorAt(0.7, QtGui.QColor("#0B101D"))
        bg_grad.setColorAt(1.0, QtGui.QColor("#05080F"))
        painter.setBrush(QtGui.QBrush(bg_grad))

        border_col = QtGui.QColor("#00E5FF") if self._axis == "X" else QtGui.QColor("#10B981")
        if not self._is_running:
            border_col = QtGui.QColor("#34D399") if self._has_completed else QtGui.QColor("#00E5FF")
        elif self._is_paused:
            border_col = QtGui.QColor("#F59E0B")
        painter.setPen(QtGui.QPen(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), 100), 1.5))
        painter.drawRoundedRect(bg_rect.adjusted(1, 1, -1, -1), 10, 10)

        # 2. Isometric Projection Setup (centered in card between top HUD badges and bottom subtitle)
        cx = w * 0.50
        cy = h * 0.66
        sx = w * 0.41
        sy = h * 0.35
        sz = h * 0.43

        def project(px, py, pz):
            sc_x = cx + (px * 0.86 - py * 0.54) * sx
            sc_y = cy + (px * 0.24 + py * 0.38) * sy - pz * sz
            return QtCore.QPointF(sc_x, sc_y)

        # Movement: toolhead moves X for X test, entire gantry moves Y for Y test.
        # Both strictly limited to ±30% back and forth from center!
        travel_limit = 0.30
        if self._mode in ("probe_cal", "load_cell_cal"):
            toolhead_x = 0.0
            gantry_y = 0.0
            if self._mode == "probe_cal":
                if self._is_running:
                    # Lower nozzle towards paper sheet based on probe Z
                    z_clamped = max(0.0, min(2.5, self._probe_z))
                    gantry_z = 0.285 + (z_clamped / 2.5) * 0.105
                else:
                    gantry_z = 0.38
            else:  # load_cell_cal
                if self._is_calibrating_weight:
                    if self._weight_hanging:
                        jog_clamped = max(-2.0, min(2.0, self._jog_z_offset))
                        gantry_z = 0.32 + (jog_clamped * 0.04)
                    else:
                        gantry_z = 0.50  # Raised high above bed for empty tare
                elif self._is_running:
                    gantry_z = 0.285  # Nozzle touching bed surface
                else:
                    gantry_z = 0.36
        else:
            if self._is_running and not self._is_paused:
                vib_amp = min(0.025, (self._freq / 134.0) * 0.025)
                vib = math.sin(self._phase * 8.0) * vib_amp
                if self._axis == "X":
                    toolhead_x = math.sin(self._phase) * travel_limit + vib
                    gantry_y = 0.0
                else:
                    toolhead_x = 0.0
                    gantry_y = math.sin(self._phase) * travel_limit + vib
            else:
                toolhead_x = 0.0
                gantry_y = 0.0
            gantry_z = 0.42

        # 3. Base Frame Floor
        corners_base = [
            (-0.85, -0.75, 0.0),
            (0.85, -0.75, 0.0),
            (0.85, 0.75, 0.0),
            (-0.85, 0.75, 0.0)
        ]
        base_poly = QtGui.QPolygonF([project(x, y, z) for x, y, z in corners_base])
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 2))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0B101D")))
        painter.drawPolygon(base_poly)

        # 4. Heated Bed Assembly (stays centered on build floor)
        bed_w = 0.70
        bed_d = 0.62
        bed_corners = [
            (-bed_w, -bed_d, 0.04),
            (bed_w, -bed_d, 0.04),
            (bed_w, bed_d, 0.04),
            (-bed_w, bed_d, 0.04)
        ]
        bed_poly = QtGui.QPolygonF([project(x, y, z) for x, y, z in bed_corners])

        # Skirt
        bed_bot = [project(x, y, 0.01) for x, y, z in bed_corners]
        skirt_poly = QtGui.QPolygonF([bed_bot[3], bed_bot[2], bed_poly[2], bed_poly[3]])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.drawPolygon(skirt_poly)

        # Bed surface
        bed_grad = QtGui.QLinearGradient(bed_poly[0], bed_poly[2])
        bed_grad.setColorAt(0.0, QtGui.QColor("#1A2130"))
        bed_grad.setColorAt(0.5, QtGui.QColor("#242F42"))
        bed_grad.setColorAt(1.0, QtGui.QColor("#161D2A"))
        bed_border = QtGui.QColor("#38BDF8")

        painter.setPen(QtGui.QPen(QtGui.QColor(bed_border.red(), bed_border.green(), bed_border.blue(), 130), 1.5))
        painter.setBrush(QtGui.QBrush(bed_grad))
        painter.drawPolygon(bed_poly)

        # PEI Grid lines
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
        for gx_step in range(-3, 4):
            gx = (bed_w * gx_step) / 3.0
            painter.drawLine(project(gx, -bed_d, 0.04), project(gx, bed_d, 0.04))
        for gy_step in range(-3, 4):
            gy = (bed_d * gy_step) / 3.0
            painter.drawLine(project(-bed_w, gy, 0.04), project(bed_w, gy, 0.04))

        # Paper sheet on bed center (for Probe Calibrate paper test)
        if self._mode == "probe_cal":
            pw, pd = 0.32, 0.26
            paper_corners = [
                (-pw, -pd, 0.045),
                (pw, -pd, 0.045),
                (pw, pd, 0.045),
                (-pw, pd, 0.045)
            ]
            paper_poly = QtGui.QPolygonF([project(x, y, z) for x, y, z in paper_corners])
            painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 1.2))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
            painter.drawPolygon(paper_poly)
            p_ctr = project(0.0, 0.0, 0.046)
            painter.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
            painter.setPen(QtGui.QPen(QtGui.QColor("#64748B")))
            painter.drawText(QtCore.QRectF(p_ctr.x() - 45, p_ctr.y() - 8, 90, 16), Qt.AlignmentFlag.AlignCenter, "TEST PAPER")

        # Digital scale on bed center (for Load Cell Scale Calibration) or force ring
        if self._mode == "load_cell_cal":
            if self._is_calibrating_weight:
                # Digital scale body on bed surface
                sc_w, sc_d = 0.36, 0.30
                scale_corners = [
                    (-sc_w, -sc_d, 0.05),
                    (sc_w, -sc_d, 0.05),
                    (sc_w, sc_d, 0.05),
                    (-sc_w, sc_d, 0.05)
                ]
                sc_poly = QtGui.QPolygonF([project(x, y, z) for x, y, z in scale_corners])
                sc_bot = [project(x, y, 0.04) for x, y, z in scale_corners]
                sc_skirt = QtGui.QPolygonF([sc_bot[3], sc_bot[2], sc_poly[2], sc_poly[3]])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
                painter.drawPolygon(sc_skirt)

                sc_grad = QtGui.QLinearGradient(sc_poly[0], sc_poly[2])
                sc_grad.setColorAt(0.0, QtGui.QColor("#1E293B"))
                sc_grad.setColorAt(1.0, QtGui.QColor("#334155"))
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8"), 1.2))
                painter.setBrush(QtGui.QBrush(sc_grad))
                painter.drawPolygon(sc_poly)

                # Weighing Disc on Scale Platform
                disc_pt = project(0.0, -0.04, 0.055)
                painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF"), 1.5))
                painter.setBrush(QtGui.QBrush(QtGui.QColor("#475569")))
                painter.drawEllipse(disc_pt, 24, 13)

                if self._weight_hanging:
                    pulse_r = 24 + (self._phase * 8.0) % 22
                    pulse_a = max(0, int(180 - (pulse_r - 24) * 8))
                    painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, pulse_a), 1.5))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(disc_pt, pulse_r, pulse_r * 0.55)

                # Digital LCD Screen on front of scale
                lcd_pt = project(0.0, 0.16, 0.055)
                lcd_rect = QtCore.QRectF(lcd_pt.x() - 32, lcd_pt.y() - 8, 64, 16)
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8"), 1))
                painter.setBrush(QtGui.QBrush(QtGui.QColor("#0B101D")))
                painter.drawRoundedRect(lcd_rect, 3, 3)

                painter.setFont(QtGui.QFont("Consolas", 8, QtGui.QFont.Weight.Bold))
                painter.setPen(QtGui.QPen(QtGui.QColor("#34D399" if self._weight_hanging else "#38BDF8")))
                lcd_val = f"{int(self._cal_grams)}.0g" if self._weight_hanging else "0.0g"
                painter.drawText(lcd_rect, Qt.AlignmentFlag.AlignCenter, lcd_val)
            else:
                contact_pt = project(0.0, 0.0, 0.045)
                painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF" if self._is_running else "#38BDF8"), 1.5))
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 229, 255, 45 if self._is_running else 20)))
                painter.drawEllipse(contact_pt, 24, 13)
                if self._is_running:
                    pulse_r = 24 + (self._phase * 8.0) % 26
                    pulse_a = max(0, int(180 - (pulse_r - 24) * 6))
                    painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, pulse_a), 1.5))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(contact_pt, pulse_r, pulse_r * 0.55)
                painter.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8")))
                painter.drawText(QtCore.QRectF(contact_pt.x() - 45, contact_pt.y() - 8, 90, 16), Qt.AlignmentFlag.AlignCenter, "FORCE SENSOR")

        # 5. Upright Extrusions
        z_top = 0.80
        rl_bot, rl_top = project(-0.85, -0.75, 0.0), project(-0.85, -0.75, z_top)
        rr_bot, rr_top = project(0.85, -0.75, 0.0), project(0.85, -0.75, z_top)
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(rl_bot, rl_top)
        painter.drawLine(rr_bot, rr_top)
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawLine(rl_top, rr_top)

        # 6. Y-Axis Linear Guide Rails (along which the entire gantry slides in Y)
        for yrx in (-0.85, 0.85):
            y_rail_start = project(yrx, -0.75, gantry_z)
            y_rail_end = project(yrx, 0.75, gantry_z)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(y_rail_start, y_rail_end)
            painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(y_rail_start, y_rail_end)

        # Dual Chrome X-Rods (slide along Y with gantry_y!)
        rod_z1 = gantry_z + 0.06
        rod_z2 = gantry_z - 0.06
        rod_y = gantry_y

        p_left_top, p_right_top = project(-0.85, rod_y, rod_z1), project(0.85, rod_y, rod_z1)
        p_left_bot, p_right_bot = project(-0.85, rod_y, rod_z2), project(0.85, rod_y, rod_z2)

        # Side brackets (slide along the Y linear rails!)
        for bx in (-0.85, 0.85):
            b_p1 = project(bx, rod_y, rod_z1 + 0.07)
            b_p2 = project(bx, rod_y, rod_z2 - 0.07)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(b_p1, b_p2)
            painter.setPen(QtGui.QPen(border_col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(b_p1, b_p2)

        # Bottom rod
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p_left_bot, p_right_bot)
        painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p_left_bot, p_right_bot)

        # Belt
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 3))
        painter.drawLine(project(-0.85, rod_y, gantry_z), project(0.85, rod_y, gantry_z))

        # Top rod
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p_left_top, p_right_top)
        painter.setPen(QtGui.QPen(QtGui.QColor("#F1F5F9"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p_left_top, p_right_top)

        # 7. 3D Moving Toolhead Carriage
        tx_w = 0.15
        ty_d = 0.13
        tz_h = 0.17

        c_corners = [
            project(toolhead_x - tx_w, rod_y - ty_d, gantry_z - tz_h),
            project(toolhead_x + tx_w, rod_y - ty_d, gantry_z - tz_h),
            project(toolhead_x + tx_w, rod_y + ty_d, gantry_z - tz_h),
            project(toolhead_x - tx_w, rod_y + ty_d, gantry_z - tz_h),
            project(toolhead_x - tx_w, rod_y - ty_d, gantry_z + tz_h),
            project(toolhead_x + tx_w, rod_y - ty_d, gantry_z + tz_h),
            project(toolhead_x + tx_w, rod_y + ty_d, gantry_z + tz_h),
            project(toolhead_x - tx_w, rod_y + ty_d, gantry_z + tz_h)
        ]

        front_poly = QtGui.QPolygonF([c_corners[3], c_corners[2], c_corners[6], c_corners[7]])
        top_poly = QtGui.QPolygonF([c_corners[4], c_corners[5], c_corners[6], c_corners[7]])
        right_poly = QtGui.QPolygonF([c_corners[2], c_corners[1], c_corners[5], c_corners[6]])

        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.drawPolygon(right_poly)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#334155")))
        painter.drawPolygon(top_poly)

        front_grad = QtGui.QLinearGradient(c_corners[7], c_corners[2])
        front_grad.setColorAt(0.0, QtGui.QColor("#1E293B"))
        front_grad.setColorAt(0.5, QtGui.QColor("#2B384B"))
        front_grad.setColorAt(1.0, QtGui.QColor("#0F172A"))
        painter.setPen(QtGui.QPen(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), 200), 1.5))
        painter.setBrush(QtGui.QBrush(front_grad))
        painter.drawPolygon(front_poly)

        # ADXL345 Sensor on Top
        adxl_pos = project(toolhead_x, rod_y, gantry_z + tz_h + 0.02)
        painter.setPen(QtGui.QPen(QtGui.QColor("#34D399"), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#047857")))
        painter.drawRoundedRect(QtCore.QRectF(adxl_pos.x() - 7, adxl_pos.y() - 4, 14, 7), 2, 2)

        if self._is_running:
            pulse_a = int(140 + 80 * math.sin(self._phase * 4.0))
            painter.setPen(QtGui.QPen(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), pulse_a), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QtCore.QRectF(adxl_pos.x() - 12, adxl_pos.y() - 12, 24, 16), 30 * 16, 120 * 16)
            painter.drawArc(QtCore.QRectF(adxl_pos.x() - 18, adxl_pos.y() - 18, 36, 24), 40 * 16, 100 * 16)

        # Spinning Fan
        fan_center = project(toolhead_x, rod_y + ty_d + 0.01, gantry_z)
        fan_r = 9.0
        painter.setPen(QtGui.QPen(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), 120), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0B101D")))
        painter.drawEllipse(fan_center, fan_r, fan_r)

        painter.save()
        painter.translate(fan_center)
        painter.rotate(self._fan_angle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#38BDF8")))
        for _ in range(4):
            painter.rotate(90)
            painter.drawRoundedRect(QtCore.QRectF(-2, -fan_r + 1, 4, fan_r - 2), 1, 1)
        painter.restore()

        # Brass Nozzle
        nozzle_top = project(toolhead_x, rod_y, gantry_z - tz_h)
        nozzle_tip = project(toolhead_x, rod_y, gantry_z - tz_h - 0.07)
        painter.setPen(QtGui.QPen(QtGui.QColor("#F59E0B"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(nozzle_top, nozzle_tip)

        if self._mode == "probe_cal":
            # Touch Probe body & pin on side of toolhead
            pr_x = toolhead_x - 0.09
            pr_top = project(pr_x, rod_y, gantry_z - tz_h + 0.05)
            pr_bot = project(pr_x, rod_y, gantry_z - tz_h - 0.03)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(pr_top, pr_bot)
            painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(pr_top, pr_bot)

            # Probe pin tip (triggered = red when near paper, deployed = cyan)
            is_triggered = (self._is_running and self._probe_z <= 0.15)
            pin_tip_z = gantry_z - tz_h - (0.05 if is_triggered else 0.07)
            pin_tip = project(pr_x, rod_y, pin_tip_z)
            pin_col = QtGui.QColor("#EF4444") if is_triggered else QtGui.QColor("#00E5FF")
            painter.setPen(QtGui.QPen(pin_col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(pr_bot, pin_tip)
        elif self._mode == "load_cell_cal":
            # Strain gauge sensor chip on toolhead mount
            lc_pos = project(toolhead_x, rod_y, gantry_z - tz_h + 0.03)
            painter.setPen(QtGui.QPen(QtGui.QColor("#34D399"), 1))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#065F46" if self._is_running else "#047857")))
            painter.drawRoundedRect(QtCore.QRectF(lc_pos.x() - 8, lc_pos.y() - 5, 16, 10), 2, 2)
            # Glowing micro strain indicator
            led_col = QtGui.QColor("#34D399" if not self._is_running else "#00E5FF")
            if self._is_calibrating_weight and self._weight_hanging:
                led_col = QtGui.QColor("#F59E0B")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(led_col))
            painter.drawEllipse(QtCore.QRectF(lc_pos.x() - 2, lc_pos.y() - 2, 4, 4))

            if self._is_calibrating_weight:
                if self._weight_hanging:
                    # Contact point on scale disc with downward tension arrows
                    contact_pt = project(toolhead_x, rod_y, gantry_z - tz_h - 0.07)
                    painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF"), 2))
                    painter.setBrush(QtGui.QBrush(QtGui.QColor("#38BDF8")))
                    painter.drawEllipse(contact_pt, 6, 3)

                    # Downward pressure force arrows
                    painter.setPen(QtGui.QPen(QtGui.QColor("#EF4444"), 2))
                    for ax_offset in (-24, 24):
                        x_arr = contact_pt.x() + ax_offset
                        painter.drawLine(QtCore.QPointF(x_arr, contact_pt.y() - 14), QtCore.QPointF(x_arr, contact_pt.y() + 4))
                        painter.drawLine(QtCore.QPointF(x_arr, contact_pt.y() + 4), QtCore.QPointF(x_arr - 3, contact_pt.y() - 1))
                        painter.drawLine(QtCore.QPointF(x_arr, contact_pt.y() + 4), QtCore.QPointF(x_arr + 3, contact_pt.y() - 1))
                else:
                    # Empty clearance circle
                    empty_pt = QtCore.QPointF(nozzle_tip.x(), nozzle_tip.y() + 18)
                    painter.setPen(QtGui.QPen(QtGui.QColor("#34D399"), 1.2, Qt.PenStyle.DashLine))
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(52, 211, 153, 25)))
                    painter.drawEllipse(empty_pt, 20, 10)
                    painter.setFont(QtGui.QFont("Segoe UI", 7, QtGui.QFont.Weight.Bold))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#34D399")))
                    painter.drawText(QtCore.QRectF(empty_pt.x() - 35, empty_pt.y() - 6, 70, 12), Qt.AlignmentFlag.AlignCenter, "EMPTY (0g)")

        # 8. Motion Subtitle
        painter.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Weight.Bold))
        if self._mode == "load_cell_cal":
            if self._has_completed:
                arrow_str = "\u2713 LOAD CELL SCALE CALIBRATED \u2022 READY TO SAVE CONFIG"
                painter.setPen(QtGui.QPen(QtGui.QColor("#34D399")))
            elif self._is_calibrating_weight:
                if self._weight_hanging:
                    arrow_str = f"\u25BC NOZZLE TOUCHING BED SCALE \u2022 READING: {int(self._cal_grams)}g \u25BC"
                    painter.setPen(QtGui.QPen(QtGui.QColor("#F59E0B")))
                else:
                    arrow_str = "STEP 1: SENSOR EMPTY \u2022 SEND ACCEPT TO CAPTURE ZERO"
                    painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF")))
            elif self._is_running:
                arrow_str = "\u25BC NOZZLE TOUCH CONTACT \u2022 MEASURING STRAIN FORCE \u25BC"
                painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF")))
            else:
                arrow_str = "READY \u2022 LOAD CELL TARED AT BED CENTER"
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8")))
        elif self._mode == "probe_cal":
            if self._has_completed:
                arrow_str = "\u2713 PROBE Z-OFFSET ACCEPTED \u2022 READY TO SAVE CONFIG"
                painter.setPen(QtGui.QPen(QtGui.QColor("#34D399")))
            elif self._is_running:
                arrow_str = "\u25BC PAPER TEST \u2022 JOG Z UNTIL SLIGHT DRAG FELT \u25BC"
                painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF")))
            else:
                arrow_str = "READY \u2022 NOZZLE & PAPER AT BED CENTER"
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8")))
        else:
            if self._is_paused:
                if self._axis == "X":
                    arrow_str = "X-AXIS COMPLETE \u2022 READYING Y-AXIS"
                else:
                    arrow_str = "VIBRATIONS COMPLETE \u2022 CALCULATING SHAPERS"
                painter.setPen(QtGui.QPen(QtGui.QColor("#F59E0B")))
            elif self._is_running:
                if self._axis == "X":
                    arrow_str = "\u25C0 \u25C0  \u00B130% X GANTRY TRAVEL  \u25B6 \u25B6"
                    painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF")))
                else:
                    arrow_str = "\u25B2 \u25BC  \u00B130% Y GANTRY TRAVEL  \u25B2 \u25BC"
                    painter.setPen(QtGui.QPen(QtGui.QColor("#10B981")))
            elif self._has_completed:
                arrow_str = "\u2713 TEST COMPLETE \u2022 READY TO SAVE CONFIG"
                painter.setPen(QtGui.QPen(QtGui.QColor("#34D399")))
            else:
                arrow_str = "READY \u2022 TOOLHEAD & BED AT REST"
                painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8")))
        painter.drawText(QtCore.QRectF(6, h - 24, w - 12, 18), Qt.AlignmentFlag.AlignCenter, arrow_str)

        # 9. 3D HUD Overlay
        badge_rect = QtCore.QRectF(8, 8, 122, 24)
        if self._mode == "load_cell_cal":
            if self._has_completed:
                border_col = QtGui.QColor("#34D399")
                badge_text = "CALIBRATED"
                hud_hz = f"{self._counts_per_gram:.1f} c/g"
            elif self._is_calibrating_weight:
                if self._weight_hanging:
                    border_col = QtGui.QColor("#F59E0B")
                    badge_text = "SCALE READING"
                    hud_hz = f"APPLIED: {int(self._cal_grams)}g"
                else:
                    border_col = QtGui.QColor("#00E5FF")
                    badge_text = "EMPTY NOZZLE"
                    hud_hz = "TARE: 0.0g"
            elif self._is_running:
                border_col = QtGui.QColor("#00E5FF")
                badge_text = "LOAD CELL"
                hud_hz = f"FORCE: {self._force_g:+.1f}g"
            else:
                border_col = QtGui.QColor("#00E5FF")
                badge_text = "READY"
                hud_hz = f"TARGET: {self._target_force}g"
        elif self._mode == "probe_cal":
            if self._has_completed:
                border_col = QtGui.QColor("#34D399")
                badge_text = "FINISHED"
                hud_hz = "CALIBRATED"
            elif self._is_running:
                border_col = QtGui.QColor("#00E5FF")
                badge_text = "MANUAL PROBE"
                hud_hz = f"Z: {self._probe_z:+.3f}"
            else:
                border_col = QtGui.QColor("#00E5FF")
                badge_text = "READY"
                hud_hz = ""
        else:
            if self._is_paused:
                border_col = QtGui.QColor("#F59E0B")
                badge_text = "PAUSED (X DONE)" if self._axis == "X" else "CALCULATING"
                hud_hz = "PAUSED"
            elif self._is_running:
                border_col = QtGui.QColor("#00E5FF") if self._axis == "X" else QtGui.QColor("#10B981")
                badge_text = f"{self._axis}-AXIS TEST"
                hud_hz = f"LIVE: {self._freq:g} Hz"
            elif self._has_completed:
                border_col = QtGui.QColor("#34D399")
                badge_text = "FINISHED"
                hud_hz = "COMPLETE"
            else:
                border_col = QtGui.QColor("#00E5FF")
                badge_text = "READY"
                hud_hz = ""

        painter.setPen(QtGui.QPen(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), 100), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(border_col.red(), border_col.green(), border_col.blue(), 30)))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setFont(QtGui.QFont("Consolas", 10, QtGui.QFont.Weight.Bold))
        painter.setPen(QtGui.QPen(border_col))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        if hud_hz:
            painter.setFont(QtGui.QFont("Consolas", 11, QtGui.QFont.Weight.Bold))
            painter.setPen(QtGui.QPen(QtGui.QColor("#F8FAFC")))
            painter.drawText(QtCore.QRectF(w - 130, 10, 120, 20), Qt.AlignmentFlag.AlignRight, hud_hz)


class CalibrationDialog(QtWidgets.QFrame):
    """Full-screen in-window touch view explaining calibration procedure with live animations."""
    closed = Signal()

    def _get_moonraker(self):
        p = self.parent()
        while p is not None:
            mr = getattr(p, "moonraker", None)
            if mr:
                return mr
            p = getattr(p, "parent", lambda: None)()
        win = self.window()
        mr = getattr(win, "moonraker", None)
        if mr:
            return mr
        app = QtWidgets.QApplication.instance()
        if app:
            for top in app.topLevelWidgets():
                mr = getattr(top, "moonraker", None)
                if mr:
                    return mr
        return None

    def __init__(self, item: dict, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.item = item
        self.scale = scale
        self.is_calibrating = False
        self._stored_trigger_force = 60
        self._target_force = 60
        self._live_force_g = 0.0
        self._tare_counts = 313744
        self._counts_per_gram = 572.3
        self._is_lc_saving = False
        self._is_calibrating_lc = False
        self._known_grams = 100
        self._scale_step = 1
        self._active_lc_tab = "scale"
        self._jog_z_cum = 0.0

        self.setObjectName("CalDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Card container
        self.card = QtWidgets.QFrame()
        self.card.setObjectName("DialogCard")
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        outer.addWidget(self.card)

        layout = QtWidgets.QVBoxLayout(self.card)

        # Header Row: Icon + Title + GCode badge
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(_s(12, scale))

        self.icon_lbl = QtWidgets.QLabel()
        self.icon_lbl.setPixmap(icons.pixmap(item["icon"], _s(44, scale)))
        self.icon_lbl.setFixedSize(_s(48, scale), _s(48, scale))
        hdr.addWidget(self.icon_lbl)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(2)
        self.title_lbl = QtWidgets.QLabel(item["title"])
        self.title_lbl.setObjectName("DialogTitle")
        title_col.addWidget(self.title_lbl)

        badge_row = QtWidgets.QHBoxLayout()
        self.cmd_lbl = QtWidgets.QLabel(item["cmd"])
        self.cmd_lbl.setObjectName("CalCmdBadge")
        badge_row.addWidget(self.cmd_lbl)
        badge_row.addStretch(1)
        title_col.addLayout(badge_row)

        hdr.addLayout(title_col, 1)

        # Close X button
        close_x = QtWidgets.QPushButton("\u2715")
        close_x.setObjectName("DialogCloseX")
        close_x.setCursor(Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(self._on_close)
        hdr.addWidget(close_x, 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(hdr)

        # Stacked Widget: Page 0 = Steps/Prereqs, Page 1 = Active Gantry Animation
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack, 1)

        # --- Page 0: Info (Prereqs & Procedure) ---
        self.info_page = QtWidgets.QWidget()
        info_lay = QtWidgets.QVBoxLayout(self.info_page)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(_s(8, scale))

        # Prereqs Box
        prereq_box = QtWidgets.QFrame()
        prereq_box.setObjectName("DialogInfoBox")
        prereq_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        p_lay = QtWidgets.QVBoxLayout(prereq_box)
        p_lay.setContentsMargins(_s(12, scale), _s(8, scale), _s(12, scale), _s(8, scale))
        p_lay.setSpacing(2)

        p_hdr = QtWidgets.QLabel("\u26A0  PREREQUISITES")
        p_hdr.setObjectName("DialogSectionHdr")
        p_lay.addWidget(p_hdr)

        p_txt = QtWidgets.QLabel(item["prereqs"])
        p_txt.setObjectName("DialogSectionTxt")
        p_txt.setWordWrap(True)
        p_lay.addWidget(p_txt)
        info_lay.addWidget(prereq_box)

        # Steps Box
        steps_box = QtWidgets.QFrame()
        steps_box.setObjectName("DialogStepsBox")
        steps_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        s_lay = QtWidgets.QVBoxLayout(steps_box)
        s_lay.setContentsMargins(_s(12, scale), _s(8, scale), _s(12, scale), _s(8, scale))
        s_lay.setSpacing(4)

        s_hdr = QtWidgets.QLabel("PROCEDURE")
        s_hdr.setObjectName("DialogSectionHdr")
        s_lay.addWidget(s_hdr)

        for step in item["steps"]:
            step_lbl = QtWidgets.QLabel(step)
            step_lbl.setObjectName("DialogStepLine")
            step_lbl.setWordWrap(True)
            s_lay.addWidget(step_lbl)

        info_lay.addWidget(steps_box, 1)
        self.stack.addWidget(self.info_page)

        # --- Page 1: Input Shaper Active & Results (Split: 3D Left, Info Right) ---
        self.cal_page = QtWidgets.QWidget()
        cal_split_lay = QtWidgets.QHBoxLayout(self.cal_page)
        cal_split_lay.setContentsMargins(0, 0, 0, 0)
        cal_split_lay.setSpacing(_s(12, scale))

        # LEFT SIDE: 3D Isometric Gantry & Bed Animation (Paused at rest during procedure view)
        cal_mode = "input_shaper"
        if item.get("id") == "probe_cal":
            cal_mode = "probe_cal"
        elif item.get("id") == "load_cell_cal":
            cal_mode = "load_cell_cal"
        self.gantry_anim = DualRodGantryAnimation(mode=cal_mode, parent=self.cal_page)
        cal_split_lay.addWidget(self.gantry_anim, 12)

        # RIGHT SIDE: Stacked panel (Page 0: Procedure, Page 1: Live Telemetry, Page 2: Completed Results)
        self.right_stack = QtWidgets.QStackedWidget()
        cal_split_lay.addWidget(self.right_stack, 10)

        # Right Stack - Page 0: Prerequisites & Procedure Steps (Initial Paused View)
        self.procedure_panel = QtWidgets.QWidget()
        proc_lay = QtWidgets.QVBoxLayout(self.procedure_panel)
        proc_lay.setContentsMargins(0, 0, 0, 0)
        proc_lay.setSpacing(_s(6, scale))

        prereq_box_side = QtWidgets.QFrame()
        prereq_box_side.setObjectName("DialogInfoBox")
        prereq_box_side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        p_side_lay = QtWidgets.QVBoxLayout(prereq_box_side)
        p_side_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        p_side_lay.setSpacing(3)

        p_side_hdr = QtWidgets.QLabel("\u26A0  PREREQUISITES")
        p_side_hdr.setObjectName("DialogSectionHdr")
        p_side_hdr.setStyleSheet("font-size: 13px; font-weight: 800; color: #F59E0B;")
        p_side_lay.addWidget(p_side_hdr)

        p_side_txt = QtWidgets.QLabel(item["prereqs"])
        p_side_txt.setObjectName("DialogSectionTxt")
        p_side_txt.setStyleSheet("font-size: 12px; color: #E2E8F0; line-height: 1.3;")
        p_side_txt.setWordWrap(True)
        p_side_lay.addWidget(p_side_txt)
        proc_lay.addWidget(prereq_box_side)

        steps_box_side = QtWidgets.QFrame()
        steps_box_side.setObjectName("DialogStepsBox")
        steps_box_side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        s_side_lay = QtWidgets.QVBoxLayout(steps_box_side)
        s_side_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        s_side_lay.setSpacing(4)

        s_side_hdr = QtWidgets.QLabel("PROCEDURE")
        s_side_hdr.setObjectName("DialogSectionHdr")
        s_side_hdr.setStyleSheet("font-size: 13px; font-weight: 800; color: #00E5FF;")
        s_side_lay.addWidget(s_side_hdr)

        for step in item["steps"]:
            step_lbl = QtWidgets.QLabel(step)
            step_lbl.setObjectName("DialogStepLine")
            step_lbl.setStyleSheet("font-size: 12px; color: #CBD5E1;")
            step_lbl.setWordWrap(True)
            s_side_lay.addWidget(step_lbl)

        proc_lay.addWidget(steps_box_side, 1)
        self.right_stack.addWidget(self.procedure_panel)

        # Right Stack - Page 1: Movements & Live Frequency Telemetry (While Running)
        self.telemetry_page = QtWidgets.QWidget()
        t_lay = QtWidgets.QVBoxLayout(self.telemetry_page)
        t_lay.setContentsMargins(0, 0, 0, 0)
        t_lay.setSpacing(_s(6, scale))

        self.axis_lbl = QtWidgets.QLabel("CURRENT AXIS: X-AXIS RESONANCE")
        self.axis_lbl.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 15px;")
        t_lay.addWidget(self.axis_lbl)

        # Live Frequency Readout Card
        hz_box = QtWidgets.QFrame()
        hz_box.setObjectName("DialogInfoBox")
        hz_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hz_box.setStyleSheet(
            "QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        hz_lay = QtWidgets.QVBoxLayout(hz_box)
        hz_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        hz_lay.setSpacing(1)

        hz_hdr = QtWidgets.QLabel("LIVE FREQUENCY SWEEP")
        hz_hdr.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 800;")
        hz_lay.addWidget(hz_hdr)

        self.big_hz_lbl = QtWidgets.QLabel("5 Hz")
        self.big_hz_lbl.setStyleSheet("color: #FFFFFF; font-size: 36px; font-weight: 900; font-family: 'Consolas', monospace;")
        hz_lay.addWidget(self.big_hz_lbl)
        t_lay.addWidget(hz_box)

        # Frequency Sweep Range Progress Bar (Klipper sweeps 5 Hz to 134 Hz)
        prog_row = QtWidgets.QHBoxLayout()
        prog_row.setSpacing(4)
        p_min = QtWidgets.QLabel("5 Hz")
        p_min.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700;")
        prog_row.addWidget(p_min)

        self.freq_pbar = QtWidgets.QProgressBar()
        self.freq_pbar.setFixedHeight(_s(11, scale))
        self.freq_pbar.setRange(5, 135)
        self.freq_pbar.setValue(5)
        self.freq_pbar.setTextVisible(False)
        self.freq_pbar.setStyleSheet("""
            QProgressBar { background: #1E293B; border-radius: 5px; border: none; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #38BDF8); border-radius: 5px; }
        """)
        prog_row.addWidget(self.freq_pbar, 1)

        p_max = QtWidgets.QLabel("135 Hz")
        p_max.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700;")
        prog_row.addWidget(p_max)
        t_lay.addLayout(prog_row)

        # Movements & Accelerometer Status Info Box
        info_card = QtWidgets.QFrame()
        info_card.setObjectName("DialogStepsBox")
        info_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        info_card.setStyleSheet("QFrame#DialogStepsBox { background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 18); border-radius: 8px; } QLabel { border: none; background: transparent; }")
        ic_lay = QtWidgets.QVBoxLayout(info_card)
        ic_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        ic_lay.setSpacing(3)

        m_line1 = QtWidgets.QLabel("\u2022 Motion: \u00B130% center amplitude")
        m_line1.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 600;")
        ic_lay.addWidget(m_line1)

        m_line2 = QtWidgets.QLabel("\u2022 Sensor: ADXL345 (SPI Active)")
        m_line2.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        ic_lay.addWidget(m_line2)

        self.telemetry_terminal_lbl = QtWidgets.QLabel("\u2022 Terminal: Initializing shaper sweep...")
        self.telemetry_terminal_lbl.setStyleSheet("color: #38BDF8; font-size: 12px; font-family: 'Consolas', monospace;")
        self.telemetry_terminal_lbl.setWordWrap(True)
        ic_lay.addWidget(self.telemetry_terminal_lbl)
        t_lay.addWidget(info_card)

        self.status_bar_lbl = QtWidgets.QLabel("Sweeping resonance vibrations...")
        self.status_bar_lbl.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 700; padding: 2px;")
        t_lay.addWidget(self.status_bar_lbl)
        t_lay.addStretch(1)

        self.right_stack.addWidget(self.telemetry_page)

        # Right Stack - Page 2: Calibration Results & Save Prompt (when finished)
        self.results_panel = QtWidgets.QWidget()
        res_lay = QtWidgets.QVBoxLayout(self.results_panel)
        res_lay.setContentsMargins(0, 0, 0, 0)
        res_lay.setSpacing(_s(6, scale))

        fin_hdr = QtWidgets.QLabel("\u2713 CALIBRATION COMPLETE")
        fin_hdr.setStyleSheet("color: #34D399; font-weight: 800; font-size: 15px;")
        res_lay.addWidget(fin_hdr)

        # X Axis Result Card
        self.x_res_card = QtWidgets.QFrame()
        self.x_res_card.setObjectName("XResCard")
        self.x_res_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.x_res_card.setStyleSheet(
            "QFrame#XResCard { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 80); border-left: 4px solid #00E5FF; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        x_lay = QtWidgets.QVBoxLayout(self.x_res_card)
        x_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        x_lay.setSpacing(2)

        x_hdr = QtWidgets.QLabel("X-AXIS RECOMMENDED")
        x_hdr.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 12px;")
        x_lay.addWidget(x_hdr)

        self.x_shaper_lbl = QtWidgets.QLabel("EI @ 114.8 Hz")
        self.x_shaper_lbl.setStyleSheet("color: #FFFFFF; font-weight: 800; font-size: 20px; font-family: 'Consolas', monospace;")
        x_lay.addWidget(self.x_shaper_lbl)

        self.x_accel_lbl = QtWidgets.QLabel("Max Accel: \u2264 24,000 mm/s\u00B2")
        self.x_accel_lbl.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: 700;")
        x_lay.addWidget(self.x_accel_lbl)
        res_lay.addWidget(self.x_res_card)

        # Y Axis Result Card
        self.y_res_card = QtWidgets.QFrame()
        self.y_res_card.setObjectName("YResCard")
        self.y_res_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.y_res_card.setStyleSheet(
            "QFrame#YResCard { background: rgba(16, 185, 129, 14); border: 1px solid rgba(16, 185, 129, 80); border-left: 4px solid #10B981; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        y_lay = QtWidgets.QVBoxLayout(self.y_res_card)
        y_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        y_lay.setSpacing(2)

        y_hdr = QtWidgets.QLabel("Y-AXIS RECOMMENDED")
        y_hdr.setStyleSheet("color: #34D399; font-weight: 800; font-size: 12px;")
        y_lay.addWidget(y_hdr)

        self.y_shaper_lbl = QtWidgets.QLabel("3HUMP_EI @ 91.4 Hz")
        self.y_shaper_lbl.setStyleSheet("color: #FFFFFF; font-weight: 800; font-size: 20px; font-family: 'Consolas', monospace;")
        y_lay.addWidget(self.y_shaper_lbl)

        self.y_accel_lbl = QtWidgets.QLabel("Max Accel: \u2264 5,500 mm/s\u00B2")
        self.y_accel_lbl.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: 700;")
        y_lay.addWidget(self.y_accel_lbl)
        res_lay.addWidget(self.y_res_card)

        # Save notice label
        save_notice = QtWidgets.QLabel("Click Save below to write parameters to printer.cfg and restart Klipper.")
        save_notice.setWordWrap(True)
        save_notice.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500;")
        res_lay.addWidget(save_notice)
        res_lay.addStretch(1)

        self.right_stack.addWidget(self.results_panel)

        # Right Stack - Page 3: Probe Calibrate Active Manual Probe Jogging
        self.probe_jog_page = QtWidgets.QWidget()
        pj_lay = QtWidgets.QVBoxLayout(self.probe_jog_page)
        pj_lay.setContentsMargins(0, 0, 0, 0)
        pj_lay.setSpacing(_s(6, scale))

        self.probe_title_lbl = QtWidgets.QLabel("MANUAL PROBE: Z-OFFSET TUNING")
        self.probe_title_lbl.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 15px;")
        pj_lay.addWidget(self.probe_title_lbl)

        # Big Z Readout Box
        z_box = QtWidgets.QFrame()
        z_box.setObjectName("DialogInfoBox")
        z_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        z_box.setStyleSheet(
            "QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        z_lay = QtWidgets.QVBoxLayout(z_box)
        z_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        z_lay.setSpacing(1)

        z_hdr = QtWidgets.QLabel("NOZZLE Z POSITION")
        z_hdr.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 800;")
        z_lay.addWidget(z_hdr)

        self.probe_z_lbl = QtWidgets.QLabel("+0.000 mm")
        self.probe_z_lbl.setStyleSheet("color: #FFFFFF; font-size: 36px; font-weight: 900; font-family: 'Consolas', monospace;")
        z_lay.addWidget(self.probe_z_lbl)
        pj_lay.addWidget(z_box)

        # Jog Step Buttons Box
        jog_box = QtWidgets.QFrame()
        jog_box.setObjectName("DialogStepsBox")
        jog_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        jog_box.setStyleSheet("QFrame#DialogStepsBox { background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 18); border-radius: 8px; }")
        jog_lay = QtWidgets.QVBoxLayout(jog_box)
        jog_lay.setContentsMargins(_s(8, scale), _s(6, scale), _s(8, scale), _s(6, scale))
        jog_lay.setSpacing(_s(4, scale))

        jog_hdr = QtWidgets.QLabel("TESTZ JOG DISTANCE")
        jog_hdr.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700;")
        jog_lay.addWidget(jog_hdr)

        # Negative buttons row (Lower nozzle closer to bed/paper)
        neg_row = QtWidgets.QHBoxLayout()
        neg_row.setSpacing(_s(4, scale))
        for step_val in (-1.0, -0.1, -0.05, -0.02):
            btn = QtWidgets.QPushButton(f"{step_val:+.2f}")
            btn.setStyleSheet("""
                QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 6px; color: #FCA5A5; font-size: 13px; font-weight: 800; min-height: 32px; }
                QPushButton:hover { background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }
                QPushButton:pressed { background: #DC2626; color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=step_val: self._on_jog_testz(s))
            neg_row.addWidget(btn)
        jog_lay.addLayout(neg_row)

        # Positive buttons row (Raise nozzle away from bed/paper)
        pos_row = QtWidgets.QHBoxLayout()
        pos_row.setSpacing(_s(4, scale))
        for step_val in (+0.02, +0.05, +0.1, +1.0):
            btn = QtWidgets.QPushButton(f"{step_val:+.2f}")
            btn.setStyleSheet("""
                QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.6); border-radius: 6px; color: #7DD3FC; font-size: 13px; font-weight: 800; min-height: 32px; }
                QPushButton:hover { background: rgba(56, 189, 248, 0.3); border-color: #38BDF8; color: #FFFFFF; }
                QPushButton:pressed { background: #0284C7; color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=step_val: self._on_jog_testz(s))
            pos_row.addWidget(btn)
        jog_lay.addLayout(pos_row)

        pj_lay.addWidget(jog_box)

        # Status text
        self.probe_status_lbl = QtWidgets.QLabel("Slide paper under nozzle. Jog Z down until slight friction drag is felt.")
        self.probe_status_lbl.setWordWrap(True)
        self.probe_status_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500; padding: 2px;")
        pj_lay.addWidget(self.probe_status_lbl)
        pj_lay.addStretch(1)

        # Accept / Abort button row
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(_s(8, scale))

        self.probe_abort_btn = QtWidgets.QPushButton("\u2715  Abort (ABORT)")
        self.probe_abort_btn.setStyleSheet("""
            QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 8px; color: #FCA5A5; font-size: 13px; font-weight: 800; min-height: 36px; padding: 0 12px; }
            QPushButton:hover { background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }
        """)
        self.probe_abort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.probe_abort_btn.clicked.connect(self._on_probe_abort)
        action_row.addWidget(self.probe_abort_btn)

        self.probe_accept_btn = QtWidgets.QPushButton("\u2713  Accept (ACCEPT)")
        self.probe_accept_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669); border: 1px solid #34D399; border-radius: 8px; color: #FFFFFF; font-size: 13px; font-weight: 800; min-height: 36px; padding: 0 14px; }
            QPushButton:hover { background: #10B981; }
        """)
        self.probe_accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.probe_accept_btn.clicked.connect(self._on_probe_accept)
        action_row.addWidget(self.probe_accept_btn, 1)

        pj_lay.addLayout(action_row)

        self.right_stack.addWidget(self.probe_jog_page)

        # Right Stack - Page 4: Probe Calibrate Results & Save Prompt
        self.probe_results_panel = QtWidgets.QWidget()
        pres_lay = QtWidgets.QVBoxLayout(self.probe_results_panel)
        pres_lay.setContentsMargins(0, 0, 0, 0)
        pres_lay.setSpacing(_s(8, scale))

        pfin_hdr = QtWidgets.QLabel("\u2713 PROBE CALIBRATION COMPLETE")
        pfin_hdr.setStyleSheet("color: #34D399; font-weight: 800; font-size: 15px;")
        pres_lay.addWidget(pfin_hdr)

        p_res_card = QtWidgets.QFrame()
        p_res_card.setObjectName("XResCard")
        p_res_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        p_res_card.setStyleSheet(
            "QFrame#XResCard { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 80); border-left: 4px solid #00E5FF; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        prc_lay = QtWidgets.QVBoxLayout(p_res_card)
        prc_lay.setContentsMargins(_s(12, scale), _s(10, scale), _s(12, scale), _s(10, scale))
        prc_lay.setSpacing(4)

        prc_hdr = QtWidgets.QLabel("NEW PROBE Z-OFFSET")
        prc_hdr.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 12px;")
        prc_lay.addWidget(prc_hdr)

        self.probe_offset_lbl = QtWidgets.QLabel("Z-Offset: 1.250 mm")
        self.probe_offset_lbl.setStyleSheet("color: #FFFFFF; font-weight: 800; font-size: 20px; font-family: 'Consolas', monospace;")
        prc_lay.addWidget(self.probe_offset_lbl)

        prc_sub = QtWidgets.QLabel("Calculated paper trigger threshold for first layer adhesion.")
        prc_sub.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: 600;")
        prc_sub.setWordWrap(True)
        prc_lay.addWidget(prc_sub)
        pres_lay.addWidget(p_res_card)

        psave_notice = QtWidgets.QLabel("Click Save below to write parameters to printer.cfg and restart Klipper.")
        psave_notice.setWordWrap(True)
        psave_notice.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500;")
        pres_lay.addWidget(psave_notice)
        pres_lay.addStretch(1)

        self.right_stack.addWidget(self.probe_results_panel)

        # Right Stack - Page 5: Load Cell Calibrate Scale & Force Tuning
        self.load_cell_panel = QtWidgets.QWidget()
        lc_lay = QtWidgets.QVBoxLayout(self.load_cell_panel)
        lc_lay.setContentsMargins(0, 0, 0, 0)
        lc_lay.setSpacing(_s(4, scale))

        # Top Navigation / Tab Selector Row
        tab_row = QtWidgets.QHBoxLayout()
        tab_row.setSpacing(_s(4, scale))

        self.tab_scale_btn = QtWidgets.QPushButton("⚖  Calibrate Scale (Weight)")
        self.tab_scale_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_scale_btn.setStyleSheet("QPushButton { background: #0284C7; border: 1px solid #38BDF8; border-radius: 6px; color: #FFFFFF; font-size: 12px; font-weight: 800; min-height: 26px; }")
        self.tab_scale_btn.clicked.connect(lambda: self._switch_lc_tab("scale"))
        tab_row.addWidget(self.tab_scale_btn, 1)

        self.tab_force_btn = QtWidgets.QPushButton("⚙  Trigger Force (60g)")
        self.tab_force_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_force_btn.setStyleSheet("QPushButton { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 20); border-radius: 6px; color: #94A3B8; font-size: 12px; font-weight: 700; min-height: 26px; } QPushButton:hover { color: #FFFFFF; }")
        self.tab_force_btn.clicked.connect(lambda: self._switch_lc_tab("force"))
        tab_row.addWidget(self.tab_force_btn, 1)

        lc_lay.addLayout(tab_row)

        # Container Stack for the two tabs
        self.lc_sub_stack = QtWidgets.QStackedWidget()
        lc_lay.addWidget(self.lc_sub_stack, 1)

        # ==============================================================
        # --- TAB 1: SCALE WEIGHT CALIBRATION WIZARD (LOAD_CELL_CALIBRATE) ---
        # ==============================================================
        self.scale_wizard_widget = QtWidgets.QWidget()
        sw_lay = QtWidgets.QVBoxLayout(self.scale_wizard_widget)
        sw_lay.setContentsMargins(0, 0, 0, 0)
        sw_lay.setSpacing(_s(4, scale))

        # Step indicator pills
        step_hdr = QtWidgets.QHBoxLayout()
        step_hdr.setSpacing(_s(4, scale))
        self.pill_step1 = QtWidgets.QLabel("1. Empty Tare")
        self.pill_step2 = QtWidgets.QLabel("2. Hang Weight")
        self.pill_step3 = QtWidgets.QLabel("3. Accept Multiplier")
        for pill in (self.pill_step1, self.pill_step2, self.pill_step3):
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setFixedHeight(_s(20, scale))
            pill.setStyleSheet("background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 20); border-radius: 4px; color: #64748B; font-size: 10px; font-weight: 700;")
            step_hdr.addWidget(pill, 1)
        self.pill_step1.setStyleSheet("background: #0284C7; border: 1px solid #38BDF8; border-radius: 4px; color: #FFFFFF; font-size: 10px; font-weight: 800;")
        sw_lay.addLayout(step_hdr)

        # Wizard Content Stack
        self.scale_step_stack = QtWidgets.QStackedWidget()
        sw_lay.addWidget(self.scale_step_stack, 1)

        # --- STEP 1: Empty Sensor Tare ---
        self.step1_view = QtWidgets.QWidget()
        s1_lay = QtWidgets.QVBoxLayout(self.step1_view)
        s1_lay.setContentsMargins(0, 0, 0, 0)
        s1_lay.setSpacing(_s(4, scale))

        s1_card = QtWidgets.QFrame()
        s1_card.setObjectName("DialogInfoBox")
        s1_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        s1_card.setStyleSheet("QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; } QLabel { border: none; background: transparent; }")
        s1c_lay = QtWidgets.QVBoxLayout(s1_card)
        s1c_lay.setContentsMargins(_s(10, scale), _s(8, scale), _s(10, scale), _s(8, scale))
        s1c_lay.setSpacing(4)

        s1_title = QtWidgets.QLabel("STEP 1: SENSOR EMPTY TARE")
        s1_title.setStyleSheet("color: #34D399; font-size: 13px; font-weight: 800;")
        s1c_lay.addWidget(s1_title)

        s1_desc = QtWidgets.QLabel("Ensure cold nozzle is clean with NO weight or bag attached. Then send ACCEPT to tare zero.")
        s1_desc.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.3;")
        s1_desc.setWordWrap(True)
        s1c_lay.addWidget(s1_desc)

        self.s1_terminal_lbl = QtWidgets.QLabel("Klipper: Prompted to ensure sensor is empty.")
        self.s1_terminal_lbl.setStyleSheet("color: #38BDF8; font-size: 11px; font-family: 'Consolas', monospace;")
        self.s1_terminal_lbl.setWordWrap(True)
        s1c_lay.addWidget(self.s1_terminal_lbl)

        s1_lay.addWidget(s1_card)

        self.step1_btn = QtWidgets.QPushButton("\u2713  Sensor Empty \u2014 Send ACCEPT")
        self.step1_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669); border: 1px solid #34D399; border-radius: 8px; color: #FFFFFF; font-size: 13px; font-weight: 800; min-height: 34px; }
            QPushButton:hover { background: #10B981; }
        """)
        self.step1_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.step1_btn.clicked.connect(self._on_scale_step1_accept)
        s1_lay.addWidget(self.step1_btn)
        s1_lay.addStretch(1)
        self.scale_step_stack.addWidget(self.step1_view)

        # --- STEP 2: Hang Known Weight & Set Grams ---
        self.step2_view = QtWidgets.QWidget()
        s2_lay = QtWidgets.QVBoxLayout(self.step2_view)
        s2_lay.setContentsMargins(0, 0, 0, 0)
        s2_lay.setSpacing(_s(3, scale))

        s2_card = QtWidgets.QFrame()
        s2_card.setObjectName("DialogInfoBox")
        s2_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        s2_card.setStyleSheet("QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; } QLabel { border: none; background: transparent; }")
        s2c_lay = QtWidgets.QVBoxLayout(s2_card)
        s2c_lay.setContentsMargins(_s(8, scale), _s(5, scale), _s(8, scale), _s(5, scale))
        s2c_lay.setSpacing(2)

        s2_title = QtWidgets.QLabel("STEP 2: APPLY WEIGHT / POSITION ONTO SCALE")
        s2_title.setStyleSheet("color: #00E5FF; font-size: 12px; font-weight: 800;")
        s2c_lay.addWidget(s2_title)

        s2_desc = QtWidgets.QLabel("Hang a known weight OR place scale on bed under nozzle and jog Z down to touch scale. Report the scale reading:")
        s2_desc.setStyleSheet("color: #CBD5E1; font-size: 11px; line-height: 1.2;")
        s2_desc.setWordWrap(True)
        s2c_lay.addWidget(s2_desc)

        # Z Jogging Controls Row
        jog_lbl = QtWidgets.QLabel("JOG NOZZLE Z (POSITION ONTO SCALE):")
        jog_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800;")
        s2c_lay.addWidget(jog_lbl)

        jog_btn_row = QtWidgets.QHBoxLayout()
        jog_btn_row.setSpacing(_s(3, scale))

        # Down buttons (Lower nozzle onto scale)
        for jz in (-1.0, -0.1, -0.05):
            btn = QtWidgets.QPushButton(f"{jz:+.2f}")
            btn.setStyleSheet("""
                QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 4px; color: #FCA5A5; font-size: 11px; font-weight: 800; min-height: 24px; }
                QPushButton:hover { background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }
                QPushButton:pressed { background: #DC2626; color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=jz: self._on_jog_nozzle_z(s))
            jog_btn_row.addWidget(btn)

        # Up buttons (Raise nozzle off scale)
        for jz in (+0.05, +0.1, +1.0):
            btn = QtWidgets.QPushButton(f"{jz:+.2f}")
            btn.setStyleSheet("""
                QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.6); border-radius: 4px; color: #7DD3FC; font-size: 11px; font-weight: 800; min-height: 24px; }
                QPushButton:hover { background: rgba(56, 189, 248, 0.3); border-color: #38BDF8; color: #FFFFFF; }
                QPushButton:pressed { background: #0284C7; color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=jz: self._on_jog_nozzle_z(s))
            jog_btn_row.addWidget(btn)

        s2c_lay.addLayout(jog_btn_row)

        self.lc_jog_status_lbl = QtWidgets.QLabel("Z Offset: +0.00 mm \u2022 Jog down to touch bed scale")
        self.lc_jog_status_lbl.setStyleSheet("color: #38BDF8; font-size: 10px; font-family: 'Consolas', monospace;")
        s2c_lay.addWidget(self.lc_jog_status_lbl)

        # Scale Reading / Weight Input
        rep_lbl = QtWidgets.QLabel("REPORT SCALE READING / WEIGHT APPLIED:")
        rep_lbl.setStyleSheet("color: #94A3B8; font-size: 10px; font-weight: 800;")
        s2c_lay.addWidget(rep_lbl)

        # Quick preset buttons: 50g, 100g, 200g, 500g
        preset_row = QtWidgets.QHBoxLayout()
        preset_row.setSpacing(_s(4, scale))
        for pw in (50, 100, 200, 500):
            p_btn = QtWidgets.QPushButton(f"{pw}g")
            p_btn.setStyleSheet("""
                QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.5); border-radius: 4px; color: #7DD3FC; font-size: 11px; font-weight: 800; min-height: 22px; }
                QPushButton:hover { background: rgba(56, 189, 248, 0.3); border-color: #38BDF8; color: #FFFFFF; }
            """)
            p_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            p_btn.clicked.connect(lambda _, w=pw: self._set_known_grams(w))
            preset_row.addWidget(p_btn)
        s2c_lay.addLayout(preset_row)

        # Big number readout & step adjustments
        adj_row = QtWidgets.QHBoxLayout()
        adj_row.setSpacing(_s(4, scale))

        for dw in (-10, -1):
            btn = QtWidgets.QPushButton(f"{dw}g")
            btn.setStyleSheet("""
                QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.5); border-radius: 4px; color: #FCA5A5; font-size: 11px; font-weight: 800; min-height: 24px; }
                QPushButton:hover { background: rgba(239, 68, 68, 0.3); color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, d=dw: self._adjust_known_grams(d))
            adj_row.addWidget(btn)

        self.known_grams_lbl = QtWidgets.QLabel("100 g")
        self.known_grams_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.known_grams_lbl.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 900; font-family: 'Consolas', monospace;")
        adj_row.addWidget(self.known_grams_lbl, 1)

        for dw in (+1, +10):
            btn = QtWidgets.QPushButton(f"+{dw}g")
            btn.setStyleSheet("""
                QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.5); border-radius: 4px; color: #7DD3FC; font-size: 11px; font-weight: 800; min-height: 24px; }
                QPushButton:hover { background: rgba(56, 189, 248, 0.3); color: #FFFFFF; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, d=dw: self._adjust_known_grams(d))
            adj_row.addWidget(btn)

        s2c_lay.addLayout(adj_row)
        s2_lay.addWidget(s2_card)

        self.step2_btn = QtWidgets.QPushButton("\u25B6  Send Scale Reading (CALIBRATE GRAMS=100)")
        self.step2_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284C7, stop:1 #0369A1); border: 1px solid #38BDF8; border-radius: 8px; color: #FFFFFF; font-size: 13px; font-weight: 800; min-height: 32px; }
            QPushButton:hover { background: #0284C7; }
        """)
        self.step2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.step2_btn.clicked.connect(self._on_scale_step2_send_grams)
        s2_lay.addWidget(self.step2_btn)
        s2_lay.addStretch(1)
        self.scale_step_stack.addWidget(self.step2_view)

        # --- STEP 3: Accept Multiplier ---
        self.step3_view = QtWidgets.QWidget()
        s3_lay = QtWidgets.QVBoxLayout(self.step3_view)
        s3_lay.setContentsMargins(0, 0, 0, 0)
        s3_lay.setSpacing(_s(4, scale))

        s3_card = QtWidgets.QFrame()
        s3_card.setObjectName("DialogInfoBox")
        s3_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        s3_card.setStyleSheet("QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; } QLabel { border: none; background: transparent; }")
        s3c_lay = QtWidgets.QVBoxLayout(s3_card)
        s3c_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        s3c_lay.setSpacing(2)

        s3_title = QtWidgets.QLabel("STEP 3: VERIFY & ACCEPT MULTIPLIER")
        s3_title.setStyleSheet("color: #34D399; font-size: 13px; font-weight: 800;")
        s3c_lay.addWidget(s3_title)

        self.s3_cpg_lbl = QtWidgets.QLabel("Counts / Gram: 572.31 counts/g")
        self.s3_cpg_lbl.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: 900; font-family: 'Consolas', monospace;")
        s3c_lay.addWidget(self.s3_cpg_lbl)

        self.s3_tare_lbl = QtWidgets.QLabel("Reference Tare: 205,315 counts")
        self.s3_tare_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; font-family: 'Consolas', monospace;")
        s3c_lay.addWidget(self.s3_tare_lbl)

        s3_notice = QtWidgets.QLabel("Klipper has calculated conversion scale factor. Send ACCEPT to accept.")
        s3_notice.setStyleSheet("color: #94A3B8; font-size: 11px;")
        s3_notice.setWordWrap(True)
        s3c_lay.addWidget(s3_notice)

        s3_lay.addWidget(s3_card)

        s3_btn_row = QtWidgets.QHBoxLayout()
        s3_btn_row.setSpacing(_s(6, scale))

        self.s3_abort_btn = QtWidgets.QPushButton("\u2715  Abort")
        self.s3_abort_btn.setStyleSheet("""
            QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 8px; color: #FCA5A5; font-size: 12px; font-weight: 800; min-height: 34px; padding: 0 12px; }
            QPushButton:hover { background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }
        """)
        self.s3_abort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.s3_abort_btn.clicked.connect(self._on_scale_abort)
        s3_btn_row.addWidget(self.s3_abort_btn)

        self.s3_accept_btn = QtWidgets.QPushButton("\u2713  Accept Multiplier (ACCEPT)")
        self.s3_accept_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669); border: 1px solid #34D399; border-radius: 8px; color: #FFFFFF; font-size: 13px; font-weight: 800; min-height: 34px; padding: 0 14px; }
            QPushButton:hover { background: #10B981; }
        """)
        self.s3_accept_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.s3_accept_btn.clicked.connect(self._on_scale_step3_accept)
        s3_btn_row.addWidget(self.s3_accept_btn, 1)

        s3_lay.addLayout(s3_btn_row)
        s3_lay.addStretch(1)
        self.scale_step_stack.addWidget(self.step3_view)

        self.lc_sub_stack.addWidget(self.scale_wizard_widget)

        # ==============================================================
        # --- TAB 2: TRIGGER FORCE TUNING & TELEMETRY ---
        # ==============================================================
        self.force_tuning_widget = QtWidgets.QWidget()
        ft_lay = QtWidgets.QVBoxLayout(self.force_tuning_widget)
        ft_lay.setContentsMargins(0, 0, 0, 0)
        ft_lay.setSpacing(_s(4, scale))

        # Config Trigger Force Tuning Card
        lc_tune_card = QtWidgets.QFrame()
        lc_tune_card.setObjectName("DialogInfoBox")
        lc_tune_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lc_tune_card.setStyleSheet(
            "QFrame#DialogInfoBox { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 60); border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        tc_lay = QtWidgets.QVBoxLayout(lc_tune_card)
        tc_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        tc_lay.setSpacing(2)

        self.lc_stored_lbl = QtWidgets.QLabel("CONFIG STORED FORCE: 60 g")
        self.lc_stored_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 800;")
        tc_lay.addWidget(self.lc_stored_lbl)

        val_row = QtWidgets.QHBoxLayout()
        val_row.setSpacing(8)
        self.lc_force_lbl = QtWidgets.QLabel("60 g")
        self.lc_force_lbl.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: 900; font-family: 'Consolas', monospace;")
        val_row.addWidget(self.lc_force_lbl)

        self.lc_delta_lbl = QtWidgets.QLabel("Stored in printer.cfg")
        self.lc_delta_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        val_row.addWidget(self.lc_delta_lbl)
        val_row.addStretch(1)
        tc_lay.addLayout(val_row)

        inc_row = QtWidgets.QHBoxLayout()
        inc_row.setSpacing(_s(4, scale))
        for delta_val in (-10, -5, +5, +10):
            sign = "+" if delta_val > 0 else ""
            btn = QtWidgets.QPushButton(f"{sign}{delta_val}g")
            if delta_val < 0:
                btn.setStyleSheet("""
                    QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.6); border-radius: 6px; color: #FCA5A5; font-size: 12px; font-weight: 800; min-height: 26px; }
                    QPushButton:hover { background: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }
                    QPushButton:pressed { background: #DC2626; color: #FFFFFF; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.6); border-radius: 6px; color: #7DD3FC; font-size: 12px; font-weight: 800; min-height: 26px; }
                    QPushButton:hover { background: rgba(56, 189, 248, 0.3); border-color: #38BDF8; color: #FFFFFF; }
                    QPushButton:pressed { background: #0284C7; color: #FFFFFF; }
                """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, d=delta_val: self._on_toggle_force(d))
            inc_row.addWidget(btn)
        tc_lay.addLayout(inc_row)

        self.lc_save_force_btn = QtWidgets.QPushButton("\U0001F4BE  Save Force to printer.cfg")
        self.lc_save_force_btn.setStyleSheet("""
            QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; color: #94A3B8; font-size: 12px; font-weight: 700; min-height: 26px; }
        """)
        self.lc_save_force_btn.setEnabled(False)
        self.lc_save_force_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lc_save_force_btn.clicked.connect(self._save_trigger_force_to_config)
        tc_lay.addWidget(self.lc_save_force_btn)

        ft_lay.addWidget(lc_tune_card)

        # Diagnostics Box
        lc_diag_box = QtWidgets.QFrame()
        lc_diag_box.setObjectName("DialogStepsBox")
        lc_diag_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lc_diag_box.setStyleSheet("QFrame#DialogStepsBox { background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 18); border-radius: 8px; } QLabel { border: none; background: transparent; }")
        diag_lay = QtWidgets.QVBoxLayout(lc_diag_box)
        diag_lay.setContentsMargins(_s(10, scale), _s(6, scale), _s(10, scale), _s(6, scale))
        diag_lay.setSpacing(3)

        self.lc_live_force_lbl = QtWidgets.QLabel("LIVE SENSOR FORCE: +0.0 g")
        self.lc_live_force_lbl.setStyleSheet("color: #34D399; font-size: 13px; font-weight: 800; font-family: 'Consolas', monospace;")
        diag_lay.addWidget(self.lc_live_force_lbl)

        self.lc_meta_lbl = QtWidgets.QLabel("Tare: 313,744 counts  \u2022  572.3 counts/g")
        self.lc_meta_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        diag_lay.addWidget(self.lc_meta_lbl)

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(_s(4, scale))

        self.lc_tare_btn = QtWidgets.QPushButton("\u2316  Tare Zero")
        self.lc_tare_btn.setStyleSheet("""
            QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.6); border-radius: 6px; color: #7DD3FC; font-size: 12px; font-weight: 800; min-height: 26px; }
            QPushButton:hover { background: rgba(56, 189, 248, 0.3); border-color: #38BDF8; color: #FFFFFF; }
        """)
        self.lc_tare_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lc_tare_btn.clicked.connect(self._on_lc_tare)
        action_row.addWidget(self.lc_tare_btn)

        self.lc_tap_btn = QtWidgets.QPushButton("\u26A1  Test Tap")
        self.lc_tap_btn.setStyleSheet("""
            QPushButton { background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.6); border-radius: 6px; color: #FCD34D; font-size: 12px; font-weight: 800; min-height: 26px; }
            QPushButton:hover { background: rgba(245, 158, 11, 0.3); border-color: #F59E0B; color: #FFFFFF; }
        """)
        self.lc_tap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lc_tap_btn.clicked.connect(self._on_lc_test_tap)
        action_row.addWidget(self.lc_tap_btn)

        diag_lay.addLayout(action_row)
        ft_lay.addWidget(lc_diag_box)
        ft_lay.addStretch(1)

        self.lc_sub_stack.addWidget(self.force_tuning_widget)

        self.right_stack.addWidget(self.load_cell_panel)

        # Right Stack - Page 6: Load Cell Calibrate Results & Save Prompt
        self.load_cell_results_panel = QtWidgets.QWidget()
        lc_res_lay = QtWidgets.QVBoxLayout(self.load_cell_results_panel)
        lc_res_lay.setContentsMargins(0, 0, 0, 0)
        lc_res_lay.setSpacing(_s(8, scale))

        lc_fin_hdr = QtWidgets.QLabel("\u2713 LOAD CELL CALIBRATION COMPLETE")
        lc_fin_hdr.setStyleSheet("color: #34D399; font-weight: 800; font-size: 15px;")
        lc_res_lay.addWidget(lc_fin_hdr)

        lc_res_card = QtWidgets.QFrame()
        lc_res_card.setObjectName("XResCard")
        lc_res_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lc_res_card.setStyleSheet(
            "QFrame#XResCard { background: rgba(0, 229, 255, 14); border: 1px solid rgba(0, 229, 255, 80); border-left: 4px solid #00E5FF; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        lcr_lay = QtWidgets.QVBoxLayout(lc_res_card)
        lcr_lay.setContentsMargins(_s(12, scale), _s(10, scale), _s(12, scale), _s(10, scale))
        lcr_lay.setSpacing(4)

        lcr_hdr = QtWidgets.QLabel("CALIBRATED SENSOR PARAMETERS")
        lcr_hdr.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 12px;")
        lcr_lay.addWidget(lcr_hdr)

        self.lc_counts_lbl = QtWidgets.QLabel("Counts / Gram: 572.3 counts/g")
        self.lc_counts_lbl.setStyleSheet("color: #FFFFFF; font-weight: 800; font-size: 18px; font-family: 'Consolas', monospace;")
        lcr_lay.addWidget(self.lc_counts_lbl)

        self.lc_res_tare_lbl = QtWidgets.QLabel("Tare Counts: 313,744 counts")
        self.lc_res_tare_lbl.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: 700; font-family: 'Consolas', monospace;")
        lcr_lay.addWidget(self.lc_res_tare_lbl)

        self.lc_res_force_lbl = QtWidgets.QLabel("Trigger Force: 60 g")
        self.lc_res_force_lbl.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 700;")
        lcr_lay.addWidget(self.lc_res_force_lbl)

        lcr_sub = QtWidgets.QLabel("Strain gauge zero-point reference and probe trigger threshold calibrated.")
        lcr_sub.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        lcr_sub.setWordWrap(True)
        lcr_lay.addWidget(lcr_sub)
        lc_res_lay.addWidget(lc_res_card)

        lcsave_notice = QtWidgets.QLabel("Click Save below to write parameters to printer.cfg and restart Klipper.")
        lcsave_notice.setWordWrap(True)
        lcsave_notice.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500;")
        lc_res_lay.addWidget(lcsave_notice)
        lc_res_lay.addStretch(1)

        self.right_stack.addWidget(self.load_cell_results_panel)

        self.stack.addWidget(self.cal_page)

        if item.get("id") in ("input_shaper", "probe_cal", "load_cell_cal"):
            self.stack.setCurrentWidget(self.cal_page)
            self.right_stack.setCurrentWidget(self.procedure_panel)
            if item.get("id") == "load_cell_cal":
                self._fetch_load_cell_config()
        else:
            self.stack.setCurrentWidget(self.info_page)

        # Bottom Button Bar
        btn_bar = QtWidgets.QHBoxLayout()
        btn_bar.setSpacing(_s(12, scale))

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setObjectName("DialogCancelBtn")
        self.cancel_btn.setStyleSheet("font-size: 13px; font-weight: 700; padding: 7px 16px;")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_close)
        btn_bar.addWidget(self.cancel_btn)

        self.start_btn = QtWidgets.QPushButton(f"Start  \u25B6  {item['cmd']}")
        self.start_btn.setObjectName("DialogStartBtn")
        self.start_btn.setStyleSheet("font-size: 13px; font-weight: 800; padding: 7px 18px;")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start)
        btn_bar.addWidget(self.start_btn, 1)

        layout.addLayout(btn_bar)

        self.apply_scale(scale)

    def _on_start(self):
        cal_id = self.item.get("id")
        main_win = self.window()
        mr = self._get_moonraker()

        homed = ""
        if mr:
            homed = str(getattr(mr, "homed_axes", "")).lower()
        if not homed and hasattr(main_win, "pages") and "home" in main_win.pages:
            homed = str(getattr(main_win.pages["home"], "_homed", "")).lower()

        # Fast query toolhead if homed string is still empty
        if not homed and mr and mr.connected:
            try:
                host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
                url = f"http://{host}/printer/objects/query?toolhead"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        th = data.get("result", {}).get("status", {}).get("toolhead", {})
                        homed = str(th.get("homed_axes", "")).lower()
                        if mr:
                            mr.homed_axes = homed
            except Exception:
                pass

        is_homed = ("x" in homed and "y" in homed and "z" in homed)
        needs_homing = cal_id in (
            "input_shaper", "probe_cal", "load_cell_cal", "z_tilt",
            "quad_gantry_level", "bed_mesh", "screws_tilt", "bed_screws",
            "probe_acc", "axis_twist", "delta_cal"
        )

        if needs_homing and not is_homed and mr and mr.connected:
            # Home only if axes are not already homed
            if cal_id in ("input_shaper", "probe_cal", "load_cell_cal"):
                self.stack.setCurrentWidget(self.cal_page)
                if cal_id == "input_shaper":
                    self.right_stack.setCurrentWidget(self.telemetry_page)
                elif cal_id == "probe_cal":
                    self.right_stack.setCurrentWidget(self.probe_jog_page)
                else:
                    self.right_stack.setCurrentWidget(self.load_cell_panel)
            self.title_lbl.setText("Homing Printer (G28)...")
            self.cmd_lbl.setText("G28  \u2022  HOMING FIRST")
            self.status_bar_lbl.setText("Axes not homed. Homing all axes (G28) first...")
            self.telemetry_terminal_lbl.setText("\u2022 Homing: Executing G28...")
            self.start_btn.setText("Homing All Axes...")
            self.start_btn.setEnabled(False)

            mr.send_gcode("G28", on_done=lambda ok: self._on_pre_calibration_homing_done(ok, cal_id), timeout=90.0)
        else:
            if cal_id == "input_shaper":
                self._start_shaper_calibration()
            elif cal_id == "probe_cal":
                self._start_probe_calibration()
            elif cal_id == "load_cell_cal":
                self._start_load_cell_view()
            else:
                self._start_generic_calibration()

    def _on_pre_calibration_homing_done(self, ok: bool, cal_id: str):
        main_win = self.window()
        mr = self._get_moonraker()
        if ok:
            if mr:
                mr.homed_axes = "xyz"
            self.status_bar_lbl.setText("Homing complete. Starting calibration...")
            self.telemetry_terminal_lbl.setText("\u2022 Homing: Complete (XYZ)")
            if cal_id == "input_shaper":
                QtCore.QTimer.singleShot(600, self._start_shaper_calibration)
            elif cal_id == "probe_cal":
                QtCore.QTimer.singleShot(600, self._start_probe_calibration)
            elif cal_id == "load_cell_cal":
                QtCore.QTimer.singleShot(600, self._start_load_cell_view)
            else:
                QtCore.QTimer.singleShot(600, self._start_generic_calibration)
        else:
            self.status_bar_lbl.setText("Homing failed or cancelled. Please check printer.")
            self.telemetry_terminal_lbl.setText("\u2022 Homing: Error or Cancelled")
            self.start_btn.setText(f"Start  \u25B6  {self.item['cmd']}")
            self.start_btn.setEnabled(True)
            self.title_lbl.setText(self.item["title"])
            self.cmd_lbl.setText(self.item["cmd"])

    def _start_generic_calibration(self):
        target_cmd = self.item.get("target_cmd", self.item["cmd"])
        self.start_btn.setText("Executing...")
        self.start_btn.setEnabled(False)
        self.status_bar_lbl.setText(f"Running {target_cmd}...")
        self.cmd_lbl.setText(f"{self.item['cmd']}  \u2022  RUNNING")
        main_win = self.window()
        mr = getattr(main_win, "moonraker", None)
        if mr and mr.connected:
            def on_done(ok):
                self.cancel_btn.setEnabled(True)
                self.cancel_btn.setText("Close")
                if ok:
                    self.status_bar_lbl.setText(f"\u2714 {self.item['title']} completed successfully.")
                    self.cmd_lbl.setText(f"{self.item['cmd']}  \u2022  COMPLETE")
                    self.start_btn.setText("\u2714 Finished")
                    self.start_btn.setEnabled(True)
                    self.start_btn.setStyleSheet(
                        "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);"
                        "border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; border-radius: 10px; padding: 6px 14px;"
                    )
                    try:
                        self.start_btn.clicked.disconnect()
                    except Exception:
                        pass
                    self.start_btn.clicked.connect(self.accept)
                else:
                    self.status_bar_lbl.setText(f"\u274C Execution failed or stopped.")
                    self.cmd_lbl.setText(f"{self.item['cmd']}  \u2022  ERROR")
                    self.start_btn.setText(f"Retry  \u25B6  {self.item['cmd']}")
                    self.start_btn.setEnabled(True)
            mr.send_gcode(target_cmd, on_done=on_done, timeout=300.0)
        else:
            QtCore.QTimer.singleShot(1200, self.accept)

    def _start_probe_calibration(self):
        self.is_calibrating = True
        self.stack.setCurrentWidget(self.cal_page)
        self.right_stack.setCurrentWidget(self.probe_jog_page)
        mr = self._get_moonraker()
        sim = not (mr and mr.connected)

        self._sim_probe_z = 2.000
        self.probe_z_lbl.setText(f"{self._sim_probe_z:+.3f} mm")
        self.gantry_anim.set_probe_z(self._sim_probe_z)
        self.gantry_anim.start(sim_mode=sim)
        self.title_lbl.setText("Probe Calibrate (Manual Paper Test)")
        self.cmd_lbl.setText("PROBE_CALIBRATE  \u2022  ACTIVE")
        self.cancel_btn.setVisible(False)
        self.start_btn.setVisible(False)

        if not sim:
            self._probe_poll_timer = QtCore.QTimer(self)
            self._probe_poll_timer.setInterval(250)
            self._probe_poll_timer.timeout.connect(self._check_probe_status)
            self._probe_poll_timer.start()

            mr.send_gcode(self.item.get("target_cmd", "PROBE_CALIBRATE"))

    def _on_jog_testz(self, step: float):
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode(f"TESTZ Z={step:+.2f}")
            QtCore.QTimer.singleShot(150, self._check_probe_status)
        else:
            self._sim_probe_z = round(self._sim_probe_z + step, 3)
            self.probe_z_lbl.setText(f"{self._sim_probe_z:+.3f} mm")
            self.gantry_anim.set_probe_z(self._sim_probe_z)
            if self._sim_probe_z <= 0.15:
                self.probe_status_lbl.setText("Nozzle near paper! Move paper to feel for slight friction drag.")
                self.probe_status_lbl.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 700; padding: 2px;")
            else:
                self.probe_status_lbl.setText("Slide paper under nozzle. Jog Z down until slight friction drag is felt.")
                self.probe_status_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500; padding: 2px;")

    def _on_probe_accept(self):
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("ACCEPT", on_done=lambda ok: self._on_probe_calibration_finished(True))
        else:
            self._on_probe_calibration_finished(True)

    def _on_probe_abort(self):
        if hasattr(self, "_probe_poll_timer") and self._probe_poll_timer.isActive():
            self._probe_poll_timer.stop()
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("ABORT")
        self._on_close()

    def _on_probe_calibration_finished(self, ok: bool = True):
        self.is_calibrating = False
        if hasattr(self, "_probe_poll_timer") and self._probe_poll_timer.isActive():
            self._probe_poll_timer.stop()

        self.gantry_anim.stop(completed=True)
        self.right_stack.setCurrentWidget(self.probe_results_panel)
        self.title_lbl.setText("Probe Calibration Results")
        self.cmd_lbl.setText("PROBE_CALIBRATE  \u2022  COMPLETE")

        self._fetch_probe_results()

        self.cancel_btn.setVisible(True)
        self.start_btn.setVisible(True)
        self.cancel_btn.setText("Close")
        self.cancel_btn.setEnabled(True)
        try:
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.accept)

        self.start_btn.setText("\U0001F4BE  Save && Apply Config (SAVE_CONFIG)")
        self.start_btn.setEnabled(True)
        self.start_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);"
            "border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; border-radius: 10px; padding: 6px 14px;"
        )
        try:
            self.start_btn.clicked.disconnect()
        except Exception:
            pass
        self.start_btn.clicked.connect(self._on_save_config)

    def _check_probe_status(self):
        mr = self._get_moonraker()
        if not mr or not mr.connected:
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _bg():
            try:
                url = f"http://{host}/printer/objects/query?manual_probe"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        mp = data.get("result", {}).get("status", {}).get("manual_probe", {})
                        is_active = mp.get("is_active", False)
                        z_pos = mp.get("z_position")
                        mr._dispatch_signal.emit(lambda: self._handle_manual_probe_update(is_active, z_pos))
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _handle_manual_probe_update(self, is_active: bool, z_pos):
        if not self.is_calibrating:
            return
        if z_pos is not None:
            self._sim_probe_z = float(z_pos)
            self.probe_z_lbl.setText(f"{float(z_pos):+.3f} mm")
            self.gantry_anim.set_probe_z(float(z_pos))
            if float(z_pos) <= 0.15:
                self.probe_status_lbl.setText("Nozzle near paper! Move paper to feel for slight friction drag.")
                self.probe_status_lbl.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 700; padding: 2px;")
            else:
                self.probe_status_lbl.setText("Slide paper under nozzle. Jog Z down until slight friction drag is felt.")
                self.probe_status_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 500; padding: 2px;")

    def _fetch_probe_results(self):
        mr = self._get_moonraker()
        host = (mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")) if mr else "127.0.0.1:7125"

        try:
            url = f"http://{host}/server/gcode_store?count=40"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    store = data.get("result", {}).get("gcode_store", [])
                    for item in reversed(store):
                        msg = item.get("message", "")
                        m = re.search(r"z_offset:\s*([\d\.-]+)", msg, re.IGNORECASE)
                        if m:
                            val = float(m.group(1))
                            self.probe_offset_lbl.setText(f"Z-Offset: {val:.3f} mm")
                            return
        except Exception:
            pass

        self.probe_offset_lbl.setText(f"Z-Offset: {abs(self._sim_probe_z):.3f} mm")

    def _start_shaper_calibration(self):
        self.is_calibrating = True
        self.stack.setCurrentWidget(self.cal_page)
        self.right_stack.setCurrentWidget(self.telemetry_page)
        mr = self._get_moonraker()
        sim = not (mr and mr.connected)

        self._shaper_start_time = time.time()
        self._last_shaper_time = self._shaper_start_time - 2.0
        self._current_freq = 0.0
        self._current_axis = "X"
        self._store_busy = False
        self._sim_pause_ticks = 0

        # Only run animation while calibrating
        self.gantry_anim.start(sim_mode=sim)
        self.title_lbl.setText("Calibrating Input Shaper...")
        self.cmd_lbl.setText("SHAPER_CALIBRATE  \u2022  RUNNING")
        self.cancel_btn.setText("Cancel")
        self.start_btn.setText("Calibrating...")
        self.start_btn.setEnabled(False)

        if sim:
            # In offline simulation mode, smoothly step Hz synchronously without network jitter
            self._sim_timer = QtCore.QTimer(self)
            self._sim_timer.setInterval(40)
            self._sim_timer.timeout.connect(self._sim_tick)
            self._sim_timer.start()
        else:
            # Polling timer at 250ms to query recent live Hz from Moonraker
            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(250)
            self._poll_timer.timeout.connect(self._check_shaper_status)
            self._poll_timer.start()

            mr.send_gcode(self.item.get("target_cmd", "SHAPER_CALIBRATE"),
                          on_done=self._on_calibration_finished, timeout=300.0)

    def _sim_tick(self):
        if not self.is_calibrating:
            return

        if self.gantry_anim._is_paused:
            self._sim_pause_ticks = getattr(self, "_sim_pause_ticks", 0) - 1
            if self._sim_pause_ticks <= 0:
                # Switch and resume for Y axis!
                self._current_axis = "Y"
                self._current_freq = 5.0
                self.gantry_anim._freq = 5.0
                self.gantry_anim.resume_for_axis("Y")
                self.axis_lbl.setText("CURRENT AXIS: Y-AXIS RESONANCE")
                self.axis_lbl.setStyleSheet("color: #10B981; font-weight: 800; font-size: 14px;")
                self.status_bar_lbl.setText("Sweeping Y-Axis resonance frequencies: 5 Hz...")
                self.status_bar_lbl.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 700; padding: 2px;")
                self.big_hz_lbl.setText("5 Hz")
                self.freq_pbar.setValue(5)
            return

        freq = self.gantry_anim._freq
        ax = self.gantry_anim._axis

        if self._current_axis != ax:
            self._current_axis = ax
            self.axis_lbl.setText(f"CURRENT AXIS: {ax}-AXIS RESONANCE")
            self.axis_lbl.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 14px;" if ax == "X" else "color: #10B981; font-weight: 800; font-size: 14px;")
            self.status_bar_lbl.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 700; padding: 2px;" if ax == "X" else "color: #10B981; font-size: 13px; font-weight: 700; padding: 2px;")

        self.big_hz_lbl.setText(f"{int(freq)} Hz")
        self.freq_pbar.setValue(min(135, max(5, int(freq))))
        self.telemetry_terminal_lbl.setText(f"\u2022 Terminal: Testing frequency {int(freq)} Hz")
        self.status_bar_lbl.setText(f"Sweeping {ax}-Axis resonance frequencies: {int(freq)} Hz...")

        if ax == "X" and freq >= 134.0:
            # X sweep complete! Pause animation and wait ~1.8 seconds (45 ticks @ 40ms)
            self.gantry_anim.pause_between_axes("X")
            self._sim_pause_ticks = 45
            self.status_bar_lbl.setText("X-Axis complete. Preparing Y-Axis resonance test...")
            self.status_bar_lbl.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 700; padding: 2px;")
            self.telemetry_terminal_lbl.setText("\u2022 Terminal: X-Axis finished \u2022 Readying Y-Axis...")
        elif ax == "Y" and freq >= 134.0:
            if hasattr(self, "_sim_timer") and self._sim_timer.isActive():
                self._sim_timer.stop()
            self.x_shaper_lbl.setText("EI @ 114.8 Hz")
            self.x_accel_lbl.setText("Max Accel: \u2264 24,000 mm/s\u00B2")
            self.y_shaper_lbl.setText("3HUMP_EI @ 91.4 Hz")
            self.y_accel_lbl.setText("Max Accel: \u2264 5,500 mm/s\u00B2")
            self._on_calibration_finished(True)

    def _reset_store_busy(self):
        self._store_busy = False

    def _check_shaper_status(self):
        if getattr(self, "_store_busy", False):
            return
        mr = self._get_moonraker()
        if not mr or not mr.connected:
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        self._store_busy = True

        def _bg():
            try:
                url = f"http://{host}/server/gcode_store?count=50"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.2) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        mr._dispatch_signal.emit(lambda: self._handle_store_updates(data))
            except Exception:
                pass
            finally:
                mr._dispatch_signal.emit(self._reset_store_busy)

        threading.Thread(target=_bg, daemon=True).start()

    def _handle_store_updates(self, data: dict):
        if not self.is_calibrating:
            return
        store = data.get("result", {}).get("gcode_store", [])
        if not store:
            return

        has_finished = False
        new_freq = None
        axis_changed = False

        for item in store:
            t = float(item.get("time", 0.0))
            if t < self._last_shaper_time:
                continue
            self._last_shaper_time = max(self._last_shaper_time, t)

            msg = item.get("message", "").strip()
            msg_lower = msg.lower()

            # 1. Starting X axis
            if "testing axis x" in msg_lower:
                if self._current_axis != "X" or self.gantry_anim._is_paused:
                    self._current_axis = "X"
                    self._current_freq = 0.0
                    axis_changed = True
                    self.gantry_anim.resume_for_axis("X")
                    self.axis_lbl.setText("CURRENT AXIS: X-AXIS RESONANCE")
                    self.axis_lbl.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 14px;")
                    self.status_bar_lbl.setText("Sweeping X-Axis resonance vibrations...")
                    self.status_bar_lbl.setStyleSheet("color: #00E5FF; font-size: 13px; font-weight: 700; padding: 2px;")
                    self.freq_pbar.setValue(5)

            # 2. X test completed -> Pause animation while waiting for Y
            elif "re-enabled [input_shaper]" in msg_lower and self._current_axis == "X":
                self.gantry_anim.pause_between_axes("X")
                self.status_bar_lbl.setText("X-Axis complete. Preparing Y-Axis resonance test...")
                self.status_bar_lbl.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 700; padding: 2px;")
                self.telemetry_terminal_lbl.setText("\u2022 Terminal: X-Axis finished \u2022 Readying Y-Axis...")

            # 3. Starting Y axis
            elif "testing axis y" in msg_lower:
                if self._current_axis != "Y" or self.gantry_anim._is_paused:
                    self._current_axis = "Y"
                    self._current_freq = 0.0
                    axis_changed = True
                    self.gantry_anim.resume_for_axis("Y")
                    self.axis_lbl.setText("CURRENT AXIS: Y-AXIS RESONANCE")
                    self.axis_lbl.setStyleSheet("color: #10B981; font-weight: 800; font-size: 14px;")
                    self.status_bar_lbl.setText("Sweeping Y-Axis resonance vibrations...")
                    self.status_bar_lbl.setStyleSheet("color: #10B981; font-size: 13px; font-weight: 700; padding: 2px;")
                    self.freq_pbar.setValue(5)
                    self.big_hz_lbl.setText("5 Hz")

            # 4. Y test completed -> Pause animation during calculation phase
            elif ("re-enabled [input_shaper]" in msg_lower and self._current_axis == "Y") or "calculating the best input shaper" in msg_lower:
                self.gantry_anim.pause_between_axes("Y")
                if "for x axis" in msg_lower:
                    self.status_bar_lbl.setText("Calculating best input shaper parameters for X axis...")
                    self.telemetry_terminal_lbl.setText("\u2022 Terminal: Fitting shapers for X axis...")
                elif "for y axis" in msg_lower:
                    self.status_bar_lbl.setText("Calculating best input shaper parameters for Y axis...")
                    self.telemetry_terminal_lbl.setText("\u2022 Terminal: Fitting shapers for Y axis...")
                else:
                    self.status_bar_lbl.setText("Resonance sweeps complete. Calculating optimal shapers...")
                    self.telemetry_terminal_lbl.setText("\u2022 Terminal: Fitting shaper models to resonance data...")
                self.status_bar_lbl.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: 700; padding: 2px;")

            # 5. Live frequency sweep from terminal
            m_f = re.search(r"testing frequency\s+([\d\.]+)\s*hz", msg, re.IGNORECASE)
            if m_f:
                parsed_hz = float(m_f.group(1))
                if new_freq is None or parsed_hz > new_freq:
                    new_freq = parsed_hz

            # 6. Parse recommended shaper values on the fly
            m_rec = re.search(r"Recommended shaper_type_([xy])\s*=\s*(\w+),\s*shaper_freq_([xy])\s*=\s*([\d\.]+)", msg, re.IGNORECASE)
            if m_rec:
                ax = m_rec.group(1).lower()
                stype = m_rec.group(2).upper()
                freq = float(m_rec.group(4))
                if ax == "x":
                    self.x_shaper_lbl.setText(f"{stype} @ {freq:.1f} Hz")
                elif ax == "y":
                    self.y_shaper_lbl.setText(f"{stype} @ {freq:.1f} Hz")

            m_acc = re.search(r"with \x27(\w+)\x27,\s*suggested max_accel\s*<=\s*([\d\.]+)", msg, re.IGNORECASE)
            if m_acc:
                acc = int(float(m_acc.group(2)))
                if "for x axis" in msg_lower or self._current_axis == "X":
                    self.x_accel_lbl.setText(f"Max Accel: \u2264 {acc:,} mm/s\u00B2")
                else:
                    self.y_accel_lbl.setText(f"Max Accel: \u2264 {acc:,} mm/s\u00B2")

            # 7. Check if test complete
            if "recommended shaper_type_y" in msg_lower or ("shaper calibration data written to" in msg_lower and "calibration_data_y" in msg_lower) or "the save_config command will update" in msg_lower:
                has_finished = True

        # Apply latest frequency update monotonically once per batch (no flickering!)
        if new_freq is not None and not self.gantry_anim._is_paused:
            if axis_changed or new_freq >= self._current_freq:
                self._current_freq = new_freq
                self.gantry_anim.set_frequency(new_freq)
                self.big_hz_lbl.setText(f"{int(new_freq)} Hz")
                self.freq_pbar.setValue(min(135, max(5, int(new_freq))))
                self.telemetry_terminal_lbl.setText(f"\u2022 Terminal: Testing frequency {int(new_freq)} Hz")
                cur_ax = self._current_axis
                self.status_bar_lbl.setText(f"Sweeping {cur_ax}-Axis resonance frequencies: {int(new_freq)} Hz...")

        if has_finished:
            self._on_calibration_finished(True)

    def _fetch_results_and_update_ui(self):
        mr = self._get_moonraker()
        host = (mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")) if mr else "127.0.0.1:7125"

        try:
            url = f"http://{host}/server/gcode_store?count=150"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    store = data.get("result", {}).get("gcode_store", [])
                    cur_ax = None
                    accels = {"x": {}, "y": {}}
                    recs = {}
                    for item in store:
                        msg = item.get("message", "")
                        msg_l = msg.lower()
                        if "calculating the best input shaper parameters for x axis" in msg_l:
                            cur_ax = "x"
                        elif "calculating the best input shaper parameters for y axis" in msg_l:
                            cur_ax = "y"

                        m_acc = re.search(r"with \x27(\w+)\x27,\s*suggested max_accel\s*<=\s*([\d\.]+)", msg, re.IGNORECASE)
                        if m_acc and cur_ax:
                            stype = m_acc.group(1).lower()
                            acc = int(float(m_acc.group(2)))
                            accels[cur_ax][stype] = acc

                        m_rec = re.search(r"Recommended shaper_type_([xy])\s*=\s*(\w+),\s*shaper_freq_([xy])\s*=\s*([\d\.]+)", msg, re.IGNORECASE)
                        if m_rec:
                            ax = m_rec.group(1).lower()
                            stype = m_rec.group(2).lower()
                            freq = float(m_rec.group(4))
                            recs[ax] = (stype, freq)

                    for ax in ("x", "y"):
                        if ax in recs:
                            stype, freq = recs[ax]
                            acc = accels[ax].get(stype, None)
                            lbl = self.x_shaper_lbl if ax == "x" else self.y_shaper_lbl
                            lbl.setText(f"{stype.upper()} @ {freq:.1f} Hz")
                            acc_lbl = self.x_accel_lbl if ax == "x" else self.y_accel_lbl
                            if acc:
                                acc_lbl.setText(f"Max Accel: \u2264 {acc:,} mm/s\u00B2")
        except Exception:
            pass

    def _on_calibration_finished(self, ok: bool = True):
        if not self.is_calibrating and self.right_stack.currentWidget() == self.results_panel:
            return

        self.is_calibrating = False
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        if hasattr(self, "_sim_timer") and self._sim_timer.isActive():
            self._sim_timer.stop()

        # ONLY show animation when running -> stop animation when finished
        self.gantry_anim.stop(completed=True)

        # Fetch latest parsed results from Moonraker and populate UI
        self._fetch_results_and_update_ui()

        # Switch to Results Panel on the Right Side! (3D view stays on left)
        self.right_stack.setCurrentWidget(self.results_panel)
        self.title_lbl.setText("Input Shaper Results")
        self.cmd_lbl.setText("SHAPER_CALIBRATE  \u2022  COMPLETE")

        # Update buttons: Close and Save Config
        self.cancel_btn.setText("Close")
        self.cancel_btn.setEnabled(True)
        try:
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.accept)

        self.start_btn.setText("\U0001F4BE  Save && Apply Config (SAVE_CONFIG)")
        self.start_btn.setEnabled(True)
        self.start_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);"
            "border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; border-radius: 10px; padding: 6px 14px;"
        )
        try:
            self.start_btn.clicked.disconnect()
        except Exception:
            pass
        self.start_btn.clicked.connect(self._on_save_config)

    def _on_save_config(self):
        self.start_btn.setText("Saving & Restarting Klipper...")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("SAVE_CONFIG", on_done=lambda ok: QtCore.QTimer.singleShot(1400, self.accept))
        else:
            QtCore.QTimer.singleShot(1400, self.accept)

    def _fetch_load_cell_config(self):
        mr = self._get_moonraker()
        host = (mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")) if mr else "127.0.0.1:7125"

        def _bg():
            tf_found = None
            try:
                url = f"http://{host}/server/files/config/printer.cfg"
                req = urllib.request.Request(url, headers={"Accept": "text/plain"})
                with urllib.request.urlopen(req, timeout=1.8) as resp:
                    if resp.status == 200:
                        content = resp.read().decode("utf-8")
                        m = re.search(r"\[load_cell_probe\][\s\S]*?trigger_force:\s*(\d+)", content)
                        if m:
                            tf_found = int(m.group(1))
            except Exception:
                pass

            lc_status = {}
            try:
                url_query = f"http://{host}/printer/objects/query?load_cell_probe"
                req_query = urllib.request.Request(url_query, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req_query, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        lc_status = data.get("result", {}).get("status", {}).get("load_cell_probe", {})
            except Exception:
                pass

            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(lambda: self._apply_initial_stored_force(tf_found, lc_status))
            else:
                QtCore.QTimer.singleShot(0, lambda: self._apply_initial_stored_force(tf_found, lc_status))

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_initial_stored_force(self, tf: int = None, lc_status: dict = None):
        if tf is not None:
            self._stored_trigger_force = tf
            self._target_force = tf
        if lc_status:
            if "force_g" in lc_status:
                self._live_force_g = float(lc_status["force_g"])
            if "counts_per_gram" in lc_status:
                self._counts_per_gram = float(lc_status["counts_per_gram"])
            if "tare_counts" in lc_status:
                self._tare_counts = int(lc_status["tare_counts"])

        if hasattr(self, "lc_stored_lbl"):
            self.lc_stored_lbl.setText(f"CONFIG STORED FORCE: {self._stored_trigger_force} g")
        if hasattr(self, "lc_force_lbl"):
            self.lc_force_lbl.setText(f"{self._target_force} g")
        if hasattr(self, "lc_delta_lbl"):
            self.lc_delta_lbl.setText("Stored in printer.cfg")
        if hasattr(self, "lc_live_force_lbl"):
            self.lc_live_force_lbl.setText(f"LIVE SENSOR FORCE: {self._live_force_g:+.1f} g")
        if hasattr(self, "lc_meta_lbl"):
            self.lc_meta_lbl.setText(f"Tare: {self._tare_counts:,} counts  \u2022  {self._counts_per_gram:.1f} counts/g")
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_force(self._live_force_g, self._target_force)

    def _start_load_cell_view(self):
        self.is_calibrating = True
        self.stack.setCurrentWidget(self.cal_page)
        self.right_stack.setCurrentWidget(self.load_cell_panel)
        mr = self._get_moonraker()
        sim = not (mr and mr.connected)

        self.title_lbl.setText("Load Cell Scale & Trigger Calibration")
        self.cmd_lbl.setText("LOAD_CELL_CALIBRATE  \u2022  ACTIVE")
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setText("Close")
        self.start_btn.setVisible(False)

        # Reset jog offset state
        self._jog_z_cum = 0.0
        if hasattr(self, "lc_jog_status_lbl"):
            self.lc_jog_status_lbl.setText("Z Offset: +0.00 mm \u2022 Jog down to touch bed scale")
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_jog_z(0.0)

        # Set wizard to Step 1 & switch to scale tab
        self._switch_lc_tab("scale")
        self._scale_step = 1
        self._update_scale_step_pills(1)
        self.scale_step_stack.setCurrentWidget(self.step1_view)

        # Start 3D gantry animation in weight calibration mode
        self.gantry_anim.set_weight_calibration(True, weight_hanging=False, grams=self._known_grams, counts_per_gram=self._counts_per_gram)
        self.gantry_anim.start(sim_mode=sim)

        # Start interactive LOAD_CELL_CALIBRATE in Klipper
        if mr and mr.connected:
            mr.send_gcode(self.item.get("target_cmd", "LOAD_CELL_CALIBRATE"))

        self._lc_poll_timer = QtCore.QTimer(self)
        self._lc_poll_timer.setInterval(200)
        self._lc_poll_timer.timeout.connect(self._poll_load_cell_status)
        self._lc_poll_timer.start()

    def _switch_lc_tab(self, tab: str):
        self._active_lc_tab = tab
        if tab == "scale":
            self.lc_sub_stack.setCurrentWidget(self.scale_wizard_widget)
            self.tab_scale_btn.setStyleSheet("""
                QPushButton { background: #0284C7; border: 1px solid #38BDF8; border-radius: 6px; color: #FFFFFF; font-size: 12px; font-weight: 800; min-height: 26px; }
            """)
            self.tab_force_btn.setStyleSheet("""
                QPushButton { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 20); border-radius: 6px; color: #94A3B8; font-size: 12px; font-weight: 700; min-height: 26px; }
                QPushButton:hover { color: #FFFFFF; }
            """)
            if hasattr(self, "gantry_anim"):
                self.gantry_anim.set_weight_calibration(True, weight_hanging=(self._scale_step >= 2), grams=self._known_grams, counts_per_gram=self._counts_per_gram)
        else:
            self.lc_sub_stack.setCurrentWidget(self.force_tuning_widget)
            self.tab_force_btn.setStyleSheet("""
                QPushButton { background: #0284C7; border: 1px solid #38BDF8; border-radius: 6px; color: #FFFFFF; font-size: 12px; font-weight: 800; min-height: 26px; }
            """)
            self.tab_scale_btn.setStyleSheet("""
                QPushButton { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 20); border-radius: 6px; color: #94A3B8; font-size: 12px; font-weight: 700; min-height: 26px; }
                QPushButton:hover { color: #FFFFFF; }
            """)
            if hasattr(self, "gantry_anim"):
                self.gantry_anim.set_weight_calibration(False)
                self.gantry_anim.set_force(self._live_force_g, self._target_force)

    def _update_scale_step_pills(self, step: int):
        self._scale_step = step
        for idx, (pill, text) in enumerate(((self.pill_step1, "1. Empty Tare"), (self.pill_step2, "2. Hang Weight"), (self.pill_step3, "3. Accept Multiplier")), start=1):
            if idx < step:
                pill.setText(f"\u2713 {text[3:]}")
                pill.setStyleSheet("background: rgba(16, 185, 129, 0.25); border: 1px solid #10B981; border-radius: 4px; color: #34D399; font-size: 10px; font-weight: 800;")
            elif idx == step:
                pill.setText(text)
                pill.setStyleSheet("background: #0284C7; border: 1px solid #38BDF8; border-radius: 4px; color: #FFFFFF; font-size: 10px; font-weight: 800;")
            else:
                pill.setText(text)
                pill.setStyleSheet("background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 20); border-radius: 4px; color: #64748B; font-size: 10px; font-weight: 700;")

    def _set_known_grams(self, grams: int):
        self._known_grams = max(1, min(2000, grams))
        self.known_grams_lbl.setText(f"{self._known_grams} g")
        self.step2_btn.setText(f"\u25B6  Send Scale Reading (CALIBRATE GRAMS={self._known_grams})")
        if hasattr(self, "gantry_anim") and self.gantry_anim._weight_hanging:
            self.gantry_anim.set_weight_calibration(True, weight_hanging=True, grams=self._known_grams, counts_per_gram=self._counts_per_gram)

    def _adjust_known_grams(self, delta: int):
        self._set_known_grams(self._known_grams + delta)

    def _on_jog_nozzle_z(self, step: float):
        self._jog_z_cum += step
        if hasattr(self, "lc_jog_status_lbl"):
            self.lc_jog_status_lbl.setText(f"Z Offset: {self._jog_z_cum:+.2f} mm \u2022 Touch nozzle to scale")
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_jog_z(self._jog_z_cum)
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode(f"G91\nG1 Z{step:+.2f} F300\nG90")

    def _on_scale_step1_accept(self):
        self.step1_btn.setEnabled(False)
        self.step1_btn.setText("Capturing empty zero...")
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("ACCEPT", on_done=lambda ok: self._after_step1_tare())
        else:
            QtCore.QTimer.singleShot(400, self._after_step1_tare)

    def _after_step1_tare(self):
        self.step1_btn.setEnabled(True)
        self.step1_btn.setText("\u2713  Sensor Empty \u2014 Send ACCEPT")
        self._scale_step = 2
        self._update_scale_step_pills(2)
        self.scale_step_stack.setCurrentWidget(self.step2_view)
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_weight_calibration(True, weight_hanging=True, grams=self._known_grams, counts_per_gram=self._counts_per_gram)

    def _on_scale_step2_send_grams(self):
        self.step2_btn.setEnabled(False)
        self.step2_btn.setText(f"Calibrating {self._known_grams}g...")
        mr = self._get_moonraker()
        cmd = f"CALIBRATE GRAMS={self._known_grams}"
        if mr and mr.connected:
            mr.send_gcode(cmd, on_done=lambda ok: self._after_step2_calibrate())
        else:
            QtCore.QTimer.singleShot(600, self._after_step2_calibrate)

    def _after_step2_calibrate(self):
        self.step2_btn.setEnabled(True)
        self.step2_btn.setText(f"\u25B6  Send Scale Reading (CALIBRATE GRAMS={self._known_grams})")
        self._scale_step = 3
        self._update_scale_step_pills(3)
        self.scale_step_stack.setCurrentWidget(self.step3_view)
        self._fetch_scale_calibration_multiplier()

    def _fetch_scale_calibration_multiplier(self):
        mr = self._get_moonraker()
        host = (mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")) if mr else "127.0.0.1:7125"

        def _bg():
            cpg_found = None
            tare_found = None
            try:
                url = f"http://{host}/server/gcode_store?count=40"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in reversed(data.get("result", {}).get("gcode_store", [])):
                            msg = item.get("message", "")
                            m_cpg = re.search(r"counts_per_gram\s*=\s*([\d\.]+)", msg, re.IGNORECASE)
                            if m_cpg:
                                cpg_found = float(m_cpg.group(1))
                            m_tare = re.search(r"reference_tare_counts\s*=\s*(-?\d+)", msg, re.IGNORECASE)
                            if m_tare:
                                tare_found = int(m_tare.group(1))
                            if cpg_found is not None:
                                break
            except Exception:
                pass

            try:
                url_q = f"http://{host}/printer/objects/query?load_cell_probe"
                req_q = urllib.request.Request(url_q, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req_q, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        lcp = data.get("result", {}).get("status", {}).get("load_cell_probe", {})
                        if cpg_found is None and "counts_per_gram" in lcp:
                            cpg_found = float(lcp["counts_per_gram"])
                        if tare_found is None and "reference_tare_counts" in lcp:
                            tare_found = int(lcp["reference_tare_counts"])
            except Exception:
                pass

            def _apply():
                if cpg_found:
                    self._counts_per_gram = cpg_found
                if tare_found:
                    self._tare_counts = tare_found
                self.s3_cpg_lbl.setText(f"Counts / Gram: {self._counts_per_gram:.2f} counts/g")
                self.s3_tare_lbl.setText(f"Reference Tare: {self._tare_counts:,} counts")
                if hasattr(self, "gantry_anim"):
                    self.gantry_anim.set_weight_calibration(True, weight_hanging=True, grams=self._known_grams, counts_per_gram=self._counts_per_gram)

            if mr and hasattr(mr, "_dispatch_signal"):
                mr._dispatch_signal.emit(_apply)
            else:
                QtCore.QTimer.singleShot(0, _apply)

        threading.Thread(target=_bg, daemon=True).start()

    def _on_scale_step3_accept(self):
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("ACCEPT", on_done=lambda ok: self._on_scale_calibration_finished(True))
        else:
            self._on_scale_calibration_finished(True)

    def _on_scale_abort(self):
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("ABORT")
        self._scale_step = 1
        self._jog_z_cum = 0.0
        if hasattr(self, "lc_jog_status_lbl"):
            self.lc_jog_status_lbl.setText("Z Offset: +0.00 mm \u2022 Jog down to touch bed scale")
        self._update_scale_step_pills(1)
        self.scale_step_stack.setCurrentWidget(self.step1_view)
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_weight_calibration(True, weight_hanging=False, grams=self._known_grams, counts_per_gram=self._counts_per_gram)
            self.gantry_anim.set_jog_z(0.0)

    def _on_scale_calibration_finished(self, ok: bool = True):
        self.is_calibrating = False
        if hasattr(self, "_lc_poll_timer") and self._lc_poll_timer.isActive():
            self._lc_poll_timer.stop()

        self.gantry_anim.stop(completed=True)
        self.right_stack.setCurrentWidget(self.load_cell_results_panel)
        self.title_lbl.setText("Load Cell Calibration Results")
        self.cmd_lbl.setText("LOAD_CELL_CALIBRATE  \u2022  COMPLETE")

        self.lc_counts_lbl.setText(f"Counts / Gram: {self._counts_per_gram:.2f} counts/g")
        self.lc_res_tare_lbl.setText(f"Tare Counts: {self._tare_counts:,} counts")
        self.lc_res_force_lbl.setText(f"Trigger Force: {self._target_force} g")

        self.cancel_btn.setVisible(True)
        self.start_btn.setVisible(True)
        self.cancel_btn.setText("Close")
        self.cancel_btn.setEnabled(True)
        try:
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.accept)

        self.start_btn.setText("\U0001F4BE  Save && Apply Config (SAVE_CONFIG)")
        self.start_btn.setEnabled(True)
        self.start_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);"
            "border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; border-radius: 10px; padding: 6px 14px;"
        )
        try:
            self.start_btn.clicked.disconnect()
        except Exception:
            pass
        self.start_btn.clicked.connect(self._on_save_config)

    def _poll_load_cell_status(self):
        mr = self._get_moonraker()
        if not mr or not mr.connected:
            sim_noise = round(math.sin(time.time() * 3.0) * 0.3, 1)
            self._live_force_g = sim_noise
            if hasattr(self, "lc_live_force_lbl"):
                self.lc_live_force_lbl.setText(f"LIVE SENSOR FORCE: {self._live_force_g:+.1f} g")
            if hasattr(self, "gantry_anim"):
                self.gantry_anim.set_force(self._live_force_g, self._target_force)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")

        def _bg():
            try:
                url = f"http://{host}/printer/objects/query?load_cell_probe"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        lcp = data.get("result", {}).get("status", {}).get("load_cell_probe", {})
                        fg = lcp.get("force_g", 0.0)
                        tc = lcp.get("tare_counts", self._tare_counts)
                        cpg = lcp.get("counts_per_gram", self._counts_per_gram)
                        if hasattr(mr, "_dispatch_signal"):
                            mr._dispatch_signal.emit(lambda: self._handle_lc_live_update(fg, tc, cpg))
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True).start()

    def _handle_lc_live_update(self, fg, tc, cpg):
        if not self.is_calibrating:
            return
        self._live_force_g = float(fg)
        self._tare_counts = int(tc)
        if cpg:
            self._counts_per_gram = float(cpg)

        val_str = f"{self._live_force_g:+.1f} g"
        if abs(self._live_force_g) < 5.0:
            col = "#34D399"
        elif abs(self._live_force_g) < self._target_force:
            col = "#00E5FF"
        else:
            col = "#F59E0B"

        if hasattr(self, "lc_live_force_lbl"):
            self.lc_live_force_lbl.setText(f"LIVE SENSOR FORCE: {val_str}")
            self.lc_live_force_lbl.setStyleSheet(f"color: {col}; font-size: 13px; font-weight: 800; font-family: 'Consolas', monospace;")
        if hasattr(self, "lc_meta_lbl"):
            self.lc_meta_lbl.setText(f"Tare: {self._tare_counts:,} counts  \u2022  {self._counts_per_gram:.1f} counts/g")

        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_force(self._live_force_g, self._target_force)

    def _on_toggle_force(self, delta: int):
        new_val = max(10, min(350, self._target_force + delta))
        new_val = round(new_val / 5.0) * 5
        self._target_force = int(new_val)

        if hasattr(self, "lc_force_lbl"):
            self.lc_force_lbl.setText(f"{self._target_force} g")

        diff = self._target_force - self._stored_trigger_force
        if diff == 0:
            if hasattr(self, "lc_delta_lbl"):
                self.lc_delta_lbl.setText("Stored in printer.cfg")
                self.lc_delta_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
            if hasattr(self, "lc_save_force_btn"):
                self.lc_save_force_btn.setEnabled(False)
                self.lc_save_force_btn.setText("\U0001F4BE  Save Force to printer.cfg")
                self.lc_save_force_btn.setStyleSheet("""
                    QPushButton { background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; color: #94A3B8; font-size: 12px; font-weight: 700; min-height: 28px; }
                """)
        else:
            sign = "+" if diff > 0 else ""
            if hasattr(self, "lc_delta_lbl"):
                self.lc_delta_lbl.setText(f"Modified: {sign}{diff} g (unsaved)")
                self.lc_delta_lbl.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 700;")
            if hasattr(self, "lc_save_force_btn"):
                self.lc_save_force_btn.setEnabled(True)
                self.lc_save_force_btn.setText(f"\U0001F4BE  Save {self._target_force}g to printer.cfg")
                self.lc_save_force_btn.setStyleSheet("""
                    QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0284C7, stop:1 #0369A1); border: 1px solid #38BDF8; border-radius: 6px; color: #FFFFFF; font-size: 12px; font-weight: 800; min-height: 28px; }
                    QPushButton:hover { background: #0284C7; }
                """)

        if hasattr(self, "gantry_anim"):
            self.gantry_anim.set_force(self._live_force_g, self._target_force)

    def _save_trigger_force_to_config(self):
        mr = self._get_moonraker()
        if not mr or not mr.connected:
            self._stored_trigger_force = self._target_force
            if hasattr(self, "lc_stored_lbl"):
                self.lc_stored_lbl.setText(f"CONFIG STORED FORCE: {self._stored_trigger_force} g")
            if hasattr(self, "lc_delta_lbl"):
                self.lc_delta_lbl.setText("\u2713 Saved in simulation mode")
                self.lc_delta_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 700;")
            if hasattr(self, "lc_save_force_btn"):
                self.lc_save_force_btn.setEnabled(False)
            return

        host = mr.active_host or (mr.hosts[0] if mr.hosts else "127.0.0.1:7125")
        new_force = self._target_force
        self.lc_save_force_btn.setEnabled(False)
        self.lc_save_force_btn.setText("Saving to printer.cfg...")

        def _bg():
            try:
                url_get = f"http://{host}/server/files/config/printer.cfg"
                req_get = urllib.request.Request(url_get)
                with urllib.request.urlopen(req_get, timeout=2.5) as resp:
                    cfg_text = resp.read().decode("utf-8")

                new_cfg, count = re.subn(
                    r"(trigger_force:\s*)\d+(\.\d+)?",
                    rf"\g<1>{new_force}",
                    cfg_text,
                    count=1
                )
                if count == 0:
                    new_cfg = re.sub(
                        r"(\[load_cell_probe\])",
                        rf"\1\ntrigger_force: {new_force}",
                        cfg_text,
                        count=1
                    )

                import uuid
                b = uuid.uuid4().hex
                body = (
                    f"--{b}\r\n"
                    f'Content-Disposition: form-data; name="root"\r\n\r\n'
                    f"config\r\n"
                    f"--{b}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="printer.cfg"\r\n'
                    f"Content-Type: text/plain\r\n\r\n"
                    f"{new_cfg}\r\n"
                    f"--{b}--\r\n"
                ).encode("utf-8")

                req_post = urllib.request.Request(
                    f"http://{host}/server/files/upload",
                    data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={b}"},
                    method="POST"
                )
                with urllib.request.urlopen(req_post, timeout=3.5) as resp:
                    pass

                def _on_success():
                    self._stored_trigger_force = new_force
                    if hasattr(self, "lc_stored_lbl"):
                        self.lc_stored_lbl.setText(f"CONFIG STORED FORCE: {self._stored_trigger_force} g")
                    if hasattr(self, "lc_delta_lbl"):
                        self.lc_delta_lbl.setText(f"\u2713 Saved {new_force}g & restarting Klipper...")
                        self.lc_delta_lbl.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 700;")
                    if hasattr(self, "lc_save_force_btn"):
                        self.lc_save_force_btn.setText("\u2713 Saved to printer.cfg")
                    mr.send_gcode("FIRMWARE_RESTART")
                    QtCore.QTimer.singleShot(2500, self.accept)

                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_on_success)
            except Exception as e:
                def _on_err(err_msg=str(e)):
                    if hasattr(self, "lc_delta_lbl"):
                        self.lc_delta_lbl.setText(f"Save failed: {err_msg[:28]}")
                        self.lc_delta_lbl.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 700;")
                    if hasattr(self, "lc_save_force_btn"):
                        self.lc_save_force_btn.setEnabled(True)
                        self.lc_save_force_btn.setText(f"Retry Save {new_force}g")
                if hasattr(mr, "_dispatch_signal"):
                    mr._dispatch_signal.emit(_on_err)

        threading.Thread(target=_bg, daemon=True).start()

    def _on_lc_tare(self):
        self.lc_tare_btn.setEnabled(False)
        self.lc_status_note.setText("Zeroing load cell sensor zero-point (LOAD_CELL_TARE)...")
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("LOAD_CELL_TARE", on_done=lambda ok: self._on_tare_done())
        else:
            QtCore.QTimer.singleShot(400, self._on_tare_done)

    def _on_tare_done(self):
        self.lc_tare_btn.setEnabled(True)
        self.lc_status_note.setText("\u2713 Sensor zero-point tared successfully.")
        self._poll_load_cell_status()

    def _on_lc_test_tap(self):
        self.lc_tap_btn.setEnabled(False)
        self.lc_status_note.setText("Performing nozzle test tap against bed (LOAD_CELL_TEST_TAP)...")
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("LOAD_CELL_TEST_TAP", on_done=lambda ok: self.lc_tap_btn.setEnabled(True))
        else:
            QtCore.QTimer.singleShot(1000, lambda: self.lc_tap_btn.setEnabled(True))

    def _on_start_load_cell_calibration(self):
        self._is_calibrating_lc = True
        self.lc_cal_btn.setEnabled(False)
        self.lc_cal_btn.setText("Calibrating...")
        self.lc_status_note.setText("Running LOAD_CELL_CALIBRATE sequence...")
        self.cmd_lbl.setText("LOAD_CELL_CALIBRATE  \u2022  CALIBRATING")
        mr = self._get_moonraker()
        if mr and mr.connected:
            mr.send_gcode("LOAD_CELL_CALIBRATE", on_done=lambda ok: self._on_load_cell_calibration_done(ok), timeout=120.0)
        else:
            QtCore.QTimer.singleShot(2500, lambda: self._on_load_cell_calibration_done(True))

    def _on_load_cell_calibration_done(self, ok: bool = True):
        self._is_calibrating_lc = False
        self.is_calibrating = False
        if hasattr(self, "_lc_poll_timer") and self._lc_poll_timer.isActive():
            self._lc_poll_timer.stop()

        self.gantry_anim.stop(completed=True)
        self.right_stack.setCurrentWidget(self.load_cell_results_panel)
        self.title_lbl.setText("Load Cell Calibration Results")
        self.cmd_lbl.setText("LOAD_CELL_CALIBRATE  \u2022  COMPLETE")

        self.lc_counts_lbl.setText(f"Counts / Gram: {self._counts_per_gram:.2f} counts/g")
        self.lc_res_tare_lbl.setText(f"Tare Counts: {self._tare_counts:,} counts")
        self.lc_res_force_lbl.setText(f"Trigger Force: {self._target_force} g")

        self.cancel_btn.setVisible(True)
        self.start_btn.setVisible(True)
        self.cancel_btn.setText("Close")
        self.cancel_btn.setEnabled(True)
        try:
            self.cancel_btn.clicked.disconnect()
        except Exception:
            pass
        self.cancel_btn.clicked.connect(self.accept)

        self.start_btn.setText("\U0001F4BE  Save && Apply Config (SAVE_CONFIG)")
        self.start_btn.setEnabled(True)
        self.start_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);"
            "border: 1px solid #34D399; color: #FFFFFF; font-weight: 800; border-radius: 10px; padding: 6px 14px;"
        )
        try:
            self.start_btn.clicked.disconnect()
        except Exception:
            pass
        self.start_btn.clicked.connect(self._on_save_config)

    def _on_close(self):
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        if hasattr(self, "_sim_timer") and self._sim_timer.isActive():
            self._sim_timer.stop()
        if hasattr(self, "_probe_poll_timer") and self._probe_poll_timer.isActive():
            self._probe_poll_timer.stop()
        if hasattr(self, "_lc_poll_timer") and self._lc_poll_timer.isActive():
            self._lc_poll_timer.stop()
        if self.is_calibrating:
            self.gantry_anim.stop()
            self.is_calibrating = False
        self.reject()

    def accept(self):
        self._cleanup()
        self.closed.emit()

    def reject(self):
        self._cleanup()
        self.closed.emit()

    def done(self, code=0):
        self._cleanup()
        self.closed.emit()

    def close(self):
        self._cleanup()
        self.closed.emit()
        super().close()

    def exec(self):
        pass

    def _cleanup(self):
        if hasattr(self, "_probe_poll_timer") and self._probe_poll_timer.isActive():
            self._probe_poll_timer.stop()
        if hasattr(self, "_lc_poll_timer") and self._lc_poll_timer.isActive():
            self._lc_poll_timer.stop()
        if hasattr(self, "_poll_timer") and self._poll_timer.isActive():
            self._poll_timer.stop()
        if hasattr(self, "gantry_anim"):
            self.gantry_anim.stop()
        self.is_calibrating = False

    def apply_scale(self, s: float):
        m = _s(10, s)
        self.card.layout().setContentsMargins(m, m, m, m)
        self.card.layout().setSpacing(_s(8, s))


class CalibrateCard(QtWidgets.QFrame):
    """Directly touchable calibration item card (no Run button)."""

    def __init__(self, item: dict, on_tap, parent=None):
        super().__init__(parent)
        self.item = item
        self.on_tap = on_tap
        self.setObjectName("CalibrateCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumWidth(0)

        self._layout = QtWidgets.QHBoxLayout(self)

        # Icon
        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # Info texts
        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(2)

        self.title_label = QtWidgets.QLabel(item["title"])
        self.title_label.setObjectName("CalTitle")
        self.title_label.setMinimumWidth(0)
        mid.addWidget(self.title_label)

        self.desc_label = QtWidgets.QLabel(item["desc"])
        self.desc_label.setObjectName("CalDesc")
        self.desc_label.setMinimumWidth(0)
        mid.addWidget(self.desc_label)

        cmd_row = QtWidgets.QHBoxLayout()
        self.cmd_badge = QtWidgets.QLabel(item.get("cmd") or "CALIBRATE")
        self.cmd_badge.setObjectName("CalCmdBadge")
        cmd_row.addWidget(self.cmd_badge)
        cmd_row.addStretch(1)
        mid.addLayout(cmd_row)

        self._layout.addLayout(mid, 1)

        # Right arrow indicator
        self.arrow = QtWidgets.QLabel("\u203A")
        self.arrow.setObjectName("CalCardArrow")
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_tap(self.item)
            event.accept()
        else:
            super().mousePressEvent(event)

    def apply_scale(self, s: float):
        m = _s(12, s)
        self._layout.setContentsMargins(m, _s(8, s), m, _s(8, s))
        self._layout.setSpacing(_s(10, s))
        self.icon_label.setPixmap(icons.pixmap(self.item["icon"], _s(38, s)))
        self.icon_label.setFixedSize(_s(42, s), _s(42, s))
        self.setFixedHeight(_s(82, s))


class CalibratePage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = "calibrate"
        self._scale = 1.0
        self._config = {}
        self._objects = []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Touch-friendly Scroll Area
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setObjectName("CalScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("CalContainer")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # 2-column grid layout
        self.grid = QtWidgets.QGridLayout(self.container)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cards = []
        self._rebuild_cards()

        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

    def update_config(self, config: dict, objects: list = None):
        """Update active Klipper config and dynamically rebuild supported calibration cards."""
        self._config = config or {}
        self._objects = objects or []
        self._rebuild_cards()

    def _rebuild_cards(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        filtered_items = [
            item for item in CALIBRATION_LIST
            if is_calibration_supported(item["id"], self._config, self._objects)
        ]

        for i, item in enumerate(filtered_items):
            card = CalibrateCard(item, on_tap=self.open_procedure_popup)
            card.apply_scale(self._scale)
            row = i // 2
            col = i % 2
            self.grid.addWidget(card, row, col)
            self.cards.append(card)

    def open_procedure_popup(self, item: dict):
        main_win = self.window()
        if item.get("id") == "bed_mesh":
            from .bed_mesh_page import BedMeshScreen
            view = BedMeshScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Bed Mesh", return_page="calibrate")
            else:
                view.show()
            return
        if item.get("id") == "probe_acc":
            from .probe_accuracy_page import ProbeAccuracyScreen
            view = ProbeAccuracyScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Probe Accuracy", return_page="calibrate")
            else:
                view.show()
            return
        if item.get("id") == "z_offset":
            from .z_offset_page import ZOffsetScreen
            view = ZOffsetScreen(scale=self._scale, parent=main_win)
            if hasattr(main_win, "open_sub_screen"):
                main_win.open_sub_screen(view, title="Z-Offset Calibration", return_page="calibrate")
            else:
                view.show()
            return
        view = CalibrationDialog(item, scale=self._scale, parent=main_win)
        if hasattr(main_win, "open_sub_screen"):
            main_win.open_sub_screen(view, title=item.get("title", "Calibration"), return_page="calibrate")
        else:
            view.show()

    def apply_scale(self, s: float):
        self._scale = s
        m = _s(14, s)
        self.grid.setContentsMargins(m, m, m, m)
        self.grid.setHorizontalSpacing(_s(12, s))
        self.grid.setVerticalSpacing(_s(10, s))
        for card in self.cards:
            card.apply_scale(s)
