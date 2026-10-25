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
STATUS_FILE="/data/local/webserver/status"
STATE_FILE="/data/local/tmp/.webserver_state"
PORT=6532
CONFIG_FILE="${MODPATH}/logs/.config"
ACTION_LOG="${MODPATH}/logs/action.log"
KSUD_BIN="/data/adb/ksud"

# ── Module config (KernelSU module guide: ksud module config) ───
# On KernelSU the value lives in the module config store
# (/data/adb/ksu/module_configs/<id>/, see module-config.md); on Magisk and
# APatch there is no ksud, so we fall back to a plain file.
resolve_ksud() {
    if [ -x "$KSUD_BIN" ]; then printf '%s' "$KSUD_BIN"; return 0; fi
    if command -v ksud >/dev/null 2>&1; then command -v ksud; return 0; fi
    if [ -x "/data/adb/ksu/bin/ksud" ]; then printf '%s' "/data/adb/ksu/bin/ksud"; return 0; fi
    return 1
}

valid_level() {
    case "$1" in off|error|info|debug) return 0 ;; *) return 1 ;; esac
}

get_log_level() {
    lvl=""
    if ksud=$(resolve_ksud); then
        lvl=$(KSU_MODULE="$MOD_ID" "$ksud" module config get log_level 2>/dev/null)
    fi
    if [ -z "$lvl" ] && [ -r "$CONFIG_FILE" ]; then
        read lvl < "$CONFIG_FILE" 2>/dev/null || true
    fi
    if ! valid_level "$lvl"; then lvl="info"; fi
    printf '%s' "$lvl"
}

set_log_level() {
    valid_level "$1" || return 1
    mkdir -p "${MODPATH}/logs" 2>/dev/null
    # Preferred store on KernelSU (guide), mirrored to a file so Magisk /
    # APatch and manual runs see the same value.
    if ksud=$(resolve_ksud); then
        KSU_MODULE="$MOD_ID" "$ksud" module config set log_level "$1" >/dev/null 2>&1
    fi
    printf '%s\n' "$1" > "$CONFIG_FILE" 2>/dev/null
    printf '%s' "$1"
}

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
# True when /proc/<pid> belongs to our server. Reading cmdline avoids matching
# unrelated python processes (and does not depend on pgrep).
# True only when /proc/<pid> is a python interpreter running THIS module's
# server.py. Matching on "server.py" alone is too loose: any shell whose
# command line merely mentions the path (or another module's server) would
# otherwise be treated as ours.
is_server_pid() {
    [ -n "$1" ] || return 1
    [ -r "/proc/$1/cmdline" ] || return 1
    cmd=$(tr '\000' ' ' < "/proc/$1/cmdline" 2>/dev/null)
    case "$cmd" in
        *"$SERVER_PY"*) ;;
        *) return 1 ;;
    esac
    case "$cmd" in
        *python*) return 0 ;;
    esac
    return 1
}

# Candidate PIDs: the server's own pid file, then pgrep (toybox / busybox),
# then a raw /proc scan when pgrep is unavailable.
pid_candidates() {
    if [ -r "$PID_FILE" ]; then
        p=""
        read p < "$PID_FILE" 2>/dev/null || true
        case "$p" in
            ''|*[!0-9]*) ;;
            *) printf '%s\n' "$p" ;;
        esac
    fi
    if command -v pgrep >/dev/null 2>&1; then
        pgrep -f "server\.py" 2>/dev/null
    else
        for d in /proc/[0-9]*; do
            printf '%s\n' "${d#/proc/}"
        done
    fi
}

# Every PID belonging to this module's server, de-duplicated.
list_server_pids() {
    seen=" "
    for p in $(pid_candidates); do
        [ "$p" = "$$" ] && continue
        is_server_pid "$p" || continue
        case "$seen" in
            *" $p "*) continue ;;
        esac
        seen="$seen$p "
        printf '%s\n' "$p"
    done
}

get_pid() {
    p=$(list_server_pids | head -n 1)
    [ -n "$p" ] || return 1
    printf '%s' "$p"
}

