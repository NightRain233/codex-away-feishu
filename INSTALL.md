# Install Codex Away

1. Extract the `codex-away` folder into `~/.codex/skills/`.
2. Restart Codex desktop.
3. Tell Codex: `安装 codex-away` or `Use $codex-away to install codex-away.`

Codex runs the terminal workflow and defaults to notification-only installation. You approve prerequisite installation and local changes, complete the Feishu bot setup, and restart Codex when prompted. If your existing `lark-cli` user login exposes your `open_id`, no direct discovery message is needed. You never need to find or copy Feishu IDs.

Notification-only mode sends completion and permission-waiting messages without installing a background reply listener or requesting macOS Accessibility permission.

To reply from Feishu and continue the same Codex desktop task, ask Codex to enable codex-away replies. This optional mode adds a LaunchAgent and locally compiles the included AppleScript source. You then grant Accessibility permission to that local App. The archive never ships a precompiled helper.
