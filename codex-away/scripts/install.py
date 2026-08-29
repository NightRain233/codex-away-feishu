#!/usr/bin/env python3
import argparse
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import tomllib

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
OPEN_ID_RE = re.compile(r"^ou_[A-Za-z0-9]+$")
CHAT_ID_RE = re.compile(r"^oc_[A-Za-z0-9]+$")
LABEL = "com.codex-away.feishu-bridge"
INSTALL_MODES = {"notify", "replies"}


def install_home() -> Path:
    override = os.environ.get("CODEX_AWAY_INSTALL_HOME")
    return Path(override).expanduser().resolve() if override else Path.home()


def write_private(file_path: Path, content: str) -> None:
    file_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = file_path.with_suffix(file_path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, file_path)


def write_executable(file_path: Path, content: str) -> None:
    file_path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    os.chmod(file_path, 0o700)


def command_string(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def backup(file_path: Path) -> Path | None:
    if not file_path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = file_path.with_name(f"{file_path.name}.codex-away-{stamp}.bak")
    shutil.copy2(file_path, backup_path)
    return backup_path


def array_end(lines: list[str], start_index: int) -> int:
    depth = 0
    started = False
    quote = None
    escaped = False
    for index in range(start_index, len(lines)):
        line = lines[index]
        value = line.split("=", 1)[1] if index == start_index else line
        for character in value:
            if escaped:
                escaped = False
                continue
            if quote == '"' and character == "\\":
                escaped = True
                continue
            if quote is not None:
                if character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
            elif character == "#":
                break
            elif character == "[":
                depth += 1
                started = True
            elif character == "]":
                depth -= 1
                if started and depth == 0:
                    return index
    raise ValueError("top-level notify array is incomplete")


def replace_existing_away(
    command: list[str], prefix: list[str]
) -> tuple[list[str], bool]:
    if (
        len(command) >= 3
        and command[1].endswith("/codex-away.py")
        and command[2] == "notify"
    ):
        return prefix + command[3:], True

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
        updated, replaced = replace_existing_away(nested, prefix)
        if replaced:
            result = list(command)
            result[index + 1] = json.dumps(updated, ensure_ascii=False)
            return result, True

    return command, False


def update_notify(config_path: Path, python: Path, away_script: Path) -> None:
    existing_text = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    )
    parsed = tomllib.loads(existing_text) if existing_text.strip() else {}
    existing = parsed.get("notify", [])
    if existing is None:
        existing = []
    if not isinstance(existing, list) or not all(
        isinstance(item, str) for item in existing
    ):
        raise ValueError("config.toml top-level notify must be an array of strings")

    prefix = [str(python), str(away_script), "notify"]
    replacement_command, replaced = replace_existing_away(existing, prefix)
    if replaced:
        wrapped = replacement_command
    elif any("codex-away.py" in item for item in existing):
        raise ValueError(
            "an existing nested codex-away notify wrapper was found; remove it before reinstalling"
        )
    else:
        wrapped = prefix + existing
    replacement = "notify = " + json.dumps(wrapped, ensure_ascii=False) + "\n"

    lines = existing_text.splitlines(keepends=True)
    notify_index = None
    first_table = len(lines)
    for index, line in enumerate(lines):
        if re.match(r"^\s*\[", line):
            first_table = index
            break
        if re.match(r"^\s*notify\s*=", line):
            notify_index = index
    if notify_index is None:
        if first_table and lines[first_table - 1].strip():
            replacement += "\n"
        lines[first_table:first_table] = [replacement]
    else:
        end_index = array_end(lines, notify_index)
        lines[notify_index : end_index + 1] = [replacement]

    updated = "".join(lines)
    tomllib.loads(updated)
    backup(config_path)
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_path.write_text(updated, encoding="utf-8")


