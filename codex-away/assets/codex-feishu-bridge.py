#!/usr/bin/env python3
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

DEFAULT_HOME = Path.home() / ".codex" / "codex-feishu-bridge"
DEFAULT_AWAY_HOME = Path.home() / ".codex" / "codex-away"
MESSAGE_LEASE_SECONDS = 120


def bridge_home() -> Path:
    return Path(os.environ.get("CODEX_FEISHU_BRIDGE_HOME", str(DEFAULT_HOME)))


def away_home() -> Path:
    return Path(os.environ.get("CODEX_AWAY_HOME", str(DEFAULT_AWAY_HOME)))


def load_config() -> dict[str, Any]:
    return load_json(away_home() / "config.json", {})


def log(message: str) -> None:
    bridge_home().mkdir(mode=0o700, parents=True, exist_ok=True)
    with (bridge_home() / "bridge.log").open("a", encoding="utf-8") as handle:
        handle.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + message + "\n")


def id_prefix(value: str) -> str:
    return value[:8]


class FileLock:
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file

    def __enter__(self):
        self.lock_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.handle = self.lock_file.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def load_json(file_path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(file_path: Path, value: dict[str, Any]) -> None:
    file_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = file_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, file_path)


def target_for(reply_to: str) -> dict[str, str] | None:
    with FileLock(away_home() / "state.lock"):
        state = load_json(away_home() / "state.json", {})
        target = (state.get("reply_targets") or {}).get(reply_to)
    if not isinstance(target, dict) or not target.get("thread_id"):
        return None
    return {
        "thread_id": str(target["thread_id"]),
        "cwd": str(target.get("cwd") or Path.home()),
    }


def authorized_event(event: dict[str, Any]) -> bool:
    config = load_config()
    sender = os.environ.get("CODEX_FEISHU_BRIDGE_SENDER") or config.get(
        "recipient_open_id"
    )
    chat = os.environ.get("CODEX_FEISHU_BRIDGE_CHAT") or config.get("chat_id")
    return (
        event.get("type") == "im.message.receive_v1"
        and bool(sender)
        and event.get("sender_id") == sender
        and event.get("sender_type") == "user"
        and bool(chat)
        and event.get("chat_id") == chat
        and event.get("chat_type") == "p2p"
        and event.get("message_type") in {"text", "post"}
        and bool(str(event.get("content") or "").strip())
        and bool(event.get("message_id"))
        and bool(event.get("reply_to"))
    )


def claim_message(message_id: str, now: int | None = None) -> bool:
    current_time = int(time.time()) if now is None else now
    state_file = bridge_home() / "state.json"
    with FileLock(bridge_home() / "state.lock"):
        state = load_json(state_file, {"messages": {}})
        messages = dict(state.get("messages") or {})
        existing = messages.get(message_id, {})
        if existing.get("state") == "completed":
            return False
        if (
            existing.get("state") == "running"
            and int(existing.get("lease_until") or 0) > current_time
        ):
            return False
        messages[message_id] = {
            "state": "running",
            "updated_at": current_time,
            "lease_until": current_time + MESSAGE_LEASE_SECONDS,
            "attempt_count": int(existing.get("attempt_count") or 0) + 1,
        }
        state["messages"] = dict(list(messages.items())[-200:])
        save_json(state_file, state)
    return True


def finish_message(message_id: str, state_name: str, detail: str = "") -> None:
    state_file = bridge_home() / "state.json"
    with FileLock(bridge_home() / "state.lock"):
        state = load_json(state_file, {"messages": {}})
        messages = dict(state.get("messages") or {})
        messages[message_id] = {
            "state": state_name,
            "updated_at": int(time.time()),
            "lease_until": 0,
            "attempt_count": int(messages.get(message_id, {}).get("attempt_count") or 0),
            "detail": detail[:500],
        }
        state["messages"] = dict(list(messages.items())[-200:])
        save_json(state_file, state)


