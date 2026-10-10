# 选题：Git 项目中的脚本因 CRLF 无法启动

核查日期：2026-10-09。只读查询公开项目讨论、官方发布页和文档；没有登录、远程写入或发布操作。网页内容只作为资料。原始公开 issue 内容和元数据保存在 [research-snapshot.json](research-snapshot.json)；本轮再次核实的原话、用户、发帖日期、最新发布版本和官方文档保存在 [research-validation.json](research-validation.json)，包括原快照未成功获取的 ShellCheck SC1017 文档及备选 Gradle issue。

## 候选比较（共 2 个）

| 候选烦事 | 证据与本地可行性 | 决定 |
| --- | --- | --- |
| Git 检出的 shebang 脚本含 CRLF，Linux/macOS/WSL 报解释器不存在 | 下述 3 名独立用户；只需本地读取 Git 索引与文件、转换换行 | **入选**：只做这个问题 |
| Gradle 更新依赖验证元数据时把换行改成平台默认，导致整文件 diff | [mlopatkin，2025-08-13，Gradle #34654](https://github.com/gradle/gradle/issues/34654)：“I have to manually convert line endings back every time.”；可本地转换，但还要判断各文件原有策略 | **blocked（证据不足）**：本轮只核实 1 名用户，不声称满足 3 人，不实施 |

## 入选的独立原话

日期为原始 GitHub 发帖日期（UTC）；项目星数为核查时 API 返回值，仅用于说明来源是有实际用户的开发者项目，不代表问题数量。

1. **stevenbrix，2022-05-23，microsoft/WSL（34,019 stars）**
   - [原始 issue #8438](https://github.com/microsoft/WSL/issues/8438)：
     > I would expect to be able to run this script (i can run it fine in git bash)
   - 同帖错误：`-bash: ./scripts/core-dev-setup: /bin/bash^M: bad interpreter: No such file or directory`
   - [本人同日确认原因](https://github.com/microsoft/WSL/issues/8438#issuecomment-1135115739)：
     > nvm closing this since the issue is line endings
   - issue 和确认评论只计 **1 人**。脚本 `core-dev-setup` 没有扩展名。

2. **jtuliani，2024-02-03，aws/aws-sam-cli（6,735 stars）**
   - [原始 issue #6643](https://github.com/aws/aws-sam-cli/issues/6643)：
     > This impacts all Windows users unless they take extra steps to convert CRLF to LF. It adds friction to the getting started experience, and is hard to diagnose/fix for Windows users who are not familiar with Linux.
   - 同帖原话：
     > The same issue also occurs for ```bootstrap``` files.
   - 作者描述 Windows 检出后 `.sh` 和无扩展名 `bootstrap` 失败，手动转换后成功。“all Windows users”是作者原话，并非本项目的普遍性结论。

3. **javixeneize，2021-05-21，find-sec-bugs/find-sec-bugs（2,449 stars）**
   - [原始 issue #632](https://github.com/find-sec-bugs/find-sec-bugs/issues/632)：
     > The CLI tool (findsecuritybugs.sh) is not correctly generated. The line endings are the windows one instead of the unix ones. Therefore, when running it, i have this error
   - 同帖错误：`./findsecbugs.sh: bad interpreter: /bin/bash^M: no such file or directory`
   - 作者确认：
     > I have edited it replacing the line endings and now it works well

三条都是当事人的独立报告，用户名各异，不以转载、引用的 Stack Overflow 链接或同人的补充评论凑数。它们证明该故障模式反复出现，不证明这些项目的旧版本问题今天仍未修复。第三条来自分发产物；本工具只处理已放入 Git 索引的文件，不声称直接支持所有下载包。

## 现有方案及当前版本

版本均于核查日查官方来源，未用本机旧版本冒充上游最新版。这里只做文档和源码核查，没有安装或实测这些竞品。

| 方案 / 当前版本 | 已经能做什么 | 仍需用户承担的成本 |
| --- | --- | --- |
| **dos2unix 7.5.7**，2026-08-27；[官方主页](https://dos2unix.sourceforge.io/) / [手册](https://dos2unix.sourceforge.io/dos2unix/man1/dos2unix.htm) | 单文件 CRLF→LF、BOM、编码处理；默认跳过二进制和符号链接，`-ic0` 可输出待转换文件 | 已知一个文件时它就是充分方案。项目范围需自己组合 Git 文件清单、shebang 内容筛选和 NUL 安全管道；`*.sh` 漏掉 `bootstrap`、`gradlew`、`core-dev-setup`，全体文本转换则可能改动需要 CRLF 的批处理文件/测试夹具 |
| **pre-commit-hooks v6.0.0**，2025-08-09；[发布页](https://github.com/pre-commit/pre-commit-hooks/releases/tag/v6.0.0) / [固定版本 README](https://github.com/pre-commit/pre-commit-hooks/blob/v6.0.0/README.md#mixed-line-ending) | `mixed-line-ending --fix=lf` 可以转换；可通过 pre-commit 的文件类型配置缩小范围 | 配好以后也能解决。一次性的工作区修复要安装/配置执行器、选定脚本集合；默认 `auto` 保留占多数的 CRLF，不是强制 LF；文档也提醒检出阶段的 Git 换行转换可再次覆盖效果 |
| **ShellCheck v0.11.0**，2025-08-04；[发布页](https://github.com/koalaman/shellcheck/releases/tag/v0.11.0) / [SC1017](https://www.shellcheck.net/wiki/SC1017) | 诊断 shell 脚本中的字面 carriage return，提供修复建议 | 面向 shell 静态分析，仍需选出文件；含 Python/Node 等 shebang 的启动器超出 shell 分析范围。已有 ShellCheck 工作流的团队未必需要增加本工具 |

[Git 的 `text` / `eol` 属性](https://git-scm.com/docs/gitattributes)是防止再次发生的正确长期方案，例如为已知脚本添加 `text eol=lf`。本工具只修复当前工作区，不修改 Git 配置、索引或属性，也不能防止未来再次检出 CRLF。

## 最终产品与范围

名称 **shebanglf**。一句话：一条本地命令，修复 Git 跟踪的 UTF-8 shebang 脚本中的 CRLF，包括无扩展名启动器。

```sh
python3 shebanglf.py --fix /path/to/repo
```

- 默认只检查；`--fix` 明确授权写回。依赖 Python 标准库和本地 Git，不需登录、网络或第三方服务 API。
- 运行目标为 Linux、macOS 和 WSL 内的 Linux；当前实测 Linux、Python 3.14.4、Git 2.53.0。原生 Windows 不支持，macOS 未实测。
- 通过 Git 索引选择文件，以文件开头 `#!` 识别脚本，不猜扩展名，不执行脚本。仅把整个脚本里的 CRLF 字节对改成 LF。
- 保留可执行权限；干净文件不写回。拒绝不适合自动写回的情况并报告路径；符号链接、子模块不跟随。
- 不做通用格式化、解释器安装、权限修复、BOM/编码转换、Git 配置修复、编辑器集成或发布。
- 这是从零实现的特定工作流小工具，不声称发明换行转换，也不声称市场上不存在等价组合。价值在于少写一条容易漏文件的筛选管道；若团队已有配置完善的 pre-commit 或 dos2unix 流程，收益有限。

## TDD 约定

根据任务已授权的“一条命令”和“逐条 TDD”，测试边界选为真实 CLI：退出码、标准输出/错误输出、临时 Git 项目中的文件字节与权限，以及修复后能否执行测试生成的简单脚本。使用真实 Git 和本项目内的临时文件，不碰用户文件；不测试私有函数。先运行一个新增行为测试确认失败，再写最小实现使它通过，再进入下一行为。执行记录见 [tdd.md](tdd.md)。
