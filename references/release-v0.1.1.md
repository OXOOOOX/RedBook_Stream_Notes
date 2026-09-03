# v0.1.1 · 交接资料完整安装包（MVP 预发布）

v0.1.0 发布后，交接资料先加入了 main，旧安装包仍缺少这些文件。v0.1.1 把它们纳入新的分发包，让通过 ZIP 安装的使用者也能完整接手项目。

## 更新内容

- 随包提供 `references/handoff.md`：发布基线、设计决策、已知限制、下一步优先级和新聊天接手提示词。
- 随包提供根目录 `AGENTS.md`，完整保留维护者禁止批量删除文件/目录的约束；包内相对链接可直接打开。
- 随包提供 `assets/offline-note-evaluation.json`，保留之前的模拟转写材料和对应验收流程。
- 同步最终 v0.1.0 CI 证据、构建复盘、权限排雷和最新发布入口。
- 打包白名单新增可选的 AGENTS.md，仍可验证不含该文件的旧版本 ZIP。
- Python 包、模块版本与 FastAPI 显示版本统一为 0.1.1。

## 安装与升级

下载本 Release 的 `redbook-live-notes.zip`，解压到新的目录，按 README 安装依赖。已有 v0.1.0 的用户先保留自己的 runtime、exports 和其他本地数据，再按宿主的 skill 安装位置完成更新；不要批量删除旧目录或录音。

本版本 ZIP 内即可阅读交接、构建、排雷和验证文档。仓库最新开发内容仍以 main 为准；v0.1.0 保留为历史版本。

## 验证与边界

本地 52 项离线测试通过。发布验证还包含打包/链接检查、AGENTS.md 保留及解压后自包含回归检查、旧版 ZIP 兼容验证，以及远程附件下载后的散列与内容核对。实际提交、CI 结果、附件大小与 SHA256 由发布时生成并附在 [GitHub Release 页面](https://github.com/OXOOOOX/RedBook_Stream_Notes/releases/tag/v0.1.1)。

本次主要更新分发内容和版本信息。录音/识别仍串行，任务索引仍在内存，停止幂等和规则摘要的已知限制仍见项目文档。本次发布没有进行真实直播录音或模型推理，未新增许可证授权。

仓库：[项目主页](https://github.com/OXOOOOX/RedBook_Stream_Notes)。历史版本：[v0.1.0](https://github.com/OXOOOOX/RedBook_Stream_Notes/releases/tag/v0.1.0)。
