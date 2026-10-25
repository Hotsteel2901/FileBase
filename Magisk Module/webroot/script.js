/* ═══════════════════════════════════════════════════════════════════════
   FileBase WebUI — Material Design 3 Expressive × Liquid Glass
   Follows the KernelSU module guide:
     • entry point is webroot/index.html, assets live next to it
     • shell access goes through the official `kernelsu` library:
         const { errno, stdout, stderr } = await exec(cmd)
     • module settings are stored with `ksud module config`, with a
       plain-file fallback for Magisk / APatch
     • `moduleInfo()` supplies the module directory instead of hard-coding
   ═══════════════════════════════════════════════════════════════════════ */

import { exec, toast as nativeToast, moduleInfo } from './kernelsu.js';

const $ = (id) => document.getElementById(id);

/* ─── API availability ─────────────────────────────────────────────────── */
const HAS_API =
  typeof window.ksu !== 'undefined' &&
  typeof window.ksu.exec === 'function';

/* ─── Theme ────────────────────────────────────────────────────────────── */
const THEME_KEY = 'fb_wui_theme';
function systemTheme() {
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function currentTheme() {
  return (
    localStorage.getItem(THEME_KEY) ||
    document.documentElement.getAttribute('data-theme') ||
    systemTheme()
  );
}
const SUN_SVG =
  '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4l1.4-1.4M18 6l1.4-1.4"/></svg>';
const MOON_SVG =
  '<svg viewBox="0 0 24 24"><path d="M20.2 13.6A8.6 8.6 0 0 1 10.4 3.8a8.6 8.6 0 1 0 9.8 9.8z"/></svg>';
function applyTheme() {
  const t = currentTheme();
  document.documentElement.setAttribute('data-theme', t);
  const icon = $('themeIcon');
  if (icon) icon.innerHTML = t === 'dark' ? SUN_SVG : MOON_SVG;
}
function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (_) {}
  applyTheme();
}
try {
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!localStorage.getItem(THEME_KEY)) applyTheme();
  });
} catch (_) {}

