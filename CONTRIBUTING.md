# Contributing

Thanks for helping improve Codex Away Feishu. Keep changes focused on the macOS Codex Desktop and Feishu workflow.

## Before opening an issue

Please include:

- macOS version and Codex Desktop version;
- whether `notify` or `replies` mode is installed;
- the exact setup or diagnostic step that failed;
- redacted output from `python3.11 scripts/setup.py doctor`;
- whether the failure happens while the Mac is locked, awake, or unlocked.

Never include Feishu app secrets, access tokens, `open_id`, `chat_id`, private paths, or full logs containing message content.

## Local checks

From `codex-away/`:

```bash
ruff check .
python3.11 -m unittest discover -s tests
python3 /path/to/quick_validate.py .
```

The real Feishu round trip and macOS Accessibility behavior require a local Mac and must be described separately from automated test results.

## Pull requests

- Explain the user-visible behavior and permission impact.
- Add focused tests for installer, runtime, or routing changes.
- Keep the archive free of credentials, logs, caches, and precompiled Accessibility artifacts.
- Update `CHANGELOG.md` for user-visible changes.
