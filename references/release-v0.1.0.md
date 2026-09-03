# v0.1.0 · 小红书直播笔记 Skill（MVP 预发布）

将 RedBook Stream Notes 整理成可安装的 `redbook-live-notes` skill，随包提供本地 Python 服务、统一命令入口和详细工程文档。

## 本次内容

- 完整 skill 入口、显示元数据，以及安装、API、操作流程、笔记质量、排障和发布说明。
- 构建过程、架构/模块说明、工程排雷、验证结果与未解决问题的长期记录。
- CLI 支持环境检查、稳定路径启动、任务创建/状态/停止、全量已有转写导出。
- 打包工具通过白名单排除运行数据，生成内容清单并支持 ZIP 完整性验证和防覆盖。
- 补齐 Python 构建配置、时区和测试依赖；加入 Ubuntu/Windows 的 GitHub Actions 工作流。
- 纳入此前工作区已有的播放器取消静音、音频预检/低音量处理、捕获日期和规则笔记改进。原始核心仍为 MVP，未将这些改进描述为连续录音架构重写。

## 安装

下载 `redbook-live-notes.zip`，将其中同名文件夹完整解压到宿主可发现的 skill 目录。在该目录按 README 创建虚拟环境，安装项目与 Playwright Chromium。通过 `$redbook-live-notes` 调用，也可独立启动 Python 服务。

源码、完整教程和文档入口见 [项目主页](https://github.com/OXOOOOX/RedBook_Stream_Notes)。附件 `.zip.sha256` 提供 ZIP 散列，可用 `Get-FileHash` 或 `sha256sum` 比对；包内还可以执行 `python scripts/package_skill.py --check`。

## 验证范围

本地 51 项离线测试通过；skill/链接/ZIP 校验、Python wheel 构建、独立目录解压启动和一次离线笔记行为验证通过。完整项目已经通过一次 Ubuntu/Windows 的远程 CI，具体提交证据保存在仓库的验证记录中；最终版本状态见 [工作流运行记录](https://github.com/OXOOOOX/RedBook_Stream_Notes/actions/workflows/validate.yml)。没有在本次发布验证中录制真实直播或执行模型推理。

## 已知限制

- 录音与 ASR 串行，识别期间有录音间隔；时间戳不是直播真实时钟。
- 系统扬声器回录可能混入其他应用声音，应保持单个直播音频任务。
- 不绕过登录、验证码、App 或平台播放限制；浏览器会话不复用用户现有登录态。
- 任务索引仅在内存，重启不能恢复旧 job ID；结束检测可能因页面关键词误判。
- 直接重复调用停止 API 可能损坏终态，CLI 会先读状态以减少误操作；核心 API 尚未实现可靠幂等保护。
- refined_note.md 含财经规则，属于待核对草稿；最终笔记应依据完整原始转写整理。
- 本仓库未指定开源许可证，此预发布不新增许可证授权声明。

安装包只包含代码、说明和模板，不包含直播录音、私人笔记、浏览器配置、模型或虚拟环境。
