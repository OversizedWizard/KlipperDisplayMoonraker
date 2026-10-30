#!/usr/bin/env bash
# ============================================================================
# Klipper Touch Display - Uninstaller
# ============================================================================

set -e

echo "Uninstalling Klipper Touch Display..."

# Stop and disable service
if [ -f "/etc/systemd/system/klipper-display.service" ]; then
    echo "Stopping and removing klipper-display.service..."
    sudo systemctl stop klipper-display.service 2>/dev/null || true
    sudo systemctl disable klipper-display.service 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/klipper-display.service"
    sudo systemctl daemon-reload
fi

# Remove desktop shortcuts
rm -f "$HOME/Desktop/KlipperDisplay.desktop"
rm -f "$HOME/.local/share/applications/klipper-display.desktop"

# Check if an existing KlipperScreen service was masked and prompt to restore
for s in KlipperScreen.service klipperscreen.service klipper-screen.service; do
    if systemctl is-enabled "$s" 2>/dev/null | grep -q "masked"; then
        read -r -p "Detected masked $s. Would you like to unmask and re-enable it? (y/n) [y]: " RESTORE
        RESTORE=${RESTORE:-y}
        if [[ "$RESTORE" =~ ^[Yy]$ ]]; then
            sudo systemctl unmask "$s"
            sudo systemctl enable "$s"
            sudo systemctl start "$s"
            echo "Restored $s."
        fi
    fi
done

# Check if autostart was backed up
for bak in "$HOME/.config/autostart/KlipperScreen.desktop.disabled_by_klipper_display" "/etc/xdg/autostart/KlipperScreen.desktop.disabled_by_klipper_display"; do
    if [ -f "$bak" ]; then
        orig="${bak%.disabled_by_klipper_display}"
        read -r -p "Restore $orig? (y/n) [y]: " RESTORE_AUTO
        RESTORE_AUTO=${RESTORE_AUTO:-y}
        if [[ "$RESTORE_AUTO" =~ ^[Yy]$ ]]; then
            sudo mv "$bak" "$orig"
            echo "Restored $orig."
        fi
    fi
done

echo "Uninstallation complete."