/* ─── i18n ─────────────────────────────────────────────────────────────── */
const I18N = {
  en: {
    subtitle: 'Control panel',
    statusChecking: 'Checking…',
    statusRunning: 'Server running',
    statusStopped: 'Server stopped',
    statusUnknown: 'Status unknown',
    statusHintIdle: 'Querying module daemon…',
    statusHintOn: 'Serving /sdcard over local hotspot',
    statusHintOff: 'Tap Start below to launch the file server',
    kPid: 'PID', kAddress: 'Address', kIface: 'Interface', kLogLevel: 'Log level', kPort: 'Port',
    copy: 'Copy', open: 'Open', copied: 'Copied', clear: 'Clear', qrBtn: 'QR',
    qrTitle: 'Scan on any device on the hotspot',
    qrDesc: 'Connect your laptop, tablet or another phone to the same Wi-Fi hotspot, then scan or type the URL above.',
    controls: 'Controls',
    startBtn: 'Start', stopBtn: 'Stop', restartBtn: 'Restart', refreshBtn: 'Refresh', wrapBtn: 'Wrap',
    logLevel: 'Log level',
    lvlInfo: 'Info — requests + status',
    lvlError: 'Error — 4xx/5xx only',
    lvlDebug: 'Debug — full details',
    lvlOff: 'Off — no logging',
    logLevelHint: "Saved through KernelSU's module config system; restart the server to apply.",
    output: 'Output',
    logsTitle: 'Server logs',
    logsHint: 'Last 120 lines of logs/server.log',
    logFilterPlaceholder: 'Filter logs…',
    filterAll: 'All', filterErr: '4xx / 5xx', filterOk: '2xx / 3xx',
    aboutTitle: 'About',
    navControl: 'Control', navLogs: 'Logs', navAbout: 'About',
    fallbackTitle: 'WebUI API unavailable',
    fallbackText: 'This page must be opened from the KernelSU Manager (or another WebUI host). You can still control the module from a terminal:',
    busy: 'Working…',
    failed: 'Failed',
    started: 'Server started', stopped: 'Server stopped', restarted: 'Server restarted',
    logSaved: 'Log level saved',
    noLog: 'No log file yet.',
    noLogMatch: 'No log lines match the current filter.',
    apiReady: 'API ready',
    apiMissing: 'API missing',
    copyOk: 'Copied',
    aboutIntro: "Serves <code>/sdcard</code> over the phone's hotspot. Browse, upload, download and edit files from any device that is connected to it.",
    aboutQuickStart: 'Quick start',
    aboutStep1: 'Turn on the phone hotspot.',
    aboutStep2: 'Tap <b>Start</b> here.',
    aboutStep3: 'Scan the QR code or open the shown address on another device.',
    aboutStep4: 'Tap <b>Stop</b> to shut the server down.',
    aboutCli: 'Terminal commands',
    aboutCliHint: 'Tap a command to copy it.',
    aboutSettings: 'Where settings are stored',
    aboutSettingsText: 'The log level is saved with <code>ksud module config set log_level …</code> on KernelSU (see the module config guide). On Magisk / APatch it falls back to <code>logs/.config</code>. Both are read by <code>action.sh</code> on every start.',
    aboutLogLevels: 'Log levels',
    aboutLevelInfo: '<b>Info</b> — client IP, method, status',
    aboutLevelError: '<b>Error</b> — only 4xx / 5xx',
    aboutLevelDebug: '<b>Debug</b> — timestamp, IP:port, method, path',
    aboutLevelOff: '<b>Off</b> — no log output',
    aboutLicense: 'License: MIT',
  },
  zh: {
    subtitle: '控制面板',
    statusChecking: '检测中…',
    statusRunning: '服务器运行中',
    statusStopped: '服务器已停止',
    statusUnknown: '状态未知',
    statusHintIdle: '正在查询模块后台状态…',
    statusHintOn: '正通过本机热点共享 /sdcard',
    statusHintOff: '点击下方“启动”按钮开启文件服务器',
    kPid: '进程号', kAddress: '访问地址', kIface: '网卡', kLogLevel: '日志级别', kPort: '端口',
    copy: '复制', open: '打开', copied: '已复制', clear: '清空', qrBtn: '二维码',
    qrTitle: '使用热点内任意设备扫码连接',
    qrDesc: '将电脑、平板或另一部手机连接到同一 Wi-Fi 热点，扫码或输入上方地址即可管理文件。',
    controls: '控制',
    startBtn: '启动', stopBtn: '停止', restartBtn: '重启', refreshBtn: '刷新', wrapBtn: '换行',
    logLevel: '日志级别',
    lvlInfo: 'Info — 记录请求与状态码',
    lvlError: 'Error — 仅 4xx/5xx',
    lvlDebug: 'Debug — 完整详情',
    lvlOff: 'Off — 不输出日志',
    logLevelHint: '通过 KernelSU 模块配置系统保存；重启服务器后生效。',
    output: '输出',
    logsTitle: '服务器日志',
    logsHint: 'logs/server.log 最后 120 行',
    logFilterPlaceholder: '搜索过滤日志…',
    filterAll: '全部', filterErr: '4xx / 5xx', filterOk: '2xx / 3xx',
    aboutTitle: '关于',
    navControl: '控制', navLogs: '日志', navAbout: '关于',
    fallbackTitle: 'WebUI API 不可用',
    fallbackText: '本页面需要在 KernelSU 管理器（或其他 WebUI 宿主）中打开。你仍然可以用终端控制模块：',
    busy: '执行中…',
    failed: '失败',
    started: '服务器已启动', stopped: '服务器已停止', restarted: '服务器已重启',
    logSaved: '日志级别已保存',
    noLog: '暂无日志文件。',
    noLogMatch: '没有符合筛选条件的日志行。',
    apiReady: 'API 就绪',
    apiMissing: 'API 不可用',
    copyOk: '已复制',
    aboutIntro: '通过手机热点共享 <code>/sdcard</code>，任何连接该热点的设备都能用浏览器浏览、上传、下载和编辑文件。',
    aboutQuickStart: '快速开始',
    aboutStep1: '打开手机热点。',
    aboutStep2: '在这里点击 <b>启动</b>。',
    aboutStep3: '在另一台设备上扫码或打开显示的地址。',
    aboutStep4: '点击 <b>停止</b> 关闭服务器。',
    aboutCli: '终端命令',
    aboutCliHint: '点击命令即可复制。',
    aboutSettings: '设置保存在哪里',
    aboutSettingsText: '日志级别在 KernelSU 上通过 <code>ksud module config set log_level …</code> 保存（见模块配置指南）；在 Magisk / APatch 上回退到 <code>logs/.config</code>。这两处都会由 <code>action.sh</code> 在每次启动时读取。',
    aboutLogLevels: '日志级别',
    aboutLevelInfo: '<b>Info</b> — 客户端 IP、方法、状态码',
    aboutLevelError: '<b>Error</b> — 仅 4xx / 5xx',
    aboutLevelDebug: '<b>Debug</b> — 时间戳、IP:端口、方法、路径',
    aboutLevelOff: '<b>Off</b> — 不输出日志',
    aboutLicense: '许可证：MIT',
  },
};

