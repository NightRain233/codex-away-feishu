#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import tomllib
from install import LABEL, array_end, backup


def install_home(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    override = os.environ.get("CODEX_AWAY_INSTALL_HOME")
    return Path(override).expanduser().resolve() if override else Path.home()


def unwrap_notify(config_path: Path) -> None:
    if not config_path.exists():
        return
    text = config_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    notify = parsed.get("notify")
    if not isinstance(notify, list):
        return
    updated_notify, changed = unwrap_existing_away(notify)
    if not changed:
        return
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if re.match(r"^\s*\[", line):
            break
        if re.match(r"^\s*notify\s*=", line):
            end_index = array_end(lines, index)
            replacement = (
                "notify = " + json.dumps(updated_notify, ensure_ascii=False) + "\n"
                if updated_notify
                else ""
            )
            lines[index : end_index + 1] = [replacement]
            updated = "".join(lines)
            tomllib.loads(updated)
            backup(config_path)
            config_path.write_text(updated, encoding="utf-8")
            return


def unwrap_existing_away(command: list[str]) -> tuple[list[str], bool]:
    if (
        len(command) >= 3
        and command[1].endswith("/codex-away.py")
        and command[2] == "notify"
    ):
        return command[3:], True

    for index, item in enumerate(command[:-1]):
        if item != "--previous-notify":
            continue
        try:
            nested = json.loads(command[index + 1])
        except json.JSONDecodeError:
            continue
        if not isinstance(nested, list) or not all(
            isinstance(value, str) for value in nested
        ):
            continue
        updated, changed = unwrap_existing_away(nested)
        if changed:
            result = list(command)
            result[index + 1] = json.dumps(updated, ensure_ascii=False)
            return result, True
    return command, False


def remove_permission_hook(hooks_path: Path) -> None:
    if not hooks_path.exists():
        return
    value = json.loads(hooks_path.read_text(encoding="utf-8"))
    hooks = value.get("hooks") if isinstance(value, dict) else None
    groups = hooks.get("PermissionRequest") if isinstance(hooks, dict) else None
    if not isinstance(groups, list):
        return
    changed = False
    retained_groups = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            retained_groups.append(group)
            continue
        retained_hooks = [
            hook
            for hook in group["hooks"]
            if not (
                isinstance(hook, dict)
                and "codex-away.py permission" in str(hook.get("command", ""))
            )
        ]
        changed = changed or len(retained_hooks) != len(group["hooks"])
        if retained_hooks:
            retained_groups.append({**group, "hooks": retained_hooks})
    if not changed:
        return
    hooks["PermissionRequest"] = retained_groups
    backup(hooks_path)
    hooks_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def move_to_trash(targets: list[Path], home: Path) -> Path:
    trash_root = home / ".Trash" / f"codex-away-{time.strftime('%Y%m%d-%H%M%S')}"
    trash_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for target in targets:
        if target.exists() or target.is_symlink():
            destination = trash_root / target.name
            if destination.exists():
                destination = trash_root / f"{target.parent.name}-{target.name}"
            shutil.move(str(target), str(destination))
    return trash_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Uninstall codex-away from this Mac.")
    parser.add_argument("--home")
    parser.add_argument("--skip-launchctl", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        parser.error(
            "uninstall changes local Codex configuration; pass --yes after approval"
        )
    home = install_home(args.home)
    codex_home = home / ".codex"
    plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"

    if not args.skip_launchctl and sys.platform == "darwin":
        subprocess.run(
            ["/bin/launchctl", "bootout", f"gui/{os.getuid()}", str(plist_path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    try:
        unwrap_notify(codex_home / "config.toml")
        remove_permission_hook(codex_home / "hooks.json")
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(f"uninstall stopped before moving files: {error}", file=sys.stderr)
        return 1

    targets = [
        codex_home / "codex-away",
        codex_home / "codex-feishu-bridge",
        home / ".local" / "bin" / "codex-away",
        home / ".local" / "bin" / "codex-feishu-bridge",
        plist_path,
        home / "Applications" / "Codex Feishu Submit.app",
    ]
    trash_root = move_to_trash(targets, home)
    print(f"codex-away moved to {trash_root}")
    print("Restart Codex to finish uninstalling the hooks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
