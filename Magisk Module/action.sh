#!/system/bin/sh
# ──────────────────────────────────────────────────────────────
#  FileBase — Action Script
#  Start / Stop / Restart / Status the file server
#  Called by root manager's "Action" button
#  Compatible: Magisk (28.0+), KernelSU (1.0.2+), APatch
# ──────────────────────────────────────────────────────────────

MODPATH="${0%/*}"
MOD_ID="filebase"
SCRIPT_DIR="${MODPATH}"
LAUNCHER="${MODPATH}/launch.sh"
STOPPER="${MODPATH}/stop.sh"
SERVER_PY="${MODPATH}/server.py"
PID_FILE="/data/local/webserver/.server_pid"
STATE_FILE="/data/local/tmp/.webserver_state"
PORT=6532

# ── Color helpers ───────────────────────────────────────────
print_header() {
    echo "╔══════════════════════════════════╗"
    echo "║  FileBase Server Control         ║"
    echo "╚══════════════════════════════════╝"
}

print_ok()   { echo "[✓] $*"; }
print_err()  { echo "[✗] $*"; }
print_info() { echo "[*] $*"; }

# ── Root env detection ──────────────────────────────────────
detect_root() {
    if command -v apd >/dev/null 2>&1; then
        echo "APatch"
    elif [ -n "$KSU" ]; then
        echo "KernelSU"
    elif [ -n "$MAGISK_VER_CODE" ]; then
        echo "Magisk"
    else
        echo "Unknown"
    fi
}

# ── Get a PID by name ───────────────────────────────────────
get_pid() {
    # Exclude the current shell ($$) because the command line of this script
    # itself contains the regex pattern and would otherwise match pgrep -f.
    for pid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$pid" -eq "$$" ] && continue
        echo "$pid"
        return 0
    done
    # Fallback: check PID file
    if [ -f "$PID_FILE" ]; then
        read p < "$PID_FILE"
        if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
            echo "$p"
            return 0
        fi
    fi
    return 1
}

# ── Status ──────────────────────────────────────────────────
do_status() {
    print_header
    echo ""
    # Read log level from config
    LOG_LVL="info"
    [ -f "${MODPATH}/logs/.config" ] && LOG_LVL=$(cat "${MODPATH}/logs/.config" 2>/dev/null | head -1 | tr -d '\n\r ')

    echo "  Root environment: $(detect_root)"
    echo "  Port: $PORT"
    echo "  Log level: $LOG_LVL"
    echo "  Module path: $MODPATH"
    echo ""

    if pid=$(get_pid); then
        print_ok "Server RUNNING (PID: $pid)"
        echo ""

        # Show stats if server is running
        if [ -f "$STATE_FILE" ]; then
            . "$STATE_FILE"
            echo "  Interface: ${HOTSPOT_IFACE:-N/A}"
            echo "  Bind IP:   ${BIND_IP:-N/A}"
        fi

        # Test if server responds
        BIND_IP=""
        [ -f "$STATE_FILE" ] && . "$STATE_FILE" 2>/dev/null
        TEST_ADDR="${BIND_IP:-127.0.0.1}"
        if curl -s --max-time 2 "http://${TEST_ADDR}:${PORT}/" >/dev/null 2>&1; then
            print_ok "Server responds OK"
        else
            print_err "Server does not respond (check firewall / iptables)"
        fi
    else
        print_err "Server STOPPED"
    fi
    echo ""
}

