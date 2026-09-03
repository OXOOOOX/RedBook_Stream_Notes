# CLI 与典型任务

统一入口是 `scripts/redbook.py`。客户端操作（health/recent/create/status/stop/export）只需要 Python 标准库；服务端和 doctor 依赖已安装环境。以下命令在 skill 根目录执行，`python` 指已安装项目的解释器。

## 命令表

| 命令 | 用途 | 主要参数 |
| --- | --- | --- |
| `doctor` | 检查依赖、时区、Chromium | `--audio` 额外查回录设备 |
| `serve` | 前台运行本地单 worker 服务 | `--port 8000`、`--runtime-dir PATH` |
| `health` | 请求 `/health` | 全局 `--api` |
| `recent` | 当前进程最近 20 个任务的精简状态 | 全局 `--api` |
| `create` | 解析链接并开始监听 | `--url` 必填，其余见下表 |
| `status JOB_ID` | 获取完整快照 | `--compact` 隐去长笔记和原文 |
| `stop JOB_ID` | 先读状态，再请求停止 | 终态或 stopping 时不重复 POST |
| `export JOB_ID` | 导出现有全部片段、快照和滚动笔记 | `--output` 必填且目录不得存在 |

全局参数必须位于命令前：`python scripts/redbook.py --api http://127.0.0.1:8010 recent`。`--api` 仅影响客户端请求，`serve` 的端口通过 `--port` 设置。

| create 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--url` | 无 | 一个小红书链接或含一个链接的分享文本；多个不同目标会报错 |
| `--chunk-seconds` | 60 | 每段录音秒数，15–600 |
| `--language` | auto | ASR 语言，中文明确时可传 zh |
| `--model` | small | 传给所选 ASR 后端的模型名称或支持的模型路径 |
| `--device` | auto | 传给后端；faster-whisper 的 auto 实际为 CPU |
| `--max-chunks` | 不限 | 正整数，包含静音分段；达到后自动停止 |
| `--headless` | 关闭 | 隐藏直播浏览器；首次运行不建议，登录或播放可能受阻 |

CLI 只接受 `xiaohongshu.com`、`xhslink.com` 及其子域名，不解析其他网页。它在创建前检查最近任务以减少误开多个录音，但检查与创建并非原子操作，API 和 viewer 也没有相同互斥保证。避免并发客户端创建任务。

## 开始监听并交付

```powershell
python scripts/redbook.py health
python scripts/redbook.py recent
python scripts/redbook.py create --url 'https://xhslink.com/example' --language zh --model small
python scripts/redbook.py status JOB_ID --compact
```

替换示例链接与返回的 job ID。在 Playwright 直播窗口完成登录/点击播放；不要误把 viewer 当作直播源。确认第一段原文非空且确属目标直播。持续查看可打开 `/viewer` 填入 job ID，或间隔查询 status。

默认 60 秒一段，首段要等待页面启动、预检、录制、模型加载及 ASR；不会打开页面后立即出现文字。SSE 每约 2 秒检查状态变化，不能缩短实际录音/识别耗时。

用户要求结束时：

```powershell
python scripts/redbook.py stop JOB_ID
python scripts/redbook.py status JOB_ID --compact
python scripts/redbook.py export JOB_ID --output 'exports/session-01'
```

stop 返回 stopping 时继续等待，不重复请求。达到终态后导出。若在进行中导出，脚本返回 `partial: true`，文件代表当时快照，后续不会自动刷新；用新目录再次导出。

`partial` 只区分导出时是否仍在活动状态；failed 也会返回 `partial: false`，这不代表完整录到了直播。判断完整性还需查看 status、error、实际 segments 和缺失范围，失败任务的已有内容应按局部材料交付。

## 已有任务

优先沿用用户给出的 job ID；只有用户未给 ID 且 recent 中存在一个明确目标时才据此选择。多个候选时不要仅按“最新”停止或导出别人的任务。health 成功但旧 ID 404 可能是服务重启，API 没有恢复命令。

## 已有磁盘文件

读用户指定 job 目录的 `chunk_*/transcript.json`，保持分段顺序，不依赖滚动 note 中最近 80 条原文。不要把 `probe` 预检音频当成正式转写音频。

两种后端的 JSON 时间基准不同：faster-whisper 保存的 `start/end` 已包含累计录音偏移；FrameNotes 的原始 JSON 按片段相对时间保存，服务加载时才添加偏移。确定生成后端、chunk_seconds 与块序号后再归一化，不能对所有 JSON 一概二次加偏移。缺少来源信息时保留分段标识并标注时间未归一化。

API 导出的 `snapshot.json` 中 segments 已统一偏移和全局编号，服务仍在时优先导出。它也是失败任务中已经成功转写部分的证据来源。

## 预期交付

| 文件 | 来源 | 用途 |
| --- | --- | --- |
| `snapshot.json` | CLI 从 API 导出 | 当前全部 segments、状态、原始链接与元数据 |
| `transcript.md` | CLI 从 snapshot 生成 | 全部可用原文与累计录音时间戳 |
| `note.md` | 服务滚动草稿 | 快速浏览；可能被静音提示覆盖 |
| `refined_note.md` | 正常结束且有转写时服务生成 | 规则整理草稿，仅存 job 目录，不由 export 下载 |
| `final_note.md` | agent 根据原文整理 | 面向用户的、经过核对的笔记 |

`export` 不复制音频或生成 Word/PDF。用户另需文档格式时用宿主可用的文档能力从 final_note 转换，并验证版面；本 skill 不预设那些工具必定存在。
