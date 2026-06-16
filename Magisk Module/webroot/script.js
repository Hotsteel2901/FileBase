/* ═══════════════════════════════════════════════════════════════════════
   FileBase WebUI — adapted from modern Magisk module webroot patterns
   ═══════════════════════════════════════════════════════════════════════ */

// APatch compatibility: map window.apatch to window.ksu if needed
if (typeof window !== "undefined" && window.apatch !== undefined && window.apatch.ksu === undefined) {
  window.ksu = window.apatch;
}

var MODULE_ID = "filebase";
var MODDIR = "/data/adb/modules/" + MODULE_ID;
var ACTION_SH = MODDIR + "/action.sh";
var PORT = 6532;

// ─── i18n ───────────────────────────────────────────────────────────────
var T = {
  en: {
    subtitle: "Android File Server — Control Panel",
    status: "Server Status",
    pid: "PID",
    bindIp: "Bind IP",
    iface: "Interface",
    logLevel: "Log Level",
    controls: "Controls",
    startBtn: "Start",
    stopBtn: "Stop",
    restartBtn: "Restart",
    refreshBtn: "Refresh",
    logLevelLabel: "Log Level:",
    output: "Console Output",
    online: "Online",
    offline: "Offline",
    noIP: "No hotspot IP",
    logSaved: "Log level saved",
    noExec: "WebUI exec API not available — see CLI fallback below",
    timeout: "Command timed out",
    dispatched: "Command dispatched — check status below",
    noRoot: "ksu.exec found but may lack root. Grant root access to KSUWebUIStandalone / MMRL.",
    navControl: "Control",
    navLogs: "Logs",
    navAbout: "About",
    logsTitle: "Server Logs",
    aboutTitle: "About / Help",
    cliFallbackTitle: "CLI Fallback",
    cliFallbackText: "WebUI exec API is not available. Use terminal instead:",
    welcomeTitle: "Welcome",
    welcomeHtml:
      "<div style='font-weight:800;margin-bottom:10px;'>👋 Welcome to FileBase</div>" +
      "<div class='warn-text'>This panel lets you start, stop, and monitor the file server.</div>" +
      "<div class='warn-text'>Use the <b>Control</b> tab for actions and status.</div>" +
      "<div class='warn-text'>Use the <b>Logs</b> tab to view server output.</div>",
    serverRunning: "Server is already running",
    serverStarted: "Server started",
    serverStopped: "Server stopped",
    serverRestarted: "Server restarted",
    checkStatusFirst: "Check status first",
    actionRunning: "Running",
    ready: "Ready",
    checking: "Checking...",
    stopped: "Stopped",
    running: "Running",
    failedStart: "Failed to start",
    logHint: "Last 80 lines of server log:",
    noLog: "No log file found.",
    copyOk: "Copied ✓",
  },
  zh: {
    subtitle: "Android 文件服务器 — 控制面板",
    status: "服务器状态",
    pid: "进程号",
    bindIp: "绑定 IP",
    iface: "网卡",
    logLevel: "日志级别",
    controls: "控制",
    startBtn: "启动",
    stopBtn: "停止",
    restartBtn: "重启",
    refreshBtn: "刷新",
    logLevelLabel: "日志级别：",
    output: "控制台输出",
    online: "在线",
    offline: "离线",
    noIP: "无热点 IP",
    logSaved: "日志级别已保存",
    noExec: "WebUI exec API 不可用 — 请使用下方的终端命令",
    timeout: "命令超时",
    dispatched: "命令已发送 — 查看下方状态",
    noRoot: "检测到 ksu.exec 但可能缺少 root 权限。请在 KSUWebUIStandalone / MMRL 中授予 root 权限。",
    navControl: "控制",
    navLogs: "日志",
    navAbout: "关于",
    logsTitle: "服务器日志",
    aboutTitle: "关于 / 帮助",
    cliFallbackTitle: "终端备用方案",
    cliFallbackText: "WebUI exec API 不可用。请使用终端命令：",
    welcomeTitle: "欢迎使用",
    welcomeHtml:
      "<div style='font-weight:800;margin-bottom:10px;'>👋 欢迎使用 FileBase</div>" +
      "<div class='warn-text'>本面板可用于启动、停止和监控文件服务器。</div>" +
      "<div class='warn-text'>使用 <b>控制</b> 标签页执行操作和查看状态。</div>" +
      "<div class='warn-text'>使用 <b>日志</b> 标签页查看服务器输出。</div>",
    serverRunning: "服务器已在运行",
    serverStarted: "服务器已启动",
    serverStopped: "服务器已停止",
    serverRestarted: "服务器已重启",
    checkStatusFirst: "请先检查状态",
    actionRunning: "执行中",
    ready: "就绪",
    checking: "检测中…",
    stopped: "已停止",
    running: "运行中",
    failedStart: "启动失败",
    logHint: "服务器日志最后 80 行：",
    noLog: "未找到日志文件。",
    copyOk: "已复制 ✓",
  }
};

