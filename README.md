# FileBase — Android File Server

A Wi-Fi hotspot file server that turns an Android phone into a full-featured web file manager. Browse, upload, download, edit, rename, and delete files on `/sdcard` from any device connected to the phone's hotspot — no app installation needed on the client side.

[中文文档 (Chinese)](README_CN.md)

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Browse** | Directory listing with sortable columns (name, size, date), breadcrumb navigation, live search filter |
| **Upload** | Button upload (multiple files), drag-and-drop with progress bar, binary-safe |
| **Download** | Single-click download with correct MIME type, UTF-8 filename support |
| **Edit** | Full-screen code editor for text files, auto-save back to server |
| **Manage** | Create files/folders, rename, delete (with confirmation dialog) |
| **i18n** | English / Chinese switch with localStorage persistence; unique user ID; new users default English |
| **Theme** | Dark / Light mode, follows system `prefers-color-scheme`, manual toggle with localStorage memory |
| **Responsive** | Desktop table layout, mobile card layout at 700px breakpoint |
| **Security** | Path traversal protection, POST size limits (100 MB upload/write, 64 KB metadata), properly escaped headers |

## Requirements

### Server (Android phone)

- **Root access** (`su`) — for iptables port forwarding and binding an auxiliary IP
- **Python 3.8+** — can be installed via Termux, Magisk module, or manual binary push
- **Mobile hotspot** turned on

### Client (connecting device)

- Any device with a web browser (phone, tablet, laptop)
- Connected to the phone's Wi-Fi hotspot

## Quick Start

### 1. Push files to the phone

```bash
adb push server.py launch.sh stop.sh /data/local/tmp/
adb shell chmod +x /data/local/tmp/launch.sh /data/local/tmp/stop.sh
```

### 2. Turn on the hotspot

Enable the mobile hotspot on your Android phone (Settings → Hotspot & tethering → Wi-Fi hotspot).

### 3. Launch the server

On the phone (via adb shell or terminal emulator):

```bash
su
sh /data/local/tmp/launch.sh
```

The launcher will:
- Automatically detect the hotspot network interface and IP
- Pick a random auxiliary IP in the same subnet (e.g., `192.168.43.172`)
- Configure iptables to allow inbound connections
- Redirect port 80 → 6532 on the auxiliary IP
- Start the Python server

```
╔══════════════════════════════════════════════════════════╗
║  Server running! Connect to:                            ║
║  http://192.168.43.172:6532                             ║
║  http://192.168.43.172  (port 80 redirected)            ║
║  Serving: /sdcard                                       ║
╚══════════════════════════════════════════════════════════╝
```

### 4. Connect from another device

Open a browser on any device connected to the phone's hotspot and navigate to the URL shown in the output.

### 5. Stop the server

```bash
sh /data/local/tmp/stop.sh
```

This kills the server process, removes the auxiliary IP alias, and cleans up iptables rules.

## Without Root

If root is not available, you can still run the server directly — just without iptables and the random auxiliary IP:

```bash
python3 /data/local/tmp/server.py
```

The server will listen on all interfaces (`0.0.0.0:6532`). Connected devices can access it at the phone's hotspot IP (usually `192.168.43.1:6532`).

## API Reference

All API endpoints are prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/list?path=<path>` | List directory contents |
| `GET` | `/api/download?path=<path>` | Download a file |
| `POST` | `/api/upload` | Upload file(s) (multipart) |
| `POST` | `/api/write` | Create or overwrite a file (JSON) |
| `POST` | `/api/delete` | Delete a file or directory |
| `POST` | `/api/mkdir` | Create a directory |
| `POST` | `/api/rename` | Rename or move a file/directory |

### Response format

**Success** (`list`):
```json
{ "entries": [{ "name": "foo.txt", "isdir": false, "size": 1234, "mtime": 1700000000 }] }
```

**Success** (write/delete/mkdir/rename/upload):
```json
{ "ok": true }
```

**Error**:
```json
{ "error": "description" }
```

## Architecture

```
launch.sh                    stop.sh
───────────                  ─────────
│ Root check │               │ Kill PID │
│ Find Python│               │ Remove IP│
│ Detect IF │                │ Clean FW │
│ Random IP │                ────────────
│ iptables  │
│ Start srv │
└─────┬─────┘
      │
      ▼
  server.py
  ───────────
  Python HTTP Server (port 6532)
  │
  ├─ GET  /          → Embedded SPA frontend
  ├─ GET  /api/*     → File operations
  └─ POST /api/*     → Mutations
```

The entire frontend is embedded in `server.py` as a Python raw string — no external HTML/CSS/JS files. The SPA makes all API calls through a central `api()` helper and uses event delegation (data attributes) for DOM interactions.

### Frontend design

- **Typography**: Bebas Neue (brand), Figtree (body), JetBrains Mono (data/code)
- **Theme**: CSS custom properties with `[data-theme="dark"]` / `[data-theme="light"]`
- **i18n**: Template-based with `data-i18n` attributes, `localStorage` persistence
- **Security**: No inline `onclick` handlers on file actions — all interactions use `data-*` attributes + event delegation

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Python not found` | Install Python via Termux (`pkg install python3`) or push a binary |
| `No hotspot IP detected` | Ensure mobile hotspot is **enabled** before launching |
| `grep: Unknown option` | Fixed in current version (uses `sed` fallback) |
| `latin-1 encode error` on download | Fixed in current version (RFC 5987 `filename*=`) |
| Can't access from client | Verify client is on the phone's hotspot Wi-Fi, not mobile data |
| Port already in use | `launch.sh` auto-kills old processes on the same port |

## License

MIT
