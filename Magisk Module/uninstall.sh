#!/system/bin/sh
# ──────────────────────────────────────────────────────────────
#  FileBase — Uninstall Cleanup
#  Stops the server and removes all traces
# ──────────────────────────────────────────────────────────────

echo "[*] FileBase: cleaning up..."

# Stop the server
if [ -f "/data/local/webserver/stop.sh" ]; then
    sh /data/local/webserver/stop.sh 2>/dev/null
fi

# Kill any lingering server
for pid in $(pgrep -f "python.*server.py" 2>/dev/null); do
    echo "[*] Killing PID $pid"
    kill "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null
done

# Remove state files
rm -f /data/local/webserver/.server_pid 2>/dev/null
rm -f /data/local/tmp/.webserver_state 2>/dev/null

# Remove runtime copy
rm -rf /data/local/webserver 2>/dev/null

# Clean up any remaining iptables rules
PORT=6532
for iface in wlan0 ap0 swlan0 eth0 rndis0 softap0; do
    iptables -D INPUT -i "$iface" -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    iptables -t nat -D PREROUTING -i "$iface" -p tcp --dport 80 -j REDIRECT --to-port "$PORT" 2>/dev/null || true
done

echo "[✓] FileBase uninstalled"
