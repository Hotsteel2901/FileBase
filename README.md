# FileBase — Android File Server

A Wi-Fi hotspot file server that turns an Android phone into a full-featured web file manager. Browse, upload, download, edit, rename, and delete files on `/sdcard` from any device connected to the phone's hotspot — no client-side install needed.

[中文文档 (Chinese)](README_CN.md)

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Browse** | Directory listing with sortable columns (name, size, date), breadcrumb navigation, live search filter |
| **Upload** | Button upload (multiple files), drag-and-drop with progress bar, binary-safe multipart parser |
| **Download** | Single-click download with correct MIME type, RFC 5987 UTF-8 filename encoding, header escaping |
| **Edit** | Full-screen monospace code editor for text files, auto-save back to server (binary files are protected from accidental edit) |
| **Manage** | Create files/folders, rename, delete (with styled confirmation dialog) |
| **i18n** | English / 中文 switch with localStorage persistence; unique user ID; new users default English |
| **Theme** | Dark / Light mode, auto-follows system `prefers-color-scheme`, manual toggle with localStorage memory |
| **Responsive** | Desktop table layout → mobile card layout at 700px breakpoint |
| **Security** | Path traversal protection, POST size limits (100 MB upload/write, 64 KB metadata), data-attribute event delegation (no inline onclick for file actions), CSRF origin check on POSTs |

## Distribution

| File | Purpose |
|------|---------|
| `dist/webserver.tar.gz` | Standalone: `server.py` + `launch.sh` + `stop.sh` + READMEs |
| `dist/filebase-v2.0.2.zip` | Magisk / KernelSU / APatch flashable module (includes WebUI panel + log management) |

## Requirements

### Server (Android phone)

- **Root access** (`su`) — required for iptables + auxiliary IP; optional if running directly
- **Python 3.8+** — install via Termux (`pkg install python`) or a Magisk-bundled binary
- **Mobile hotspot** turned on (for hotspot mode; Wi‑Fi LAN also works)

### Client (connecting device)

- Any web browser — phone, tablet, laptop — connected to the phone's hotspot / Wi‑Fi

---

## Quick Start (standalone)

### 1. Push files

```bash
adb push server.py launch.sh stop.sh /data/local/tmp/
adb shell chmod +x /data/local/tmp/launch.sh /data/local/tmp/stop.sh
```

### 2. Turn on hotspot

Settings → Hotspot & tethering → Wi‑Fi hotspot.

### 3. Launch

```bash
su
sh /data/local/tmp/launch.sh
```

The launcher auto‑detects the hotspot interface, picks a random auxiliary IP (e.g. `192.168.43.172`), sets up iptables, and starts the server:

```
╔══════════════════════════════════════════════════════════╗
║  Server running! Connect to:                            ║
║  http://192.168.43.172:6532                             ║
║  http://192.168.43.172  (port 80 → 6532)               ║
║  Serving: /sdcard                                       ║
║  Log level: info    Log file: logs/server.log           ║
╚══════════════════════════════════════════════════════════╝
```

### 4. Stop

```bash
sh /data/local/tmp/stop.sh
```

### Without root

```bash
python3 /data/local/tmp/server.py
# Access at http://<phone-ip>:6532
```

---

## Magisk / KernelSU / APatch Module

The module provides a **persistent system-level install** with auto‑start on boot, one‑tap control via your root manager's Action button, and an optional graphical WebUI panel.

### Install

1. Download `dist/filebase-v2.0.2.zip`
2. Root manager → Modules → Install from storage → select the zip
3. No reboot required — use the **Action** button immediately

**Supported managers:** Magisk 28.0+, KernelSU 1.0.2+, APatch (latest)

### Usage