let lang =
  localStorage.getItem('fb_wui_lang') ||
  ((navigator.language || '').toLowerCase().startsWith('zh') ? 'zh' : 'en');

const t = (key) => (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;

/* ─── Offline QR Code Generator (ISO-18004 Byte Mode, EC Level L, v1-v4) ─ */
const QR_VERSIONS = [
  null,
  { size: 21, total: 26, data: 19, ec: 7, align: [] },
  { size: 25, total: 44, data: 34, ec: 10, align: [6, 18] },
  { size: 29, total: 70, data: 55, ec: 15, align: [6, 22] },
  { size: 33, total: 100, data: 80, ec: 20, align: [6, 26] },
];

function qrGfMul(a, b) {
  if (a === 0 || b === 0) return 0;
  let r = 0;
  for (let i = 0; i < 8; i++) {
    if ((b >> i) & 1) r ^= a << i;
  }
  for (let i = 14; i >= 8; i--) {
    if ((r >> i) & 1) r ^= 0x11d << (i - 8);
  }
  return r;
}

function qrReedSolomon(data, ecLen) {
  let gen = [1];
  for (let i = 0; i < ecLen; i++) {
    const next = new Array(gen.length + 1).fill(0);
    let root = 1;
    for (let j = 0; j < i; j++) root = qrGfMul(root, 2);
    for (let j = 0; j < gen.length; j++) {
      next[j] ^= gen[j];
      next[j + 1] ^= qrGfMul(gen[j], root);
    }
    gen = next;
  }
  const msg = data.concat(new Array(ecLen).fill(0));
  for (let i = 0; i < data.length; i++) {
    const coef = msg[i];
    if (coef !== 0) {
      for (let j = 0; j < gen.length; j++) {
        msg[i + j] ^= qrGfMul(gen[j], coef);
      }
    }
  }
  return msg.slice(data.length);
}

function renderQrSvg(text) {
  const bytes = Array.from(new TextEncoder().encode(text));
  let ver = 1;
  while (ver <= 4 && QR_VERSIONS[ver].data < bytes.length + 2) ver++;
  if (ver > 4) return '';
  const cfg = QR_VERSIONS[ver];
  const n = cfg.size;

  const bits = [];
  const pushBits = (val, len) => {
    for (let i = len - 1; i >= 0; i--) bits.push((val >> i) & 1);
  };
  pushBits(0b0100, 4);
  pushBits(bytes.length, 8);
  bytes.forEach((b) => pushBits(b, 8));
  for (let i = 0; i < 4 && bits.length < cfg.data * 8; i++) bits.push(0);
  while (bits.length % 8 !== 0) bits.push(0);
  const codewords = [];
  for (let i = 0; i < bits.length; i += 8) {
    let b = 0;
    for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
    codewords.push(b);
  }
  const pads = [0xec, 0x11];
  let padIdx = 0;
  while (codewords.length < cfg.data) codewords.push(pads[padIdx++ & 1]);
  const fullWords = codewords.concat(qrReedSolomon(codewords, cfg.ec));

  const grid = Array.from({ length: n }, () => new Array(n).fill(null));
  const reserved = Array.from({ length: n }, () => new Array(n).fill(false));

  const setMod = (r, c, v) => {
    if (r >= 0 && r < n && c >= 0 && c < n) {
      grid[r][c] = v ? 1 : 0;
      reserved[r][c] = true;
    }
  };
  const finder = (tr, tc) => {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const inOuter = r >= 0 && r <= 6 && c >= 0 && c <= 6;
        const onEdge = r === 0 || r === 6 || c === 0 || c === 6;
        const inCore = r >= 2 && r <= 4 && c >= 2 && c <= 4;
        setMod(tr + r, tc + c, inOuter && (onEdge || inCore));
      }
    }
  };
  finder(0, 0);
  finder(0, n - 7);
  finder(n - 7, 0);

  for (let i = 8; i < n - 8; i++) {
    setMod(6, i, i % 2 === 0);
    setMod(i, 6, i % 2 === 0);
  }
  if (cfg.align.length) {
    const [a0, a1] = cfg.align;
    for (let r = -2; r <= 2; r++) {
      for (let c = -2; c <= 2; c++) {
        setMod(a1 + r, a1 + c, Math.max(Math.abs(r), Math.abs(c)) !== 1);
      }
    }
  }
  setMod(4 * ver + 9, 8, 1);
  for (let i = 0; i < 9; i++) {
    if (!reserved[8][i]) reserved[8][i] = true;
    if (!reserved[i][8]) reserved[i][8] = true;
  }
  for (let i = 0; i < 8; i++) {
    reserved[8][n - 1 - i] = true;
    reserved[n - 1 - i][8] = true;
  }

  let bitPos = 0;
  const totalBits = fullWords.length * 8;
  let up = true;
  for (let right = n - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let v = 0; v < n; v++) {
      const r = up ? n - 1 - v : v;
      for (let dx = 0; dx < 2; dx++) {
        const c = right - dx;
        if (!reserved[r][c]) {
          let bit = 0;
          if (bitPos < totalBits) {
            bit = (fullWords[bitPos >> 3] >> (7 - (bitPos & 7))) & 1;
            bitPos++;
          }
          if ((r + c) % 2 === 0) bit ^= 1;
          grid[r][c] = bit;
        }
      }
    }
    up = !up;
  }

  // Format bits for EC Level L (01) + Mask 0 (000) -> 0x77c4
  const fmt = 0x77c4;
  const fCoords1 = [
    [8, 0], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 7], [8, 8],
    [7, 8], [5, 8], [4, 8], [3, 8], [2, 8], [1, 8], [0, 8],
  ];
  const fCoords2 = [
    [n - 1, 8], [n - 2, 8], [n - 3, 8], [n - 4, 8], [n - 5, 8], [n - 6, 8], [n - 7, 8],
    [8, n - 8], [8, n - 7], [8, n - 6], [8, n - 5], [8, n - 4], [8, n - 3], [8, n - 2], [8, n - 1],
  ];
  for (let i = 0; i < 15; i++) {
    const b = (fmt >> i) & 1;
    grid[fCoords1[i][0]][fCoords1[i][1]] = b;
    grid[fCoords2[i][0]][fCoords2[i][1]] = b;
  }

  let path = '';
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (grid[r][c]) path += `M${c},${r}h1v1h-1z`;
    }
  }
  return `<svg viewBox="-1 -1 ${n + 2} ${n + 2}" xmlns="http://www.w3.org/2000/svg"><path d="${path}" fill="#121631"/></svg>`;
}

