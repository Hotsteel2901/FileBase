#!/system/bin/sh
# ──────────────────────────────────────────────────────────────
#  FileBase — Installation Script
#  Copies server files & sets permissions
#  Compatible: Magisk (28.0+), KernelSU (1.0.2+), APatch
# ──────────────────────────────────────────────────────────────

[ -z "$MODPATH" ] && MODPATH="${0%/*}"

# Detect root environment
if command -v apd >/dev/null 2>&1; then
    ROOT_ENV="APatch"
elif [ -n "$KSU" ]; then
    ROOT_ENV="KernelSU"
elif [ -n "$MAGISK_VER_CODE" ]; then
    ROOT_ENV="Magisk"
else
    ROOT_ENV="Unknown"
fi

ui_print "─────────────────────────────────────"
ui_print "  FileBase — Android File Server"
ui_print "  Root env: $ROOT_ENV"
ui_print "─────────────────────────────────────"

# Copy server files to module directory
ui_print "  → Installing server files..."
cp -f "$MODPATH/common/server.py"  "$MODPATH/server.py"  2>/dev/null
cp -f "$MODPATH/common/launch.sh"  "$MODPATH/launch.sh"  2>/dev/null
cp -f "$MODPATH/common/stop.sh"    "$MODPATH/stop.sh"    2>/dev/null

# Set executable permissions
chmod 755 "$MODPATH/server.py"   2>/dev/null
chmod 755 "$MODPATH/launch.sh"   2>/dev/null
chmod 755 "$MODPATH/stop.sh"     2>/dev/null
chmod 755 "$MODPATH/action.sh"   2>/dev/null
chmod 755 "$MODPATH/service.sh"  2>/dev/null

# Create runtime directory
mkdir -p /data/local/webserver 2>/dev/null

# Copy server files to runtime path as well (for manual usage)
cp -f "$MODPATH/common/server.py"  /data/local/webserver/server.py  2>/dev/null
cp -f "$MODPATH/common/launch.sh"  /data/local/webserver/launch.sh  2>/dev/null
cp -f "$MODPATH/common/stop.sh"    /data/local/webserver/stop.sh    2>/dev/null
chmod 755 /data/local/webserver/server.py   2>/dev/null
chmod 755 /data/local/webserver/launch.sh   2>/dev/null
chmod 755 /data/local/webserver/stop.sh     2>/dev/null

# Check for Python availability
PYTHON_OK=0
if command -v python3 >/dev/null 2>&1; then
    ui_print "  ✓ Python 3 found at: $(command -v python3)"
    PYTHON_OK=1
elif [ -x /data/data/com.termux/files/usr/bin/python3 ]; then
    ui_print "  ✓ Python 3 found (Termux)"
    PYTHON_OK=1
elif [ -x /data/local/tmp/python3 ]; then
    ui_print "  ✓ Python 3 found (manual install)"
    PYTHON_OK=1
elif [ -x /data/adb/python3 ]; then
    ui_print "  ✓ Python 3 found (/data/adb)"
    PYTHON_OK=1
fi

if [ "$PYTHON_OK" -eq 0 ]; then
    ui_print "  ⚠ Python 3 NOT found!"
    ui_print "    Install Python 3 via Termux:"
    ui_print "      pkg install python"
    ui_print "    Then reboot or re-flash this module."
fi

ui_print "  ✓ Installation complete"
ui_print ""
ui_print "  Usage:"
ui_print "    sh /data/local/webserver/launch.sh  (start)"
ui_print "    sh /data/local/webserver/stop.sh    (stop)"
ui_print "  Or use the action button in your root manager."
ui_print "─────────────────────────────────────"