var LANG = (function() {
  var s = localStorage.getItem("fb_wui_lang");
  if (s) return s;
  return (navigator.language || "").toLowerCase().indexOf("zh") === 0 ? "zh" : "en";
})();

function t(k) { return (T[LANG] && T[LANG][k]) || (T.en[k] || k); }

function applyI18n() {
  var els = document.querySelectorAll("[data-i18n]");
  for (var i = 0; i < els.length; i++) {
    els[i].textContent = t(els[i].getAttribute("data-i18n"));
  }
  var btn = document.getElementById("langBtn");
  if (btn) btn.textContent = LANG === "zh" ? "中文 / EN" : "EN / 中文";
  var btn2 = document.getElementById("langBtn2");
  if (btn2) btn2.textContent = LANG === "zh" ? "中文 / EN" : "EN / 中文";
}

function toggleLang() {
  LANG = LANG === "en" ? "zh" : "en";
  localStorage.setItem("fb_wui_lang", LANG);
  applyI18n();
  refreshStatus();
}

// ─── Root exec API ──────────────────────────────────────────────────────
var HAS_API = false;
var API_METHOD = null;

function checkApi() {
  if (typeof ksu !== "undefined" && typeof ksu.exec === "function") {
    HAS_API = true;
    API_METHOD = "ksu.exec";
    return "ksu.exec";
  }
  if (typeof exec === "function") {
    HAS_API = true;
    API_METHOD = "exec()";
    return "exec()";
  }
  HAS_API = false;
  API_METHOD = null;
  return null;
}

function kexec(cmd) {
  try {
    var out = ksu.exec(cmd);
    if (out === null || out === undefined) return "";
    return String(out).trim();
  } catch (e) {
    return "ERROR calling ksu.exec(): " + e;
  }
}

