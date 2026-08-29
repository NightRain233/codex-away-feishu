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

## 快速安装

### 方式 A：让 Codex 安装 Skill

下载 [`dist/codex-away-skill-macos.zip`](dist/codex-away-skill-macos.zip)，解压后将 `codex-away` 放入 `~/.codex/skills/`，重启 Codex Desktop，然后发送：

```text
请使用 $codex-away 安装 Codex Away Feishu，默认只安装通知模式。
```

安装器会先执行只读检查，在写入本地文件前展示路径并请求确认。需要 macOS、Codex Desktop、Python 3.11+ 和已配置的飞书 CLI。

### 方式 B：从仓库安装

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

## 开发验证

```bash
cd codex-away
ruff check .
python3.11 -m unittest discover -s tests
python3 /path/to/quick_validate.py .
```

## 许可证

MIT License，见 [LICENSE](LICENSE)。