# ── Start ───────────────────────────────────────────────────
do_start() {
    print_header
    echo ""

    if pid=$(get_pid); then
        print_info "Server is already running (PID: $pid)"
        echo "  Use 'restart' to restart it."
        echo ""
        return 0
    fi

    # Check Python
    for candidate in python3 python3.12 python3.11 python3.10; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    done
    # Search common Android paths
    if [ -z "$PYTHON" ]; then
        for p in /data/data/com.termux/files/usr/bin/python3 \
                 /data/local/tmp/python3 /data/adb/python3; do
            if [ -x "$p" ]; then
                PYTHON="$p"
                break
            fi
        done
    fi

    if [ -z "$PYTHON" ]; then
        print_err "Python 3 not found!"
        echo "  Install via Termux: pkg install python"
        echo ""
        return 1
    fi

    print_info "Python: $PYTHON"
    print_info "Starting server..."

    # Kill any existing server first (avoid port conflicts / stale aliases)
    for oldpid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$oldpid" -eq "$$" ] && continue
        print_info "Killing existing server (PID $oldpid)..."
        kill "$oldpid" 2>/dev/null || true
    done
    sleep 1
    for oldpid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$oldpid" -eq "$$" ] && continue
        kill -9 "$oldpid" 2>/dev/null || true
    done

    # Detect hotspot
    HOTSPOT_IFACE=""
    HOTSPOT_IP=""

    # Scan all interfaces
    ip -f inet addr show 2>/dev/null | awk '
      /^[0-9]+:/ { iface=$2; gsub(/:/, "", iface) }
      /inet / {
        split($2, a, "/")
        if (a[1] != "127.0.0.1") print iface, a[1]
      }
    ' > /tmp/.ws_scan 2>/dev/null

    if [ -f /tmp/.ws_scan ]; then
        while read -r iface addr; do
            case "$addr" in 192.168.*)
                HOTSPOT_IFACE="$iface"; HOTSPOT_IP="$addr"; break ;;
            esac
        done < /tmp/.ws_scan
        rm -f /tmp/.ws_scan
    fi

    # Fallback interface list
    if [ -z "$HOTSPOT_IFACE" ]; then
        for iface in wlan0 ap0 wlan1 swlan0 rndis0 softap0 eth0; do
            addr=$(ip -f inet addr show "$iface" 2>/dev/null | grep "inet " | head -1 | awk '{print $2}' | cut -d/ -f1)
            if [ -n "$addr" ] && [ "$addr" != "127.0.0.1" ]; then
                HOTSPOT_IFACE="$iface"
                HOTSPOT_IP="$addr"
                break
            fi
        done
    fi

    BIND_IP="0.0.0.0"

    # Generate random auxiliary IP if hotspot found
    if [ -n "$HOTSPOT_IP" ]; then
        SUBNET_PREFIX=$(echo "$HOTSPOT_IP" | sed 's/\.[0-9]*$//')
        my_last=$(echo "$HOTSPOT_IP" | sed 's/.*\.//')
        while true; do
            # Pick host number in upper range (200-250) to avoid DHCP pool collision
            rand=$(( (RANDOM % 51) + 200 ))
            [ "$rand" -ne "$my_last" ] && break
        done
        BIND_IP="${SUBNET_PREFIX}.${rand}"

        # Bind the alias
        ip addr del "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true
        ip addr add "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || BIND_IP="$HOTSPOT_IP"

        # iptables rules
        iptables -I INPUT -i "$HOTSPOT_IFACE" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
        if [ "$BIND_IP" != "$HOTSPOT_IP" ]; then
            iptables -t nat -I PREROUTING -i "$HOTSPOT_IFACE" -d "$BIND_IP" -p tcp --dport 80 \
                -j REDIRECT --to-port "$PORT" 2>/dev/null || true
        fi

        # Save state for cleanup
        cat > "$STATE_FILE" <<EOF
