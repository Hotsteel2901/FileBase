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
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>FileBase</title>
<style>
/* ═══ Design tokens ═══════════════════════════════════════════════════════ */
[data-theme="light"]{
  --bg:#bfe6fb;
  --bg-grad:radial-gradient(150% 100% at 50% -20%,#f2fcff 0%,#cfeeff 22%,#9fdcf9 48%,#8ed4f6 62%,#c3ebff 74%,#dcf3cc 88%,#b7e3a0 100%);
  --surface:rgba(255,255,255,.72);--surface-2:rgba(255,255,255,.62);--surface-3:rgba(234,247,255,.62);
  --surface-solid:#ffffff;
  --border:rgba(255,255,255,.85);--border-2:rgba(140,195,235,.55);
  --text:#0d3a56;--text-2:#3f6a86;--text-3:#6d92a9;
  --brand:#2f9bd4;--brand-2:#5cc0ea;--brand-soft:rgba(88,190,240,.2);--brand-ring:rgba(80,180,235,.55);
  --on-brand:#04314a;
  --ok:#2f9e52;--warn:#c8860f;--danger:#dd4b4b;
  --danger-soft:rgba(224,82,82,.13);--ok-soft:rgba(90,200,120,.16);
  --shadow-1:0 2px 6px rgba(20,80,120,.14);--shadow-2:0 18px 44px rgba(20,90,140,.24);
  --scroll:#9fd4f2;
  --glass-hi:rgba(255,255,255,.92);
  --table-head:rgba(226,244,255,.9);
}
[data-theme="dark"]{
  --bg:#0a2438;
  --bg-grad:radial-gradient(1200px 700px at 15% -10%,rgba(90,190,240,.18),transparent 60%),
            radial-gradient(900px 600px at 88% 0%,rgba(140,120,255,.14),transparent 65%),
            radial-gradient(900px 500px at 50% 110%,rgba(60,200,180,.12),transparent 70%),
            linear-gradient(180deg,#0a2539 0%,#0d3049 40%,#10425f 72%,#0d3a56 100%);
  --surface:rgba(15,44,66,.72);--surface-2:rgba(20,52,76,.66);--surface-3:rgba(27,64,90,.6);
  --surface-solid:#0f3048;
  --border:rgba(140,215,255,.16);--border-2:rgba(140,215,255,.32);
  --text:#e8f6ff;--text-2:#a8cade;--text-3:#7195ab;
  --brand:#4fb3e8;--brand-2:#7cd0f5;--brand-soft:rgba(80,190,240,.16);--brand-ring:rgba(110,200,250,.5);
  --on-brand:#04263c;
  --ok:#4ed08a;--warn:#eec258;--danger:#ff7a7a;
  --danger-soft:rgba(255,122,122,.14);--ok-soft:rgba(78,208,138,.16);
  --shadow-1:0 2px 6px rgba(0,0,0,.4);--shadow-2:0 20px 48px rgba(0,0,0,.55);
  --scroll:#2d5e7d;
  --glass-hi:rgba(190,235,255,.35);
  --table-head:rgba(13,52,78,.92);
}

/* ═══ Base ════════════════════════════════════════════════════════════════ */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:15px;-webkit-text-size-adjust:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  background:var(--bg);background-image:var(--bg-grad);background-attachment:fixed;
  color:var(--text);min-height:100vh;display:flex;flex-direction:column;
  -webkit-font-smoothing:antialiased;animation:fade .3s ease;
  transition:background-color .3s ease,color .3s ease;
}
/* 云层光晕 */
body::before{
  content:'';position:fixed;inset:-40px;z-index:-1;pointer-events:none;
  background:
    radial-gradient(240px 90px at 88% 4%,rgba(255,255,236,.8),rgba(255,255,236,0) 70%),
    radial-gradient(300px 90px at 6% 12%,rgba(255,255,255,.55),rgba(255,255,255,0) 72%),
    radial-gradient(340px 110px at 90% 26%,rgba(255,255,255,.4),rgba(255,255,255,0) 74%),
    radial-gradient(240px 80px at 28% 40%,rgba(255,255,255,.3),rgba(255,255,255,0) 76%);
  animation:cloudDrift 120s ease-in-out infinite alternate;
}
/* 循环上升的玻璃泡泡（明/暗自适应） */
.bubbles{position:fixed;inset:0;z-index:-1;overflow:hidden;pointer-events:none}
.bubbles i{
  position:absolute;left:var(--x,50%);bottom:-18vh;width:var(--s,22px);height:var(--s,22px);
  border-radius:50%;opacity:var(--o,.55);will-change:transform;
  background:
    radial-gradient(circle at 32% 26%,rgba(255,255,255,.95) 0 9%,rgba(255,255,255,.18) 40%,rgba(255,255,255,.03) 62%),
    radial-gradient(circle at 50% 50%,rgba(255,255,255,.02) 54%,rgba(255,255,255,.4) 86%,rgba(255,255,255,.78) 100%);
  box-shadow:inset -4px -6px 12px rgba(255,255,255,.45),inset 3px 4px 9px rgba(255,255,255,.35),0 2px 14px rgba(150,215,255,.28);
  animation:bubbleRise var(--d,32s) linear infinite;
  animation-delay:var(--dl,0s);
}
.bubbles i::after{
  content:'';position:absolute;right:20%;bottom:24%;width:24%;height:24%;border-radius:50%;
  background:radial-gradient(circle at 40% 35%,rgba(255,255,255,.85),rgba(255,255,255,0) 74%);
}
.bubbles i:nth-child(1){--x:4%;--s:16px;--d:36s;--dl:-6s;--o:.5}
.bubbles i:nth-child(2){--x:14%;--s:30px;--d:46s;--dl:-30s;--o:.44}
.bubbles i:nth-child(3){--x:24%;--s:12px;--d:30s;--dl:-16s;--o:.52}
.bubbles i:nth-child(4){--x:33%;--s:48px;--d:58s;--dl:-44s;--o:.38}
.bubbles i:nth-child(5){--x:44%;--s:20px;--d:38s;--dl:-10s;--o:.5}
.bubbles i:nth-child(6){--x:53%;--s:10px;--d:28s;--dl:-22s;--o:.55}
.bubbles i:nth-child(7){--x:61%;--s:36px;--d:50s;--dl:-34s;--o:.4}
.bubbles i:nth-child(8){--x:70%;--s:22px;--d:40s;--dl:-2s;--o:.5}
.bubbles i:nth-child(9){--x:78%;--s:14px;--d:32s;--dl:-26s;--o:.5}
.bubbles i:nth-child(10){--x:86%;--s:60px;--d:64s;--dl:-52s;--o:.36}
.bubbles i:nth-child(11){--x:93%;--s:18px;--d:34s;--dl:-14s;--o:.46}
.bubbles i:nth-child(12){--x:49%;--s:26px;--d:44s;--dl:-38s;--o:.4}
[data-theme="dark"] body::before{
  background:
    radial-gradient(300px 120px at 85% 6%,rgba(140,215,255,.14),rgba(140,215,255,0) 70%),
    radial-gradient(340px 120px at 8% 16%,rgba(120,160,255,.12),rgba(120,160,255,0) 72%),
    radial-gradient(300px 100px at 60% 88%,rgba(90,220,190,.08),rgba(90,220,190,0) 74%),
    radial-gradient(260px 100px at 90% 40%,rgba(180,140,255,.08),rgba(180,140,255,0) 74%);
}
[data-theme="dark"] .bubbles i{
  background:
    radial-gradient(circle at 32% 26%,rgba(215,245,255,.95) 0 9%,rgba(190,235,255,.16) 40%,rgba(190,235,255,.03) 62%),
    radial-gradient(circle at 50% 50%,rgba(190,235,255,.02) 54%,rgba(190,235,255,.4) 86%,rgba(190,235,255,.8) 100%);
  box-shadow:inset -4px -6px 12px rgba(190,235,255,.4),inset 3px 4px 9px rgba(190,235,255,.3),0 0 18px rgba(110,205,255,.45);
  filter:drop-shadow(0 0 6px rgba(110,205,255,.3));
}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#cfeeff,var(--scroll));border-radius:99px;border:2px solid rgba(255,255,255,.55);background-clip:content-box}
::-webkit-scrollbar-track{background:transparent}
::selection{background:var(--brand-soft);color:var(--text)}
a{color:inherit}
input,button,textarea,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--brand-ring);outline-offset:2px;border-radius:8px}

