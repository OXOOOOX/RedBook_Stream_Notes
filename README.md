# RedBook Stream Notes · 小红书直播笔记 Skill

[![Validate skill](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/workflows/validate.yml/badge.svg)](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/workflows/validate.yml)

把小红书直播分享链接变成本地音频分段、带时间戳的转写，以及可对照原文核对的中文笔记。

本仓库同时是可安装的 **`redbook-live-notes` skill** 和独立的 Python/FastAPI 应用。完整代码随 skill 分发，没有硬编码的个人目录，不需要另一个 RedBook 项目，也不需要 OpenAI API Key。适合有桌面和音频设备的本机。

第一次了解项目，可依次读[构建过程](references/build-process.md)、[工程排雷](references/engineering-lessons.md)和[验证记录](references/validation.md)。安装包见 [GitHub Releases](https://github.com/OXOOOOX/RedBook_Stream_Notes/releases)；源码、安装包和文档的范围见[发布指南](references/publishing.md)。

换机器或在新的 agent 会话继续开发时，从[项目交接](references/handoff.md)开始：包含已发布基线、重要决策、未解决事项、模拟验收材料和可复制的接手提示词。

```text
分享文本 / 直播链接
        ↓
Playwright 打开直播页面 → 用户完成必要的登录/播放
        ↓
默认扬声器 loopback → WAV 分段 → 本地 ASR
        ↓
任务 API / 实时查看器 / 原始转写
        ↓
导出全部可用片段 → agent 对照原文整理最终笔记
```

## 功能与边界

- 提取小红书分享链接，打开网页版直播，尝试播放和取消静音。
- 分段回录默认扬声器，检查静音，对较低音量做归一化。
- 优先使用本地 FrameNotes 脚本；未满足选择条件时使用 faster-whisper。
- 通过 `/viewer` 的 SSE 更新查看状态、原文和滚动笔记。
- 统一 CLI 支持环境检查、服务启动、任务创建/查询/停止和全量转写导出。
- skill 指导 agent 去除口头禅、核对错词、保留数字与条件，形成基于原文的笔记。
- 提供排除运行数据的 ZIP 打包脚本、内容清单和离线验证。

当前核心仍是 MVP。**录音与识别串行，识别期间存在录音间隔**；时间戳按累计录音计算，不等于直播真实时钟。系统其他应用的声音也会被录入，同一台机器应只运行一个直播音频任务。

服务不处理登录、验证码、App 限制，不复用现有 Chrome 登录态。结束检测可能误判，服务重启后不能按旧 job ID 恢复。服务没有身份验证，应保持本机使用。

`refined_note.md` 是含财经规则的待核对草稿，可能生成原文未明确支持的叙述。skill 要求从完整原始转写另行整理 `final_note.md`。详见[实际限制与排障](references/troubleshooting.md)。

## 快速开始

需要 Python 3.10+。Windows 为主要使用环境；macOS/Linux 需验证系统音频路由，目前没有跨平台回录成功保证。

```powershell
git clone https://github.com/OXOOOOX/RedBook_Stream_Notes.git
Set-Location RedBook_Stream_Notes
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python scripts/redbook.py doctor
.\.venv\Scripts\python scripts/redbook.py doctor --audio
.\.venv\Scripts\python scripts/redbook.py serve
```

打开[实时查看器](http://127.0.0.1:8000/viewer)，粘贴实际链接并开始监听。在新开的直播浏览器窗口完成登录/播放。也可在第二个终端使用 CLI：

```powershell
.\.venv\Scripts\python scripts/redbook.py create --url 'https://xhslink.com/example' --language zh
.\.venv\Scripts\python scripts/redbook.py status JOB_ID --compact
.\.venv\Scripts\python scripts/redbook.py stop JOB_ID
.\.venv\Scripts\python scripts/redbook.py status JOB_ID --compact
.\.venv\Scripts\python scripts/redbook.py export JOB_ID --output 'exports/session-01'
```

替换示例 URL 和返回的 JOB_ID。stop 返回 stopping 时需等至 stopped/failed，再导出和关闭服务。导出目录必须不存在。首次识别可能下载/加载模型；doctor 不录音、不下载模型，只有实际首段正确转写才证明音频链路可用。

## 安装为 skill

把完整仓库或发布 ZIP 中的 `redbook-live-notes/` 放入宿主发现目录，不能只复制 SKILL.md。当前官方 Codex 文档列出用户级 `~/.agents/skills/`、项目级 `.agents/skills/`；部分本地安装器使用 `~/.codex/skills/` 或 `$CODEX_HOME/skills/`，以实际宿主为准，避免同名重复安装。参见 [OpenAI skill 文档](https://learn.chatgpt.com/docs/build-skills)与[详细安装指南](references/setup.md)。

也可对支持 skill-installer 的环境说：

```text
使用 $skill-installer 从 OXOOOOX/RedBook_Stream_Notes 仓库根路径 .
安装 skill，命名为 redbook-live-notes。
```

安装后可这样调用：

```text
使用 $redbook-live-notes 监听这个小红书直播：[粘贴分享文本]。
保留原始转写，结束后去掉口头禅，整理要点、时间线和待核对词。
```

```text
使用 $redbook-live-notes 查看任务 abc123def456 的进度，
结束后导出全部可用转写，并根据原文整理笔记。
```

```text
使用 $redbook-live-notes 整理我指定目录内已有的 transcript.json，
保留不确定术语和缺失范围说明。
```

## 完整文档

| 文件 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | agent 入口、触发范围、工作流和参考路由 |
| [agents/openai.yaml](agents/openai.yaml) | 显示名称、简介、默认提示词 |
| [统一 CLI](scripts/redbook.py) | 环境检查、服务与任务操作 |
| [打包工具](scripts/package_skill.py) | 白名单 ZIP、清单与验证 |
| [环境安装](references/setup.md) | 依赖、发现目录、后台运行、FrameNotes |
| [命令与工作流](references/workflows.md) | CLI 参数、已有任务、历史转写、导出 |
| [API 参考](references/api.md) | 请求/响应、SSE、状态和磁盘产物 |
| [笔记质量](references/note-quality.md) | 原文证据、纠错和交付核对 |
| [故障排查](references/troubleshooting.md) | 播放、回录、模型、结束、恢复与输出 |
| [构建过程与架构](references/build-process.md) | 项目目标、模块关系、基线、现有增强与 skill 封装 |
| [工程排雷复盘](references/engineering-lessons.md) | 根因、修复/规避、未解决限制与后续优先级 |
| [验证记录](references/validation.md) | 已执行检查、结果、范围与真实设备验证边界 |
| [项目交接](references/handoff.md) | 发布基线、决策、下一步、重跑样例与新聊天接手入口 |
| [v0.1.0 发布说明](references/release-v0.1.0.md) | 本次交付内容、安装方法和已知限制 |
| [发布指南](references/publishing.md) | 本地验证、打包、GitHub 提交与 Release |
| [笔记模板](assets/final-note-template.md) | 可按主题调整的最终笔记结构 |

## API 与产物

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/viewer` | 实时查看器 |
| GET | `/jobs/recent` | 当前服务最近 20 个任务 |
| POST | `/jobs` | 创建任务 |
| GET | `/jobs/{job_id}` | 状态、全部现有片段和滚动笔记 |
| GET | `/jobs/{job_id}/events` | SSE 全量快照更新 |
| POST | `/jobs/{job_id}/stop` | 请求停止 |

接口说明见 [Swagger UI](http://127.0.0.1:8000/docs)。没有历史任务数据库、文件下载 API 或自动恢复接口。

CLI serve 默认写入 skill 根目录下 `runtime/jobs/JOB_ID/`，可通过 `--runtime-dir PATH` 改变。每个任务包含 probe 预检、chunk_0001 等分段目录中的 audio.wav 和成功转写的 transcript.json、滚动 note.md，以及正常结束且有转写时生成的 refined_note.md。

export 另行输出 `snapshot.json`、`transcript.md`、`note.md`，不复制音频。agent 根据原文另行整理 final_note.md。runtime、导出笔记、链接参数和录音均不应上传为 skill。历史文件需要批量清理时请手动处理。

## 开发与打包

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python scripts/package_skill.py --check
.\.venv\Scripts\python scripts/package_skill.py
```

默认输出 `dist/redbook-live-notes.zip`，包含单一顶层文件夹及所需源码，排除 runtime、环境、录音、Git 和缓存。同名 ZIP 存在时拒绝覆盖；用新的 `--output` 或显式 `--force` 替换单个产物。GitHub Actions 工作流执行离线测试和打包，不能代替真实页面/声卡/ASR 测试。

## 授权状态

仓库尚未指定开源许可证。本次封装不替作者决定授权条款；正式作为开源项目发布前，请维护者选择并加入 LICENSE。第三方依赖遵循各自许可证。