# ── Connectivity probe ──────────────────────────────────────
# curl is not guaranteed to exist on every ROM, and busybox/toybox nc has no
# -z flag on Android, so fall back to the heartbeat file the server refreshes
# every 10 s. Exit codes: 0 = responds, 1 = not responding, 2 = unverifiable.
server_responds() {
    addr="$1"
    # Prefer the heartbeat the server refreshes every 10 s: a cheap liveness
    # check that adds nothing to the server log.
    hb="/data/local/webserver/.heartbeat"
    if [ -r "$hb" ]; then
        now=$(date +%s 2>/dev/null)
        last=""
        # `read` is a shell builtin (no external tools) and drops the newline.
        read last < "$hb" 2>/dev/null || true
        case "$now" in ''|*[!0-9]*) now=0 ;; esac
        case "$last" in ''|*[!0-9]*) last=0 ;; esac
        if [ "$now" -gt 0 ] && [ "$last" -gt 0 ]; then
            if [ $((now - last)) -le 30 ]; then
                return 0
            fi
        fi
    fi
    if command -v curl >/dev/null 2>&1; then
        # /api/ping is not recorded in the log (see server.py).
        if curl -s --max-time 2 "http://${addr}:${PORT}/api/ping" >/dev/null 2>&1; then
            return 0
        fi
        return 1
    fi
    return 2
}

# ── Status ──────────────────────────────────────────────────
do_status() {
    print_header
    echo ""
    LOG_LVL=$(get_log_level)

    echo "  Root environment: $(detect_root)"
    echo "  Port: $PORT"
    echo "  Log level: $LOG_LVL (applies after a restart)"
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
        TEST_ADDR="${BIND_IP:-127.0.0.1}"
        [ "$TEST_ADDR" = "0.0.0.0" ] && TEST_ADDR="127.0.0.1"
        server_responds "$TEST_ADDR"
        case $? in
            0) print_ok "Server responds OK" ;;
            2) print_info "Server process is running (HTTP check skipped: no curl)" ;;
            *) print_err "Server does not respond (check firewall / iptables)" ;;
        esac
    else
        print_err "Server STOPPED"
    fi
    echo ""
}