@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes rowIn{from{opacity:0;transform:translateY(10px) scale(.995)}to{opacity:1;transform:none}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.45}}
@keyframes backdropIn{from{opacity:0}to{opacity:1}}
@keyframes popIn{from{opacity:0;transform:translateY(10px) scale(.965)}to{opacity:1;transform:none}}
@keyframes toastIn{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
@keyframes barFlow{0%{background-position:0% 50%}100%{background-position:200% 50%}}
@keyframes dropPulse{0%,100%{transform:scale(1);border-color:var(--brand)}50%{transform:scale(1.03);border-color:var(--brand-2)}}
@keyframes badgeIn{from{opacity:0;transform:scale(.85)}to{opacity:1;transform:none}}
@keyframes cloudDrift{from{transform:translate3d(0,0,0)}to{transform:translate3d(-24px,10px,0)}}
@keyframes bubbleRise{
  0%{transform:translate3d(0,0,0)}
  12%{transform:translate3d(10px,-14vh,0)}
  30%{transform:translate3d(-12px,-36vh,0)}
  50%{transform:translate3d(12px,-60vh,0)}
  70%{transform:translate3d(-10px,-84vh,0)}
  88%{transform:translate3d(8px,-106vh,0)}
  100%{transform:translate3d(0,-126vh,0)}
}
@keyframes sheen{from{transform:translateX(-150%) skewX(-18deg)}to{transform:translateX(260%) skewX(-18deg)}}

/* ═══ Top bar ═════════════════════════════════════════════════════════════ */
.topbar{
  position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:14px;
  height:58px;padding:0 18px;
  background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(233,248,255,.62));
  backdrop-filter:saturate(160%) blur(14px);-webkit-backdrop-filter:saturate(160%) blur(14px);
  border-bottom:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.95),0 10px 26px rgba(30,95,145,.16);
}
[data-theme="dark"] .topbar{
  background:linear-gradient(180deg,rgba(24,62,90,.85),rgba(13,44,66,.72));
  border-bottom-color:rgba(140,215,255,.2);
  box-shadow:inset 0 1px 0 rgba(190,235,255,.25),0 12px 30px rgba(0,0,0,.4);
}
.brand{display:flex;align-items:center;gap:9px;flex:0 0 auto;user-select:none}
.brand-logo{
  width:28px;height:28px;border-radius:9px;display:grid;place-items:center;
  background:radial-gradient(120% 120% at 30% 22%,#bfe9ff 0%,#6cc3ee 52%,#2f9bd4 100%);
  border:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 #fff,0 5px 12px rgba(47,155,212,.35);
}
.brand-logo svg{width:15px;height:15px;stroke:#fff;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 1px 1px rgba(10,70,110,.35))}
.brand-text{
  font-size:14px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;
  color:var(--text);
  text-shadow:0 1px 0 rgba(255,255,255,.7);
}
[data-theme="dark"] .brand-text{text-shadow:0 1px 0 rgba(0,0,0,.4)}
.breadcrumb{
  flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:1px;
  overflow-x:auto;scrollbar-width:none;font-size:13px;
}
.breadcrumb::-webkit-scrollbar{display:none}
.bc-root{display:inline-flex;align-items:center}
.bc-root svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.bc-root,.bc-link{
  padding:5px 9px;border-radius:9px;color:var(--text-2);white-space:nowrap;
  cursor:pointer;transition:background .15s,color .15s,box-shadow .15s;
}
.bc-root:hover,.bc-link:hover{
  color:var(--text);background:rgba(255,255,255,.65);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 2px 6px rgba(30,95,145,.14);
}
[data-theme="dark"] .bc-root:hover,[data-theme="dark"] .bc-link:hover{background:rgba(70,140,190,.22)}
.bc-link.current{color:var(--text);font-weight:700;cursor:default}
.bc-link.current:hover{background:transparent;box-shadow:none}
.bc-sep{color:var(--text-3);font-size:11px;padding:0 1px;user-select:none}
.controls{display:flex;align-items:center;gap:7px;flex:0 0 auto}

/* ═══ Buttons ═════════════════════════════════════════════════════════════ */
.ctrl-btn{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:34px;padding:0 12px;border-radius:99px;cursor:pointer;user-select:none;
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(228,244,255,.82));
  border:1px solid rgba(150,205,240,.9);color:#1c6ba0;
  font-size:12.5px;font-weight:700;
  box-shadow:inset 0 1px 0 #fff,0 4px 10px rgba(30,95,145,.16);
  transition:background .16s,border-color .16s,color .16s,transform .16s,box-shadow .16s;
}
[data-theme="dark"] .ctrl-btn{
  background:linear-gradient(180deg,rgba(52,102,138,.85),rgba(24,62,90,.85));
  border-color:rgba(140,215,255,.3);color:#a8dcf5;
  box-shadow:inset 0 1px 0 rgba(190,235,255,.28),0 4px 12px rgba(0,0,0,.35);
}
.ctrl-btn:hover{color:var(--text);transform:translateY(-1px);box-shadow:inset 0 1px 0 #fff,0 7px 16px rgba(30,95,145,.24)}
.ctrl-btn:active{transform:translateY(0) scale(.97)}
.ctrl-btn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.ctrl-btn.icon-only{width:34px;padding:0}
.ctrl-btn.lang-btn{min-width:46px}
.ctrl-btn.admin-btn{color:#b07a10;border-color:rgba(220,170,60,.6);background:linear-gradient(180deg,rgba(255,252,240,.96),rgba(255,244,214,.85))}
.ctrl-btn.admin-btn:hover{color:#8a5f07;border-color:rgba(200,140,30,.75);background:linear-gradient(180deg,#fffdf4,#ffefc9)}
[data-theme="dark"] .ctrl-btn.admin-btn{color:#f0c04a;border-color:rgba(240,192,74,.4);background:linear-gradient(180deg,rgba(112,84,20,.5),rgba(84,60,12,.5))}
.ctrl-btn.on{color:#fff;border-color:transparent;background:linear-gradient(180deg,#9fe0ff,#3aa9de);box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 6px 16px rgba(47,155,212,.4)}
[data-theme="dark"] .ctrl-btn.on{color:#06283e;background:linear-gradient(180deg,#8fd8f5,#3f9ed6)}

/* ═══ Toolbar ═════════════════════════════════════════════════════════════ */
.toolbar{
  display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  padding:10px 18px;
  background:linear-gradient(180deg,rgba(255,255,255,.6),rgba(240,250,255,.4));
  border-bottom:1px solid rgba(255,255,255,.8);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
}
[data-theme="dark"] .toolbar{background:linear-gradient(180deg,rgba(16,50,74,.6),rgba(10,36,54,.45));border-bottom-color:rgba(140,215,255,.14)}
.tool-btn{
  display:inline-flex;align-items:center;gap:7px;
  height:34px;padding:0 13px;border-radius:99px;cursor:pointer;user-select:none;white-space:nowrap;
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(228,244,255,.8));
  border:1px solid rgba(150,205,240,.85);color:#1c6ba0;
  font-size:12.5px;font-weight:700;
  box-shadow:inset 0 1px 0 #fff,0 4px 10px rgba(30,95,145,.14);
  transition:background .16s,border-color .16s,color .16s,transform .16s,box-shadow .16s;
}
[data-theme="dark"] .tool-btn{
  background:linear-gradient(180deg,rgba(50,100,136,.8),rgba(24,62,90,.82));
  border-color:rgba(140,215,255,.28);color:#a8dcf5;
  box-shadow:inset 0 1px 0 rgba(190,235,255,.25),0 4px 12px rgba(0,0,0,.32);
}
.tool-btn:hover{color:var(--text);transform:translateY(-1px);box-shadow:inset 0 1px 0 #fff,0 7px 16px rgba(30,95,145,.22)}
.tool-btn:active{transform:translateY(0) scale(.97)}
.tool-btn svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.tool-btn.primary{
  position:relative;overflow:hidden;
  background:linear-gradient(180deg,#e0f7ff 0%,#a9e1fb 42%,#6dc1ee 58%,#4ba9de 100%);
  border-color:#55aadd;color:#063d61;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.95),inset 0 -8px 12px rgba(30,110,170,.2),0 6px 16px rgba(40,110,160,.3);
  text-shadow:0 1px 0 rgba(255,255,255,.55);
}
.tool-btn.primary::after{
  content:'';position:absolute;top:0;bottom:0;left:0;width:44%;pointer-events:none;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.65),transparent);
  transform:translateX(-150%) skewX(-18deg);
}
.tool-btn.primary:hover{color:#05314f;filter:brightness(1.04)}
.tool-btn.primary:hover::after{animation:sheen .9s ease}
[data-theme="dark"] .tool-btn.primary{background:linear-gradient(180deg,#b8ecff 0%,#66c2ef 48%,#3a9fd8 62%,#2b8ac4 100%);color:#042c44}
.tool-btn.danger:hover{color:var(--danger);border-color:rgba(224,82,82,.55);background:var(--danger-soft)}
.search-box{
  margin-left:auto;height:34px;padding:0 15px;border-radius:99px;width:215px;
  background:linear-gradient(180deg,rgba(255,255,255,.95),rgba(235,248,255,.85));
  border:1px solid rgba(150,205,240,.85);color:var(--text);
  font-size:12.5px;box-shadow:inset 0 2px 4px rgba(30,95,145,.1);
  transition:border-color .16s,box-shadow .16s;
}
[data-theme="dark"] .search-box{background:linear-gradient(180deg,rgba(20,56,82,.9),rgba(13,42,64,.9));border-color:rgba(140,215,255,.26);box-shadow:inset 0 2px 5px rgba(0,0,0,.35)}
.search-box::placeholder{color:var(--text-3)}
.search-box:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--brand-soft)}

/* ═══ Status bar ══════════════════════════════════════════════════════════ */
.statusbar{
  display:flex;align-items:center;gap:16px;padding:7px 18px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;color:var(--text-2);
  background:rgba(255,255,255,.42);border-bottom:1px solid rgba(255,255,255,.7);
}
[data-theme="dark"] .statusbar{background:rgba(12,42,62,.5);border-bottom-color:rgba(140,215,255,.12);color:var(--text-2)}
.statusbar .stat{display:flex;align-items:center;gap:6px}
.statusbar .dot{width:7px;height:7px;border-radius:99px;background:radial-gradient(circle at 32% 28%,#c9f4ff,#3aa9de);box-shadow:0 0 6px rgba(90,190,240,.8),inset 0 1px 0 #fff}

/* ═══ Content / table ═════════════════════════════════════════════════════ */
.content{flex:1 1 auto;display:flex;flex-direction:column;min-width:0}
.file-table{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0}
/* Fixed layout keeps long names ellipsised instead of pushing the actions
   column off-screen on narrow phones. */
.file-col-name{width:auto}
.file-col-size{width:122px}
.file-col-date{width:172px}
.file-table th:last-child,.file-table td:last-child{width:310px}
.file-table thead th{
  position:sticky;top:0;z-index:20;text-align:left;
  padding:11px 18px;font-size:10.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;
  color:var(--text-2);background:var(--table-head);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  border-bottom:1px solid rgba(255,255,255,.75);
  cursor:pointer;user-select:none;white-space:nowrap;transition:color .15s;
}
[data-theme="dark"] .file-table thead th{border-bottom-color:rgba(140,215,255,.16)}
.file-table thead th:hover{color:var(--text)}
.file-table thead th.sorted{color:var(--brand)}
.sort-arrow{margin-left:5px;font-size:9px;opacity:.45}
.file-table thead th.sorted .sort-arrow{opacity:1;color:var(--brand)}
.file-row{
  background:linear-gradient(180deg,rgba(255,255,255,.5),rgba(255,255,255,.32));
  border-bottom:1px solid rgba(255,255,255,.7);
  animation:rowIn .32s cubic-bezier(.2,.75,.2,1) backwards;
  transition:background .16s,box-shadow .18s,transform .18s;
}
.file-row:nth-child(even){background:linear-gradient(180deg,rgba(255,255,255,.4),rgba(255,255,255,.24))}
[data-theme="dark"] .file-row{background:linear-gradient(180deg,rgba(16,52,78,.55),rgba(10,38,58,.45));border-bottom-color:rgba(140,215,255,.14)}
[data-theme="dark"] .file-row:nth-child(even){background:linear-gradient(180deg,rgba(13,46,70,.5),rgba(9,34,52,.42))}
.file-row:hover{
  background:linear-gradient(90deg,rgba(255,255,255,.85),rgba(255,255,255,.55));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.95),inset 0 -1px 0 rgba(255,255,255,.6),0 2px 10px rgba(30,95,145,.12);
  transform:translateX(2px);
}
[data-theme="dark"] .file-row:hover{background:linear-gradient(90deg,rgba(70,150,200,.4),rgba(70,150,200,.2));box-shadow:inset 0 1px 0 rgba(190,235,255,.2)}
.file-row td{padding:9px 18px;vertical-align:middle;overflow:hidden}
.file-name{display:flex;align-items:center;gap:11px;min-width:0}
.file-icon{
  width:30px;height:30px;border-radius:9px;flex:0 0 auto;display:grid;place-items:center;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;font-weight:800;
  color:var(--text-2);
  background:linear-gradient(180deg,rgba(255,255,255,.95),rgba(226,242,252,.85));
  border:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 #fff,0 3px 8px rgba(30,95,145,.15);
  letter-spacing:.02em;
  transition:transform .2s cubic-bezier(.2,.8,.2,1),background .2s,color .2s,border-color .2s,box-shadow .2s;
}
[data-theme="dark"] .file-icon{background:linear-gradient(180deg,rgba(58,108,142,.85),rgba(28,68,96,.85));border-color:rgba(140,215,255,.3);box-shadow:inset 0 1px 0 rgba(190,235,255,.3),0 3px 8px rgba(0,0,0,.3)}
.file-row:hover .file-icon{transform:scale(1.08)}
.file-icon.folder{
  color:#0c5d8c;
  background:linear-gradient(180deg,#e8f9ff 0%,#b9e5fb 46%,#7cc4ec 60%,#57aee0 100%);
  border-color:rgba(255,255,255,.95);
  box-shadow:inset 0 1px 0 #fff,inset 0 -6px 9px rgba(30,110,170,.2),0 4px 10px rgba(47,155,212,.3);
}
[data-theme="dark"] .file-icon.folder{color:#06283e;background:linear-gradient(180deg,#c2ecff 0%,#74c6ef 52%,#3d9ad3 100%);border-color:rgba(190,235,255,.5)}
.file-name-text{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13.5px}
.file-name-link{color:var(--text);text-decoration:none;cursor:pointer;transition:color .15s,text-shadow .15s}
.file-name-link:hover{color:var(--brand-2);text-shadow:0 1px 0 rgba(255,255,255,.6)}
[data-theme="dark"] .file-name-link:hover{color:var(--brand-2);text-shadow:none}
.file-meta{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;color:var(--text-2);white-space:nowrap}
.file-actions{white-space:nowrap;text-align:right}
.file-act-btn{
  display:inline-flex;align-items:center;height:26px;padding:0 10px;margin-left:4px;
  border-radius:99px;cursor:pointer;font-size:11.5px;font-weight:700;
  background:transparent;border:1px solid transparent;color:var(--text-2);
  transition:all .15s;
}
.file-act-btn:hover{
  color:#0c5d8c;background:linear-gradient(180deg,rgba(255,255,255,.95),rgba(228,244,255,.85));
  border-color:rgba(150,205,240,.9);box-shadow:inset 0 1px 0 #fff,0 3px 8px rgba(30,95,145,.15);
}
[data-theme="dark"] .file-act-btn:hover{color:#bfe9ff;background:linear-gradient(180deg,rgba(52,102,138,.8),rgba(24,62,90,.8));border-color:rgba(140,215,255,.3)}
.file-act-btn.del:hover{color:var(--danger);background:var(--danger-soft);border-color:rgba(224,82,82,.5)}

/* ═══ Empty state ═════════════════════════════════════════════════════════ */
.empty-state{flex:1 1 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:72px 24px;text-align:center}
.empty-state-icon{
  width:58px;height:58px;border-radius:19px;display:grid;place-items:center;color:#4c86ab;
  background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(226,242,252,.7));
  border:1px solid rgba(255,255,255,.9);
  box-shadow:inset 0 1px 0 #fff,0 8px 20px rgba(30,95,145,.18);
  animation:floaty 3.6s ease-in-out infinite;
}
[data-theme="dark"] .empty-state-icon{background:linear-gradient(180deg,rgba(50,100,136,.7),rgba(20,56,82,.7));border-color:rgba(140,215,255,.25);color:#8fc4e0;box-shadow:inset 0 1px 0 rgba(190,235,255,.25),0 8px 20px rgba(0,0,0,.35)}
.empty-state-icon svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.empty-state-text{font-size:13.5px;color:var(--text-2)}

/* ═══ Progress ════════════════════════════════════════════════════════════ */
.progress-bar{
  position:fixed;top:0;left:0;height:3px;width:0;z-index:200;
  background:linear-gradient(90deg,#8fe3ff,#3aa9de,#8fe3ff);
  background-size:200% 100%;
  box-shadow:0 0 12px rgba(90,190,240,.85),0 1px 0 rgba(255,255,255,.6);
  transition:width .25s cubic-bezier(.2,.8,.2,1);
  animation:barFlow 1.2s linear infinite;
}

/* ═══ Toasts ══════════════════════════════════════════════════════════════ */
.toast-container{position:fixed;right:18px;bottom:18px;z-index:300;display:flex;flex-direction:column;gap:9px;pointer-events:none}
.toast{
  display:flex;align-items:center;gap:9px;max-width:min(88vw,380px);
  padding:11px 16px;border-radius:99px;font-size:12.5px;font-weight:700;
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(233,248,255,.88));
  border:1px solid rgba(255,255,255,.95);color:var(--text);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  box-shadow:inset 0 1px 0 #fff,var(--shadow-2);
  animation:toastIn .28s cubic-bezier(.2,.85,.2,1) both;
}
[data-theme="dark"] .toast{background:linear-gradient(180deg,rgba(30,72,102,.95),rgba(16,48,70,.95));border-color:rgba(140,215,255,.3)}
.toast-dot{width:8px;height:8px;border-radius:99px;background:radial-gradient(circle at 30% 30%,#c9f4ff,#3aa9de);box-shadow:0 0 8px rgba(90,190,240,.8);flex:0 0 auto}
.toast.error{border-color:rgba(224,82,82,.6)}
.toast.error .toast-dot{background:radial-gradient(circle at 30% 30%,#ffc9c9,var(--danger));box-shadow:0 0 8px rgba(224,82,82,.8)}
.toast.success{border-color:rgba(90,200,120,.65)}
.toast.success .toast-dot{background:radial-gradient(circle at 30% 30%,#d2ffdd,var(--ok));box-shadow:0 0 8px rgba(90,200,120,.8)}

/* ═══ Drop overlay ════════════════════════════════════════════════════════ */
.drop-overlay{
  position:fixed;inset:0;z-index:150;display:none;align-items:center;justify-content:center;
  background:rgba(210,240,255,.55);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
}
[data-theme="dark"] .drop-overlay{background:rgba(6,26,40,.6)}
.drop-overlay.active{display:flex;animation:backdropIn .2s ease both}
.drop-overlay-inner{
  display:flex;flex-direction:column;align-items:center;gap:12px;
  padding:44px 56px;border-radius:26px;border:2px dashed var(--brand);
  background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(224,244,255,.7));
  color:#0c5d8c;box-shadow:inset 0 1px 0 #fff,0 20px 50px rgba(30,95,145,.3);
  animation:dropPulse 1.7s ease-in-out infinite;
}
[data-theme="dark"] .drop-overlay-inner{background:linear-gradient(180deg,rgba(28,70,100,.9),rgba(14,44,66,.9));color:#a8dcf5}
.drop-overlay-icon svg{width:38px;height:38px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.drop-overlay-text{font-size:15px;font-weight:800}

/* ═══ Modals ══════════════════════════════════════════════════════════════ */
.modal-backdrop{
  position:fixed;inset:0;z-index:250;display:none;align-items:center;justify-content:center;padding:18px;
  background:rgba(10,50,80,.35);
  backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px);
}
[data-theme="dark"] .modal-backdrop{background:rgba(0,10,18,.55)}
.modal-backdrop.active{display:flex;animation:backdropIn .18s ease both}
.modal{
  width:100%;max-width:760px;max-height:88vh;display:flex;flex-direction:column;
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(238,250,255,.92));
  border:1px solid rgba(255,255,255,.95);border-radius:24px;
  box-shadow:inset 0 1px 0 #fff,0 30px 70px rgba(20,85,135,.35);
  animation:popIn .26s cubic-bezier(.2,.85,.2,1) both;overflow:hidden;
}
[data-theme="dark"] .modal{background:linear-gradient(180deg,rgba(24,62,90,.97),rgba(12,38,58,.97));border-color:rgba(140,215,255,.3);box-shadow:inset 0 1px 0 rgba(190,235,255,.25),0 30px 70px rgba(0,0,0,.6)}
.modal.sm{max-width:440px}
.modal-header{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:15px 18px;border-bottom:1px solid rgba(255,255,255,.8);
  background:linear-gradient(180deg,rgba(255,255,255,.65),rgba(255,255,255,0));
}
[data-theme="dark"] .modal-header{border-bottom-color:rgba(140,215,255,.16);background:linear-gradient(180deg,rgba(70,140,190,.16),rgba(70,140,190,0))}
.modal-title{display:flex;align-items:center;gap:9px;font-size:14.5px;font-weight:800}
.modal-title .accent{color:var(--brand)}
.modal-close{
  width:30px;height:30px;border-radius:99px;display:grid;place-items:center;cursor:pointer;
  background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(228,244,255,.8));
  border:1px solid rgba(150,205,240,.8);color:var(--text-2);font-size:15px;line-height:1;
  transition:all .15s;
}
[data-theme="dark"] .modal-close{background:linear-gradient(180deg,rgba(52,102,138,.7),rgba(24,62,90,.7));border-color:rgba(140,215,255,.28)}
.modal-close:hover{color:var(--danger);border-color:rgba(224,82,82,.6);transform:rotate(90deg)}
.modal-body{padding:18px;overflow-y:auto;flex:1 1 auto}
.modal-footer{display:flex;justify-content:flex-end;gap:9px;padding:14px 18px;border-top:1px solid rgba(255,255,255,.8);background:linear-gradient(0deg,rgba(255,255,255,.55),rgba(255,255,255,0))}
[data-theme="dark"] .modal-footer{border-top-color:rgba(140,215,255,.16);background:linear-gradient(0deg,rgba(70,140,190,.12),rgba(70,140,190,0))}
.modal textarea{
  width:100%;min-height:340px;padding:14px;border-radius:16px;resize:vertical;
  background:linear-gradient(180deg,rgba(255,255,255,.85),rgba(240,250,255,.8));
  border:1px solid rgba(150,205,240,.7);color:var(--text);
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.65;
  box-shadow:inset 0 2px 5px rgba(30,95,145,.1);
  transition:border-color .16s,box-shadow .16s;
}
[data-theme="dark"] .modal textarea{background:linear-gradient(180deg,rgba(10,34,52,.9),rgba(13,42,62,.9));border-color:rgba(140,215,255,.25);box-shadow:inset 0 2px 6px rgba(0,0,0,.4)}
.modal textarea:focus,.modal input[type=text]:focus,.login-input:focus{
  outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--brand-soft);
}
.modal input[type=text],.login-input{
  width:100%;height:42px;padding:0 15px;border-radius:99px;
  background:linear-gradient(180deg,rgba(255,255,255,.95),rgba(235,248,255,.85));
  border:1px solid rgba(150,205,240,.8);color:var(--text);font-size:14px;
  box-shadow:inset 0 2px 4px rgba(30,95,145,.1);
  transition:border-color .16s,box-shadow .16s;
}
[data-theme="dark"] .modal input[type=text],[data-theme="dark"] .login-input{background:linear-gradient(180deg,rgba(12,40,60,.92),rgba(15,46,68,.92));border-color:rgba(140,215,255,.26);box-shadow:inset 0 2px 5px rgba(0,0,0,.4)}
.modal input::placeholder,.login-input::placeholder{color:var(--text-3)}
.btn{
  height:38px;padding:0 20px;border-radius:99px;cursor:pointer;
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(228,244,255,.82));
  border:1px solid rgba(150,205,240,.85);color:#1c6ba0;
  font-size:13px;font-weight:700;
  box-shadow:inset 0 1px 0 #fff,0 4px 10px rgba(30,95,145,.14);
  transition:transform .16s cubic-bezier(.2,.8,.2,1),background .16s,border-color .16s,color .16s,box-shadow .16s;
}
[data-theme="dark"] .btn{background:linear-gradient(180deg,rgba(50,100,136,.8),rgba(24,62,90,.82));border-color:rgba(140,215,255,.28);color:#a8dcf5;box-shadow:inset 0 1px 0 rgba(190,235,255,.25),0 4px 12px rgba(0,0,0,.32)}
.btn:hover{color:var(--text);transform:translateY(-1px);box-shadow:inset 0 1px 0 #fff,0 7px 16px rgba(30,95,145,.22)}
.btn:active{transform:scale(.965)}
.btn-primary{
  background:linear-gradient(180deg,#e0f7ff 0%,#a9e1fb 42%,#6dc1ee 58%,#4ba9de 100%);
  border-color:#55aadd;color:#063d61;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.95),inset 0 -8px 12px rgba(30,110,170,.2),0 6px 16px rgba(40,110,160,.3);
  text-shadow:0 1px 0 rgba(255,255,255,.5);
}
.btn-primary:hover{color:#05314f;filter:brightness(1.04)}
[data-theme="dark"] .btn-primary{background:linear-gradient(180deg,#b8ecff 0%,#66c2ef 48%,#3a9fd8 62%,#2b8ac4 100%);color:#042c44}
.btn-danger{
  background:linear-gradient(180deg,#ffd9d9 0%,#ff9d9d 44%,#ef6a6a 58%,#d94f4f 100%);
  border-color:#d95353;color:#5c0d0d;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.9),inset 0 -8px 12px rgba(150,30,30,.25),0 6px 16px rgba(200,70,70,.3);
  text-shadow:0 1px 0 rgba(255,255,255,.4);
}
.btn-danger:hover{color:#4a0808;filter:brightness(1.04)}
[data-theme="dark"] .btn-danger{background:linear-gradient(180deg,#ffbdbd 0%,#ef8080 48%,#d95f5f 62%,#c04a4a 100%);color:#3d0505}
.btn-ghost{background:transparent;box-shadow:none}
.btn-ghost:hover{background:rgba(255,255,255,.6)}
.login-error{min-height:18px;margin-top:8px;font-size:12px;color:var(--danger);font-weight:600}

/* ═══ Badge ═══════════════════════════════════════════════════════════════ */
.admin-badge{
  display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:99px;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10px;font-weight:800;
  letter-spacing:.06em;text-transform:uppercase;
  color:#8a5f07;background:linear-gradient(180deg,#fff6d8,#ffe9a8);
  border:1px solid rgba(210,160,50,.6);box-shadow:inset 0 1px 0 #fff;
  animation:badgeIn .25s cubic-bezier(.2,.85,.2,1) both;
}
[data-theme="dark"] .admin-badge{color:#f0c04a;background:linear-gradient(180deg,rgba(112,84,20,.6),rgba(84,60,12,.6));border-color:rgba(240,192,74,.45);box-shadow:inset 0 1px 0 rgba(255,230,150,.3)}

/* ═══ Footer ══════════════════════════════════════════════════════════════ */
.footer{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:9px 18px;border-top:1px solid rgba(255,255,255,.8);
  background:rgba(255,255,255,.45);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;color:var(--text-2);
}
[data-theme="dark"] .footer{background:rgba(12,42,62,.5);border-top-color:rgba(140,215,255,.12)}
.footer-id{display:flex;align-items:center;gap:6px}
.footer-id span:last-child{color:var(--text)}

/* ═══ Loading skeleton ════════════════════════════════════════════════════ */
.loading .file-row{
  background:linear-gradient(90deg,var(--surface) 25%,var(--surface-2) 50%,var(--surface) 75%);
  background-size:200% 100%;animation:shimmer 1.4s infinite;height:48px;border:0;
}

/* ═══ Responsive ══════════════════════════════════════════════════════════ */
@media(max-width:760px){
  .topbar{height:52px;padding:0 12px;gap:10px}
  .brand-text{display:none}
  .toolbar{padding:8px 12px;gap:6px}
  .tool-btn{padding:0 10px;font-size:12px}
  .tool-btn .lbl{display:none}
  .tool-btn.primary .lbl{display:inline}
  .search-box{margin-left:0;width:100%;order:99}
  .file-table thead th{padding:9px 12px}
  .file-row td{padding:8px 12px}
  /* Phones: turn each row into "name on line 1, actions on line 2" instead of
     squeezing four buttons into a narrow column. */
  .file-table,.file-table thead,.file-table tbody{display:block}
  .file-table{table-layout:auto}
  .file-table thead tr{display:flex}
  .file-table thead th{display:block;flex:1}
  .file-table thead th.file-col-size,
  .file-table thead th.file-col-date,
  .file-table thead th:last-child{display:none}
  .file-row{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:11px 14px}
  .file-row td{display:block;padding:0;border:0;overflow:visible;width:auto}
  .file-row td.file-name{display:flex;align-items:center;gap:10px;flex:1 1 auto;min-width:0}
  .file-col-size,.file-col-date{flex:0 0 auto}
  .file-row td.file-actions{display:flex;justify-content:flex-end;gap:3px;flex:1 1 100%;white-space:nowrap}
  .file-act-btn{margin-left:0}
  .file-icon{width:27px;height:27px;border-radius:8px;font-size:9.5px}
  .file-name-text{font-size:13px}
  .file-act-btn{padding:0 7px;font-size:11px}
  .statusbar{padding:6px 12px;font-size:10px;gap:12px}
  .footer{flex-direction:column;gap:3px;text-align:center}
  .toast-container{right:12px;left:12px;bottom:12px}
  .toast{max-width:none}
}

/* ═══ Motion safety ═══════════════════════════════════════════════════════
   Respect the OS "reduce motion" setting: keep the UI fully usable, just
   without the decorative movement. */
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{
    animation-duration:.001ms !important;
    animation-iteration-count:1 !important;
    transition-duration:.001ms !important;
    scroll-behavior:auto !important;
  }
  .empty-state-icon{animation:none !important}
  body::before,body::after{animation:none !important}
  .bubbles{display:none !important}
}
</style>
<script>
/* Apply the saved theme before first paint so light/dark never flashes. */
try {
  var _t = localStorage.getItem('fb_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', _t);
} catch (e) {}
</script>
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#9fdcf9">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d3049">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs><linearGradient id='a' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='%239fe0ff'/><stop offset='1' stop-color='%232f9bd4'/></linearGradient></defs><rect width='64' height='64' rx='15' fill='url(%23a)'/><rect x='5' y='5' width='54' height='26' rx='12' fill='%23fff' opacity='.3'/><path d='M10 22a5 5 0 0 1 5-5h11l4.5 4.5H49a5 5 0 0 1 5 5V47a5 5 0 0 1-5 5H15a5 5 0 0 1-5-5z' fill='%23fff' opacity='.95'/><path d='M10 30h44' stroke='%23bfe9ff' stroke-width='3'/></svg>">
</head>
<body>
<div class="bubbles" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
<div class="progress-bar" id="progress"></div>

<div class="drop-overlay" id="dropOverlay">
  <div class="drop-overlay-inner">
    <div class="drop-overlay-icon">
      <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/></svg>
    </div>
    <div class="drop-overlay-text" data-i18n="dropFiles">Drop files to upload</div>
  </div>
</div>

<div class="toast-container" id="toastContainer"></div>

<header class="topbar">
  <div class="brand">
    <span class="brand-logo">
      <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
    </span>
    <span class="brand-text">FileBase</span>
  </div>
  <nav class="breadcrumb" id="breadcrumb"></nav>
  <div class="controls">
    <button class="ctrl-btn admin-btn" id="adminBtn" style="display:none" onclick="App.showLogin()" data-i18n="adminLogin">Admin</button>
    <button class="ctrl-btn icon-only" id="themeToggle" title="Toggle theme" aria-label="Toggle theme">
      <span id="themeIcon" class="theme-icon">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      </span>
    </button>
    <button class="ctrl-btn lang-btn" id="langToggle" aria-label="Switch language">EN</button>
  </div>
</header>

<section class="toolbar">
  <button class="tool-btn" onclick="App.goUp()" title="Up">
    <svg viewBox="0 0 24 24"><path d="M12 19V5m0 0-6 6m6-6 6 6"/></svg>
    <span class="lbl" data-i18n="up">Up</span>
  </button>
  <button class="tool-btn" onclick="App.refresh()" title="Refresh">
    <svg viewBox="0 0 24 24"><path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 4v6h-6"/></svg>
    <span class="lbl" data-i18n="refresh">Refresh</span>
  </button>
  <button class="tool-btn primary" onclick="document.getElementById('fileInput').click()" title="Upload">
    <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
    <span class="lbl" data-i18n="upload">Upload</span>
  </button>
  <input type="file" id="fileInput" multiple style="position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden">
  <button class="tool-btn" onclick="App.newFolderModal()" title="New folder">
    <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11.5v5M9.5 14h5"/></svg>
    <span class="lbl" data-i18n="newFolder">Folder</span>
  </button>
  <button class="tool-btn" onclick="App.newFileModal()" title="New file">
    <svg viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12.5v5M9.5 15h5"/></svg>
    <span class="lbl" data-i18n="newFile">File</span>
  </button>
  <input type="text" class="search-box" id="searchBox" data-i18n-placeholder="search" placeholder="Filter...">
</section>

<div class="statusbar" id="statusbar">
  <div class="stat"><div class="dot"></div><span id="statusCount">0 items</span></div>
  <div class="stat" id="statusFolders"></div>
  <div class="stat" id="statusFiles"></div>
</div>

<main class="content">
  <table class="file-table">
    <thead>
      <tr>
        <th class="file-col-name" onclick="App.sort(0)"><span data-i18n="name">Name</span><span class="sort-arrow">&#9652;</span></th>
        <th class="file-col-size" onclick="App.sort(1)"><span data-i18n="size">Size</span><span class="sort-arrow">&#9652;</span></th>
        <th class="file-col-date" onclick="App.sort(2)"><span data-i18n="modified">Modified</span><span class="sort-arrow">&#9652;</span></th>
        <th style="text-align:right"><span data-i18n="actions">Actions</span></th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty-state" id="emptyState" style="display:none">
    <div class="empty-state-icon">
      <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
    </div>
    <div class="empty-state-text" data-i18n="emptyDir">Empty directory</div>
  </div>
</main>

<div class="modal-backdrop" id="editBackdrop" onclick="if(event.target===this)App.closeEdit()">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-title"><span class="accent">&#9998;</span> <span id="editTitle">Edit File</span></div>
      <button class="modal-close" onclick="App.closeEdit()" aria-label="Close">&times;</button>
    </div>
    <div class="modal-body"><textarea id="editContent" spellcheck="false"></textarea></div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeEdit()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" onclick="App.saveEdit()" data-i18n="save">Save</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="nameBackdrop" onclick="if(event.target===this)App.closeNameModal()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title"><span class="accent" id="nameIcon">&#9654;</span> <span id="nameTitle">New Folder</span></div>
      <button class="modal-close" onclick="App.closeNameModal()" aria-label="Close">&times;</button>
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

<div class="modal-backdrop" id="delBackdrop" onclick="if(event.target===this)App.closeDelModal()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title" style="color:var(--danger)"><span>&#9888;</span> <span data-i18n="deleteConfirm">Confirm Delete</span></div>
      <button class="modal-close" onclick="App.closeDelModal()" aria-label="Close">&times;</button>
    </div>
    <div class="modal-body"><p style="font-size:13px;color:var(--text-2)" id="delMsg">Delete this item?</p></div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeDelModal()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-danger" onclick="App.confirmDel()" data-i18n="delete">Delete</button>
    </div>
  </div>
</div>

<div class="modal-backdrop" id="loginBackdrop" onclick="if(event.target===this)App.closeLogin()">
  <div class="modal sm">
    <div class="modal-header">
      <div class="modal-title"><span style="color:var(--brand)">&#128274;</span> <span data-i18n="adminLogin">Admin Login</span></div>
      <button class="modal-close" onclick="App.closeLogin()" aria-label="Close">&times;</button>
    </div>
    <div class="modal-body">
      <input type="text" id="loginUser" class="login-input" placeholder="Username" data-i18n-placeholder="username" style="margin-bottom:10px">
      <input type="password" id="loginPass" class="login-input" placeholder="Password" data-i18n-placeholder="password">
      <div class="login-error" id="loginError"></div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="App.closeLogin()" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" onclick="App.doLogin()" data-i18n="login">Login</button>
    </div>
  </div>
</div>

<footer class="footer">
  <div class="footer-id"><span>ID</span><span id="footerUid">&mdash;</span></div>
  <div><span data-i18n="serving">Serving</span>: <span id="footerRoot">/sdcard</span> &middot; <span id="footerPort">:6532</span></div>
</footer>
<script>
/* ═══════════════════════════════════════════════════
   FILEBASE — Android File Manager Frontend
   ═══════════════════════════════════════════════════ */
var App = (() => {

// ─── i18n ─────────────────────────────────────────
const L = {
  en: {
    title:"FILEBASE", up:"Up", refresh:"Refresh", upload:"Upload",
    newFolder:"Folder", newFile:"File", search:"Filter...",
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
    renameTitle:"Rename", downloadLabel:"Download", loadFailed:"Failed to load directory",
    actionFailed:"Action failed", invalidName:"Invalid name",
    unsaved:"Unsaved changes", unsavedMsg:"Discard unsaved changes?",
    keepEditing:"Keep editing", discard:"Discard",
    alreadyExists:"A file or folder with that name already exists",
  },
  zh: {
    title:"文件管理器", up:"返回", refresh:"刷新", upload:"上传",
    newFolder:"新建文件夹", newFile:"新建文件", search:"搜索...",
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
let loadSeq = 0;   // navigation counter: stale directory responses are dropped
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
  const seq = ++loadSeq;
  showProgress(30);
  try {
    const data = await api('/list?path=' + encodeURIComponent(path));
    if (seq !== loadSeq) return;   // a newer navigation superseded this request
    currentData = data.entries || [];
    renderTable();
    renderBreadcrumb();
    updateStatus();
    showProgress(100);
    setTimeout(() => showProgress(0), 300);
  } catch(e) {
    if (seq !== loadSeq) return;
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
    // Root crumb: an inline SVG (the old "&#8962;" glyph is font-dependent and
    // rendered as a missing-glyph box on some WebViews).
    const rootIcon = '<svg viewBox="0 0 24 24"><path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M6 9.5V20h12V9.5"/></svg>';
    let html = '<span class="bc-root" data-nav="/">' + (isAdmin ? '/' : rootIcon) + '</span>';
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
  updateStatus();   // keep the status counts in sync with the active filter

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
    // Directories get empty size/date cells: a literal dash looked like stray
    // clutter once the mobile layout shows those cells inline.
    const sizeStr = e.isdir ? '' : fmtSize(e.size);
    const mtimeStr = e.isdir ? '' : fmtDate(e.mtime);
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

    return '<tr class="file-row" style="animation-delay:' + (Math.min(i, 24) * 14) + 'ms">' +
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
