#!/system/bin/sh
# ──────────────────────────────────────────────────────────
#  Android File Server Launcher
#  Serves /sdcard over the hotspot LAN on port 6532
#  Assigns a random auxiliary IP on the hotspot subnet
#  Requires: root (su), Python 3 on device
# ──────────────────────────────────────────────────────────

set -e

PORT=6532
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER="$SCRIPT_DIR/server.py"
STATE_FILE="/data/local/tmp/.webserver_state"

# ── Color output ──────────────────────────────────────────
red()   { echo -e "\033[31m$*\033[0m"; }
green() { echo -e "\033[32m$*\033[0m"; }
cyan()  { echo -e "\033[36m$*\033[0m"; }
yellow(){ echo -e "\033[33m$*\033[0m"; }

# ── Check root ────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo "Requesting root..."
    exec su -c "sh \"$0\" $*"
fi

green "[✓] Running as root"

# ── Check Python 3 ───────────────────────────────────────
PYTHON=""
for candidate in python3 python3.12 python3.11 python3.10 python3.9 python3.8; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

# Also search common Android paths
if [ -z "$PYTHON" ]; then
    for p in /data/data/*/files/usr/bin/python3 \
             /data/user/0/*/files/usr/bin/python3 \
             /sdcard/.python/bin/python3 \
             /data/local/tmp/python3; do
        if [ -x "$p" ]; then
            PYTHON="$p"
            break
        fi
    done
fi

if [ -z "$PYTHON" ]; then
    red "[✗] Python 3 not found!"
    echo ""
    echo "Install Python via one of these methods:"
    echo "  • Termux:    pkg install python"
    echo "  • Magisk:    Install python3 module"
    echo "  • Manual:    Push python3 binary to /data/local/tmp/"
    exit 1
fi

green "[✓] Python found: $PYTHON"

# ── Check server script exists ───────────────────────────
if [ ! -f "$SERVER" ]; then
    red "[✗] server.py not found at: $SERVER"
    exit 1
fi

green "[✓] Server script: $SERVER"

# ── Detect hotspot interface & IP ────────────────────────
HOTSPOT_IFACE=""
HOTSPOT_IP=""
SUBNET_PREFIX=""

# Collect all non-loopback inet addresses with iface names
ip -f inet addr show 2>/dev/null | awk '
  /^[0-9]+:/ { iface=$2; gsub(/:/, "", iface) }
  /inet / {
    split($2, a, "/")
    if (a[1] != "127.0.0.1") print iface, a[1]
  }
' > /tmp/.ws_ips

if [ -s /tmp/.ws_ips ]; then
    # Prefer 192.168.x.x (typical Android hotspot)
    while read -r iface addr; do
        case "$addr" in
            192.168.*) HOTSPOT_IFACE="$iface"; HOTSPOT_IP="$addr"; break ;;
        esac
    done < /tmp/.ws_ips

    # Fallback: any other private range
    if [ -z "$HOTSPOT_IP" ]; then
        while read -r iface addr; do
            case "$addr" in
                10.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*)
                    HOTSPOT_IFACE="$iface"; HOTSPOT_IP="$addr"; break ;;
            esac
        done < /tmp/.ws_ips
    fi
fi
rm -f /tmp/.ws_ips

if [ -n "$HOTSPOT_IP" ]; then
    SUBNET_PREFIX=$(echo "$HOTSPOT_IP" | sed 's/\.[0-9]*$//')
    green "[✓] Hotspot: $HOTSPOT_IFACE @ $HOTSPOT_IP"
else
    cyan "[?] No hotspot IP detected — server will listen on all interfaces"
fi

# ── Generate random auxiliary IP ─────────────────────────
BIND_IP=""
ALIAS_LABEL="webserver"

if [ -n "$SUBNET_PREFIX" ]; then
    # Pick a random host number: avoid 1 (gateway), 2-49 (DHCP pool),
    # and the device's own last octet
    my_last=$(echo "$HOTSPOT_IP" | sed 's/.*\.//')
    while true; do
        rand=$(( (RANDOM % 200) + 50 ))   # 50–249
        if [ "$rand" -ne "$my_last" ]; then
            break
        fi
    done
    BIND_IP="${SUBNET_PREFIX}.${rand}"
    green "[✓] Random IP: $BIND_IP (based on host $HOTSPOT_IP)"

    # Bind the auxiliary IP as an alias on the interface
    # Remove stale alias first (best effort)
    ip addr del "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true
    ip addr add "${BIND_IP}/24" dev "$HOTSPOT_IFACE" label "${HOTSPOT_IFACE}:${ALIAS_LABEL}" 2>/dev/null || \
        ip addr add "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true

    # Verify it stuck
    if ip -f inet addr show "$HOTSPOT_IFACE" 2>/dev/null | grep -q "$BIND_IP"; then
        green "[✓] Alias bound: ${HOTSPOT_IFACE}:${ALIAS_LABEL} → $BIND_IP"
    else
        yellow "[!] Alias binding may have failed — falling back to host IP"
        BIND_IP="$HOTSPOT_IP"
    fi
