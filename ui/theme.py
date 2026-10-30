"""Theme: colours + stylesheet generator.

The UI is designed at BASE_W x BASE_H (800x480) for 5-inch Raspberry Pi screens.
Every size in the stylesheet is multiplied by a scale factor so the interface fits any screen.
"""

BASE_W, BASE_H = 800, 480

COLORS = {
    "text": "#F3F4F6",
    "muted": "#94A3B8",
    "dim": "#64748B",
    "cyan": "#00E5FF",
    "border": "rgba(255, 255, 255, 22)",
}


def build_stylesheet(s: float) -> str:
    """Return the application stylesheet scaled by factor `s`."""

    def px(v: float) -> str:
        return f"{max(1, round(v * s))}px"

    c = COLORS
    return f"""
QWidget {{
    color: {c['text']};
    font-family: "Inter", "Segoe UI", "Roboto", "DejaVu Sans", sans-serif;
    font-size: {px(13)};
}}

QWidget#Root {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0F1624, stop:1 #07090E);
}}

/* ---------- Sidebar ---------- */
QFrame#Sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #121A2A, stop:1 #0C111C);
    border-right: 1px solid {c['border']};
}}

QToolButton#NavButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {px(14)};
    color: {c['muted']};
    font-size: {px(11)};
    font-weight: 600;
    padding-top: {px(6)};
    padding-bottom: {px(4)};
}}
QToolButton#NavButton:hover {{
    background: rgba(255, 255, 255, 12);
    color: {c['text']};
}}
QToolButton#NavButton:pressed {{
    background: rgba(0, 229, 255, 30);
}}
QToolButton#NavButton:checked {{
    color: #FFFFFF;
    border: 1px solid rgba(0, 229, 255, 110);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 229, 255, 40), stop:1 rgba(58, 134, 255, 70));
}}
QToolButton#NavButton[accent="danger"]:checked {{
    border: 1px solid rgba(244, 63, 94, 130);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 138, 91, 40), stop:1 rgba(225, 29, 72, 75));
}}

/* ---------- Top bar ---------- */
QFrame#TopBar {{
    background: rgba(16, 22, 36, 200);
    border-bottom: 1px solid {c['border']};
}}
QLabel#PageTitle {{
    font-size: {px(18)};
    font-weight: 700;
}}
QLabel#PrinterName {{
    color: {c['dim']};
    font-size: {px(12)};
    font-weight: 600;
}}
QLabel#StatusPill {{
    color: #FBBF24;
    background: rgba(251, 191, 36, 28);
    border: 1px solid rgba(251, 191, 36, 90);
    border-radius: {px(11)};
    padding: {px(3)} {px(10)};
    font-size: {px(11)};
    font-weight: 700;
}}
QLabel#StatusPill[state="connected"] {{
    color: #34D399;
    background: rgba(16, 185, 129, 32);
    border: 1px solid rgba(16, 185, 129, 120);
}}
QLabel#StatusPill[state="standby"] {{
    color: #38BDF8;
    background: rgba(56, 189, 248, 28);
    border: 1px solid rgba(56, 189, 248, 110);
}}
QLabel#StatusPill[state="disconnected"] {{
    color: #F87171;
    background: rgba(239, 68, 68, 28);
    border: 1px solid rgba(239, 68, 68, 100);
}}
QLabel#Clock {{
    background: rgba(255, 255, 255, 12);
    border: 1px solid {c['border']};
    border-radius: {px(8)};
    padding: {px(4)} {px(10)};
    font-size: {px(13)};
    font-weight: 700;
}}
QLabel#ProbePill {{
    color: #34D399;
    background: rgba(16, 185, 129, 24);
    border: 1px solid rgba(16, 185, 129, 90);
    border-radius: {px(8)};
    padding: {px(4)} {px(10)};
    font-size: {px(12)};
    font-weight: 800;
    font-family: "Consolas", "Courier New", monospace;
}}
QLabel#ProbePill:hover {{
    background: rgba(16, 185, 129, 45);
    border-color: #34D399;
}}
QLabel#ProbePill[state="alert"] {{
    color: #FBBF24;
    background: rgba(251, 191, 36, 28);
    border: 1px solid rgba(251, 191, 36, 100);
}}

/* ---------- Content ---------- */
QFrame#Card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(30, 39, 62, 200), stop:1 rgba(18, 24, 39, 220));
    border: 1px solid {c['border']};
    border-radius: {px(18)};
}}
QLabel#Hero {{
    font-size: {px(28)};
    font-weight: 800;
}}
QLabel#Subtitle {{
    color: {c['muted']};
    font-size: {px(14)};
}}
QLabel#Chip {{
    color: {c['cyan']};
    background: rgba(0, 229, 255, 22);
    border: 1px solid rgba(0, 229, 255, 80);
    border-radius: {px(12)};
    padding: {px(5)} {px(14)};
    font-size: {px(11)};
    font-weight: 700;
}}

/* ---------- Temperature cards ---------- */
QFrame#TempCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(30, 39, 62, 210), stop:1 rgba(18, 24, 39, 230));
    border: 1px solid {c['border']};
    border-radius: {px(16)};
}}
QFrame#TempCard:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(38, 50, 78, 240), stop:1 rgba(22, 30, 48, 250));
}}
QFrame#TempCard[kind="nozzle"] {{ border: 1px solid rgba(255, 122, 0, 70); }}
QFrame#TempCard[kind="nozzle"]:hover {{ border: 1px solid rgba(255, 122, 0, 160); }}
QFrame#TempCard[kind="bed"] {{ border: 1px solid rgba(0, 229, 255, 70); }}
QFrame#TempCard[kind="bed"]:hover {{ border: 1px solid rgba(0, 229, 255, 160); }}

QLabel#TempTitle {{
    color: {c['muted']};
    font-size: {px(12)};
    font-weight: 700;
}}
QLabel#TempValue {{
    font-size: {px(34)};
    font-weight: 800;
}}
QLabel#TempTarget {{
    color: {c['muted']};
    font-size: {px(12)};
    font-weight: 600;
}}
QLabel#TempState {{
    border-radius: {px(9)};
    padding: {px(3)} {px(8)};
    font-size: {px(10)};
    font-weight: 800;
}}
QLabel#TempState[state="heating"] {{
    color: #FF9A3C; background: rgba(255, 122, 0, 30); border: 1px solid rgba(255, 122, 0, 110);
}}
QLabel#TempState[state="ready"] {{
    color: #34D399; background: rgba(16, 185, 129, 30); border: 1px solid rgba(16, 185, 129, 110);
}}
QLabel#TempState[state="cooling"] {{
    color: #67E8F9; background: rgba(0, 229, 255, 25); border: 1px solid rgba(0, 229, 255, 100);
}}
QLabel#TempState[state="off"] {{
    color: {c['dim']}; background: rgba(255, 255, 255, 10); border: 1px solid {c['border']};
}}

QProgressBar#TempBar {{
    background: rgba(255, 255, 255, 16);
    border: none;
    border-radius: {px(4)};
}}
QProgressBar#TempBar::chunk {{
    border-radius: {px(4)};
}}
QProgressBar#TempBar[kind="nozzle"]::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFB547, stop:1 #FF4D00);
}}
QProgressBar#TempBar[kind="bed"]::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #3A86FF);
}}

/* ---------- Load Cell Probe Strip on Home Page ---------- */
QFrame#LoadCellStrip {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(20, 28, 46, 230), stop:1 rgba(11, 16, 28, 250));
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: {px(8)};
}}
QFrame#LoadCellStrip:hover {{
    border: 1px solid rgba(0, 229, 255, 120);
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(28, 38, 62, 240), stop:1 rgba(15, 22, 38, 255));
}}

/* ---------- Calibration Cards ---------- */
QFrame#CalibrateCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(28, 36, 56, 190), stop:1 rgba(16, 22, 36, 210));
    border: 1px solid {c['border']};
    border-radius: {px(14)};
}}
QFrame#CalibrateCard:hover {{
    border: 1px solid rgba(0, 229, 255, 90);
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(34, 44, 70, 220), stop:1 rgba(20, 28, 46, 230));
}}
QFrame#CalibrateCard:pressed {{
    background: rgba(0, 229, 255, 25);
    border: 1px solid rgba(0, 229, 255, 160);
}}

QLabel#CalTitle {{
    font-size: {px(14)};
    font-weight: 700;
    color: {c['text']};
}}

QLabel#CalCmdBadge {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: {px(10)};
    font-weight: 700;
    color: {c['cyan']};
    background: rgba(0, 229, 255, 20);
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: {px(6)};
    padding: {px(2)} {px(8)};
}}

QLabel#CalDesc {{
    font-size: {px(11)};
    color: {c['muted']};
}}

QLabel#CalCardArrow {{
    font-size: {px(22)};
    font-weight: 700;
    color: {c['dim']};
    padding-right: {px(4)};
}}
QFrame#CalibrateCard:hover QLabel#CalCardArrow {{
    color: {c['cyan']};
}}

/* ---------- Procedural Modal Dialog ---------- */
QFrame#DialogCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #141C2E, stop:1 #0B0F19);
    border: 1px solid rgba(0, 229, 255, 100);
    border-radius: {px(20)};
}}

QLabel#DialogTitle {{
    font-size: {px(17)};
    font-weight: 800;
    color: #FFFFFF;
}}

QPushButton#DialogCloseX {{
    background: rgba(255, 255, 255, 10);
    border: 1px solid {c['border']};
    border-radius: {px(14)};
    color: {c['muted']};
    font-size: {px(14)};
    font-weight: 700;
    min-width: {px(28)};
    min-height: {px(28)};
    max-width: {px(28)};
    max-height: {px(28)};
}}
QPushButton#DialogCloseX:hover {{
    background: rgba(239, 68, 68, 40);
    border-color: rgba(239, 68, 68, 120);
    color: #FFFFFF;
}}

QFrame#DialogInfoBox {{
    background: rgba(245, 158, 11, 16);
    border: 1px solid rgba(245, 158, 11, 70);
    border-radius: {px(10)};
}}

QFrame#DialogStepsBox {{
    background: rgba(0, 0, 0, 40);
    border: 1px solid {c['border']};
    border-radius: {px(10)};
}}

QLabel#DialogSectionHdr {{
    font-size: {px(10)};
    font-weight: 800;
    letter-spacing: 0.5px;
    color: #FBBF24;
}}
QFrame#DialogStepsBox QLabel#DialogSectionHdr {{
    color: {c['cyan']};
}}

QLabel#DialogSectionTxt {{
    font-size: {px(11)};
    color: {c['text']};
    line-height: 1.3;
}}

QLabel#DialogStepLine {{
    font-size: {px(11)};
    color: #E2E8F0;
    padding-left: {px(4)};
}}

QPushButton#DialogCancelBtn {{
    background: rgba(255, 255, 255, 10);
    border: 1px solid {c['border']};
    border-radius: {px(10)};
    color: {c['muted']};
    font-size: {px(13)};
    font-weight: 700;
    min-height: {px(40)};
    padding: 0 {px(18)};
}}
QPushButton#DialogCancelBtn:hover {{
    background: rgba(255, 255, 255, 18);
    color: {c['text']};
}}

QPushButton#DialogStartBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #00E5FF, stop:1 #2563EB);
    color: #05070A;
    border: none;
    border-radius: {px(10)};
    font-size: {px(13)};
    font-weight: 800;
    min-height: {px(40)};
    padding: 0 {px(20)};
}}
QPushButton#DialogStartBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #38F8FF, stop:1 #3B82F6);
}}
QPushButton#DialogStartBtn:pressed {{
    background: #00B4D8;
}}
QPushButton#DialogStartBtn:disabled {{
    background: rgba(255, 255, 255, 20);
    color: {c['dim']};
}}

/* ---------- Preheat Preset, Cooldown & Apply Buttons ---------- */
QPushButton#PreheatPresetBtn {{
    background: rgba(255, 255, 255, 12);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: {px(8)};
    color: #F1F5F9;
    font-weight: 700;
    font-size: {px(12)};
    line-height: 1.2;
}}
QPushButton#PreheatPresetBtn:hover {{
    background: rgba(0, 229, 255, 25);
    border-color: rgba(0, 229, 255, 120);
    color: #00E5FF;
}}
QPushButton#PreheatPresetBtn[active="true"] {{
    background: rgba(0, 229, 255, 40);
    border: 1px solid #00E5FF;
    color: #00E5FF;
}}

QPushButton#PreheatCooldownBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 229, 255, 30), stop:1 rgba(37, 99, 235, 45));
    border: 1px solid #00E5FF;
    border-radius: {px(10)};
    color: #67E8F9;
    font-weight: 800;
    font-size: {px(12)};
    padding: 0 {px(14)};
}}
QPushButton#PreheatCooldownBtn:hover {{
    background: rgba(0, 229, 255, 60);
    color: #FFFFFF;
}}

QPushButton#PreheatApplyBtn {{
    border-radius: {px(10)};
    font-size: {px(13)};
    font-weight: 800;
    color: #FFFFFF;
    padding: 0 {px(16)};
}}
QPushButton#PreheatApplyBtn[kind="nozzle"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FF7A00, stop:1 #FF4D00);
    border: 1px solid #FFA149;
}}
QPushButton#PreheatApplyBtn[kind="nozzle"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FF9433, stop:1 #FF601A);
}}
QPushButton#PreheatApplyBtn[kind="bed"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #00E5FF, stop:1 #2563EB);
    border: 1px solid #38F8FF;
}}
QPushButton#PreheatApplyBtn[kind="bed"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #38F8FF, stop:1 #3B82F6);
}}

/* ---------- Axis Coordinate & Jog Controls ---------- */
QFrame#AxisCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(28, 36, 56, 210), stop:1 rgba(16, 22, 36, 230));
    border: 1px solid {c['border']};
    border-radius: {px(14)};
}}
QFrame#AxisCard[axis="X"] {{ border-left: 3px solid #00E5FF; }}
QFrame#AxisCard[axis="Y"] {{ border-left: 3px solid #10B981; }}
QFrame#AxisCard[axis="Z"] {{ border-left: 3px solid #A855F7; }}

QLabel#AxisTitle {{
    font-size: {px(13)};
    font-weight: 800;
    color: #CBD5E1;
    margin: 0px;
    padding: 0px;
}}
QLabel#AxisCoord {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: {px(18)};
    font-weight: 800;
    color: #FFFFFF;
}}
QLabel#AxisHomedBadge {{
    border-radius: {px(4)};
    padding: {px(1)} {px(3)};
    font-size: {px(8)};
    font-weight: 700;
}}
QLabel#AxisHomedBadge[homed="true"] {{
    color: #34D399;
    background: rgba(16, 185, 129, 25);
    border: 1px solid rgba(16, 185, 129, 90);
}}
QLabel#AxisHomedBadge[homed="false"] {{
    color: #94A3B8;
    background: rgba(255, 255, 255, 12);
    border: 1px solid rgba(255, 255, 255, 24);
}}

QFrame#JogCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(26, 34, 52, 200), stop:1 rgba(15, 20, 32, 220));
    border: 1px solid {c['border']};
    border-radius: {px(16)};
}}

QPushButton#JogBtn {{
    background: rgba(255, 255, 255, 14);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: {px(12)};
    color: #F8FAFC;
    font-size: {px(24)};
    font-weight: 800;
}}
QPushButton#JogBtn:hover {{
    background: rgba(0, 229, 255, 30);
    border-color: rgba(0, 229, 255, 120);
    color: #00E5FF;
}}
QPushButton#JogBtn:pressed {{
    background: rgba(0, 229, 255, 60);
}}

QPushButton#JogHomeBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 229, 255, 45), stop:1 rgba(37, 99, 235, 65));
    border: 1px solid rgba(0, 229, 255, 140);
    border-radius: {px(12)};
    color: #FFFFFF;
    font-size: {px(13)};
    font-weight: 800;
}}
QPushButton#JogHomeBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(56, 248, 255, 70), stop:1 rgba(59, 130, 246, 90));
}}
QPushButton#JogHomeBtn:pressed {{
    background: #00B4D8;
}}

QPushButton#StepBtn {{
    background: rgba(255, 255, 255, 12);
    border: 1px solid {c['border']};
    border-radius: {px(8)};
    color: #F1F5F9;
    font-size: {px(14)};
    font-weight: 800;
}}
QPushButton#StepBtn:hover {{
    background: rgba(255, 255, 255, 20);
    color: {c['text']};
}}
QPushButton#StepBtn:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #00E5FF, stop:1 #2563EB);
    border: 1px solid #38BDF8;
    color: #05070A;
    font-weight: 800;
}}

QPushButton#HomeAllBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 229, 255, 40), stop:1 rgba(37, 99, 235, 60));
    border: 1px solid rgba(0, 229, 255, 120);
    border-radius: {px(8)};
    color: #E0F2FE;
    font-size: {px(11)};
    font-weight: 800;
    min-height: {px(30)};
    padding: 0 {px(12)};
}}
QPushButton#HomeAllBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(56, 248, 255, 65), stop:1 rgba(59, 130, 246, 85));
    border-color: #38BDF8;
    color: #FFFFFF;
}}
QPushButton#HomeAllBtn:pressed {{
    background: #00B4D8;
    color: #05070A;
}}

QPushButton#MotorsOffBtn {{
    background: rgba(239, 68, 68, 25);
    border: 1px solid rgba(239, 68, 68, 100);
    border-radius: {px(8)};
    color: #FCA5A5;
    font-size: {px(11)};
    font-weight: 800;
    min-height: {px(30)};
    padding: 0 {px(12)};
}}
QPushButton#MotorsOffBtn:hover {{
    background: rgba(239, 68, 68, 50);
    border-color: rgba(239, 68, 68, 180);
    color: #FFFFFF;
}}
QPushButton#MotorsOffBtn:pressed {{
    background: #DC2626;
    color: #FFFFFF;
}}

/* Scroll Area & Container */
QScrollArea#CalScrollArea,
QWidget#CalContainer,
QScrollArea#CalScrollArea > QWidget,
QScrollArea#CalScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

/* Scrollbar */
QScrollBar:vertical {{
    background: transparent;
    width: {px(8)};
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 30);
    border-radius: {px(4)};
    min-height: {px(24)};
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(0, 229, 255, 120);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
"""

