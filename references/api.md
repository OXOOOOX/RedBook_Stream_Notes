# 本地服务 API 与输出约定

本页依据 `src/redbook_stream_notes/main.py`、`schemas.py`、`jobs.py`、`asr.py`、`browser.py`、`config.py` 和 `notes.py` 描述当前实现。示例假定服务已在 `http://127.0.0.1:8000` 启动；端口以实际启动命令为准。URL、任务 ID、路径均为占位示例。

## 接口范围

| 方法 | 路径 | 返回内容 |
| --- | --- | --- |
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/viewer` | 内置中文监听页面，`text/html` |
| `GET` | `/jobs/recent` | 当前进程最近创建的最多 20 个任务快照，按创建时间倒序 |
| `POST` | `/jobs` | 创建任务并立即返回初始快照 |
| `GET` | `/jobs/{job_id}` | 指定任务的当前完整快照 |
| `GET` | `/jobs/{job_id}/events` | SSE 任务快照流，`text/event-stream` |
| `POST` | `/jobs/{job_id}/stop` | 提出停止请求，并返回当时的任务快照 |

成功响应使用 HTTP 200；创建接口没有设置 HTTP 201。查询、订阅或停止不存在的任务返回 HTTP 404，响应体为 `{"detail":"job not found"}`。不满足请求模型的输入由 FastAPI/Pydantic 返回 HTTP 422。浏览器、音频设备或 ASR 在任务创建后出错，通常表现为任务快照中的 `status: "failed"` 和 `error`，而不是创建接口返回 HTTP 500。

服务没有实现身份认证、任务删除、任务重启、磁盘任务恢复、音频上传、笔记修改、文件下载或精炼笔记获取接口。`/health` 仅检查 HTTP 应用可响应，不会检查扬声器、浏览器、模型或 FrameNotes。服务用于本地操作；将监听地址改为公共网卡并不会自动增加访问控制。

## 创建任务

`POST /jobs` 接收 JSON 对象：

| 字段 | 类型 | 默认值 | 当前约束与实际用途 |
| --- | --- | --- | --- |
| `url` | HTTP/HTTPS URL | 必填 | Pydantic `HttpUrl` 校验；后端直接导航此地址，不会从整段分享文本提取链接，也没有限定域名 |
| `chunk_seconds` | 整数 | `60` | `15` 至 `600`，包含边界；每个正式录音分段的目标秒数 |
| `language` | 字符串 | `"auto"` | 原样交给 ASR；fallback 中 `auto` 表示不指定语言，否则传给 `language` 参数 |
| `asr_model` | 字符串 | `"small"` | 原样交给模型后端；模型名或可用路径由后端解释 |
| `asr_device` | 字符串 | `"auto"` | FrameNotes 分支原样传递；faster-whisper 分支将 `auto` 映射为 `cpu` |
| `headless` | 布尔值 | `false` | 是否以无界面方式启动 Playwright Chromium；默认保留窗口供播放和登录检查 |
| `max_chunks` | 整数或 `null` | `null` | 指定时必须大于等于 `1`；达到正式分段数量后自动停止 |

`language`、`asr_model` 和 `asr_device` 没有在请求模型中使用枚举验证，因此 HTTP 创建成功不等于所填值一定被 ASR 支持。`max_chunks` 统计已处理分段，静音段也计入；音频预检不计入。

```powershell
$baseUri = 'http://127.0.0.1:8000'
$requestBody = @{
    url = 'https://www.xiaohongshu.com/livestream/REPLACE_WITH_LIVE_ID'
    chunk_seconds = 60
    language = 'auto'
    asr_model = 'small'
    asr_device = 'auto'
    headless = $false
    max_chunks = 2
} | ConvertTo-Json

$job = Invoke-RestMethod -Method Post -Uri "$baseUri/jobs" `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($requestBody))
$job.id
$job.status
```

将占位 URL 换为真实直播链接后执行。使用短链接时，浏览器通过正常页面导航处理网站重定向，服务没有单独的短链接解析 API。持续监听可删除 `max_chunks` 字段或将其设为 `$null`。

初始快照通常为 `starting`，尚不能说明直播已播放或音频可用。创建请求将任务加入当前进程的内存字典，并在后台启动异步工作任务。

## 任务快照

