# Codex Away Feishu

让 [Codex Desktop](https://openai.com/codex/) 在你离开电脑时仍然可达：任务完成或等待权限时，通过飞书通知你；需要时，再把飞书回复送回对应的 Codex Desktop 任务。

> Codex Desktop 是主工作台，飞书只是通知和延续层。这个项目不是把飞书变成第二个 Codex 客户端。

## 适合谁

- 让 Codex 在本机长时间运行，离开电脑后想知道结果。
- 不想错过 Codex 的权限等待。
- 偶尔需要从飞书给当前 Codex 任务补一句指令。
- 使用 macOS Codex Desktop，并希望保留原来的上下文、文件和界面。

如果你需要在服务器上长期运行无头 Codex，或把飞书做成完整远程编程客户端，请考虑 App Server 或其他远程 Agent 方案。

## 工作方式

```text
Codex Desktop
    |
    | completion / permission hooks
    v
Codex Away Feishu -----> Feishu bot -----> 你的飞书
                              |
                              | optional direct reply
                              v
                    对应的 Codex Desktop task
```

## 两种安装模式

| 模式 | 能做什么 | 额外权限 |
| --- | --- | --- |
| `notify`（默认） | 完成通知、权限等待提醒 | 不需要 macOS 辅助功能权限 |
| `replies`（可选） | 在通知基础上，把飞书回复送回对应任务 | 后台监听器 + 本地 AppleScript App + 辅助功能权限 |

长结果会自动拆成多条 Feishu Markdown 消息，不会截断。每一段都映射到同一个任务，回复最后一段最自然。

### 重要限制

回复桥使用 macOS GUI 自动化将消息提交到 Codex Desktop。锁屏时，macOS 可能阻止模拟回车；这时消息会在解锁后才能提交。通知模式不受这个限制。

## 技术路线

项目把 Codex Desktop 当作唯一的任务执行端，不启动第二个 Codex，也不尝试把飞书做成完整 IDE：

```text
Codex hooks (notify / PermissionRequest)
    -> 本地 Python 运行时
    -> lark-cli 机器人
    -> 飞书私聊

飞书回复（仅 replies 模式）
    -> 本地 WebSocket 事件监听
    -> message_id -> Codex task_id 映射
    -> codex:// 深链打开原任务
    -> AppleScript 辅助 App 激活窗口并提交 Return
```

因此，通知模式只负责把本机事件送到飞书；回复模式才需要 GUI 自动化。它不使用 Codex App Server，也不在云端保存任务状态。

## `npx` 到底安装了什么

上面的 `npx skills add ...` 使用的是 npm 上的通用 `skills` 安装器。安装器会从 GitHub 克隆本仓库，找到 `codex-away/SKILL.md`，再把这个 Skill 安装到 Codex 的全局 Skill 目录。我们的 Skill 没有上传到 npm；GitHub 仓库才是源码和版本的来源，npm 只提供安装器。

这也意味着安装时需要网络访问 GitHub/npm。不能联网时，请改用 Release ZIP。OpenAI API 另有独立的 Skills 上传接口，但本项目没有使用那条路线。[OpenAI Skills API](https://developers.openai.com/api/reference/python/resources/skills/methods/create)

## 为什么需要授权

授权分成相互独立的几层，通知模式和回复模式不需要同样的权限：

- **飞书应用权限**：机器人需要发送私聊消息；开启 `replies` 后，还需要接收消息事件并读取回复关联信息。
- **Codex 本地配置写入**：安装器会在用户确认后合并 `~/.codex/config.toml`、Hook 配置和本地运行时文件，并保留备份。
- **macOS 辅助功能权限（仅 replies）**：AppleScript 辅助 App 需要获得“控制电脑”的权限，才能激活 Codex Desktop 并模拟提交键盘操作。macOS 不允许程序绕过这一安全边界自动授权。

项目不会替用户远程批准 Codex 权限请求，也不会把飞书密钥写进命令、仓库或日志。

## 风险与边界

- Codex 的任务结果和工作目录会发送到配置的飞书会话，请不要对包含敏感内容的任务盲目开启通知。
- 回复只接受配置用户在配置 P2P 会话中、针对已映射消息的回复；陌生人消息不会被转发到 Codex。
- 锁屏或睡眠可能阻止 GUI 回车，导致回复延迟到解锁后；通知链路仍可工作。
- 本机 Python 运行时、LaunchAgent 和 AppleScript 辅助 App 都以当前用户身份运行，卸载前应使用项目提供的 disable/cleanup 流程。

## 快速安装

### 推荐：一条命令安装 Skill

```bash
npx skills add NightRain233/codex-away-feishu --skill codex-away -a codex -g
```

重启 Codex Desktop 后，粘贴这句提示词：

```text
请使用 $codex-away 安装 GitHub 仓库 https://github.com/NightRain233/codex-away-feishu 中的 Codex Away Feishu。
先阅读 Skill 的安装说明并运行只读 preflight。默认只安装 notify（仅通知）模式，不要开启 replies，不要申请 macOS 辅助功能权限。
安装前请告诉我会修改哪些本地文件，并在真正写入前等待我的确认。完成后运行 doctor，并告诉我还需要完成哪些飞书配置或重启步骤。
```

完整安装流程见 [`INSTALL.md`](INSTALL.md)。

### 备选：从 Release ZIP 安装

下载 [`dist/codex-away-skill-macos.zip`](dist/codex-away-skill-macos.zip)，解压后将 `codex-away` 放入 `~/.codex/skills/`，重启 Codex Desktop，然后使用 `INSTALL.md` 中的提示词。安装器会先执行只读检查，在写入本地文件前展示路径并请求确认。

### 开发者：从仓库安装

```bash
git clone https://github.com/NightRain233/codex-away-feishu.git
cp -R codex-away-feishu/codex-away ~/.codex/skills/
```

然后重启 Codex Desktop，并让 Codex 运行安装流程。不要把飞书密钥、`open_id` 或 `chat_id` 写进命令、Issue 或仓库。

## 开启和关闭回复

通知模式是默认模式。明确需要从飞书回复时，在 Skill 目录执行：

```bash
python3.11 scripts/setup.py enable-replies --yes
```

关闭回复但保留通知：

```bash
python3.11 scripts/setup.py disable-replies --yes
```

回复模式会在本机编译 AppleScript 辅助 App，不会在仓库分发预编译二进制。macOS 辅助功能权限必须由用户手动授予。

## 安全边界

- 只接受配置用户在配置 P2P 会话中的直接回复。
- 飞书消息不会远程批准 Codex 权限请求。
- 凭据、运行状态、日志和个人路径只保存在本机。
- 安装器会备份并合并已有的 Codex `notify` 与 `PermissionRequest` 配置。

## 文档

- [安装与配置](codex-away/references/setup.md)
- [Codex Skill 入口](codex-away/SKILL.md)
- [贡献与本地验证](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## CI/CD 与 Release

GitHub Actions 已在每次 push 和 Pull Request 上运行 Ruff、Python 单元测试和 Skill 结构校验。它验证的是源码质量，不会在 Ubuntu runner 上启动 Codex Desktop、配置飞书或申请 macOS 权限。

Release ZIP 可以继续作为 macOS 用户的离线安装包；后续可以增加一个仅在 `v*` 标签触发的打包工作流，自动生成 ZIP 并上传到 GitHub Release。这样 CI 负责可重复构建，GitHub Release 负责分发，用户机器上的运行时和密钥仍不会进入 CI。

## 开发验证

```bash
cd codex-away
ruff check .
python3.11 -m unittest discover -s tests
python3 /path/to/quick_validate.py .
```

## 许可证

MIT License，见 [LICENSE](LICENSE)。