else
    BIND_IP="0.0.0.0"
    yellow "[!] No hotspot detected — binding all interfaces"
fi

# ── Save state for cleanup ───────────────────────────────
cat > "$STATE_FILE" <<EOF
HOTSPOT_IFACE=$HOTSPOT_IFACE
BIND_IP=$BIND_IP
HOTSPOT_IP=$HOTSPOT_IP
PORT=$PORT
ALIAS_LABEL=$ALIAS_LABEL
EOF

# ── Kill any existing server on this port ────────────────
old_pid=$(ss -tlnp 2>/dev/null | grep ":$PORT " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
if [ -n "$old_pid" ]; then
    echo "[*] Killing existing server (PID $old_pid)..."
    kill "$old_pid" 2>/dev/null || true
    sleep 1
fi

# ── Set up iptables to allow inbound connections on port ─
if [ -n "$HOTSPOT_IFACE" ]; then
    iptables -I INPUT -i "$HOTSPOT_IFACE" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    # Redirect port 80 on the auxiliary IP to our server port
    if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
        iptables -t nat -I PREROUTING -i "$HOTSPOT_IFACE" -d "$BIND_IP" -p tcp --dport 80 \
            -j REDIRECT --to-port "$PORT" 2>/dev/null || true
    fi
    green "[✓] iptables rules added for $HOTSPOT_IFACE"
fi

# ── Ensure /sdcard exists ────────────────────────────────
if [ ! -d "/sdcard" ]; then
    if [ -d "/storage/emulated/0" ]; then
        ln -sf /storage/emulated/0 /sdcard
        green "[✓] Created /sdcard symlink"
    else
        red "[✗] /sdcard not found and /storage/emulated/0 missing"
        exit 1
    fi
fi

# ── Start the server ─────────────────────────────────────
echo ""
cyan "╔══════════════════════════════════════════════════════════╗"
if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
    cyan "║  Server running! Connect to:                            ║"
    cyan "║  http://${BIND_IP}:${PORT}                                ║"
    cyan "║  http://${BIND_IP}  (port 80 redirected)                 ║"
    cyan "║  (host device: $HOTSPOT_IP)                              ║"
else
    cyan "║  Server running on port ${PORT}                           ║"
    cyan "║  Turn on hotspot and connect from another device        ║"
fi
cyan "║  Serving: /sdcard                                       ║"
cyan "║  Press Ctrl+C to stop                                   ║"
cyan "╚══════════════════════════════════════════════════════════╝"
echo ""

# Trap SIGINT/SIGTERM for cleanup
cleanup() {
    echo ""
    echo "[*] Cleaning up..."
    if [ -f "$STATE_FILE" ]; then
        . "$STATE_FILE"
    fi
    # Remove alias IP
    if [ -n "$BIND_IP" ] && [ -n "$HOTSPOT_IFACE" ] && [ "$BIND_IP" != "$HOTSPOT_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
        echo "[*] Removing alias $BIND_IP from $HOTSPOT_IFACE"
        ip addr del "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true
    fi
    # Remove iptables rules
    if [ -n "$HOTSPOT_IFACE" ]; then
        iptables -D INPUT -i "$HOTSPOT_IFACE" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
        if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
            iptables -t nat -D PREROUTING -i "$HOTSPOT_IFACE" -d "$BIND_IP" -p tcp --dport 80 \
                -j REDIRECT --to-port "$PORT" 2>/dev/null || true
        fi
    fi
    rm -f "$STATE_FILE"
    echo "[✓] Done"
    exit 0
}
trap cleanup INT TERM

# Launch server — run with unbuffered output for live logs
# Pass BIND_IP so the server binds only to that address
exec env BIND_IP="$BIND_IP" "$PYTHON" -u "$SERVER"
