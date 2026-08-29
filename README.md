# Codex Away Feishu

让 Codex Desktop 在你离开电脑时仍然可达：通过飞书接收 Codex 完成通知和权限等待提醒，并可选地把飞书回复送回对应的 Codex Desktop 任务。

这是一个 macOS 本地 Skill，Codex Desktop 仍然是主工作台，飞书只是通知和延续层。默认安装为“仅通知”模式，不安装后台回复监听器，也不需要 macOS 辅助功能权限。

## 安装

最简单的方式是下载 [`dist/codex-away-skill-macos.zip`](dist/codex-away-skill-macos.zip)，解压后将 `codex-away` 放入 `~/.codex/skills/`，重启 Codex Desktop，然后告诉 Codex：

```text
请使用 $codex-away 安装 Codex Away Feishu。
```

安装流程会先运行只读检查，并在写入本地文件前展示路径和请求确认。需要 Python 3.11+、macOS、Codex Desktop 和飞书 CLI。

## 两种模式

默认只安装通知：

- Codex 完成通知
- Codex 权限等待提醒
- 不安装 LaunchAgent、AppleScript App 或持续消息监听

需要从飞书继续 Codex 时，再启用可选回复桥：

```bash
python3.11 scripts/setup.py enable-replies --yes
```

回复模式会额外安装后台监听器和本地编译的 AppleScript 辅助 App，并需要用户在 macOS 设置中授予辅助功能权限。回复长消息时，任意分段都映射到同一个 Codex 任务，推荐回复最后一段。

## 安全边界

- 仅接受配置用户在配置 P2P 会话中的直接回复。
- 飞书回复不会远程批准 Codex 权限请求。
- AppleScript 源码随仓库分发，辅助 App 在本机编译，不提交预编译二进制。
- 凭据、open_id、chat_id、日志和本地配置不会进入仓库。

详细安装和排障说明见 [`codex-away/SKILL.md`](codex-away/SKILL.md) 和 [`codex-away/references/setup.md`](codex-away/references/setup.md)。

## 开发验证

```bash
cd codex-away
ruff check .
python3.11 -m unittest discover -s tests
```

## 许可证

MIT License，见 [`LICENSE`](LICENSE)。
