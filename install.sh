#!/usr/bin/env bash
# ============================================================================
# Klipper Touch Display - Automated Installer
# ============================================================================

set -e

# Styling & Colors
C_RESET="\033[0m"
C_CYAN="\033[1;36m"
C_GREEN="\033[1;32m"
C_AMBER="\033[1;33m"
C_RED="\033[1;31m"
C_GRAY="\033[0;90m"

echo -e "${C_CYAN}"
echo "=========================================================="
echo "          KLIPPER TOUCH DISPLAY INSTALLER                 "
echo "=========================================================="
echo -e "${C_RESET}"

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
CURRENT_USER="$(id -un)"

# Check running environment
if [ "$EUID" -eq 0 ]; then
    echo -e "${C_AMBER}[!] Warning: Please run this script as your regular user (e.g., pi or biqu), not root.${C_RESET}"
    echo -e "${C_AMBER}    The installer will request sudo privileges when needed.${C_RESET}"
    exit 1
fi

# Ensure sudo access
if ! sudo -v; then
    echo -e "${C_RED}[ERROR] Sudo privileges are required to install system packages and services.${C_RESET}"
    exit 1
fi

echo -e "${C_GREEN}[1/4] Installing system dependencies via apt...${C_RESET}"
sudo apt-get update -y
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-pyqt6 \
    python3-pyqt6.qtsvg \
    xinit \
    x11-xserver-utils \
    matchbox-window-manager \
    libgl1 \
    libegl1

echo -e "${C_GREEN}[2/4] Setting up Python virtual environment...${C_RESET}"
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
fi

chmod +x "$INSTALL_DIR/launch.sh"

echo -e "\n${C_GREEN}[3/4] Checking for existing Klipper display startups...${C_RESET}"

EXISTING_SERVICE=""
for s in KlipperScreen.service klipperscreen.service klipper-screen.service; do
    if systemctl list-unit-files "$s" 2>/dev/null | grep -q "$s" || [ -f "/etc/systemd/system/$s" ] || [ -f "/lib/systemd/system/$s" ]; then
        EXISTING_SERVICE="$s"
        break
    fi
done

EXISTING_AUTOSTART=""
if [ -f "$HOME/.config/autostart/KlipperScreen.desktop" ]; then
    EXISTING_AUTOSTART="$HOME/.config/autostart/KlipperScreen.desktop"
elif [ -f "/etc/xdg/autostart/KlipperScreen.desktop" ]; then
    EXISTING_AUTOSTART="/etc/xdg/autostart/KlipperScreen.desktop"
fi

if [ -n "$EXISTING_SERVICE" ] || [ -n "$EXISTING_AUTOSTART" ]; then
    echo -e "${C_AMBER}----------------------------------------------------------${C_RESET}"
    echo -e "${C_AMBER}[!] Detected existing Klipper display startup:${C_RESET}"
    [ -n "$EXISTING_SERVICE" ] && echo -e "    ${C_CYAN}• Systemd Service: $EXISTING_SERVICE${C_RESET}"
    [ -n "$EXISTING_AUTOSTART" ] && echo -e "    ${C_CYAN}• Autostart desktop file: $EXISTING_AUTOSTART${C_RESET}"
    echo -e "${C_AMBER}----------------------------------------------------------${C_RESET}"
    read -r -p "Would you like to disable and replace the existing display startup? (y/n) [default: y]: " REPLACE_CHOICE
    REPLACE_CHOICE=${REPLACE_CHOICE:-y}
    if [[ "$REPLACE_CHOICE" =~ ^[Yy]$ ]]; then
        if [ -n "$EXISTING_SERVICE" ]; then
            echo -e "${C_GRAY}Stopping and disabling $EXISTING_SERVICE...${C_RESET}"
            sudo systemctl stop "$EXISTING_SERVICE" 2>/dev/null || true
            sudo systemctl disable "$EXISTING_SERVICE" 2>/dev/null || true
            sudo systemctl mask "$EXISTING_SERVICE" 2>/dev/null || true
            echo -e "${C_GREEN}✓ $EXISTING_SERVICE disabled and masked.${C_RESET}"
        fi
        if [ -n "$EXISTING_AUTOSTART" ]; then
            BACKUP_AUTOSTART="${EXISTING_AUTOSTART}.disabled_by_klipper_display"
            echo -e "${C_GRAY}Backing up autostart file to $BACKUP_AUTOSTART...${C_RESET}"
            sudo mv "$EXISTING_AUTOSTART" "$BACKUP_AUTOSTART" 2>/dev/null || true
            echo -e "${C_GREEN}✓ Autostart file backed up.${C_RESET}"
        fi
    else
        echo -e "${C_GRAY}Keeping existing display startup as requested.${C_RESET}"
    fi
else
    echo -e "${C_GRAY}No existing KlipperScreen service found.${C_RESET}"
fi

