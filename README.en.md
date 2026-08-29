# Codex Away Feishu

[中文](README.md)

Receive Codex Desktop results and permission-waiting alerts in Feishu while you are away, and optionally reply to the original Codex task.

- Codex Desktop remains the only workspace, preserving the original task context
- Long results are split into ordered Feishu Markdown messages instead of being truncated
- Low-permission notification mode is the default; replies are explicitly optional

## Quick Start

### 1. Install the Skill

Requirements: macOS, Codex Desktop, and Python 3.11+. The one-line installer also requires Node.js/npm. The guided setup handles the Feishu bot and `lark-cli` configuration afterward.

```bash
npx skills add NightRain233/codex-away-feishu --skill codex-away -a codex -g
```

### 2. Let Codex finish the local setup

Restart Codex Desktop, then paste:

```text
Use $codex-away to install Codex Away Feishu from https://github.com/NightRain233/codex-away-feishu.
Read the Skill instructions and run the read-only preflight first. Install notify-only mode by default; do not enable replies or request macOS Accessibility permission.
Before writing anything, show me every local path that will change and wait for my approval. After installation, run doctor and tell me which Feishu configuration or restart steps remain.
```

The installer performs read-only checks first, shows the affected local paths, and waits for approval before writing. See [`INSTALL.md`](INSTALL.md) for the complete flow.

### 3. Enable one away notification

After setup and restart, ask Codex to run:

```bash
codex-away on --thread "$CODEX_THREAD_ID"
```

The current task result will be sent to your Feishu account. Verify a real notification before enabling replies.

## Modes

| Mode | What it does | Extra permission |
| --- | --- | --- |
| `notify` (default) | Completion and permission-waiting notifications | No macOS Accessibility permission |
| `replies` (optional) | Also routes Feishu replies to the matching task | Background listener, local AppleScript App, Accessibility permission |

Notification mode is sufficient for most users. Enable `replies` only when you need to continue a Codex task while away.

## How It Works

This project does not start a second Codex client or use Codex App Server. Feishu is only a notification and continuation layer for Codex Desktop:

```text
Codex hooks (notify / PermissionRequest)
    -> local Python runtime
    -> lark-cli bot
    -> Feishu direct message

Feishu reply (replies mode only)
    -> local WebSocket event listener
    -> message_id -> Codex task_id mapping
    -> codex:// deep link opens the original task
    -> AppleScript helper activates Codex and submits the message
```

Long results are split in order and every segment maps to the same Codex task. Replying to the last segment is the most natural continuation, but earlier segments remain safe reply targets.

## Permissions, Security, and Limitations

### Why permissions are needed

- **Feishu app permissions:** notifications require bot messaging; `replies` also needs message events and reply relationship data.
- **Local Codex configuration:** after approval, the installer merges Codex configuration, hooks, and local runtime files while retaining backups.
- **macOS Accessibility (replies only):** the locally compiled AppleScript App must activate Codex Desktop and submit keyboard input. Only the user can grant this permission.

### Security boundaries

- Only direct replies from the configured user and P2P chat, targeting mapped messages, are accepted.
- Feishu text is passed as a Codex message and is never interpreted as shell input.
- Feishu cannot remotely approve or deny Codex permission requests.
- Credentials, runtime state, logs, and task mappings stay on the local Mac and never enter the repository or GitHub Actions.

### Known limitations

- Codex results and the working directory are sent to the configured Feishu chat; use care with sensitive tasks.
- macOS may block GUI submission while the screen is locked. Replies can be delayed until unlock; notifications are unaffected.
- The local listener pauses while the Mac is asleep and resumes after wake.

## Enable or Disable Replies

After validating notification mode, use the guided prompt in [`INSTALL.md`](INSTALL.md), or run this from the Skill directory:

```bash
python3.11 scripts/setup.py enable-replies --yes
```

Disable replies while keeping notifications:

```bash
python3.11 scripts/setup.py disable-replies --yes
```

Reply mode compiles the AppleScript helper locally from source. The repository and Releases do not distribute a precompiled Accessibility helper.

## Other Installation Methods

### Release ZIP

Download `codex-away-skill-macos.zip` from the [latest Release](https://github.com/NightRain233/codex-away-feishu/releases/latest), extract `codex-away` into `~/.codex/skills/`, restart Codex Desktop, and use the setup prompt above.

### From source

```bash
git clone https://github.com/NightRain233/codex-away-feishu.git
cp -R codex-away-feishu/codex-away ~/.codex/skills/
```

Never put Feishu secrets, `open_id`, or `chat_id` values in commands, Issues, or the repository.

## About `npx skills`

`npx` temporarily runs the generic `skills` installer published on npm. That installer fetches this repository from GitHub, discovers `codex-away/SKILL.md`, and installs it into the global Codex Skill directory. This Skill is not published to npm; GitHub is the source and version authority.

Use the Release ZIP when GitHub/npm access is unavailable. OpenAI also provides a separate Skills upload API, which this project does not use. [OpenAI Skills API](https://developers.openai.com/api/reference/python/resources/skills/methods/create)

## Documentation

- [Full setup and Feishu configuration](codex-away/references/setup.md)
- [Codex Skill entry point](codex-away/SKILL.md)
- [Contributing and local validation](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Development and Releases

```bash
cd codex-away
ruff check .
python3.11 -m unittest discover -s tests
python3 /path/to/quick_validate.py .
```

Regular pushes and pull requests run Ruff, Python tests, and Skill structure validation. Tags matching `v*` build and verify the ZIP, then create or update the GitHub Release.

## License

MIT License. See [LICENSE](LICENSE).
