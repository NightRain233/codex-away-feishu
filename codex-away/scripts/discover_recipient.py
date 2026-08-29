#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def bot_is_ready(lark_cli: Path) -> bool:
    result = subprocess.run(
        [str(lark_cli), "auth", "status", "--json"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "lark-cli auth status failed", file=sys.stderr)
        return False
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    bot = (value.get("identities") or {}).get("bot") or {}
    return bot.get("status") == "ready" and bot.get("available") is True


def current_user_open_id(lark_cli: Path) -> str | None:
    environment = os.environ.copy()
    environment["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    environment["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    result = subprocess.run(
        [str(lark_cli), "auth", "status", "--json", "--verify"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
        env=environment,
    )
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    user = (value.get("identities") or {}).get("user") or {}
    open_id = str(user.get("openId") or "")
    if user.get("status") == "ready" and open_id.startswith("ou_"):
        return open_id
    return None


def discover(lark_cli: Path, timeout_seconds: int) -> dict[str, str]:
    print(
        "Send any direct message to this lark-cli bot from the Feishu account "
        "that should receive Codex notifications.",
        file=sys.stderr,
        flush=True,
    )
    environment = os.environ.copy()
    environment["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    environment["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    child = subprocess.Popen(
        [
            str(lark_cli),
            "event",
            "consume",
            "im.message.receive_v1",
            "--as",
            "bot",
            "--timeout",
            f"{timeout_seconds}s",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
        env=environment,
    )
    deadline = time.monotonic() + timeout_seconds + 10
    try:
        assert child.stdout is not None
        for line in child.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(event, dict)
                and event.get("type") == "im.message.receive_v1"
                and event.get("sender_type") == "user"
                and event.get("chat_type") == "p2p"
                and str(event.get("sender_id") or "").startswith("ou_")
                and str(event.get("chat_id") or "").startswith("oc_")
            ):
                child.terminate()
                return {
                    "recipient_open_id": str(event["sender_id"]),
                    "chat_id": str(event["chat_id"]),
                    "lark_cli": str(lark_cli),
                }
            if time.monotonic() > deadline:
                break
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    raise RuntimeError("no matching direct message was received before timeout")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover the Feishu recipient open_id and P2P chat_id."
    )
    parser.add_argument("--lark-cli")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    lark_value = args.lark_cli or shutil.which("lark-cli")
    if not lark_value:
        print("lark-cli was not found", file=sys.stderr)
        return 1
    lark_cli = Path(lark_value).expanduser().resolve()
    if not bot_is_ready(lark_cli):
        print(
            "The lark-cli bot identity is not ready. Configure a Feishu app first.",
            file=sys.stderr,
        )
        return 1
    try:
        result = discover(lark_cli, max(10, args.timeout))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"discovery failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
