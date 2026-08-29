#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import discover_recipient
import install as installer

SCRIPT_DIR = Path(__file__).resolve().parent


def target_python(value: str | None) -> Path:
    return Path(value or sys.executable).expanduser().resolve()


def target_lark_cli(value: str | None) -> Path | None:
    resolved = value or shutil.which("lark-cli")
    return Path(resolved).expanduser().resolve() if resolved else None


def executable_python_311(python: Path) -> bool:
    if not python.is_file() or not os.access(python, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import sys; raise SystemExit(sys.version_info < (3, 11))",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def find_codex_app(home: Path) -> Path | None:
    configured = os.environ.get("CODEX_AWAY_CODEX_APP")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        return candidate if candidate.is_dir() else None
    candidates = [
        Path("/Applications/Codex.app"),
        Path("/Applications/ChatGPT.app"),
        home / "Applications" / "Codex.app",
        home / "Applications" / "ChatGPT.app",
    ]
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def installation_paths(home: Path, mode: str = "notify") -> list[str]:
    paths = [
        str(home / ".codex" / "codex-away"),
        str(home / ".local" / "bin" / "codex-away"),
        str(home / ".codex" / "config.toml"),
        str(home / ".codex" / "hooks.json"),
    ]
    if mode == "replies":
        paths[1:1] = [
            str(home / ".codex" / "codex-feishu-bridge"),
            str(home / ".local" / "bin" / "codex-feishu-bridge"),
            str(home / "Applications" / "Codex Feishu Submit.app"),
            str(
                home / "Library" / "LaunchAgents" / "com.codex-away.feishu-bridge.plist"
            ),
        ]
    return paths


def installed_mode(home: Path) -> str | None:
    config_path = home / ".codex" / "codex-away" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(config, dict):
        return None
    mode = config.get("install_mode")
    if mode in installer.INSTALL_MODES:
        return str(mode)
    if config.get("chat_id"):
        return "replies"
    return "notify"


def selected_mode(args: argparse.Namespace, home: Path) -> str:
    requested = getattr(args, "mode", None)
    return requested or installed_mode(home) or "notify"


def configured_recipient(home: Path, mode: str) -> dict[str, str | None] | None:
    config_path = home / ".codex" / "codex-away" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(config, dict):
        return None
    recipient_open_id = str(config.get("recipient_open_id") or "")
    chat_id = str(config.get("chat_id") or "")
    if not installer.OPEN_ID_RE.fullmatch(recipient_open_id):
        return None
    if mode == "replies" and not installer.CHAT_ID_RE.fullmatch(chat_id):
        return None
    return {
        "recipient_open_id": recipient_open_id,
        "chat_id": chat_id or None,
    }


def collect_preflight(args: argparse.Namespace) -> dict:
    home = installer.install_home()
    mode = selected_mode(args, home)
    python = target_python(args.python)
    lark_cli = target_lark_cli(args.lark_cli)
    codex_app = find_codex_app(home)
    platform_ok = sys.platform == "darwin"
    python_ok = executable_python_311(python)
    lark_cli_ok = bool(lark_cli and lark_cli.is_file() and os.access(lark_cli, os.X_OK))
    bot_ready = bool(lark_cli_ok and discover_recipient.bot_is_ready(lark_cli))
    configured = configured_recipient(home, mode)
    user_open_id = (
        discover_recipient.current_user_open_id(lark_cli)
        if lark_cli_ok and not configured and mode == "notify"
        else None
    )
    discovery = (
        "existing_config"
        if configured
        else "authenticated_user"
        if mode == "notify" and user_open_id
        else "direct_message"
    )
    config_ok = False
    config_error = None
    if platform_ok and python_ok:
        try:
            installer.preflight_codex_config(
                home / ".codex",
                python,
                home / ".codex" / "codex-away" / "codex-away.py",
            )
            config_ok = True
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            config_error = str(error)

    blockers = []
    if not platform_ok:
        blockers.append("codex-away currently supports macOS only")
    if not codex_app:
        blockers.append("Codex or ChatGPT desktop app was not found")
    if not python_ok:
        blockers.append("Python 3.11 or newer is required")
    if not lark_cli_ok:
        blockers.append("lark-cli is not installed or executable")
    elif not bot_ready:
        blockers.append("lark-cli bot identity is not ready")
    if not config_ok:
        blockers.append(config_error or "Codex configuration preflight failed")

    return {
        "ready": not blockers,
        "blockers": blockers,
        "home": str(home),
        "python": str(python),
        "python_ok": python_ok,
        "lark_cli": str(lark_cli) if lark_cli else None,
        "lark_cli_ok": lark_cli_ok,
        "bot_ready": bot_ready,
        "recipient_discovery": discovery,
        "codex_app": str(codex_app) if codex_app else None,
        "codex_config_ok": config_ok,
        "mode": mode,
        "changes": installation_paths(home, mode),
        "manual_steps": (
            (
                ["send one direct message to the configured Feishu bot"]
                if discovery == "direct_message"
                else []
            )
            + (
                ["grant Accessibility permission to Codex Feishu Submit.app"]
                if mode == "replies"
                else []
            )
            + ["restart Codex desktop after installation"]
        ),
    }


def print_preflight(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("codex-away setup preflight")
    print(f"mode: {result['mode']}")
    print(f"ready: {'yes' if result['ready'] else 'no'}")
    for blocker in result["blockers"]:
        print(f"BLOCKED: {blocker}")
    print("Files and directories changed after approval:")
    for file_path in result["changes"]:
        print(f"- {file_path}")


def install_bridge(args: argparse.Namespace) -> int:
    if not args.yes:
        print(
            "installation requires approval after reviewing setup.py preflight output",
            file=sys.stderr,
        )
        return 10
    result = collect_preflight(args)
    if not result["ready"]:
        print_preflight(result, args.json)
        return 2

    python = target_python(args.python)
    lark_cli = target_lark_cli(args.lark_cli)
    mode = result["mode"]
    assert lark_cli is not None
    recipient = configured_recipient(installer.install_home(), mode)
    if not recipient:
        recipient_open_id = (
            discover_recipient.current_user_open_id(lark_cli)
            if mode == "notify"
            else None
        )
        if recipient_open_id:
            recipient = {
                "recipient_open_id": recipient_open_id,
                "chat_id": None,
            }
        else:
            print(
                "Send one direct text message to the configured Feishu bot now. "
                "Waiting for the matching private chat...",
                file=sys.stderr,
                flush=True,
            )
            recipient = discover_recipient.discover(lark_cli, max(10, args.timeout))
    install_args = argparse.Namespace(
        recipient_open_id=recipient["recipient_open_id"],
        chat_id=recipient["chat_id"],
        mode=mode,
        lark_cli=str(lark_cli),
        python=str(python),
        skip_codex_config=args.skip_codex_config,
        skip_launchctl=args.skip_launchctl,
        recompile_helper=args.recompile_helper,
        yes=True,
    )
    installer.install(install_args)
    return 0


def enable_replies(args: argparse.Namespace) -> int:
    if not args.yes:
        print(
            "enabling replies requires approval after reviewing preflight output",
            file=sys.stderr,
        )
        return 10
    args.mode = "replies"
    result = collect_preflight(args)
    if not result["ready"]:
        print_preflight(result, args.json)
        return 2

    home = installer.install_home()
    python = target_python(args.python)
    lark_cli = target_lark_cli(args.lark_cli)
    assert lark_cli is not None
    config_path = home / ".codex" / "codex-away" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        config = {}
    recipient_open_id = str(config.get("recipient_open_id") or "")
    chat_id = str(config.get("chat_id") or "")
    if not installer.OPEN_ID_RE.fullmatch(
        recipient_open_id
    ) or not installer.CHAT_ID_RE.fullmatch(chat_id):
        print(
            "Send one direct text message to the configured Feishu bot now. "
            "Waiting for the matching private chat...",
            file=sys.stderr,
            flush=True,
        )
        recipient = discover_recipient.discover(lark_cli, max(10, args.timeout))
        recipient_open_id = recipient["recipient_open_id"]
        chat_id = recipient["chat_id"]

    install_args = argparse.Namespace(
        recipient_open_id=recipient_open_id,
        chat_id=chat_id,
        mode="replies",
        lark_cli=str(lark_cli),
        python=str(python),
        skip_codex_config=args.skip_codex_config,
        skip_launchctl=args.skip_launchctl,
        recompile_helper=args.recompile_helper,
        yes=True,
    )
    installer.install(install_args)
    return 0


def disable_replies(args: argparse.Namespace) -> int:
    if not args.yes:
        print(
            "disabling replies requires approval because it changes a LaunchAgent",
            file=sys.stderr,
        )
        return 10
    installer.disable_replies(installer.install_home(), args.skip_launchctl)
    print("codex-away replies disabled; notifications remain installed")
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    python = target_python(args.python)
    command = [str(python), str(SCRIPT_DIR / "doctor.py")]
    if args.home:
        command.extend(["--home", args.home])
    if args.skip_launchctl:
        command.append("--skip-launchctl")
    if args.mode:
        command.extend(["--mode", args.mode])
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guided setup for the codex-away Feishu bridge."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="run read-only checks")
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--lark-cli")
    preflight.add_argument("--python")
    preflight.add_argument("--mode", choices=sorted(installer.INSTALL_MODES))

    install = subparsers.add_parser(
        "install", help="discover the recipient and install after approval"
    )
    install.add_argument("--yes", action="store_true")
    install.add_argument("--json", action="store_true")
    install.add_argument("--timeout", type=int, default=180)
    install.add_argument("--lark-cli")
    install.add_argument("--python")
    install.add_argument("--skip-codex-config", action="store_true")
    install.add_argument("--skip-launchctl", action="store_true")
    install.add_argument("--recompile-helper", action="store_true")
    install.add_argument("--mode", choices=sorted(installer.INSTALL_MODES))

    enable = subparsers.add_parser(
        "enable-replies", help="add the optional Feishu reply bridge"
    )
    enable.add_argument("--yes", action="store_true")
    enable.add_argument("--json", action="store_true")
    enable.add_argument("--timeout", type=int, default=180)
    enable.add_argument("--lark-cli")
    enable.add_argument("--python")
    enable.add_argument("--skip-codex-config", action="store_true")
    enable.add_argument("--skip-launchctl", action="store_true")
    enable.add_argument("--recompile-helper", action="store_true")

    disable = subparsers.add_parser(
        "disable-replies", help="stop the reply bridge but keep notifications"
    )
    disable.add_argument("--yes", action="store_true")
    disable.add_argument("--skip-launchctl", action="store_true")

    doctor = subparsers.add_parser("doctor", help="check the installed bridge")
    doctor.add_argument("--home")
    doctor.add_argument("--python")
    doctor.add_argument("--skip-launchctl", action="store_true")
    doctor.add_argument("--mode", choices=sorted(installer.INSTALL_MODES))

    args = parser.parse_args()
    try:
        if args.command == "preflight":
            result = collect_preflight(args)
            print_preflight(result, args.json)
            return 0 if result["ready"] else 2
        if args.command == "install":
            return install_bridge(args)
        if args.command == "enable-replies":
            return enable_replies(args)
        if args.command == "disable-replies":
            return disable_replies(args)
        if args.command == "doctor":
            return run_doctor(args)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"setup failed: {error}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