/* ─── Module location ──────────────────────────────────────────────────── */
let MODDIR = '/data/adb/modules/filebase';
let MODID = 'filebase';

function resolveModule() {
  try {
    const info = JSON.parse(moduleInfo() || '{}');
    if (info.moduleDir) MODDIR = info.moduleDir;
    if (info.id) MODID = info.id;
  } catch (_) {}
}

/* ─── Shell helpers ────────────────────────────────────────────────────── */
const quote = (s) => "'" + String(s).replace(/'/g, "'\\''") + "'";

async function sh(command) {
  const result = await exec(command);
  return result || { errno: -1, stdout: '', stderr: '' };
}

function withTimeout(promise, ms, label) {
  let timer = null;
  const guard = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error((label || 'command') + ' timed out after ' + Math.round(ms / 1000) + 's')),
      ms,
    );
  });
  return Promise.race([promise, guard]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

function parseKv(text) {
  const out = {};
  String(text || '').split(/\r?\n/).forEach((line) => {
    const i = line.indexOf('=');
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  });
  return out;
}

async function readText(path, maxLines) {
  try {
    const tail = maxLines ? ' | tail -n ' + maxLines : '';
    const { stdout } = await sh('cat ' + quote(path) + ' 2>/dev/null' + tail);
    return stdout || '';
  } catch (_) {
    return '';
  }
}

/* ─── UI helpers ───────────────────────────────────────────────────────── */
let toastTimer = null;

function showToast(message, kind) {
  const el = $('toast');
  el.textContent = message;
  el.className = 'toast' + (kind ? ' toast-' + kind : '');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3800);
}

