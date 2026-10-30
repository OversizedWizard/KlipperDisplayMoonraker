# 🚀 Klipper Touch Display

A modern, high-performance, dark-themed touchscreen interface for **Klipper 3D Printers** and **Moonraker**.

Designed from the ground up for responsive touchscreens (7-inch, 5-inch, 4.3-inch, HDMI/DSI/SPI), featuring interactive visual calibration tools, real-time telemetry, and hardware-accelerated rendering.

---

## ✨ Features

- **🎯 Z-Offset & Paper Friction Calibration**:
  - Interactive nozzle clearance & squish visual diagram.
  - **Paper Friction Test**: Automated homing check, moves nozzle to probe center, and lowers smoothly to `Z=0.00 mm`.
  - **Live Jog Adjustments**: Step buttons (`0.005mm` to `0.100mm`) execute real-time physical micro-moves (`SET_GCODE_OFFSET MOVE=1`) so you feel friction change on the paper immediately.
  - 2-tap armed `SAVE_CONFIG` writes new offset permanently to `printer.cfg`.

- **⚡ Input Shaper Calibration**:
  - Direct integration with `adxl345`, `lis2dw`, and `mpu9250` resonance testers.
  - Live frequency vibration sweep telemetry (5 Hz to 135 Hz).
  - Automatically parses and displays recommended algorithms (`MZV`, `EI`, `2HUMP_EI`, `3HUMP_EI`) with one-tap `SAVE_CONFIG`.

- **📐 Bed Mesh Visualizer**:
  - Dynamically detects your configured mesh grid from `printer.cfg` (supports both rectangular beds and circular/delta beds).
  - Live probe point counters and visual inspection diagram.

- **🎯 Probe Accuracy Test**:
  - Standard deviation, range, min, and max calculations with live sample counting.

- **⚖️ Load Cell Calibration & Live Tare**:
  - Real-time nozzle contact force monitoring in grams.
  - Nozzle test tap verification, empty tare zeroing, and 2-step calibration with known reference weight.

- **🔥 Thermal & Extruder Management**:
  - Beautiful preheat popups for PLA, PETG, ABS, TPU, and custom targets.
  - Animated extruder feed gears during extrusion and retraction.

- **🧵 Filament & Spool Manager**:
  - Step-by-step load, unload, purge, and cold pull workflows.

---

## 🖥️ Requirements

- **Supported Hardware**: Raspberry Pi (3B+, 4B, 5, Zero 2W), BTT Pi, CB1, Orange Pi, or any Linux PC/SBC.
- **Operating System**: Raspberry Pi OS (Debian Bullseye / Bookworm), Ubuntu, Armbian, or Linux Mint.
- **Backend**: Working [Klipper](https://github.com/Klipper3d/klipper) and [Moonraker](https://github.com/Arksine/moonraker) installation.

---

## 📦 Installation

Clone this repository to your printer host (e.g., Raspberry Pi) and run the automated installer:

```bash
cd ~
git clone https://github.com/OversizedWizard/KlipperDisplayMoonraker.git
cd KlipperDisplayMoonraker
chmod +x install.sh
./install.sh
```

---

## 🛠️ Installer Options

The installer is completely interactive and handles system dependencies, Python virtual environment, and startup configuration:

### 1. Existing KlipperScreen Detection
The installer automatically scans for existing `KlipperScreen.service` or autostart desktop entries:
```text
[!] Detected existing Klipper display startup:
    • Systemd Service: KlipperScreen.service
Would you like to disable and replace the existing display startup? (y/n) [default: y]:
```
- Choosing **`y`** safely stops, disables, and masks the existing service so there are no display conflicts.

### 2. Startup Mode Selection
Choose how your display boots:
```text
Choose how you want Klipper Display to run on your system:
  [1] Boot straight to app (Dedicated Kiosk Mode - Recommended)
      • Boots directly into Klipper Display in fullscreen on startup.
      • Standalone display session, disables desktop overhead.
      • Touchscreen optimized with hidden mouse cursor.
      • Matches standard KlipperScreen behavior.

  [2] Desktop Mode with Shortcut
      • Keeps / re-enables standard Raspberry Pi OS Desktop.
      • Creates a desktop launcher icon (~/Desktop/KlipperDisplay.desktop).
      • Launch the display whenever you need by double-clicking.
```

---

## 🎮 Manual Run & Command-Line Flags

To test or run manually from the terminal:

```bash
# Fullscreen kiosk on touchscreen (hides mouse cursor):
./launch.sh

# Windowed mode on desktop:
./launch.sh --desktop

# Direct Python run with custom resolution:
python3 main.py --width 1024 --height 600
```

### Available Arguments
| Flag | Description |
|------|-------------|
| `--fullscreen` | Runs window in borderless fullscreen mode. |
| `--hide-cursor` | Hides the mouse pointer for touchscreen use. |
| `--width <pixels>` | Sets custom window width (default: 800). |
| `--height <pixels>` | Sets custom window height (default: 480). |

---

## 🔧 Service Management

If installed in **Kiosk Mode**, control the service using standard `systemctl` commands:

```bash
# Restart the display service:
sudo systemctl restart klipper-display

# Stop the display service:
sudo systemctl stop klipper-display

# Check live service status:
sudo systemctl status klipper-display

# View live application logs:
journalctl -u klipper-display -f
```

---

## 🗑️ Uninstallation

If you ever wish to remove the display or restore your previous KlipperScreen setup:

```bash
chmod +x uninstall.sh
./uninstall.sh
```
The uninstaller removes the service, deletes desktop icons, and offers to unmask and re-enable your original `KlipperScreen.service`.

---

## 📄 License
This project is licensed under the MIT License. See `LICENSE` for details.

