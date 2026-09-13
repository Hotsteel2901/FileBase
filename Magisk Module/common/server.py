#!/usr/bin/env python3
"""Android /sdcard web file server — listens on port 6532."""

import http.server
import json
import os
import re
import signal
import shutil
import stat
import sys
import threading
import time
import urllib.parse
import mimetypes
import subprocess
import shlex
import base64

HOST = os.environ.get("BIND_IP", "0.0.0.0")
PORT = 6532
ROOT = "/sdcard"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")  # off / error / info / debug
# Log levels: off=nothing, error=4xx/5xx only, info=requests+status, debug=all+timing

ADMIN_USER = "admin"
ADMIN_PASS = "hotsteel"
ADMIN_TOKENS = {}  # token -> True (in-memory session store)

# Maximum number of bytes we will read into memory for a JSON request body.
_JSON_BODY_LIMIT = 104857600  # 100 MB
_META_BODY_LIMIT = 65536      # 64 KB

_STATUS_RE = re.compile(r'"\s*(\d{3})(?:\s|$)')
_ERRCODE_RE = re.compile(r'\bcode\s+(\d{3})\b')


def _content_length(handler):
    """Parse the request Content-Length.

    Returns the byte count, or None when the header is missing/invalid.
    """
    raw = handler.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _under_root(root_real, candidate):
    """True when *candidate* is the root itself or lives inside it."""
    if root_real == "/":
        return candidate.startswith("/")
    if candidate == root_real:
        return True
    return candidate.startswith(root_real + os.sep)

# ── HTML frontend (embedded so no extra files needed) ────────────────────

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>FileBase</title>
<!-- No external webfonts: the server usually runs on an offline hotspot LAN. -->
<style>
/* ═══ RESET ═══ */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

/* ═══ THEME VARIABLES ═══ */
[data-theme="dark"]{
  --bg:#0c0c0c;--surface:#151515;--surface-2:#1e1e1e;--surface-3:#262626;
  --border:#2a2a2a;--border-hi:#3a3a3a;
  --text:#e4e4e4;--text-dim:#707070;--text-muted:#4a4a4a;
  --accent:#d4943a;--accent-bright:#e8a838;--accent-dim:rgba(212,148,58,.12);
  --danger:#d94040;--danger-dim:rgba(217,64,64,.12);
  --success:#3da060;--success-dim:rgba(61,160,96,.12);
  --glow:0 0 20px rgba(212,148,58,.15);
  --dot:rgba(255,255,255,.025);
  --shadow:0 4px 24px rgba(0,0,0,.6);
  --scrollbar-thumb:#333;--scrollbar-track:transparent;
}
[data-theme="light"]{
  --bg:#f4f2ed;--surface:#ffffff;--surface-2:#faf8f4;--surface-3:#f0ede6;
  --border:#ddd9d2;--border-hi:#c8c4bc;
  --text:#1a1a1a;--text-dim:#888880;--text-muted:#b0aca4;
  --accent:#b87a20;--accent-bright:#d4943a;--accent-dim:rgba(184,122,32,.1);
  --danger:#c03030;--danger-dim:rgba(192,48,48,.08);
  --success:#2d8a4a;--success-dim:rgba(45,138,74,.1);
  --glow:0 2px 12px rgba(184,122,32,.1);
  --dot:rgba(0,0,0,.03);
  --shadow:0 4px 24px rgba(0,0,0,.08);
  --scrollbar-thumb:#ccc;--scrollbar-track:transparent;
}

/* ═══ BASE ═══ */
html{font-size:15px;-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{
  font-family:'Figtree',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;
  display:flex;flex-direction:column;
  background-image:radial-gradient(var(--dot) 1px,transparent 1px);
  background-size:20px 20px;
  animation:fadeIn .4s ease;
}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--scrollbar-track)}
::-webkit-scrollbar-thumb{background:var(--scrollbar-thumb);border-radius:3px}
::selection{background:var(--accent-dim);color:var(--accent-bright)}
a{color:inherit}
input,button,textarea{font-family:inherit;font-size:inherit}

@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes slideUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}

/* ═══ HEADER ═══ */
.topbar{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 20px;display:flex;align-items:center;height:52px;
  position:sticky;top:0;z-index:100;gap:16px;
}
.brand{
  font-family:'Bebas Neue','Arial Narrow',Impact,'Arial Black',sans-serif;
  font-size:22px;letter-spacing:3px;color:var(--accent);
  display:flex;align-items:center;gap:10px;flex-shrink:0;
  user-select:none;
}
.brand-dot{
  width:8px;height:8px;border-radius:50%;background:var(--accent);
  animation:pulse 2s ease infinite;
  box-shadow:0 0 6px var(--accent);
}
.breadcrumb{
  flex:1;display:flex;align-items:center;gap:2px;
  font-size:13px;min-width:0;overflow-x:auto;
  scrollbar-width:none;
}
.breadcrumb::-webkit-scrollbar{display:none}
.bc-sep{color:var(--text-muted);padding:0 2px;user-select:none;font-size:11px}
.bc-link{
  color:var(--text-dim);cursor:pointer;padding:4px 8px;border-radius:2px;
  white-space:nowrap;transition:color .15s,background .15s;
}
.bc-link:hover{color:var(--text);background:var(--accent-dim)}
.bc-link.current{color:var(--accent);font-weight:600;cursor:default}
.bc-link.current:hover{background:transparent}
.bc-root{color:var(--text-dim);cursor:pointer;padding:4px 6px;border-radius:2px}
.bc-root:hover{color:var(--text);background:var(--accent-dim)}
.controls{display:flex;align-items:center;gap:6px;flex-shrink:0}
.ctrl-btn{
  background:var(--surface-2);border:1px solid var(--border);color:var(--text-dim);
  padding:5px 12px;border-radius:2px;cursor:pointer;font-size:12px;font-weight:600;
  transition:all .15s;display:flex;align-items:center;gap:5px;user-select:none;
}
.ctrl-btn:hover{color:var(--accent);border-color:var(--accent);background:var(--accent-dim);transform:translateY(-1px)}
.ctrl-btn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:2}

