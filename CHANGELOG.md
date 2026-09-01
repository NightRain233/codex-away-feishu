# Changelog

## Unreleased

- Ignore completion events from persistent Codex subagent threads while preserving notifications for their parent desktop tasks.

## 0.1.0 - 2026-08-29

Initial public release.

- Feishu completion and permission-waiting notifications for Codex Desktop.
- Optional reply bridge with task routing, LaunchAgent, and locally compiled AppleScript helper.
- Notification-only installation as the default, with incremental reply enable/disable commands.
- Lossless UTF-8-safe splitting for long Feishu messages; every segment maps to the same task.
- Guided setup, diagnostics, configuration backups, tests, and downloadable macOS Skill archive.
