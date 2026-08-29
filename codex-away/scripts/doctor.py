#!/usr/bin/env python3
import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

import tomllib

LABEL = "com.codex-away.feishu-bridge"


def check(condition: bool, label: str, detail: str = "") -> bool:
    marker = "OK" if condition else "FAIL"
    suffix = f": {detail}" if detail else ""
    print(f"[{marker}] {label}{suffix}")
    return condition


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a codex-away installation.")
    parser.add_argument("--home")
    parser.add_argument("--skip-launchctl", action="store_true")
    parser.add_argument("--mode", choices=("notify", "replies"))
    args = parser.parse_args()
    home = Path(args.home).expanduser().resolve() if args.home else Path.home()
    codex_home = home / ".codex"
    away_home = codex_home / "codex-away"
    bridge_home = codex_home / "codex-feishu-bridge"
    helper = home / "Applications" / "Codex Feishu Submit.app"
    plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    results = []

    config_path = away_home / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        config = {}
    recipient = str(config.get("recipient_open_id") or "")
    chat_id = str(config.get("chat_id") or "")
    configured_mode = config.get("install_mode")
    if configured_mode not in {"notify", "replies"}:
        configured_mode = "replies" if chat_id else "notify"
    mode = args.mode or configured_mode
    replies_enabled = mode == "replies"
    print(f"codex-away doctor (mode={mode})")
    results.append(check(configured_mode == mode, "installation mode", mode))
    lark_cli = Path(str(config.get("lark_cli") or ""))
    results.append(
        check(bool(re.fullmatch(r"ou_[A-Za-z0-9]+", recipient)), "recipient open_id")
    )
    if replies_enabled:
        results.append(
            check(bool(re.fullmatch(r"oc_[A-Za-z0-9]+", chat_id)), "P2P chat_id")
        )
    results.append(
        check(
            lark_cli.is_file() and os.access(lark_cli, os.X_OK),
            "lark-cli",
            str(lark_cli),
        )
    )

    if lark_cli.is_file():
        auth = subprocess.run(
            [str(lark_cli), "auth", "status", "--json"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        try:
            bot = (json.loads(auth.stdout).get("identities") or {}).get("bot") or {}
        except json.JSONDecodeError:
            bot = {}
        results.append(
            check(
                auth.returncode == 0 and bot.get("status") == "ready",
                "lark-cli bot identity",
            )
        )

    results.append(
        check((away_home / "codex-away.py").is_file(), "notification runtime")
    )
    if replies_enabled:
        results.append(
            check(
                (bridge_home / "codex-feishu-bridge.py").is_file(),
                "reply bridge runtime",
            )
        )
        results.append(check(helper.is_dir(), "Accessibility helper app", str(helper)))

        try:
            plist = plistlib.loads(plist_path.read_bytes())
        except (FileNotFoundError, plistlib.InvalidFileException, OSError):
            plist = {}
        results.append(check(plist.get("Label") == LABEL, "LaunchAgent plist"))

    try:
        codex_config = tomllib.loads(
            (codex_home / "config.toml").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        codex_config = {}
    notify = codex_config.get("notify") or []
    results.append(
        check(
            isinstance(notify, list)
            and any("codex-away.py" in str(item) for item in notify),
            "Codex completion notify hook",
        )
    )

    try:
        hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        hooks = {}
    permission_text = json.dumps(
        (hooks.get("hooks") or {}).get("PermissionRequest") or []
    )
    results.append(
        check("codex-away.py permission" in permission_text, "Codex permission hook")
    )

    if replies_enabled and not args.skip_launchctl:
        bridge_log = bridge_home / "bridge.log"
        log_text = bridge_log.read_text(encoding="utf-8") if bridge_log.exists() else ""
        results.append(
            check("listener ready" in log_text, "Feishu event listener readiness")
        )

    if replies_enabled and not args.skip_launchctl and sys.platform == "darwin":
        service = subprocess.run(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
        results.append(
            check(
                service.returncode == 0 and "state = running" in service.stdout,
                "LaunchAgent running",
            )
        )

    if replies_enabled:
        print("Accessibility permission must be confirmed manually in System Settings.")
    else:
        print("Reply bridge checks skipped in notification-only mode.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