| Interface | How |
|-----------|-----|
| **Action button** | Tap "Action" in the root manager module list → runs `action.sh` with `start`/`stop`/`restart`/`status`/`log` |
| **WebUI panel** | Requires [KSUWebUIStandalone](https://github.com/5ec1cff/KsuWebUIStandalone) or [MMRL](https://github.com/MMRLApp/MMRL) — graphical buttons + live status + log level selector |
| **Terminal** | `su -c 'sh /data/adb/modules/filebase/action.sh start'` |

### action.sh commands

```
sh action.sh start          Start server (auto-detect hotspot, random IP, iptables)
sh action.sh stop           Stop server + clean up alias IP + iptables
sh action.sh restart        Stop then start
sh action.sh status         Show PID, bind IP, interface, log level, connectivity
sh action.sh log [N]        Show last N log lines (default 50)
```

### WebUI features

- **Start / Stop / Restart** buttons with timeout‑safe execution
- **Live status**: PID, bind IP, interface, log level
- **Log level selector**: `Info` · `Error` · `Debug` · `Off` — saved to `logs/.config`
- **i18n**: English / 中文 toggle, remembered via localStorage

### Log levels

| Level | Behavior |
|-------|----------|
| `info` (default) | Client IP + HTTP method + status code |
| `error` | Only 4xx / 5xx responses |
| `debug` | Timestamp, IP:port, method, full path |
| `off` | No log file (stdout → /dev/null) |

Logs are written to `<module>/logs/server.log`. Configured via the WebUI dropdown or by writing to `logs/.config`.

---

## API Reference

All endpoints prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/list?path=<path>` | List directory contents |
| `GET` | `/api/download?path=<path>` | Download a file (RFC 5987 UTF-8 filename) |
| `POST` | `/api/upload` | Upload file(s) — `multipart/form-data` |
| `POST` | `/api/write` | Create / overwrite a file — JSON `{path, content}` |
| `POST` | `/api/delete` | Delete a file or directory — JSON `{path}` |
| `POST` | `/api/mkdir` | Create a directory — JSON `{path}` |
| `POST` | `/api/rename` | Rename / move — JSON `{oldPath, newPath}` |
| `POST` | `/api/login` | Admin login — JSON `{user, pass}` → `{ok, token}` |
| `POST` | `/api/logout` | Admin logout — invalidates token |
| `GET` | `/api/auth` | Check admin auth status → `{admin: bool}` |

### Response format

**Success** (`/api/list`):
```json
{ "entries": [{ "name": "foo.txt", "isdir": false, "size": 1234, "mtime": 1700000000, "editable": true }] }
```

**Success** (other POST):
```json
{ "ok": true }
```

**Error**:
```json
{ "error": "description" }
```

---

## Project Structure

```
server.py                     HTTP server + embedded SPA frontend
launch.sh                     Root launcher (interface scan, iptables, random IP)
stop.sh                       Graceful shutdown (alias removal, iptables cleanup)

README.md / README_CN.md      Documentation (EN / ZH)

magisk_module/                Magisk/KSU/APatch module source
├── module.prop               Multi-root metadata (ksu=1, sufs=1)
├── customize.sh              Install script
├── action.sh                 Control entry-point (start/stop/status/log)
├── service.sh                Boot auto-start
├── uninstall.sh              Cleanup
├── common/                   Server files → copied to module root on install
│   ├── server.py
│   ├── launch.sh
│   └── stop.sh
├── webroot/
│   └── index.html            WebUI control panel
├── META-INF/                 Recovery flash support
├── build.sh                  Rebuild the flashable zip
└── filebase-v2.0.2.zip       Pre-built module

dist/                         Distribution archives
├── webserver.tar.gz          Standalone package
└── filebase-v2.0.2.zip       Flashable module
```

### Frontend design

- **Typography**: Bebas Neue (brand), Figtree (UI body), JetBrains Mono (code / data)
- **Theme**: CSS custom properties with `[data-theme="dark"]` / `[data-theme="light"]`
- **i18n**: Template-driven via `data-i18n` attributes, `localStorage` persistence
- **Security**: File actions use `data-*` attributes + event delegation; no inline `onclick`
- **Upload**: Visually‑hidden native file input (opacity:0) for cross‑browser compatibility

---

## Super Admin

FileBase includes a hidden super admin mode for full root-level file management.

### How to access

1. An **Admin** button is visible in the top-right control bar of the web UI
2. Click it to open the login dialog
3. The Admin button remains visible at all times

### Credentials

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `hotsteel` |

### What admin mode changes

- **File system root** shifts from `/sdcard` to `/` — the entire Android filesystem is accessible
- Navigate **up from `/sdcard`** to the root directory and browse `/data`, `/system`, `/proc`, etc.
- All operations (upload, delete, rename, edit) work on any path the server process can access
- The footer shows `Serving: /` instead of `Serving: /sdcard`
- A red **ADMIN** badge appears in the UI

### Security notes

- The login endpoint uses a fixed username/password — change `ADMIN_USER` and `ADMIN_PASS` in `server.py` for production use

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Python not found` | Install via Termux (`pkg install python3`) or push a binary |
| `No hotspot IP detected` | Ensure hotspot is **enabled before** launching; module scans all interfaces |
| Upload button doesn't open file picker | Fixed — file input uses opacity-based hiding, not `display:none` |
| Theme toggle not working | Fixed — SVG icon wrapper uses `<span>` for reliable `innerHTML` |
| Chinese filenames fail on download | Fixed — RFC 5987 `filename*=UTF-8''...` encoding |
| Module WebUI hangs on Start | Fixed — backgrounded command + 15s timeout |
| Can't access from client | Verify client is on phone's hotspot Wi‑Fi, not mobile data |
| `grep: Unknown option` | Fixed — uses `sed` fallback for Android busybox compatibility |

## License

MIT