function kexec_all(cmd) {
  var safe = cmd.replace(/'/g, "'\\''");
  return kexec("sh -c '" + safe + " 2>&1'");
}

// ─── Touch feedback ─────────────────────────────────────────────────────
function attachSpringTapFeedback() {
  var selector = ["button", ".bottom-nav-item"].join(",");
  var els = document.querySelectorAll(selector);
  for (var i = 0; i < els.length; i++) {
    (function(el) {
      if (el.dataset && el.dataset.springTapInit === "true") return;
      if (el.dataset) el.dataset.springTapInit = "true";
      var startX = 0, startY = 0, moved = false;
      el.addEventListener("touchstart", function(event) {
        var touch = event.touches && event.touches[0];
        if (!touch) return;
        startX = touch.clientX; startY = touch.clientY; moved = false;
      }, { passive: true });
      el.addEventListener("touchmove", function(event) {
        var touch = event.touches && event.touches[0];
        if (!touch) return;
        if (Math.abs(touch.clientX - startX) > 8 || Math.abs(touch.clientY - startY) > 8) moved = true;
      }, { passive: true });
      el.addEventListener("touchend", function() {
        if (moved) return;
        if (el.disabled || el.classList.contains("spring-tap")) return;
        el.classList.remove("spring-tap");
        void el.offsetWidth;
        el.classList.add("spring-tap");
        setTimeout(function() { el.classList.remove("spring-tap"); }, 380);
      }, { passive: true });
      el.addEventListener("touchcancel", function() { moved = true; }, { passive: true });
    })(els[i]);
  }
}

// ─── Toast system ───────────────────────────────────────────────────────
var toastAction = null;
var toastSecondaryAction = null;
var toastTertiaryAction = null;
var progressToastActive = false;

function setToastActionsHidden(hidden) {
  var actions = document.querySelector("#toast-card .toast-actions");
  if (!actions) return;
  if (hidden) actions.classList.add("hidden");
  else actions.classList.remove("hidden");
}

function showProgressToast(title, text) {
  progressToastActive = true;
  showToastHtml(
    title || t("checking"),
    "<div class='progress-row'>" +
      "<div class='spinner'></div>" +
      "<div class='warn-text' id='progress-text'>" + esc(text || t("checking")) + "</div>" +
    "</div>" +
    "<div class='warn-note'>" + (LANG === "zh" ? "请勿退出页面。" : "Please do not exit the page.") + "</div>",
    true,
    t("checking"),
    function() {}
  );
  setToastActionsHidden(true);
}

function hideProgressToastIfActive() {
  if (!progressToastActive) return;
  progressToastActive = false;
  hideToast();
}

function showToastHtml(title, htmlMessage, isOk, primaryText, onPrimary, secondaryText, onSecondary, tertiaryText, onTertiary) {
  var overlay = document.getElementById("toast-overlay");
  var tt = document.getElementById("toast-title");
  var m = document.getElementById("toast-message");
  var b1 = document.getElementById("toast-ok");
  var b2 = document.getElementById("toast-secondary");
  var b3 = document.getElementById("toast-tertiary");
  if (!overlay || !tt || !m || !b1 || !b2 || !b3) return;

  tt.textContent = title || t("ready");
  tt.classList.remove("ok", "bad", "pulse");
  if (isOk) tt.classList.add("ok");
  else tt.classList.add("bad", "pulse");

  m.innerHTML = htmlMessage || "";

  b1.textContent = primaryText ? primaryText : t("ready");
  toastAction = (typeof onPrimary === "function") ? onPrimary : null;

  if (secondaryText && typeof onSecondary === "function") {
    b2.textContent = secondaryText;
    b2.classList.remove("hidden");
    toastSecondaryAction = onSecondary;
  } else {
    b2.classList.add("hidden");
    toastSecondaryAction = null;
  }

  if (tertiaryText && typeof onTertiary === "function") {
    b3.textContent = tertiaryText;
    b3.classList.remove("hidden");
    toastTertiaryAction = onTertiary;
  } else {
    b3.classList.add("hidden");
    toastTertiaryAction = null;
  }

  var card = document.getElementById("toast-card");
  if (card) {
    card.classList.remove("bounce-in");
    void card.offsetWidth;
    card.classList.add("bounce-in");
  }
  setToastActionsHidden(false);
  overlay.classList.remove("hidden");
}

function hideToast() {
  var overlay = document.getElementById("toast-overlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  toastAction = null;
  toastSecondaryAction = null;
  toastTertiaryAction = null;
}

// ─── Utils ────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setConsole(text) {
  var el = document.getElementById("console");
  if (el) el.textContent = text || "—";
}

function setLogConsole(text) {
  var el = document.getElementById("logConsole");
  if (el) el.textContent = text || t("noLog");
}

function setButtonsDisabled(disabled) {
  var ids = ["btnStart", "btnStop", "btnRestart", "btnRefresh"];
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (el) el.disabled = disabled;
  }
}

