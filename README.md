# Codex Away Feishu

[English](README.en.md)

离开电脑后，在飞书接收 Codex Desktop 的任务结果和权限等待提醒；需要时，还可以从飞书回复原来的 Codex 任务。

- Codex Desktop 始终是唯一工作台，原任务上下文不会被搬到第二个客户端
- 长结果自动拆成多条 Feishu Markdown 消息，不会截断
- 默认仅安装低权限通知模式，回复能力按需开启

## Quick Start

### 1. 安装 Skill

要求：macOS、Codex Desktop、Python 3.11+。使用下面的一行命令安装时，还需要 Node.js/npm；飞书机器人和 `lark-cli` 配置由后续引导完成。

```bash
npx skills add NightRain233/codex-away-feishu --skill codex-away -a codex -g
```

### 2. 让 Codex 完成本机安装

重启 Codex Desktop，然后粘贴：

```text
请使用 $codex-away 安装 GitHub 仓库 https://github.com/NightRain233/codex-away-feishu 中的 Codex Away Feishu。
先阅读 Skill 的安装说明并运行只读 preflight。默认只安装 notify（仅通知）模式，不要开启 replies，不要申请 macOS 辅助功能权限。
安装前请告诉我会修改哪些本地文件，并在真正写入前等待我的确认。完成后运行 doctor，并告诉我还需要完成哪些飞书配置或重启步骤。
```

安装器会先执行只读检查，展示将要修改的本地路径，并在真正写入前等待确认。完整流程见 [`INSTALL.md`](INSTALL.md)。

### 3. 开启一次离开模式

安装并重启完成后，让 Codex 执行：

```bash
codex-away on --thread "$CODEX_THREAD_ID"
```

完成当前任务后，结果会发送到你的飞书。先验证真实通知，再决定是否开启回复能力。

## 两种模式

| 模式 | 能做什么 | 额外权限 |
| --- | --- | --- |
| `notify`（默认） | 任务完成通知、权限等待提醒 | 不需要 macOS 辅助功能权限 |
| `replies`（可选） | 在通知基础上，把飞书回复送回对应任务 | 后台监听器、本地 AppleScript App、辅助功能权限 |

通知模式适合大多数人。只有确实需要离开电脑后继续给 Codex 补充指令时，才需要开启 `replies`。

## 工作原理

项目不启动第二个 Codex，也不使用 Codex App Server。飞书只是 Codex Desktop 的通知和延续层：

```text
Codex hooks (notify / PermissionRequest)
    -> 本地 Python 运行时
    -> lark-cli 机器人
    -> 飞书私聊

飞书回复（仅 replies 模式）
    -> 本地 WebSocket 事件监听
    -> message_id -> Codex task_id 映射
    -> codex:// 深链打开原任务
    -> AppleScript 辅助 App 激活 Codex 并提交消息
```

长结果会按顺序拆分，每一段都映射到同一个 Codex 任务；回复最后一段是最自然的继续方式，回复较早的分段也仍会回到同一任务。

## 权限、安全与限制

### 为什么需要授权

- **飞书应用权限**：通知需要机器人发送私聊消息；`replies` 还需要接收消息事件和读取回复关联信息。
- **Codex 本地配置写入**：安装器会在确认后合并 `~/.codex/config.toml`、Hook 配置和本地运行时文件，并保留备份。
- **macOS 辅助功能权限（仅 replies）**：本地编译的 AppleScript App 需要激活 Codex Desktop 并模拟提交操作；该权限必须由用户手动授予。

### 安全边界

- 只接受配置用户在配置 P2P 会话中、针对已映射消息的直接回复。
- 飞书文本只会作为 Codex 消息传入，不会被解释成 Shell 命令。
- 飞书消息不能远程批准或拒绝 Codex 权限请求。
- 凭据、运行状态、日志和任务映射只保存在本机，不进入仓库或 GitHub Actions。

### 已知限制

- Codex 的任务结果和工作目录会发送到配置的飞书会话，请谨慎处理敏感任务。
- 锁屏时 macOS 可能阻止 GUI 模拟提交；回复会延迟到解锁后，通知模式不受影响。
- Mac 进入睡眠后，本地监听器会暂停，直到系统唤醒。

## 开启或关闭回复

通知模式验证完成后，可以让 Codex 按照 [`INSTALL.md`](INSTALL.md) 中的回复模式提示词引导安装，也可以在 Skill 目录运行：

```bash
python3.11 scripts/setup.py enable-replies --yes
```

关闭回复但保留通知：

```bash
python3.11 scripts/setup.py disable-replies --yes
```

回复模式会在本机从源码编译 AppleScript 辅助 App，仓库和 Release 不分发预编译的辅助功能程序。

## 其他安装方式

### Release ZIP

从 [最新 Release](https://github.com/NightRain233/codex-away-feishu/releases/latest) 下载 `codex-away-skill-macos.zip`，解压后将 `codex-away` 放入 `~/.codex/skills/`，重启 Codex Desktop，再使用上面的安装提示词。

### 从源码安装

```bash
git clone https://github.com/NightRain233/codex-away-feishu.git
cp -R codex-away-feishu/codex-away ~/.codex/skills/
```

不要把飞书密钥、`open_id` 或 `chat_id` 写进命令、Issue 或仓库。

## 关于 `npx skills`

`npx` 临时运行 npm 上的通用 `skills` 安装器；安装器从 GitHub 获取本仓库，找到 `codex-away/SKILL.md`，再安装到 Codex 的全局 Skill 目录。我们的 Skill 没有发布到 npm，GitHub 才是源码和版本来源。

不能访问 GitHub/npm 时，请使用 Release ZIP。OpenAI API 另有独立的 Skills 上传接口，本项目没有使用那条路线。[OpenAI Skills API](https://developers.openai.com/api/reference/python/resources/skills/methods/create)

## 文档

- [完整安装与飞书配置](codex-away/references/setup.md)
- [Codex Skill 入口](codex-away/SKILL.md)
- [贡献与本地验证](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## 开发与发布

```bash
cd codex-away
ruff check .
python3.11 -m unittest discover -s tests
python3 /path/to/quick_validate.py .
```

普通 push 和 Pull Request 会运行 Ruff、Python 单元测试和 Skill 结构校验。推送 `v*` 标签时，GitHub Actions 会构建并验证 ZIP，然后自动创建或更新 GitHub Release。

## License

MIT License，见 [LICENSE](LICENSE)。
