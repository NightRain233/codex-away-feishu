# Setup Guide

## Choose a mode

Use notification-only mode unless the user explicitly asks to reply from Feishu.

| Mode | Installs | Manual permission |
| --- | --- | --- |
| `notify` | Notification runtime, CLI switch, completion hook, permission-waiting hook | None beyond normal Feishu bot setup |
| `replies` | Everything in `notify`, plus event listener, LaunchAgent, and locally compiled AppleScript App | macOS Accessibility for the helper App |

An existing legacy installation with a P2P `chat_id` is treated as reply-enabled. Do not silently downgrade it during reinstallation.

## Changed paths

Both modes change only the current user's files:

- `~/.codex/codex-away/`: notification runtime and private local configuration
- `~/.local/bin/codex-away`: notification switch
- `~/.codex/config.toml`: wraps the existing top-level Codex `notify` command
- `~/.codex/hooks.json`: adds a `PermissionRequest` notification hook

Reply mode additionally changes:

- `~/.codex/codex-feishu-bridge/`: Feishu event listener and AppleScript source
- `~/.local/bin/codex-feishu-bridge`: bridge launcher
- `~/Applications/Codex Feishu Submit.app`: locally compiled Accessibility helper
- `~/Library/LaunchAgents/com.codex-away.feishu-bridge.plist`: background listener

Before changing `config.toml` or `hooks.json`, the installer writes timestamped backups beside them. It preserves an existing notification callback by calling it after codex-away.

## Guided workflow

Do not make the user execute these commands. Run them on the user's behalf and pause only for explicit approval or a required UI action.

### 1. Run read-only preflight

For a new default notification installation, or to preserve the mode of an existing installation:

```bash
python3.11 scripts/setup.py preflight --json
```

For notification plus replies:

```bash
python3.11 scripts/setup.py preflight --mode replies --json
```

Explain every blocker. State the selected mode and show the exact `changes` paths before requesting approval. Preflight validates temporary copies of Codex configuration.

### 2. Configure a Feishu bot

If `lark-cli` is missing, request approval before installing its npm package:

```bash
npm install -g @larksuite/cli
```

If the bot is not ready, start this command in the background because it waits for the user:

```bash
lark-cli config init --new
```

Extract the returned verification URL unchanged. Generate a PNG QR code in the current directory with `lark-cli auth qrcode`, show both the link and QR code, then wait for the user to finish setup.

Every mode needs the bot capability, permission to send bot messages, a published app version, and availability to the installing user.

Notification-only setup first tries the verified `lark-cli` user identity's `open_id`. If unavailable, it falls back to one direct message. That fallback additionally needs:

1. Bot permission `im:message.p2p_msg:readonly`.
2. Long-connection subscription to `im.message.receive_v1`.

Reply mode always needs those receive permissions and event subscription because it must identify and continuously listen to the P2P chat.

For an existing app, keep its secret out of shell history by using `lark-cli config init --app-id APP_ID --app-secret-stdin`.

### 3. Approve and install

After bot setup, obtain approval for the paths returned by preflight.

Install the preflight-selected mode. This defaults new installations to notification-only and preserves existing reply installations:

```bash
python3.11 scripts/setup.py install --yes
```

Install replies immediately when explicitly requested:

```bash
python3.11 scripts/setup.py install --mode replies --yes
```

If setup announces direct-message discovery, tell the user to send one direct text message to the bot while the command waits. The setup command keeps discovered IDs out of command arguments.

Reply mode compiles `assets/Codex Feishu Submit.applescript` locally. The archive intentionally contains no precompiled App.

### 4. Complete manual steps

Both modes require restarting Codex desktop so updated hooks are loaded.

Reply mode additionally requires the user to open System Settings, Privacy & Security, Accessibility, and enable:

`~/Applications/Codex Feishu Submit.app`

This permission lets the helper bring Codex to the foreground and submit a deep-linked message with Return. Never request Accessibility permission for notification-only mode.

### 5. Verify the selected mode

Run diagnostics with the selected mode:

```bash
python3.11 scripts/setup.py doctor --mode notify
```

or:

```bash
python3.11 scripts/setup.py doctor --mode replies
```

Then enable one notification for the current task:

```bash
codex-away on --thread "$CODEX_THREAD_ID"
```

Complete a Codex turn and confirm that the Feishu message arrives. In reply mode, also reply directly to that message and confirm it is submitted in the same Codex desktop task. Process health alone is insufficient verification.

## Add or remove replies later

Before enabling replies, run `preflight --mode replies --json`, show its additional paths, and obtain approval. Then run:

```bash
python3.11 scripts/setup.py enable-replies --yes
```

Grant Accessibility permission, restart Codex, and verify with `doctor --mode replies` plus a real reply.

To keep notifications while disabling replies, show that the LaunchAgent will be stopped and obtain approval. Then run:

```bash
python3.11 scripts/setup.py disable-replies --yes
```

The command unloads the listener, moves its LaunchAgent plist into the private bridge directory, clears reply mappings, and leaves notification hooks intact. It preserves the helper and source so replies can be re-enabled later.

## Diagnostics

Useful local logs:

- `~/.codex/codex-away/notify.log`
- `~/.codex/codex-feishu-bridge/bridge.log` in reply mode
- `~/.codex/codex-feishu-bridge/launchd.stderr.log` in reply mode

Common failures:

- No Feishu notification: verify bot sending permission, recipient ID, Codex notification configuration, and `codex-away on` state.
- Reply mode does not return messages: verify receive-event subscription, long connection, LaunchAgent, and that the message directly replies to a notification.
- Codex opens but does not send: recheck Accessibility permission for the locally compiled helper App.
- Permission notification arrives: this is informational only. The bridge deliberately cannot approve a permission request remotely.

Long completion messages are sent in multiple ordered Markdown messages when they exceed the safe Feishu payload size. The content is not truncated, and every segment remains mapped to the same Codex task; replying to the last segment is recommended.
