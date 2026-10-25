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
import gzip
import hashlib
import mmap
import tempfile

HOST = os.environ.get("BIND_IP", "0.0.0.0")
PORT = 6532
ROOT = "/sdcard"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info")  # off / error / info / debug
# Log levels: off=nothing, error=4xx/5xx only, info=requests+status, debug=all+timing

ADMIN_USER = "admin"
ADMIN_PASS = "hotsteel"
ADMIN_TOKENS = {}  # token -> expiry epoch (in-memory session store)
ADMIN_TOKEN_TTL = 12 * 3600  # 12 hours

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
<meta name="theme-color" content="#070912" id="themeColor">
<style>
/* ══════════════════════════════════════════════════════════════════════════
   FileBase — Material Design 3 Expressive × Liquid Glass
   Two layers: (1) liquid-glass surfaces with dual specular rims and depth,
   (2) M3 Expressive shape/motion/type: squircle-to-pill morphing, tonal
       palettes, and spatial spring physics.
   Performance rules baked in: no backdrop-filter over scrolling content,
   transform/opacity-only animation, virtualised rows, no per-row shadows.
   ══════════════════════════════════════════════════════════════════════════ */

/* ─── Tokens ─────────────────────────────────────────────────────────────── */
[data-theme="light"]{
  --bg:#eef1fc;
  --bg-grad:
    radial-gradient(120% 82% at 50% -18%,#ffffff 0%,#f2f0ff 38%,#e5ebff 68%,#ebf8f5 100%);
  --orb-1:rgba(98,114,255,.35);
  --orb-2:rgba(36,214,186,.27);
  --orb-3:rgba(255,118,136,.23);
  --g1:rgba(255,255,255,.78);
  --g2:rgba(255,255,255,.48);
  --g-solid:rgba(255,255,255,.78);
  --g-solid-2:rgba(255,255,255,.56);
  --stroke:rgba(22,28,72,.09);
  --stroke-2:rgba(22,28,72,.18);
  --hi:rgba(255,255,255,.96);
  --lo:rgba(22,28,72,.05);
  --txt:#121631;
  --txt-2:#464e70;
  --txt-3:#757e9f;
  --primary:#4854dc;
  --primary-2:#7562ff;
  --on-primary:#ffffff;
  --primary-soft:rgba(72,84,220,.12);
  --secondary:#088875;
  --secondary-soft:rgba(8,136,117,.12);
  --tertiary:#d43f5d;
  --tertiary-soft:rgba(212,63,93,.12);
  --accent:#5f7a00;
  --ok:#0b8a54;
  --warn:#a86c00;
  --danger:#cc3131;
  --danger-soft:rgba(204,49,49,.12);
  --ok-soft:rgba(11,138,84,.12);
  --shadow:0 28px 68px -28px rgba(34,42,110,.34),0 10px 24px -14px rgba(34,42,110,.16);
  --shadow-sm:0 10px 26px -14px rgba(34,42,110,.36);
  --scrim:rgba(20,26,64,.32);
  --code-bg:rgba(14,19,44,.94);
  --code-txt:#dee6ff;
  --code-dim:#8b96c4;
  --table-head:rgba(255,255,255,.62);
  --hl:rgba(72,84,220,.075);
  --icon-folder-1:#8290ff; --icon-folder-2:#4c58e2;
  --icon-image-1:#ff96aa; --icon-image-2:#dc4362;
  --icon-video-1:#b894ff; --icon-video-2:#7747e6;
  --icon-audio-1:#4ae3c5; --icon-audio-2:#0e9e88;
  --icon-code-1:#7eb2ff; --icon-code-2:#3566e2;
  --icon-arch-1:#ffc876; --icon-arch-2:#d98218;
  --icon-doc-1:#9fb0d8; --icon-doc-2:#6c82b5;
  --icon-apk-1:#8be086; --icon-apk-2:#369e42;
  --icon-pdf-1:#ff8a8a; --icon-pdf-2:#d64040;
}
[data-theme="dark"]{
  --bg:#060814;
  --bg-grad:
    radial-gradient(125% 92% at 50% -24%,#161d42 0%,#0b1026 46%,#060814 100%);
  --orb-1:rgba(100,116,255,.48);
  --orb-2:rgba(42,216,186,.30);
  --orb-3:rgba(255,102,124,.24);
  --g1:rgba(255,255,255,.095);
  --g2:rgba(255,255,255,.034);
  --g-solid:rgba(16,21,46,.72);
  --g-solid-2:rgba(255,255,255,.052);
  --stroke:rgba(255,255,255,.11);
  --stroke-2:rgba(255,255,255,.22);
  --hi:rgba(255,255,255,.30);
  --lo:rgba(0,0,0,.32);
  --txt:#f0f3ff;
  --txt-2:#acb4d6;
  --txt-3:#7680aa;
  --primary:#acb5ff;
  --primary-2:#8e79ff;
  --on-primary:#090d2a;
  --primary-soft:rgba(154,166,255,.15);
  --secondary:#52e8c6;
  --secondary-soft:rgba(82,232,198,.14);
  --tertiary:#ff94aa;
  --tertiary-soft:rgba(255,148,170,.14);
  --accent:#d8f26a;
  --ok:#52e3a2;
  --warn:#f7ca68;
  --danger:#ff8a8a;
  --danger-soft:rgba(255,120,120,.15);
  --ok-soft:rgba(82,227,162,.14);
  --shadow:0 34px 80px -32px rgba(0,0,0,.92),0 14px 32px -18px rgba(0,0,0,.72);
  --shadow-sm:0 12px 30px -16px rgba(0,0,0,.86);
  --scrim:rgba(3,5,14,.66);
  --code-bg:rgba(5,8,20,.88);
  --code-txt:#dee6ff;
  --code-dim:#7b86b2;
  --table-head:rgba(12,16,36,.76);
  --hl:rgba(172,181,255,.095);
  --icon-folder-1:#9ca8ff; --icon-folder-2:#5864e8;
  --icon-image-1:#ff9eb0; --icon-image-2:#e04868;
  --icon-video-1:#c09eff; --icon-video-2:#7d4ee8;
  --icon-audio-1:#64edd0; --icon-audio-2:#12a28c;
  --icon-code-1:#8cb6ff; --icon-code-2:#3b6ae2;
  --icon-arch-1:#ffd285; --icon-arch-2:#da8820;
  --icon-doc-1:#b3c2e6; --icon-doc-2:#6d81ad;
  --icon-apk-1:#9cea96; --icon-apk-2:#379b44;
  --icon-pdf-1:#ff9d9d; --icon-pdf-2:#d34444;
}

/* ─── Base & Physics ─────────────────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:15px;-webkit-text-size-adjust:100%;color-scheme:dark}
[data-theme="light"]{color-scheme:light}
:root{--row-h:56px;--radius:28px;--ease-spring:cubic-bezier(.22,1.35,.32,1);--ease-out:cubic-bezier(.2,.85,.2,1)}
body{
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  color:var(--txt);background:var(--bg);background-image:var(--bg-grad);
  height:100vh;height:100dvh;overflow:hidden;display:flex;flex-direction:column;
  -webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent;
  transition:background-color .3s ease,color .3s ease;
}
button,input,textarea,select{font:inherit;color:inherit}
button{border:0;background:none;cursor:pointer}
a{color:inherit;text-decoration:none}
::selection{background:var(--primary-soft);color:var(--txt)}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px;border-radius:12px}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--primary) 45%,transparent);border-radius:99px;border:3px solid transparent;background-clip:content-box}
::-webkit-scrollbar-track{background:transparent}

/* ─── Ambient Liquid Mesh ────────────────────────────────────────────────── */
.bg{position:fixed;inset:0;z-index:-2;overflow:hidden;pointer-events:none}
.bg i{position:absolute;display:block;width:72vmax;height:72vmax;border-radius:50%;opacity:.92;will-change:transform}
.bg i:nth-child(1){top:-38vmax;left:-24vmax;background:radial-gradient(circle at 50% 50%,var(--orb-1),transparent 66%);animation:orbA 34s ease-in-out infinite alternate}
.bg i:nth-child(2){bottom:-42vmax;right:-26vmax;background:radial-gradient(circle at 50% 50%,var(--orb-2),transparent 66%);animation:orbB 42s ease-in-out infinite alternate}
.bg i:nth-child(3){top:24%;right:-34vmax;width:54vmax;height:54vmax;background:radial-gradient(circle at 50% 50%,var(--orb-3),transparent 68%);animation:orbA 50s ease-in-out infinite alternate-reverse}
.noise{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.045;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size:160px 160px}
@keyframes orbA{from{transform:translate3d(0,0,0) scale(1)}to{transform:translate3d(6vmax,4vmax,0) scale(1.08)}}
@keyframes orbB{from{transform:translate3d(0,0,0) scale(1.05)}to{transform:translate3d(-5vmax,-3vmax,0) scale(1)}}

/* ─── Glass surface ──────────────────────────────────────────────────────── */
.glass{
  background:linear-gradient(156deg,var(--g1),var(--g2));
  border:1px solid var(--stroke);
  box-shadow:var(--shadow),inset 0 1.5px 0 var(--hi),inset 0 -1px 0 var(--lo);
}
.glass-blur{
  backdrop-filter:blur(24px) saturate(190%);
  -webkit-backdrop-filter:blur(24px) saturate(190%);
}
@supports not ((backdrop-filter:blur(2px)) or (-webkit-backdrop-filter:blur(2px))){
  .glass-blur{background:var(--g-solid)}
}

/* ─── Motion ─────────────────────────────────────────────────────────────── */
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes popIn{from{opacity:0;transform:translateY(14px) scale(.96)}to{opacity:1;transform:none}}
@keyframes sheetIn{from{opacity:0;transform:translateY(40px)}to{opacity:1;transform:none}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes shimmer{0%{background-position:-180% 0}100%{background-position:180% 0}}
@keyframes pulseDot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.45;transform:scale(.82)}}
@keyframes floaty{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}

/* ─── App bar (Liquid Glass) ─────────────────────────────────────────────── */
.appbar{
  position:relative;z-index:40;flex:0 0 auto;
  display:flex;align-items:center;gap:12px;
  height:64px;padding:0 16px;
  background:linear-gradient(180deg,var(--g1),var(--g2));
  backdrop-filter:blur(26px) saturate(195%);
  -webkit-backdrop-filter:blur(26px) saturate(195%);
  border-bottom:1px solid var(--stroke);
  box-shadow:0 14px 34px -24px rgba(0,0,0,.65),inset 0 1.5px 0 var(--hi);
}
.brand{display:flex;align-items:center;gap:10px;flex:0 0 auto;cursor:pointer;border-radius:16px;padding:4px 8px 4px 4px;transition:background .2s,transform .22s var(--ease-spring)}
.brand:hover{background:var(--hl);transform:scale(1.02)}
.brand-logo{
  width:38px;height:38px;border-radius:14px;display:grid;place-items:center;flex:none;
  background:linear-gradient(145deg,var(--icon-folder-1),var(--icon-folder-2));
  box-shadow:0 8px 18px -8px var(--icon-folder-2),inset 0 1.5px 0 rgba(255,255,255,.78),inset 0 -2px 5px rgba(0,0,0,.18);
}
.brand-logo svg{width:19px;height:19px;stroke:#fff;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 1px 1px rgba(0,0,0,.25))}
.brand-text{font-size:15.5px;font-weight:850;letter-spacing:-.015em;white-space:nowrap}
.brand-text small{display:block;font-size:10px;font-weight:750;color:var(--txt-3);letter-spacing:.08em;text-transform:uppercase}

.crumbs{flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:2px;overflow-x:auto;scrollbar-width:none;
  -webkit-overflow-scrolling:touch;touch-action:pan-x;
  padding:4px;border-radius:16px;background:var(--g-solid-2);border:1px solid var(--stroke);box-shadow:inset 0 1px 0 var(--hi)}
.crumbs::-webkit-scrollbar{display:none}
.crumb{
  display:inline-flex;align-items:center;gap:6px;flex:none;height:30px;padding:0 12px;border-radius:999px;
  font-size:12.5px;font-weight:700;color:var(--txt-2);white-space:nowrap;
  transition:background .16s,color .16s,transform .18s var(--ease-spring);
}
.crumb:hover{color:var(--txt);background:var(--hl)}
.crumb.current{color:var(--txt);font-weight:800;background:var(--primary-soft)}
.crumb svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.crumb-sep{color:var(--txt-3);font-size:10px;opacity:.7;flex:none;user-select:none}

.actions{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.icon-btn{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  height:38px;min-width:38px;padding:0 10px;border-radius:14px;
  font-size:12.5px;font-weight:780;color:var(--txt-2);
  background:var(--g-solid-2);border:1px solid var(--stroke);
  box-shadow:inset 0 1px 0 var(--hi);
  transition:transform .22s var(--ease-spring),border-radius .22s,background .18s,color .18s,border-color .18s;
}
.icon-btn:hover{color:var(--txt);background:var(--hl);border-color:var(--stroke-2);border-radius:20px;transform:translateY(-1.5px)}
.icon-btn:active{transform:scale(.93)}
.icon-btn svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.icon-btn.admin{color:var(--secondary);border-color:color-mix(in srgb,var(--secondary) 32%,transparent);background:color-mix(in srgb,var(--secondary) 10%,transparent)}
.icon-btn.admin.on{color:var(--on-primary);background:linear-gradient(145deg,var(--primary-2),var(--primary));border-color:transparent;box-shadow:0 8px 18px -10px var(--primary),inset 0 1px 0 rgba(255,255,255,.4)}
.icon-btn .lbl{font-size:12px}
.icon-btn.lang{min-width:44px;padding:0 9px;letter-spacing:.02em}

/* ─── Toolbar ────────────────────────────────────────────────────────────── */
.toolbar{
  position:relative;z-index:30;flex:0 0 auto;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap;
  padding:11px 16px 9px;
}
.toolbar .sep{width:1px;height:24px;background:var(--stroke);flex:none;margin:0 2px}
.tool{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  height:40px;padding:0 15px;border-radius:14px;white-space:nowrap;
  font-size:12.5px;font-weight:780;color:var(--txt-2);
  background:linear-gradient(160deg,var(--g1),var(--g2));
  border:1px solid var(--stroke);
  box-shadow:var(--shadow-sm),inset 0 1.5px 0 var(--hi);
  transition:transform .22s var(--ease-spring),border-radius .22s,color .18s,background .18s,border-color .18s;
}
.tool:hover{color:var(--txt);border-color:var(--stroke-2);border-radius:20px;transform:translateY(-1.5px)}
.tool:active{transform:scale(.95);border-radius:12px}
.tool svg{width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.tool-accent{
  color:var(--on-primary);border-color:transparent;
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  box-shadow:0 12px 26px -12px var(--primary),inset 0 1.5px 0 rgba(255,255,255,.45),inset 0 -2px 6px rgba(0,0,0,.14);
}
.tool-accent:hover{color:var(--on-primary);filter:brightness(1.06)}

/* Segmented View Mode Switcher (List / Grid) */
.view-seg{
  display:inline-flex;padding:3px;border-radius:14px;
  background:var(--g-solid-2);border:1px solid var(--stroke);
  box-shadow:inset 0 1px 0 var(--hi);
}
.view-seg button{
  width:34px;height:32px;border-radius:11px;display:grid;place-items:center;
  color:var(--txt-3);transition:background .2s,color .2s,transform .2s var(--ease-spring),border-radius .2s;
}
.view-seg button:hover{color:var(--txt)}
.view-seg button.active{
  color:var(--on-primary);border-radius:999px;
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  box-shadow:0 6px 14px -6px var(--primary),inset 0 1px 0 rgba(255,255,255,.4);
}
.view-seg svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}

.upload-split{position:relative;display:flex;align-items:center}
.sort-wrap{position:relative;display:flex;align-items:center}
.sort-arrow-ind{margin-left:auto;font-size:10px;color:var(--primary);opacity:0;transition:opacity .15s}
.menu button.active .sort-arrow-ind{opacity:1}
.menu button.active{color:var(--primary);background:var(--primary-soft)}
.upload-split .caret{width:30px;padding:0;margin-left:-1px;border-radius:0 14px 14px 0}
.upload-split .btn-upload{border-radius:14px 0 0 14px}
.menu{
  position:absolute;top:calc(100% + 8px);left:0;z-index:90;min-width:210px;
  display:none;flex-direction:column;gap:2px;padding:7px;
  border-radius:20px;background:var(--g-solid);border:1px solid var(--stroke-2);
  box-shadow:0 26px 60px -22px rgba(0,0,0,.7),inset 0 1.5px 0 var(--hi);
  backdrop-filter:blur(24px) saturate(185%);-webkit-backdrop-filter:blur(24px) saturate(185%);
}
.menu.open{display:flex;animation:popIn .22s var(--ease-spring) both}
.menu button{
  display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border-radius:13px;
  font-size:13px;font-weight:700;color:var(--txt);text-align:left;transition:background .14s;
}
.menu button:hover{background:var(--hl)}
.menu svg{width:17px;height:17px;stroke:var(--primary);fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}

.search{
  margin-left:auto;display:flex;align-items:center;gap:8px;height:40px;padding:0 13px;
  border-radius:15px;width:min(280px,100%);
  background:var(--g-solid-2);border:1px solid var(--stroke);
  box-shadow:inset 0 1px 0 var(--hi);
  transition:border-color .18s,box-shadow .18s,background .18s,border-radius .2s;
}
.search:focus-within{border-color:var(--primary);border-radius:20px;box-shadow:0 0 0 3px var(--primary-soft);background:var(--g1)}
.search svg{width:16px;height:16px;stroke:var(--txt-3);fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round;flex:none}
.search input{flex:1;min-width:0;height:100%;background:none;border:0;outline:none;font-size:13px}
.search input::placeholder{color:var(--txt-3)}
.search .kbd{font-family:ui-monospace,Menlo,monospace;font-size:10px;color:var(--txt-3);border:1px solid var(--stroke);border-radius:6px;padding:1px 5px;flex:none}
.search-clear{display:none;width:20px;height:20px;border-radius:99px;background:var(--hl);color:var(--txt-2);font-size:13px;line-height:1;flex:none;place-items:center}
.search.has-value .search-clear{display:grid}
.search.has-value .kbd{display:none}

/* Quick Access & Category Filter Chips */
.chips-row{display:flex;align-items:center;gap:10px;padding:0 16px 10px;overflow-x:auto;scrollbar-width:none;flex:0 0 auto;-webkit-overflow-scrolling:touch;touch-action:pan-x}
.chips-row::-webkit-scrollbar{display:none}
.chips{display:flex;align-items:center;gap:6px;flex:none}
.chips:empty{display:none}
.chips-divider{width:1px;height:18px;background:var(--stroke-2);flex:none}
.chip{
  display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 12px;border-radius:999px;flex:none;
  font-size:11.5px;font-weight:750;color:var(--txt-2);background:var(--g-solid-2);
  border:1px solid var(--stroke);box-shadow:inset 0 1px 0 var(--hi);
  transition:background .16s,color .16s,border-color .16s,transform .18s var(--ease-spring);
}
.chip svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.chip:hover{color:var(--txt);border-color:var(--stroke-2);transform:translateY(-1px)}
.chip.active{color:var(--on-primary);background:linear-gradient(145deg,var(--primary-2),var(--primary));border-color:transparent;box-shadow:0 6px 14px -6px var(--primary)}
.chip.cat.active{color:var(--on-primary);background:linear-gradient(145deg,var(--secondary),#0a9680)}

/* ─── File list & Grid View ──────────────────────────────────────────────── */
.list-card{
  position:relative;z-index:10;flex:1 1 auto;min-height:0;margin:0 16px;
  display:flex;flex-direction:column;
  border-radius:var(--radius);overflow:hidden;
  background:var(--g-solid);border:1px solid var(--stroke);
  box-shadow:var(--shadow),inset 0 1.5px 0 var(--hi),inset 0 -1px 0 var(--lo);
}
.list-head{
  flex:0 0 auto;display:grid;grid-template-columns:minmax(0,1fr) 112px 158px 148px;
  gap:8px;align-items:center;height:44px;padding:0 16px;
  background:var(--table-head);border-bottom:1px solid var(--stroke);
  font-size:10.5px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--txt-3);
  user-select:none;
}
.head-name-wrap{display:flex;align-items:center;gap:10px;height:100%}
.head-pick{
  width:20px;height:20px;border-radius:6px;display:grid;place-items:center;flex:none;
  border:1.5px solid var(--stroke-2);background:var(--g-solid-2);color:transparent;
  transition:background .16s,border-color .16s,color .16s,transform .18s var(--ease-spring);
}
.head-pick:hover{border-color:var(--primary);transform:scale(1.06)}
.head-pick.checked{background:linear-gradient(145deg,var(--primary-2),var(--primary));border-color:transparent;color:var(--on-primary)}
.head-pick svg{width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}
.list-head button.sort-btn{display:inline-flex;align-items:center;gap:5px;height:100%;color:inherit;font:inherit;letter-spacing:inherit;text-transform:inherit;transition:color .15s}
.list-head button.sort-btn:hover{color:var(--txt-2)}
.list-head button.sort-btn.sorted{color:var(--primary)}
.list-head .arrow{font-size:8px;opacity:.5;transition:transform .2s}
.list-head button.sort-btn.sorted .arrow{opacity:1}
.list-head .col-actions{text-align:right;padding-right:4px}

.list-body{
  flex:1 1 0%;min-height:0;overflow-y:auto;overflow-x:hidden;
  overscroll-behavior:contain;-webkit-overflow-scrolling:touch;
  contain:layout paint;overflow-anchor:none;touch-action:pan-y;
}
.list-body > .vtop,.list-body > .vbot{height:0;overflow-anchor:none}
.rows{overflow-anchor:none}

.row{
  display:grid;grid-template-columns:minmax(0,1fr) 112px 158px 148px;gap:8px;align-items:center;
  height:var(--row-h);padding:0 16px;
  border-bottom:1px solid color-mix(in srgb,var(--stroke) 55%,transparent);
  font-size:13.5px;transition:background-color .14s ease;
}
.row:last-child{border-bottom:0}
.row:hover{background:var(--hl)}
.row .c-name{display:flex;align-items:center;gap:11px;min-width:0}
.row .c-name .txt{min-width:0;display:flex;flex-direction:column;gap:1px}
.row .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:650;line-height:1.35;display:block;width:100%;text-align:left;background:none;border:0;padding:0;font-family:inherit;font-size:inherit;color:inherit}
.row .name.link{cursor:pointer}
.row .name.link:hover{color:var(--primary)}
.row .sub{display:none;font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:var(--txt-3);white-space:nowrap}
.row .meta{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--txt-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .c-acts{display:flex;justify-content:flex-end;gap:2px}

/* Expressive Grid View */
.rows.grid-mode{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(162px,1fr));
  gap:12px;padding:14px 16px;
}
.rows.grid-mode .row{
  display:flex;flex-direction:column;align-items:stretch;justify-content:space-between;
  height:178px;padding:12px;border-radius:22px;
  background:var(--g-solid-2);border:1px solid var(--stroke);
  box-shadow:inset 0 1px 0 var(--hi);
  transition:transform .22s var(--ease-spring),border-color .18s,background .18s;
  position:relative;
}
.rows.grid-mode .row:hover{transform:translateY(-3px);border-color:var(--stroke-2);background:var(--hl)}
.rows.grid-mode .row .c-name{flex-direction:column;align-items:flex-start;gap:10px;flex:1;min-height:0}
.rows.grid-mode .row .ftype{width:100%;height:92px;border-radius:16px;overflow:hidden;position:relative}
.rows.grid-mode .row .ftype svg{width:28px;height:28px}
.rows.grid-mode .row .ftype img.thumb{width:100%;height:100%;object-fit:cover;display:block}
.rows.grid-mode .row .c-name .txt{width:100%}
.rows.grid-mode .row .sub{display:block}
.rows.grid-mode .row .meta{display:none}
.rows.grid-mode .row .c-acts{position:absolute;top:16px;right:16px;background:var(--g-solid);border-radius:10px;padding:2px;border:1px solid var(--stroke)}
.rows.grid-mode .row .c-acts .act{display:none}
.rows.grid-mode .row .c-acts .act.more{display:inline-flex;opacity:1;width:26px;height:26px}
.rows.grid-mode .row .pick{position:absolute;top:18px;left:18px;z-index:3;background:var(--g-solid)}

.ftype{
  width:38px;height:38px;border-radius:13px;flex:none;display:grid;place-items:center;
  background:linear-gradient(145deg,var(--icon-doc-1),var(--icon-doc-2));
  box-shadow:inset 0 1.5px 0 rgba(255,255,255,.58),0 6px 14px -7px rgba(0,0,0,.5);
  transition:transform .22s var(--ease-spring),border-radius .24s var(--ease-spring);
}
.row:hover .ftype{transform:scale(1.06) rotate(-3deg);border-radius:16px}
.rows.grid-mode .row:hover .ftype{transform:none;border-radius:16px}
.ftype svg{width:19px;height:19px;stroke:#fff;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 1px 1px rgba(0,0,0,.22))}
.ftype.folder{background:linear-gradient(145deg,var(--icon-folder-1),var(--icon-folder-2))}
.ftype.image{background:linear-gradient(145deg,var(--icon-image-1),var(--icon-image-2))}
.ftype.video{background:linear-gradient(145deg,var(--icon-video-1),var(--icon-video-2))}
.ftype.audio{background:linear-gradient(145deg,var(--icon-audio-1),var(--icon-audio-2))}
.ftype.code{background:linear-gradient(145deg,var(--icon-code-1),var(--icon-code-2))}
.ftype.archive{background:linear-gradient(145deg,var(--icon-arch-1),var(--icon-arch-2))}
.ftype.apk{background:linear-gradient(145deg,var(--icon-apk-1),var(--icon-apk-2))}
.ftype.pdf{background:linear-gradient(145deg,var(--icon-pdf-1),var(--icon-pdf-2))}

.act{
  display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:11px;
  color:var(--txt-3);opacity:.25;transition:opacity .14s,background .14s,color .14s,transform .18s var(--ease-spring);
}
.row:hover .act,.row:focus-within .act{opacity:1}
@media (hover:none){.act{opacity:1}}
.act:hover{color:var(--primary);background:var(--primary-soft);transform:scale(1.08)}
.act.del:hover{color:var(--danger);background:var(--danger-soft)}
.act svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.act.more{display:none}

/* ─── Empty / skeleton ───────────────────────────────────────────────────── */
.empty{
  flex:1 1 0%;min-height:0;overflow-y:auto;display:none;flex-direction:column;align-items:center;justify-content:center;gap:14px;
  padding:48px 24px;text-align:center;-webkit-overflow-scrolling:touch;
}
.empty.show{display:flex;animation:rise .35s var(--ease-out) both}
.empty-ico{
  width:78px;height:78px;border-radius:26px;display:grid;place-items:center;color:var(--primary);
  background:linear-gradient(150deg,var(--g1),var(--g2));
  border:1px solid var(--stroke);box-shadow:var(--shadow),inset 0 1.5px 0 var(--hi);
  animation:floaty 4.2s ease-in-out infinite;
}
.empty-ico svg{width:32px;height:32px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.empty h3{font-size:15.5px;font-weight:850;letter-spacing:-.01em}
.empty p{font-size:12.5px;color:var(--txt-3);max-width:34ch;line-height:1.6}
.empty .tool{margin-top:2px}

.skeleton{display:none;flex-direction:column;gap:0;padding:8px 0}
.skeleton.show{display:flex}
.sk{display:flex;align-items:center;gap:11px;height:var(--row-h);padding:0 16px}
.sk i{display:block;border-radius:10px;height:12px;
  background:linear-gradient(90deg,var(--g-solid-2) 25%,var(--hl) 37%,var(--g-solid-2) 63%);
  background-size:300% 100%;animation:shimmer 1.3s linear infinite}
.sk .sq{width:36px;height:36px;border-radius:12px;flex:none}
.sk .w1{width:34%}.sk .w2{width:52%}.sk .w3{width:22%}

/* ─── Status bar with Storage Meter ──────────────────────────────────────── */
.statusbar{
  flex:0 0 auto;display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding:9px 20px calc(9px + env(safe-area-inset-bottom));
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:10.5px;color:var(--txt-3);
  border-top:1px solid var(--stroke);
  background:linear-gradient(0deg,var(--g-solid),transparent);
}
.stat{display:flex;align-items:center;gap:6px;white-space:nowrap}
.stat b{color:var(--txt-2);font-weight:700}
.stat .dot{width:7px;height:7px;border-radius:99px;background:var(--ok);box-shadow:0 0 8px var(--ok);animation:pulseDot 2.4s ease-in-out infinite}
.storage-meter{display:none;align-items:center;gap:7px}
.storage-meter.show{display:inline-flex}
.storage-bar{width:64px;height:6px;border-radius:99px;background:var(--stroke);overflow:hidden}
.storage-fill{height:100%;width:0%;border-radius:99px;background:linear-gradient(90deg,var(--secondary),var(--primary));transition:width .4s ease}
.statusbar .spacer{flex:1}
.statusbar .path{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:44vw;color:var(--txt-2)}

/* ─── Floating Upload Progress Capsule ───────────────────────────────────── */
.upload-pill{
  position:fixed;left:50%;transform:translateX(-50%);bottom:calc(52px + env(safe-area-inset-bottom));z-index:320;
  display:none;align-items:center;gap:12px;padding:10px 18px;border-radius:999px;
  background:var(--g-solid);border:1px solid var(--stroke-2);
  box-shadow:0 20px 48px -16px rgba(0,0,0,.7),inset 0 1.5px 0 var(--hi);
  backdrop-filter:blur(22px) saturate(185%);-webkit-backdrop-filter:blur(22px) saturate(185%);
  font-size:12.5px;font-weight:780;color:var(--txt);
  animation:popIn .28s var(--ease-spring) both;
}
.upload-pill.show{display:inline-flex}
.upload-pill .up-pct{font-family:ui-monospace,Menlo,monospace;color:var(--primary);font-weight:850}

/* ─── FAB ────────────────────────────────────────────────────────────────── */
.fab{
  position:fixed;right:18px;bottom:calc(54px + env(safe-area-inset-bottom));z-index:35;
  display:none;align-items:center;gap:8px;height:56px;padding:0 22px;border-radius:20px;
  font-size:14px;font-weight:800;color:var(--on-primary);
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  box-shadow:0 18px 38px -14px var(--primary),inset 0 1.5px 0 rgba(255,255,255,.45);
  transition:transform .24s var(--ease-spring),border-radius .24s,box-shadow .2s;
}
.fab:hover{transform:translateY(-2px) scale(1.03);border-radius:28px}
.fab:active{transform:scale(.95)}
.fab svg{width:21px;height:21px;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}

/* ─── Progress ───────────────────────────────────────────────────────────── */
.progress{
  position:fixed;top:0;left:0;height:3.5px;width:0;z-index:300;border-radius:0 99px 99px 0;
  background:linear-gradient(90deg,var(--secondary),var(--primary),var(--tertiary));
  background-size:200% 100%;box-shadow:0 0 14px color-mix(in srgb,var(--primary) 70%,transparent);
  transition:width .3s var(--ease-out),opacity .3s;opacity:0;
}
.progress.on{opacity:1;animation:barFlow 1.1s linear infinite}
@keyframes barFlow{0%{background-position:0% 50%}100%{background-position:200% 50%}}

/* ─── Sheets / dialogs ───────────────────────────────────────────────────── */
.backdrop{
  position:fixed;inset:0;z-index:200;display:none;align-items:center;justify-content:center;padding:18px;
  background:var(--scrim);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
}
.backdrop.open{display:flex;animation:fadeIn .18s ease both}
.sheet{
  width:100%;max-width:760px;max-height:min(88vh,860px);display:flex;flex-direction:column;overflow:hidden;
  border-radius:32px;background:var(--g-solid);border:1px solid var(--stroke-2);
  box-shadow:0 40px 100px -30px rgba(0,0,0,.75),inset 0 1.5px 0 var(--hi);
  backdrop-filter:blur(28px) saturate(190%);-webkit-backdrop-filter:blur(28px) saturate(190%);
  animation:popIn .3s var(--ease-spring) both;
}
.sheet.sm{max-width:440px}
.sheet-head{display:flex;align-items:center;gap:10px;padding:18px 20px 12px;flex:0 0 auto}
.sheet-title{flex:1;min-width:0;display:flex;align-items:center;gap:10px;font-size:15px;font-weight:850;letter-spacing:-.01em}
.sheet-title .glyph{
  width:38px;height:38px;border-radius:13px;display:grid;place-items:center;flex:none;color:#fff;
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  box-shadow:inset 0 1.5px 0 rgba(255,255,255,.45),0 6px 14px -8px var(--primary);
}
.sheet-title .glyph svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.sheet-title .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sheet-title .nm small{display:block;font-size:11px;font-weight:650;color:var(--txt-3);letter-spacing:.02em;margin-top:1px;overflow:hidden;text-overflow:ellipsis}
.close-x{
  width:36px;height:36px;border-radius:13px;display:grid;place-items:center;flex:none;
  color:var(--txt-2);background:var(--g-solid-2);border:1px solid var(--stroke);
  font-size:18px;line-height:1;transition:transform .22s var(--ease-spring),color .16s,background .16s;
}
.close-x:hover{color:var(--danger);background:var(--danger-soft);transform:rotate(90deg)}
.sheet-body{padding:6px 20px 18px;overflow-y:auto;flex:1 1 auto}
.sheet-foot{
  display:flex;justify-content:flex-end;gap:9px;padding:14px 20px calc(14px + env(safe-area-inset-bottom));
  border-top:1px solid var(--stroke);flex:0 0 auto;flex-wrap:wrap;
}
.sheet-grab{display:none}

.edit-area{
  width:100%;min-height:min(52vh,440px);padding:15px 16px;border-radius:20px;resize:vertical;
  background:var(--code-bg);color:var(--code-txt);border:1px solid color-mix(in srgb,var(--primary) 24%,transparent);
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.7;
  box-shadow:inset 0 2px 12px rgba(0,0,0,.4);outline:none;
}
.edit-area.wrap-on{white-space:pre-wrap;word-break:break-word}
.edit-area:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-soft),inset 0 2px 12px rgba(0,0,0,.4)}
.edit-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:var(--txt-3);padding:9px 4px 0}
.edit-bar .dirty{color:var(--warn);font-weight:750}
.edit-bar .dirty.hide{visibility:hidden}

.field{display:flex;flex-direction:column;gap:7px;margin-bottom:12px}
.field span{font-size:11.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--txt-3)}
.input{
  width:100%;height:48px;padding:0 16px;border-radius:16px;
  background:var(--g-solid-2);border:1px solid var(--stroke);color:var(--txt);font-size:14px;
  outline:none;transition:border-color .16s,box-shadow .16s,background .16s;
}
.input::placeholder{color:var(--txt-3)}
.input:focus{border-color:var(--primary);background:var(--g1);box-shadow:0 0 0 3px var(--primary-soft)}
.field-error{min-height:16px;font-size:12px;font-weight:700;color:var(--danger)}

.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  height:44px;padding:0 20px;border-radius:16px;
  font-size:13px;font-weight:800;color:var(--txt-2);
  background:var(--g-solid-2);border:1px solid var(--stroke);
  box-shadow:inset 0 1px 0 var(--hi);
  transition:transform .22s var(--ease-spring),border-radius .22s,background .16s,color .16s,border-color .16s,box-shadow .16s;
}
.btn:hover{color:var(--txt);border-color:var(--stroke-2);border-radius:22px;transform:translateY(-1.5px)}
.btn:active{transform:scale(.95)}
.btn svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.btn-primary{
  color:var(--on-primary);border-color:transparent;
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  box-shadow:0 12px 26px -12px var(--primary),inset 0 1.5px 0 rgba(255,255,255,.45);
}
.btn-primary:hover{color:var(--on-primary);filter:brightness(1.06)}
.btn-danger{color:#fff;border-color:transparent;background:linear-gradient(145deg,#ff8080,#d43b3b);box-shadow:0 12px 26px -12px rgba(212,59,59,.8),inset 0 1.5px 0 rgba(255,255,255,.38)}
.btn-danger:hover{color:#fff;filter:brightness(1.06)}
.btn:disabled{opacity:.5;cursor:default;transform:none}

/* Action sheet & Shortcuts Grid */
.act-list{display:flex;flex-direction:column;gap:4px;padding-top:2px}
.act-item{
  display:flex;align-items:center;gap:13px;width:100%;padding:12px 14px;border-radius:16px;
  font-size:14px;font-weight:700;color:var(--txt);text-align:left;
  transition:background .15s,transform .15s;
}
.act-item:hover{background:var(--hl)}
.act-item:active{transform:scale(.985)}
.act-item .ai{width:38px;height:38px;border-radius:13px;display:grid;place-items:center;flex:none;background:var(--primary-soft);color:var(--primary)}
.act-item .ai svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.act-item.danger{color:var(--danger)}
.act-item.danger .ai{background:var(--danger-soft);color:var(--danger)}
.act-item .desc{min-width:0;overflow:hidden;text-overflow:ellipsis}

.kbd-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding-top:4px}
.kbd-item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 13px;border-radius:14px;background:var(--g-solid-2);border:1px solid var(--stroke);font-size:12.5px;font-weight:680;color:var(--txt-2)}
.kbd-item kbd{font-family:ui-monospace,Menlo,monospace;font-size:11px;font-weight:800;padding:3px 7px;border-radius:7px;background:var(--primary-soft);color:var(--primary);border:1px solid color-mix(in srgb,var(--primary) 24%,transparent)}