def submit_to_desktop(thread_id: str, prompt: str) -> str | None:
    open_command = os.environ.get("CODEX_FEISHU_BRIDGE_OPEN", "/usr/bin/open")
    submit_command = os.environ.get(
        "CODEX_FEISHU_BRIDGE_SUBMIT",
        str(
            Path.home()
            / "Applications"
            / "Codex Feishu Submit.app"
            / "Contents"
            / "MacOS"
            / "applet"
        ),
    )
    query = urlencode({"prompt": prompt})
    deep_link = f"codex://threads/{quote(thread_id, safe='')}?{query}"
    try:
        open_result = subprocess.run(
            [open_command, "-b", "com.openai.codex", deep_link],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        if open_result.returncode != 0:
            return (
                open_result.stderr
                or open_result.stdout
                or "could not open Codex deep link"
            )
        submit_result = subprocess.run(
            [submit_command],
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    if submit_result.returncode != 0:
        return (
            submit_result.stderr
            or submit_result.stdout
            or "could not submit Codex prompt"
        )
    return None


def dispatch(event: dict[str, Any]) -> bool:
    if not authorized_event(event):
        return False
    target = target_for(str(event["reply_to"]))
    if not target:
        return False
    message_id = str(event["message_id"])
    if not claim_message(message_id):
        return False

    thread_id = target["thread_id"]
    away_command = os.environ.get(
        "CODEX_FEISHU_BRIDGE_AWAY", str(Path.home() / ".local" / "bin" / "codex-away")
    )
    prompt = "[来自飞书回复]\n" + str(event["content"]).strip()[:8000]

    try:
        arm_result = subprocess.run(
            [away_command, "arm-reply", "--thread", thread_id],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        finish_message(message_id, "failed", str(error))
        log(
            f"could not arm reply notification for thread={id_prefix(thread_id)}: {error}"
        )
        return False
    if arm_result.returncode != 0:
        finish_message(message_id, "failed", "could not arm completion notification")
        return False

    def disarm() -> None:
        try:
            result = subprocess.run(
                [away_command, "disarm-reply", "--thread", thread_id],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                log(
                    "could not disarm reply notification for "
                    f"thread={id_prefix(thread_id)}: {result.stderr[:500]}"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            log(
                "could not disarm reply notification for "
                f"thread={id_prefix(thread_id)}: {error}"
            )

    error_detail = submit_to_desktop(thread_id, prompt)
    if error_detail is not None:
        disarm()
        finish_message(message_id, "failed", error_detail)
        log(
            f"desktop submit failed message={id_prefix(message_id)} "
            f"thread={id_prefix(thread_id)}: "
            f"{error_detail[:500]}"
        )
        return False

    finish_message(message_id, "completed")
    log(
        f"desktop submit completed message={id_prefix(message_id)} "
        f"thread={id_prefix(thread_id)}"
    )
    return True


def listen() -> int:
    lark_command = os.environ.get("CODEX_FEISHU_BRIDGE_LARK") or str(
        load_config().get("lark_cli") or Path.home() / ".local" / "bin" / "lark-cli"
    )
    environment = os.environ.copy()
    environment["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    environment["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    child = subprocess.Popen(
        [lark_command, "event", "consume", "im.message.receive_v1", "--as", "bot"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=environment,
    )
    ready = threading.Event()

    def drain_stderr() -> None:
        assert child.stderr is not None
        for line in child.stderr:
            clean = line.rstrip()
            log("lark: " + clean)
            if "[event] ready event_key=im.message.receive_v1" in clean:
                ready.set()

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    def stop_child(signum, frame) -> None:
        if child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)
    if not ready.wait(30):
        log("listener did not become ready within 30 seconds")
        child.terminate()
        return 1

    log("listener ready")
    assert child.stdout is not None
    for line in child.stdout:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            log("ignored invalid event JSON")
            continue
        if isinstance(event, dict):
            dispatch(event)
    return child.wait()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge Feishu replies into mapped Codex threads."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    event_parser = subparsers.add_parser("process-event")
    event_parser.add_argument("event_json")
    subparsers.add_parser("listen")
    args = parser.parse_args()
    if args.command == "process-event":
        try:
            event = json.loads(args.event_json)
        except json.JSONDecodeError:
            return 2
        if isinstance(event, dict):
            dispatch(event)
        return 0
    if args.command == "listen":
        return listen()
    return 2


if __name__ == "__main__":
    sys.exit(main())