/* ═══ TOOLBAR ═══ */
.toolbar{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:8px 20px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;
}
.tool-btn{
  background:var(--surface-2);border:1px solid var(--border);color:var(--text-dim);
  padding:6px 14px;border-radius:2px;cursor:pointer;font-size:12px;font-weight:500;
  transition:all .15s;display:inline-flex;align-items:center;gap:6px;
  white-space:nowrap;user-select:none;
}
.tool-btn:hover{color:var(--text);border-color:var(--border-hi);background:var(--surface-3);transform:translateY(-1px);box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.tool-btn{transition:all .2s}
.tool-btn:active{transform:scale(.97)}
.tool-btn.primary{background:var(--accent-dim);color:var(--accent);border-color:var(--accent)}
.tool-btn.primary:hover{background:var(--accent);color:#0c0c0c}
.tool-btn.danger:hover{color:var(--danger);border-color:var(--danger);background:var(--danger-dim)}
.search-box{
  margin-left:auto;background:var(--surface-2);border:1px solid var(--border);
  color:var(--text);padding:6px 12px;border-radius:2px;font-size:12px;width:180px;
  transition:border-color .15s;
}
.search-box:focus{outline:none;border-color:var(--accent)}
.search-box::placeholder{color:var(--text-muted)}

/* ═══ STATUS BAR ═══ */
.statusbar{
  padding:6px 20px;font-size:11px;color:var(--text-muted);
  display:flex;align-items:center;gap:12px;
  font-family:'JetBrains Mono','Courier New',monospace;
  border-bottom:1px solid var(--border);background:var(--surface);
}
.statusbar .stat{display:flex;align-items:center;gap:4px}
.statusbar .dot{width:4px;height:4px;border-radius:50%;background:var(--accent)}

/* ═══ FILE LIST ═══ */
.content{flex:1;padding:0}
.file-table{width:100%;border-collapse:collapse}
.file-table thead th{
  text-align:left;padding:10px 16px;font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.8px;color:var(--text-muted);
  border-bottom:1px solid var(--border);cursor:pointer;user-select:none;
  position:sticky;top:0;background:var(--surface);z-index:5;
  transition:color .15s;
}
.file-table thead th:hover{color:var(--text-dim)}
.file-table thead th.sorted{color:var(--accent)}
.file-table thead th .sort-arrow{margin-left:4px;font-size:10px;opacity:.5}
.file-table thead th.sorted .sort-arrow{opacity:1;color:var(--accent)}
.file-row{transition:all .2s;
  border-bottom:1px solid var(--border);transition:background .12s;
  animation:slideUp .25s ease both;
}
.file-row:hover{background:var(--surface-2);transform:translateX(2px)}
.file-row td{padding:8px 16px;vertical-align:middle}
.file-name{display:flex;align-items:center;gap:10px;min-width:0}
.file-icon{
  width:28px;height:28px;border-radius:2px;
  display:flex;align-items:center;justify-content:center;
  font-size:13px;flex-shrink:0;
  background:var(--surface-3);color:var(--text-dim);
  font-family:'JetBrains Mono','Courier New',monospace;
  font-weight:500;
}
.file-icon.folder{color:var(--accent);background:var(--accent-dim)}
.file-name-text{
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-size:13px;font-weight:500;
}
.file-name-link{color:var(--text);text-decoration:none;cursor:pointer;transition:color .15s}
.file-name-link:hover{color:var(--accent)}
.file-meta{
  font-family:'JetBrains Mono','Courier New',monospace;
  font-size:11px;color:var(--text-dim);white-space:nowrap;
}
.file-actions{white-space:nowrap;display:flex;gap:4px}
.file-act-btn{
  background:transparent;border:1px solid transparent;color:var(--text-muted);
  padding:3px 8px;border-radius:2px;cursor:pointer;font-size:11px;
  transition:all .15s;
}
.file-act-btn:hover{color:var(--text);border-color:var(--border);background:var(--surface-3)}
.file-act-btn.del:hover{color:var(--danger);border-color:var(--danger);background:var(--danger-dim)}

/* ═══ EMPTY STATE ═══ */
.empty-state{
  text-align:center;padding:80px 20px;color:var(--text-muted);
}
.empty-state-icon{font-size:48px;margin-bottom:12px;opacity:.3}
.empty-state-text{font-size:14px;font-weight:500}

/* ═══ PROGRESS ═══ */
.progress-bar{
  position:fixed;top:0;left:0;height:2px;background:var(--accent);z-index:200;
  transition:width .2s ease;width:0;
  box-shadow:0 0 8px var(--accent);
}

/* ═══ TOAST ═══ */
.toast-container{position:fixed;bottom:20px;right:20px;z-index:300;display:flex;flex-direction:column;gap:8px}
.toast{
  background:var(--surface-2);border:1px solid var(--border);color:var(--text);
  padding:10px 18px;border-radius:3px;font-size:12px;font-weight:500;
  box-shadow:var(--shadow);animation:slideUp .25s ease;
  display:flex;align-items:center;gap:8px;max-width:320px;
}
.toast.error{border-color:var(--danger);color:var(--danger)}
.toast.success{border-color:var(--success);color:var(--success)}
.toast-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.toast.error .toast-dot{background:var(--danger)}
.toast.success .toast-dot{background:var(--success)}
.toast.info .toast-dot{background:var(--accent)}

/* ═══ DROP OVERLAY ═══ */
.drop-overlay{
  position:fixed;inset:0;background:var(--accent-dim);
  border:2px dashed var(--accent);z-index:150;display:none;
  justify-content:center;align-items:center;
  backdrop-filter:blur(2px);
}
.drop-overlay.active{display:flex}
.drop-overlay-inner{
  text-align:center;color:var(--accent);
}
.drop-overlay-icon{font-size:48px;margin-bottom:8px}
.drop-overlay-text{font-size:16px;font-weight:600}

/* ═══ MODAL ═══ */
.modal-backdrop{
  position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:100;
  display:none;justify-content:center;align-items:center;
  backdrop-filter:blur(3px);
}
.modal-backdrop.active{display:flex}
.modal{
  background:var(--surface);border:1px solid var(--border);border-radius:4px;
  width:92%;max-width:700px;max-height:85vh;display:flex;flex-direction:column;
  box-shadow:var(--shadow);animation:slideUp .2s ease;
}
.modal.sm{max-width:420px}
.modal-header{
  padding:16px 20px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
}
.modal-title{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.modal-title .accent{color:var(--accent)}
.modal-close{
  background:transparent;border:none;color:var(--text-dim);cursor:pointer;
  padding:4px 8px;border-radius:2px;font-size:18px;line-height:1;
  transition:color .15s;
}
.modal-close:hover{color:var(--text)}
.modal-body{padding:16px 20px;flex:1;overflow-y:auto}
.modal-footer{
  padding:12px 20px;border-top:1px solid var(--border);
  display:flex;gap:8px;justify-content:flex-end;
}
.modal textarea{
  width:100%;min-height:350px;background:var(--bg);color:var(--text);
  border:1px solid var(--border);border-radius:2px;padding:14px;
  font-family:'JetBrains Mono','Courier New',monospace;font-size:12px;
  resize:vertical;line-height:1.6;transition:border-color .15s;
}
.modal textarea:focus{outline:none;border-color:var(--accent)}
.modal input[type=text]{
  width:100%;background:var(--bg);color:var(--text);
  border:1px solid var(--border);border-radius:2px;padding:10px 14px;
  font-size:14px;transition:border-color .15s;
}
.modal input[type=text]:focus{outline:none;border-color:var(--accent)}
.modal input[type=text]::placeholder{color:var(--text-muted)}
.btn{
  padding:8px 20px;border-radius:2px;border:1px solid var(--border);
  cursor:pointer;font-size:12px;font-weight:500;transition:all .15s;
  background:var(--surface-2);color:var(--text-dim);
}
.btn:hover{color:var(--text);border-color:var(--border-hi)}
.btn-primary{background:var(--accent);color:#0c0c0c;border-color:var(--accent);font-weight:600}
.btn-primary:hover{background:var(--accent-bright)}

/* ═══ FOOTER ═══ */
.footer{
  padding:8px 20px;font-size:10px;color:var(--text-muted);
  display:flex;align-items:center;justify-content:space-between;
  border-top:1px solid var(--border);background:var(--surface);
  font-family:'JetBrains Mono','Courier New',monospace;
}
.footer-id{display:flex;align-items:center;gap:6px}
.footer-id span{color:var(--text-dim)}

/* ═══ RESPONSIVE ═══ */
@media(max-width:700px){
  .topbar{padding:0 12px;gap:10px;height:48px}
  .brand{font-size:18px;letter-spacing:2px}
  .brand-text{display:none}
  .toolbar{padding:6px 12px;gap:4px}
  .tool-btn{padding:5px 10px;font-size:11px}
  .search-box{width:120px;margin-left:0}
  .content{padding:0}
  .file-table thead th{padding:8px 10px;font-size:10px}
  .file-row td{padding:6px 10px}
  .file-icon{width:24px;height:24px;font-size:11px}
  .file-name-text{font-size:12px}
  .file-meta{font-size:10px}
  .file-act-btn{padding:2px 6px;font-size:10px}
  .file-col-size,.file-col-date{display:none}
  .statusbar{padding:4px 12px;font-size:10px}
  .footer{flex-direction:column;gap:4px;text-align:center}
  .modal{width:96%;max-height:90vh}
  .modal textarea{min-height:250px}
}

/* ═══ LOADING SHIMMER ═══ */
.loading .file-row{transition:all .2s;
  background:linear-gradient(90deg,var(--surface) 25%,var(--surface-2) 50%,var(--surface) 75%);
  background-size:200% 100%;
  animation:shimmer 1.5s infinite;
  height:40px;
}

/* ═══ ADMIN ═══ */
.admin-badge{
  display:inline-flex;align-items:center;gap:4px;
  background:var(--danger-dim);color:var(--danger);
  padding:2px 8px;border-radius:2px;font-size:10px;font-weight:700;
  letter-spacing:.5px;text-transform:uppercase;
  font-family:'JetBrains Mono','Courier New',monospace;
}
.ctrl-btn.admin-btn{color:var(--danger);border-color:var(--danger)}
.ctrl-btn.admin-btn:hover{background:var(--danger);color:#fff}

/* ═══ LOGIN MODAL ═══ */
.login-input{
  width:100%;background:var(--bg);color:var(--text);
  border:1px solid var(--border);border-radius:2px;padding:10px 14px;
  font-size:14px;font-family:'JetBrains Mono','Courier New',monospace;
  transition:border-color .15s;
}
.login-input:focus{outline:none;border-color:var(--accent)}
.login-input::placeholder{color:var(--text-muted)}
.login-error{color:var(--danger);font-size:12px;min-height:16px;margin-top:6px}
</style>
</head>
<body>
<div class="progress-bar" id="progress"></div>

<!-- Drop overlay -->
<div class="drop-overlay" id="dropOverlay">
  <div class="drop-overlay-inner">
    <div class="drop-overlay-icon">&#9654;</div>
    <div class="drop-overlay-text" data-i18n="dropFiles">Drop files to upload</div>
  </div>
</div>

<!-- Toast container -->
<div class="toast-container" id="toastContainer"></div>

<!-- ═══ TOP BAR ═══ -->
<div class="topbar">
  <div class="brand">
    <div class="brand-dot"></div>
    <span class="brand-text">FILEBASE</span>
  </div>
  <div class="breadcrumb" id="breadcrumb"></div>
  <div class="controls">
    <button class="ctrl-btn admin-btn" id="adminBtn" style="display:none" onclick="App.showLogin()" data-i18n="adminLogin">Admin</button>
    <button class="ctrl-btn" id="themeToggle" title="Toggle theme">
      <span id="themeIcon" class="theme-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
      </span>
    </button>
    <button class="ctrl-btn" id="langToggle">EN</button>
  </div>
</div>

<!-- ═══ TOOLBAR ═══ -->
<div class="toolbar">
  <button class="tool-btn" onclick="App.goUp()" data-i18n="up">&#8593; Up</button>
  <button class="tool-btn" onclick="App.refresh()" data-i18n="refresh">&#8635; Refresh</button>
  <button class="tool-btn primary" onclick="document.getElementById('fileInput').click()" data-i18n="upload">&#11014; Upload</button>
  <input type="file" id="fileInput" multiple style="position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden">
  <button class="tool-btn" onclick="App.newFolderModal()" data-i18n="newFolder">&#9654; Folder</button>
  <button class="tool-btn" onclick="App.newFileModal()" data-i18n="newFile">&#9654; File</button>
  <input type="text" class="search-box" id="searchBox" data-i18n-placeholder="search" placeholder="Filter...">
</div>

<!-- ═══ STATUS BAR ═══ -->
<div class="statusbar" id="statusbar">
  <div class="stat"><div class="dot"></div><span id="statusCount">0 items</span></div>
  <div class="stat" id="statusFolders"></div>
  <div class="stat" id="statusFiles"></div>
</div>

<!-- ═══ FILE LIST ═══ -->
<div class="content">
  <table class="file-table">
    <thead>
      <tr>
        <th class="file-col-name" onclick="App.sort(0)"><span data-i18n="name">Name</span><span class="sort-arrow">&#9652;</span></th>
        <th class="file-col-size" onclick="App.sort(1)"><span data-i18n="size">Size</span><span class="sort-arrow">&#9652;</span></th>
        <th class="file-col-date" onclick="App.sort(2)"><span data-i18n="modified">Modified</span><span class="sort-arrow">&#9652;</span></th>
        <th><span data-i18n="actions">Actions</span></th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty-state" id="emptyState" style="display:none">
    <div class="empty-state-icon">&#9654;</div>
    <div class="empty-state-text" data-i18n="emptyDir">Empty directory</div>
  </div>
</div>

<!-- ═══ EDIT MODAL ═══ -->
<div class="modal-backdrop" id="editBackdrop" onclick="if(event.target===this)App.closeEdit()">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-title"><span class="accent">&#9998;</span> <span id="editTitle">Edit File</span></div>
      <button class="modal-close" onclick="App.closeEdit()">&times;</button>
    </div>
    <div class="modal-body">
      <textarea id="editContent" spellcheck="false"></textarea>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeEdit()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" onclick="App.saveEdit()" data-i18n="save">Save</button>
    </div>
  </div>
</div>

<!-- ═══ NAME INPUT MODAL ═══ -->
<div class="modal-backdrop" id="nameBackdrop" onclick="if(event.target===this)App.closeNameModal()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title"><span class="accent" id="nameIcon">&#9654;</span> <span id="nameTitle">New Folder</span></div>
      <button class="modal-close" onclick="App.closeNameModal()">&times;</button>
    </div>
    <div class="modal-body">
      <input type="text" id="nameInput" placeholder="Enter name..." data-i18n-placeholder="enterName">
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeNameModal()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="nameConfirmBtn" onclick="App.confirmName()">Create</button>
    </div>
  </div>
</div>

<!-- ═══ DELETE CONFIRM MODAL ═══ -->
<div class="modal-backdrop" id="delBackdrop" onclick="if(event.target===this)App.closeDelModal()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title" style="color:var(--danger)"><span>&#9888;</span> <span data-i18n="deleteConfirm">Confirm Delete</span></div>
      <button class="modal-close" onclick="App.closeDelModal()">&times;</button>
    </div>
    <div class="modal-body">
      <p style="font-size:13px;color:var(--text-dim)" id="delMsg">Delete this item?</p>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeDelModal()" data-i18n="cancel">Cancel</button>
      <button class="btn" style="background:var(--danger);color:#fff;border-color:var(--danger)" onclick="App.confirmDel()" data-i18n="delete">Delete</button>
    </div>
  </div>
</div>

<!-- ═══ LOGIN MODAL ═══ -->
<div class="modal-backdrop" id="loginBackdrop" onclick="if(event.target===this)App.closeLogin()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title" style="color:var(--danger)"><span>&#128274;</span> <span data-i18n="adminLogin">Admin Login</span></div>
      <button class="modal-close" onclick="App.closeLogin()">&times;</button>
    </div>
    <div class="modal-body">
      <input type="text" id="loginUser" class="login-input" placeholder="Username" data-i18n-placeholder="username" style="margin-bottom:10px"><br>
      <input type="password" id="loginPass" class="login-input" placeholder="Password" data-i18n-placeholder="password">
      <div class="login-error" id="loginError"></div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeLogin()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" onclick="App.doLogin()" data-i18n="login">Login</button>
    </div>
  </div>
</div>

<!-- ═══ FOOTER ═══ -->
<div class="footer">
  <div class="footer-id"><span>ID:</span><span id="footerUid">—</span></div>
  <div><span data-i18n="serving">Serving</span>: <span id="footerRoot">/sdcard</span> &middot; <span id="footerPort">:6532</span></div>
</div>

<script>
/* ═══════════════════════════════════════════════════
   FILEBASE — Android File Manager Frontend
   ═══════════════════════════════════════════════════ */
var App = (() => {

// ─── i18n ─────────────────────────────────────────
const L = {
  en: {
    title:"FILEBASE", up:"↑ Up", refresh:"↻ Refresh", upload:"↑ Upload",
    newFolder:"▸ Folder", newFile:"▸ File", search:"Filter...",
    name:"Name", size:"Size", modified:"Modified", actions:"Actions",
    edit:"Edit", delete:"Delete", rename:"Rename", download:"Download",
    cancel:"Cancel", save:"Save", create:"Create",
    editFile:"Edit File", newFolderTitle:"New Folder", newFileTitle:"New File",
    enterName:"Enter name...",
    deleteConfirm:"Confirm Delete",
    deleteFileMsg:'Delete file ', deleteFolderMsg:'Delete folder ',
    deleteEnd:'? This cannot be undone.',
    dropFiles:"Drop files to upload",
    uploaded:"Uploaded", failed:"Failed", deleted:"Deleted",
    renamed:"Renamed", saved:"Saved", created:"Created",
    cannotRead:"Cannot read file",
    items:"items", folders:"folders", files:"files",
    serving:"Serving", connected:"Connected",
    emptyDir:"Empty directory",
    editLabel:"Edit", deleteLabel:"Delete", renameLabel:"Rename",
    langBtn:"EN", langAlt:"中文",
    adminLogin:"Admin Login", adminBtn:"Admin", logout:"Logout",
    username:"Username", password:"Password", login:"Login",
    loginFailed:"Invalid credentials", rootDir:"Root",
    adminBadges:"ADMIN", filterNoMatch:"No matching files",
    renameTitle:"Rename", downloadLabel:"Get", loadFailed:"Failed to load directory",
    actionFailed:"Action failed", invalidName:"Invalid name",
    unsaved:"Unsaved changes", unsavedMsg:"Discard unsaved changes?",
    keepEditing:"Keep editing", discard:"Discard",
    alreadyExists:"A file or folder with that name already exists",
  },
  zh: {
    title:"文件管理器", up:"↑ 返回", refresh:"↻ 刷新", upload:"↑ 上传",
    newFolder:"▸ 新建文件夹", newFile:"▸ 新建文件", search:"搜索...",
    name:"名称", size:"大小", modified:"修改时间", actions:"操作",
    edit:"编辑", delete:"删除", rename:"重命名", download:"下载",
    cancel:"取消", save:"保存", create:"创建",
    editFile:"编辑文件", newFolderTitle:"新建文件夹", newFileTitle:"新建文件",
    enterName:"输入名称...",
    deleteConfirm:"确认删除",
    deleteFileMsg:'删除文件 ', deleteFolderMsg:'删除文件夹 ',
    deleteEnd:'？此操作不可撤销。',
    dropFiles:"拖放文件以上传",
    uploaded:"已上传", failed:"失败", deleted:"已删除",
    renamed:"已重命名", saved:"已保存", created:"已创建",
    cannotRead:"无法读取文件",
    items:"项", folders:"个文件夹", files:"个文件",
    serving:"服务中", connected:"已连接",
    emptyDir:"空目录",
    editLabel:"编辑", deleteLabel:"删除", renameLabel:"重命名",
    langBtn:"中文", langAlt:"EN",
    adminLogin:"管理员登录", adminBtn:"管理", logout:"退出",
    username:"用户名", password:"密码", login:"登录",
    loginFailed:"用户名或密码错误", rootDir:"根目录",
    adminBadges:"管理员", filterNoMatch:"无匹配文件",
    renameTitle:"重命名", downloadLabel:"下载", loadFailed:"目录加载失败",
    actionFailed:"操作失败", invalidName:"名称无效",
    unsaved:"有未保存的修改", unsavedMsg:"放弃未保存的修改？",
    keepEditing:"继续编辑", discard:"放弃",
    alreadyExists:"已存在同名文件或文件夹",
  }
};

// ─── State ────────────────────────────────────────
let currentPath = "/";
let currentData = [];
let sortCol = 0, sortAsc = true;
let nameMode = null;
let editingPath = "";
let renameTarget = "";
let editDirty = false;
let lastRendered = [];
let delTarget = null;
let delIsDir = false;
let dragCounter = 0;
let isAdmin = false;
let adminToken = localStorage.getItem('fb_admin_token') || '';

// ─── User Identity ────────────────────────────────
function generateId() {
  const a = () => Math.random().toString(36).substring(2, 6);
  return a() + '-' + a() + '-' + a();
}
function getUserId() {
  let id = localStorage.getItem('fb_uid');
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : generateId();
    localStorage.setItem('fb_uid', id);
  }
  return id;
}

// ─── Language ─────────────────────────────────────
function detectLang() {
  const stored = localStorage.getItem('fb_lang');
  if (stored) return stored;
  const sys = navigator.language || navigator.userLanguage || '';
  return sys.toLowerCase().startsWith('zh') ? 'zh' : 'en';
}
function getLang() { return detectLang(); }
function setLang(lang) {
  localStorage.setItem('fb_lang', lang);
  applyLang();
}
function t(key) { return L[getLang()][key] || L.en[key] || key; }
function applyLang() {
  const lang = getLang();
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  // Show the language the button will switch *to*, not the current one.
  document.getElementById('langToggle').textContent = lang === 'zh' ? 'EN' : '中文';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (L[lang][key]) el.textContent = L[lang][key];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (L[lang][key]) el.placeholder = L[lang][key];
  });
  document.title = 'FileBase — ' + L[lang].title;
}

// ─── Theme ────────────────────────────────────────
function getSystemTheme() {
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function getTheme() {
  return localStorage.getItem('fb_theme') || getSystemTheme();
}
function setTheme(theme) {
  localStorage.setItem('fb_theme', theme);
  applyTheme();
}
function toggleTheme() {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}
function applyTheme() {
  document.documentElement.setAttribute('data-theme', getTheme());
  updateThemeIcon();
}
function updateThemeIcon() {
  const wrap = document.getElementById('themeIcon');
  const isDark = getTheme() === 'dark';
  wrap.innerHTML = isDark
    ? '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
    : '<svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (!localStorage.getItem('fb_theme')) applyTheme();
});

// ─── API ──────────────────────────────────────────
  function authHeaders(extra) {
    const h = Object.assign({}, extra || {});
    if (isAdmin && adminToken) h['Authorization'] = 'Bearer ' + adminToken;
    return h;
  }
  async function api(endpoint, opts) {
    const merged = Object.assign({}, opts || {});
    merged.headers = authHeaders(merged.headers);
    const res = await fetch('/api' + endpoint, merged);
    let data = null;
    try { data = await res.json(); } catch(e) { data = null; }
    if (!res.ok) {
      const err = new Error((data && data.error) || ('HTTP ' + res.status));
      err.status = res.status;
      throw err;
    }
    return data || {};
  }
async function loadDir(path) {
  showProgress(30);
  try {
    const data = await api('/list?path=' + encodeURIComponent(path));
    currentData = data.entries || [];
    renderTable();
    renderBreadcrumb();
    updateStatus();
    showProgress(100);
    setTimeout(() => showProgress(0), 300);
  } catch(e) {
    showProgress(0);
    currentData = [];
    document.getElementById('tbody').innerHTML = '';
    const empty = document.getElementById('emptyState');
    empty.style.display = 'block';
    empty.querySelector('.empty-state-text').textContent =
      t('loadFailed') + ': ' + (e && e.message ? e.message : '');
    updateStatus();
    toast(t('loadFailed') + ': ' + (e && e.message ? e.message : ''), 'error');
  }
}

// ─── Navigation ───────────────────────────────────
  function go(path) { if (!path) path = '/'; currentPath = path; loadDir(path); }
  function goUp() {
    const rootPath = '/';
    if (currentPath === rootPath) return;
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    const newPath = '/' + parts.join('/') + (parts.length ? '/' : '');
    go(newPath);
  }
function refresh() { loadDir(currentPath); }

// ─── Breadcrumb ───────────────────────────────────
  function renderBreadcrumb() {
    const bc = document.getElementById('breadcrumb');
    const parts = currentPath.split('/').filter(Boolean);
    let html = '<span class="bc-root" data-nav="/">' + (isAdmin ? '/' : '&#8962;') + '</span>';
    if (isAdmin) {
      // Show additional root indicator for admin
    }
    let accum = '';
    parts.forEach((p, i) => {
      accum += '/' + p;
      html += '<span class="bc-sep">›</span>';
      if (i === parts.length - 1) {
        html += '<span class="bc-link current">' + esc(p) + '</span>';
      } else {
        html += '<span class="bc-link" data-nav="' + esc(accum) + '/">' + esc(p) + '</span>';
      }
    });
    bc.innerHTML = html;
  }

// ─── Status Bar ───────────────────────────────────
function updateStatus() {
  const total = lastRendered.length;
  const dirs = lastRendered.filter(e => e.isdir).length;
  const files = total - dirs;
  document.getElementById('statusCount').textContent = total + ' ' + t('items');
  document.getElementById('statusFolders').textContent = dirs + ' ' + t('folders');
  document.getElementById('statusFiles').textContent = files + ' ' + t('files');
}

// ─── Render Table ─────────────────────────────────
function renderTable() {
  const tbody = document.getElementById('tbody');
  const empty = document.getElementById('emptyState');
  const filter = document.getElementById('searchBox').value.toLowerCase();
  let items = currentData.filter(e => e.name.toLowerCase().includes(filter));

  items.sort((a, b) => {
    let va, vb;
    if (sortCol === 0) { va = a.name.toLowerCase(); vb = b.name.toLowerCase(); }
    else if (sortCol === 1) { va = a.size || 0; vb = b.size || 0; }
    else { va = a.mtime || 0; vb = b.mtime || 0; }
    return va < vb ? (sortAsc ? -1 : 1) : va > vb ? (sortAsc ? 1 : -1) : 0;
  });
  items.sort((a, b) => (b.isdir ? 1 : 0) - (a.isdir ? 1 : 0));
  lastRendered = items;

  updateSortHeaders();

  if (items.length === 0 && currentData.length === 0) {
    // Directory is truly empty (no filter active)
    empty.style.display = 'block';
    empty.querySelector('.empty-state-text').textContent = t('emptyDir');
    return;
  }
  if (items.length === 0) {
    // Filter yielded no results
    empty.style.display = 'block';
    empty.querySelector('.empty-state-text').textContent = t('filterNoMatch');
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = items.map((e, i) => {
    const ext = e.isdir ? '' : e.name.split('.').pop().toLowerCase();
    const iconLabel = e.isdir ? (esc(e.name.charAt(0).toUpperCase())) : ext.substring(0, 3).toUpperCase();
    const iconClass = e.isdir ? 'file-icon folder' : 'file-icon';
    const sizeStr = e.isdir ? '—' : fmtSize(e.size);
    const mtimeStr = e.isdir ? '—' : fmtDate(e.mtime);
    const encPath = encodeURIComponent(currentPath + e.name);
    const rawPath = currentPath + e.name;
    // Native <a download> cannot send an Authorization header, so pass the
    // admin token in the query string to keep downloads streaming (and range
    // capable) instead of buffering the whole file in JavaScript.
    const tok = (isAdmin && adminToken) ? ('&token=' + encodeURIComponent(adminToken)) : '';
    const dlUrl = '/api/download?path=' + encPath + tok;

    let nameHtml;
    if (e.isdir) {
      nameHtml = '<a class="file-name-link" data-action="navigate" data-path="' + esc(rawPath) + '/">' + esc(e.name) + '</a>';
    } else {
      nameHtml = '<a class="file-name-link" href="' + esc(dlUrl) + '" download>' + esc(e.name) + '</a>';
    }

    const isdir = e.isdir ? '1' : '0';
    let acts = '';
    if (!e.isdir) {
      acts += '<button class="file-act-btn" data-action="download" data-url="' + esc(dlUrl) + '">' + t('downloadLabel') + '</button>';
    }
    if (e.editable) {
      acts += '<button class="file-act-btn" data-action="edit" data-path="' + esc(rawPath) + '">' + t('editLabel') + '</button>';
    }
    acts += '<button class="file-act-btn" data-action="rename" data-path="' + esc(rawPath) + '">' + t('renameLabel') + '</button>';
    acts += '<button class="file-act-btn del" data-action="delete" data-path="' + esc(rawPath) + '" data-isdir="' + isdir + '">' + t('deleteLabel') + '</button>';

    return '<tr class="file-row" style="animation-delay:' + (i * 20) + 'ms">' +
      '<td class="file-name"><div class="' + iconClass + '">' + iconLabel + '</div>' +
      '<div class="file-name-text">' + nameHtml + '</div></td>' +
      '<td class="file-meta file-col-size">' + sizeStr + '</td>' +
      '<td class="file-meta file-col-date">' + mtimeStr + '</td>' +
      '<td class="file-actions">' + acts + '</td></tr>';
  }).join('');
}

// ─── Sort ─────────────────────────────────────────
function sort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  renderTable();
}
function updateSortHeaders() {
  const ths = document.querySelectorAll('.file-table thead th');
  ths.forEach((th, i) => {
    const arrow = th.querySelector('.sort-arrow');
    if (i === sortCol) {
      th.classList.add('sorted');
      if (arrow) arrow.textContent = sortAsc ? '▲' : '▼';
    } else {
      th.classList.remove('sorted');
      if (arrow) arrow.textContent = '▲';
    }
  });
}

// ─── Upload ───────────────────────────────────────
async function uploadFiles(files) {
  if (!files.length) return;
  const arr = Array.from(files);
  for (let i = 0; i < arr.length; i++) {
    const file = arr[i];
    const pctBase = (i / arr.length) * 100;
    const pctRange = 100 / arr.length;
    await new Promise(resolve => {
      const fd = new FormData();
      fd.append('path', currentPath);
      fd.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
	      if (isAdmin && adminToken) xhr.setRequestHeader('Authorization', 'Bearer ' + adminToken);
      xhr.onload = () => {
        if (xhr.status === 200) {
          try {
            const res = JSON.parse(xhr.responseText);
            if (res.files && res.files.length) {
              res.files.forEach(f => {
                toast(f.ok ? (t('uploaded') + ': ' + f.name) : (t('failed') + ': ' + f.name), f.ok ? 'success' : 'error');
              });
            } else {
              toast(t('uploaded') + ': ' + file.name, 'success');
            }
          } catch(e) {
            toast(t('uploaded') + ': ' + file.name, 'success');
          }
        } else {
          toast(t('failed') + ': ' + file.name, 'error');
        }
        showProgress(i === arr.length - 1 ? 100 : 0);
        resolve();
      };
      xhr.onerror = () => { toast(t('failed') + ': ' + file.name, 'error'); showProgress(0); resolve(); };
      xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
          const filePct = e.loaded / e.total;
          showProgress(pctBase + filePct * pctRange);
        }
      };
      xhr.send(fd);
    });
  }
  showProgress(100);
  setTimeout(() => showProgress(0), 300);
  refresh();
  document.getElementById('fileInput').value = '';
}
document.getElementById('fileInput').addEventListener('change', function() {
  if (this.files.length) uploadFiles(this.files);
});

// ─── Delete ───────────────────────────────────────
function deleteItem(path, isdir) {
  delTarget = path;
  delIsDir = isdir;
  const name = path.split('/').filter(Boolean).pop();
  const prefix = isdir ? t('deleteFolderMsg') : t('deleteFileMsg');
  document.getElementById('delMsg').textContent = prefix + name + t('deleteEnd');
  document.getElementById('delBackdrop').classList.add('active');
}
function closeDelModal() { document.getElementById('delBackdrop').classList.remove('active'); }
async function confirmDel() {
  if (!delTarget) return;
  try {
    await api('/delete', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({path: delTarget}) });
    toast(t('deleted'), 'success');
    closeDelModal();
    refresh();
  } catch(e) {
    toast(t('actionFailed') + ': ' + (e && e.message ? e.message : ''), 'error');
  }
}

// ─── Rename ───────────────────────────────────────
function renameItem(oldPath) {
  renameTarget = oldPath;
  const oldName = oldPath.split('/').filter(Boolean).pop();
  nameMode = 'rename';
  openNameModal(t('renameTitle'), '✎');
  const inp = document.getElementById('nameInput');
  inp.value = oldName;
  inp.select();
}

// ─── Edit File ────────────────────────────────────
async function editFile(path) {
  editingPath = path;
  const name = path.split('/').filter(Boolean).pop();
  document.getElementById('editTitle').textContent = name;
  try {
    const res = await fetch('/api/download?path=' + encodeURIComponent(path),
        {headers: authHeaders()});
    if (!res.ok) {
      let msg = t('cannotRead');
      try { const j = await res.json(); if (j && j.error) msg = j.error; } catch(e) {}
      throw new Error(msg);
    }
    const text = await res.text();
    document.getElementById('editContent').value = text;
    editDirty = false;
    document.getElementById('editBackdrop').classList.add('active');
  } catch(e) { toast((e && e.message) || t('cannotRead'), 'error'); }
}
async function saveEdit() {
  const content = document.getElementById('editContent').value;
  try {
    const res = await fetch('/api/write', { method:'POST',
      headers: authHeaders({'Content-Type':'application/json'}),
      body: JSON.stringify({path: editingPath, content, overwrite: true}) });
    let data = null;
    try { data = await res.json(); } catch(e) { data = null; }
    if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));
    editDirty = false;
    toast(t('saved'), 'success');
    closeEdit();
    refresh();
  } catch(e) { toast((e && e.message) || t('actionFailed'), 'error'); }
}
function closeEdit(force) {
  if (!force && editDirty) {
    const discard = confirm(t('unsaved') + '\n\n' + t('unsavedMsg'));
    if (!discard) return;
  }
  editDirty = false;
  document.getElementById('editBackdrop').classList.remove('active');
}

