# FileBase — Android 文件服务器

把 Android 手机变成全功能网页文件管理器。连接手机热点的任何设备打开浏览器即可浏览、上传、下载、编辑 `/sdcard` 内的所有文件——无需安装客户端 App。

[English Documentation](README.md)

---

## 功能

| 类别 | 说明 |
|------|------|
| **浏览** | 虚拟列表在 2 万文件下依然 60 fps；可排序（名称/大小/日期）、面包屑、快捷入口与实时过滤 |
| **预览** | 图片、视频、音频、PDF、文本都在玻璃面板中就地打开，无需下载后再看 |
| **上传** | 批量多文件上传带实时进度、支持文件夹上传、拖放上传；单请求 100 MB，流式落盘不占内存 |
| **下载** | 单击下载 + 正确 MIME 类型 + RFC 5987 UTF-8 文件名 + HTTP Range（断点续传 / 视频拖动） |
| **编辑** | 玻璃面板中的代码编辑器，Ctrl/Cmd + S 保存，二进制保护 + 5 MB 上限，未保存修改有自定义确认 |
| **管理** | 新建文件/文件夹、重命名、移动、多选批量删除、复制路径、玻璃确认弹窗 |
| **导航** | URL 与历史记录同步（前进/后退可用）、目录缓存、键盘快捷键（`/` 搜索、`U` 上传、`N` 新建、`Ctrl+A` 全选） |
| **国际化** | 中文 / English 切换 + localStorage 持久化；首次访问跟随浏览器语言 |
| **主题** | Liquid Glass 深色 / 浅色主题，自动跟随 `prefers-color-scheme`，手动切换可记忆 |
| **响应式** | 桌面网格 → 820px 以下移动端列表 + 底部面板 + 扩展 FAB |
| **安全** | 路径穿越防护、POST 大小限制、CSRF 跨域检查、管理员 Bearer 令牌会话 |
| **并发** | 多线程请求处理；HTML 与大体积 JSON 列表启用 gzip；UI 使用 ETag/304 |

### 性能说明

- 列目录只做一次 `os.scandir`，不再为了判断“是否文本”而打开每个文件。
- 管理员模式优先直接读文件系统，只有真正遇到权限错误才回退到 `su`。
- 上传先写入临时文件再内存映射，100 MB 上传不再需要 200 MB 内存。
- 文件列表只渲染可见行；2 万个文件大约只有 20 个 DOM 节点。

## 发布文件

| 文件 | 用途 |
|------|------|
| `dist/webserver.tar.gz` | 独立版：`server.py` + `launch.sh` + `stop.sh` + README |
| `dist/filebase-v6.0.0.zip` | Magisk / KernelSU / APatch 卡刷模块（含 WebUI 面板 + 日志管理） |

## 环境要求

### 服务器端（Android 手机）

- **Root 权限**（`su`）— iptables + 辅助 IP 需要；直接运行可免 root
- **Python 3.8+** — Termux 安装（`pkg install python`）或 Magisk 模块自带
- **移动热点** 已开启（热点模式）；Wi‑Fi 局域网也可用

### 客户端（连接设备）

- 任意浏览器（手机/平板/电脑），连接到手机热点/Wi‑Fi 即可

---

## 快速开始（独立版）

### 1. 推送文件

```bash
adb push server.py launch.sh stop.sh /data/local/tmp/
adb shell chmod +x /data/local/tmp/launch.sh /data/local/tmp/stop.sh
```

### 2. 打开热点

设置 → 热点和网络共享 → WLAN 热点。

### 3. 启动

```bash
su
sh /data/local/tmp/launch.sh
```

启动脚本自动检测热点网卡和 IP、在同子网选取随机辅助 IP（如 `192.168.43.172`）、配置 iptables 并启动服务器：

```
╔══════════════════════════════════════════════════════════╗
║  服务器已启动！访问地址：                                ║
║  http://192.168.43.172:6532                             ║
║  http://192.168.43.172  (80 端口自动转发)               ║
║  服务目录: /sdcard                                      ║
║  日志级别: info    日志文件: logs/server.log             ║
╚══════════════════════════════════════════════════════════╝
```

### 4. 停止

```bash
sh /data/local/tmp/stop.sh
```

### 无 Root 运行

```bash
python3 /data/local/tmp/server.py
# 浏览器访问 http://<手机IP>:6532
```

---

## Magisk / KernelSU / APatch 模块

模块提供**持久化系统级安装**，支持 Root 管理器内一键控制、可选的图形 WebUI 面板。**服务器不会开机自启**——由你显式启动/停止（Action 按钮、WebUI 或终端命令）。这样也避免了"开机时热点还没起来、随机 IP 配置失败"的老问题。

