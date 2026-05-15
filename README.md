# RedBook Stream Notes

用户提交小红书直播分享链接后，服务会打开网页版页面，持续录制系统播放音频，分段 ASR，并把转写内容汇总成可读 note。

当前实现是 MVP：它不绕过小红书登录、风控或播放限制。如果页面要求登录或点击播放，需要在打开的浏览器窗口里人工完成；服务负责持续监听系统输出音频、转写和汇总。

## 功能

- `POST /jobs`：创建直播监听任务
- `GET /jobs/{job_id}`：查看任务状态、转写片段和实时 note
- `POST /jobs/{job_id}/stop`：停止任务
- Playwright 打开直播分享链接
- Windows/macOS/Linux 通过 `soundcard` 录制默认扬声器 loopback
- 优先复用本机 FrameNotes 的 `transcribe-audio.ps1`
- 未配置 FrameNotes 时，使用 `faster-whisper` 直接转写

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m playwright install chromium
```

如果要优先复用 FrameNotes，请设置 `REDBOOK_FRAMENOTES_ROOT` 指向本机 FrameNotes 仓库根目录，或把 FrameNotes 放在本项目同级目录：

```text
..\FrameNotes\scripts\transcribe-audio.ps1
```

## 启动

```powershell
.\.venv\Scripts\python -m uvicorn redbook_stream_notes.main:app --reload --host 127.0.0.1 --port 8000
```

打开接口文档：

```text
http://127.0.0.1:8000/docs
```

## 创建任务

```powershell
$body = @{
  url = "https://www.xiaohongshu.com/..."
  chunk_seconds = 60
  language = "auto"
  asr_model = "small"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/jobs -ContentType 'application/json' -Body $body
```

## 重要限制

- 录音源是系统默认扬声器 loopback。开始任务前请把直播声音路由到默认播放设备，并避免同时播放其他音频。
- 浏览器不会自动处理验证码、登录弹窗、App 唤起和平台风控。
- 长时间任务会在 `runtime/jobs/<job_id>/` 下持续生成音频片段、转写 JSON/TXT 和 note。
- 不会批量删除生成文件；清理历史任务请手动删除对应目录。
