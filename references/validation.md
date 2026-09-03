# 验证记录与适用范围

本记录对应 2026-09-03 的 skill 封装与发布整理。它记录实际做过的检查，不将代码中存在某项功能等同于真实直播已经验证。

## 本地验证

| 检查 | 实际结果 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 封装前原有 pytest | 8 passed | 当时 API、viewer、笔记用例通过 | 真实浏览器/录音/ASR 链路 |
| 封装后 pytest | 51 passed：原有 8、CLI 20、打包 23 | 命令行为、完整导出、防覆盖、分发内容及损坏检测等离线行为 | 多平台硬件支持、真实平台页面或长期录制 |
| skill-creator quick_validate | 通过 | 入口 frontmatter、命名等基本格式 | agent 所有场景下的判断质量 |
| package_skill --check | 通过 | 允许的文件、元数据、相对文档链接、文本和脚本语法 | 引用网页未来仍可访问 |
| package_skill --verify | 通过 | ZIP 内容与内置散列清单一致，结构满足分发要求 | 来源真实性；SHA256 清单不是数字签名 |
| doctor | 通过所列静态必要条件 | 当前解释器有依赖、Asia/Shanghai 和 Chromium 文件 | 模型推理、真实回录、直播播放成功 |
| Python wheel 构建 | 成功，版本 0.1.0 | 当前环境中构建元数据和包发现可工作 | 本地已完成全新环境安装；wheel 也不是完整 skill ZIP |
| 独立目录包启动 | 通过 | ZIP 解压后可从另一当前目录调用脚本、启动服务及设定独立数据目录 | 真实直播的登录或播放能力 |
| 离线笔记行为验证 | 通过一次受限场景 | 对给定转写保留否定、数值、目标/事实区别和待核对词 | 全部类型的直播摘要质量 |

本地环境为 Windows、Python 3.13.5，复用了机器上已有依赖。没有为了本次检查下载模型或进行真实直播录音；不声称本机完成了“全新环境端到端安装”。

## 独立目录检查如何做

把白名单 ZIP 解压到新临时目录，从原仓库以外的当前目录执行包内脚本。用单独端口启动 `serve`，为它指定一个新的空 job 目录。实际检查了：

1. 包内 `package_skill.py --check` 与 `redbook.py --help` 成功。
2. `/health` 返回 `{"status":"ok"}`，CLI health 能得到同样结果。
3. `/jobs/recent` 是空数组，没有创建录音任务。
4. `/viewer` 能返回包含 EventSource 的 HTML。
5. `/openapi.json` 包含任务停止等预期路由。
6. 指定的数据目录存在且没有任务文件。

检查结束仅终止了本次启动的空服务进程，未操作用户其他进程。该检查验证分发包的路径自包含性，不是浏览器渲染或音频集成测试。

## 离线整理行为验证

使用独立目录中的模拟失败任务，提供两条转写：第一条明确“不讨论资金流，也不判断压力位”，并区分今天 300 名与昨天 200 名访客；第二条提出未来七天测试标题，3% 是目标而不是已达成值，并保留听写未确认的工具名。

agent 按 skill 输出 `final_note.md`，保留原始 snapshot.json，未启动服务或录音。检查了原始快照内容一致、否定没有消失、数值完整、目标没有变成事实、工具名仍待核对，并标注 failed 与部分转写范围。

此次验证发现入口对本地桌面/音频条件的表述可能误导离线整理；已把要求限定到直播回录，并明确已有文字材料可跳过环境、服务和录音流程。仅验证了一次代表性场景，不等于通用摘要基准成绩。

## GitHub 持续集成

仓库工作流在 Ubuntu 和 Windows runner 上用 Python 3.11 安装 `.[dev]`、运行 pytest、检查文档/skill 并构建 ZIP。不安装 Chromium 或下载 ASR 模型，不启动音频回录。源码在干净 runner 中安装成功的证据应以对应提交的运行结果为准。

可查看 [Validate skill 运行记录](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/workflows/validate.yml)。README 徽章显示工作流状态；本文不预先声称未来提交或尚未结束的运行成功。

2026-09-03 已完成首次完整项目的远程验证：提交 `92cb1e50489fe405e688c153a6602f36daede9a0` 的 [CI 运行 33728654353](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/runs/33728654353) 中，`validate (ubuntu-latest)` 与 `validate (windows-latest)` 均为 success。两端均完成安装、离线测试、skill/文档检查、ZIP 构建和构建产物上传。这是具体提交的证据；后续发布仍检查最终目标提交的结果。

工作流最初通过已授权 GitHub App 单独上传时，远程尚无完整 skill 代码，该中间提交产生过一次失败运行；完整代码合并后的上述运行通过。这个失败不作为最终版本的验证结果，也不从记录中隐去。相关权限问题和同步过程已写入[工程排雷](engineering-lessons.md)。

v0.1.0 最终发布提交为 `9376ed220502e7e5950ef0a6428665a44ab9ffb8`。其 [main 检查 33728862251](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/runs/33728862251) 和 [v0.1.0 标签检查 33729004469](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/runs/33729004469) 的 Windows/Ubuntu 作业均通过。发布附件已下载回本地并通过 SHA256 和内置清单校验；版本、大小与散列保存在[项目交接](handoff.md)。

## v0.1.1 交接资料更新验证

2026-09-03 为完整交接包追加检查：

- 全量 pytest 为 **52 passed**，其中打包测试为 24 项；新增用例确认可选的 AGENTS.md 保留原始中文 UTF-8/CRLF 字节、散列和解压后的相对文档链接。
- `package_skill.py --check` 和 skill-creator 基础格式校验通过。
- pyproject、模块和 FastAPI OpenAPI 中的版本均为 `0.1.1`。
- 从 GitHub 下载实际发布的 v0.1.0 ZIP，使用新版校验器验证成功，27 个文件与旧清单一致。

最终提交的 Windows/Ubuntu CI、v0.1.1 附件下载回验及实际 SHA256 作为发布门槛；对应结果附在 [v0.1.1 Release](https://github.com/OXOOOOX/RedBook_Stream_Notes/releases/tag/v0.1.1) 中，避免把尚未产生的提交散列写入待打包文档。本节没有新增真实设备或模型推理验证。

## 真实设备验收仍需另做

在用户实际环境中，按[安装指南](setup.md)先检查设备，再用目标直播进行短时录制：确认播放器可听，回录文件包含目标语音，第一段识别正确，停止后可导出。中文可明确传 `--language zh`，测试用 `--chunk-seconds 15 --max-chunks 1` 限定范围。

即使短测试成功，也需要单独评估长时间稳定性、录音间隔、页面误判结束和 ASR 质量。具体风险及处理分层见[工程排雷](engineering-lessons.md)与[故障排查](troubleshooting.md)。
