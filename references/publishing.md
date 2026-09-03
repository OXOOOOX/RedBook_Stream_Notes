# GitHub 发布指南

## 发布范围

仓库根目录即 skill，维护一份源码；发布时用白名单打包。包内包含入口、agents 元数据、README、依赖声明、脚本、参考文档、模板、服务源码，以及维护者未来加入的 LICENSE。测试和 CI 保留在仓库中。工程背景见[构建过程](build-process.md)，已做检查见[验证记录](validation.md)。

## 本地验证

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/redbook.py --help
python scripts/package_skill.py --check
```

pytest 不访问直播、不录音、不下载模型。设备检查另用 `doctor --audio`；真实页面与 ASR 链路另做 15 秒、1 块测试。没有设备的 CI 不需要录音或安装 Chromium。宿主若带有 skill-creator，可额外用其 quick_validate.py 验证仓库根目录。

## 生成和核对 ZIP

```powershell
python scripts/package_skill.py
python scripts/package_skill.py --verify dist/redbook-live-notes.zip
```

默认产物是 `dist/redbook-live-notes.zip`，工具输出 SHA256；ZIP 根目录为 `redbook-live-notes/`，内部 MANIFEST.json 记录文件内容散列。查看 `--help` 获取全部选项。

再次生成可选新路径：

```powershell
python scripts/package_skill.py --output dist/redbook-live-notes-review.zip
```

确需替换该文件时传 `--force`。把 ZIP 解压到新的目录后，运行其中 `scripts/redbook.py --help` 与 `scripts/package_skill.py --check`，确认不依赖原仓库外的文件。只有安装依赖后才能启动应用。

白名单防止运行数据误入包，但源码/Markdown 中手写的敏感数据仍会被包含。示例使用虚构链接，不复制 Cookie、真实分享参数、个人目录、录音或现场笔记。Git 已跟踪文件不会因 .gitignore 自动取消跟踪，因此仍需检查 status 和 diff。

## 提交与推送

以下为明确要求上传/发布时执行的手动流程；仅运行打包脚本不会 push 或创建 Release。已有业务代码修改应保留并一起审阅。这个流程不要求覆盖远程历史、修改仓库可见性或把本地运行数据加入版本控制。

```powershell
git status --short
git diff --stat
git diff --check
git add SKILL.md README.md agents references assets scripts tests .github .gitignore pyproject.toml requirements.txt
git diff --cached --stat
git diff --cached --check
```

如需包含已审阅的 src 改动，另行 `git add src/redbook_stream_notes`。未暂存的代码不会出现在远程提交中，ZIP 则读取当前工作区；确保两者是准备发布的同一版本。

确认版本、目标分支与 remote 后：

```powershell
git commit -m "Package RedBook Stream Notes as a reusable skill"
git push origin main
```

示例是本仓库现有 origin/main；以实际分支和仓库流程为准。需 PR 的分支遵循既有流程。

如果推送包含 `.github/workflows/` 且 GitHub 报缺少 `workflow` scope，仓库管理员权限也不会自动补齐该凭据的 scope。先确认实际使用的登录凭据；只有已经获得相应授权的工具可以上传工作流。若没有，请账号持有人完成授权后继续，保留本地提交。不要在日志或文档中输出实际 token。本项目此次上传的具体处置见[工程复盘](engineering-lessons.md)。

## GitHub Release

在对应提交/tag 上创建 Release，上传本工具生成的 ZIP；可把工具输出的 SHA256 写入 Release 描述。说明安装方式、变更、验证范围及录音间隔/规则摘要的主要限制。GitHub 自动提供的源码 ZIP 不等同于白名单安装包。

本次发布说明保存在 [release-v0.1.0.md](release-v0.1.0.md)。打包后的 SHA256 可另存同名 `.zip.sha256` 文件随附件上传；它是该 ZIP 的校验值，不应提前写进参与打包的文档形成循环依赖。Release 应明确绑定已推送且经过检查的提交。MVP 阶段使用预发布标记，避免把有限验证误表述为正式生产可用。

仓库的工作流只做测试并上传 CI 构建产物，不自动 push、打 tag、公开 Release 或发布 PyPI。未来升级版本时核对 pyproject.toml、src 的 __version__ 和 FastAPI version；skill 名称保持 redbook-live-notes。

## 许可证

当前没有指定 LICENSE，本包不声明 MIT、Apache 或其他开源授权。由维护者决定后加入实际许可证，打包工具会包含它；pyproject 的授权声明应与其一致。
