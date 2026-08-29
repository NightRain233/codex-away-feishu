#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_HOME = Path.home() / ".codex" / "codex-away"
MAX_MESSAGE_BYTES = 24000


def home_dir() -> Path:
    return Path(os.environ.get("CODEX_AWAY_HOME", str(DEFAULT_HOME)))


def state_path() -> Path:
    return home_dir() / "state.json"


def lock_path() -> Path:
    return home_dir() / "state.lock"


def log_path() -> Path:
    return home_dir() / "notify.log"


def config_path() -> Path:
    return home_dir() / "config.json"


def load_config() -> dict[str, Any]:
    try:
        value = json.loads(config_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def default_state() -> dict[str, Any]:
    return {
        "mode": "off",
        "thread_id": None,
        "enabled_at": None,
        "sent_event_ids": [],
        "reply_targets": {},
        "reply_once_threads": [],
    }


def load_state() -> dict[str, Any]:
    try:
        value = json.loads(state_path().read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return {**default_state(), **value}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return default_state()


def save_state(state: dict[str, Any]) -> None:
    home_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = state_path().with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, state_path())


class StateLock:
    def __enter__(self):
        home_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
        self.handle = lock_path().open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def write_log(message: str) -> None:
    try:
        home_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + message + "\n")
    except OSError:
        pass


def lark_cli() -> str:
    return os.environ.get("CODEX_AWAY_LARK_CLI") or str(
        load_config().get("lark_cli") or Path.home() / ".local" / "bin" / "lark-cli"
    )


def recipient() -> str:
    return os.environ.get("CODEX_AWAY_RECIPIENT") or str(
        load_config().get("recipient_open_id") or ""
    )


def replies_enabled() -> bool:
    config = load_config()
    mode = config.get("install_mode")
    if mode in {"notify", "replies"}:
        return mode == "replies"
    return bool(config.get("chat_id"))


def codex_home_dir() -> Path:
    return Path(os.environ.get("CODEX_AWAY_CODEX_HOME", str(Path.home() / ".codex")))


