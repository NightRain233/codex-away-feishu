---
name: codex-away
description: Install, configure, diagnose, or uninstall macOS Codex notifications to Feishu, with an optional reply bridge back into the matching Codex desktop task. Use when the user mentions codex-away, remote Codex notifications, or replying to Codex from Feishu. macOS Codex desktop only.
---

# Codex Away

Set up user-scoped Codex desktop notifications to a Feishu bot. Notification-only mode is the default. The reply bridge is an explicit advanced option because it adds a background listener and macOS Accessibility permission. Keep credentials out of commands, logs, the skill, and generated archives.

## Route

- For installation or reconfiguration, read [references/setup.md](references/setup.md), then drive the staged setup with `scripts/setup.py`. Do not make the user copy IDs or run its terminal commands. If replies were not explicitly requested, install notification-only mode.
- For a health check, run `python3.11 scripts/setup.py doctor` and explain each failed check before changing anything.
- For uninstall, enumerate the affected paths, obtain explicit approval, then run `python3.11 scripts/uninstall.py --yes`. The uninstaller moves installed files to Trash and unwraps only this tool's hooks.

## Guided installation

1. Run `python3.11 scripts/setup.py preflight --json`. This selects `notify` for a new installation and preserves an existing installation's mode. Pass `--mode replies` only when the user explicitly asks for replies, or `--mode notify` when they explicitly ask to remove replies. Summarize blockers and show every path under `changes` before requesting approval.
2. If `lark-cli` is missing, ask before installing `@larksuite/cli`. If the bot identity is not ready, start `lark-cli config init --new` in the background. Show its verification URL unchanged, generate a QR code with `lark-cli auth qrcode`, and stop until the user completes setup.
3. After approval, run `python3.11 scripts/setup.py install --yes`, adding the same explicit `--mode` override used for preflight, if any. Notification-only mode first reuses saved configuration or the authenticated user's `open_id`; only ask for one direct bot message if setup says discovery requires it. Reply mode reuses a saved private chat or discovers one.
4. In notification-only mode, ask only for a Codex restart. In reply mode, also ask the user to grant Accessibility permission to the locally compiled helper. Do not claim completion before the required restart.
5. After restart, run `python3.11 scripts/setup.py doctor --mode MODE`, enable a one-shot notification, and verify a real completion. Verify a direct Feishu reply only in reply mode.

The workflow is resumable. On any retry, start with preflight or doctor and continue from the failed stage. Do not create duplicate hooks, services, or bot applications merely because a previous attempt stopped.

## Installation invariants

- Require macOS, Codex desktop, Python 3.11+, and `lark-cli` with a ready bot identity.
- Never copy another person's Feishu app credentials, `open_id`, or `chat_id`.
- Never put a Feishu app secret in a shell argument. If configuring an existing app, use `lark-cli config init --app-secret-stdin`.
- Notification-only mode needs bot messaging. It does not install the reply runtime, LaunchAgent, AppleScript helper, or request Accessibility permission.
- If notification-only setup can read the authenticated user's `open_id`, it does not need receive-event discovery. Otherwise it falls back to one direct message and needs `im:message.p2p_msg:readonly` plus `im.message.receive_v1` during discovery.
- Reply mode needs `im:message.p2p_msg:readonly`, long-connection subscription to `im.message.receive_v1`, and the configured P2P chat.
- Let `scripts/setup.py` derive the recipient `open_id` and, when needed, P2P `chat_id`. Never ask the user to copy these IDs.
- Before running `scripts/install.py --yes`, show the user the local paths and configuration files it will change and obtain approval.
- Preserve existing Codex notifications and hooks. The installer backs up and wraps the existing top-level `notify` command, and merges its `PermissionRequest` hook.
- In reply mode, distribute the AppleScript source and let `install.py` compile `Codex Feishu Submit.app` locally. Do not install a precompiled helper from the archive.
- Reply-mode Accessibility permission must be granted manually to `~/Applications/Codex Feishu Submit.app`. Do not attempt to bypass TCC.
- Restart Codex after hook changes. Verify the enabled features through a real completion notification and, only when enabled, a direct Feishu reply.

## Optional replies

- Add replies to an existing notification installation with `python3.11 scripts/setup.py enable-replies --yes` after showing its preflight paths and obtaining approval.
- Disable replies with `python3.11 scripts/setup.py disable-replies --yes` after approval. This stops the listener, prevents relaunch, clears reply mappings, and leaves notifications installed.
- Existing installations without an `install_mode` value remain reply-enabled when they contain a P2P `chat_id`; do not silently downgrade them during reinstallation.

## Safety boundary

Accept only direct replies from the configured user in the configured P2P chat, and only when the replied-to Feishu message maps to a Codex task. Feishu text is URL-encoded into a Codex deep link; it is never interpreted as shell input. This bridge must not remotely approve Codex permission requests.

Long completion messages are split into ordered Feishu messages without truncation. Every segment ID maps to the same Codex task, so replying to the last segment is the natural continuation path while replies to earlier segments remain safe.