def update_permission_hook(hooks_path: Path, python: Path, away_script: Path) -> None:
    if hooks_path.exists():
        value = json.loads(hooks_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("hooks.json must contain a JSON object")
    else:
        value = {"description": "User-level Codex hooks.", "hooks": {}}
    hooks = value.setdefault("hooks", {})
    permission_groups = hooks.setdefault("PermissionRequest", [])
    if not isinstance(permission_groups, list):
        raise TypeError("hooks.json PermissionRequest must be an array")
    command = command_string([str(python), str(away_script), "permission"])
    for group in permission_groups:
        for hook in group.get("hooks", []) if isinstance(group, dict) else []:
            if isinstance(hook, dict) and "codex-away.py permission" in str(
                hook.get("command", "")
            ):
                hook.update(
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 35,
                        "statusMessage": "Sending Codex away-mode permission notification",
                    }
                )
                break
        else:
            continue
        break
    else:
        permission_groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 35,
                        "statusMessage": "Sending Codex away-mode permission notification",
                    }
                ]
            }
        )
    backup(hooks_path)
    write_private(hooks_path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def preflight_codex_config(codex_home: Path, python: Path, away_script: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-away-preflight-") as temporary_dir:
        temporary_codex_home = Path(temporary_dir)
        for name in ("config.toml", "hooks.json"):
            source = codex_home / name
            if source.exists():
                shutil.copy2(source, temporary_codex_home / name)
        update_notify(temporary_codex_home / "config.toml", python, away_script)
        update_permission_hook(temporary_codex_home / "hooks.json", python, away_script)


def launch_agent(home: Path, python: Path, bridge_script: Path) -> dict:
    bridge_home = home / ".codex" / "codex-feishu-bridge"
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(bridge_script), "listen"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "EnvironmentVariables": {
            "HOME": str(home),
            "PATH": f"{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(bridge_home / "launchd.stdout.log"),
        "StandardErrorPath": str(bridge_home / "launchd.stderr.log"),
    }


def run_launchctl(plist_path: Path) -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["/bin/launchctl", "bootout", domain, str(plist_path)],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")


def validate_args(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if sys.platform != "darwin":
        raise ValueError("codex-away currently supports macOS only")
    if args.mode not in INSTALL_MODES:
        raise ValueError("installation mode must be notify or replies")
    if not OPEN_ID_RE.fullmatch(args.recipient_open_id):
        raise ValueError("recipient open_id must start with ou_")
    if args.mode == "replies" and not CHAT_ID_RE.fullmatch(args.chat_id or ""):
        raise ValueError("chat_id must start with oc_")
    python = Path(args.python or sys.executable).expanduser().resolve()
    lark_value = args.lark_cli or shutil.which("lark-cli")
    if not lark_value:
        raise ValueError("lark-cli was not found; install and configure it first")
    lark_cli = Path(lark_value).expanduser().resolve()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError(f"Python is not executable: {python}")
    if not lark_cli.is_file() or not os.access(lark_cli, os.X_OK):
        raise ValueError(f"lark-cli is not executable: {lark_cli}")
    return install_home(), python, lark_cli


def stop_reply_service(home: Path, skip_launchctl: bool) -> None:
    plist_path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if not skip_launchctl and sys.platform == "darwin":
        subprocess.run(
            [
                "/bin/launchctl",
                "bootout",
                f"gui/{os.getuid()}",
                str(plist_path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    if plist_path.exists():
        disabled_path = (
            home / ".codex" / "codex-feishu-bridge" / "disabled-launch-agent.plist"
        )
        disabled_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.replace(plist_path, disabled_path)


def update_reply_mode(home: Path, enabled: bool) -> None:
    away_home = home / ".codex" / "codex-away"
    config_path = away_home / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            config = {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        config = {}
    config["install_mode"] = "replies" if enabled else "notify"
    write_private(config_path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")

    state_path = away_home / "state.json"
    if not enabled and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = None
        if isinstance(state, dict):
            state["reply_targets"] = {}
            state["reply_once_threads"] = []
            write_private(
                state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n"
            )


def disable_replies(home: Path, skip_launchctl: bool) -> None:
    stop_reply_service(home, skip_launchctl)
    update_reply_mode(home, False)


def install(args: argparse.Namespace) -> None:
    home, python, lark_cli = validate_args(args)
    replies_enabled = args.mode == "replies"
    codex_home = home / ".codex"
    away_home = codex_home / "codex-away"
    bridge_home = codex_home / "codex-feishu-bridge"
    bin_home = home / ".local" / "bin"
    launch_agents = home / "Library" / "LaunchAgents"
    applications = home / "Applications"
    away_script = away_home / "codex-away.py"
    bridge_script = bridge_home / "codex-feishu-bridge.py"
    helper_source = bridge_home / "Codex Feishu Submit.applescript"
    helper_app = applications / "Codex Feishu Submit.app"
    plist_path = launch_agents / f"{LABEL}.plist"

    if not args.skip_codex_config:
        preflight_codex_config(codex_home, python, away_script)

    away_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(ASSETS / "codex-away.py", away_script)
    os.chmod(away_script, 0o700)

    config = {
        "recipient_open_id": args.recipient_open_id,
        "lark_cli": str(lark_cli),
        "install_mode": args.mode,
    }
    if args.chat_id:
        config["chat_id"] = args.chat_id
    write_private(away_home / "config.json", json.dumps(config, indent=2) + "\n")
    write_executable(
        bin_home / "codex-away",
        f'#!/bin/sh\nexec {shlex.quote(str(python))} {shlex.quote(str(away_script))} "$@"\n',
    )
    if replies_enabled:
        bridge_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copy2(ASSETS / "codex-feishu-bridge.py", bridge_script)
        shutil.copy2(ASSETS / "Codex Feishu Submit.applescript", helper_source)
        os.chmod(bridge_script, 0o700)
        os.chmod(helper_source, 0o600)
        write_executable(
            bin_home / "codex-feishu-bridge",
            f'#!/bin/sh\nexec {shlex.quote(str(python))} {shlex.quote(str(bridge_script))} "$@"\n',
        )
        if not helper_app.exists() or args.recompile_helper:
            applications.mkdir(mode=0o755, parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    "/usr/bin/osacompile",
                    "-x",
                    "-o",
                    str(helper_app),
                    str(helper_source),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "osacompile failed")

        launch_agents.mkdir(mode=0o755, parents=True, exist_ok=True)
        with plist_path.open("wb") as handle:
            plistlib.dump(
                launch_agent(home, python, bridge_script), handle, sort_keys=False
            )
    else:
        disable_replies(home, args.skip_launchctl)

    if not args.skip_codex_config:
        update_notify(codex_home / "config.toml", python, away_script)
        update_permission_hook(codex_home / "hooks.json", python, away_script)
    if replies_enabled and not args.skip_launchctl:
        run_launchctl(plist_path)

    print(f"codex-away installed (mode={args.mode})")
    if replies_enabled:
        print(f"helper_app={helper_app}")
        print(f"launch_agent={plist_path}")
        print(
            "Restart Codex after granting Accessibility permission to the helper app."
        )
    else:
        print("Restart Codex to load the notification hooks.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the codex-away Feishu bridge."
    )
    parser.add_argument("--recipient-open-id", required=True)
    parser.add_argument("--chat-id")
    parser.add_argument("--mode", choices=sorted(INSTALL_MODES), default="notify")
    parser.add_argument("--lark-cli")
    parser.add_argument("--python")
    parser.add_argument("--skip-codex-config", action="store_true")
    parser.add_argument("--skip-launchctl", action="store_true")
    parser.add_argument("--recompile-helper", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        parser.error(
            "installation changes local Codex and launchd configuration; pass --yes after approval"
        )
    try:
        install(args)
    except (
        OSError,
        TypeError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(f"install failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
