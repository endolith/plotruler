#!/usr/bin/env bash
# Install PlotRuler for the current Linux user (run from the repo root).
#
# This uses the distro's Python and PySide6 rather than building a frozen
# binary, which is the idiomatic way to ship a Qt Python app on Linux.
#
# Usage:
#   ./scripts/install_linux.sh          # editable install + launcher
#   ./scripts/install_linux.sh --icons  # also install a tray/launcher icon
#
# Requires: python3, pip, python3-tk-free PySide6 wheel availability, and
# the system library libxcb-cursor (Qt 6.5+ xcb plugin).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
FLAVOR="${1:-}"

# Qt 6.5+ refuses to load its xcb platform plugin without the xcb-cursor
# library, and PlotRuler is X11-first on Linux. It is a system package, not
# a pip dependency, so pip install would succeed and the app would still
# abort at startup. Check for it first and point the user at their distro's
# package. ldconfig missing (e.g. non-glibc) means we cannot tell, so skip.
check_system_deps() {
    if ! command -v ldconfig >/dev/null 2>&1; then
        return 0
    fi
    if ! ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor'; then
        echo "PlotRuler needs the system library libxcb-cursor to run under X11." >&2
        echo "Install it with your package manager, then re-run this script:" >&2
        echo "  Debian/Ubuntu:  sudo apt install libxcb-cursor0" >&2
        echo "  Fedora/RHEL:    sudo dnf install xcb-util-cursor" >&2
        echo "  Arch:           sudo pacman -S xcb-util-cursor" >&2
        exit 1
    fi
}

check_system_deps

if command -v uv >/dev/null 2>&1; then
    uv pip install -e .
else
    python3 -m pip install -e .
fi

# Install the desktop launcher so PlotRuler shows in the app grid / can be
# launched by name. The Exec points at the installed 'plotruler' script.
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp build/plotruler.desktop "$DESKTOP_DIR/plotruler.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

if [ "$FLAVOR" = "--icons" ]; then
    ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$ICON_DIR"
    python3 -c "from plotruler.tray import make_icon; make_icon(256).pixmap(256,256).save('$ICON_DIR/plotruler.png', 'PNG')"
fi

echo "PlotRuler installed. Launch with: plotruler"
echo "To verify a first run: plotruler"