// ─── Status refresh ───────────────────────────────────────────────────────
// Runs action.sh status and shows its raw output in the console.
// No automated detection — the user sees the same output as CLI.
function refreshStatus() {
  if (!HAS_API) {
    setConsole(t("noExec"));
    return;
  }
  var raw = kexec_all("sh " + ACTION_SH + " status");
  setConsole(raw || "(no output)");
}

// ─── Actions ──────────────────────────────────────────────────────────────
function doAction(action) {
  if (!HAS_API) {
    setConsole(t("noExec"));
    return;
  }
  if (["start", "stop", "restart"].indexOf(action) === -1) return;

  setButtonsDisabled(true);

  if (action === "start" || action === "restart") {
    var lvl = document.getElementById("logLevelSel").value;
    if (["info", "error", "debug", "off"].indexOf(lvl) === -1) lvl = "info";
    kexec_all("mkdir -p " + MODDIR + "/logs && echo " + lvl + " > " + MODDIR + "/logs/.config");
  }

  setConsole(t("actionRunning") + ": " + action + "...");
  showProgressToast(t("actionRunning"), action + "...");

  setTimeout(function() {
    var raw = kexec_all("sh " + ACTION_SH + " " + action);
    hideProgressToastIfActive();
    setConsole(raw || "(no output)");

    if (raw.indexOf("already running") !== -1 || raw.indexOf("Server started") !== -1) {
      showToastHtml(
        action === "start" ? t("serverStarted") : t("serverRestarted"),
        "<div style='font-weight:800;margin-bottom:10px;color:#2d8a4a;'>✅ " + (action === "start" ? t("serverStarted") : t("serverRestarted")) + "</div>" +
        "<div class='warn-text'>" + esc(raw.split("\n").slice(0, 6).join("\n")) + "</div>",
        true,
        t("ready"),
        function() {}
      );
    } else if (raw.indexOf("Server stopped") !== -1) {
      showToastHtml(
        t("serverStopped"),
        "<div style='font-weight:800;margin-bottom:10px;color:#2d8a4a;'>✅ " + t("serverStopped") + "</div>",
        true,
        t("ready"),
        function() {}
      );
    } else if (raw.indexOf("failed") !== -1 || raw.indexOf("Error") !== -1 || raw.indexOf("not found") !== -1) {
      showToastHtml(
        t("failedStart"),
        "<div class='warn-head'>❌ " + t("failedStart") + "</div>" +
        "<div class='warn-text'>" + esc(raw.split("\n").slice(0, 8).join("\n")) + "</div>",
        false,
        t("ready"),
        function() {}
      );
    }

    setButtonsDisabled(false);
    refreshStatus();
  }, 80);
}

// ─── Log level change ─────────────────────────────────────────────────────
function onLogLevelChange() {
  var lvl = document.getElementById("logLevelSel").value;
  if (["info", "error", "debug", "off"].indexOf(lvl) === -1) lvl = "info";
  kexec_all("mkdir -p " + MODDIR + "/logs && echo " + lvl + " > " + MODDIR + "/logs/.config");
  setConsole(t("logSaved") + ": " + lvl);
}

// ─── Logs page ────────────────────────────────────────────────────────────
function refreshLogs() {
  if (!HAS_API) {
    setLogConsole(t("noExec"));
    return;
  }
  var raw = kexec_all("cat " + MODDIR + "/logs/server.log 2>/dev/null | tail -n 80");
  setLogConsole(raw || t("noLog"));
}

// ─── Page navigation ──────────────────────────────────────────────────────
function showPage(pageName) {
  var pages = ["page-control", "page-logs", "page-about"];
  var navs = ["nav-control", "nav-logs", "nav-about"];
  var names = ["control", "logs", "about"];
  for (var i = 0; i < pages.length; i++) {
    var p = document.getElementById(pages[i]);
    var n = document.getElementById(navs[i]);
    if (p) p.style.display = names[i] === pageName ? "block" : "none";
    if (n) n.classList.toggle("active", names[i] === pageName);
  }
  if (pageName === "logs") refreshLogs();
}

