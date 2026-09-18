/* ═══════════════════════════════════════════════════════════════════════
   FileBase WebUI

   Follows the KernelSU module guide (website/docs/zh_CN/guide/module-webui.md):
     • entry point is webroot/index.html, assets live next to it
     • shell access goes through the official `kernelsu` library:
         const { errno, stdout, stderr } = await exec(cmd)
       (the old synchronous `ksu.exec(cmd)` string API is NOT the documented
        one and broke under other WebUI hosts)
     • module settings are stored with `ksud module config` (module-config.md),
       with a plain-file fallback for Magisk / APatch
     • `moduleInfo()` supplies the module directory instead of hard-coding it
   ═══════════════════════════════════════════════════════════════════════ */

import { exec, toast as nativeToast, moduleInfo } from './kernelsu.js';

const $ = (id) => document.getElementById(id);

/* ─── API availability (guide: the library needs the manager's ksu bridge) ─ */
const HAS_API =
  typeof window.ksu !== 'undefined' &&
  typeof window.ksu.exec === 'function';

/* ─── Theme (manual toggle; follows the system until the user picks) ───── */
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
    kPid: 'PID', kAddress: 'Address', kIface: 'Interface', kLogLevel: 'Log level',
    controls: 'Controls',
    startBtn: 'Start', stopBtn: 'Stop', restartBtn: 'Restart', refreshBtn: 'Refresh',
    logLevel: 'Log level',
    lvlInfo: 'Info — requests + status',
    lvlError: 'Error — 4xx/5xx only',
    lvlDebug: 'Debug — full details',
    lvlOff: 'Off — no logging',
    logLevelHint: "Saved through KernelSU's module config system; restart the server to apply.",
    output: 'Output',
    logsTitle: 'Server logs',
    logsHint: 'Last 120 lines of logs/server.log',
    aboutTitle: 'About',
    navControl: 'Control', navLogs: 'Logs', navAbout: 'About',
    fallbackTitle: 'WebUI API unavailable',
    fallbackText: 'This page must be opened from the KernelSU Manager (or another WebUI host). You can still control the module from a terminal:',
    busy: 'Working…',
    failed: 'Failed',
    started: 'Server started', stopped: 'Server stopped', restarted: 'Server restarted',
    logSaved: 'Log level saved',
    noLog: 'No log file yet.',
    apiReady: 'API ready',
    apiMissing: 'API missing',
    copyOk: 'Copied',
    aboutIntro: "Serves <code>/sdcard</code> over the phone's hotspot. Browse, upload, download and edit files from any device that is connected to it.",
    aboutQuickStart: 'Quick start',
    aboutStep1: 'Turn on the phone hotspot.',
    aboutStep2: 'Tap <b>Start</b> here.',
    aboutStep3: 'Open the shown address on another device.',
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
    kPid: '进程号', kAddress: '访问地址', kIface: '网卡', kLogLevel: '日志级别',
    controls: '控制',
    startBtn: '启动', stopBtn: '停止', restartBtn: '重启', refreshBtn: '刷新',
    logLevel: '日志级别',
    lvlInfo: 'Info — 记录请求与状态码',
    lvlError: 'Error — 仅 4xx/5xx',
    lvlDebug: 'Debug — 完整详情',
    lvlOff: 'Off — 不输出日志',
    logLevelHint: '通过 KernelSU 模块配置系统保存；重启服务器后生效。',
    output: '输出',
    logsTitle: '服务器日志',
    logsHint: 'logs/server.log 最后 120 行',
    aboutTitle: '关于',
    navControl: '控制', navLogs: '日志', navAbout: '关于',
    fallbackTitle: 'WebUI API 不可用',
    fallbackText: '本页面需要在 KernelSU 管理器（或其他 WebUI 宿主）中打开。你仍然可以用终端控制模块：',
    busy: '执行中…',
    failed: '失败',
    started: '服务器已启动', stopped: '服务器已停止', restarted: '服务器已重启',
    logSaved: '日志级别已保存',
    noLog: '暂无日志文件。',
    apiReady: 'API 就绪',
    apiMissing: 'API 不可用',
    copyOk: '已复制',
    aboutIntro: '通过手机热点共享 <code>/sdcard</code>，任何连接该热点的设备都能用浏览器浏览、上传、下载和编辑文件。',
    aboutQuickStart: '快速开始',
    aboutStep1: '打开手机热点。',
    aboutStep2: '在这里点击 <b>启动</b>。',
    aboutStep3: '在另一台设备上打开显示的地址。',
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