所有返回任务的接口使用同一个 `JobSnapshot` 结构：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | 字符串 | UUID 十六进制字符串的前 12 位，用于本进程任务索引和输出目录名 |
| `url` | 字符串 | 请求 URL 经 `HttpUrl` 处理后转为字符串；不是浏览器最终重定向 URL |
| `status` | 字符串 | `starting`、`listening`、`stopping`、`stopped`、`failed` |
| `created_at` | 日期时间字符串 | 创建时间，使用带 UTC 时区的时间对象序列化 |
| `updated_at` | 日期时间字符串 | 最近一次调用任务 `touch()` 的时间；不会在每次 HTTP 读取时改变 |
| `chunks_completed` | 整数 | 完成处理的正式录音分段数，包含跳过 ASR 的静音段 |
| `note` | 字符串 | 当前滚动 Markdown 笔记或阶段提示；不包含 `refined_note.md` 文件正文 |
| `ended_reason` | 字符串或 `null` | 自动结束原因；手动停止通常保留 `null` |
| `error` | 字符串或 `null` | 工作任务捕获到的异常消息 |
| `segments` | 数组 | 当前累计的完整转写片段列表；API 没有分页或条数裁剪 |

单个 `TranscriptSegment`：

```json
{
  "index": 1,
  "start": 1.25,
  "end": 4.8,
  "start_text": "00:00:01.250",
  "end_text": "00:00:04.800",
  "text": "这里是示例转写内容。"
}
```

`index` 在内存任务中从 1 开始累计编号。`start`、`end` 为相对于正式分段序列的秒数，公式为“该段 ASR 时间 + 之前已完成段数 × `chunk_seconds`”；格式化字段为 `HH:MM:SS.mmm`。它们不是直播原始时间码，也不是从任务创建时刻连续计算的墙钟时间。浏览器启动、音频预检和 ASR 等待时间均不会加到时间轴中。

```powershell
$snapshot = Invoke-RestMethod -Uri "$baseUri/jobs/$($job.id)"
$snapshot | Select-Object id, status, chunks_completed, ended_reason, error
$snapshot.segments | Select-Object -Last 5
$snapshot.note

$recent = Invoke-RestMethod -Uri "$baseUri/jobs/recent"
$recent | Select-Object id, status, created_at, chunks_completed
```

`/jobs/recent` 只查看当前进程内存。服务重启后历史任务文件仍可能存在，但旧 ID 会返回 404。多个服务进程也不会共享此字典，应以单进程运行此实现。

## 状态与结束语义

正常状态大致为 `starting → listening → stopped`。用户停止时可能看到 `stopping`；工作流程捕获异常时变为 `failed`。

| 状态 | 能确定的事实 | 不能据此确定的事实 |
| --- | --- | --- |
| `starting` | 后台任务已经创建 | 浏览器或音频已就绪 |
| `listening` | 浏览器打开流程已返回，任务正在预检、录音或转写 | 当前有声音、每秒产生文字、已经完成模型加载 |
| `stopping` | 已设置停止事件 | 当前录音或 ASR 已被打断、浏览器已关闭 |
| `stopped` | 工作循环正常结束并执行了精炼笔记写入逻辑 | 一定有转写或精炼文件、浏览器清理一定已经完成 |
| `failed` | 工作流程捕获了异常，详情在 `error` | 已完整收尾或生成最终精炼笔记 |

停止接口先将状态设为 `stopping` 并设置事件，最多等待后台任务 5 秒后返回。它不取消正在执行的录音线程、ASR 子进程或模型计算。若在录音中请求停止，通常仍会完成当前整段录音、检查直播状态并进行该段 ASR，然后才退出循环。初始化或预检阶段也没有每一步立即检查停止事件。

推荐在发出停止前读取状态，只对活动任务发一次停止请求，再轮询到 `stopped` 或 `failed`：

```powershell
$snapshot = Invoke-RestMethod -Uri "$baseUri/jobs/$($job.id)"
if ($snapshot.status -notin @('stopped', 'failed', 'stopping')) {
    $snapshot = Invoke-RestMethod -Method Post -Uri "$baseUri/jobs/$($job.id)/stop"
}

while ($snapshot.status -notin @('stopped', 'failed')) {
    Start-Sleep -Seconds 2
    $snapshot = Invoke-RestMethod -Uri "$baseUri/jobs/$($job.id)"
    $snapshot | Select-Object status, chunks_completed, ended_reason, error
}
```

