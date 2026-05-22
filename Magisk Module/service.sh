#!/system/bin/sh
# ──────────────────────────────────────────────────────────────
#  FileBase — Late Boot Service
#  Auto-starts the file server after boot completes
#  Compatible: Magisk (28.0+), KernelSU (1.0.2+), APatch
# ──────────────────────────────────────────────────────────────

MODPATH="${0%/*}"

# Wait for the system to settle
sleep 30

# Only start if a hotspot or Wi-Fi interface is up (has IP)
HAS_NET=0
for iface in wlan0 ap0 swlan0 eth0 rndis0 softap0; do
    if ip -f inet addr show "$iface" 2>/dev/null | grep -q "inet "; then
        HAS_NET=1
        break
    fi
done

# Also try scanning all interfaces
if [ "$HAS_NET" -eq 0 ]; then
    if ip -f inet addr show 2>/dev/null | grep -v "127.0.0.1" | grep -q "inet "; then
        HAS_NET=1
    fi
fi

if [ "$HAS_NET" -eq 0 ]; then
    # No network — try again later
    sleep 60
    for iface in wlan0 ap0 swlan0 eth0 rndis0 softap0; do
        if ip -f inet addr show "$iface" 2>/dev/null | grep -q "inet "; then
            HAS_NET=1
            break
        fi
    done
fi

if [ "$HAS_NET" -eq 0 ]; then
    # Still no network — exit, user can start manually
    exit 0
fi

# Check if already running
if pgrep -f "python.*server.py" >/dev/null 2>&1; then
    exit 0
fi

# Start the server silently
sh "$MODPATH/action.sh" start >/dev/null 2>&1 &

exit 0
