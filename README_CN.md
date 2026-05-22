# FileBase — Android 文件服务器

把 Android 手机变成全功能网页文件管理器。连接手机热点的任何设备打开浏览器即可浏览、上传、下载、编辑 `/sdcard` 内的所有文件——无需安装客户端 App。

[English Documentation](README.md)

---

## 功能

| 类别 | 说明 |
|------|------|
| **浏览** | 目录列表 + 可排序列（名称/大小/日期）+ 面包屑导航 + 实时搜索过滤 |
| **上传** | 按钮多选上传、拖放上传带进度条、二进制安全 multipart 解析 |
| **下载** | 单击下载 + 正确 MIME 类型 + RFC 5987 UTF-8 文件名编码 |
| **编辑** | 全屏等宽代码编辑器，保存后直接写回服务器（二进制文件受保护，不会被误编辑） |
| **管理** | 新建文件/文件夹、重命名、删除（带确认弹窗） |
| **国际化** | 中文 / English 切换 + localStorage 持久化；新用户默认英文；唯一用户标识 |
| **主题** | 深色 / 浅色模式，自动跟随系统 `prefers-color-scheme`，手动切换可记忆 |
| **响应式** | 桌面端表格布局 → 700px 断点切换移动端卡片布局 |
| **安全** | 路径穿越防护、POST 大小限制（上传/写入 100 MB，元数据 64 KB）、data-* 事件委托（无内联 onclick）、POST 请求跨域防护 |

## 发布文件

| 文件 | 用途 |
|------|------|
| `dist/webserver.tar.gz` | 独立版：`server.py` + `launch.sh` + `stop.sh` + README |
| `dist/filebase-v2.0.2.zip` | Magisk / KernelSU / APatch 卡刷模块（含 WebUI 面板 + 日志管理） |

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

模块提供**持久化系统级安装**，支持开机自启、Root 管理器内一键控制、可选的图形 WebUI 面板。

### 安装

1. 下载 `dist/filebase-v2.0.2.zip`
2. Root 管理器 → 模块 → 从本地安装 → 选择 zip
3. 无需重启——安装后即可使用 **Action** 按钮

**支持管理器：** Magisk 28.0+、KernelSU 1.0.2+、APatch（最新版）

### 使用方式

| 方式 | 操作 |
|------|------|
| **Action 按钮** | Root 管理器模块列表点"Action" → 执行 `action.sh`（start/stop/restart/status/log） |
| **WebUI 面板** | 需安装 [KSUWebUIStandalone](https://github.com/5ec1cff/KsuWebUIStandalone) 或 [MMRL](https://github.com/MMRLApp/MMRL) → 图形按钮 + 实时状态 + 日志级别选择 |
| **终端** | `su -c 'sh /data/adb/modules/filebase/action.sh start'` |

### action.sh 命令

```
sh action.sh start          启动服务器（自动检测热点、随机 IP、iptables）
sh action.sh stop           停止服务器 + 清理 IP 别名 + iptables
sh action.sh restart        重启
sh action.sh status         查看状态（PID、绑定 IP、网卡、日志级别、连通性）
sh action.sh log [N]        查看最后 N 行日志（默认 50）
```

### WebUI 功能

- **启动 / 停止 / 重启** 按钮（带超时保护）
- **实时状态**：PID、绑定 IP、网卡、日志级别
- **日志级别选择**：`Info` · `Error` · `Debug` · `Off` — 自动保存到 `logs/.config`
- **中英切换**：localStorage 记忆

### 日志级别

| 级别 | 效果 |
|------|------|
| `info`（默认） | 记录客户端 IP + HTTP 方法 + 状态码 |
| `error` | 仅 4xx / 5xx 错误 |
| `debug` | 时间戳、IP:端口、方法、完整路径 |
| `off` | 不输出日志（stdout → /dev/null） |

日志文件：`<模块目录>/logs/server.log`。可通过 WebUI 下拉菜单或直接写入 `logs/.config` 配置。

---

## API 接口

所有端点以 `/api` 开头。

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/list?path=<路径>` | 列出目录内容 |
| `GET` | `/api/download?path=<路径>` | 下载文件（RFC 5987 UTF-8 文件名） |
| `POST` | `/api/upload` | 上传文件 — `multipart/form-data` |
| `POST` | `/api/write` | 创建/覆盖文件 — JSON `{path, content}` |
| `POST` | `/api/delete` | 删除文件或目录 — JSON `{path}` |
| `POST` | `/api/mkdir` | 创建目录 — JSON `{path}` |
| `POST` | `/api/rename` | 重命名/移动 — JSON `{oldPath, newPath}` |
| `POST` | `/api/login` | 管理员登录 — JSON `{user, pass}` → `{ok, token}` |
| `POST` | `/api/logout` | 管理员注销 — 作废 token |
| `GET` | `/api/auth` | 检查管理员认证状态 → `{admin: bool}` |

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
├── service.sh                 开机自启
├── uninstall.sh               卸载清理
├── common/                    服务器文件 → 安装时复制到模块根目录
│   ├── server.py
│   ├── launch.sh
│   └── stop.sh
├── webroot/
│   └── index.html             WebUI 控制面板
├── META-INF/                  卡刷兼容
├── build.sh                   一键构建 zip
└── filebase-v2.0.2.zip        已构建的刷入包

dist/                          发布归档
├── webserver.tar.gz           独立版
└── filebase-v2.0.2.zip        卡刷模块
```

### 前端设计

- **字体**：Bebas Neue（品牌标题）、Figtree（UI 正文）、JetBrains Mono（代码/数据）
- **主题**：CSS 自定义属性 + `[data-theme="dark"]` / `[data-theme="light"]`
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

## 许可证

MIT