当前停止操作不是可靠的幂等终态操作：对已经 `stopped` 或 `failed` 的任务再次调用 `/stop`，仍会把状态改为 `stopping`，已经结束的后台任务不会再恢复终态。避免重复停止已经终结的任务。

`ended_reason` 的当前来源：

| 值 | 触发条件 |
| --- | --- |
| `max_chunks_reached` | 下一轮正式录音前发现已达到 `max_chunks` |
| 页面命中的中文关键词 | 页面正文前 5,000 字包含结束词之一 |
| `media-ended` | 页面任一 `video` 或 `audio` 的 `ended` 为真 |
| `live_ended` | 管理器收到 `ended=true` 但没有原因时使用的兜底值；当前页面检查函数正常路径会给出具体原因 |
| `null` | 常见于用户停止；失败也可能没有结束原因 |

结束词按代码数组顺序匹配：`直播已结束`、`直播结束`、`主播已离开`、`主播暂时离开`、`本场直播已结束`、`已下播`、`回放`。这是页面启发式判断，可能将正文中的无关词或暂时离开误判为结束。检查在录音前和录音后各进行一次；没有独立的持续页面监控线程。静音本身不触发自动结束。

## SSE 快照流

`GET /jobs/{job_id}/events` 使用 `event: job` 事件，`data` 是完整任务快照 JSON：

```text
event: job
data: {"id":"EXAMPLE_JOB_ID","status":"listening", "...":"此处省略其他快照字段"}

```

以上数据只展示协议形状，实际事件包含完整快照。服务约每 2 秒检查一次状态，只有以下签名发生变化时发送新事件：`status`、`chunks_completed`、片段数量、`updated_at`、`ended_reason`、`error`。首次连接会发送当前快照；`stopped` 或 `failed` 的最后一个快照发送后关闭流。

没有逐词 token 流、增量片段事件、事件 ID、历史重放或固定频率心跳。客户端重新连接时得到当前完整快照；没有新快照时，连接可能长时间没有数据。服务器返回 `Cache-Control: no-cache`、`Connection: keep-alive` 和 `X-Accel-Buffering: no`。

可将以下 Python 标准库示例保存为单独文件后运行；替换任务 ID：

```python
import json
from urllib.request import Request, urlopen

base_url = "http://127.0.0.1:8000"
job_id = "REPLACE_WITH_JOB_ID"
request = Request(
    f"{base_url}/jobs/{job_id}/events",
    headers={"Accept": "text/event-stream"},
)

event_name = None
data_lines = []
with urlopen(request) as response:
    for raw_line in response:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line == "":
            if event_name == "job" and data_lines:
                snapshot = json.loads("\n".join(data_lines))
                print(
                    snapshot.get("status"),
                    snapshot.get("chunks_completed"),
                    snapshot.get("ended_reason"),
                    snapshot.get("error"),
                    flush=True,
                )
                if snapshot.get("status") in {"stopped", "failed", "missing"}:
                    break
            event_name, data_lines = None, []
        elif line.startswith("event:"):
            event_name = line[6:].lstrip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
```

首次访问未知任务会直接返回 HTTP 404。服务也有“订阅途中任务从内存消失”的防御分支，会发出 `{"status":"missing","error":"job not found"}` 后关闭流；当前代码没有提供删除任务的接口。

## 内置页面的差异

`/viewer` 可以接收一段小红书分享文本。其前端正则提取 `xhslink.com`、`www.xiaohongshu.com` 或 `xiaohongshu.com` 的 HTTP/HTTPS 链接，并清除末尾部分中文标点或括号；API 本身没有此提取逻辑。

页面创建任务时固定发送 `chunk_seconds: 60`、`language: "auto"`、`asr_model: "small"`、`asr_device: "auto"`、`headless: false`。页面没有这些参数的输入控件，也不设置 `max_chunks`。自定义参数应使用 API。页面可连接已有任务 ID，通过 `EventSource` 显示完整快照中的笔记，以及最近 250 条转写片段。

## 文件落盘与时间语义