// ─── Copy CLI fallback ────────────────────────────────────────────────────
function setupCopyButton(buttonId, textToCopy) {
  var btn = document.getElementById(buttonId);
  if (!btn) return;
  btn.addEventListener("click", function() {
    if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(textToCopy).then(
        function() {
          btn.textContent = t("copyOk");
          setTimeout(function() { btn.textContent = textToCopy; }, 1500);
        },
        function() { prompt("Copy:", textToCopy); }
      );
    } else {
      prompt("Copy:", textToCopy);
    }
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function() {
  attachSpringTapFeedback();
  applyI18n();

  var api = checkApi();
  var diag = document.getElementById("diag");
  if (api) {
    diag.className = "diag diag-ok";
    diag.textContent = "API: " + api + " (testing...)";
    document.getElementById("cliFallback").style.display = "none";

    var testOut = kexec_all("echo fb_test_ok");
    if (testOut && testOut.indexOf("fb_test_ok") !== -1) {
      diag.textContent = "API: " + api + " (ready)";
      diag.className = "diag diag-ok";
      refreshStatus();
    } else {
      diag.textContent = "API: " + api + " — WARNING: " + t("noRoot");
      diag.className = "diag diag-fail";
      setConsole(t("noRoot"));
    }
  } else {
    diag.className = "diag diag-fail";
    diag.textContent = "API: NOT AVAILABLE — install KSUWebUIStandalone or MMRL, or use CLI";
    document.getElementById("cliFallback").style.display = "block";
    setConsole(t("noExec"));
  }

  if (HAS_API) {
    var lvlOut = kexec_all("cat " + MODDIR + "/logs/.config 2>/dev/null || echo info");
    var lvl = (lvlOut || "info").trim();
    var sel = document.getElementById("logLevelSel");
    if (sel) sel.value = lvl;
  }

  document.getElementById("btnStart").addEventListener("click", function() { doAction("start"); });
  document.getElementById("btnStop").addEventListener("click", function() { doAction("stop"); });
  document.getElementById("btnRestart").addEventListener("click", function() { doAction("restart"); });
  document.getElementById("btnRefresh").addEventListener("click", function() { refreshStatus(); });
  document.getElementById("logLevelSel").addEventListener("change", onLogLevelChange);
  document.getElementById("langBtn").addEventListener("click", toggleLang);

  var langBtn2 = document.getElementById("langBtn2");
  if (langBtn2) langBtn2.addEventListener("click", toggleLang);

  var btnRefreshLogs = document.getElementById("btnRefreshLogs");
  if (btnRefreshLogs) btnRefreshLogs.addEventListener("click", function() { refreshLogs(); });

  document.getElementById("nav-control").addEventListener("click", function() { showPage("control"); });
  document.getElementById("nav-logs").addEventListener("click", function() { showPage("logs"); });
  document.getElementById("nav-about").addEventListener("click", function() { showPage("about"); });

  document.getElementById("toast-ok").addEventListener("click", function() {
    var fn = toastAction; hideToast(); if (fn) fn();
  });
  document.getElementById("toast-secondary").addEventListener("click", function() {
    var fn = toastSecondaryAction; hideToast(); if (fn) fn();
  });
  document.getElementById("toast-tertiary").addEventListener("click", function() {
    var fn = toastTertiaryAction; hideToast(); if (fn) fn();
  });

  setupCopyButton("copy-start", "su -c 'sh /data/adb/modules/filebase/action.sh start'");
  setupCopyButton("copy-stop", "su -c 'sh /data/adb/modules/filebase/action.sh stop'");
  setupCopyButton("copy-status", "su -c 'sh /data/adb/modules/filebase/action.sh status'");

  setTimeout(function() {
    showToastHtml(t("welcomeTitle"), t("welcomeHtml"), true, t("ready"), function() {});
  }, 400);
});