/* ─── Snackbar ───────────────────────────────────────────────────────────── */
.toasts{
  position:fixed;right:18px;bottom:calc(18px + env(safe-area-inset-bottom));z-index:400;
  display:flex;flex-direction:column;gap:8px;pointer-events:none;max-width:min(92vw,420px);
}
.toast{
  display:flex;align-items:center;gap:10px;
  padding:12px 16px;border-radius:18px;
  font-size:12.5px;font-weight:750;color:var(--txt);
  background:var(--g-solid);border:1px solid var(--stroke-2);
  box-shadow:0 22px 48px -18px rgba(0,0,0,.65),inset 0 1.5px 0 var(--hi);
  backdrop-filter:blur(22px) saturate(185%);-webkit-backdrop-filter:blur(22px) saturate(185%);
  animation:popIn .32s var(--ease-spring) both;
}
.toast.out{opacity:0;transform:translateY(8px);transition:opacity .25s,transform .25s}
.toast .ti{width:22px;height:22px;border-radius:99px;flex:none;display:grid;place-items:center;background:var(--primary-soft);color:var(--primary)}
.toast .ti svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.toast.ok .ti{background:var(--ok-soft);color:var(--ok)}
.toast.err{color:var(--danger)}
.toast.err .ti{background:var(--danger-soft);color:var(--danger)}