function notify(message) {
  showToast(message, 'ok');
  try {
    nativeToast(message);
  } catch (_) {}
}

function notifyError(message) {
  showToast(message || t('failed'), 'err');
}

function setOutput(text) {
  $('output').textContent = text && text.trim() ? text : '—';
}

function setBusy(isBusy) {
  ['btnStart', 'btnStop', 'btnRestart'].forEach((id) => {
    $(id).disabled = isBusy;
  });
  $('logLevelSel').disabled = isBusy;
  document.querySelectorAll('#logLevelSeg .seg-btn').forEach((btn) => {
    btn.disabled = isBusy;
  });
}

function syncLogLevelUi(level) {
  const lvl = level || 'info';
  $('logLevelSel').value = lvl;
  document.querySelectorAll('#logLevelSeg .seg-btn').forEach((btn) => {
    btn.classList.toggle('is-active', btn.getAttribute('data-level') === lvl);
  });
  const descMap = { info: 'lvlInfo', error: 'lvlError', debug: 'lvlDebug', off: 'lvlOff' };
  const descEl = $('logLevelDesc');
  if (descEl) descEl.textContent = t(descMap[lvl] || 'lvlInfo');
}

let startedEpoch = 0;
let isServerRunning = false;

function updateUptimeBadge() {
  const sub = $('vUptime');
  if (!sub) return;
  if (isServerRunning && startedEpoch > 0) {
    const sec = Math.max(0, Math.floor(Date.now() / 1000) - startedEpoch);
    sub.textContent = '● ' + formatUptime(sec);
  } else {
    sub.textContent = '';
  }
}

function renderStatus(st) {
  lastStatus = st;
  const running = st.RUNNING === '1';
  isServerRunning = running;

  const card = $('statusCard');
  if (card) {
    card.className = 'card status-card ' + (running ? 'state-on' : 'state-off');
  }
  const dot = $('statusDot');
  dot.className = 'dot ' + (running ? 'dot-on' : 'dot-off');
  $('statusText').textContent = running ? t('statusRunning') : t('statusStopped');
  const hint = $('statusHint');
  if (hint) hint.textContent = running ? t('statusHintOn') : t('statusHintOff');

  $('vPid').textContent = running && st.PID ? st.PID : '—';

  const port = st.PORT || '6532';
  $('vPort').textContent = port;
  const host =
    st.ADDR ||
    (st.BIND_IP && st.BIND_IP !== '0.0.0.0' ? st.BIND_IP : '') ||
    (st.HOTSPOT_IP || '');
  const url = running && host ? 'http://' + host + ':' + port : '';
  $('vAddr').textContent = url || '—';
  $('vAddr').dataset.url = url;
  $('btnCopyAddr').disabled = !url;
  $('btnOpenAddr').disabled = !url;
  $('btnQrAddr').disabled = !url;

  if (!url) {
    $('qrPanel').classList.add('hidden');
  } else if (!$('qrPanel').classList.contains('hidden')) {
    $('qrSvgWrap').innerHTML = renderQrSvg(url);
  }

  $('vIface').textContent = st.IFACE || '—';
  const lvl = st.LOG_LEVEL || 'info';
  $('vLogLevel').textContent = lvl;
  syncLogLevelUi(lvl);

  startedEpoch = parseInt(st.STARTED, 10) || 0;
  updateUptimeBadge();
}