# ── Start ───────────────────────────────────────────────────
do_start() {
    print_header
    echo ""

    # Runtime directories must exist before anything writes into them.
    mkdir -p "${MODPATH}/logs" 2>/dev/null
    mkdir -p /data/local/webserver 2>/dev/null
    mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null

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
    for oldpid in $(list_server_pids); do
        print_info "Killing existing server (PID $oldpid)..."
        kill "$oldpid" 2>/dev/null || true
    done
    sleep 1
    for oldpid in $(list_server_pids); do
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

    LOG_LVL=$(get_log_level)

    cd "$MODPATH"
    LOG_FILE="${MODPATH}/logs/server.log"
    if [ "$LOG_LVL" = "off" ]; then
        LOG_FILE="/dev/null"
        # Don't leave a stale log behind that looks like current output.
        : > "${MODPATH}/logs/server.log" 2>/dev/null
    fi

    # The server MUST be fully detached from this shell. When action.sh is run
    # from the WebUI, KernelSU executes it in a temporary root shell that is
    # destroyed as soon as the command returns (withNewRootShell { ... });
    # a plain `cmd &` would be killed together with that shell, leaving no
    # running server and no log. setsid gives the server its own session.
    if command -v setsid >/dev/null 2>&1; then
        LAUNCHER="setsid"
    elif [ -x /system/bin/setsid ]; then
        LAUNCHER="/system/bin/setsid"
    elif command -v busybox >/dev/null 2>&1; then
        LAUNCHER="busybox setsid"
    else
        LAUNCHER="nohup"
    fi

    # Drop stale runtime facts so we can tell when the new process is up.
    : > "$STATUS_FILE" 2>/dev/null
    : > "$PID_FILE" 2>/dev/null

    # shellcheck disable=SC2086  # LAUNCHER may be "busybox setsid"
    LOG_LEVEL="$LOG_LVL" BIND_IP="$BIND_IP" $LAUNCHER "$PYTHON" -u "$SERVER_PY" \
        > "$LOG_FILE" 2>&1 </dev/null &
    echo "$!" > "$PID_FILE" 2>/dev/null

    # Wait for the server to actually bind (it rewrites the pid + status files).
    i=0
    pid=""
    while [ $i -lt 6 ]; do
        sleep 1
        if pid=$(get_pid); then break; fi
        pid=""
        i=$((i + 1))
    done

    # Prefer the address the server itself reports (covers BIND_IP=0.0.0.0 and
    # an unbound alias), falling back to what the launcher computed.
    SRV_IP=""
    [ -r "$STATUS_FILE" ] && SRV_IP=$(sed -n 's/^IP=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
    SHOW_IP="$BIND_IP"
    case "$SHOW_IP" in ""|"0.0.0.0") SHOW_IP="$SRV_IP" ;; esac
    [ -z "$SHOW_IP" ] && SHOW_IP="$HOTSPOT_IP"

    if [ -n "$pid" ]; then
        print_ok "Server started (PID: $pid)"
        echo ""
        if [ -n "$SHOW_IP" ]; then
            echo "  Connect to:"
            echo "    http://${SHOW_IP}:${PORT}"
            echo "    http://${SHOW_IP}  (port 80 → $PORT)"
        else
            echo "  Connect to:  http://<phone-ip>:${PORT}"
            echo "  (turn on the hotspot, then check 'status')"
        fi
        echo "  Log level:   $LOG_LVL"
        echo "  Log file:    ${MODPATH}/logs/server.log"
        [ "$LOG_LVL" = "off" ] && echo "  Logging is disabled (log level: off)."
    else
        print_err "Server failed to start."
        echo "  Last lines of the log:"
        tail -n 15 "$LOG_FILE" 2>/dev/null | sed 's/^/    /'
        [ "$LOG_LVL" = "off" ] && echo "  (log level is 'off'; set it to info/debug to see why)"
        echo "  Try: sh ${MODPATH}/action.sh log"
    fi
    echo ""
}

# ── Stop ────────────────────────────────────────────────────
do_stop() {
    print_header
    echo ""

    stopped=0
    # Kill this module's server (strict match, see is_server_pid)
    for pid in $(list_server_pids); do
        print_info "Killing PID $pid..."
        kill "$pid" 2>/dev/null || true
        stopped=1
    done
    sleep 1

    # Force kill lingering
    for pid in $(list_server_pids); do
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
    rm -f "$STATUS_FILE"

    # Verify no real server remains (exclude current shell to avoid self-matching)
    has_server=0
    for p in $(list_server_pids); do
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
    if [ -f "$LOGFILE" ]; then
        tail -n "${1:-50}" "$LOGFILE"
    else
        print_info "No log file found. Logs are written to: ${MODPATH}/logs/server.log"
    fi
    echo ""
}