/* ─── Drop overlay ───────────────────────────────────────────────────────── */
.drop{
  position:fixed;inset:0;z-index:250;display:none;align-items:center;justify-content:center;
  background:color-mix(in srgb,var(--scrim) 82%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
}
.drop.on{display:flex;animation:fadeIn .16s ease both}
.drop-in{
  display:flex;flex-direction:column;align-items:center;gap:14px;padding:40px 52px;border-radius:32px;text-align:center;
  color:var(--primary);background:var(--g-solid);border:2px dashed color-mix(in srgb,var(--primary) 60%,transparent);
  box-shadow:var(--shadow),inset 0 1.5px 0 var(--hi);
}
.drop-in svg{width:40px;height:40px;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.drop-in b{font-size:15px;color:var(--txt)}
.drop-in small{font-size:12px;color:var(--txt-3)}

/* ─── Selection ──────────────────────────────────────────────────────────── */
.pick{
  width:24px;height:24px;border-radius:8px;flex:none;display:none;place-items:center;
  border:1.6px solid var(--stroke-2);color:transparent;background:var(--g-solid-2);
  transition:transform .2s var(--ease-spring),background .16s,border-color .16s,color .16s;
}
body.selecting .pick{display:grid}
.pick svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;transform:scale(.4);transition:transform .22s var(--ease-spring)}
.row.picked .pick{background:linear-gradient(145deg,var(--primary-2),var(--primary));border-color:transparent;color:var(--on-primary)}
.row.picked .pick svg{transform:scale(1)}
.row.picked{background:var(--primary-soft)}
body.selecting .row .c-acts{opacity:.35;pointer-events:none}
.selbar{
  display:none;align-items:center;gap:8px;flex-wrap:wrap;
  margin:0 16px 10px;padding:10px 14px;border-radius:22px;flex:0 0 auto;
  background:linear-gradient(145deg,var(--primary-2),var(--primary));
  color:var(--on-primary);box-shadow:0 16px 34px -16px var(--primary),inset 0 1.5px 0 rgba(255,255,255,.38);
  animation:rise .26s var(--ease-spring) both;
}
.selbar.show{display:flex}
.selbar .n{font-size:13px;font-weight:850;margin-right:auto;padding-left:4px}
.selbar button{
  display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 13px;border-radius:12px;
  font-size:12px;font-weight:780;color:var(--on-primary);background:rgba(255,255,255,.16);
  transition:background .16s,transform .18s var(--ease-spring),border-radius .18s;
}
.selbar button:hover{background:rgba(255,255,255,.26);border-radius:16px}
.selbar button:active{transform:scale(.95)}
.selbar button svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.selbar button.danger{background:rgba(255,90,90,.28)}
.selbar button.danger:hover{background:rgba(255,90,90,.4)}

/* ─── Preview & Gallery Navigation ───────────────────────────────────────── */
.preview-sheet{max-width:940px;background:var(--g-solid)}
.prev-body{position:relative;display:flex;align-items:center;justify-content:center;min-height:180px;padding:6px 16px 18px}
.prev-body img,.prev-body video{max-width:100%;max-height:66vh;border-radius:20px;display:block;box-shadow:0 24px 60px -28px rgba(0,0,0,.7);animation:previewIn .38s var(--ease-spring) both}
.prev-body video{background:#000}
.prev-body audio{width:100%;max-width:520px}
.prev-body iframe{width:100%;height:64vh;border:0;border-radius:18px;background:#fff}
.prev-text{
  width:100%;max-height:62vh;overflow:auto;padding:16px 18px;border-radius:18px;
  background:var(--code-bg);color:var(--code-txt);border:1px solid var(--stroke);
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.7;
  white-space:pre-wrap;word-break:break-word;
}
.prev-note{font-size:12.5px;color:var(--txt-3);text-align:center;padding:20px}
@keyframes previewIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:none}}
.spin{width:34px;height:34px;border-radius:50%;border:3px solid var(--stroke-2);border-top-color:var(--primary);animation:spin .8s linear infinite}

/* ─── View transition (folder navigation) ────────────────────────────────── */
::view-transition-old(root){animation:fadeOut .18s ease both}
::view-transition-new(root){animation:fadeIn .28s var(--ease-out) both}
@keyframes fadeOut{to{opacity:0;transform:scale(.995)}}
.rows.enter .row{animation:rowIn .34s var(--ease-spring) both;animation-delay:var(--d,0ms)}
@keyframes rowIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* ─── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width:980px){
  .search{margin-left:0;order:99;flex:1 1 100%;width:auto}
  .list-head{grid-template-columns:minmax(0,1fr) 100px 140px 140px}
  .row{grid-template-columns:minmax(0,1fr) 100px 140px 140px}
}
@media (max-width:820px){
  :root{--row-h:64px}
  .brand-text{display:none}
  .appbar{height:60px;gap:8px;padding:0 10px}
  .crumbs{background:transparent;border:0;padding:0 2px;box-shadow:none}
  .crumb{padding:0 8px;font-size:12px}
  .icon-btn .lbl{display:none}
  .toolbar{padding:10px 12px 8px;gap:6px}
  .tool{padding:0 12px}
  .tool .lbl{display:none}
  .tool-accent .lbl{display:inline}
  .search{margin-left:0;order:99;width:100%;flex:1 1 100%}
  .search .kbd{display:none}
  .chips-row{padding:0 12px 8px}
  .list-card{margin:0 10px;border-radius:24px}
  .list-head{grid-template-columns:minmax(0,1fr) auto;height:40px;padding:0 14px;gap:6px}
  .list-head .col-size,.list-head .col-date{display:none}
  .row{grid-template-columns:minmax(0,1fr) auto;gap:6px;padding:0 12px}
  .row .meta{display:none}
  .row .sub{display:block}
  .row .c-acts .act{display:none}
  .row .c-acts .act.more{display:inline-flex;opacity:1}
  .rows.grid-mode{grid-template-columns:repeat(auto-fill,minmax(136px,1fr));gap:10px;padding:12px}
  .fab{display:inline-flex}
  .toolbar .upload-split{display:none}
  .statusbar{padding:8px 14px calc(8px + env(safe-area-inset-bottom));font-size:10px;gap:10px}
  .statusbar .path{display:none}
  .selbar{margin:0 10px 8px;border-radius:18px}
  .selbar .n{font-size:12.5px}
  .selbar button{height:32px;padding:0 10px;font-size:11.5px}
  .prev-body img,.prev-body video{max-height:58dvh}
  .toasts{right:12px;left:12px;bottom:calc(78px + env(safe-area-inset-bottom));max-width:none}
  .toast{max-width:none}
  .backdrop{align-items:flex-end;padding:0}
  .sheet,.sheet.sm{max-width:none;max-height:92vh;max-height:92dvh;border-radius:28px 28px 0 0;animation:sheetIn .34s var(--ease-spring) both}
  .sheet-grab{display:block;width:40px;height:4px;border-radius:99px;background:var(--stroke-2);margin:10px auto 2px;flex:none}
  .sheet-head{padding:10px 16px 8px}
  .sheet-body{padding:4px 16px 16px}
  .sheet-foot{padding:12px 16px calc(12px + env(safe-area-inset-bottom))}
  .sheet-foot .btn{flex:1}
  .empty-ico{width:64px;height:64px;border-radius:22px}
  .kbd-grid{grid-template-columns:1fr}
}
@media (max-width:430px){
  .appbar{gap:6px}
  .actions{gap:4px}
  .icon-btn{height:36px;min-width:36px;padding:0 8px}
  .statusbar .stat.hide-xs{display:none}
}
@media (max-height:520px){
  body{height:auto;min-height:100vh;min-height:100dvh;overflow-y:auto}
  .list-card{min-height:320px}
}
@media (min-width:821px){.fab{display:none!important}}

/* ─── Motion / transparency preferences ──────────────────────────────────── */
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}
  .bg i{animation:none!important}
}
@media (prefers-reduced-transparency:reduce){
  .glass,.glass-blur,.appbar,.toast,.sheet{backdrop-filter:none;-webkit-backdrop-filter:none;background:var(--g-solid)}
}
</style>
<script>
/* Theme before first paint — no flash. */
try {
  var _t = localStorage.getItem('fb_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-theme', _t);
} catch (e) {}
</script>
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#eef0fb">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#070912">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs><linearGradient id='a' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%23a9b3ff'/><stop offset='1' stop-color='%235d67e8'/></linearGradient></defs><rect width='64' height='64' rx='18' fill='url(%23a)'/><path d='M10 22a6 6 0 0 1 6-6h9l5 5h18a6 6 0 0 1 6 6v17a6 6 0 0 1-6 6H16a6 6 0 0 1-6-6z' fill='%23fff' opacity='.96'/><path d='M10 30h44' stroke='%23dfe3ff' stroke-width='3'/></svg>">
</head>
<body>

<div class="bg" aria-hidden="true"><i></i><i></i><i></i></div>
<div class="noise" aria-hidden="true"></div>
<noscript>
  <div style="position:fixed;inset:0;z-index:999;display:grid;place-items:center;padding:24px;text-align:center;background:var(--bg);color:var(--txt);font:600 14px/1.6 system-ui,sans-serif">
    FileBase needs JavaScript to list and manage files. / FileBase 需要启用 JavaScript 才能管理文件。
  </div>
</noscript>

<div class="progress" id="progress" role="progressbar" aria-hidden="true"></div>

<div class="drop" id="dropOverlay" aria-hidden="true">
  <div class="drop-in">
    <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/></svg>
    <b data-i18n="dropFiles">Drop files to upload</b>
    <small data-i18n="dropHint">They land in the folder you are viewing</small>
  </div>
</div>

<div class="toasts" id="toastContainer" role="status" aria-live="polite"></div>

<div class="upload-pill" id="uploadPill" role="status" aria-live="polite">
  <span class="spin" style="width:16px;height:16px;border-width:2px"></span>
  <span id="uploadPillText" data-i18n="uploading">Uploading…</span>
  <span class="up-pct" id="uploadPillPct">0%</span>
</div>

<header class="appbar">
  <button class="brand" id="brandHome" type="button" title="Home">
    <span class="brand-logo" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
    </span>
    <span class="brand-text">FileBase<small data-i18n="brandSub">file server</small></span>
  </button>

  <nav class="crumbs" id="breadcrumb" aria-label="Breadcrumb"></nav>

  <div class="actions">
    <button class="icon-btn admin" id="adminBtn" type="button" title="Admin" aria-label="Admin">
      <svg viewBox="0 0 24 24"><path d="M12 3l7.5 3.2v5.3c0 4.4-3 8.2-7.5 9.5-4.5-1.3-7.5-5.1-7.5-9.5V6.2z"/><path d="M9.2 12.2l2 2 3.6-3.8"/></svg>
      <span class="lbl" data-i18n="adminBtn">Admin</span>
    </button>
    <button class="icon-btn" id="helpBtn" type="button" title="Shortcuts (?)" aria-label="Shortcuts">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.3 2.4c-.9.4-1.3.9-1.3 1.9M12 16.8v.1"/></svg>
    </button>
    <button class="icon-btn" id="themeToggle" type="button" title="Theme" aria-label="Toggle theme">
      <span id="themeIcon"></span>
    </button>
    <button class="icon-btn lang" id="langToggle" type="button" aria-label="Switch language">中文</button>
  </div>
</header>

<section class="toolbar" aria-label="File actions">
  <button class="tool" id="btnUp" type="button" title="Up one level">
    <svg viewBox="0 0 24 24"><path d="M12 19V5m0 0-6 6m6-6 6 6"/></svg>
    <span class="lbl" data-i18n="up">Up</span>
  </button>
  <button class="tool" id="btnRefresh" type="button" title="Refresh (R)">
    <svg viewBox="0 0 24 24"><path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 4v6h-6"/></svg>
    <span class="lbl" data-i18n="refresh">Refresh</span>
  </button>
  <div class="sep" aria-hidden="true"></div>
  <div class="upload-split">
    <button class="tool tool-accent btn-upload" id="btnUpload" type="button" title="Upload (U)">
      <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
      <span class="lbl" data-i18n="upload">Upload</span>
    </button>
    <button class="tool tool-accent caret" id="btnUploadMenu" type="button" aria-label="Upload options" aria-haspopup="true">
      <svg viewBox="0 0 24 24"><path d="M7 10l5 5 5-5"/></svg>
    </button>
    <div class="menu" id="uploadMenu" role="menu">
      <button type="button" role="menuitem" data-pick="files">
        <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
        <span data-i18n="uploadFiles">Upload files</span>
      </button>
      <button type="button" role="menuitem" data-pick="folder">
        <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5M9.5 13.5h5"/></svg>
        <span data-i18n="uploadFolder">Upload folder</span>
      </button>
    </div>
  </div>
  <input type="file" id="fileInput" multiple style="position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden">
  <button class="tool" id="btnNewFolder" type="button" title="New folder (N)">
    <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5M9.5 13.5h5"/></svg>
    <span class="lbl" data-i18n="newFolder">Folder</span>
  </button>
  <button class="tool" id="btnNewFile" type="button" title="New file">
    <svg viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12.5v5M9.5 15h5"/></svg>
    <span class="lbl" data-i18n="newFile">File</span>
  </button>
  <button class="tool" id="btnSelect" type="button" title="Select (S)">
    <svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg>
    <span class="lbl" data-i18n="select">Select</span>
  </button>
  <div class="sort-wrap">
    <button class="tool" id="btnSort" type="button" title="Sort" aria-haspopup="true">
      <svg viewBox="0 0 24 24"><path d="M7 4v16m0 0-3.5-3.5M7 20l3.5-3.5"/><path d="M13 6h7M13 12h5M13 18h3"/></svg>
      <span class="lbl" data-i18n="sort">Sort</span>
    </button>
    <div class="menu" id="sortMenu" role="menu">
      <button type="button" role="menuitem" data-sort="0"><span data-i18n="sortName">Name</span><span class="sort-arrow-ind">↑</span></button>
      <button type="button" role="menuitem" data-sort="1"><span data-i18n="sortSize">Size</span><span class="sort-arrow-ind">↑</span></button>
      <button type="button" role="menuitem" data-sort="2"><span data-i18n="sortDate">Modified</span><span class="sort-arrow-ind">↑</span></button>
    </div>
  </div>
  <div class="view-seg" role="group" aria-label="View mode">
    <button type="button" class="active" id="viewListBtn" title="List view (G)" aria-label="List view">
      <svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>
    <button type="button" id="viewGridBtn" title="Grid view (G)" aria-label="Grid view">
      <svg viewBox="0 0 24 24"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/></svg>
    </button>
  </div>
  <input type="file" id="folderInput" webkitdirectory directory multiple style="position:absolute;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden">
  <div class="search" id="searchWrap">
    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
    <input type="text" id="searchBox" data-i18n-placeholder="search" placeholder="Filter…" autocomplete="off" spellcheck="false" aria-label="Filter">
    <button class="search-clear" id="searchClear" type="button" aria-label="Clear filter">&times;</button>
    <span class="kbd">/</span>
  </div>
</section>

<div class="chips-row">
  <div class="chips" id="catChips" aria-label="Category filter">
    <button type="button" class="chip cat active" data-cat="all" data-i18n="catAll">All</button>
    <button type="button" class="chip cat" data-cat="folder" data-i18n="catFolders">Folders</button>
    <button type="button" class="chip cat" data-cat="media" data-i18n="catMedia">Media</button>
    <button type="button" class="chip cat" data-cat="doc" data-i18n="catDocs">Docs &amp; Code</button>
    <button type="button" class="chip cat" data-cat="arc" data-i18n="catArc">Archives</button>
  </div>
  <div class="chips-divider" aria-hidden="true"></div>
  <div class="chips" id="chips" aria-label="Quick access"></div>
</div>

<div class="selbar" id="selBar">
  <span class="n" id="selCount">0 selected</span>
  <button type="button" id="selAllBtn"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg><span data-i18n="selectAll">Select all</span></button>
  <button type="button" id="selMove"><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 13h6m0 0-2.5-2.5M15 13l-2.5 2.5"/></svg><span data-i18n="move">Move</span></button>
  <button type="button" class="danger" id="selDelete"><svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4.5h6V7M6 7l1 13h10l1-13"/></svg><span data-i18n="delete">Delete</span></button>
  <button type="button" id="selClear"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg><span data-i18n="cancel">Cancel</span></button>
</div>

<main class="list-card">
  <div class="list-head" id="listHead">
    <div class="head-name-wrap">
      <button class="head-pick" id="pickAllBtn" type="button" aria-label="Select all">
        <svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
      </button>
      <button id="sortName" class="sort-btn" type="button"><span data-i18n="name">Name</span><span class="arrow">&#9650;</span></button>
    </div>
    <button id="sortSize" class="sort-btn col-size" type="button"><span data-i18n="size">Size</span><span class="arrow">&#9650;</span></button>
    <button id="sortDate" class="sort-btn col-date" type="button"><span data-i18n="modified">Modified</span><span class="arrow">&#9650;</span></button>
    <span class="col-actions" data-i18n="actions">Actions</span>
  </div>
  <div class="list-body" id="listBody" role="list">
    <div class="vtop" id="vTop"></div>
    <div class="rows" id="vRows"></div>
    <div class="vbot" id="vBot"></div>
  </div>
  <div class="skeleton" id="skeleton" aria-hidden="true">
    <div class="sk"><i class="sq"></i><i class="w2"></i></div>
    <div class="sk"><i class="sq"></i><i class="w1"></i></div>
    <div class="sk"><i class="sq"></i><i class="w3"></i></div>
    <div class="sk"><i class="sq"></i><i class="w2"></i></div>
    <div class="sk"><i class="sq"></i><i class="w1"></i></div>
  </div>
  <div class="empty" id="emptyState">
    <div class="empty-ico" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
    </div>
    <h3 id="emptyTitle" data-i18n="emptyDir">Empty folder</h3>
    <p id="emptyText" data-i18n="emptyHint">Drop files here, or upload something to get started.</p>
    <button class="tool tool-accent" id="emptyUpload" type="button">
      <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
      <span data-i18n="upload">Upload</span>
    </button>
  </div>
</main>

