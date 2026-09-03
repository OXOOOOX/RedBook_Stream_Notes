# 构建过程：从直播转写 MVP 到可分发 skill

这份记录解释当前项目由哪些部分组成、此次包装做了什么、为什么这样设计，以及如何重建和验证。它依据 Git 基线、包装开始时已有的工作区改动、当前代码和本次执行过的检查编写，不补写没有证据的早期开发故事。

## 目标与交付形态

原项目已经是一个本地直播转写服务。此次工作的目标是让另一个使用者或 agent 拿到一个完整目录后，能够理解适用场景、配置环境、启动服务、处理任务、保留原文、整理笔记，并将不含用户运行数据的安装包发布到 GitHub。

最终保留两种互补入口：

- **独立应用**：Python/FastAPI 服务、内置网页和 HTTP API，可以不依赖 skill 宿主使用。
- **`redbook-live-notes` skill**：入口说明、agent 元数据、参考资料、命令脚本和完整应用源码。宿主负责理解用户意图与整理最终笔记，服务负责录音和转写。

仓库根目录同时作为 skill 根目录，避免再复制一份服务源码到另一个 skill 子项目。安装时需要保留完整目录，不能只复制 [SKILL.md](../SKILL.md)。ZIP 安装包和 Python wheel 用途不同：ZIP 包含 skill 工作流与参考资料；wheel 验证的是 Python 应用的构建能力，不能代替完整 skill 安装包。

直播采集需要本机桌面、可播放的页面和可用音频设备。只有已有文字转写需要整理时，可以直接离线工作，不需要启动服务或录音。这两个入口在当前 skill 中已明确分开。

## 可验证的版本分层

本次开始核对的 Git 基线是 `f4773ec`，提交标题为 `Add RedBook livestream transcription service`。基线只有一个可见的原始服务提交；不能据此重建作者逐日实现或调试的顺序。下表按可验证来源分层，不将工作区中的所有变化都归功于此次包装。

| 层次 | 可以确认的内容 | 证据与边界 |
| --- | --- | --- |
| 已提交的 MVP | FastAPI 任务接口与查看器、内存任务管理、Playwright 页面操作、loopback 分段录音、FrameNotes/faster-whisper 转写、滚动和规则式精炼笔记，以及原有测试 | 可用 `git show f4773ec:<文件路径>` 阅读；当前 `main.py`、`schemas.py`、`asr.py`、`recorder.py` 的核心能力已经存在于基线 |
| 包装前已有的未提交增强 | 更强的取消静音尝试、音频预检和低音量处理、FrameNotes 默认路径定位、笔记日期与一部分领域规则调整、相关笔记测试 | 包装开始时这些改动已经存在。此次保留，没有将其描述成包装阶段新写的采集功能 |
| 此次 skill 包装 | 根级 skill 入口、元数据、分层说明、最终笔记模板、CLI、白名单打包工具、打包与 CLI 测试、依赖声明和构建配置、GitHub Actions 验证工作流 | 可以从新增脚本、说明和相对于基线的差异复核 |
| 本次补充的项目记录 | 构建过程、验证边界和排障经验的可维护说明 | 记录代码与已执行结果；远程发布状态以对应提交、CI 和发布记录为准 |

包装前已有增强的具体范围如下：

- [browser.py](../src/redbook_stream_notes/browser.py)：取消静音尝试由 3 轮增至 5 轮；加入播放器悬停、图标点击失败后的坐标点击，以及播放器静音样式检查。
- [config.py](../src/redbook_stream_notes/config.py)：FrameNotes 默认位置从依赖当前工作目录的 `../FrameNotes` 改为根据模块路径计算项目根目录，再取其同级 `FrameNotes`。
- [jobs.py](../src/redbook_stream_notes/jobs.py)：增加最多 3 次、每次 3 秒的声音预检；静音峰值阈值由 `0.001` 调整为 `0.0002`；对非静音但较弱的分段做有限增益放大；笔记构建传入任务创建时间。
- [notes.py](../src/redbook_stream_notes/notes.py)：加入 `Asia/Shanghai` 日期格式化，扩展纠错词表，调整财经摘要的触发条件与回退提炼逻辑。已有的 `tests/test_notes.py` 增加日期和部分未提及主题的检查。