# ── Machine-readable info ───────────────────────────────────
# Emits stable KEY=VALUE lines for the WebUI. Keep this contract stable:
# the WebUI parses it instead of scraping the human-readable status output.
do_info() {
    HOTSPOT_IFACE=""
    BIND_IP=""
    HOTSPOT_IP=""
    [ -f "$STATE_FILE" ] && . "$STATE_FILE"

    # Facts reported by the running server itself. These are authoritative for
    # the bind address because the server may end up listening on all
    # interfaces (0.0.0.0) while only it knows the hotspot IP.
    srv_ip=""
    srv_host=""
    srv_iface=""
    srv_port=""
    srv_started=""
    if [ -r "$STATUS_FILE" ]; then
        srv_host=$(sed -n 's/^HOST=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
        srv_ip=$(sed -n 's/^IP=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
        srv_iface=$(sed -n 's/^IFACE=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
        srv_port=$(sed -n 's/^PORT=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
        srv_started=$(sed -n 's/^STARTED=//p' "$STATUS_FILE" 2>/dev/null | head -n 1)
    fi

    echo "MODULE_ID=$MOD_ID"
    echo "MODULE_DIR=$MODPATH"
    echo "PORT=${srv_port:-${PORT:-6532}}"
    echo "STARTED=${srv_started:-}"
    echo "LOG_LEVEL=$(get_log_level)"

    if pid=$(get_pid); then
        echo "RUNNING=1"
        echo "PID=$pid"
    else
        echo "RUNNING=0"
        echo "PID="
    fi

    echo "IFACE=${HOTSPOT_IFACE:-${srv_iface:-}}"
    echo "BIND_IP=${BIND_IP:-}"
    echo "HOTSPOT_IP=${HOTSPOT_IP:-}"

    # ADDR is what a client should actually open in a browser. Prefer, in order:
    # the launcher's alias IP, the address the server really bound to, and
    # finally the hotspot IP the server detected while listening on 0.0.0.0.
    addr_out=""
    case "$BIND_IP" in
        ""|"0.0.0.0") ;;
        *) addr_out="$BIND_IP" ;;
    esac
    if [ -z "$addr_out" ]; then
        case "$srv_host" in
            ""|"0.0.0.0") addr_out="$srv_ip" ;;
            *) addr_out="$srv_host" ;;
        esac
    fi
    [ -z "$addr_out" ] && addr_out="$HOTSPOT_IP"
    echo "ADDR=$addr_out"

    addr="${addr_out:-127.0.0.1}"
    server_responds "$addr"
    echo "RESPONDS=$?"
}

# ── Log level ───────────────────────────────────────────────
# `loglevel`        -> print the current level
# `loglevel <level>`-> persist a new level (ksud module config, file fallback)
do_loglevel() {
    if [ -n "$1" ]; then
        if set_log_level "$1" >/dev/null; then
            printf '%s\n' "$1"
        else
            print_err "invalid level: $1 (use off|error|info|debug)"
            return 1
        fi
    else
        get_log_level
        echo ""
    fi
}

# ── Toggle — the manager's Action button ────────────────────
# KernelSU runs `ksud module action <id>` with NO arguments, so the Action
# button has to do something useful by itself: start when stopped, stop when
# running. (The previous default was `status`, which is why the button only
# ever reported "Server STOPPED".)
do_toggle() {
    if get_pid >/dev/null 2>&1; then
        do_stop
    else
        do_start
    fi
}

# ── Command table ───────────────────────────────────────────
run_command() {
    cmd="$1"
    # No argument (the manager's Action button) means "toggle".
    [ -z "$cmd" ] && cmd="toggle"
    case "$cmd" in
        start)    do_start ;;
        stop)     do_stop ;;
        restart)  do_restart ;;
        toggle)   do_toggle ;;
        status)   do_status ;;
        info)     do_info ;;
        log)      do_log "${2:-50}" ;;
        loglevel) do_loglevel "$2" ;;
        *)
            echo "Usage: action.sh {start|stop|restart|toggle|status|info|log [lines]|loglevel [level]}"
            echo ""
            do_status
            ;;
    esac
}

# ── Dispatch ────────────────────────────────────────────────
if [ ! -t 0 ]; then
    # Non-interactive mode: capture output
    exec 2>&1
fi

mkdir -p "${MODPATH}/logs" 2>/dev/null

CMD="$1"
[ -z "$CMD" ] && CMD="toggle"

if [ "$CMD" = "info" ]; then
    # Pure machine-readable output: no persistence, no decoration.
    run_command "$CMD" "$2"
    exit $?
fi

# Human-facing commands additionally persist their complete output to
# logs/action.log. The manager's exec() captures stdout, but that capture can
# come back empty or truncated when the command backgrounds a process; the file
# on disk is the reliable copy and the WebUI reads it back.
TMP_OUT="${MODPATH}/logs/.action.tmp"
run_command "$CMD" "$2" > "$TMP_OUT" 2>&1
rc=$?
cat "$TMP_OUT" 2>/dev/null
if [ -s "$TMP_OUT" ]; then
    cp -f "$TMP_OUT" "$ACTION_LOG" 2>/dev/null || cat "$TMP_OUT" > "$ACTION_LOG" 2>/dev/null
fi
rm -f "$TMP_OUT" 2>/dev/null
exit $rc