<div class="statusbar" role="status" aria-live="polite">
  <div class="stat"><span class="dot"></span><span id="statusCount">0</span></div>
  <div class="stat hide-xs" id="statusFolders"></div>
  <div class="stat hide-xs" id="statusFiles"></div>
  <div class="stat hide-xs" id="statusSize"></div>
  <div class="storage-meter" id="storageMeter">
    <span class="storage-bar"><span class="storage-fill" id="storageFill"></span></span>
    <span id="statusFree"></span>
  </div>
  <div class="spacer"></div>
  <div class="path" id="statusPath">/sdcard</div>
</div>

<button class="fab" id="fabUpload" type="button">
  <svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
  <span data-i18n="upload">Upload</span>
</button>

<!-- ═══ Editor ═══════════════════════════════════════════════════════════ -->
<div class="backdrop" id="editBackdrop" data-close="closeEdit">
  <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="editTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph"><svg viewBox="0 0 24 24"><path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5 17.5 10.5"/></svg></span>
        <span class="nm"><span id="editTitle">Edit file</span><small data-i18n="editSub">Changes stay on the device</small></span>
      </div>
      <button class="icon-btn" id="editWrapBtn" type="button" title="Toggle word wrap" aria-label="Toggle word wrap">
        <svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h13a3 3 0 1 1 0 6h-4m0 0 2-2m-2 2 2 2M4 18h5"/></svg>
      </button>
      <button class="close-x" type="button" data-close="closeEdit" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <textarea id="editContent" class="edit-area" spellcheck="false" wrap="off"></textarea>
      <div class="edit-bar">
        <span id="editStats">0 B</span>
        <span id="editCursor">Ln 1, Col 1</span>
        <span id="editDirty" class="dirty hide" data-i18n="unsavedBadge">Unsaved</span>
        <span style="margin-left:auto" data-i18n="saveHint">Ctrl / Cmd + S to save</span>
      </div>
    </div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeEdit" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="editSave" type="button" data-i18n="save">Save</button>
    </div>
  </div>
</div>

<!-- ═══ Name dialog ══════════════════════════════════════════════════════ -->
<div class="backdrop" id="nameBackdrop" data-close="closeNameModal">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="nameTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph" id="nameGlyph"><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></span>
        <span class="nm"><span id="nameTitle">New folder</span><small data-i18n="nameSub">Inside the current folder</small></span>
      </div>
      <button class="close-x" type="button" data-close="closeNameModal" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <div class="field">
        <span data-i18n="nameLabel">Name</span>
        <input type="text" id="nameInput" class="input" placeholder="Enter name…" data-i18n-placeholder="enterName" autocomplete="off">
      </div>
      <div class="field-error" id="nameError"></div>
    </div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeNameModal" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="nameConfirmBtn" type="button">Create</button>
    </div>
  </div>
</div>

<!-- ═══ Delete dialog ════════════════════════════════════════════════════ -->
<div class="backdrop" id="delBackdrop" data-close="closeDelModal">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="delTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph" style="background:linear-gradient(150deg,#ff8080,#d43b3b)"><svg viewBox="0 0 24 24"><path d="M12 4l8.5 15h-17z"/><path d="M12 10v4M12 16.6v.1"/></svg></span>
        <span class="nm"><span id="delTitle" data-i18n="deleteConfirm">Delete?</span><small data-i18n="deleteSub">This cannot be undone</small></span>
      </div>
      <button class="close-x" type="button" data-close="closeDelModal" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body"><p id="delMsg" style="font-size:13.5px;line-height:1.65;color:var(--txt-2)"></p></div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeDelModal" data-i18n="cancel">Cancel</button>
      <button class="btn btn-danger" id="delConfirm" type="button" data-i18n="delete">Delete</button>
    </div>
  </div>
</div>

<!-- ═══ Login dialog ═════════════════════════════════════════════════════ -->
<div class="backdrop" id="loginBackdrop" data-close="closeLogin">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="loginTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph"><svg viewBox="0 0 24 24"><rect x="4.5" y="10.5" width="15" height="10" rx="3"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/></svg></span>
        <span class="nm"><span id="loginTitle" data-i18n="adminLogin">Admin login</span><small data-i18n="loginSub">Unlocks the whole filesystem</small></span>
      </div>
      <button class="close-x" type="button" data-close="closeLogin" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <div class="field">
        <span data-i18n="username">Username</span>
        <input type="text" id="loginUser" class="input" placeholder="admin" autocomplete="username">
      </div>
      <div class="field">
        <span data-i18n="password">Password</span>
        <input type="password" id="loginPass" class="input" placeholder="••••••••" autocomplete="current-password">
      </div>
      <div class="field-error" id="loginError"></div>
    </div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeLogin" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="loginBtn" type="button" data-i18n="login">Log in</button>
    </div>
  </div>
</div>

<!-- ═══ Preview (with Gallery Navigation & Quick Edit) ═══════════════════ -->
<div class="backdrop" id="prevBackdrop" data-close="closePreview">
  <div class="sheet preview-sheet" role="dialog" aria-modal="true" aria-labelledby="prevTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph" id="prevGlyph"><svg viewBox="0 0 24 24"><path d="M6 3.5h7.5L18 8v12.5H6z"/><path d="M13.5 3.5V8H18"/></svg></span>
        <span class="nm"><span id="prevTitle">Preview</span><small id="prevSub"></small></span>
      </div>
      <button class="icon-btn" id="prevPrevBtn" type="button" title="Previous (←)" aria-label="Previous">
        <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
      </button>
      <button class="icon-btn" id="prevNextBtn" type="button" title="Next (→)" aria-label="Next">
        <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
      </button>
      <button class="icon-btn" id="prevEditBtn" type="button" title="Edit" aria-label="Edit" style="display:none">
        <svg viewBox="0 0 24 24"><path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5 17.5 10.5"/></svg>
      </button>
      <button class="icon-btn" id="prevDownload" type="button" title="Download" aria-label="Download">
        <svg viewBox="0 0 24 24"><path d="M12 4v11m0 0-4-4m4 4 4-4"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/></svg>
      </button>
      <button class="close-x" type="button" data-close="closePreview" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body prev-body" id="prevBody"></div>
  </div>
</div>

<!-- ═══ Confirm (replaces the native confirm dialog) ═════════════════════ -->
<div class="backdrop" id="confirmBackdrop" data-close="closeConfirm">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph" id="confirmGlyph"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 8v5M12 16.4v.1"/></svg></span>
        <span class="nm"><span id="confirmTitle">Confirm</span><small id="confirmSub"></small></span>
      </div>
      <button class="close-x" type="button" data-close="closeConfirm" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body"><p id="confirmMsg" style="font-size:13.5px;line-height:1.65;color:var(--txt-2)"></p></div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeConfirm" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="confirmOk" type="button">OK</button>
    </div>
  </div>
</div>

<!-- ═══ Move to… ═════════════════════════════════════════════════════════ -->
<div class="backdrop" id="moveBackdrop" data-close="closeMove">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="moveTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph"><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 13h6m0 0-2.5-2.5M15 13l-2.5 2.5"/></svg></span>
        <span class="nm"><span id="moveTitle" data-i18n="moveTitle">Move to…</span><small data-i18n="moveSub">Destination folder path</small></span>
      </div>
      <button class="close-x" type="button" data-close="closeMove" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <div class="field">
        <span data-i18n="destPath">Destination</span>
        <input type="text" id="moveInput" class="input" placeholder="/Download" autocomplete="off" spellcheck="false">
      </div>
      <div class="field-error" id="moveError"></div>
    </div>
    <div class="sheet-foot">
      <button class="btn" type="button" data-close="closeMove" data-i18n="cancel">Cancel</button>
      <button class="btn btn-primary" id="moveConfirm" type="button" data-i18n="move">Move</button>
    </div>
  </div>
</div>

<!-- ═══ Action sheet ══════════════════════════════════════════════════════ -->
<div class="backdrop" id="actBackdrop" data-close="closeActions">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="actTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph" id="actGlyph"><svg viewBox="0 0 24 24"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></svg></span>
        <span class="nm"><span id="actTitle">File</span><small id="actSub"></small></span>
      </div>
      <button class="close-x" type="button" data-close="closeActions" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <div class="act-list" id="actList"></div>
    </div>
  </div>
</div>

<!-- ═══ Keyboard Shortcuts Sheet ══════════════════════════════════════════ -->
<div class="backdrop" id="helpBackdrop" data-close="closeHelp">
  <div class="sheet sm" role="dialog" aria-modal="true" aria-labelledby="helpTitle">
    <div class="sheet-grab"></div>
    <div class="sheet-head">
      <div class="sheet-title">
        <span class="glyph"><svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M7 10h1M11 10h2M16 10h1M8 14h8"/></svg></span>
        <span class="nm"><span id="helpTitle" data-i18n="shortcutsTitle">Keyboard shortcuts</span><small data-i18n="shortcutsSub">Navigate faster with keys</small></span>
      </div>
      <button class="close-x" type="button" data-close="closeHelp" aria-label="Close">&times;</button>
    </div>
    <div class="sheet-body">
      <div class="kbd-grid">
        <div class="kbd-item"><span data-i18n="search">Filter…</span><kbd>/</kbd></div>
        <div class="kbd-item"><span data-i18n="upload">Upload</span><kbd>U</kbd></div>
        <div class="kbd-item"><span data-i18n="newFolder">Folder</span><kbd>N</kbd></div>
        <div class="kbd-item"><span data-i18n="refresh">Refresh</span><kbd>R</kbd></div>
        <div class="kbd-item"><span data-i18n="toggleView">List / Grid</span><kbd>G</kbd></div>
        <div class="kbd-item"><span data-i18n="select">Select</span><kbd>S</kbd></div>
        <div class="kbd-item"><span data-i18n="selectAll">Select all</span><kbd>Ctrl+A</kbd></div>
        <div class="kbd-item"><span data-i18n="up">Up</span><kbd>⌫</kbd></div>
      </div>
    </div>
  </div>
</div>

<script>
/* ══════════════════════════════════════════════════════════════════════════
   FileBase front-end
   · virtualised list (only visible rows exist in the DOM)
   · stale-while-revalidate directory cache, debounced filtering
   · batched uploads, keyboard shortcuts, URL + history sync
   ══════════════════════════════════════════════════════════════════════════ */