function formatUptime(sec) {
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec / 60);
  if (m < 60) return m + 'm ' + (sec % 60) + 's';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h ' + (m % 60) + 'm';
  return Math.floor(h / 24) + 'd ' + (h % 24) + 'h';
}

function setUnavailable() {
  $('apiBadge').textContent = t('apiMissing');
  $('apiBadge').className = 'badge badge-warn';
  $('statusText').textContent = t('statusUnknown');
  $('fallbackCmd').textContent =
    "su -c 'sh " + MODDIR + "/action.sh info'\n" +
    "su -c 'sh " + MODDIR + "/action.sh start'\n" +
    "su -c 'sh " + MODDIR + "/action.sh stop'";
  $('fallbackCard').classList.remove('hidden');
  setBusy(true);
}

/* ─── Controller ───────────────────────────────────────────────────────── */
let busy = false;
let lastStatus = null;
let rawLogLines = [];
let logFilterKind = 'all';

async function refreshInfo() {
  if (!HAS_API || busy) return;
  try {
    const { stdout, stderr, errno } = await withTimeout(
      sh('sh ' + quote(MODDIR + '/action.sh') + ' info'),
      10000,
      'info',
    );
    if (errno !== 0 && !stdout) {
      notifyError(stderr || t('failed'));
      return;
    }
    renderStatus(parseKv(stdout));
  } catch (e) {
    notifyError(e.message);
  }
}

async function runAction(name) {
  if (!HAS_API || busy) return;
  busy = true;
  setBusy(true);
  setOutput(t('busy') + ' ' + name);
  try {
    const res = await withTimeout(
      sh('sh ' + quote(MODDIR + '/action.sh') + ' ' + quote(name)),
      30000,
      name,
    );

    let out = (res.stdout || '') + (res.stderr ? '\n' + res.stderr : '');
    const persisted = await readText(MODDIR + '/logs/action.log');
    if (persisted.trim() && persisted.trim().length >= out.trim().length) {
      out = persisted;
    }

    if (name === 'start' || name === 'restart') {
      const serverLog = await readText(MODDIR + '/logs/server.log', 25);
      if (serverLog.trim()) {
        out += '\n\n--- logs/server.log (last 25 lines) ---\n' + serverLog.trim();
      }
    }

    setOutput(out.trim() || '(no output)');
    if (res.errno === 0) {
      notify(name === 'start' ? t('started') : name === 'stop' ? t('stopped') : t('restarted'));
    } else {
      notifyError(res.stderr || (t('failed') + ' (exit ' + res.errno + ')'));
    }
  } catch (e) {
    notifyError(e.message);
  } finally {
    busy = false;
    setBusy(false);
    await refreshInfo();
  }
}