输出根目录由 `settings.runtime_dir` 决定。裸 Uvicorn 启动时默认是相对于服务工作目录的 `runtime/jobs`；`scripts/redbook.py serve` 会固定为 skill 根目录下 `runtime/jobs`，也可用 `--runtime-dir` 指定直接存放 job 文件夹的目录。默认示例：

```text
C:\work\redbook-live-notes\runtime\jobs\<job_id>\
├── probe\
│   ├── audio_probe_1.wav
│   ├── audio_probe_2.wav       # 仅在前一次探测未达音量阈值时出现
│   └── audio_probe_3.wav       # 同上
├── chunk_0001\
│   ├── audio.wav
│   └── transcript.json        # 该段实际执行并成功完成 ASR 时出现
├── chunk_0002\
│   └── ...
├── note.md
└── refined_note.md            # 正常结束且至少有一个转写片段时写入
```

文件不是全部预创建的。创建任务只创建任务目录；初始 `note` 先存在于内存。预检仍静音、正式静音分段、正常转写或部分结束路径才会写 `note.md`。异常路径不会统一补写全部文件。FrameNotes 后端可能额外输出其他文件，具体以外部脚本为准。

| 文件 | 当前行为 |
| --- | --- |
| `probe/audio_probe_*.wav` | 每次预检最多录 3 次，每次 3 秒；预检再次执行时可能覆盖同名文件；不进入正式转写或分段计数 |
| `chunk_*/audio.wav` | 系统默认扬声器 loopback 录音；配置为 16 kHz、单声道；低音量归一化会覆盖该 WAV |
| `chunk_*/transcript.json` | 该分段的后端输出。faster-whisper 写入 `audio` 绝对路径和 `segments`，其中时间已加全局分段偏移；FrameNotes 原文件预期为局部时间，加载进任务时才加偏移 |
| `note.md` | 每个已处理正式分段后重写的滚动笔记，静音提示可能覆盖之前的笔记正文；先前片段仍保留在内存中 |
| `refined_note.md` | 正常完成时，有转写片段才写入；使用规则式清理和总结，没有额外 LLM 调用；API 不直接返回此文件 |

faster-whisper 输出到分段 JSON 的 `index` 从该段的 1 开始；加入任务内存后统一改为跨段累计编号。不要直接把不同后端的分段 JSON 当成时间基准完全相同的文件拼接。需要完整且统一的累计片段时，在服务仍运行期间保存任务快照。

`note.md` 的“原始转写”只保留最后 80 个片段；时间线按每 8 个片段组成一条摘要，累计片段没有在 API 中裁剪。精炼时间线最多 12 条。笔记中的日期来自任务创建时间并转换为 `Asia/Shanghai`；它不表示主播开播时间。“已转写时长”取最后一条片段的结束时间，不等于任务墙钟耗时。

录音与 ASR 是依次执行的。一个分段录完后，系统先检查页面、分析音量、执行转写并写笔记，才开始下一个分段。这期间发生的直播声音没有被后台持续录入。此实现因此不能保证无间隙全程录制，`max_chunks × chunk_seconds` 也不能用作精确的墙钟结束定时器。

## ASR 分支和配置边界

每次转写按以下条件选择后端：如果 `settings.framenotes_root/scripts/transcribe-audio.ps1` 存在，并且 PATH 能找到名为 `powershell` 的可执行文件，就使用 FrameNotes；否则使用本地 `faster-whisper`。

FrameNotes 根目录仅通过环境变量 `REDBOOK_FRAMENOTES_ROOT` 配置，默认是项目根目录的同级 `FrameNotes` 文件夹。配置在模块导入时读取，修改环境变量后需重启服务。当前没有调用 `load_dotenv()`，因此仅把变量写进 `.env` 不会自动生效。

fallback 后端将 `auto` 设备转为 CPU，固定使用 `compute_type="int8"`、`vad_filter=True` 和 `beam_size=5`，模型在该任务首次非静音转写时创建并供同一任务后续分段复用。FrameNotes 返回非零退出码或产物不符合预期时直接使任务失败，不会再自动切换 fallback。

`runtime_dir`、`sample_rate`、`channels` 没有对应的请求字段，也没有在当前 `Settings` 中读取同名环境变量。`default_chunk_seconds` 虽存在于设置模型，但请求的实际默认值在 `CreateJobRequest` 中固定为 `60`。