// ─── New File / Folder ────────────────────────────
function newFolderModal() { nameMode = 'folder'; openNameModal(t('newFolderTitle'), '▸'); }
function newFileModal() { nameMode = 'file'; openNameModal(t('newFileTitle'), '▸'); }
function openNameModal(title, icon) {
  document.getElementById('nameTitle').textContent = title;
  document.getElementById('nameIcon').textContent = icon;
  document.getElementById('nameInput').value = '';
  document.getElementById('nameInput').placeholder = t('enterName');
  const okBtn = document.getElementById('nameConfirmBtn');
  if (okBtn) okBtn.textContent = nameMode === 'rename' ? t('rename') : t('create');
  document.getElementById('nameBackdrop').classList.add('active');
  setTimeout(() => document.getElementById('nameInput').focus(), 100);
}
function closeNameModal() { document.getElementById('nameBackdrop').classList.remove('active'); }
async function confirmName() {
  const name = document.getElementById('nameInput').value.trim();
  if (!name) return;
  if (name.indexOf('/') !== -1 || name === '.' || name === '..') {
    toast(t('invalidName'), 'error');
    return;
  }
  const fullPath = currentPath + name;
  try {
    if (nameMode === 'folder') {
      await api('/mkdir', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({path: fullPath}) });
    } else if (nameMode === 'rename') {
      const dir = renameTarget.substring(0, renameTarget.lastIndexOf('/') + 1);
      if (dir + name === renameTarget) { closeNameModal(); return; }
      await api('/rename', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({oldPath: renameTarget, newPath: dir + name}) });
    } else {
      await api('/write', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({path: fullPath, content: '', overwrite: false}) });
    }
    toast(t(nameMode === 'rename' ? 'renamed' : 'created') + ': ' + name, 'success');
    closeNameModal();
    refresh();
  } catch(e) {
    if (e && e.status === 409) {
      toast(t('alreadyExists'), 'error');
    } else {
      toast(t('actionFailed') + ': ' + (e && e.message ? e.message : ''), 'error');
    }
  }
}

