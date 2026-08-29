# Install Codex Away Feishu

## Recommended: install as a Skill

Run this in a terminal:

```bash
npx skills add NightRain233/codex-away-feishu --skill codex-away -a codex -g
```

Restart Codex Desktop after the Skill installer finishes. Then paste this prompt into Codex:

```text
请使用 $codex-away 安装 GitHub 仓库 https://github.com/NightRain233/codex-away-feishu 中的 Codex Away Feishu。

先阅读 Skill 的安装说明并运行只读 preflight。默认只安装 notify（仅通知）模式，不要开启 replies，不要申请 macOS 辅助功能权限。

安装前请告诉我会修改哪些本地文件，并在真正写入前等待我的确认。完成后运行 doctor，并告诉我还需要完成哪些飞书配置或重启步骤。
```

这句提示词会让 Codex 负责本机安装流程；它不会把飞书密钥、open_id 或 chat_id 写入命令或仓库。

## Optional: enable replies

通知模式安装完成并验证后，如果确实需要从飞书回复 Codex，再对 Codex 说：

```text
请阅读 codex-away 的回复桥安装说明，先运行 replies 模式的只读 preflight。
如果需要新增 LaunchAgent、AppleScript 辅助 App 或 macOS 辅助功能权限，请逐项说明并等待我的确认。
确认后再开启 replies，并在完成后运行 doctor。
```

## Offline ZIP

没有使用 `npx skills` 时，可以从 [v0.1.0 Release](https://github.com/NightRain233/codex-away-feishu/releases/tag/v0.1.0) 下载 `codex-away-skill-macos.zip`，解压后将其中的 `codex-away` 文件夹复制到 `~/.codex/skills/`，重启 Codex Desktop，再使用上面的提示词。

## Requirements

- macOS
- Codex Desktop
- Python 3.11 or newer
- Feishu CLI (`lark-cli`) and a configured bot

新安装默认不需要辅助功能权限。只有开启 replies 模式，才需要本地编译 AppleScript App 和 macOS 辅助功能授权。
