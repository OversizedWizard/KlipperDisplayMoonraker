#!/usr/bin/env bash
# ============================================================================
# Klipper Touch Display - Application Launcher
# ============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Activate Python virtual environment
if [ -d "$DIR/venv" ]; then
    source "$DIR/venv/bin/activate"
elif [ -d "$HOME/klipper-display-env" ]; then
    source "$HOME/klipper-display-env/bin/activate"
fi

# Standalone X11 environment tuning (disable blanking, optional window manager)
if [ -z "$DESKTOP_SESSION" ] && [ -n "$DISPLAY" ]; then
    if command -v xset >/dev/null 2>&1; then
        xset s off -dpms s noblank 2>/dev/null || true
    fi
    if command -v matchbox-window-manager >/dev/null 2>&1; then
        matchbox-window-manager -use_titlebar no 2>/dev/null &
    fi
fi

# Launch application
if [ "$1" = "--desktop" ]; then
    shift
    exec python3 main.py "$@"
else
    exec python3 main.py --fullscreen --hide-cursor "$@"
fi