var App = (function () {
'use strict';

/* ─── i18n ───────────────────────────────────────────────────────────── */
var L = {
  en: {
    brandSub:"file server", title:"File manager",
    up:"Up", refresh:"Refresh", upload:"Upload", newFolder:"Folder", newFile:"File",
    search:"Filter…", name:"Name", size:"Size", modified:"Modified", actions:"Actions",
    edit:"Edit", delete:"Delete", rename:"Rename", download:"Download", open:"Open",
    cancel:"Cancel", save:"Save", create:"Create", more:"More",
    editSub:"Changes stay on the device", saveHint:"Ctrl / Cmd + S to save",
    newFolderTitle:"New folder", newFileTitle:"New file", renameTitle:"Rename",
    nameSub:"Inside the current folder", nameLabel:"Name", enterName:"Enter name…",
    deleteConfirm:"Delete?", deleteSub:"This cannot be undone",
    deleteFileMsg:"Delete file ", deleteFolderMsg:"Delete folder ", deleteEnd:"?",
    dropFiles:"Drop files to upload", dropHint:"They land in the folder you are viewing",
    uploaded:"Uploaded", failed:"Failed", deleted:"Deleted", renamed:"Renamed", saved:"Saved", created:"Created",
    cannotRead:"Cannot read file", tooLarge:"File is too large for the editor", binary:"Binary file — edit blocked",
    items:"items", folders:"folders", files:"files", totalSize:"total",
    emptyDir:"Empty folder", emptyHint:"Drop files here, or upload something to get started.",
    filterNoMatch:"Nothing matches", filterHint:"Try a different filter or clear it to see everything.",
    serving:"Serving", connected:"Connected", rootDir:"Root",
    adminLogin:"Admin login", adminBtn:"Admin", logout:"Log out", loginSub:"Unlocks the whole filesystem",
    username:"Username", password:"Password", login:"Log in", loginFailed:"Invalid credentials",
    adminOn:"Admin mode enabled", adminOff:"Signed out",
    unsavedBadge:"Unsaved", unsaved:"Unsaved changes", unsavedMsg:"Discard unsaved changes?",
    loadFailed:"Failed to load folder", actionFailed:"Action failed", invalidName:"Invalid name",
    alreadyExists:"A file or folder with that name already exists",
    quick:"Jump to", uploading:"Uploading…", uploadDone:"Upload finished", uploadFail:"Some files failed",
    editStats:"{n} characters", cleared:"Filter cleared", copied:"Command copied",
    uploadHint:"Upload", newFolderChip:"New folder",
    select:"Select", selected:"{n} selected", selectAll:"Select all", clearSel:"Clear",
    move:"Move", moveTitle:"Move to…", moveSub:"Destination folder path", destPath:"Destination",
    moveDone:"Moved", moveFail:"Move failed", deleteMany:"Delete {n} items?",
    preview:"Preview", previewFail:"Cannot preview this file", downloadToView:"Download this file to view it",
    confirmTitle:"Are you sure?", confirmDelete:"Delete", unsavedTitle:"Discard changes?",
    keepEditing:"Keep editing", discard:"Discard", freeSpace:"free",
    uploadFiles:"Upload files", uploadFolder:"Upload folder", loading:"Loading…",
    sort:"Sort", sortName:"Name", sortSize:"Size", sortDate:"Modified date",
    copyPath:"Copy path", pathCopied:"Path copied", logoutConfirm:"Leave admin mode?",
    logoutSub:"You will be back in the /sdcard sandbox", logoutOk:"Log out",
    catAll:"All", catFolders:"Folders", catMedia:"Media", catDocs:"Docs & Code", catArc:"Archives",
    shortcutsTitle:"Keyboard shortcuts", shortcutsSub:"Navigate faster with keys", toggleView:"List / Grid",
  },
  zh: {
    brandSub:"文件服务器", title:"文件管理器",
    up:"返回", refresh:"刷新", upload:"上传", newFolder:"文件夹", newFile:"文件",
    search:"搜索…", name:"名称", size:"大小", modified:"修改时间", actions:"操作",
    edit:"编辑", delete:"删除", rename:"重命名", download:"下载", open:"打开",
    cancel:"取消", save:"保存", create:"创建", more:"更多",
    editSub:"修改只保存在本机", saveHint:"Ctrl / Cmd + S 保存",
    newFolderTitle:"新建文件夹", newFileTitle:"新建文件", renameTitle:"重命名",
    nameSub:"创建在当前文件夹内", nameLabel:"名称", enterName:"输入名称…",
    deleteConfirm:"确认删除？", deleteSub:"此操作不可撤销",
    deleteFileMsg:"删除文件 ", deleteFolderMsg:"删除文件夹 ", deleteEnd:"？",
    dropFiles:"拖放文件以上传", dropHint:"文件会保存到当前所在文件夹",
    uploaded:"已上传", failed:"失败", deleted:"已删除", renamed:"已重命名", saved:"已保存", created:"已创建",
    cannotRead:"无法读取文件", tooLarge:"文件过大，无法在编辑器中打开", binary:"二进制文件，禁止编辑",
    items:"项", folders:"个文件夹", files:"个文件", totalSize:"总计",
    emptyDir:"空文件夹", emptyHint:"把文件拖到这里，或点击上传开始使用。",
    filterNoMatch:"没有匹配项", filterHint:"换个关键词，或清空筛选查看全部。",
    serving:"服务中", connected:"已连接", rootDir:"根目录",
    adminLogin:"管理员登录", adminBtn:"管理", logout:"退出登录", loginSub:"解锁整个文件系统",
    username:"用户名", password:"密码", login:"登录", loginFailed:"用户名或密码错误",
    adminOn:"已进入管理员模式", adminOff:"已退出管理员模式",
    unsavedBadge:"未保存", unsaved:"有未保存的修改", unsavedMsg:"放弃未保存的修改？",
    loadFailed:"目录加载失败", actionFailed:"操作失败", invalidName:"名称无效",
    alreadyExists:"已存在同名文件或文件夹",
    quick:"快速跳转", uploading:"正在上传…", uploadDone:"上传完成", uploadFail:"部分文件上传失败",
    editStats:"{n} 个字符", cleared:"已清空筛选", copied:"命令已复制",
    uploadHint:"上传", newFolderChip:"新建文件夹",
    select:"多选", selected:"已选 {n} 项", selectAll:"全选", clearSel:"清空",
    move:"移动", moveTitle:"移动到…", moveSub:"输入目标文件夹路径", destPath:"目标路径",
    moveDone:"已移动", moveFail:"移动失败", deleteMany:"删除 {n} 个项目？",
    preview:"预览", previewFail:"无法预览此文件", downloadToView:"下载后查看此文件",
    confirmTitle:"确认操作？", confirmDelete:"删除", unsavedTitle:"放弃修改？",
    keepEditing:"继续编辑", discard:"放弃", freeSpace:"可用",
    uploadFiles:"上传文件", uploadFolder:"上传文件夹", loading:"加载中…",
    sort:"排序", sortName:"名称", sortSize:"大小", sortDate:"修改时间",
    copyPath:"复制路径", pathCopied:"路径已复制", logoutConfirm:"退出管理员模式？",
    logoutSub:"将回到 /sdcard 沙箱", logoutOk:"退出登录",
    catAll:"全部", catFolders:"文件夹", catMedia:"媒体", catDocs:"文档与代码", catArc:"压缩包与安装包",
    shortcutsTitle:"键盘快捷键", shortcutsSub:"使用快捷键高效浏览与操作", toggleView:"列表 / 网格视图",
  }
};

var lang = localStorage.getItem('fb_lang') || ((navigator.language || '').toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en');
function t(k) { var d = L[lang] || L.en; return d[k] != null ? d[k] : (L.en[k] != null ? L.en[k] : k); }

/* ─── State ──────────────────────────────────────────────────────────── */
var currentPath = '/';
var currentData = [];
var view = [];                 // filtered + sorted entries
var sortCol = +(localStorage.getItem('fb_sort_col') || 0);
var sortAsc = localStorage.getItem('fb_sort_asc') !== '0';
var viewMode = localStorage.getItem('fb_view_mode') || 'list';
var catFilter = 'all';
var loadSeq = 0;
var isAdmin = false;
var adminToken = localStorage.getItem('fb_admin_token') || '';
var nameMode = null, renameTarget = '';
var editingPath = '', editDirty = false, editWrap = false;
var delTarget = null, delIsDir = false;
var actTarget = null;
var dragDepth = 0;
var ROW_H = 56, rangeStart = -1, rangeEnd = -1, scrollRaf = 0;
var selection = new Set();       // entry names currently picked
var selectMode = false;
var previewEntry = null;
var confirmResolve = null;
var moveTargets = [];
var freeSpace = null, totalSpace = null, usedSpace = null;
var pressTimer = 0, pressStart = null, pressRow = null, longPressed = false;

var CACHE = new Map();         // path -> {t, entries}
var statsAt = 0;
var CACHE_TTL = 20000, CACHE_MAX = 14;

/* ─── Tiny helpers ───────────────────────────────────────────────────── */
function $(id) { return document.getElementById(id); }
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function fmtSize(b) {
  if (b == null || isNaN(b)) return '—';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(b < 10240 ? 1 : 0) + ' KB';
  if (b < 1073741824) return (b / 1048576).toFixed(b < 10485760 ? 1 : 0) + ' MB';
  return (b / 1073741824).toFixed(2) + ' GB';
}
function fmtDate(ts) {
  if (!ts) return '—';
  var d = new Date(ts * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  var sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' });
}
function normPath(p) {
  if (!p) return '/';
  var clean = ('/' + p).replace(/\/+/g, '/').replace(/\/\.\//g, '/');
  if (clean.length > 1 && clean.charAt(clean.length - 1) === '/') clean = clean.slice(0, -1);
  return clean;
}
function dirOf(p) { var i = p.lastIndexOf('/'); return i <= 0 ? '/' : p.slice(0, i + 1); }
function baseOf(p) { return p.split('/').filter(Boolean).pop() || '/'; }
function joinPath(dir, name) { return (dir === '/' ? '' : dir) + '/' + name; }

function copyText(text) {
  var done = function () { toast(t('pathCopied'), 'ok'); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  } else fallback();
  function fallback() {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); done(); } catch (e) {}
    ta.remove();
  }
}

/* ─── Icons ──────────────────────────────────────────────────────────── */
var ICONS = {
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4.5 17l4.4-4.4 3 3 3.2-3.2 4.4 4.4"/>',
  video: '<rect x="3.5" y="6" width="11.5" height="12" rx="2.5"/><path d="M15 10.6l5-2.6v8l-5-2.6z"/>',
  audio: '<path d="M9 17.5V6l9.5-2v11.5"/><circle cx="6.6" cy="18" r="2.4"/><circle cx="16.1" cy="15.8" r="2.4"/>',
  code: '<path d="M9.2 8.2L5 12l4.2 3.8M14.8 8.2L19 12l-4.2 3.8"/>',
  archive: '<rect x="4" y="4.5" width="16" height="4.5" rx="1.6"/><path d="M6 9v9.5a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 18.5V9"/><path d="M10.2 13.2h3.6"/>',
  apk: '<path d="M12 3.5l7.5 4.2v8.6L12 20.5l-7.5-4.2V7.7z"/><path d="M8.6 12.4h6.8M12 8.6v7.6"/>',
  pdf: '<path d="M6 3.5h7.5L18 8v12.5H6z"/><path d="M13.5 3.5V8H18"/><path d="M9 16.5c2.4.6 4-1.2 3-3.2-1.1-2.1-2.6.6-1.5 2.7.9 1.7 2.8 2.4 4.2 1.9"/>',
  text: '<path d="M6 3.5h7.5L18 8v12.5H6z"/><path d="M13.5 3.5V8H18"/><path d="M9 12.5h6M9 16h4"/>',
  file: '<path d="M6 3.5h7.5L18 8v12.5H6z"/><path d="M13.5 3.5V8H18"/>'
};
var TYPE_MAP = {
  image: 'jpg jpeg png gif webp bmp ico heic heif avif svg raw dng tif tiff',
  video: 'mp4 mkv avi mov webm 3gp flv m4v mpg mpeg ts',
  audio: 'mp3 wav flac ogg m4a aac opus wma mid midi amr',
  code: 'js mjs ts tsx jsx json html htm css scss less py rb go rs c h cpp cc hpp java kt kts swift php sh bash zsh yml yaml toml ini xml sql lua vue svelte gradle',
  archive: 'zip gz tar rar 7z bz2 xz zst tgz iso img apks xapk obb',
  apk: 'apk aab jar dex',
  pdf: 'pdf',
  text: 'txt md markdown log csv tsv readme conf cfg env properties'
};
var EXT_TYPE = {};
Object.keys(TYPE_MAP).forEach(function (type) {
  TYPE_MAP[type].split(' ').forEach(function (ext) { EXT_TYPE[ext] = type; });
});
function classify(entry) {
  if (entry.isdir) return 'folder';
  var i = entry.name.lastIndexOf('.');
  var ext = i > 0 ? entry.name.slice(i + 1).toLowerCase() : '';
  return EXT_TYPE[ext] || 'file';
}
function matchCategory(kind, cat) {
  if (!cat || cat === 'all') return true;
  if (cat === 'folder') return kind === 'folder';
  if (cat === 'media') return kind === 'image' || kind === 'video' || kind === 'audio';
  if (cat === 'doc') return kind === 'text' || kind === 'code' || kind === 'pdf' || kind === 'file';
  if (cat === 'arc') return kind === 'archive' || kind === 'apk';
  return true;
}
function iconSvg(kind) { return '<svg viewBox="0 0 24 24">' + (ICONS[kind] || ICONS.file) + '</svg>'; }

/* ─── Theme & language ───────────────────────────────────────────────── */
function systemTheme() { return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
function getTheme() { return localStorage.getItem('fb_theme') || systemTheme(); }
function applyTheme() {
  var th = getTheme();
  document.documentElement.setAttribute('data-theme', th);
  var tc = document.getElementById('themeColor');
  if (tc) tc.setAttribute('content', th === 'dark' ? '#070912' : '#eef0fb');
  var icon = $('themeIcon');
  if (icon) {
    icon.innerHTML = th === 'dark'
      ? '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.6"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg>'
      : '<svg viewBox="0 0 24 24"><path d="M20.5 14A8.5 8.5 0 1 1 10 3.5a7 7 0 0 0 10.5 10.5z"/></svg>';
  }
}
function applyViewMode(mode) {
  viewMode = mode === 'grid' ? 'grid' : 'list';
  localStorage.setItem('fb_view_mode', viewMode);
  if ($('viewListBtn')) $('viewListBtn').classList.toggle('active', viewMode === 'list');
  if ($('viewGridBtn')) $('viewGridBtn').classList.toggle('active', viewMode === 'grid');
  var rows = $('vRows');
  if (rows) rows.classList.toggle('grid-mode', viewMode === 'grid');
  rangeStart = -1; rangeEnd = -1;
  renderList(true);
}
function applyLang() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(function (el) {
    var k = el.getAttribute('data-i18n');
    var d = L[lang] || L.en;
    if (d[k] != null) el.textContent = d[k];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
    var k = el.getAttribute('data-i18n-placeholder');
    var d = L[lang] || L.en;
    if (d[k] != null) el.placeholder = d[k];
  });
  $('langToggle').textContent = lang === 'zh' ? 'EN' : '中文';
  document.title = 'FileBase — ' + t('title');
  updateSortHeaders();
  updateSelBar();
  if (currentData.length || view.length) { buildView(); renderWindow(true); }
  renderChips();
}

/* ─── API ────────────────────────────────────────────────────────────── */
function authHeaders(extra) {
  var h = extra || {};
  if (isAdmin && adminToken) h['Authorization'] = 'Bearer ' + adminToken;
  return h;
}
async function api(endpoint, opts) {
  var o = Object.assign({}, opts || {});
  o.headers = authHeaders(o.headers || {});
  var res = await fetch('/api' + endpoint, o);
  var data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    var err = new Error((data && data.error) || ('HTTP ' + res.status));
    err.status = res.status;
    throw err;
  }
  return data || {};
}

/* ─── Progress ───────────────────────────────────────────────────────── */
var progTimer = 0;
function progress(pct) {
  var el = $('progress');
  if (!el) return;
  clearTimeout(progTimer);
  if (pct <= 0) {
    el.classList.remove('on');
    el.style.width = '0%';
    return;
  }
  el.classList.add('on');
  el.style.width = Math.max(4, Math.min(100, pct)) + '%';
  if (pct >= 100) progTimer = setTimeout(function () { progress(0); }, 340);
}

/* ─── Snackbar ───────────────────────────────────────────────────────── */
function toast(msg, type) {
  var box = $('toastContainer');
  var el = document.createElement('div');
  el.className = 'toast ' + (type || '');
  var glyph = type === 'err'
    ? '<path d="M12 7v6M12 16.6v.1"/>'
    : type === 'ok'
      ? '<path d="M5 12.5l4.5 4.5L19 7.5"/>'
      : '<circle cx="12" cy="12" r="8"/><path d="M12 8v4M12 15.6v.1"/>';
  el.innerHTML = '<span class="ti"><svg viewBox="0 0 24 24">' + glyph + '</svg></span><span>' + esc(msg) + '</span>';
  box.appendChild(el);
  while (box.children.length > 4) box.removeChild(box.firstChild);
  setTimeout(function () {
    el.classList.add('out');
    setTimeout(function () { el.remove(); }, 260);
  }, 3200);
}

/* ─── Breadcrumbs ────────────────────────────────────────────────────── */
function renderBreadcrumb() {
  var bc = $('breadcrumb');
  var parts = currentPath.split('/').filter(Boolean);
  var home = '<svg viewBox="0 0 24 24"><path d="M3.5 10.5L12 3.5l8.5 7"/><path d="M6 9.5V20h12V9.5"/></svg>';
  var rootLabel = parts.length ? '' : (isAdmin ? '/' : t('rootDir'));
  var html = '<button class="crumb' + (parts.length ? '' : ' current') + '" data-nav="/">' +
    home + (rootLabel ? '<span class="home-txt">' + esc(rootLabel) + '</span>' : '') + '</button>';
  var accum = '';
  var start = 0;
  if (parts.length > 4) start = parts.length - 4;
  for (var i = start; i < parts.length; i++) {
    accum += '/' + parts[i];
    if (i === start && start > 0) html += '<span class="crumb-sep">…</span>';
    var last = i === parts.length - 1;
    html += '<span class="crumb-sep">›</span>';
    html += last
      ? '<span class="crumb current">' + esc(parts[i]) + '</span>'
      : '<button class="crumb" data-nav="' + esc(accum) + '">' + esc(parts[i]) + '</button>';
  }
  bc.innerHTML = html;
  bc.scrollLeft = bc.scrollWidth;
}

/* ─── Quick access chips ─────────────────────────────────────────────── */
var QUICK_COMMON = [
  { p: '/Download', k: 'download' },
  { p: '/DCIM', k: null },
  { p: '/Pictures', k: null },
  { p: '/Movies', k: null },
  { p: '/Music', k: null },
  { p: '/Documents', k: null }
];
var QUICK_ADMIN = [
  { p: '/', k: 'rootDir' },
  { p: '/sdcard', k: null, n: 'sdcard' },
  { p: '/data', k: null, n: 'data' },
  { p: '/system', k: null, n: 'system' },
  { p: '/sdcard/Download', k: 'download' }
];
function renderChips() {
  var box = $('chips');
  if (!box) return;
  var list = isAdmin ? QUICK_ADMIN : QUICK_COMMON;
  var html = '<span class="chip" style="border:0;background:transparent;padding-left:2px;pointer-events:none;color:var(--txt-3)">' +
    '<svg viewBox="0 0 24 24"><path d="M13 2.8L5.5 13H11l-1 8.2L17.5 11H12z"/></svg>' +
    esc(t('quick')) + '</span>';
  list.forEach(function (item) {
    var label = item.k ? t(item.k) : (item.n || item.p.replace(/^\//, ''));
    if (item.p === '/sdcard/Download') label = 'Download';
    if (item.p === '/' && item.k) label = '/';
    var active = currentPath === item.p || (item.p !== '/' && currentPath.indexOf(item.p + '/') === 0);
    html += '<button class="chip' + (active ? ' active' : '') + '" data-nav="' + esc(item.p) + '">' + esc(label) + '</button>';
  });
  box.innerHTML = html;
}

/* ─── Filter / sort / virtual list ───────────────────────────────────── */
function buildView() {
  var q = ($('searchBox').value || '').trim().toLowerCase();
  var out = [];
  var i, e;
  for (i = 0; i < currentData.length; i++) {
    e = currentData[i];
    if (catFilter !== 'all' && !matchCategory(e._kind, catFilter)) continue;
    if (q && e._n.indexOf(q) === -1) continue;
    out.push(e);
  }
  var col = sortCol, asc = sortAsc ? 1 : -1;
  out.sort(function (a, b) {
    if (a.isdir !== b.isdir) return a.isdir ? -1 : 1;   // folders always lead
    var r = 0;
    if (col === 1) r = (a.size || 0) - (b.size || 0);
    else if (col === 2) r = (a.mtime || 0) - (b.mtime || 0);
    else r = a._n < b._n ? -1 : a._n > b._n ? 1 : 0;
    return r * asc;
  });
  view = out;
}

function measureRow() {
  ROW_H = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--row-h')) || 56;
}

function renderWindow(force) {
  measureRow();
  var body = $('listBody');
  var rows = $('vRows');
  var total = view.length;
  if (rows) rows.classList.toggle('grid-mode', viewMode === 'grid');

  if (viewMode === 'grid') {
    var gridEnd = Math.min(total, 240);
    if (!force && rangeStart === 0 && rangeEnd === gridEnd) return;
    rangeStart = 0; rangeEnd = gridEnd;
    var gHtml = '';
    for (var gi = 0; gi < gridEnd; gi++) gHtml += rowHtml(view[gi], gi, gi);
    rows.innerHTML = gHtml;
    $('vTop').style.height = '0px';
    $('vBot').style.height = (window.innerWidth <= 820 ? '78px' : '0px');
    return;
  }

  var vh = body.clientHeight || 420;
  var top = body.scrollTop || 0;
  var overscan = 6;
  var start = Math.max(0, Math.floor(top / ROW_H) - overscan);
  var end = Math.min(total, Math.ceil((top + vh) / ROW_H) + overscan);
  if (start === end && total) end = Math.min(total, start + 1);
  if (!force && start === rangeStart && end === rangeEnd) return;
  if (!force && rows) rows.classList.remove('enter');

  var oldStart = rangeStart, oldEnd = rangeEnd;
  rangeStart = start; rangeEnd = end;

  var i, html = '';
  if (!force && oldStart >= 0 && oldEnd > oldStart && start < oldEnd && end > oldStart && rows.children.length === (oldEnd - oldStart)) {
    while (rows.firstElementChild && +rows.firstElementChild.getAttribute('data-idx') < start) {
      rows.removeChild(rows.firstElementChild);
    }
    while (rows.lastElementChild && +rows.lastElementChild.getAttribute('data-idx') >= end) {
      rows.removeChild(rows.lastElementChild);
    }
    if (start < oldStart) {
      var pre = '';
      for (i = start; i < Math.min(oldStart, end); i++) pre += rowHtml(view[i], i, 0);
      if (pre) rows.insertAdjacentHTML('afterbegin', pre);
    }
    if (end > oldEnd) {
      var post = '';
      for (i = Math.max(oldEnd, start); i < end; i++) post += rowHtml(view[i], i, 0);
      if (post) rows.insertAdjacentHTML('beforeend', post);
    }
  } else {
    for (i = start; i < end; i++) html += rowHtml(view[i], i, i - start);
    rows.innerHTML = html;
  }
  $('vTop').style.height = (start * ROW_H) + 'px';
  $('vBot').style.height = Math.max(0, (total - end) * ROW_H + (window.innerWidth <= 820 ? 78 : 0)) + 'px';
}

function enterRows() {
  var rows = $('vRows');
  if (!rows) return;
  rows.classList.remove('enter');
  void rows.offsetWidth;
  rows.classList.add('enter');
  setTimeout(function () { rows.classList.remove('enter'); }, 620);
}

function rowHtml(e, idx, relIdx) {
  var kind = e._kind;
  var isDir = e.isdir;
  var size = isDir ? '' : fmtSize(e.size);
  var date = isDir ? '' : fmtDate(e.mtime);
  var acts = '';
  if (!isDir) acts += actBtn('download', 'download', t('download'));
  if (e.editable) acts += actBtn('edit', 'edit', t('edit'));
  acts += actBtn('rename', 'rename', t('rename'));
  acts += actBtn('delete', 'delete del', t('delete'));
  var picked = selection.has(e.name);
  var delay = (relIdx != null ? Math.max(0, Math.min(relIdx, 14)) : Math.min(idx, 14)) * 16;
  var nameCell = '<button class="name link" type="button" data-act="' +
    (isDir ? 'nav' : 'preview') + '" data-idx="' + idx + '">' + esc(e.name) + '</button>';
  var ftypeInner = (viewMode === 'grid' && kind === 'image' && e.size <= 16 * 1024 * 1024)
    ? '<img class="thumb" loading="lazy" src="' + esc(previewUrl(e.name)) + '" alt="">'
    : iconSvg(kind);
  return '<div class="row' + (picked ? ' picked' : '') + '" role="listitem" data-idx="' + idx +
    '" style="--d:' + delay + 'ms">' +
    '<div class="c-name">' +
      '<button class="pick" type="button" data-act="pick" data-idx="' + idx + '" aria-label="' + esc(t('select')) + '">' +
        '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button>' +
      '<span class="ftype ' + kind + '">' + ftypeInner + '</span>' +
      '<span class="txt">' + nameCell + (isDir ? '' : '<span class="sub">' + esc(size) + ' · ' + esc(date) + '</span>') + '</span></div>' +
    '<div class="meta">' + esc(size) + '</div>' +
    '<div class="meta">' + esc(date) + '</div>' +
    '<div class="c-acts">' + acts +
      '<button class="act more" type="button" data-act="sheet" data-idx="' + idx + '" aria-label="' + esc(t('more')) + '">' +
      '<svg viewBox="0 0 24 24"><circle cx="6" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18" cy="12" r="1.4"/></svg></button>' +
    '</div></div>';
}

var ACTION_ICONS = {
  download: '<path d="M12 4v11m0 0-4-4m4 4 4-4"/><path d="M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2"/>',
  edit: '<path d="M4 20h4l10-10a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5 17.5 10.5"/>',
  rename: '<path d="M4 7h10M9 4v6M4 17h9"/><path d="M15 12l5 5m0-5-5 5"/>',
  delete: '<path d="M4 7h16M9 7V4.5h6V7M6 7l1 13h10l1-13"/>',
  preview: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  move: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 13h6m0 0-2.5-2.5M15 13l-2.5 2.5"/>',
  open: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9.5 13.5l3-3 3 3"/>',
  select: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"/>'
};
function actBtn(act, cls, label) {
  return '<button class="act ' + cls + '" type="button" data-act="' + act + '" aria-label="' + esc(label) + '" title="' + esc(label) + '">' +
    '<svg viewBox="0 0 24 24">' + ACTION_ICONS[act] + '</svg></button>';
}

function renderList(force) {
  var body = $('listBody');
  var empty = $('emptyState');
  var sk = $('skeleton');
  sk.classList.remove('show');
  if (!view.length) {
    body.style.display = 'none';
    empty.classList.add('show');
    if (currentData.length === 0) {
      $('emptyTitle').textContent = t('emptyDir');
      $('emptyText').textContent = t('emptyHint');
      $('emptyUpload').style.display = '';
    } else {
      $('emptyTitle').textContent = t('filterNoMatch');
      $('emptyText').textContent = t('filterHint');
      $('emptyUpload').style.display = 'none';
    }
    $('vRows').innerHTML = '';
    $('vTop').style.height = '0px';
    $('vBot').style.height = '0px';
    return;
  }
  empty.classList.remove('show');
  body.style.display = '';
  renderWindow(true);
  if (force && viewMode === 'list') {
    var maxScroll = Math.max(0, view.length * ROW_H - body.clientHeight);
    if (body.scrollTop > maxScroll) {
      body.scrollTop = maxScroll;
      renderWindow(true);
    }
  }
}

function showSkeleton() {
  $('emptyState').classList.remove('show');
  $('listBody').style.display = 'none';
  $('skeleton').classList.add('show');
  $('vRows').innerHTML = '';
}

function updateStatus() {
  var dirs = 0, files = 0, bytes = 0;
  for (var i = 0; i < view.length; i++) {
    if (view[i].isdir) dirs++; else { files++; bytes += view[i].size || 0; }
  }
  $('statusCount').textContent = view.length + ' ' + t('items');
  $('statusFolders').textContent = dirs + ' ' + t('folders');
  $('statusFiles').textContent = files + ' ' + t('files');
  $('statusSize').textContent = fmtSize(bytes) + ' ' + t('totalSize');
  updateStorageMeter();
  $('statusPath').textContent = currentPath;
}

function updateStorageMeter() {
  var meter = $('storageMeter');
  var fill = $('storageFill');
  var txt = $('statusFree');
  if (!txt) return;
  if (freeSpace == null) {
    if (meter) meter.classList.remove('show');
    txt.textContent = '';
    return;
  }
  txt.textContent = fmtSize(freeSpace) + ' ' + t('freeSpace');
  if (meter) meter.classList.add('show');
  if (fill && totalSpace > 0) {
    var pct = Math.max(3, Math.min(100, Math.round(((totalSpace - freeSpace) / totalSpace) * 100)));
    fill.style.width = pct + '%';
  }
}

async function loadStats(force) {
  if (!force && Date.now() - statsAt < 15000) return;
  statsAt = Date.now();
  try {
    var s = await api('/stats');
    freeSpace = s.free;
    totalSpace = s.total;
    usedSpace = s.used;
    updateStorageMeter();
  } catch (e) { /* stats are decorative */ }
}

function updateSortHeaders() {
  var map = [['sortName', 0], ['sortSize', 1], ['sortDate', 2]];
  map.forEach(function (pair) {
    var el = $(pair[0]);
    if (!el) return;
    var active = sortCol === pair[1];
    el.classList.toggle('sorted', active);
    var arrow = el.querySelector('.arrow');
    if (arrow) {
      arrow.textContent = sortAsc ? '▲' : '▼';
      arrow.style.transform = active ? 'none' : 'rotate(90deg)';
    }
  });
  var menu = $('sortMenu');
  if (menu) {
    menu.querySelectorAll('[data-sort]').forEach(function (btn) {
      var active = +btn.getAttribute('data-sort') === sortCol;
      btn.classList.toggle('active', active);
      var ind = btn.querySelector('.sort-arrow-ind');
      if (ind) ind.textContent = active ? (sortAsc ? '↑' : '↓') : '↑';
    });
  }
}

function renderAll(force) {
  buildView();
  renderBreadcrumb();
  renderChips();
  updateStatus();
  updateSortHeaders();
  updateSelBar();
  renderList(force !== false);
}

/* ─── Cache + loading ────────────────────────────────────────────────── */
function cachePut(path, entries) {
  CACHE.set(path, { t: Date.now(), entries: entries });
  if (CACHE.size > CACHE_MAX) {
    var oldestKey = null, oldest = Infinity;
    CACHE.forEach(function (v, k) { if (v.t < oldest) { oldest = v.t; oldestKey = k; } });
    if (oldestKey) CACHE.delete(oldestKey);
  }
}
function cacheGet(path) {
  var hit = CACHE.get(path);
  if (!hit) return null;
  if (Date.now() - hit.t > CACHE_TTL) { CACHE.delete(path); return null; }
  return hit.entries;
}
function prepareEntry(e) {
  if (Array.isArray(e)) {
    e = { name: e[0], isdir: e[1] === 1, size: e[2] || 0, mtime: e[3] || 0, editable: e[4] === 1 };
  }
  e._n = String(e.name).toLowerCase();
  e._kind = classify(e);
  return e;
}

function renderWithTransition(fn) {
  if (document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    try { document.startViewTransition(fn); return; } catch (e) { /* fall through */ }
  }
  fn();
}

async function loadDir(path, opts) {
  opts = opts || {};
  var seq = ++loadSeq;
  var usedTransition = false;
  var paint = function () {
    if (usedTransition || !opts.transition) { renderAll(true); enterRows(); return; }
    usedTransition = true;
    renderWithTransition(function () { renderAll(true); enterRows(); });
  };
  var cached = cacheGet(path);
  if (cached) {
    currentData = cached;
    paint();
  } else if (!opts.soft) {
    showSkeleton();
  }
  progress(28);
  try {
    var data = await api('/list?path=' + encodeURIComponent(path) + '&compact=1');
    if (seq !== loadSeq) return;
    var entries = (data.entries || []).map(prepareEntry);
    currentData = entries;
    cachePut(path, entries);
    paint();
    progress(100);
    loadStats();
  } catch (e) {
    if (seq !== loadSeq) return;
    progress(0);
    currentData = [];
    renderAll(true);
    toast(t('loadFailed') + ': ' + ((e && e.message) || ''), 'err');
  }
}

/* ─── Navigation + history ───────────────────────────────────────────── */
function setPathUi(path) {
  currentPath = path;
  var url = path === '/' ? location.pathname : location.pathname + '?path=' + encodeURIComponent(path);
  try { history.pushState({ p: path }, '', url); } catch (e) {}
}
function go(path, opts) {
  opts = opts || {};
  path = normPath(path || '/');
  if (path === currentPath && !opts.force) return;
  currentPath = path;
  $('listBody').scrollTop = 0;
  rangeStart = -1; rangeEnd = -1;
  clearSelection();
  if (opts.push !== false) setPathUi(path);
  loadDir(path, Object.assign({ transition: true }, opts));
}
function goUp() {
  if (currentPath === '/') return;
  go(dirOf(currentPath));
}
function refresh() { loadDir(currentPath, { soft: true, force: true }); }

/* ─── Actions ────────────────────────────────────────────────────────── */
function findEntry(idx) { return view[idx] || null; }
function downloadUrl(name) {
  return '/api/download?path=' + encodeURIComponent(joinPath(currentPath, name)) +
    (isAdmin && adminToken ? '&token=' + encodeURIComponent(adminToken) : '');
}
function triggerDownload(url) {
  if (!url) return;
  var a = document.createElement('a');
  a.href = url; a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function editFile(path) {
  editingPath = path;
  var name = baseOf(path);
  $('editTitle').textContent = name;
  try {
    var data = await api('/text?path=' + encodeURIComponent(path));
    var area = $('editContent');
    area.value = data.content || '';
    editDirty = false;
    updateEditStats();
    updateEditCursor();
    openModal('editBackdrop');
    setTimeout(function () { area.focus(); area.setSelectionRange(0, 0); updateEditCursor(); }, 140);
  } catch (e) {
    var msg = e && e.status === 413 ? t('tooLarge') : e && e.status === 415 ? t('binary') : ((e && e.message) || t('cannotRead'));
    toast(msg, 'err');
  }
}
async function saveEdit() {
  var content = $('editContent').value;
  var btn = $('editSave');
  btn.disabled = true;
  try {
    await fetch('/api/write', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ path: editingPath, content: content, overwrite: true })
    }).then(async function (res) {
      if (!res.ok) {
        var d = null; try { d = await res.json(); } catch (e) {}
        throw new Error((d && d.error) || ('HTTP ' + res.status));
      }
    });
    editDirty = false;
    toast(t('saved'), 'ok');
    closeEdit(true);
    refresh();
  } catch (e) {
    toast((e && e.message) || t('actionFailed'), 'err');
  } finally {
    btn.disabled = false;
  }
}
function updateEditStats() {
  var v = $('editContent').value;
  $('editStats').textContent = t('editStats').replace('{n}', v.length.toLocaleString());
  $('editDirty').classList.toggle('hide', !editDirty);
}
function updateEditCursor() {
  var area = $('editContent');
  var cur = $('editCursor');
  if (!area || !cur) return;
  var pos = area.selectionStart || 0;
  var before = area.value.slice(0, pos);
  var lines = before.split('\n');
  var ln = lines.length;
  var col = lines[lines.length - 1].length + 1;
  cur.textContent = 'Ln ' + ln + ', Col ' + col;
}
function toggleEditWrap() {
  editWrap = !editWrap;
  var area = $('editContent');
  var btn = $('editWrapBtn');
  if (area) area.setAttribute('wrap', editWrap ? 'soft' : 'off');
  if (btn) btn.classList.toggle('on', editWrap);
}
function closeEdit(force) {
  if (!force && editDirty) {
    askConfirm({
      title: t('unsavedTitle'),
      msg: t('unsavedMsg'),
      okLabel: t('discard'),
      danger: true
    }).then(function (ok) {
      if (!ok) return;
      editDirty = false;
      closeModal('editBackdrop');
    });
    return;
  }
  editDirty = false;
  closeModal('editBackdrop');
}
function markDirty() { editDirty = true; updateEditStats(); updateEditCursor(); }

function deleteItem(path, isdir) {
  delTarget = path;
  delIsDir = isdir;
  var name = baseOf(path);
  $('delMsg').textContent = (isdir ? t('deleteFolderMsg') : t('deleteFileMsg')) + name + t('deleteEnd');
  openModal('delBackdrop');
}
function closeDelModal() { closeModal('delBackdrop'); }
async function confirmDel() {
  if (!delTarget) return;
  var btn = $('delConfirm');
  btn.disabled = true;
  try {
    await api('/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: delTarget })
    });
    toast(t('deleted'), 'ok');
    closeDelModal();
    CACHE.delete(currentPath);
    refresh();
  } catch (e) {
    toast(t('actionFailed') + ': ' + ((e && e.message) || ''), 'err');
  } finally { btn.disabled = false; }
}

function renameItem(path) {
  renameTarget = path;
  nameMode = 'rename';
  openNameModal(t('renameTitle'), 'rename');
  var inp = $('nameInput');
  inp.value = baseOf(path);
  setTimeout(function () { inp.focus(); inp.select(); }, 120);
}
function newFolderModal() { nameMode = 'folder'; openNameModal(t('newFolderTitle'), 'folder'); }
function newFileModal() { nameMode = 'file'; openNameModal(t('newFileTitle'), 'file'); }
function openNameModal(title, kind) {
  $('nameTitle').textContent = title;
  $('nameGlyph').innerHTML = '<svg viewBox="0 0 24 24">' + (ICONS[kind] || ICONS.folder) + '</svg>';
  var inp = $('nameInput');
  inp.value = '';
  inp.placeholder = t('enterName');
  $('nameError').textContent = '';
  $('nameConfirmBtn').textContent = nameMode === 'rename' ? t('rename') : t('create');
  openModal('nameBackdrop');
  setTimeout(function () { inp.focus(); }, 130);
}
function closeNameModal() { closeModal('nameBackdrop'); }
async function confirmName() {
  var name = $('nameInput').value.trim();
  var errEl = $('nameError');
  if (!name) return;
  if (name.indexOf('/') !== -1 || name === '.' || name === '..') {
    errEl.textContent = t('invalidName');
    return;
  }
  errEl.textContent = '';
  var fullPath = joinPath(currentPath, name);
  var btn = $('nameConfirmBtn');
  btn.disabled = true;
  try {
    if (nameMode === 'folder') {
      await api('/mkdir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: fullPath })
      });
    } else if (nameMode === 'rename') {
      var dir = dirOf(renameTarget);
      if (dir + name === renameTarget) { closeNameModal(); return; }
      await api('/rename', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ oldPath: renameTarget, newPath: dir + name })
      });
    } else {
      await api('/write', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: fullPath, content: '', overwrite: false })
      });
    }
    toast(t(nameMode === 'rename' ? 'renamed' : 'created') + ': ' + name, 'ok');
    closeNameModal();
    CACHE.delete(currentPath);
    refresh();
  } catch (e) {
    if (e && e.status === 409) errEl.textContent = t('alreadyExists');
    else errEl.textContent = (e && e.message) || t('actionFailed');
  } finally { btn.disabled = false; }
}