// ─── Drag & Drop ──────────────────────────────────
document.addEventListener('dragenter', e => { e.preventDefault(); dragCounter++;
  document.getElementById('dropOverlay').classList.add('active'); });
document.addEventListener('dragleave', e => { e.preventDefault(); dragCounter--;
  if (dragCounter <= 0) { dragCounter = 0; document.getElementById('dropOverlay').classList.remove('active'); } });
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => {
  e.preventDefault(); dragCounter = 0;
  document.getElementById('dropOverlay').classList.remove('active');
  if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
});

// ─── Progress ─────────────────────────────────────
function showProgress(pct) { document.getElementById('progress').style.width = pct + '%'; }

// ─── Download ─────────────────────────────────────
function triggerDownload(url) {
  if (!url) return;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ─── Toast ────────────────────────────────────────
function toast(msg, type) {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = 'toast ' + (type || 'info');
  el.innerHTML = '<div class="toast-dot"></div>' + esc(msg);
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s';
    setTimeout(() => el.remove(), 300); }, 3000);
}

// ─── Utils ────────────────────────────────────────
function fmtSize(b) {
  if (b == null) return '—';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
  return (b/1073741824).toFixed(2) + ' GB';
}
function fmtDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  }
  return d.toLocaleDateString([], {month:'short', day:'numeric', year:'numeric'});
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ─── Admin ────────────────────────────────────────
  function showLogin() {
    document.getElementById('loginUser').value = '';
    document.getElementById('loginPass').value = '';
    document.getElementById('loginError').textContent = '';
    document.getElementById('loginBackdrop').classList.add('active');
    setTimeout(() => document.getElementById('loginUser').focus(), 100);
  }
  function closeLogin() { document.getElementById('loginBackdrop').classList.remove('active'); }
  async function doLogin() {
    const user = document.getElementById('loginUser').value.trim();
    const pwd = document.getElementById('loginPass').value;
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user: user, pass: pwd})
      });
      const data = await res.json();
      if (data.ok && data.token) {
        isAdmin = true;
        adminToken = data.token;
        localStorage.setItem('fb_admin_token', adminToken);
        closeLogin();
        applyAdminState();
        currentPath = '/';
        go('/');
        toast(t('adminBadges'), 'success');
      } else {
        document.getElementById('loginError').textContent = t('loginFailed');
      }
    } catch(e) {
      document.getElementById('loginError').textContent = t('loginFailed');
    }
  }
  async function doLogout() {
    try {
      await fetch('/api/logout', {method: 'POST', headers: authHeaders()});
    } catch(e) {}
    isAdmin = false;
    adminToken = '';
    localStorage.removeItem('fb_admin_token');
    applyAdminState();
    currentPath = '/';
    go('/');
  }
  function applyAdminState() {
    const btn = document.getElementById('adminBtn');
    if (isAdmin) {
      btn.style.display = '';
      btn.textContent = t('logout');
      btn.classList.add('admin-btn');
      btn.onclick = doLogout;
    } else {
      btn.style.display = '';
      btn.textContent = t('adminBtn');
      btn.classList.remove('admin-btn');
      btn.onclick = showLogin;
    }
    document.getElementById('footerRoot').textContent = isAdmin ? '/' : '/sdcard';
  }
  async function checkAuth() {
    if (!adminToken) { isAdmin = false; applyAdminState(); return; }
    try {
      const res = await fetch('/api/auth', {headers: authHeaders()});
      const data = await res.json();
      isAdmin = !!data.admin;
    } catch(e) {
      isAdmin = false;
    }
    if (!isAdmin) {
      adminToken = '';
      localStorage.removeItem('fb_admin_token');
    }
    applyAdminState();
  }
  // ─── Init ─────────────────────────────────────────
  function init() {
    const uid = getUserId();
    document.getElementById('footerUid').textContent = uid;

    applyTheme();
    applyLang();

    // Admin: check stored token viability
    checkAuth().then(() => {
      go(isAdmin ? '/' : '/');
    });

    // Login modal: Enter key submits
    document.getElementById('loginPass').addEventListener('keydown', e => {
      if (e.key === 'Enter') doLogin();
    });
    document.getElementById('loginUser').addEventListener('keydown', e => {
      if (e.key === 'Enter') document.getElementById('loginPass').focus();
    });

    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
    document.getElementById('langToggle').addEventListener('click', () => {
      setLang(getLang() === 'en' ? 'zh' : 'en');
    });

    // Track editor dirtiness so closing with unsaved changes can warn.
    document.getElementById('editContent').addEventListener('input', () => {
      editDirty = true;
    });

    // Enter confirms the new-file / new-folder / rename dialog.
    document.getElementById('nameInput').addEventListener('keydown', e => {
      if (e.key === 'Enter') confirmName();
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeEdit(); closeNameModal(); closeDelModal(); closeLogin();
      }
    });

    // Event delegation: breadcrumb navigation
    document.getElementById('breadcrumb').addEventListener('click', function(e) {
      const navEl = e.target.closest('[data-nav]');
      if (navEl) go(navEl.dataset.nav);
    });

    // Event delegation: file actions
    document.getElementById('tbody').addEventListener('click', function(e) {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      const path = btn.dataset.path;
      if (action === 'edit') editFile(path);
      else if (action === 'rename') renameItem(path);
      else if (action === 'delete') deleteItem(path, btn.dataset.isdir === '1');
      else if (action === 'navigate') go(path);
      else if (action === 'download') triggerDownload(btn.dataset.url);
    });

    // Search input
    document.getElementById('searchBox').addEventListener('input', renderTable);
  }