这些变化能从差异中确认，但它们不构成真实直播成功、跨平台音频可用或摘要准确率提高的实测证明。尤其是领域规则仍可能因为关键词共现而给出原文没有表达的结论。

## 架构与数据流

当前系统分成“用户意图与操作”“本地采集服务”“证据与笔记”“发布产物”四部分：

```text
用户提供直播分享文本 / 任务 ID / 已有转写
                    │
                    ▼
           SKILL.md 判断任务类型
                    │
        ┌───────────┴────────────────┐
        │                            │
   新直播或运行中任务              已有文字材料
        │                            │
   scripts/redbook.py                 │
   或 /viewer、HTTP API               │
        │                            │
        ▼                            │
   FastAPI → JobManager              │
        │                            │
   Chromium 打开页面                  │
        │                            │
   默认扬声器回录 → WAV               │
        │                            │
   静音检查 / 低音量放大              │
        │                            │
   FrameNotes 或 faster-whisper      │
        │                            │
   累计 segments + 滚动规则笔记        │
        │                            │
   API / SSE / 全量快照导出 ──────────┤
                                     ▼
                         保留原始材料，按原文核对
                                     │
                                     ▼
                              final_note.md

仓库中的入口、代码、说明、模板
                    │
          package_skill.py 白名单收集
                    │
      ZIP + MANIFEST.json + SHA-256
```

上图的采集链路按分段顺序执行。录音和 ASR 没有形成并行流水线；ASR 计算期间没有持续录音，因此图中的连接不能理解为直播内容被无间隙保存。

### 模块职责

| 文件 | 当前职责 | 设计上应保留的区分 |
| --- | --- | --- |
| [SKILL.md](../SKILL.md) | 判断新直播、已有任务、离线整理或排障；路由到对应参考资料 | 规定 agent 如何做事，不直接提供录音进程 |
| [agents/openai.yaml](../agents/openai.yaml) | 显示名称、简介与包含 skill 名称的默认提示词 | 是宿主展示元数据，不包含账号或浏览器配置 |
| [scripts/redbook.py](../scripts/redbook.py) | 环境检查、稳定启动位置、分享链接提取、API 客户端、导出 | 对现有服务的辅助层；部分保护只在 CLI 中生效 |
| [main.py](../src/redbook_stream_notes/main.py) | 7 个业务路由、内置查看器、SSE 完整快照事件 | HTTP 成功和任务处理成功是两件事 |
| [schemas.py](../src/redbook_stream_notes/schemas.py) | 创建参数、片段和任务快照模型 | 段长及段数受约束，模型/设备等字符串仍交由 ASR 后端解释 |
| [jobs.py](../src/redbook_stream_notes/jobs.py) | 创建任务、状态变化、录音与转写调度、收尾落盘 | 任务索引在内存；正常停止和异常失败的落盘结果可能不同 |
| [browser.py](../src/redbook_stream_notes/browser.py) | 启动独立 Chromium 上下文，尝试播放，检查页面结束信号 | 不复用现有 Chrome 登录态，不处理验证码或登录限制 |
| [recorder.py](../src/redbook_stream_notes/recorder.py) | 获取默认扬声器及 loopback 输入，录制固定长度 WAV | 录制系统输出混音，不能按标签页隔离声音 |
| [asr.py](../src/redbook_stream_notes/asr.py) | 选择后端、调用转写、读取或写入片段 JSON、补充分段偏移 | 两种后端的分段 JSON 时间基准不同，内存快照统一使用累计时间坐标 |
| [notes.py](../src/redbook_stream_notes/notes.py) | 关键词、截句、时间线、纠错和领域规则草稿 | 规则输出不是事实核查后的最终笔记 |
| [config.py](../src/redbook_stream_notes/config.py) | 运行目录、FrameNotes 位置、16 kHz 单声道等设置 | 不是自动加载任意环境变量的配置框架 |
| [scripts/package_skill.py](../scripts/package_skill.py) | 校验入口与链接、选择发布文件、构建和验证 ZIP | 分发应用所需文本/源码，排除现场数据和开发环境 |
| [最终笔记模板](../assets/final-note-template.md) | 来源、范围、要点、时间线、待核对内容、原始材料 | 允许按主题调整，不强迫非财经内容使用板块观察结构 |