/* ─── Selection ──────────────────────────────────────────────────────── */
function clearSelection() {
  selection.clear();
  selectMode = false;
  document.body.classList.remove('selecting');
  $('selBar').classList.remove('show');
  updateSelBar();
  renderWindow(true);
}
function enterSelect(entry) {
  selectMode = true;
  document.body.classList.add('selecting');
  $('selBar').classList.add('show');
  if (entry) selection.add(entry.name);
  updateSelBar();
  renderWindow(true);
}
function togglePick(entry) {
  if (selection.has(entry.name)) selection.delete(entry.name);
  else selection.add(entry.name);
  if (!selection.size) { clearSelection(); return; }
  updateSelBar();
  renderWindow(true);
}
function toggleSelectAll() {
  if (!view.length) return;
  var allPicked = view.every(function (e) { return selection.has(e.name); });
  if (allPicked) {
    clearSelection();
    return;
  }
  selectMode = true;
  document.body.classList.add('selecting');
  view.forEach(function (e) { selection.add(e.name); });
  updateSelBar();
  renderWindow(true);
}
function updateSelBar() {
  var n = selection.size;
  $('selCount').textContent = t('selected').replace('{n}', n);
  $('selBar').classList.toggle('show', n > 0 || selectMode);
  var pa = $('pickAllBtn');
  if (pa) {
    var allPicked = view.length > 0 && view.every(function (e) { return selection.has(e.name); });
    pa.classList.toggle('picked', allPicked);
  }
}
function selectedEntries() {
  return view.filter(function (e) { return selection.has(e.name); });
}
async function deleteSelected() {
  var items = selectedEntries();
  if (!items.length) return;
  var ok = await askConfirm({
    title: t('confirmDelete'),
    msg: t('deleteMany').replace('{n}', items.length),
    okLabel: t('delete'),
    danger: true
  });
  if (!ok) return;
  var paths = items.map(function (e) { return joinPath(currentPath, e.name); });
  try {
    await api('/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: paths })
    });
    toast(t('deleted') + ' (' + items.length + ')', 'ok');
    clearSelection();
    CACHE.delete(currentPath);
    refresh();
  } catch (e) {
    toast((e && e.message) || t('actionFailed'), 'err');
  }
}

/* ─── Move ───────────────────────────────────────────────────────────── */
function openMove(entries) {
  moveTargets = entries.map(function (e) { return joinPath(currentPath, e.name); });
  $('moveInput').value = currentPath;
  $('moveError').textContent = '';
  openModal('moveBackdrop');
  setTimeout(function () { var i = $('moveInput'); i.focus(); i.select(); }, 130);
}
function closeMove() { closeModal('moveBackdrop'); }
async function confirmMove() {
  var dest = normPath(($('moveInput').value || '').trim() || '/');
  if (!moveTargets.length) return;
  var btn = $('moveConfirm');
  btn.disabled = true;
  var moved = 0, failed = 0;
  for (var i = 0; i < moveTargets.length; i++) {
    var src = moveTargets[i];
    var target = (dest === '/' ? '' : dest) + '/' + baseOf(src);
    if (target === src) { moved++; continue; }
    try {
      await api('/rename', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ oldPath: src, newPath: target })
      });
      moved++;
    } catch (e) { failed++; }
  }
  btn.disabled = false;
  if (failed) $('moveError').textContent = t('moveFail') + ' (' + failed + ')';
  else {
    toast(t('moveDone') + ': ' + moved, 'ok');
    closeMove();
    clearSelection();
    CACHE.clear();
    refresh();
  }
}

/* ─── Preview ────────────────────────────────────────────────────────── */
function previewUrl(name) {
  return '/api/download?path=' + encodeURIComponent(joinPath(currentPath, name)) + '&inline=1' +
    (isAdmin && adminToken ? '&token=' + encodeURIComponent(adminToken) : '');
}
function previewableFiles() {
  return view.filter(function (e) { return !e.isdir; });
}
function stepPreview(dir) {
  if (!previewEntry) return;
  var list = previewableFiles();
  if (list.length <= 1) return;
  var idx = -1;
  for (var i = 0; i < list.length; i++) {
    if (list[i].name === previewEntry.name) { idx = i; break; }
  }
  if (idx === -1) return;
  var next = (idx + dir + list.length) % list.length;
  previewFile(list[next]);
}
function previewFile(entry) {
  previewEntry = entry;
  var list = previewableFiles();
  var idx = -1;
  for (var i = 0; i < list.length; i++) {
    if (list[i].name === entry.name) { idx = i; break; }
  }
  var posStr = list.length > 1 && idx >= 0 ? ' · ' + (idx + 1) + '/' + list.length : '';
  $('prevTitle').textContent = entry.name;
  $('prevSub').textContent = fmtSize(entry.size) + ' · ' + fmtDate(entry.mtime) + posStr;
  $('prevGlyph').innerHTML = iconSvg(entry._kind);
  $('prevBody').innerHTML = '<div class="spin"></div>';
  $('prevDownload').onclick = function () { triggerDownload(downloadUrl(entry.name)); };
  var editBtn = $('prevEditBtn');
  if (editBtn) {
    editBtn.style.display = entry.editable ? '' : 'none';
    editBtn.onclick = function () {
      var p = joinPath(currentPath, entry.name);
      closePreview();
      editFile(p);
    };
  }
  if ($('prevPrevBtn')) $('prevPrevBtn').style.display = list.length > 1 ? '' : 'none';
  if ($('prevNextBtn')) $('prevNextBtn').style.display = list.length > 1 ? '' : 'none';
  openModal('prevBackdrop');
  var kind = entry._kind;
  var url = previewUrl(entry.name);
  if (kind === 'image') {
    $('prevBody').innerHTML = '<img src="' + esc(url) + '" alt="">';
    var img = $('prevBody').querySelector('img');
    if (img) img.onerror = prevFail;
  } else if (kind === 'video') {
    $('prevBody').innerHTML = '<video src="' + esc(url) + '" controls playsinline preload="metadata"></video>';
    var vid = $('prevBody').querySelector('video');
    if (vid) vid.onerror = prevFail;
  } else if (kind === 'audio') {
    $('prevBody').innerHTML = '<audio src="' + esc(url) + '" controls preload="metadata"></audio>';
  } else if (kind === 'pdf') {
    $('prevBody').innerHTML = '<iframe src="' + esc(url) + '" title="PDF"></iframe>';
  } else if (entry.editable && entry.size <= 2 * 1024 * 1024) {
    api('/text?path=' + encodeURIComponent(joinPath(currentPath, entry.name))).then(function (data) {
      if (previewEntry !== entry) return;
      $('prevBody').innerHTML = '<pre class="prev-text">' + esc(data.content || '') + '</pre>';
    }).catch(function () {
      $('prevBody').innerHTML = '<div class="prev-note">' + esc(t('previewFail')) + '</div>';
    });
  } else {
    $('prevBody').innerHTML = '<div class="prev-note">' + esc(t('downloadToView')) + '</div>';
  }
}
function prevFail() {
  $('prevBody').innerHTML = '<div class="prev-note">' + esc(t('previewFail')) + '<br>' + esc(t('downloadToView')) + '</div>';
}
function closePreview() {
  $('prevBody').innerHTML = '';
  previewEntry = null;
  closeModal('prevBackdrop');
}