async function applyLogLevel(explicitLevel) {
  const level = explicitLevel || $('logLevelSel').value;
  syncLogLevelUi(level);
  if (!HAS_API) return;
  try {
    const { stdout, stderr, errno } = await withTimeout(
      sh('sh ' + quote(MODDIR + '/action.sh') + ' loglevel ' + quote(level)),
      10000,
      'loglevel',
    );
    if (errno === 0) {
      notify(t('logSaved') + ': ' + (stdout.trim() || level));
      await refreshInfo();
    } else {
      notifyError(stderr || t('failed'));
    }
  } catch (e) {
    notifyError(e.message);
  }
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function classifyLogLine(line) {
  if (/("\s*[45]\d\d\b|\bcode\s+[45]\d\d\b|\bERROR\b|Traceback)/i.test(line)) return 'err';
  if (/("\s*[23]\d\d\b)/.test(line)) return 'ok';
  return 'info';
}

function renderFilteredLogs(keepScroll) {
  const box = $('logView');
  if (!rawLogLines.length) {
    box.textContent = t('noLog');
    return;
  }
  const q = ($('logSearch').value || '').trim().toLowerCase();
  const filtered = rawLogLines.filter((line) => {
    if (q && line.toLowerCase().indexOf(q) === -1) return false;
    if (logFilterKind === 'err') return classifyLogLine(line) === 'err';
    if (logFilterKind === 'ok') return classifyLogLine(line) === 'ok';
    return true;
  });

  if (!filtered.length) {
    box.textContent = t('noLogMatch');
    return;
  }

  box.innerHTML = filtered
    .map((line) => {
      const kind = classifyLogLine(line);
      const cls = kind === 'err' ? 'log-line-err' : kind === 'ok' ? 'log-line-ok' : '';
      return cls ? `<span class="${cls}">${escHtml(line)}</span>` : escHtml(line);
    })
    .join('\n');

  if (keepScroll) box.scrollTop = box.scrollHeight;
}

async function refreshLogs() {
  if (!HAS_API) return;
  try {
    const box = $('logView');
    const wasAtBottom =
      !box.textContent ||
      box.textContent === '—' ||
      box.scrollTop + box.clientHeight >= box.scrollHeight - 24;
    const text = await readText(MODDIR + '/logs/server.log', 120);
    const trimmed = text.trim();
    rawLogLines = trimmed ? trimmed.split(/\r?\n/) : [];
    renderFilteredLogs(wasAtBottom);
  } catch (e) {
    notifyError(e.message);
  }
}

/* ─── i18n / pages / about ─────────────────────────────────────────────── */
function applyI18n() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  $('langBtn').textContent = lang === 'zh' ? 'EN' : '中文';
  $('apiBadge').textContent = HAS_API ? t('apiReady') : t('apiMissing');
  $('apiBadge').className = 'badge ' + (HAS_API ? 'badge-ok' : 'badge-warn');
  syncLogLevelUi($('logLevelSel').value || 'info');
  if (lastStatus) renderStatus(lastStatus);
  else if (!HAS_API) $('statusText').textContent = t('statusUnknown');
  renderAbout();
}

function renderAbout() {
  const copyCmd = (cmd) =>
    '<code class="copy-cmd" data-copy="' + cmd.replace(/"/g, '&quot;') + '">' + cmd + '</code>';
  const base = "su -c 'sh " + MODDIR + '/action.sh ';
  $('aboutBody').innerHTML =
    '<p>' + t('aboutIntro') + '</p>' +
    '<h3>' + t('aboutQuickStart') + '</h3><ol>' +
    '<li>' + t('aboutStep1') + '</li>' +
    '<li>' + t('aboutStep2') + '</li>' +
    '<li>' + t('aboutStep3') + '</li>' +
    '<li>' + t('aboutStep4') + '</li></ol>' +
    '<h3>' + t('aboutCli') + '</h3><ul class="cmd-list">' +
    '<li>' + copyCmd(base + "start'") + '</li>' +
    '<li>' + copyCmd(base + "stop'") + '</li>' +
    '<li>' + copyCmd(base + "restart'") + '</li>' +
    '<li>' + copyCmd(base + "status'") + '</li>' +
    '<li>' + copyCmd(base + "log 200'") + '</li>' +
    '<li>' + copyCmd(base + "loglevel debug'") + '</li>' +
    '</ul><p class="hint">' + t('aboutCliHint') + '</p>' +
    '<h3>' + t('aboutLogLevels') + '</h3><ul>' +
    '<li>' + t('aboutLevelInfo') + '</li>' +
    '<li>' + t('aboutLevelError') + '</li>' +
    '<li>' + t('aboutLevelDebug') + '</li>' +
    '<li>' + t('aboutLevelOff') + '</li></ul>' +
    '<h3>' + t('aboutSettings') + '</h3><p>' + t('aboutSettingsText') + '</p>' +
    '<p><b>' + t('aboutLicense') + '</b></p>';
}

function showPage(name) {
  ['control', 'logs', 'about'].forEach((p) => {
    $('page-' + p).classList.toggle('hidden', p !== name);
    $('tab-' + p).classList.toggle('is-active', p === name);
  });
  window.scrollTo(0, 0);
  if (name === 'logs') refreshLogs();
}

function toggleLang() {
  lang = lang === 'en' ? 'zh' : 'en';
  localStorage.setItem('fb_wui_lang', lang);
  applyI18n();
}

async function copyText(text, el) {
  const done = () => {
    if (!el) return;
    const old = el.textContent;
    el.textContent = t('copyOk');
    setTimeout(() => {
      el.textContent = old;
    }, 1200);
  };
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      done();
      return;
    }
  } catch (_) {}
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    done();
  } catch (_) {}
  ta.remove();
}

/* ─── Boot ─────────────────────────────────────────────────────────────── */
function bindEvents() {
  $('btnStart').addEventListener('click', () => runAction('start'));
  $('btnStop').addEventListener('click', () => runAction('stop'));
  $('btnRestart').addEventListener('click', () => runAction('restart'));
  $('btnRefreshLogs').addEventListener('click', refreshLogs);

  $('btnQuickRefresh').addEventListener('click', function () {
    this.classList.remove('spinning');
    void this.offsetWidth;
    this.classList.add('spinning');
    refreshInfo();
  });

  $('btnQrAddr').addEventListener('click', () => {
    const url = $('vAddr').dataset.url;
    if (!url) return;
    const panel = $('qrPanel');
    const hidden = panel.classList.toggle('hidden');
    if (!hidden) {
      $('qrSvgWrap').innerHTML = renderQrSvg(url);
    }
  });

  $('btnCopyAddr').addEventListener('click', function () {
    const url = $('vAddr').dataset.url;
    if (url) copyText(url, this.querySelector('span'));
  });
  $('btnOpenAddr').addEventListener('click', function () {
    const url = $('vAddr').dataset.url;
    if (!url) return;
    const win = window.open(url, '_blank', 'noopener');
    if (!win) location.href = url;
  });

  $('btnClearOutput').addEventListener('click', () => setOutput('—'));
  $('btnCopyOutput').addEventListener('click', function () {
    copyText($('output').textContent, this.querySelector('span'));
  });
  $('btnCopyLogs').addEventListener('click', function () {
    copyText($('logView').textContent, this.querySelector('span'));
  });
  $('btnWrapLogs').addEventListener('click', function () {
    const nowNoWrap = $('logView').classList.toggle('nowrap');
    this.setAttribute('aria-pressed', nowNoWrap ? 'false' : 'true');
  });

  $('logSearch').addEventListener('input', () => renderFilteredLogs(false));
  $('logFilterChips').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-filter]');
    if (!btn) return;
    logFilterKind = btn.getAttribute('data-filter') || 'all';
    document.querySelectorAll('#logFilterChips .chip').forEach((c) => {
      c.classList.toggle('is-active', c === btn);
    });
    renderFilteredLogs(false);
  });

  $('logLevelSel').addEventListener('change', () => applyLogLevel());
  $('logLevelSeg').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-level]');
    if (!btn || btn.disabled) return;
    applyLogLevel(btn.getAttribute('data-level'));
  });

  $('themeBtn').addEventListener('click', toggleTheme);
  $('langBtn').addEventListener('click', toggleLang);

  ['control', 'logs', 'about'].forEach((p) => {
    $('tab-' + p).addEventListener('click', () => showPage(p));
  });

  $('aboutBody').addEventListener('click', (e) => {
    const el = e.target.closest('[data-copy]');
    if (el) copyText(el.getAttribute('data-copy'), el);
  });
}

function main() {
  resolveModule();
  applyTheme();
  applyI18n();
  bindEvents();

  if (!HAS_API) {
    setUnavailable();
    return;
  }
  refreshInfo();
  // Live 1s uptime counter when server is running
  setInterval(() => {
    if (document.visibilityState === 'visible' && isServerRunning) {
      updateUptimeBadge();
    }
  }, 1000);
  setInterval(() => {
    if (document.visibilityState === 'visible' && !busy) refreshInfo();
  }, 15000);
  setInterval(() => {
    if (document.visibilityState !== 'visible' || busy) return;
    if ($('page-logs').classList.contains('hidden')) return;
    const box = $('logView');
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 24;
    if (atBottom) refreshLogs();
  }, 20000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
