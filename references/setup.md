# 环境安装与启动

## 能运行在哪里

需要 Python 3.10+、可显示浏览器的本地桌面、默认播放设备及可用的 loopback 输入。Windows 是本项目主要工作环境。macOS/Linux 是否可回录取决于实际系统设备与音频路由，不能仅凭 Python 依赖安装成功保证可用；详见[排障](troubleshooting.md)。无桌面/音频设备的 CI 只做离线测试。

无需 OpenAI API Key；服务内的 ASR 默认在本地执行。首次使用 faster-whisper 的模型名称时可能下载模型，需要网络与磁盘空间。具体模型下载、硬件支持以依赖自身为准，本项目不包含权重。

## 安装 skill 文件

本仓库根目录就是 skill；应完整复制或克隆，不能只复制 SKILL.md。建议安装目录命名为 `redbook-live-notes`。

当前官方文档列出的用户级发现目录为 `~/.agents/skills`，项目级为 `.agents/skills`。本地内置 skill-installer 也可能安装至 `$CODEX_HOME/skills` 或 `~/.codex/skills`；沿用宿主实际列出的可发现目录，不要同时安装多个同名副本。目录和自动发现说明参见 [OpenAI 官方 skill 文档](https://learn.chatgpt.com/docs/build-skills)。

Windows 手动安装示例（远程仓库需已包含本次封装文件）：

```powershell
$skillParent = Join-Path $HOME '.agents\skills'
$skillTarget = Join-Path $skillParent 'redbook-live-notes'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
if (Test-Path -LiteralPath $skillTarget) { throw '目标已存在，请先检查已有 skill；不要覆盖。' }
git clone https://github.com/OXOOOOX/RedBook_Stream_Notes.git $skillTarget
Set-Location -LiteralPath $skillTarget
```

也可把发布 ZIP 中的 `redbook-live-notes/` 文件夹放入发现目录，或让 `$skill-installer` 从仓库根路径 `.` 安装并命名 `redbook-live-notes`。如果宿主未显示新 skill，重启或刷新后再检查。已有同名 skill 时先比较版本和来源；本次封装不要求删除或覆盖旧安装。

## 安装 Python 依赖

在 skill 根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python scripts/redbook.py doctor
.\.venv\Scripts\python scripts/redbook.py doctor --audio
```

Linux/macOS 的虚拟环境解释器对应 `.venv/bin/python`，创建环境时可用 `python3`。操作系统音频依赖不由 pip 完整管理；遇到设备/动态库错误先看排障，不要无限重装 Python 包。

`doctor` 检查当前解释器的包存在性、时区数据和 Chromium 可执行文件，显示可选 FrameNotes 选择情况。`--audio` 额外枚举默认扬声器和对应回录输入，不录音。返回 0 表示这些静态检查通过，1 表示必要检查失败；不会验证实际播放、模型加载或 ASR 结果。

开发验证使用 `python -m pip install -e ".[dev]"`，额外包含 pytest 与 httpx。`requirements.txt` 作为兼容入口引用相同依赖声明。`tzdata` 用来确保干净环境可显示 Asia/Shanghai 日期。

## 启动与运行位置

前台启动：

```powershell
.\.venv\Scripts\python scripts/redbook.py serve
```

- 查看器：<http://127.0.0.1:8000/viewer>
- 接口说明：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

新终端中调用 health/recent/create 等客户端命令。serve 默认监听 `127.0.0.1:8000`，固定单 worker、禁用自动重载，默认数据目录为 skill 根目录下 `runtime/jobs`。生产式录制期间不要使用 `--reload`，不要启动多个 worker。

可显式选择工作目录外的数据位置：

```powershell
.\.venv\Scripts\python scripts/redbook.py serve --port 8010 --runtime-dir 'D:\LiveNotes\jobs'
.\.venv\Scripts\python scripts/redbook.py --api http://127.0.0.1:8010 health
```

`--runtime-dir` 表示直接存放 job 文件夹的目录，不再额外追加 `runtime/jobs`。相对路径按调用时当前目录解释，绝对路径更明确。裸 `uvicorn redbook_stream_notes.main:app` 则使用进程当前目录下 `runtime/jobs`。

Windows 后台运行示例：

```powershell
$skillRoot = (Get-Location).Path
$pythonPath = Join-Path $skillRoot '.venv\Scripts\python.exe'
$helperPath = Join-Path $skillRoot 'scripts\redbook.py'
$logDir = Join-Path $skillRoot 'runtime\service-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$serverProcess = Start-Process -FilePath $pythonPath `
  -ArgumentList @('"' + $helperPath + '"', 'serve') `
  -WorkingDirectory $skillRoot -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logDir "$runStamp.stdout.log") `
  -RedirectStandardError (Join-Path $logDir "$runStamp.stderr.log")
$serverProcess.Id
```

服务进程窗口隐藏；create 仍会打开可见的直播浏览器，这是完成登录/播放所需窗口。记录 PID、日志路径、端口与 job ID。`health` 响应前不要创建任务。关闭前台服务前，先停止活动任务并确认终态、导出；后台服务的退出由管理该进程的宿主完成，不按名称终止其他 Python 进程。

## 可选 FrameNotes

当前服务会检查 `REDBOOK_FRAMENOTES_ROOT/scripts/transcribe-audio.ps1`。没有设置时，尝试 skill 根目录的同级 `FrameNotes` 文件夹。示例：

```powershell
$env:REDBOOK_FRAMENOTES_ROOT = 'D:\Projects\FrameNotes'
.\.venv\Scripts\python scripts/redbook.py doctor
.\.venv\Scripts\python scripts/redbook.py serve
```

环境变量必须在启动服务前设置。子进程继承启动环境；其他终端里修改变量不会改变已运行服务。项目没有自动读取 `.env`，也没有其他 `REDBOOK_*` 环境变量接口。

选择 FrameNotes 还要求 PATH 中存在 `powershell`（只安装 `pwsh` 不满足条件）。脚本接收音频路径及 `-Model`、`-Language`、`-Device`，需要在音频同目录生成 `transcript.json`；segments 项至少包含 `index`、`start`、`end`、`text`，时间为该音频片段内相对秒数。

未选中 FrameNotes 时使用 faster-whisper。已选中但运行出错时任务会失败，不会自动回退。要明确使用 faster-whisper，可在启动前将 `REDBOOK_FRAMENOTES_ROOT` 指向一个没有该脚本的明确目录；不要重命名或删除用户已有工具。