def state_db_paths() -> list[Path]:
    configured = os.environ.get("CODEX_AWAY_CODEX_STATE_DB")
    if configured:
        return [Path(configured)]
    try:
        return sorted(
            codex_home_dir().glob("state_*.sqlite"),
            key=lambda candidate: candidate.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []


def is_persistent_thread(thread_id: str) -> bool:
    checked_store = False
    for database_path in state_db_paths():
        if not database_path.is_file():
            continue
        try:
            database_uri = database_path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(database_uri, uri=True, timeout=1) as connection:
                row = connection.execute(
                    "SELECT 1 FROM threads WHERE id = ? LIMIT 1", (thread_id,)
                ).fetchone()
            checked_store = True
            if row:
                return True
        except (OSError, sqlite3.Error) as error:
            write_log(f"could not inspect Codex thread store: {error}")

    sessions_dir = codex_home_dir() / "sessions"
    try:
        if sessions_dir.is_dir():
            checked_store = True
            if next(sessions_dir.rglob(f"*-{thread_id}.jsonl"), None):
                return True
    except OSError as error:
        write_log(f"could not inspect Codex sessions: {error}")

    if checked_store:
        write_log(f"ignored completion for non-persistent thread {thread_id}")
        return False
    write_log("could not validate Codex thread persistence; allowing completion")
    return True


def event_id(payload: dict[str, Any], kind: str) -> str:
    session = str(payload.get("thread-id") or payload.get("session_id") or "")
    turn = str(payload.get("turn-id") or payload.get("turn_id") or "")
    detail = str(payload.get("tool_name") or kind)
    return hashlib.sha256(f"{kind}:{session}:{turn}:{detail}".encode()).hexdigest()[:32]


def matches(state: dict[str, Any], payload: dict[str, Any]) -> bool:
    wanted = state.get("thread_id")
    actual = payload.get("thread-id") or payload.get("session_id")
    global_match = state.get("mode") in {"once", "always"} and (
        not wanted or wanted == actual
    )
    reply_match = bool(actual and actual in state.get("reply_once_threads", []))
    return global_match or reply_match


def truncate(text: str, limit: int = 1800) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def split_message(text: str, max_bytes: int = MAX_MESSAGE_BYTES) -> list[str]:
    """Split user-visible Markdown without cutting a UTF-8 character."""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    parts: list[str] = []
    remaining = text
    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= max_bytes:
            parts.append(remaining)
            break
        cut = max_bytes
        while cut > 0 and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        candidate = encoded[:cut].decode("utf-8")
        boundary = max(candidate.rfind("\n\n"), candidate.rfind("\n"))
        if boundary > 0:
            cut = len(candidate[:boundary].encode("utf-8"))
        part = encoded[:cut].decode("utf-8")
        parts.append(part)
        remaining = remaining[len(part) :]
    return parts or [""]


def inline_code(text: str) -> str:
    return text.replace("`", "\\`")


def send_message(text: str, unique_id: str) -> dict[str, Any] | None:
    recipient_id = recipient()
    if not recipient_id:
        write_log("recipient_open_id is not configured")
        return None
    command = [
        lark_cli(),
        "im",
        "+messages-send",
        "--as",
        "bot",
        "--user-id",
        recipient_id,
        "--markdown",
        text,
        "--idempotency-key",
        "codex-away-" + unique_id[:36],
    ]
    environment = os.environ.copy()
    environment["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    environment["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        write_log(f"lark invocation failed: {error}")
        return None
    if result.returncode != 0:
        write_log(
            f"lark send failed ({result.returncode}): {truncate(result.stderr, 500)}"
        )
        return None
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        envelope = None
    if not isinstance(envelope, dict) or envelope.get("ok") is not True:
        write_log(
            f"lark send returned invalid success envelope: {truncate(result.stdout, 500)}"
        )
        return None
    return envelope


def send_messages(text: str, unique_id: str) -> list[dict[str, Any]] | None:
    responses: list[dict[str, Any]] = []
    for index, part in enumerate(split_message(text), start=1):
        response = send_message(part, f"{unique_id}-{index}")
        if not response:
            return None
        responses.append(response)
    return responses


def process_event(payload: dict[str, Any], kind: str) -> None:
    actual_thread = str(payload.get("thread-id") or payload.get("session_id") or "")
    if kind == "complete" and actual_thread and not is_persistent_thread(actual_thread):
        return
    unique_id = event_id(payload, kind)
    with StateLock():
        state = load_state()
        if not matches(state, payload) or unique_id in state.get("sent_event_ids", []):
            return

        cwd = str(payload.get("cwd") or "未知")
        if kind == "permission":
            tool = str(payload.get("tool_name") or "未知工具")
            tool_input = payload.get("tool_input") or {}
            description = (
                tool_input.get("description") if isinstance(tool_input, dict) else None
            )
            body = (
                f"#### Codex 需要你处理\n\n"
                f"**原因：** 等待权限批准（{tool}）\n\n"
                f"**工作目录：** `{inline_code(cwd)}`"
            )
            if description:
                body += f"\n\n**说明：** {description!s}"
        else:
            summary = str(
                payload.get("last-assistant-message") or "本轮没有最终回复。"
            ).strip()
            body = f"#### Codex 本轮已结束\n\n**工作目录：** `{inline_code(cwd)}`\n\n{summary}"

        responses = send_messages(body, unique_id)
        if not responses:
            return

        sent = list(state.get("sent_event_ids", []))
        sent.append(unique_id)
        state["sent_event_ids"] = sent[-100:]
        message_ids = [
            str((response.get("data") or {}).get("message_id") or "")
            for response in responses
        ]
        if kind == "complete" and actual_thread and replies_enabled():
            reply_targets = dict(state.get("reply_targets", {}))
            target = {"thread_id": str(actual_thread), "cwd": cwd}
            for message_id in message_ids:
                if message_id:
                    reply_targets[message_id] = target
            state["reply_targets"] = dict(list(reply_targets.items())[-100:])
        if kind == "complete" and actual_thread:
            state["reply_once_threads"] = [
                item
                for item in state.get("reply_once_threads", [])
                if item != actual_thread
            ]
        if kind == "complete" and state.get("mode") == "once":
            state["mode"] = "off"
            state["thread_id"] = None
        save_state(state)


def run_upstream(payload_json: str, upstream: list[str]) -> None:
    if not upstream:
        return
    try:
        result = subprocess.run(
            upstream + [payload_json],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            write_log(
                f"upstream notify failed ({result.returncode}): {truncate(result.stderr, 500)}"
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        write_log(f"upstream notify invocation failed: {error}")


def enable(mode: str, thread_id: str | None) -> int:
    selected_thread = thread_id or os.environ.get("CODEX_THREAD_ID")
    with StateLock():
        state = load_state()
        state.update(
            {
                "mode": mode,
                "thread_id": selected_thread,
                "enabled_at": int(time.time()),
                "sent_event_ids": [],
            }
        )
        save_state(state)
    scope = (
        f"thread {selected_thread}"
        if selected_thread
        else "the next matching Codex event"
    )
    print(f"codex-away enabled ({mode}) for {scope}")
    return 0


def disable() -> int:
    with StateLock():
        state = load_state()
        state.update({"mode": "off", "thread_id": None})
        save_state(state)
    print("codex-away disabled")
    return 0


def arm_reply(thread_id: str) -> int:
    if not replies_enabled():
        write_log("ignored arm-reply because the reply bridge is disabled")
        return 2
    with StateLock():
        state = load_state()
        threads = list(state.get("reply_once_threads", []))
        if thread_id not in threads:
            threads.append(thread_id)
        state["reply_once_threads"] = threads[-20:]
        save_state(state)
    return 0


def disarm_reply(thread_id: str) -> int:
    with StateLock():
        state = load_state()
        state["reply_once_threads"] = [
            item for item in state.get("reply_once_threads", []) if item != thread_id
        ]
        save_state(state)
    return 0


def show_status() -> int:
    state = load_state()
    print(f"mode: {state.get('mode', 'off')}")
    print(f"thread: {state.get('thread_id') or 'any'}")
    print(f"replies: {'enabled' if replies_enabled() else 'disabled'}")
    return 0


def parse_payload(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        write_log(f"invalid event JSON: {error}")
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Control Codex completion notifications to Feishu."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("on", "always"):
        child = subparsers.add_parser(name)
        child.add_argument("--thread", help="only notify for this Codex thread id")
    subparsers.add_parser("off")
    subparsers.add_parser("status")
    arm_parser = subparsers.add_parser("arm-reply")
    arm_parser.add_argument("--thread", required=True)
    disarm_parser = subparsers.add_parser("disarm-reply")
    disarm_parser.add_argument("--thread", required=True)
    notify_parser = subparsers.add_parser("notify")
    notify_parser.add_argument("notify_args", nargs="+")
    subparsers.add_parser("permission")
    args = parser.parse_args(argv)

    if args.command == "on":
        return enable("once", args.thread)
    if args.command == "always":
        return enable("always", args.thread)
    if args.command == "off":
        return disable()
    if args.command == "status":
        return show_status()
    if args.command == "arm-reply":
        return arm_reply(args.thread)
    if args.command == "disarm-reply":
        return disarm_reply(args.thread)
    if args.command == "notify":
        payload_json = args.notify_args[-1]
        upstream = args.notify_args[:-1]
        run_upstream(payload_json, upstream)
        payload = parse_payload(payload_json)
        if payload and payload.get("type") == "agent-turn-complete":
            process_event(payload, "complete")
        return 0
    if args.command == "permission":
        payload = parse_payload(sys.stdin.read())
        if payload and payload.get("hook_event_name") == "PermissionRequest":
            process_event(payload, "permission")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