HOTSPOT_IFACE=$HOTSPOT_IFACE
BIND_IP=$BIND_IP
HOTSPOT_IP=$HOTSPOT_IP
PORT=$PORT
ALIAS_LABEL=webserver
EOF
    fi

    # Ensure log directory exists
    mkdir -p "${MODPATH}/logs" 2>/dev/null
    mkdir -p /data/local/webserver 2>/dev/null

    # Read log level from config (default info)
    LOG_LVL="info"
    CONFIG_FILE="${MODPATH}/logs/.config"
    if [ -f "$CONFIG_FILE" ]; then
        LOG_LVL=$(cat "$CONFIG_FILE" 2>/dev/null | head -1 | tr -d '\n\r ')
        [ -z "$LOG_LVL" ] && LOG_LVL="info"
        case "$LOG_LVL" in
            off|error|info|debug) ;;  # valid
            *) LOG_LVL="info" ;;       # default for invalid values
        esac
    fi

    # Launch server in background with log level
    cd "$MODPATH"
    LOG_FILE="${MODPATH}/logs/server.log"
    [ "$LOG_LVL" = "off" ] && LOG_FILE="/dev/null"
    LOG_LEVEL="$LOG_LVL" BIND_IP="$BIND_IP" "$PYTHON" -u "$SERVER_PY" > "$LOG_FILE" 2>&1 </dev/null &
    pid=$!
    echo "$pid" > "$PID_FILE"

    sleep 2

    if kill -0 "$pid" 2>/dev/null; then
        print_ok "Server started (PID: $pid)"
        if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
            echo ""
            echo "  Connect to:"
            echo "    http://${BIND_IP}:${PORT}"
            echo "    http://${BIND_IP}  (port 80 → $PORT)"
        elif [ -n "$HOTSPOT_IP" ]; then
            echo ""
            echo "  Connect to:"
            echo "    http://${HOTSPOT_IP}:${PORT}"
        else
            echo ""
            echo "  Turn on hotspot and check:"
            echo "    http://<phone-ip>:${PORT}"
        fi
        echo ""
        echo "  Log level: $LOG_LVL"
        echo "  Log file:  ${MODPATH}/logs/server.log"
        [ "$LOG_LVL" = "off" ] && echo "  Logging is disabled."
    else
        print_err "Server failed to start. Check log:"
        echo "  cat ${MODPATH}/logs/server.log"
    fi
    echo ""
}

# ── Stop ────────────────────────────────────────────────────
do_stop() {
    print_header
    echo ""

    stopped=0
    # Kill by name (exclude current shell to avoid self-matching)
    for pid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$pid" -eq "$$" ] && continue
        print_info "Killing PID $pid..."
        kill "$pid" 2>/dev/null || true
        stopped=1
    done
    sleep 1

    # Force kill lingering
    for pid in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$pid" -eq "$$" ] && continue
        kill -9 "$pid" 2>/dev/null || true
    done

    # Remove alias IP
    if [ -f "$STATE_FILE" ]; then
        . "$STATE_FILE"
        if [ -n "$BIND_IP" ] && [ -n "$HOTSPOT_IFACE" ] && \
           [ "$BIND_IP" != "$HOTSPOT_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
            ip addr del "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true
        fi
        # Clean iptables
        if [ -n "$HOTSPOT_IFACE" ]; then
            iptables -D INPUT -i "$HOTSPOT_IFACE" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
            if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
                iptables -t nat -D PREROUTING -i "$HOTSPOT_IFACE" -d "$BIND_IP" -p tcp --dport 80 \
                    -j REDIRECT --to-port "$PORT" 2>/dev/null || true
            fi
        fi
    fi

    rm -f "$PID_FILE" "$STATE_FILE"

    # Verify no real server remains (exclude current shell to avoid self-matching)
    has_server=0
    for p in $(pgrep -f "python.*server\.py" 2>/dev/null); do
        [ "$p" -eq "$$" ] && continue
        has_server=1
        break
    done
    if [ "$stopped" -eq 1 ] || [ "$has_server" -eq 0 ]; then
        print_ok "Server stopped"
    else
        print_info "Server was not running"
    fi
    echo ""
}

# ── Restart ─────────────────────────────────────────────────
do_restart() {
    do_stop
    sleep 1
    do_start
}

# ── Log ─────────────────────────────────────────────────────
do_log() {
    print_header
    echo ""
    LOGFILE="${MODPATH}/logs/server.log"
    [ -f /data/local/webserver/server.log ] && LOGFILE=/data/local/webserver/server.log
    if [ -f "$LOGFILE" ]; then
        tail -n "${1:-50}" "$LOGFILE"
    else
        print_info "No log file found. Logs are written to: ${MODPATH}/logs/server.log"
    fi
    echo ""
}

# ── Dispatch ────────────────────────────────────────────────
if [ ! -t 0 ]; then
    # Non-interactive mode: capture output
    exec 2>&1
fi

case "${1:-status}" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_restart
        ;;
    status)
        do_status
        ;;
    log)
        do_log "${2:-50}"
        ;;
    *)
        echo "Usage: action.sh {start|stop|restart|status|log [lines]}"
        echo ""
        do_status
        ;;
esac