### 一个直播任务如何运行

1. 客户端提交创建参数。API 校验后生成 12 位任务 ID、创建任务目录，并在当前进程保存任务对象；后台协程负责后续处理。
2. 服务创建转写器，再打开新的 Playwright Chromium 页面。默认是可见窗口，页面加载等待 `domcontentloaded`。需要登录或点击播放时，由用户在这个窗口完成。
3. 状态设为 `listening` 后进行声音预检。这里的 `listening` 包括预检、录音和识别，不能作为已经成功转写的凭证。
4. 正式循环先检查段数上限和页面结束状态，再录制一个完整分段。录完后再次检查页面状态、分析音频，并根据静音门槛决定是否执行 ASR。
5. ASR 返回的新片段加上累计分段偏移，加入内存列表并统一编号。服务重写滚动 `note.md`；静音段会改写为相应提示，但仍递增分段计数。
6. 正常结束时，有片段才写 `refined_note.md`。捕获到异常时将状态记为 `failed` 并保存错误文本；异常路径不保证已生成全部最终文件。最后尝试关闭浏览器资源。
7. 查看器通过 SSE 接收完整快照，约每 2 秒检查变化后更新；每个事件不是逐词转写。CLI 的 `export` 另存全量快照、完整可用转写和当前滚动笔记。
8. agent 依据 [笔记质量规范](note-quality.md) 对原始片段进行整理，写入新的 `final_note.md`，保留数字、否定、条件、来源和不确定词。

原生 API 的完整定义、字段和状态边界见 [API 参考](api.md)。

### 后端与输出选择

如果 FrameNotes 脚本存在且 PATH 中有 `powershell`，服务优先调用外部脚本；否则使用 faster-whisper。这里的“否则”只发生在选择阶段：已经选中的 FrameNotes 执行失败，不会自动再试另一个后端。faster-whisper 中 `device=auto` 实际映射为 CPU，计算类型固定为 `int8`。

正式音频位于 `runtime/jobs/<job_id>/chunk_0001/audio.wav` 一类目录；转写成功后有对应 JSON。CLI 启动会固定默认运行目录到 skill 根目录，并允许 `serve --runtime-dir` 指定独立数据位置。裸 Uvicorn 启动仍沿用应用原本相对当前目录的行为。

输出分层是此次整理中的关键约定：

- **原始证据**：WAV、分段 JSON、累计 `snapshot.json`。不得为迎合摘要而改写。
- **自动草稿**：`note.md` 与 `refined_note.md`。前者原始转写展示有条数限制，后者含领域规则。
- **最终交付**：agent 根据完整可用片段另行整理的 `final_note.md`，明确本次可用范围与缺失。

导出会保留所有快照片段，不受查看器最近 250 条或滚动笔记最后 80 条的展示限制。它不复制音频，也不生成最终笔记。CLI 返回的 `partial` 仅按任务是否仍处于活动状态计算；`failed` 也属于终态，因此 `partial: false` 不能解释为整场内容完整。

## 此次包装如何落地

### 1. 先确认现有能力和未提交改动

包装首先依据代码与 Git 差异确认能力，而不是按旧 README 中的描述推断。这样识别出了原有查看器、近期任务列表、SSE 和精炼文件，同时也识别出串行录音、内存任务、启发式下播、停止终态改写等限制。

已有业务源码增强予以保留；包装没有借机重写录音调度或财经规则。文档因此明确区分“已具备”“辅助脚本缓解”“尚未解决”，避免把加上说明文档当成修复实现。

