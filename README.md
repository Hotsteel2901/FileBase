# FileBase — Android File Server

A Wi-Fi hotspot file server that turns an Android phone into a full-featured web file manager. Browse, upload, download, edit, rename, and delete files on `/sdcard` from any device connected to the phone's hotspot — no client-side install needed.

[中文文档 (Chinese)](README_CN.md)

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Browse** | Directory listing with sortable columns (name, size, date), breadcrumb navigation, live search filter |
| **Upload** | Button upload (multiple files), drag-and-drop with progress bar, binary-safe multipart parser |
| **Download** | Single-click download with correct MIME type, RFC 5987 UTF-8 filename encoding, HTTP Range support (resume / video seeking) |
| **Edit** | Full-screen monospace code editor for text files, auto-save back to server (binary files are protected from accidental edit) |
| **Manage** | Create files/folders, rename, delete (with styled confirmation dialog) |
| **i18n** | English / 中文 switch with localStorage persistence; unique user ID; first visit follows the browser language (falls back to English) |
| **Theme** | Dark / Light mode, auto-follows system `prefers-color-scheme`, manual toggle with localStorage memory |
| **Responsive** | Desktop table layout → mobile card layout at 700px breakpoint |
| **Security** | Path traversal protection, POST size limits (100 MB upload/write, 64 KB metadata), data-attribute event delegation (no inline onclick for file actions), CSRF origin check on POSTs |
| **Concurrency** | Threaded request handling, so a large upload or download no longer blocks other clients |

## Distribution

| File | Purpose |
|------|---------|
| `dist/webserver.tar.gz` | Standalone: `server.py` + `launch.sh` + `stop.sh` + READMEs |
| `dist/filebase-v5.0.0.zip` | Magisk / KernelSU / APatch flashable module (includes WebUI panel + log management) |

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

The module provides a **persistent system-level install** with one‑tap control via your root manager's Action button and an optional graphical WebUI panel. **The server does not start on boot** — you start and stop it explicitly (Action button, WebUI, or the CLI). This avoids the classic "hotspot is not up yet at boot, so the random-IP setup fails" problem.

### Install

1. Download `dist/filebase-v5.0.0.zip`
2. Root manager → Modules → Install from storage → select the zip
3. **Reboot once.** KernelSU/Magisk stage new modules in `modules_update/` and merge them in on the next boot, so `action.sh` and `webroot/` only exist after a reboot — the WebUI is refused and the Action button fails until then.
4. After rebooting, use the **Action** button or open the WebUI

**Supported managers:** Magisk 28.0+, KernelSU 1.0.2+, APatch (latest)

### Usage