### 安装

1. 下载 `dist/filebase-v6.0.0.zip`
2. Root 管理器 → 模块 → 从本地安装 → 选择 zip
3. **需要重启一次。** KernelSU/Magisk 会把新模块先放在 `modules_update/`，重启时才合并生效，所以重启前 `action.sh` 和 `webroot/` 都还不存在——此时 WebUI 会被拒绝打开，Action 按钮也会失败。
4. 重启后再使用 **Action** 按钮或打开 WebUI

**支持管理器：** Magisk 28.0+、KernelSU 1.0.2+、APatch（最新版）

### 使用方式

| 方式 | 操作 |
|------|------|
| **Action 按钮** | Root 管理器模块列表点"Action" → 未运行则启动、已运行则停止（即 `action.sh toggle`；也支持 start/stop/restart/status/log） |
| **WebUI 面板** | 在 KernelSU 管理器模块页直接打开（管理器会用 WebView 渲染 `webroot/`）；Magisk / APatch 需 [KSUWebUIStandalone](https://github.com/5ec1cff/KsuWebUIStandalone) 或 [MMRL](https://github.com/MMRLApp/MMRL) |
| **终端** | `su -c 'sh /data/adb/modules/filebase/action.sh start'` |

### action.sh 命令

```
sh action.sh start          启动服务器（自动检测热点、随机 IP、iptables）
sh action.sh stop           停止服务器 + 清理 IP 别名 + iptables
sh action.sh restart        重启
sh action.sh toggle         未运行则启动，已运行则停止
sh action.sh status         查看状态（PID、绑定 IP、网卡、日志级别、连通性）
sh action.sh info           机器可读的 KEY=VALUE 状态（WebUI 使用）
sh action.sh log [N]        查看最后 N 行日志（默认 50）
sh action.sh loglevel [级别]  读取（不带参数）或设置日志级别
```

KernelSU 执行 Action 按钮时用的是 `ksud module action <id>`，**不传任何参数**，
因此无参数时的默认行为是 `toggle`：点了就启动（未运行时）或停止（运行中）。
（此前默认是 `status`，所以按钮永远只显示 "Server STOPPED"。）

### WebUI 功能

面板严格按 KernelSU 的[模块 WebUI 指南](https://kernelsu.org/zh_CN/guide/module-webui.html)编写：

- **入口** 是 `webroot/index.html`，CSS/JS 与它同级；权限与 SELinux context
  按指南交给 KernelSU 处理，模块自己不设置。
- **Shell 交互使用官方 `kernelsu` 库**：
  `const { errno, stdout, stderr } = await exec(cmd)`。该库以 `webroot/kernelsu.js`
  原样内置（Apache-2.0），因此无需打包器即可 `import`。此前使用的同步
  `ksu.exec(cmd)` 字符串写法**不是**指南里的接口，换 WebUI 宿主就会失效。
- **模块目录来自 `moduleInfo()`**，不再写死路径。
- **原生 Toast** 使用库提供的 `toast()`。
- **启动 / 停止 / 重启** 按钮带超时保护。
- **实时状态**（PID、地址、网卡、日志级别）来自 `action.sh info` 这个稳定的
  `KEY=VALUE` 契约，而不是去解析给人看的文本。
- **日志级别选择**：`Info` · `Error` · `Debug` · `Off`。
- **中英切换**：首次访问跟随浏览器语言。
- **控制台显示完整输出**。KernelSU 执行 `exec()` 用的是临时 root shell，
  命令返回后该 shell 就被销毁，所以命令的 stdout 可能为空或被截断（用
  `cmd &` 起的服务也会跟着一起被杀）。因此 FileBase 用 `setsid` 启动服务，
  并让 `action.sh` 把完整输出落盘到 `logs/action.log`，WebUI 再把这个文件
  读回来显示；启动/重启后还会附上 `logs/server.log`，里面有绑定地址和
  Python 报错。
- **地址始终可查**。服务端会把 `PID/HOST/PORT/IFACE/IP` 写进运行时状态文件，
  因此即使监听在 `0.0.0.0` 或日志级别为 `off`，面板也能显示访问地址。

### 日志级别保存在哪里

按[模块配置指南](https://kernelsu.org/zh_CN/guide/module-config.html)，该值通过
KernelSU 的模块配置系统持久化：

```sh
ksud module config set log_level debug     # action.sh 会自动设置 KSU_MODULE
```

在 Magisk / APatch 上（没有 `ksud`）回退到 `logs/.config`。`action.sh` 读取时
优先 ksud 配置、其次文件；每次修改都会同时写入两处，因此在 KernelSU 上卸载
管理器也不会丢失，在其他管理器上同样可用。

### 日志级别

| 级别 | 效果 |
|------|------|
| `info`（默认） | 记录客户端 IP + HTTP 方法 + 状态码 |
| `error` | 仅 4xx / 5xx 错误 |
| `debug` | 时间戳、IP:端口、方法、完整路径 |
| `off` | 不输出日志（stdout → /dev/null） |

日志文件：`<模块目录>/logs/server.log`。可通过 WebUI 下拉菜单、`sh action.sh loglevel <级别>` 或 `ksud module config set log_level <级别>` 设置（见上文）。新的日志级别在服务器**下次启动**时生效——想立即应用请在 WebUI 中点「重启」。

### 自行构建刷入包

```bash
sh "Magisk Module/build.sh"
```

脚本会先把仓库根目录的 `server.py` / `launch.sh` / `stop.sh` 同步到
`Magisk Module/common/`，再生成 `dist/filebase-<版本>.zip` 与全新的
`dist/webserver.tar.gz`。GitHub Release 流程使用同一个脚本，因此发布包
不会夹带旧版 server。

---

## API 接口

所有端点以 `/api` 开头。

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/list?path=<路径>` | 列出目录内容（加 `compact=1` 返回位置数组，超大目录体积约减少 60%） |
| `GET` | `/api/download?path=<路径>` | 下载文件（RFC 5987 文件名，支持 HTTP `Range`；预览用 `inline=1`） |
| `POST` | `/api/upload` | 上传文件 — `multipart/form-data` |
| `POST` | `/api/write` | 创建/覆盖文件 — JSON `{path, content, overwrite?}`（`overwrite:false` 时若已存在返回 409） |
| `POST` | `/api/delete` | 删除文件或目录 — JSON `{path}`，批量用 `{paths: [...]}` |
| `POST` | `/api/mkdir` | 创建目录 — JSON `{path}` |
| `POST` | `/api/rename` | 重命名/移动 — JSON `{oldPath, newPath}` |
| `POST` | `/api/login` | 管理员登录 — JSON `{user, pass}` → `{ok, token}` |
| `POST` | `/api/logout` | 管理员注销 — 作废 token |
| `GET` | `/api/auth` | 检查管理员认证状态 → `{admin: bool}` |
| `GET` | `/api/text?path=<路径>` | 编辑器读取文本（二进制 415，超过 5 MB 返回 413） |
| `GET` | `/api/stats` | 当前根目录的磁盘用量 |

下载支持单段 `Range: bytes=...` 请求（返回 206 部分内容，越界返回 416），
因此大文件可以断点续传。管理员通常使用 `Bearer` 请求头认证；浏览器原生
下载（`<a download>`）无法发送请求头，可改为在 URL 后附加
`&token=<token>`。

### 返回格式

**成功**（`/api/list`）：
```json
{ "entries": [{ "name": "照片.jpg", "isdir": false, "size": 2048, "mtime": 1700000000, "editable": true }] }
```

**成功**（其他 POST）：
```json
{ "ok": true }
```

**错误**：
```json
{ "error": "错误描述" }
```

---

## 项目结构

```
server.py                      HTTP 服务器 + 内嵌单页前端
launch.sh                      Root 启动器（网卡扫描、iptables、随机 IP）
stop.sh                        优雅停止（移除 IP 别名、清理 iptables）

README.md / README_CN.md       文档（英文 / 中文）

magisk_module/                 Magisk/KSU/APatch 模块源码
├── module.prop                多 root 元数据（ksu=1, sufs=1）
├── customize.sh               安装脚本
├── action.sh                  控制入口（启动/停止/状态/日志）
├── uninstall.sh               卸载清理
├── common/                    服务器文件 → 安装时复制到模块根目录
│   ├── server.py
│   ├── launch.sh
│   └── stop.sh
├── webroot/
│   ├── index.html             WebUI 入口（指南要求）
│   ├── script.js               WebUI 逻辑（ES 模块，import kernelsu.js）
│   ├── kernelsu.js            KernelSU 官方 WebUI 库（原样内置）
│   └── style.css              WebUI 样式
├── META-INF/                  卡刷兼容
└── build.sh                   一键构建 zip + 独立版 tar.gz

dist/                          发布归档
├── webserver.tar.gz           独立版
└── filebase-v6.0.0.zip        卡刷模块
```

### 前端设计

**设计语言 — Liquid Glass × Material 3 Expressive**

- **玻璃质感**：多层半透明、1px 高光描边、内阴影与细微噪点；用渐变光晕代替 blur 滤镜，在手机上依然轻量
- **M3 Expressive**：大圆角、色调色块、弹簧动效（`cubic-bezier(.22,1.2,.36,1)`）、扩展 FAB、底部面板，WebUI 使用 M3 导航栏
- **字体**：只使用系统字体，不请求外部网络字体，完全离线可用
- **主题**：CSS 自定义属性 + `[data-theme="dark"]` / `[data-theme="light"]`，支持的浏览器在切换时使用 View Transition
- **动效预算**：只动画 transform/opacity，列表虚拟化，并支持 `prefers-reduced-motion` 与 `prefers-reduced-transparency`
- **国际化**：`data-i18n` 属性模板驱动，`localStorage` 持久化
- **安全**：文件操作使用 `data-*` 属性 + 事件委托，无内联 `onclick`
- **上传**：原生文件输入框透明度隐藏（非 `display:none`），兼容所有浏览器

---

## 超级管理员

FileBase 内置隐藏的超级管理员模式，可管理安卓手机的整个文件系统。

### 如何访问

1. 网页端右上角控制区直接显示**管理**按钮
2. 点击后弹出登录对话框
3. 管理按钮始终可见

### 登录凭据

| 字段 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `hotsteel` |

### 管理员模式变化

- **文件根目录**从 `/sdcard` 变为 `/`——可访问安卓整个文件系统
- 可以从 `/sdcard` 向上导航到根目录，浏览 `/data`、`/system`、`/proc` 等
- 所有操作（上传、删除、重命名、编辑）对服务器进程可访问的任何路径生效
- 页脚显示 `服务中: /` 而非 `服务中: /sdcard`
- 界面中出现红色 **管理员** 标识

### 安全说明

- 管理员 token 存储在浏览器 `localStorage` 中，每次请求都会在服务端验证
- 登录端点使用固定用户名/密码——生产环境请修改 `server.py` 中的 `ADMIN_USER` 和 `ADMIN_PASS`

---

## 常见问题

| 问题 | 解决方法 |
|------|----------|
| `找不到 Python` | 通过 Termux 安装（`pkg install python3`）或手动推送二进制 |
| `未检测到热点 IP` | 确保启动脚本前已**开启**热点；模块会扫描所有网卡 |
| 上传按钮不弹出文件选择器 | 已修复——改用 opacity 隐藏输入框，不使用 `display:none` |
| 主题切换无效 | 已修复——SVG 图标改用 `<span>` 包裹，兼容所有浏览器 innerHTML |
| 中文文件名下载报错 | 已修复——RFC 5987 `filename*=UTF-8''...` 编码 |
| 模块 WebUI 点击启动卡住 | 已修复——命令后台执行 + 15 秒超时保护 |
| 客户端无法访问 | 确认客户端连接的是手机热点 Wi‑Fi 而非移动数据 |
| `grep: Unknown option` | 已修复——Android busybox 环境改用 `sed` |
| `error` 日志级别没有任何输出 | 已修复——4xx/5xx 过滤现在能正确解析状态码 |
| 管理员无法下载 `/data` 下的文件 | 已修复——管理员下载会携带 token，大文件改为流式传输 |
| 一个大文件下载会卡死整个页面 | 已修复——服务器改为多线程 |
| 大文件无法断点续传 | 已修复——已支持 HTTP Range |
| WebUI 显示「API 不可用」 | 页面没有在 WebUI 宿主的 WebView 中打开——请从 KernelSU 管理器模块页进入（Magisk/APatch 用 KSUWebUIStandalone / MMRL）；页面上会显示终端备用命令 |
| WebUI 按钮没有反应 | 面板依赖 `kernelsu` WebUI 桥接；请确认模块已启用，且安装后重启过 |
| 刚安装完 Action 按钮 / WebUI 打不开 | 需要先重启一次。新模块会先放在 `modules_update/`，重启时才合并，重启前 `action.sh` 和 `webroot/` 都还不存在 |
| 需要安装 metamodule 吗？ | 不需要。FileBase 从不修改 `/system`，因此 KernelSU 对「挂载 system/ 目录」才要求的 metamodule 并不适用 |
| 没有日志 / 找不到 IP 和端口 | 看 `logs/action.log`（上一条命令的完整输出）和 `logs/server.log`（服务端自身输出），WebUI 控制台两者都会显示；运行时状态文件里也始终记录着地址 |
| 切换日志级别好像没反应 | 新级别在服务器**下次启动**时生效——点「重启」（或 `action.sh restart`）。级别为 `off` 时 `logs/server.log` 会被清空 |
| 从面板启动后服务立刻消失 | 已修复——服务用 `setsid` 启动，能脱离管理器临时 root shell 存活 |

## 许可证

MIT