// Public API
return {
  go, goUp, refresh, sort, editFile, saveEdit, closeEdit,
  deleteItem, closeDelModal, confirmDel,
  renameItem, newFolderModal, newFileModal,
  closeNameModal, confirmName, uploadFiles, init,
    showLogin, closeLogin, doLogin, doLogout
};

})();

// Init — script at end of body so DOM is ready
App.init();
</script>
</body>
</html>
"""

# ── Server handler ───────────────────────────────────────────────────────

# Binary extensions that should never be opened in the text editor
_BINARY_EXTS = {
    '.apk','.aab','.zip','.gz','.tar','.rar','.7z','.bz2','.xz','.zst',
    '.jpg','.jpeg','.png','.gif','.webp','.bmp','.ico',
    '.mp3','.mp4','.ogg','.wav','.flac','.aac','.m4a','.mkv','.avi','.mov',
    '.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.odt','.ods',
    '.exe','.dll','.so','.o','.pyc','.class','.dex','.jar','.war',
    '.db','.sqlite','.iso','.img','.bin','.dat',
}

def _is_binary(filepath):
    """Check if a file appears to be binary by extension or content heuristics."""
    import os.path
    _, ext = os.path.splitext(filepath)
    if ext.lower() in _BINARY_EXTS:
        return True
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
        return b'\x00' in chunk
    except Exception:
        return True

class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 enables keep-alive. Every response must therefore carry an
    # accurate Content-Length (or use Connection: close).
    protocol_version = "HTTP/1.1"
    # Drop idle/stalled connections so a client that stops reading cannot pin
    # a worker thread forever.
    timeout = 60

    def _is_admin(self):
        """Check if the request carries a valid admin token.

        The token is normally sent as a ``Bearer`` authorization header.  Native
        browser downloads (``<a download>``) cannot set headers, so a ``token``
        query parameter is accepted as well; that keeps large downloads
        streamable by the browser instead of buffering them in JavaScript.
        """
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            if auth[7:] in ADMIN_TOKENS:
                return True
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            token = qs.get("token", [""])[0]
        except Exception:
            token = ""
        return bool(token) and token in ADMIN_TOKENS

    def _get_root(self):
        """Return filesystem root based on admin status."""
        return "/" if self._is_admin() else ROOT

    def _su_exec(self, cmd, input_data=None, timeout=30):
        """Run a shell command via su -c. Returns (returncode, stdout, stderr)."""
        try:
            p = subprocess.run(
                ['su', '-c', cmd],
                input=input_data,
                capture_output=True,
                timeout=timeout
            )
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, b'', b'timeout'
        except Exception as e:
            return 1, b'', str(e).encode()

    def _admin_listdir(self, path):
        """List a directory using su, returning list of entry dicts."""
        qpath = shlex.quote(path)
        script = (
            'cd ' + qpath + ' 2>/dev/null || { printf "\\n"; exit 0; }; '
            'for f in .* *; do '
            '  [ "$f" = "." ] && continue; '
            '  [ "$f" = ".." ] && continue; '
            '  [ ! -e "$f" ] 2>/dev/null && continue; '
            '  n=$(printf "%s" "$f" | base64 -w0 2>/dev/null || printf "%s" "$f" | tr -d "\\n" | base64 2>/dev/null); '
            '  [ -z "$n" ] && continue; '
            '  if [ -d "$f" ] 2>/dev/null; then t=d; else t=f; fi; '
            '  s=$(stat -c %s "$f" 2>/dev/null || wc -c < "$f" 2>/dev/null); s=${s:-0}; '
            '  m=$(stat -c %Y "$f" 2>/dev/null || echo 0); m=${m:-0}; '
            '  printf "%s|%s|%s|%s\\n" "$n" "$t" "${s//[^0-9]/}" "$m"; '
            'done'
        )
        code, stdout, stderr = self._su_exec(script)
        if code != 0 and code != 124:
            err = stderr.decode(errors='replace').strip()
            if err:
                raise PermissionError(err)
            raise PermissionError("Cannot access directory")
        entries = []
        for line in stdout.decode(errors='replace').strip().split('\n'):
            line = line.strip('\r')
            if not line:
                continue
            parts = line.split('|', 3)
            if len(parts) != 4:
                continue
            name_b64, ftype, size_str, mtime_str = parts
            try:
                name = base64.b64decode(name_b64).decode('utf-8', errors='replace')
            except Exception:
                continue
            try:
                size = int(size_str.strip())
            except ValueError:
                size = 0
            try:
                mtime = int(float(mtime_str.strip()))
            except ValueError:
                mtime = 0
            is_dir = (ftype == 'd')
            editable = False
            if not is_dir and size <= 5 * 1024 * 1024:
                # Mirror the non-admin listing: never offer the text editor for
                # binary payloads (a video/mp3 would be corrupted on save).
                try:
                    editable = not _is_binary(os.path.join(path, name))
                except Exception:
                    editable = False
            entries.append({
                "name": name,
                "isdir": is_dir,
                "size": size,
                "mtime": mtime,
                "editable": editable,
            })
        return entries

    @staticmethod
    def _status_code(msg):
        """Best-effort extraction of an HTTP status code from a log line."""
        m = _STATUS_RE.search(msg)
        if m:
            return int(m.group(1))
        m = _ERRCODE_RE.search(msg)
        if m:
            return int(m.group(1))
        m = re.match(r'^\s*(\d{3})\s', msg)
        if m:
            return int(m.group(1))
        return None

    def log_message(self, format, *args):
        if LOG_LEVEL == "off":
            return
        msg = format % args
        if "/api/ping" in msg:
            return  # health probe: never logged
        stripped = msg.strip()
        if LOG_LEVEL == "error":
            # Only log 4xx/5xx responses. request lines look like
            # `"GET /x HTTP/1.1" 404 -` and send_error() lines look like
            # `code 404, message ...`, so parse the code out of either shape.
            code = self._status_code(stripped)
            if code is None or code < 400:
                return
            sys.stderr.write("[%s] %s - [%s] %s\n" %
                             (HOST,
                              self.client_address[0],
                              self.log_date_time_string(), stripped))
        elif LOG_LEVEL == "debug":
            ts = time.strftime("%H:%M:%S")
            sys.stderr.write("[%s] %s:%d %s| %s\n" %
                             (ts, self.client_address[0],
                              self.client_address[1], self.command, stripped))
        else:
            sys.stderr.write("[%s] %s - [%s] %s\n" %
                             (HOST,
                              self.client_address[0],
                              self.log_date_time_string(), stripped))

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # Homepage / UI
        if parsed.path == "/" or parsed.path == "/index.html":
            body = INDEX_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
            return

        # API: check admin auth status
        if parsed.path == "/api/auth":
            self._json_response(200, {"admin": self._is_admin()})
            return

        # API: lightweight health probe used by action.sh / the WebUI. It is
        # deliberately excluded from the request log so status polling does not
        # fill server.log with noise.
        if parsed.path == "/api/ping":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        # API: list directory
        if parsed.path == "/api/list":
            path = qs.get("path", ["/"])[0]
            full = self._resolve(path)
            if not full:
                return self._json_error(403, "Path not allowed")
            entries = []
            try:
                if self._is_admin():
                    entries = self._admin_listdir(full)
                else:
                    if not os.path.isdir(full):
                        return self._json_error(404, "Directory not found")
                    for name in os.listdir(full):
                        fp = os.path.join(full, name)
                        try:
                            st = os.stat(fp)
                        except OSError:
                            # Broken symlink or a file that vanished mid-listing:
                            # keep the entry (using lstat when possible) instead
                            # of failing the whole directory listing.
                            try:
                                st = os.lstat(fp)
                            except OSError:
                                continue
                        isdir = stat.S_ISDIR(st.st_mode)
                        editable = not isdir and st.st_size <= 5 * 1024 * 1024 and not _is_binary(fp)
                        entries.append({
                            "name": name,
                            "isdir": isdir,
                            "size": st.st_size,
                            "mtime": int(st.st_mtime),
                            "editable": editable,
                        })
            except PermissionError:
                return self._json_error(403, "Permission denied")
            except OSError as e:
                self.log_message("ERROR: %s", e)
                return self._json_error(500, "Internal error")
            self._json_response(200, {"entries": entries})
            return

        # API: download file
        if parsed.path == "/api/download":
            path = qs.get("path", [""])[0]
            full = self._resolve(path)
            if not full:
                return self._json_error(403, "Path not allowed")
            return self._serve_download(full)

        # Fallback: serve static or 404
        not_found = b"Not found"
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(not_found)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(not_found)

    # ── POST ─────────────────────────────────────────────────────────────
    def _json_body(self, limit):
        """Read and parse a JSON request body, replying with an error on failure.

        Returns the parsed object, or None when a response has already been
        sent (missing/invalid Content-Length, oversized or malformed body).
        """
        length = _content_length(self)
        if length is None:
            self._json_error(411, "Content-Length required")
            return None
        if length > limit:
            self._json_error(413, "Request too large")
            return None
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except Exception:
            self._json_error(400, "Invalid JSON")
            return None

    def do_POST(self):
        # CSRF protection: reject cross-origin POSTs
        origin = self.headers.get("Origin", "")
        if origin:
            host = self.headers.get("Host", "")
            from urllib.parse import urlparse as _urlparse
            try:
                o = _urlparse(origin)
                origin_host = o.hostname
                if o.port and o.port not in (80, 443):
                    origin_host += ":" + str(o.port)
                # Require Host header; allow same-origin or localhost
                if not host or (origin_host != host and origin_host != "localhost" and origin_host != "localhost:" + str(PORT)):
                    return self._json_error(403, "Cross-origin request denied")
            except Exception:
                return self._json_error(403, "Invalid origin")
        parsed = urllib.parse.urlparse(self.path)

        # API: admin login
        if parsed.path == "/api/login":
            data = self._json_body(4096)
            if data is None:
                return
            user = data.get("user", "")
            pwd = data.get("pass", "")
            if user == ADMIN_USER and pwd == ADMIN_PASS:
                import secrets
                token = secrets.token_hex(32)
                ADMIN_TOKENS[token] = True
                self._json_response(200, {"ok": True, "token": token})
            else:
                self._json_error(403, "Invalid credentials")
            return

        # API: admin logout
        if parsed.path == "/api/logout":
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                ADMIN_TOKENS.pop(auth[7:], None)
            self._json_response(200, {"ok": True})
            return

        # API: upload file
        if parsed.path == "/api/upload":
            return self._handle_upload()

        # API: write file content
        if parsed.path == "/api/write":
            data = self._json_body(_JSON_BODY_LIMIT)
            if data is None:
                return
            path = data.get("path", "")
            content = data.get("content", "")
            full = self._resolve(path)
            if not full:
                return self._json_error(403, "Path not allowed")
            if not data.get("overwrite", True) and self._path_exists(full):
                return self._json_error(409, "File already exists")
            try:
                if self._is_admin():
                    qfull = shlex.quote(full)
                    qdir = shlex.quote(os.path.dirname(full))
                    code, _, stderr = self._su_exec(
                        'mkdir -p ' + qdir + ' && cat > ' + qfull,
                        input_data=content.encode('utf-8'),
                        timeout=60)
                    if code != 0:
                        raise OSError(stderr.decode(errors='replace'))
                else:
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "w", encoding="utf-8") as f:
                        f.write(content)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        # API: delete
        if parsed.path == "/api/delete":
            data = self._json_body(_META_BODY_LIMIT)
            if data is None:
                return
            full = self._resolve(data.get("path", ""))
            if not full:
                return self._json_error(403, "Path not allowed")
            if full == os.path.realpath(self._get_root()):
                return self._json_error(400, "Refusing to delete the root directory")
            try:
                if self._is_admin():
                    qfull = shlex.quote(full)
                    code, _, stderr = self._su_exec('rm -rf ' + qfull, timeout=30)
                    if code != 0:
                        raise OSError(stderr.decode(errors='replace'))
                else:
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    else:
                        os.remove(full)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        # API: mkdir
        if parsed.path == "/api/mkdir":
            data = self._json_body(_META_BODY_LIMIT)
            if data is None:
                return
            full = self._resolve(data.get("path", ""))
            if not full:
                return self._json_error(403, "Path not allowed")
            try:
                if self._is_admin():
                    qfull = shlex.quote(full)
                    code, _, stderr = self._su_exec('mkdir -p ' + qfull, timeout=15)
                    if code != 0:
                        raise OSError(stderr.decode(errors='replace'))
                else:
                    os.makedirs(full, exist_ok=True)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        # API: rename
        if parsed.path == "/api/rename":
            data = self._json_body(_META_BODY_LIMIT)
            if data is None:
                return
            old = self._resolve(data.get("oldPath", ""))
            new = self._resolve(data.get("newPath", ""))
            if not old or not new:
                return self._json_error(403, "Path not allowed")
            try:
                if self._is_admin():
                    qold = shlex.quote(old)
                    qnew = shlex.quote(new)
                    qdir = shlex.quote(os.path.dirname(new))
                    code, _, stderr = self._su_exec(
                        'mkdir -p ' + qdir + ' && mv ' + qold + ' ' + qnew,
                        timeout=15)
                    if code != 0:
                        raise OSError(stderr.decode(errors='replace'))
                else:
                    os.makedirs(os.path.dirname(new), exist_ok=True)
                    os.rename(old, new)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        self._json_error(404, "Unknown endpoint")

    # ── Helpers ──────────────────────────────────────────────────────────
    def _path_exists(self, full):
        """Existence check that also works for paths only root can see."""
        try:
            if os.path.lexists(full):
                return True
        except OSError:
            pass
        if self._is_admin():
            code, _, _ = self._su_exec(
                '[ -e %s ] || [ -L %s ]' % (shlex.quote(full), shlex.quote(full)),
                timeout=10)
            return code == 0
        return False

    @staticmethod
    def _content_disposition(fname):
        """Build an RFC 6266 / RFC 5987 compliant Content-Disposition value."""
        try:
            ascii_fname = fname.encode('ascii', 'replace').decode('ascii')
        except Exception:
            ascii_fname = "download"
        ascii_fname = ascii_fname.replace('"', '').replace('\\', '')
        if not ascii_fname:
            ascii_fname = "download"
        return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
            ascii_fname, urllib.parse.quote(fname, safe=''))

    def _parse_range(self, size):
        """Parse a single-range ``Range`` header.

        Returns (start, end) inclusive, ``None`` when the header is absent or
        unsupported, or ``"invalid"`` when the client asked for an unsatisfiable
        range (caller should reply 416).
        """
        header = self.headers.get("Range", "").strip()
        if not header or not header.startswith("bytes="):
            return None
        spec = header[len("bytes="):].split(",")[0].strip()
        if "-" not in spec:
            return None
        start_s, _, end_s = spec.partition("-")
        try:
            if start_s == "":
                # Suffix range: last N bytes.
                length = int(end_s)
                if length <= 0:
                    return "invalid"
                start = max(0, size - length)
                end = size - 1
            else:
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
        except ValueError:
            return None
        if size == 0:
            return "invalid"
        if start < 0 or start >= size or end < start:
            return "invalid"
        end = min(end, size - 1)
        return (start, end)

    def _serve_download(self, full):
        """Stream a file with HTTP range support.

        The server process usually already runs as root (module mode), so a
        plain ``open()`` is attempted first.  Only when that fails do we fall
        back to ``su -c cat`` for admin sessions — and that fallback streams the
        subprocess output instead of buffering the whole file in memory.
        """
        if os.path.isdir(full):
            return self._json_error(400, "Is a directory")

        fname = os.path.basename(full) or "download"
        ctype, _ = mimetypes.guess_type(full)
        if not ctype:
            ctype = "application/octet-stream"

        try:
            f = open(full, "rb")
        except (FileNotFoundError, NotADirectoryError):
            return self._json_error(404, "File not found")
        except PermissionError:
            if self._is_admin():
                return self._serve_download_via_su(full, fname, ctype)
            return self._json_error(403, "Permission denied")
        except OSError:
            return self._json_error(404, "File not found")

        try:
            size = os.fstat(f.fileno()).st_size
            rng = self._parse_range(size)
            if rng == "invalid":
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if rng:
                start, end = rng
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Range",
                                 "bytes %d-%d/%d" % (start, end, size))
                f.seek(start)
            else:
                start, length = 0, size
                self.send_response(200)

            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", self._content_disposition(fname))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._copy_stream(f, length)
        finally:
            try:
                f.close()
            except Exception:
                pass

    def _serve_download_via_su(self, full, fname, ctype):
        """Fallback download for files the server process cannot read directly."""
        qfull = shlex.quote(full)
        # Verify the file exists and is readable before we commit to a 200.
        try:
            probe = subprocess.run(
                ["su", "-c", "[ -f %s ] && [ -r %s ]" % (qfull, qfull)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            return self._json_error(404, "File not found or permission denied")
        if probe.returncode != 0:
            return self._json_error(404, "File not found or permission denied")

        try:
            proc = subprocess.Popen(
                ["su", "-c", "cat " + qfull],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return self._json_error(404, "File not found or permission denied")

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", self._content_disposition(fname))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def _copy_stream(self, f, length):
        """Copy at most *length* bytes from a binary file to the response."""
        remaining = length
        while remaining > 0:
            chunk = f.read(min(65536, remaining))
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            remaining -= len(chunk)

    def _resolve(self, path):
        """Resolve a virtual path under the appropriate root, preventing traversal.
        Returns the real path, or None if path escapes root."""
        root = self._get_root()
        root_real = os.path.realpath(root)
        # Normalise the incoming virtual path to an absolute, cleaned form.
        clean = os.path.normpath("/" + (path or "").lstrip("/"))

        if root_real == "/":
            # Admin mode: any absolute path is under root.
            return os.path.realpath(clean)

        # Accept both "/foo" (relative to root) and "/sdcard/foo" (already
        # prefixed) without producing "/sdcard/sdcard/foo".
        if clean == root_real or clean.startswith(root_real + os.sep):
            candidate = clean
        else:
            candidate = os.path.join(root_real, clean.lstrip("/"))
        real = os.path.realpath(candidate)
        # Traversal guard: real must be root_real itself or a child of it.
        if _under_root(root_real, real):
            return real
        return None

    def _handle_upload(self):
        """Parse multipart form-data for file upload."""
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            return self._json_error(400, "Expected multipart/form-data")
        length = _content_length(self)
        if length is None:
            return self._json_error(411, "Content-Length required")
        if length > 104857600:  # 100 MB limit
            return self._json_error(413, "File too large (max 100 MB)")
        boundary = ctype.split("boundary=")[-1].strip().strip('"').encode()
        if not boundary:
            return self._json_error(400, "Missing multipart boundary")
        data = self.rfile.read(length)

        # RFC 2046: boundaries are preceded by \r\n (or start of data)
        # and followed by \r\n or --\r\n
        delimiter = b"\r\n--" + boundary

        # Pass 1: split the body into (headers, body) parts.
        parts = []
        # Find first boundary (may be at start without leading \r\n)
        start = data.find(b"--" + boundary)
        if start == -1:
            return self._json_error(400, "Invalid multipart data")
        pos = start + len(b"--" + boundary)
        if data[pos:pos+2] == b"\r\n":
            pos += 2

        while pos < len(data):
            header_end = data.find(b"\r\n\r\n", pos)
            if header_end == -1:
                break
            headers_block = data[pos:header_end]
            body_start = header_end + 4

            # Find the next boundary — only \r\n--boundary (RFC-correct)
            next_pos = data.find(delimiter, body_start)
            if next_pos == -1:
                # No more parts
                break
            parts.append((headers_block, data[body_start:next_pos]))

            # Move past the delimiter and its trailing \r\n
            pos = next_pos + len(delimiter)
            if data[pos:pos+2] == b"\r\n":
                pos += 2
            elif data[pos:pos+4] == b"--\r\n" or data[pos:pos+3] == b"--":
                break

        # Pass 2: locate fields and files. The `path` field is resolved first
        # so uploads work no matter which order the client sends the parts in.
        target_path = "/"
        files = []
        for headers_block, body in parts:
            is_file = False
            is_path = False
            filename = None
            for hline in headers_block.split(b"\r\n"):
                if b"Content-Disposition" in hline:
                    if b'name="path"' in hline:
                        is_path = True
                    elif b'name="file"' in hline and b"filename=" in hline:
                        is_file = True
                        for seg in hline.split(b";"):
                            seg = seg.strip()
                            if seg.startswith(b"filename="):
                                filename = seg[len(b"filename="):].strip(b'"').decode("utf-8", errors="replace")

            if is_path:
                target_path = body.decode("utf-8", errors="replace").strip()
            elif is_file and filename:
                files.append((filename, body))

        dest_dir = self._resolve(target_path or "/")
        if not dest_dir:
            return self._json_error(403, "Path not allowed")

        # Pass 3: write the uploaded files.
        files_uploaded = []
        for filename, body in files:
            fn = os.path.basename(filename).replace("\x00", "")
            if not fn or fn in (".", ".."):
                continue
            dest = os.path.join(dest_dir, fn)
            if not _under_root(os.path.realpath(self._get_root()),
                               os.path.realpath(dest)):
                return self._json_error(403, "Path not allowed")
            try:
                if self._is_admin():
                    qdest_dir = shlex.quote(dest_dir)
                    qdest = shlex.quote(dest)
                    code, _, stderr = self._su_exec(
                        'mkdir -p ' + qdest_dir + ' && cat > ' + qdest,
                        input_data=body, timeout=60)
                    if code != 0:
                        raise OSError(stderr.decode(errors='replace'))
                else:
                    os.makedirs(dest_dir, exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(body)
            except Exception as e:
                files_uploaded.append({
                    "name": fn, "ok": False, "error": str(e) or "write failed",
                })
                continue
            files_uploaded.append({"name": fn, "ok": True})

        self._json_response(200, {"ok": True, "files": files_uploaded})

    def _json_response(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        self._json_response(code, {"error": msg})


def get_hotspot_ip():
    """Try to detect the hotspot interface IP by scanning all interfaces."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["ip", "-f", "inet", "addr", "show"],
            stderr=subprocess.DEVNULL).decode(errors="replace")
        iface = None
        # Parse output: lines like "    inet 192.168.43.1/24 ..."
        for block in out.split("\n"):
            stripped = block.lstrip()
            if stripped and stripped[0].isdigit():
                iface = block.strip().split(":")[1].strip() if ":" in block else None
            elif stripped.startswith("inet ") and iface:
                ip = stripped.split()[1].split("/")[0] if not stripped.split()[1].startswith("127") else None
                if ip and ip != "127.0.0.1" and ip.startswith(("192.168.", "10.", "172.")):
                    return iface, ip
    except Exception:
        pass
    # Fallback: try common names
    for iface in ["wlan0", "ap0", "wlan1", "swlan0", "rndis0", "softap0", "eth0"]:
        try:
            out = subprocess.check_output(
                ["ip", "-f", "inet", "addr", "show", iface],
                stderr=subprocess.DEVNULL).decode(errors="replace")
            for line in out.split("\n"):
                if "inet " in line:
                    ip = line.strip().split()[1].split("/")[0]
                    if ip != "127.0.0.1":
                        return iface, ip
        except Exception:
            continue
    return None, None