| Interface | How |
|-----------|-----|
| **Action button** | Tap "Action" in the root manager module list → starts the server, or stops it if it is already running (`action.sh toggle`; `start`/`stop`/`restart`/`status`/`log` also work) |
| **WebUI panel** | Open it from the KernelSU Manager module page (the manager renders `webroot/` in a WebView). On Magisk / APatch use [KSUWebUIStandalone](https://github.com/5ec1cff/KsuWebUIStandalone) or [MMRL](https://github.com/MMRLApp/MMRL) |
| **Terminal** | `su -c 'sh /data/adb/modules/filebase/action.sh start'` |

### action.sh commands

```
sh action.sh start          Start server (auto-detect hotspot, random IP, iptables)
sh action.sh stop           Stop server + clean up alias IP + iptables
sh action.sh restart        Stop then start
sh action.sh toggle         Start if stopped, stop if running
sh action.sh status         Show PID, bind IP, interface, log level, connectivity
sh action.sh info           Machine-readable KEY=VALUE status (used by the WebUI)
sh action.sh log [N]        Show last N log lines (default 50)
sh action.sh loglevel [LVL] Read (no arg) or set the log level
```

KernelSU runs the Action button as `ksud module action <id>` **without any
arguments**, so the no-argument default is `toggle`: tapping Action starts the
server when it is stopped and stops it when it is running. (It used to default
to `status`, which is why the button only ever printed "Server STOPPED".)

### WebUI features

The panel is written the way KernelSU's [module WebUI guide](https://kernelsu.org/guide/module-webui.html) describes:

- **Entry point** is `webroot/index.html`; CSS/JS live next to it. Permissions and
  SELinux context are left to KernelSU, as the guide requires.
- **Shell access uses the official `kernelsu` library** —
  `const { errno, stdout, stderr } = await exec(cmd)`. The library is vendored
  verbatim as `webroot/kernelsu.js` (Apache‑2.0) so the page can `import` it
  without a bundler. The old synchronous `ksu.exec(cmd)` string API is *not*
  the documented interface and broke under other WebUI hosts.
- **Module directory comes from `moduleInfo()`** instead of a hard‑coded path.
- **Native toasts** via the library's `toast()`.
- **Start / Stop / Restart** buttons with a timeout guard.
- **Live status** (PID, address, interface, log level) parsed from
  `action.sh info`, a stable `KEY=VALUE` contract — not scraped from
  human‑readable output.
- **Log level selector**: `Info` · `Error` · `Debug` · `Off`.
- **i18n**: English / 中文, first visit follows the browser language.
- **Console shows the complete output.** KernelSU runs `exec()` in a temporary
  root shell that is destroyed when the command returns, so a command's stdout
  can come back empty or truncated (and a naive `cmd &` server is killed with
  it). FileBase therefore starts the server with `setsid` and has `action.sh`
  persist its full output to `logs/action.log`; the WebUI reads that file back.
  After a start/restart it also appends `logs/server.log`, which holds the bind
  address and any Python traceback.
- **The address is always discoverable.** The server writes
  `PID/HOST/PORT/IFACE/IP` to a runtime status file, so the panel can show the
  URL even when the server listens on `0.0.0.0` or the log level is `off`.

### Where the log level is stored

Following the [module config guide](https://kernelsu.org/guide/module-config.html),
the value is persisted with KernelSU's module config system:

```sh
ksud module config set log_level debug     # KSU_MODULE is set by action.sh
```

On Magisk / APatch (no `ksud`) it falls back to `logs/.config`. `action.sh`
reads the ksud config first, then the file, and both are written whenever the
level changes — so the setting survives manager uninstalls on KernelSU and
still works everywhere else.

### Log levels

| Level | Behavior |
|-------|----------|
| `info` (default) | Client IP + HTTP method + status code |
| `error` | Only 4xx / 5xx responses |
| `debug` | Timestamp, IP:port, method, full path |
| `off` | No log file (stdout → /dev/null) |

Logs are written to `<module>/logs/server.log`. Set the level with the WebUI dropdown, `sh action.sh loglevel <level>`, or `ksud module config set log_level <level>` (see above). A new level takes effect the next time the server starts — use **Restart** in the WebUI to apply it immediately.

### Build the flashable zip yourself

```bash
sh "Magisk Module/build.sh"
```

The script syncs `server.py` / `launch.sh` / `stop.sh` from the repo root into
`Magisk Module/common/`, then writes `dist/filebase-<version>.zip` plus a fresh
`dist/webserver.tar.gz`. The release workflow uses the same script, so a
release can never bundle a stale copy of the server.

---

## API Reference

All endpoints prefixed with `/api`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/list?path=<path>` | List directory contents |
| `GET` | `/api/download?path=<path>` | Download a file (RFC 5987 filename, HTTP `Range` supported) |
| `POST` | `/api/upload` | Upload file(s) — `multipart/form-data` |
| `POST` | `/api/write` | Create / overwrite a file — JSON `{path, content, overwrite?}` (`overwrite:false` returns 409 if the path exists) |
| `POST` | `/api/delete` | Delete a file or directory — JSON `{path}` |
| `POST` | `/api/mkdir` | Create a directory — JSON `{path}` |
| `POST` | `/api/rename` | Rename / move — JSON `{oldPath, newPath}` |
| `POST` | `/api/login` | Admin login — JSON `{user, pass}` → `{ok, token}` |
| `POST` | `/api/logout` | Admin logout — invalidates token |
| `GET` | `/api/auth` | Check admin auth status → `{admin: bool}` |

Downloads honour a single-range `Range: bytes=...` request (206 partial
content, 416 when unsatisfiable) so large files can be resumed. Admin sessions
normally authenticate with a `Bearer` header; native browser downloads may
instead append `&token=<token>` to the URL because `<a download>` cannot send
headers.

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
├── uninstall.sh              Cleanup
├── common/                   Server files → copied to module root on install
│   ├── server.py
│   ├── launch.sh
│   └── stop.sh
├── webroot/
│   ├── index.html            WebUI entry point (required by the KSU guide)
│   ├── script.js             WebUI logic (ES module, imports kernelsu.js)
│   ├── kernelsu.js           Official KernelSU WebUI library (vendored)
│   └── style.css             WebUI styles
├── META-INF/                 Recovery flash support
└── build.sh                  Rebuild the flashable zip + standalone tarball

dist/                         Distribution archives
├── webserver.tar.gz          Standalone package
└── filebase-v5.0.0.zip       Flashable module
```

### Frontend design

- **Typography**: system font stack, no external webfont requests (Bebas Neue / Figtree / JetBrains Mono are used only when installed locally, so the UI works fully offline)
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
| `error` log level shows nothing | Fixed — the 4xx/5xx filter now parses the status code correctly |
| Admin download of `/data` files fails | Fixed — admin downloads carry the token, and large files stream instead of buffering |
| One big download freezes the whole page | Fixed — the server is now threaded |
| Cannot resume a large download | Fixed — HTTP Range requests are supported |
| WebUI shows "API unavailable" | The page was opened outside a WebUI host — open it from the KernelSU Manager (or KSUWebUIStandalone / MMRL); the terminal fallback is shown on the page |
| WebUI controls do nothing | The panel needs the `kernelsu` WebUI bridge; check that the module is enabled and rebooted after install |
| Action button / WebUI fails right after installing | Reboot once first. New modules are staged in `modules_update/` and merged in at boot, so `action.sh` and `webroot/` do not exist until then |
| Do I need a metamodule? | No. FileBase never modifies `/system`, so KernelSU's metamodule requirement (which only applies to modules mounting a `system/` directory) does not apply |
| No logs / can't find the IP and port | Check `logs/action.log` (complete output of the last command) and `logs/server.log` (server's own output). The WebUI console shows both. The runtime status file also always carries the address |
| Switching the log level seems to do nothing | A new level is applied the next time the server starts — tap **Restart** (or run `action.sh restart`). While `off`, `logs/server.log` is intentionally emptied |
| Server dies right after starting from the panel | Fixed — it is launched with `setsid` so it survives the manager's temporary root shell |

## License

MIT