/* ─── Module location (guide: ask the manager, don't hard-code) ────────── */
let MODDIR = '/data/adb/modules/filebase';
let MODID = 'filebase';

function resolveModule() {
  try {
    const info = JSON.parse(moduleInfo() || '{}');
    if (info.moduleDir) MODDIR = info.moduleDir;
    if (info.id) MODID = info.id;
  } catch (_) {
    /* keep the defaults */
  }
}

/* ─── Shell helpers built on the documented exec() API ─────────────────── */
const quote = (s) => "'" + String(s).replace(/'/g, "'\\''") + "'";

async function sh(command) {
  // exec() resolves with { errno, stdout, stderr } and never throws for a
  // non-zero exit status; it only rejects when the bridge itself fails.
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

// Read a file from the module directory (optionally its last N lines).
// KernelSU's exec() returns the captured stdout; reading a file is the
// reliable path when a command's own output cannot be captured completely.
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
  toastTimer = setTimeout(() => el.classList.add('hidden'), 4000);
}

function notify(message) {
  showToast(message, 'ok');
  try {
    nativeToast(message); // manager-provided native toast (guide API)
  } catch (_) {}
}

function notifyError(message) {
  showToast(message || t('failed'), 'err');
}

function setOutput(text) {
  $('output').textContent = text && text.trim() ? text : '—';
}

function setBusy(busy) {
  ['btnStart', 'btnStop', 'btnRestart'].forEach((id) => {
    $(id).disabled = busy;
  });
  $('logLevelSel').disabled = busy;
}

function renderStatus(st) {
  lastStatus = st;
  const running = st.RUNNING === '1';
  const dot = $('statusDot');
  dot.className = 'dot ' + (running ? 'dot-on' : 'dot-off');
  $('statusText').textContent = running ? t('statusRunning') : t('statusStopped');
  $('vPid').textContent = running && st.PID ? st.PID : '—';

  const port = st.PORT || '6532';
  // ADDR comes from action.sh info and already accounts for the server binding
  // to 0.0.0.0 (where only the server knows the hotspot address).
  const host =
    st.ADDR ||
    (st.BIND_IP && st.BIND_IP !== '0.0.0.0' ? st.BIND_IP : '') ||
    (st.HOTSPOT_IP || '');
  $('vAddr').textContent = running && host ? 'http://' + host + ':' + port : '—';
  $('vIface').textContent = st.IFACE || '—';
  $('vLogLevel').textContent = st.LOG_LEVEL || 'info';
  if (st.LOG_LEVEL) $('logLevelSel').value = st.LOG_LEVEL;
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

    // KernelSU's exec() captures stdout, but that capture can come back empty
    // or truncated when the command backgrounds a process (the shell it runs
    // in is torn down on return). action.sh writes the same output to
    // logs/action.log, so read it back and prefer whichever is complete.
    const persisted = await readText(MODDIR + '/logs/action.log');
    if (persisted.trim() && persisted.trim().length >= out.trim().length) {
      out = persisted;
    }

    // Also show the server's own output: it holds the bind address and any
    // Python traceback when startup fails.
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

async function applyLogLevel() {
  if (!HAS_API) return;
  const level = $('logLevelSel').value;
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

async function refreshLogs() {
  if (!HAS_API) return;
  try {
    const text = await readText(MODDIR + '/logs/server.log', 120);
    $('logView').textContent = text.trim() || t('noLog');
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
  $('langBtn').textContent = lang === 'zh' ? 'EN' : '中文';
  $('apiBadge').textContent = HAS_API ? t('apiReady') : t('apiMissing');
  $('apiBadge').className = 'badge ' + (HAS_API ? 'badge-ok' : 'badge-warn');
  // Dynamic status text is not driven by data-i18n, so refresh it explicitly
  // (otherwise switching language leaves the old wording on screen).
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
  // Fallback for WebViews without the async clipboard API.
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
  $('logLevelSel').addEventListener('change', applyLogLevel);
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
  resolveModule(); // no-op when the ksu bridge is missing (guarded internally)
  applyTheme();
  applyI18n();
  bindEvents();

  if (!HAS_API) {
    setUnavailable();
    return;
  }
  refreshInfo();
  // Light auto-refresh so the status card stays live without clobbering the
  // user's output pane.
  setInterval(() => {
    if (document.visibilityState === 'visible' && !busy) refreshInfo();
  }, 15000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