class _ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Threaded server so one slow transfer cannot block every other client."""

    daemon_threads = True
    allow_reuse_address = True
    # Class attribute: applied during server_bind(), i.e. before listen().
    request_queue_size = 64


def main():
    iface, ip = get_hotspot_ip()
    if HOST not in ("0.0.0.0", ""):
        print("[*] Bound to: %s:%d" % (HOST, PORT))
        if ip:
            print("[*] Hotspot host: %s @ %s" % (iface, ip))
    elif ip:
        print("[*] Hotspot detected: %s @ %s" % (iface, ip))
        print("[*] Server listening on all interfaces port %d" % PORT)
    else:
        print("[*] Could not detect hotspot interface")
        print("[*] Server listening on all interfaces port %d" % PORT)

    # ── Heartbeat daemon ──────────────────────────────────────────────────
    # Writes epoch timestamp to disk every 10 s. The WebUI detects
    # server liveness by checking how fresh this file is — no pgrep needed.
    # The heartbeat is only a convenience for the WebUI. Standalone no-root
    # runs cannot write under /data, so degrade gracefully instead of crashing.
    hbt_file = None
    try:
        os.makedirs("/data/local/webserver", exist_ok=True)
        hbt_file = "/data/local/webserver/.heartbeat"
    except OSError:
        print("[*] Heartbeat file unavailable (running without root) — continuing")

    if hbt_file:
        def _heartbeat():
            while True:
                try:
                    with open(hbt_file, "w") as f:
                        f.write(str(int(time.time())))
                except Exception:
                    pass
                time.sleep(10)

        threading.Thread(target=_heartbeat, daemon=True).start()

    try:
        server = _ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        print("[✗] Cannot listen on %s:%d — %s" % (HOST, PORT, e))
        print("    Another server may already be using this port. "
              "Run stop.sh first, or set PORT to a free port.")
        sys.exit(1)

    # Runtime facts the WebUI / action.sh can always read from disk. The bind
    # address is written here (not only to stdout) because the caller's shell
    # may be torn down right after start, and because log level "off" would
    # otherwise leave no way to discover the address.
    try:
        os.makedirs("/data/local/webserver", exist_ok=True)
        with open("/data/local/webserver/.server_pid", "w") as f:
            f.write(str(os.getpid()))
        with open("/data/local/webserver/status", "w") as f:
            f.write("PID=%d\n" % os.getpid())
            f.write("HOST=%s\n" % HOST)
            f.write("PORT=%d\n" % PORT)
            f.write("IFACE=%s\n" % (iface or ""))
            f.write("IP=%s\n" % (ip or ""))
            f.write("ROOT=%s\n" % ROOT)
            f.write("LOG_LEVEL=%s\n" % LOG_LEVEL)
            f.write("STARTED=%d\n" % int(time.time()))
    except OSError as e:
        print("[*] Could not write runtime status file: %s" % e)

    def _terminate(signum, frame):
        # Raising here unwinds out of serve_forever() in the main thread, which
        # lets the shutdown path below run without deadlocking.
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _terminate)
        except (ValueError, OSError):
            pass

    print("[*] Serving %s on port %d — press Ctrl+C to stop" % (ROOT, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
