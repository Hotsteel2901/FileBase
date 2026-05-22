#!/system/bin/sh
# Stop the Android file server, remove alias IP, and clean up iptables

PORT=6532
STATE_FILE="/data/local/tmp/.webserver_state"

echo "[*] Stopping Android File Server..."

# Load state if available
if [ -f "$STATE_FILE" ]; then
    . "$STATE_FILE"
    echo "[*] State loaded: iface=$HOTSPOT_IFACE bind_ip=$BIND_IP"
fi

# Kill the server process
pids=$(pgrep -f "python.*server.py" 2>/dev/null || true)
if [ -n "$pids" ]; then
    for pid in $pids; do
        echo "[*] Killing PID $pid"
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
    pids=$(pgrep -f "python.*server.py" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
    echo "[✓] Server stopped"
else
    echo "[?] No server process found"
fi

# Remove alias IP
if [ -n "$BIND_IP" ] && [ -n "$HOTSPOT_IFACE" ] && \
   [ "$BIND_IP" != "$HOTSPOT_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
    echo "[*] Removing alias $BIND_IP from $HOTSPOT_IFACE"
    ip addr del "${BIND_IP}/24" dev "$HOTSPOT_IFACE" 2>/dev/null || true
    echo "[✓] Alias removed"
fi

# Clean up iptables rules (best effort)
for iface in wlan0 ap0 wlan1 swlan0 rndis0 softap0 eth0; do
    iptables -D INPUT -i "$iface" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    if [ -n "$BIND_IP" ] && [ "$BIND_IP" != "$HOTSPOT_IP" ] && [ "$BIND_IP" != "0.0.0.0" ]; then
        iptables -t nat -D PREROUTING -i "$iface" -d "$BIND_IP" -p tcp --dport 80 \
            -j REDIRECT --to-port "$PORT" 2>/dev/null || true
    fi
done
echo "[✓] iptables rules cleaned up"

rm -f "$STATE_FILE"
