# Codex Away Feishu

Keep [Codex Desktop](https://openai.com/codex/) reachable while you are away: receive Feishu notifications when a task completes or needs permission, and optionally send a Feishu reply back to the matching Codex Desktop task.

Codex Desktop remains the primary workspace. Feishu is only the notification and continuation layer; this project is not a second Codex client.

## Choose a mode

| Mode | What it does | Extra permission |
| --- | --- | --- |
| `notify` (default) | Completion and permission-waiting notifications | No macOS Accessibility permission |
| `replies` (optional) | Also routes Feishu replies to the matching task | Background listener, local AppleScript App, Accessibility permission |

Long results are split into ordered Feishu Markdown messages instead of being truncated. Each segment maps to the same task; replying to the last segment is recommended.

The reply bridge uses macOS GUI automation. While the Mac is locked, macOS may block simulated keyboard input; a reply can be submitted after the Mac is unlocked. Notification-only mode is unaffected.

## Quick install

Download [`dist/codex-away-skill-macos.zip`](dist/codex-away-skill-macos.zip), extract `codex-away` into `~/.codex/skills/`, restart Codex Desktop, and ask Codex:

```text
Use $codex-away to install Codex Away Feishu. Install notification-only mode by default.
```

Requirements: macOS, Codex Desktop, Python 3.11+, and a configured Feishu CLI. The guided installer runs read-only checks first and asks for approval before changing local files.

See the [Chinese README](README.md), [setup guide](codex-away/references/setup.md), and [contributing guide](CONTRIBUTING.md) for details.