### 2. 建立可按任务读取的 skill 文档

主入口保持操作顺序和关键边界，详尽内容拆到参考资料：

- [setup.md](setup.md)：环境、安装、后台进程、输出目录和 FrameNotes。
- [workflows.md](workflows.md)：CLI 与典型任务，包括已有任务和历史材料。
- [api.md](api.md)：真实路由、模式、SSE、停止、后端和落盘约定。
- [note-quality.md](note-quality.md)：基于原文的清洗与核对规则。
- [troubleshooting.md](troubleshooting.md)：按现象排查，区分已实现行为与能力限制。
- [publishing.md](publishing.md)：白名单构建、验证和 GitHub 发布步骤。

文档链接使用包内相对路径，安装到新位置仍可浏览。没有把本机已有音频、任务链接、Cookie、个人目录或现场笔记作为示例复制进 skill。

### 3. 增加轻量 CLI，把重复操作做成确定步骤

[redbook.py](../scripts/redbook.py) 的 HTTP 客户端、参数解析和导出使用 Python 标准库，不要求额外安装专门客户端。启动服务或检查应用依赖时才导入相应库。关键行为包括：

- `doctor` 检查解释器、依赖模块、时区和 Chromium 可执行文件；`--audio` 仅额外枚举设备，不录音。
- `serve` 固定本机地址、单 worker、禁用重载，并根据脚本位置定位源码和默认数据目录，减少从不同工作目录启动时的差异。
- `create` 离线提取一个明确的小红书链接，保留参数，拒绝歧义目标和伪装域名；创建前查看近期任务，避免常见的重复录音。
- `stop` 先读状态，终态或已经停止中的任务只返回快照，避免触发原生 API 把终态重新写成 `stopping` 的行为。
- `export` 只创建全新目录，保留完整快照和所有可用片段，拒绝覆盖用户已有导出。

这些辅助行为没有改写服务的底层约束。查看器或直接调用 API 可以绕过 CLI 检查；近期任务查询最多 20 条，创建前检查也不是原子互斥锁。停止保护是客户端规避，不能说原生停止接口已经变成幂等操作。

### 4. 让依赖声明支持安装和构建

[pyproject.toml](../pyproject.toml) 增加 setuptools 构建后端、`src` 包发现、README 元数据和仓库地址；为已有 Pydantic 2 用法标注最低版本，同时声明兼容的 FastAPI 最低版本。加入 `tzdata` 以支持干净环境的 `Asia/Shanghai` 日期转换，开发依赖加入测试客户端使用的 `httpx`。

[requirements.txt](../requirements.txt) 作为兼容入口引用项目的开发依赖声明，避免同时维护两套依赖列表。依赖安装命令从项目根目录执行。

项目仍使用 `0.1.0` 版本，依赖没有锁定到完整、固定的传递依赖集合。因此这里的“可复现”是提供明确可重跑的流程与校验，不宣称任意日期、操作系统和依赖解析结果都得到完全相同的运行环境。

### 5. 采用白名单安装包，而非压缩整个工作目录

[package_skill.py](../scripts/package_skill.py) 只收集必需根文件、`scripts` 的 Python 脚本、`references` 的 Markdown、`assets` 的指定文本类型，以及 `src/redbook_stream_notes` 的 Python 源码；存在 LICENSE 时一并纳入。测试与 GitHub Actions 配置留在源码仓库，不进入 skill 安装包。

校验阶段检查入口元数据、相对链接、文本编码、Python 语法、JSON 内容和未完成的脚手架标记，并拒绝目录链接及不符合规则的文件路径。runtime、导出、录音、浏览器资料、虚拟环境、模型、缓存和常见凭据文件名不属于分发范围。

ZIP 使用单一顶层目录 `redbook-live-notes/`，文件顺序和 ZIP 元数据固定，附带文件大小及 SHA-256 清单。构建后会重新验证文件和清单，再发布到输出路径。默认不覆盖同名包；明确 `--force` 时只替换该 ZIP。临时文件清理针对工具自己创建的一个明确路径，不进行批量目录删除。