echo -e "\n${C_GREEN}[4/4] Configure Display Startup Mode...${C_RESET}"
echo -e "${C_CYAN}==========================================================${C_RESET}"
echo -e "Choose how you want Klipper Display to run on your system:"
echo -e "  ${C_GREEN}[1] Boot straight to app (Dedicated Kiosk Mode - Recommended)${C_RESET}"
echo -e "      • Boots directly into Klipper Display in fullscreen on startup."
echo -e "      • Standalone display session, disables desktop overhead."
echo -e "      • Touchscreen optimized with hidden mouse cursor."
echo -e "      • Matches standard KlipperScreen behavior."
echo ""
echo -e "  ${C_AMBER}[2] Desktop Mode with Shortcut${C_RESET}"
echo -e "      • Keeps / re-enables standard Raspberry Pi OS Desktop."
echo -e "      • Creates a desktop launcher icon (~/Desktop/KlipperDisplay.desktop)."
echo -e "      • Launch the display whenever you need by double-clicking."
echo -e "${C_CYAN}==========================================================${C_RESET}"
read -r -p "Enter selection [1 or 2] (default: 1): " MODE_CHOICE
MODE_CHOICE=${MODE_CHOICE:-1}

SERVICE_FILE="/etc/systemd/system/klipper-display.service"

if [ "$MODE_CHOICE" = "1" ]; then
    echo -e "\n${C_CYAN}Configuring Boot Straight to App (Kiosk Mode)...${C_RESET}"
    
    # Generate systemd service file
    cat <<EOF | sudo tee "$SERVICE_FILE" >/dev/null
[Unit]
Description=Klipper Touch Display Service
After=network-online.target moonraker.service
Wants=network-online.target moonraker.service

[Service]
Type=simple
User=$CURRENT_USER
Environment=DISPLAY=:0
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/xinit /bin/bash $INSTALL_DIR/launch.sh -- :0 vt7 -nocursor
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable klipper-display.service
    echo -e "${C_GREEN}✓ Enabled klipper-display.service on boot.${C_RESET}"

    read -r -p "Would you like to start the display service now? (y/n) [default: y]: " START_NOW
    START_NOW=${START_NOW:-y}
    if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
        echo -e "${C_GRAY}Starting klipper-display.service...${C_RESET}"
        sudo systemctl restart klipper-display.service
    fi

else
    echo -e "\n${C_CYAN}Configuring Desktop Mode with Shortcut...${C_RESET}"

    # Disable kiosk service if present
    if [ -f "$SERVICE_FILE" ]; then
        sudo systemctl stop klipper-display.service 2>/dev/null || true
        sudo systemctl disable klipper-display.service 2>/dev/null || true
    fi

    # Ensure desktop graphical target is default
    sudo systemctl set-default graphical.target 2>/dev/null || true

    # Prepare desktop directory
    DESKTOP_DIR="$HOME/Desktop"
    mkdir -p "$DESKTOP_DIR"
    mkdir -p "$HOME/.local/share/applications"

    DESKTOP_ENTRY="[Desktop Entry]
Version=1.0
Type=Application
Name=Klipper Display
Comment=Modern Touchscreen Interface for Klipper & Moonraker
Exec=/bin/bash $INSTALL_DIR/launch.sh --desktop
Icon=$INSTALL_DIR/assets/klipper.svg
Path=$INSTALL_DIR
Terminal=false
StartupNotify=true
Categories=Utility;Engineering;3DPrinting;
"

    # Write desktop launcher and application menu launcher
    echo "$DESKTOP_ENTRY" > "$DESKTOP_DIR/KlipperDisplay.desktop"
    echo "$DESKTOP_ENTRY" > "$HOME/.local/share/applications/klipper-display.desktop"

    chmod +x "$DESKTOP_DIR/KlipperDisplay.desktop"
    chmod +x "$HOME/.local/share/applications/klipper-display.desktop"

    # Trust desktop file on newer desktop managers (gio / pcmanfm)
    if command -v gio >/dev/null 2>&1; then
        gio set "$DESKTOP_DIR/KlipperDisplay.desktop" metadata::trusted true 2>/dev/null || true
    fi

    echo -e "${C_GREEN}✓ Created Desktop shortcut at $DESKTOP_DIR/KlipperDisplay.desktop${C_RESET}"
    echo -e "${C_GREEN}✓ Created Application Menu entry.${C_RESET}"
    echo -e "${C_GREEN}✓ Standard Desktop remains active.${C_RESET}"
fi

echo -e "\n${C_CYAN}==========================================================${C_RESET}"
echo -e "${C_GREEN}         INSTALLATION COMPLETED SUCCESSFULLY!            ${C_RESET}"
echo -e "${C_CYAN}==========================================================${C_RESET}"
if [ "$MODE_CHOICE" = "1" ]; then
    echo -e "• Mode: ${C_GREEN}Kiosk (Boot straight to app)${C_RESET}"
    echo -e "• Service: sudo systemctl restart klipper-display"
    echo -e "• Service status: sudo systemctl status klipper-display"
    echo -e "• View logs: journalctl -u klipper-display -f"
else
    echo -e "• Mode: ${C_AMBER}Desktop Mode${C_RESET}"
    echo -e "• Double-click ${C_CYAN}Klipper Display${C_RESET} on your desktop to launch."
    echo -e "• Manual terminal run: ${C_CYAN}$INSTALL_DIR/launch.sh --desktop${C_RESET}"
fi
echo -e "${C_CYAN}==========================================================${C_RESET}\n"