/* ─── Shortcuts Help Sheet ───────────────────────────────────────────── */
function showHelp() { openModal('helpBackdrop'); }
function closeHelp() { closeModal('helpBackdrop'); }

/* ─── Confirm sheet ──────────────────────────────────────────────────── */
function askConfirm(opts) {
  opts = opts || {};
  return new Promise(function (resolve) {
    confirmResolve = resolve;
    $('confirmTitle').textContent = opts.title || t('confirmTitle');
    $('confirmSub').textContent = opts.sub || '';
    $('confirmMsg').textContent = opts.msg || '';
    var ok = $('confirmOk');
    ok.textContent = opts.okLabel || 'OK';
    ok.className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');
    $('confirmGlyph').style.background = opts.danger
      ? 'linear-gradient(150deg,#ff8080,#d43b3b)'
      : 'linear-gradient(150deg,var(--primary-2),var(--primary))';
    openModal('confirmBackdrop');
    setTimeout(function () { ok.focus(); }, 120);
  });
}
function closeConfirm(ok) {
  closeModal('confirmBackdrop');
  var r = confirmResolve;
  confirmResolve = null;
  if (r) r(!!ok);
}

/* ─── Action sheet ───────────────────────────────────────────────────── */
function closeActions() { closeModal('actBackdrop'); }
function openActions(entry) {
  actTarget = entry;
  $('actTitle').textContent = entry.name;
  $('actSub').textContent = (entry.isdir ? t('folders') : fmtSize(entry.size));
  $('actGlyph').innerHTML = iconSvg(entry._kind);
  var items = [];
  if (entry.isdir) {
    items.push(item('open', 'open', t('open')));
  } else {
    items.push(item('preview', 'preview', t('preview')));
    items.push(item('download', 'download', t('download')));
    if (entry.editable) items.push(item('edit', 'edit', t('edit')));
  }
  items.push(item('move', 'move', t('move')));
  items.push(item('rename', 'rename', t('rename')));
  items.push(item('copy', 'copy', t('copyPath')));
  items.push(item('select', 'select', t('select')));
  items.push(item('delete', 'delete', t('delete'), true));
  $('actList').innerHTML = items.join('');
  openModal('actBackdrop');
}
function item(act, icon, label, danger) {
  return '<button class="act-item' + (danger ? ' danger' : '') + '" type="button" data-do="' + act + '">' +
    '<span class="ai"><svg viewBox="0 0 24 24">' + (ACTION_ICONS[icon] || ACTION_ICONS.preview) + '</svg></span>' +
    '<span class="desc">' + esc(label) + '</span></button>';
}

/* ─── Upload ─────────────────────────────────────────────────────────── */
function pickFiles(folder) {
  (folder === true ? $('folderInput') : $('fileInput')).click();
}
function showUploadPill(pct, text) {
  var pill = $('uploadPill');
  if (!pill) return;
  if (pct == null) { pill.classList.remove('show'); return; }
  pill.classList.add('show');
  if ($('uploadPillText')) $('uploadPillText').textContent = text || t('uploading');
  if ($('uploadPillPct')) $('uploadPillPct').textContent = Math.max(0, Math.min(100, Math.round(pct))) + '%';
}

async function uploadFiles(files) {
  var list = Array.prototype.slice.call(files || []);
  if (!list.length) return;
  var batches = [], cur = [], curSize = 0;
  list.forEach(function (f) {
    if (cur.length && (cur.length >= 16 || curSize + f.size > 64 * 1024 * 1024)) {
      batches.push(cur); cur = []; curSize = 0;
    }
    cur.push(f); curSize += f.size;
  });
  if (cur.length) batches.push(cur);
  var totalBytes = list.reduce(function (s, f) { return s + f.size; }, 0) || 1;
  var doneBytes = 0, okCount = 0, failCount = 0;
  progress(4);
  showUploadPill(0, t('uploading') + ' (' + list.length + ')');
  for (var i = 0; i < batches.length; i++) {
    var batch = batches[i];
    var batchBytes = batch.reduce(function (s, f) { return s + f.size; }, 0);
    try {
      var result = await uploadBatch(batch, function (loaded) {
        var pct = ((doneBytes + loaded) / totalBytes) * 100;
        progress(pct);
        showUploadPill(pct, t('uploading') + ' (' + list.length + ')');
      });
      (result.files || []).forEach(function (f) { if (f.ok) okCount++; else failCount++; });
      if (!result.files) okCount += batch.length;
    } catch (e) {
      failCount += batch.length;
    }
    doneBytes += batchBytes;
    var batchPct = (doneBytes / totalBytes) * 100;
    progress(batchPct);
    showUploadPill(batchPct, t('uploading') + ' (' + list.length + ')');
  }
  showUploadPill(null);
  if (failCount) toast(t('uploadFail') + ' (' + failCount + ')', 'err');
  else toast(t('uploadDone') + ' · ' + okCount, 'ok');
  CACHE.delete(currentPath);
  refresh();
  $('fileInput').value = '';
  $('folderInput').value = '';
}

function uploadBatch(batch, onProgress) {
  return new Promise(function (resolve, reject) {
    var fd = new FormData();
    fd.append('path', currentPath);
    batch.forEach(function (f) { fd.append('file', f, f.webkitRelativePath || f.name); });
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    if (isAdmin && adminToken) xhr.setRequestHeader('Authorization', 'Bearer ' + adminToken);
    xhr.upload.onprogress = function (e) { if (e.lengthComputable) onProgress(e.loaded); };
    xhr.onload = function () {
      if (xhr.status !== 200) { reject(new Error('HTTP ' + xhr.status)); return; }
      try { resolve(JSON.parse(xhr.responseText)); } catch (e) { resolve({}); }
    };
    xhr.onerror = function () { reject(new Error('network')); };
    xhr.send(fd);
  });
}

/* ─── Modals ─────────────────────────────────────────────────────────── */
function openModal(id) {
  var el = $(id);
  if (!el) return;
  el.classList.add('open');
  var focusable = el.querySelector('textarea, input, .btn-primary, .close-x');
  if (focusable && !/input|textarea/i.test(focusable.tagName)) focusable.focus();
}
function closeModal(id) {
  var el = $(id);
  if (el) el.classList.remove('open');
}
function anyModalOpen() {
  return !!document.querySelector('.backdrop.open');
}
function closeTopModal() {
  var el = document.querySelector('.backdrop.open');
  if (!el) return false;
  var closeName = el.getAttribute('data-close');
  if (closeName === 'closeEdit') closeEdit();
  else if (closeName === 'closeDelModal') closeDelModal();
  else if (closeName === 'closeLogin') closeLogin();
  else if (closeName === 'closeActions') closeActions();
  else if (closeName === 'closeConfirm') closeConfirm(false);
  else if (closeName === 'closePreview') closePreview();
  else if (closeName === 'closeMove') closeMove();
  else if (closeName === 'closeHelp') closeHelp();
  else closeModal(el.id);
  return true;
}

/* ─── Admin ──────────────────────────────────────────────────────────── */
function showLogin() {
  $('loginUser').value = '';
  $('loginPass').value = '';
  $('loginError').textContent = '';
  openModal('loginBackdrop');
  setTimeout(function () { $('loginUser').focus(); }, 130);
}
function closeLogin() { closeModal('loginBackdrop'); }
async function doLogin() {
  var user = $('loginUser').value.trim();
  var pwd = $('loginPass').value;
  var btn = $('loginBtn');
  btn.disabled = true;
  try {
    var res = await fetch('/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: user, pass: pwd })
    });
    var data = await res.json();
    if (data.ok && data.token) {
      isAdmin = true;
      adminToken = data.token;
      localStorage.setItem('fb_admin_token', adminToken);
      closeLogin();
      applyAdminState();
      toast(t('adminOn'), 'ok');
      CACHE.clear();
      go('/', { force: true });
    } else {
      $('loginError').textContent = t('loginFailed');
    }
  } catch (e) {
    $('loginError').textContent = t('loginFailed');
  } finally { btn.disabled = false; }
}
async function doLogout() {
  try {
    await fetch('/api/logout', { method: 'POST', headers: authHeaders() });
  } catch (e) {}
  isAdmin = false;
  adminToken = '';
  localStorage.removeItem('fb_admin_token');
  applyAdminState();
  toast(t('adminOff'));
  CACHE.clear();
  go('/', { force: true });
}
function confirmLogout() {
  askConfirm({
    title: t('logoutConfirm'),
    sub: t('logoutSub'),
    okLabel: t('logoutOk'),
    danger: true
  }).then(function (ok) { if (ok) doLogout(); });
}
function applyAdminState() {
  var btn = $('adminBtn');
  btn.classList.toggle('on', isAdmin);
  btn.title = isAdmin ? t('logout') : t('adminBtn');
  btn.querySelector('.lbl').textContent = isAdmin ? t('logout') : t('adminBtn');
  btn.onclick = isAdmin ? confirmLogout : showLogin;
  $('statusPath').textContent = currentPath;
}
async function checkAuth() {
  if (!adminToken) { isAdmin = false; applyAdminState(); return; }
  try {
    var res = await fetch('/api/auth', { headers: authHeaders() });
    var data = await res.json();
    isAdmin = !!data.admin;
  } catch (e) { isAdmin = false; }
  if (!isAdmin) {
    adminToken = '';
    localStorage.removeItem('fb_admin_token');
  }
  applyAdminState();
}

/* ─── Events ─────────────────────────────────────────────────────────── */
function bind() {
  $('brandHome').onclick = function () { go(isAdmin ? '/' : '/'); };
  $('btnUp').onclick = goUp;
  $('btnRefresh').onclick = refresh;
  $('btnUpload').onclick = function () { pickFiles(false); };
  $('btnUploadMenu').onclick = function (e) {
    e.stopPropagation();
    $('uploadMenu').classList.toggle('open');
  };
  $('uploadMenu').addEventListener('click', function (e) {
    var b = e.target.closest('[data-pick]');
    if (!b) return;
    $('uploadMenu').classList.remove('open');
    pickFiles(b.getAttribute('data-pick') === 'folder');
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.upload-split')) $('uploadMenu').classList.remove('open');
  });
  $('fabUpload').onclick = pickFiles;
  $('emptyUpload').onclick = pickFiles;
  $('fileInput').addEventListener('change', function () { if (this.files.length) uploadFiles(this.files); });
  $('folderInput').addEventListener('change', function () { if (this.files.length) uploadFiles(this.files); });
  $('btnSelect').onclick = function () {
    if (selectMode) clearSelection();
    else enterSelect(null);
  };
  if ($('pickAllBtn')) $('pickAllBtn').onclick = toggleSelectAll;
  if ($('selAllBtn')) $('selAllBtn').onclick = toggleSelectAll;
  if ($('viewListBtn')) $('viewListBtn').onclick = function () { applyViewMode('list'); };
  if ($('viewGridBtn')) $('viewGridBtn').onclick = function () { applyViewMode('grid'); };
  if ($('helpBtn')) $('helpBtn').onclick = showHelp;
  if ($('prevPrevBtn')) $('prevPrevBtn').onclick = function () { stepPreview(-1); };
  if ($('prevNextBtn')) $('prevNextBtn').onclick = function () { stepPreview(1); };
  if ($('editWrapBtn')) $('editWrapBtn').onclick = toggleEditWrap;

  $('btnSort').onclick = function (e) {
    e.stopPropagation();
    $('sortMenu').classList.toggle('open');
  };
  $('sortMenu').addEventListener('click', function (e) {
    var b = e.target.closest('[data-sort]');
    if (!b) return;
    setSort(+b.getAttribute('data-sort'));
    $('sortMenu').classList.remove('open');
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.sort-wrap')) $('sortMenu').classList.remove('open');
  });
  $('selClear').onclick = clearSelection;
  $('selDelete').onclick = deleteSelected;
  $('selMove').onclick = function () { openMove(selectedEntries()); };
  $('moveConfirm').onclick = confirmMove;
  $('confirmOk').onclick = function () { closeConfirm(true); };

  $('btnNewFolder').onclick = newFolderModal;
  $('btnNewFile').onclick = newFileModal;

  $('themeToggle').onclick = function () {
    localStorage.setItem('fb_theme', getTheme() === 'dark' ? 'light' : 'dark');
    applyTheme();
  };
  $('langToggle').onclick = function () {
    lang = lang === 'zh' ? 'en' : 'zh';
    localStorage.setItem('fb_lang', lang);
    applyLang();
  };
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if (!localStorage.getItem('fb_theme')) applyTheme();
  });

  $('sortName').onclick = function () { setSort(0); };
  $('sortSize').onclick = function () { setSort(1); };
  $('sortDate').onclick = function () { setSort(2); };

  var searchTimer = 0;
  var box = $('searchBox');
  box.addEventListener('input', function () {
    $('searchWrap').classList.toggle('has-value', !!box.value);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      buildView();
      updateStatus();
      $('listBody').scrollTop = 0;
      renderList(true);
    }, 90);
  });
  box.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { box.value = ''; box.dispatchEvent(new Event('input')); box.blur(); }
  });
  $('searchClear').onclick = function () { box.value = ''; box.dispatchEvent(new Event('input')); box.focus(); };

  $('listBody').addEventListener('scroll', function () {
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(function () { scrollRaf = 0; renderWindow(false); });
  }, { passive: true });

  $('breadcrumb').addEventListener('click', function (e) {
    var el = e.target.closest('[data-nav]');
    if (el) go(el.getAttribute('data-nav'));
  });
  $('chips').addEventListener('click', function (e) {
    var el = e.target.closest('[data-nav]');
    if (el) go(el.getAttribute('data-nav'));
  });
  if ($('catChips')) {
    $('catChips').addEventListener('click', function (e) {
      var btn = e.target.closest('[data-cat]');
      if (!btn) return;
      catFilter = btn.getAttribute('data-cat') || 'all';
      $('catChips').querySelectorAll('[data-cat]').forEach(function (b) {
        b.classList.toggle('active', b === btn);
      });
      buildView();
      updateStatus();
      $('listBody').scrollTop = 0;
      rangeStart = -1; rangeEnd = -1;
      renderList(true);
    });
  }

  $('vRows').addEventListener('click', function (e) {
    var rowEl = e.target.closest('.row');
    if (!rowEl) return;
    var entry = findEntry(+rowEl.getAttribute('data-idx'));
    if (!entry) return;
    if (longPressed) { longPressed = false; return; }
    var el = e.target.closest('[data-act]');
    var act = el ? el.getAttribute('data-act') : '';
    var path = joinPath(currentPath, entry.name);
    if (act === 'pick') { togglePick(entry); return; }
    if (selectMode) { togglePick(entry); return; }
    if (act === 'sheet') { openActions(entry); return; }
    if (act === 'download') { triggerDownload(downloadUrl(entry.name)); return; }
    if (act === 'edit') { editFile(path); return; }
    if (act === 'rename') { renameItem(path); return; }
    if (act === 'delete') { deleteItem(path, entry.isdir); return; }
    if (act === 'nav' || (entry.isdir && !act)) { go(path + '/'); return; }
    if (act === 'preview' || !act) { previewFile(entry); }
  });

  var rowsEl = $('vRows');
  rowsEl.addEventListener('pointerdown', function (e) {
    if (e.pointerType === 'mouse') return;
    if (e.target.closest('.c-acts')) return;
    var row = e.target.closest('.row');
    if (!row) return;
    pressRow = findEntry(+row.getAttribute('data-idx'));
    pressStart = { x: e.clientX, y: e.clientY };
    longPressed = false;
    clearTimeout(pressTimer);
    pressTimer = setTimeout(function () {
      if (!pressRow) return;
      longPressed = true;
      enterSelect(pressRow);
      if (navigator.vibrate) { try { navigator.vibrate(12); } catch (err) {} }
    }, 430);
  }, { passive: true });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (evt) {
    rowsEl.addEventListener(evt, function () {
      clearTimeout(pressTimer);
      pressRow = null;
      pressStart = null;
      setTimeout(function () { longPressed = false; }, 60);
    }, { passive: true });
  });
  rowsEl.addEventListener('pointermove', function (e) {
    if (!pressStart) return;
    if (Math.abs(e.clientX - pressStart.x) > 12 || Math.abs(e.clientY - pressStart.y) > 12) {
      clearTimeout(pressTimer);
      pressStart = null;
    }
  }, { passive: true });

  $('actList').addEventListener('click', function (e) {
    var btn = e.target.closest('[data-do]');
    if (!btn || !actTarget) return;
    var entry = actTarget;
    var path = joinPath(currentPath, entry.name);
    var doIt = btn.getAttribute('data-do');
    closeActions();
    if (doIt === 'open') go(path + '/');
    else if (doIt === 'preview') previewFile(entry);
    else if (doIt === 'download') triggerDownload(downloadUrl(entry.name));
    else if (doIt === 'edit') editFile(path);
    else if (doIt === 'move') openMove([entry]);
    else if (doIt === 'rename') renameItem(path);
    else if (doIt === 'copy') copyText(path);
    else if (doIt === 'select') enterSelect(entry);
    else if (doIt === 'delete') deleteItem(path, entry.isdir);
  });

  $('editSave').onclick = saveEdit;
  $('editContent').addEventListener('input', markDirty);
  ['click', 'keyup', 'select'].forEach(function (ev) {
    $('editContent').addEventListener(ev, updateEditCursor);
  });
  $('editContent').addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveEdit(); }
    if (e.key === 'Tab') {
      e.preventDefault();
      var s = this.selectionStart, en = this.selectionEnd;
      this.value = this.value.slice(0, s) + '  ' + this.value.slice(en);
      this.selectionStart = this.selectionEnd = s + 2;
      markDirty();
    }
  });

  $('nameConfirmBtn').onclick = confirmName;
  $('nameInput').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); confirmName(); }
  });
  $('delConfirm').onclick = confirmDel;
  $('loginBtn').onclick = doLogin;
  $('loginPass').addEventListener('keydown', function (e) { if (e.key === 'Enter') doLogin(); });
  $('loginUser').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') $('loginPass').focus();
  });

  document.querySelectorAll('[data-close]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (e.target !== el && el.classList.contains('backdrop')) return;
      var fn = el.getAttribute('data-close');
      if (fn === 'closeEdit') closeEdit();
      else if (fn === 'closeNameModal') closeNameModal();
      else if (fn === 'closeDelModal') closeDelModal();
      else if (fn === 'closeLogin') closeLogin();
      else if (fn === 'closeActions') closeActions();
      else if (fn === 'closeConfirm') closeConfirm(false);
      else if (fn === 'closePreview') closePreview();
      else if (fn === 'closeMove') closeMove();
      else if (fn === 'closeHelp') closeHelp();
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (closeTopModal()) return;
      if (selectMode) { clearSelection(); return; }
      if (document.activeElement === $('searchBox')) return;
      if ($('searchBox').value) { $('searchBox').value = ''; $('searchWrap').classList.remove('has-value'); buildView(); renderList(true); }
      return;
    }
    if ($('prevBackdrop') && $('prevBackdrop').classList.contains('open')) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); stepPreview(-1); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); stepPreview(1); return; }
    }
    if (anyModalOpen()) return;
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    var inField = /input|textarea|select/i.test(tag);
    var k = e.key.toLowerCase();
    if ((e.metaKey || e.ctrlKey) && k === 'a' && !inField) {
      e.preventDefault();
      enterSelect(null);
      view.forEach(function (x) { selection.add(x.name); });
      updateSelBar();
      renderWindow(true);
      return;
    }
    if (inField) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (k === '/') { e.preventDefault(); $('searchBox').focus(); }
    else if (e.key === '?') { e.preventDefault(); showHelp(); }
    else if (k === 'g') { e.preventDefault(); applyViewMode(viewMode === 'grid' ? 'list' : 'grid'); }
    else if (k === 'u') { e.preventDefault(); pickFiles(); }
    else if (k === 'n') { e.preventDefault(); newFolderModal(); }
    else if (k === 'r') { e.preventDefault(); refresh(); }
    else if (k === 's') { e.preventDefault(); if (selectMode) clearSelection(); else enterSelect(null); }
    else if (k === 'backspace') { e.preventDefault(); goUp(); }
  });

  // Drag & drop
  window.addEventListener('dragenter', function (e) {
    if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') === -1) return;
    e.preventDefault();
    dragDepth++;
    $('dropOverlay').classList.add('on');
  });
  window.addEventListener('dragover', function (e) { if (e.dataTransfer) e.preventDefault(); });
  window.addEventListener('dragleave', function (e) {
    e.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) $('dropOverlay').classList.remove('on');
  });
  window.addEventListener('drop', function (e) {
    e.preventDefault();
    dragDepth = 0;
    $('dropOverlay').classList.remove('on');
    if (e.dataTransfer && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  document.addEventListener('contextmenu', function (e) {
    if (e.target.closest('.row')) e.preventDefault();
  });

  window.addEventListener('popstate', function () {
    var p = new URLSearchParams(location.search).get('path') || '/';
    currentPath = normPath(p);
    $('listBody').scrollTop = 0;
    rangeStart = -1; rangeEnd = -1;
    loadDir(currentPath, { soft: true });
  });

  var resizeTimer = 0;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { renderWindow(true); }, 120);
  });

}