同样输入与构建环境下的重复构建一致性有测试覆盖。清单用于检测意外损坏和内容不一致，不是数字签名。白名单也不是全文秘密扫描器：有人手工把敏感信息写进允许分发的源码或 Markdown，仍需要审阅发现。

### 6. 为新增分发行为设置离线验证

新增 `tests/test_skill_cli.py` 覆盖分享文本、域名与歧义检查、停止保护、已有活动任务和完整导出等行为。`tests/test_skill_package.py` 覆盖包范围、路径、元数据、链接、清单、重复构建、覆盖保护和解压后自包含验证。测试使用合成数据与临时目录，不依赖真实直播。

`.github/workflows/validate.yml` 配置了 Ubuntu 和 Windows、Python 3.11 的离线测试与打包，并上传 CI 构建产物。工作流定义本身不代表远程执行成功；具体运行结果应查看对应提交的 CI 记录。当前流程不会自动发布 PyPI、创建公开 Release 或推送提交。

## 本次已经完成的验证

下面记录包装阶段已经执行过的结果；后续代码或文档更改应重新运行相应检查。最新发布对应的详细记录以[验证记录](validation.md)为准。

| 检查 | 已观察结果 | 能证明什么 |
| --- | --- | --- |
| 包装开始前的测试 | 8 项通过 | 原有离线 API、查看器和笔记测试可运行 |
| 包装后的测试集 | 51 项通过：8 项原有、20 项 CLI、23 项打包测试 | 对应离线断言通过，不代表真实直播已测试 |
| skill 格式校验 | 宿主附带 `quick_validate.py` 对根目录校验通过 | 该校验器检查的 skill 格式成立 |
| 打包源码与 ZIP 验证 | `--check` 与 `--verify` 通过 | 当前允许分发文件、包内链接及内容清单符合工具规则 |
| 静态 doctor | 依赖、时区与 Chromium 检查通过；未枚举音频设备 | 检查到所需静态环境，不证明播放或回录可用 |
| Python wheel 构建 | `pip wheel --no-deps --no-build-isolation` 成功 | 应用可以在当时环境构建 wheel；未进行完整全新依赖安装 |
| 安装包搬迁验证 | ZIP 解压到独立临时目录，`--help` 和 `--check` 可运行 | 帮助与包内引用不依赖原仓库位置 |
| 解压包 HTTP 冒烟 | 使用独立空运行目录启动包内服务；health、空 recent、viewer 中 EventSource、OpenAPI 和 CLI health 检查通过 | 打包后的应用可导入并响应这些本地 HTTP 路径 |
| 离线笔记任务前向测试 | 使用根级 skill，保留合成快照并生成最终笔记，核对关键事实通过 | agent 按 skill 可以处理已有文字材料，无须触发监听 |

HTTP 冒烟没有创建直播任务，结束时只停止该次测试自行启动的无任务进程。没有读取原有任务目录作为验证数据。

### 离线笔记前向测试的具体价值

测试请求是“把已有直播转写整理成笔记，保留数字和不确定词，不重新监听”。输入包含任务失败信息、两条转写，以及刻意容易诱发规则误判的内容：

- 明确说“不讨论资金流，也不判断压力位”，实际主题是直播间运营。
- 今天 300 名访客、昨天 200 名访客，要求分开。
- 未来七天先测试标题。
- 百分之三是目标转化率，原文明确不是已经达到。
- 工具听起来叫“星流宝”，名字仍需核对。

执行在 `tempfile.mkdtemp` 创建的独立目录完成，只读取 skill 入口、笔记规范与模板，不访问浏览器、音频、网络或已有运行数据。产出 `snapshot.json` 与 `final_note.md`，验证原始快照对象未变、两条转写均保留；最终笔记保留数字、否定、不确定词和任务失败/缺失范围，未生成财经判断。

