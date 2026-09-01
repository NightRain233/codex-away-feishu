import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def load_asset(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, ASSETS / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AWAY = load_asset("codex_away_runtime", "codex-away.py")
BRIDGE = load_asset("codex_feishu_bridge_runtime", "codex-feishu-bridge.py")


class RuntimeConfigTests(unittest.TestCase):
    def test_notification_runtime_ignores_ephemeral_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_db = Path(temporary_directory) / "state.sqlite"
            with sqlite3.connect(state_db) as connection:
                connection.execute("CREATE TABLE threads (id TEXT PRIMARY KEY)")
                connection.execute(
                    "INSERT INTO threads (id) VALUES (?)", ("persistent-thread",)
                )
            with patch.dict(
                os.environ,
                {"CODEX_AWAY_CODEX_STATE_DB": str(state_db)},
                clear=False,
            ):
                self.assertTrue(AWAY.is_persistent_thread("persistent-thread"))
                self.assertFalse(AWAY.is_persistent_thread("ephemeral-thread"))

    def test_notification_runtime_ignores_persistent_subagent_threads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_db = Path(temporary_directory) / "state.sqlite"
            with sqlite3.connect(state_db) as connection:
                connection.execute(
                    "CREATE TABLE threads ("
                    "id TEXT PRIMARY KEY, source TEXT, thread_source TEXT, "
                    "agent_path TEXT)"
                )
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?)",
                    (
                        "root-thread",
                        "vscode",
                        "user",
                        None,
                    ),
                )
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?)",
                    (
                        "child-thread",
                        json.dumps(
                            {
                                "subagent": {
                                    "thread_spawn": {
                                        "parent_thread_id": "root-thread",
                                        "depth": 1,
                                    }
                                }
                            }
                        ),
                        "subagent",
                        "/root/review",
                    ),
                )
            with patch.dict(
                os.environ,
                {
                    "CODEX_AWAY_CODEX_STATE_DB": str(state_db),
                    "CODEX_AWAY_HOME": temporary_directory,
                },
                clear=False,
            ):
                self.assertTrue(AWAY.is_persistent_thread("root-thread"))
                self.assertFalse(AWAY.is_persistent_thread("child-thread"))
                AWAY.enable("always", None)
                with patch.object(AWAY, "send_messages") as send:
                    AWAY.process_event(
                        {
                            "thread-id": "child-thread",
                            "turn-id": "child-turn",
                            "cwd": "/friend/project",
                            "last-assistant-message": "child complete",
                        },
                        "complete",
                    )
                send.assert_not_called()

    def test_notification_runtime_detects_subagent_from_legacy_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_db = Path(temporary_directory) / "state.sqlite"
            with sqlite3.connect(state_db) as connection:
                connection.execute(
                    "CREATE TABLE threads (id TEXT PRIMARY KEY, source TEXT)"
                )
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?)",
                    (
                        "child-thread",
                        json.dumps({"subagent": {"thread_spawn": {"depth": 1}}}),
                    ),
                )
            with patch.dict(
                os.environ,
                {"CODEX_AWAY_CODEX_STATE_DB": str(state_db)},
                clear=False,
            ):
                self.assertFalse(AWAY.is_persistent_thread("child-thread"))

    def test_notification_runtime_reads_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            away_home = Path(temporary_directory)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "lark_cli": "/friend/lark-cli",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ, {"CODEX_AWAY_HOME": str(away_home)}, clear=False
            ):
                self.assertEqual(AWAY.recipient(), "ou_friend")
                self.assertEqual(AWAY.lark_cli(), "/friend/lark-cli")

    def test_notification_only_does_not_store_reply_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            away_home = Path(temporary_directory)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "lark_cli": "/friend/lark-cli",
                        "install_mode": "notify",
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "thread-id": "persistent-thread",
                "turn-id": "turn-1",
                "cwd": "/friend/project",
                "last-assistant-message": "done",
            }
            with (
                patch.dict(
                    os.environ, {"CODEX_AWAY_HOME": str(away_home)}, clear=False
                ),
                patch.object(AWAY, "is_persistent_thread", return_value=True),
                patch.object(
                    AWAY,
                    "send_message",
                    return_value={"data": {"message_id": "om_notice"}},
                ),
            ):
                AWAY.enable("always", "persistent-thread")
                AWAY.process_event(event, "complete")
                self.assertFalse(AWAY.replies_enabled())

            state = json.loads((away_home / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["reply_targets"], {})

    def test_split_message_preserves_long_utf8_content(self) -> None:
        original = "标题\n\n" + ("中文内容 and details\n" * 2000)
        parts = AWAY.split_message(original, max_bytes=1000)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 1000 for part in parts))
        self.assertEqual("".join(parts), original)

    def test_long_completion_maps_every_message_and_includes_last(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            away_home = Path(temporary_directory)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "lark_cli": "/friend/lark-cli",
                        "install_mode": "replies",
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "thread-id": "persistent-thread",
                "turn-id": "turn-long",
                "cwd": "/friend/project",
                "last-assistant-message": "result\n" * 5000,
            }
            responses = [
                {"data": {"message_id": "om_first"}},
                {"data": {"message_id": "om_second"}},
            ]
            with (
                patch.dict(
                    os.environ, {"CODEX_AWAY_HOME": str(away_home)}, clear=False
                ),
                patch.object(AWAY, "is_persistent_thread", return_value=True),
                patch.object(AWAY, "send_message", side_effect=responses) as send,
            ):
                AWAY.enable("always", "persistent-thread")
                AWAY.process_event(event, "complete")

            self.assertGreater(send.call_count, 1)
            state = json.loads((away_home / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(
                state["reply_targets"],
                {
                    "om_first": {
                        "thread_id": "persistent-thread",
                        "cwd": "/friend/project",
                    },
                    "om_second": {
                        "thread_id": "persistent-thread",
                        "cwd": "/friend/project",
                    },
                },
            )

    def test_legacy_reply_installation_remains_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            away_home = Path(temporary_directory)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "chat_id": "oc_private",
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ, {"CODEX_AWAY_HOME": str(away_home)}, clear=False
            ):
                self.assertTrue(AWAY.replies_enabled())

    def test_bridge_accepts_only_configured_private_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            away_home = Path(temporary_directory)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "chat_id": "oc_private",
                    }
                ),
                encoding="utf-8",
            )
            event = {
                "type": "im.message.receive_v1",
                "sender_id": "ou_friend",
                "sender_type": "user",
                "chat_id": "oc_private",
                "chat_type": "p2p",
                "message_type": "text",
                "content": "continue",
                "message_id": "om_reply",
                "reply_to": "om_notification",
            }
            with patch.dict(
                os.environ, {"CODEX_AWAY_HOME": str(away_home)}, clear=False
            ):
                self.assertTrue(BRIDGE.authorized_event(event))
                self.assertFalse(
                    BRIDGE.authorized_event({**event, "sender_id": "ou_someone_else"})
                )
                self.assertFalse(
                    BRIDGE.authorized_event({**event, "chat_type": "group"})
                )


if __name__ == "__main__":
    unittest.main()