function setSort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  localStorage.setItem('fb_sort_col', String(sortCol));
  localStorage.setItem('fb_sort_asc', sortAsc ? '1' : '0');
  buildView();
  updateSortHeaders();
  $('listBody').scrollTop = 0;
  renderList(true);
}

/* ─── Init ───────────────────────────────────────────────────────────── */
function init() {
  applyTheme();
  applyLang();
  if ($('viewListBtn')) $('viewListBtn').classList.toggle('active', viewMode === 'list');
  if ($('viewGridBtn')) $('viewGridBtn').classList.toggle('active', viewMode === 'grid');
  if ($('vRows')) $('vRows').classList.toggle('grid-mode', viewMode === 'grid');
  bind();
  measureRow();
  loadStats();
  var startPath = normPath(new URLSearchParams(location.search).get('path') || '/');
  currentPath = startPath;
  checkAuth().then(function () {
    loadDir(startPath, { soft: false, transition: true });
  });
}

return {
  init: init,
  go: go, goUp: goUp, refresh: refresh, sort: setSort,
  editFile: editFile, saveEdit: saveEdit, closeEdit: closeEdit,
  deleteItem: deleteItem, closeDelModal: closeDelModal, confirmDel: confirmDel,
  renameItem: renameItem, newFolderModal: newFolderModal, newFileModal: newFileModal,
  closeNameModal: closeNameModal, confirmName: confirmName,
  uploadFiles: uploadFiles, showLogin: showLogin, closeLogin: closeLogin,
  doLogin: doLogin, doLogout: doLogout, closeActions: closeActions,
  toggleTheme: function () { localStorage.setItem('fb_theme', getTheme() === 'dark' ? 'light' : 'dark'); applyTheme(); }
};
})();

App.init();
</script>
</body>
</html>
"""

# Pre-encode the UI once instead of re-encoding ~90 KB on every page load.
# A gzip copy is produced on first request and reused; the ETag lets a repeat
# visit cost a single empty 304 response.
_INDEX_BYTES = INDEX_HTML.encode("utf-8")
_INDEX_ETAG = '"fb-%s"' % hashlib.sha1(_INDEX_BYTES).hexdigest()[:16]
_INDEX_GZIP = None
_INDEX_GZIP_LOCK = threading.Lock()


def _index_gzip():
    global _INDEX_GZIP
    if _INDEX_GZIP is None:
        with _INDEX_GZIP_LOCK:
            if _INDEX_GZIP is None:
                _INDEX_GZIP = gzip.compress(_INDEX_BYTES, 6)
    return _INDEX_GZIP


# ── Server handler ───────────────────────────────────────────────────────

# Extensions that should never be opened in the text editor. This is used for
# two different things:
#   * ``_BINARY_EXTS``  — hard "never show an editor button" list.
#   * ``_is_editable``  — cheap, I/O-free decision used while listing a folder.
# Listing used to open every file and read 8 KB just to answer "is this text?",
# which made folders with a few thousand files crawl on a phone. The extension
# check below costs nothing; the content sniff still runs when the editor opens
# a file (``/api/text``), so a mislabelled binary can never be corrupted.
_BINARY_EXTS = {
    '.apk','.aab','.apks','.xapk','.zip','.gz','.tar','.tgz','.rar','.7z','.bz2','.xz','.zst',
    '.jpg','.jpeg','.png','.gif','.webp','.bmp','.ico','.heic','.heif','.avif','.tif','.tiff',
    '.dng','.raw','.psd','.ai','.sketch','.fig',
    '.mp3','.mp4','.ogg','.oga','.opus','.wav','.flac','.aac','.m4a','.m4v','.mkv','.avi',
    '.mov','.webm','.3gp','.flv','.wmv','.mpg','.mpeg','.ts','.amr','.mid','.midi',
    '.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.odt','.ods','.odp',
    '.exe','.dll','.so','.o','.a','.pyc','.pyo','.class','.dex','.jar','.war','.wasm',
    '.db','.sqlite','.sqlite3','.realm','.iso','.img','.bin','.dat','.obb','.ttf','.otf',
    '.woff','.woff2','.eot','.ttc','.pak','.unity3d','.blend','.stl','.obj',
}

_EDIT_MAX_BYTES = 5 * 1024 * 1024


def _is_editable(name, size, isdir):
    """I/O-free guess: can the text editor open this entry?"""
    if isdir or size > _EDIT_MAX_BYTES:
        return False
    _, ext = os.path.splitext(name)
    return ext.lower() not in _BINARY_EXTS


def _listdir_entries(full):
    """Fast directory listing using a single scandir pass (no extra stat calls).

    ``os.scandir`` caches the stat data returned by the kernel, so this is
    roughly one syscall per entry instead of ``stat`` + ``open`` + ``read``.
    """
    entries = []
    with os.scandir(full) as it:
        for de in it:
            try:
                st = de.stat(follow_symlinks=True)
            except OSError:
                continue
            is_dir = stat.S_ISDIR(st.st_mode)
            size = 0 if is_dir else int(st.st_size)
            entries.append({
                "name": de.name,
                "isdir": is_dir,
                "size": size,
                "mtime": int(st.st_mtime),
                "editable": _is_editable(de.name, size, is_dir),
            })
    return entries


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
        if auth.startswith("Bearer ") and self._token_valid(auth[7:]):
            return True
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            token = qs.get("token", [""])[0]
        except Exception:
            token = ""
        return bool(token) and self._token_valid(token)

    @staticmethod
    def _token_valid(token):
        """Check a session token and drop it once its TTL has elapsed."""
        exp = ADMIN_TOKENS.get(token)
        if not exp:
            return False
        if exp < time.time():
            ADMIN_TOKENS.pop(token, None)
            return False
        return True

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
        """List a directory for an admin session.

        In module mode the server already runs as root, so a plain scandir is
        both correct and dramatically faster than shelling out. The old code
        spawned ``su`` plus ``base64``/``stat`` for *every* entry, which is why
        admin mode felt slow in big folders. The shell path below is now only a
        last resort for directories this process genuinely cannot read.
        """
        try:
            return _listdir_entries(path)
        except FileNotFoundError:
            return []
        except PermissionError:
            pass
        except OSError:
            pass

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
            entries.append({
                "name": name,
                "isdir": is_dir,
                "size": size,
                "mtime": mtime,
                "editable": _is_editable(name, size, is_dir),
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
        # Never write admin tokens to disk, even at debug level.
        msg = re.sub(r"token=[^&\s\"]+", "token=***", msg)
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

        # Homepage / UI — gzip + ETag so a repeat visit costs one tiny 304.
        if parsed.path == "/" or parsed.path == "/index.html":
            return self._serve_index()

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
                    entries = _listdir_entries(full)
            except PermissionError:
                return self._json_error(403, "Permission denied")
            except OSError as e:
                self.log_message("ERROR: %s", e)
                return self._json_error(500, "Internal error")
            # ``compact=1`` returns positional arrays, which roughly halves the
            # payload and JSON parse time for very large folders. The embedded
            # UI always uses it; the documented default stays the object format.
            if qs.get("compact", ["0"])[0] in ("1", "true", "yes"):
                entries = [[e["name"], 1 if e["isdir"] else 0, e["size"],
                            e["mtime"], 1 if e["editable"] else 0] for e in entries]
            self._json_response(200, {"entries": entries})
            return

        # API: read a text file for the editor. Doing the binary/size guard here
        # (instead of while listing) keeps directory listings I/O free.
        if parsed.path == "/api/text":
            path = qs.get("path", [""])[0]
            full = self._resolve(path)
            if not full:
                return self._json_error(403, "Path not allowed")
            if os.path.isdir(full):
                return self._json_error(400, "Is a directory")
            try:
                size = os.path.getsize(full)
            except OSError:
                return self._json_error(404, "File not found")
            if size > _EDIT_MAX_BYTES:
                return self._json_error(413, "File too large for the editor")
            if _is_binary(full):
                return self._json_error(415, "Binary file cannot be edited")
            try:
                if self._is_admin() and not os.access(full, os.R_OK):
                    code, out, _ = self._su_exec("cat " + shlex.quote(full), timeout=30)
                    if code != 0:
                        return self._json_error(403, "Permission denied")
                    raw = out
                else:
                    with open(full, "rb") as f:
                        raw = f.read(_EDIT_MAX_BYTES + 1)
            except PermissionError:
                return self._json_error(403, "Permission denied")
            except OSError:
                return self._json_error(404, "File not found")
            if len(raw) > _EDIT_MAX_BYTES:
                return self._json_error(413, "File too large for the editor")
            if b"\x00" in raw:
                return self._json_error(415, "Binary file cannot be edited")
            text = raw.decode("utf-8", errors="replace")
            self._json_response(200, {"content": text, "size": size})
            return

        # API: download file (``inline=1`` is used by the preview sheet)
        if parsed.path == "/api/download":
            path = qs.get("path", [""])[0]
            full = self._resolve(path)
            if not full:
                return self._json_error(403, "Path not allowed")
            inline = qs.get("inline", ["0"])[0] in ("1", "true", "yes")
            return self._serve_download(full, inline)

        # API: storage stats for the status bar
        if parsed.path == "/api/stats":
            root = self._get_root()
            try:
                usage = shutil.disk_usage(root)
                payload = {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "root": root,
                }
                self._json_response(200, payload)
            except OSError as e:
                self._json_error(500, str(e))
            return

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
                # Prune expired sessions so the in-memory store cannot grow
                # without bound on a long-running server.
                now = time.time()
                for old, exp in list(ADMIN_TOKENS.items()):
                    if exp < now:
                        ADMIN_TOKENS.pop(old, None)
                ADMIN_TOKENS[token] = now + ADMIN_TOKEN_TTL
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
                self._fs_write_bytes(full, content.encode("utf-8"))
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        # API: delete (single path, or a batch via {"paths": [...]})
        if parsed.path == "/api/delete":
            data = self._json_body(_META_BODY_LIMIT * 16)
            if data is None:
                return
            raw_paths = data.get("paths")
            if not isinstance(raw_paths, list):
                raw_paths = [data.get("path", "")]
            root_real = os.path.realpath(self._get_root())
            results = []
            for raw in raw_paths[:500]:
                full = self._resolve(raw or "")
                if not full:
                    results.append({"path": raw, "ok": False, "error": "Path not allowed"})
                    continue
                if full == root_real:
                    results.append({"path": raw, "ok": False,
                                    "error": "Refusing to delete the root directory"})
                    continue
                try:
                    self._fs_delete(full)
                    results.append({"path": raw, "ok": True})
                except Exception as e:
                    results.append({"path": raw, "ok": False, "error": str(e)})
            if "paths" in data:
                self._json_response(200, {"ok": True, "results": results})
            elif results and results[0]["ok"]:
                self._json_response(200, {"ok": True})
            else:
                err = results[0]["error"] if results else "Delete failed"
                self._json_error(500, err)
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
                self._fs_mkdir(full)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        # API: rename / move
        if parsed.path == "/api/rename":
            data = self._json_body(_META_BODY_LIMIT)
            if data is None:
                return
            old = self._resolve(data.get("oldPath", ""))
            new = self._resolve(data.get("newPath", ""))
            if not old or not new:
                return self._json_error(403, "Path not allowed")
            if old == os.path.realpath(self._get_root()):
                return self._json_error(400, "Refusing to move the root directory")
            try:
                self._fs_rename(old, new)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self.log_message("ERROR: %s", e)
                self._json_error(500, "Internal error")
            return

        self._json_error(404, "Unknown endpoint")

    # ── Helpers ──────────────────────────────────────────────────────────
    def _fs_write_bytes(self, full, payload):
        """Write bytes directly when possible, falling back to ``su``.

        The server runs as root in module mode, so spawning a shell for every
        save/upload is pure overhead. Only escalate when the direct write
        genuinely fails with a permission error.
        """
        try:
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full, "wb") as f:
                f.write(payload)
            return
        except OSError:
            if not self._is_admin():
                raise
        qfull = shlex.quote(full)
        qdir = shlex.quote(os.path.dirname(full) or "/")
        code, _, stderr = self._su_exec(
            "mkdir -p " + qdir + " && cat > " + qfull,
            input_data=payload, timeout=120)
        if code != 0:
            raise OSError(stderr.decode(errors="replace").strip() or "write failed")

    def _fs_mkdir(self, full):
        try:
            os.makedirs(full, exist_ok=True)
            return
        except OSError:
            if not self._is_admin():
                raise
        code, _, stderr = self._su_exec("mkdir -p " + shlex.quote(full), timeout=15)
        if code != 0:
            raise OSError(stderr.decode(errors="replace").strip() or "mkdir failed")

    def _fs_delete(self, full):
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            return
        except OSError:
            if not self._is_admin():
                raise
        code, _, stderr = self._su_exec("rm -rf " + shlex.quote(full), timeout=60)
        if code != 0:
            raise OSError(stderr.decode(errors="replace").strip() or "delete failed")

    def _fs_rename(self, old, new):
        try:
            parent = os.path.dirname(new)
            if parent:
                os.makedirs(parent, exist_ok=True)
            os.replace(old, new)
            return
        except OSError:
            if not self._is_admin():
                raise
        qdir = shlex.quote(os.path.dirname(new) or "/")
        code, _, stderr = self._su_exec(
            "mkdir -p " + qdir + " && mv -f " + shlex.quote(old) + " " + shlex.quote(new),
            timeout=60)
        if code != 0:
            raise OSError(stderr.decode(errors="replace").strip() or "rename failed")

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
    def _content_disposition(fname, inline=False):
        """Build an RFC 6266 / RFC 5987 compliant Content-Disposition value."""
        try:
            ascii_fname = fname.encode('ascii', 'replace').decode('ascii')
        except Exception:
            ascii_fname = "download"
        ascii_fname = ascii_fname.replace('"', '').replace('\\', '')
        if not ascii_fname:
            ascii_fname = "download"
        return "%s; filename=\"%s\"; filename*=UTF-8''%s" % (
            "inline" if inline else "attachment",
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

    def _serve_download(self, full, inline=False):
        """Stream a file with HTTP range support.

        ``inline=True`` uses ``Content-Disposition: inline`` so the preview
        sheet can play video/audio and show images in place.
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
                return self._serve_download_via_su(full, fname, ctype, inline)
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
            self.send_header("Content-Disposition",
                             self._content_disposition(fname, inline))
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

    def _serve_download_via_su(self, full, fname, ctype, inline=False):
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
        self.send_header("Content-Disposition",
                         self._content_disposition(fname, inline))
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
        """Parse multipart form-data and write the files.

        The body is spooled to a temp file (memory up to 16 MB, disk after
        that) and then memory-mapped, so a 100 MB upload no longer needs two
        or three full copies resident in RAM — important on a phone.
        """
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

        spool = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
        data = b""
        try:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                spool.write(chunk)
                remaining -= len(chunk)
            if remaining:
                return self._json_error(400, "Incomplete request body")
            if length:
                spool.seek(0)
                try:
                    data = mmap.mmap(spool.fileno(), 0, access=mmap.ACCESS_READ)
                except (OSError, ValueError):
                    spool.seek(0)
                    data = spool.read()
            return self._parse_upload_body(data, boundary)
        finally:
            try:
                if hasattr(data, "close"):
                    data.close()
            except Exception:
                pass
            try:
                spool.close()
            except Exception:
                pass

    def _parse_upload_body(self, data, boundary):
        """Split a multipart body and persist the file parts."""
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
        root_real = os.path.realpath(self._get_root())
        files_uploaded = []
        for filename, body in files:
            # Preserve folder structure for directory uploads while stripping
            # any traversal components from the client-supplied path.
            segs = [p.replace("\x00", "") for p in filename.replace("\\", "/").split("/")
                    if p and p not in (".", "..")]
            if not segs:
                continue
            fn = segs[-1]
            if not fn:
                continue
            rel = os.path.join(*segs)
            dest = os.path.join(dest_dir, rel)
            if not _under_root(root_real, os.path.realpath(dest)):
                return self._json_error(403, "Path not allowed")
            try:
                self._fs_write_bytes(dest, bytes(body))
            except Exception as e:
                files_uploaded.append({
                    "name": fn, "ok": False, "error": str(e) or "write failed",
                })
                continue
            files_uploaded.append({"name": fn, "ok": True})

        self._json_response(200, {"ok": True, "files": files_uploaded})

    def _serve_index(self):
        """Serve the embedded UI with ETag + gzip."""
        if self.headers.get("If-None-Match", "") == _INDEX_ETAG:
            self.send_response(304)
            self.send_header("ETag", _INDEX_ETAG)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            return
        use_gzip = "gzip" in self.headers.get("Accept-Encoding", "").lower()
        body = _index_gzip() if use_gzip else _INDEX_BYTES
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", _INDEX_ETAG)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json_response(self, code, data):
        body = json.dumps(data, separators=(",", ":")).encode()
        use_gzip = len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "").lower()
        if use_gzip:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

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