这次测试暴露了两处入口歧义：旧描述将桌面与音频权限写成通用要求，编号主流程也可能被误读为离线整理必须先运行服务。当前入口已将桌面/音频要求限定为直播采集，明确已有快照或粘贴文字可跳过环境、服务与录音步骤，并把编号流程改名为“新直播与运行中任务流程”。这属于经前向任务检验后做出的实际文档修正。

## 从源码重建与复核

以下命令在完整源码仓库根目录执行。若手上只有安装 ZIP，包内没有 `tests` 和 Git 历史，跳过 Git 差异与 pytest 步骤；包内仍可运行帮助、源码校验和应用。

### 检查当前源码与基线

```powershell
git status --short
git log -5 --oneline
git diff --stat f4773ec
git diff --check
```

未跟踪的新文件不会出现在普通 `git diff` 中，应同时检查 `git status`。打包读取当前工作区，GitHub 提交读取暂存的内容，二者不能在未经比较时视为同一版本。提交与发布操作见 [发布指南](publishing.md)。

### 建立环境并运行离线验证

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python scripts/redbook.py --help
.\.venv\Scripts\python scripts/package_skill.py --check
```

pytest 和打包校验不需要直播页面、Chromium 安装、音频设备或 ASR 模型推理。安装 Python 依赖本身可能需要网络。macOS/Linux 的解释器位置对应 `.venv/bin/python`，实际回录能力仍需另外验证。

### 构建应用和 skill 安装包

```powershell
.\.venv\Scripts\python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist/wheels .
.\.venv\Scripts\python scripts/package_skill.py --output dist/redbook-live-notes-review.zip
.\.venv\Scripts\python scripts/package_skill.py --verify dist/redbook-live-notes-review.zip
Get-FileHash -Algorithm SHA256 -LiteralPath 'dist/redbook-live-notes-review.zip'
```

选择尚不存在的 ZIP 输出路径。需要再次构建时可使用新的文件名；明确要替换一个已有 ZIP 时再传 `--force`。不要为重建而批量删除历史录音、导出目录或整个工作区。

### 在新目录检查安装包自包含性

先把该 ZIP 解压到一个新建的独立目录，再从其中的 `redbook-live-notes` 根目录执行：

```powershell
python scripts/redbook.py --help
python scripts/package_skill.py --check
```

启动服务需要该目录的依赖可用。使用已明确安装依赖的解释器，给测试服务单独的空数据目录，并选择空闲端口：

```powershell
python scripts/redbook.py serve --port 8010 --runtime-dir 'C:\work\redbook-smoke-jobs'
```

另一个终端只执行无任务检查：

```powershell
python scripts/redbook.py --api http://127.0.0.1:8010 health
python scripts/redbook.py --api http://127.0.0.1:8010 recent
```

这个流程不创建录音任务。若要进一步验证真实直播，先按 [安装指南](setup.md) 安装 Chromium、执行设备检查，再使用用户给定的可播放链接做明确标记的短测试。短测试不能替代用户要求的完整监听。

## 尚未由此次构建证明或解决的事项

此次完成了分发、离线使用、客户端保护和文档准确性的工作；没有改变以下底层边界：

- 没有实测本次环境中的真实直播播放、loopback 回录或 ASR 模型推理，也没有验证跨平台真实录音成功。
- 没有把串行采集改为无间隙录制，没有增加多路音频隔离、说话人分离或精确墙钟时间轴。
- 没有实现账号持久化、验证码处理、任务数据库、重启恢复、服务级并发锁或身份认证。
- 没有修复原生停止接口对终态的改写；CLI 只是避免执行该路径。
- 没有把领域规则摘要升级为通用的事实核查或语义理解引擎；最终笔记仍必须对照完整可用原文。
- 没有因存在 ZIP 或 wheel 就自动授予开源许可证，也不能据此推断 GitHub Release 已发布。

这些事项分别需要架构修改、具体环境验证或维护者决策。维护时应继续把“新增代码”“测试通过”“真实场景验证”和“已经发布”分别记录，避免只凭某一层成功推断整条链路完成。
