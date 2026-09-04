import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import tomllib

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("codex_away_install", SCRIPT)
assert SPEC and SPEC.loader
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)

SCRIPTS = SCRIPT.parent
sys.path.insert(0, str(SCRIPTS))
UNINSTALL_SPEC = importlib.util.spec_from_file_location(
    "codex_away_uninstall", SCRIPTS / "uninstall.py"
)
assert UNINSTALL_SPEC and UNINSTALL_SPEC.loader
UNINSTALL = importlib.util.module_from_spec(UNINSTALL_SPEC)
UNINSTALL_SPEC.loader.exec_module(UNINSTALL)


class InstallConfigTests(unittest.TestCase):
    def test_notify_wraps_and_preserves_existing_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = Path(temporary_directory) / "config.toml"
            config.write_text(
                'notify = ["/existing/python", "/existing/notify.py"]\n\n[features]\nfoo = true\n',
                encoding="utf-8",
            )

            INSTALL.update_notify(
                config, Path("/new/python"), Path("/new/codex-away.py")
            )

            parsed = tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(
                parsed["notify"],
                [
                    "/new/python",
                    "/new/codex-away.py",
                    "notify",
                    "/existing/python",
                    "/existing/notify.py",
                ],
            )
            self.assertTrue(parsed["features"]["foo"])

    def test_notify_reinstall_does_not_nest_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = Path(temporary_directory) / "config.toml"
            config.write_text(
                'notify = ["/old/python", "/old/codex-away.py", "notify", "/upstream"]\n',
                encoding="utf-8",
            )

            INSTALL.update_notify(
                config, Path("/new/python"), Path("/new/codex-away.py")
            )

            parsed = tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(
                parsed["notify"],
                ["/new/python", "/new/codex-away.py", "notify", "/upstream"],
            )

    def test_notify_reinstall_updates_computer_use_previous_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = Path(temporary_directory) / "config.toml"
            previous = json.dumps(["/old/python", "/old/codex-away.py", "notify"])
            config.write_text(
                "notify = "
                + json.dumps(
                    ["/computer-use", "turn-ended", "--previous-notify", previous]
                )
                + "\n",
                encoding="utf-8",
            )

            INSTALL.update_notify(
                config, Path("/new/python"), Path("/new/codex-away.py")
            )

            parsed = tomllib.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(
                parsed["notify"][:3],
                ["/computer-use", "turn-ended", "--previous-notify"],
            )
            self.assertEqual(
                json.loads(parsed["notify"][3]),
                ["/new/python", "/new/codex-away.py", "notify"],
            )

    def test_uninstall_recursively_removes_nested_notify_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = Path(temporary_directory) / "config.toml"
            nested_away = json.dumps(
                [
                    "/old/python",
                    "/old/codex-away.py",
                    "notify",
                    "/original/notify",
                ]
            )
            inner = json.dumps(
                ["/inner-wrapper", "--previous-notify", nested_away]
            )
            config.write_text(
                "notify = "
                + json.dumps(
                    ["/outer-wrapper", "--previous-notify", inner]
                )
                + "\n",
                encoding="utf-8",
            )

            INSTALL.update_notify(
                config, Path("/new/python"), Path("/new/codex-away.py")
            )

            UNINSTALL.unwrap_notify(config)

            notify = tomllib.loads(config.read_text(encoding="utf-8"))["notify"]
            inner_result = json.loads(notify[2])
            self.assertEqual(
                json.loads(inner_result[2]), ["/original/notify"]
            )

    def test_uninstall_preserves_malformed_nested_notify(self) -> None:
        command = [
            "/computer-use",
            "turn-ended",
            "--previous-notify",
            "not-json",
        ]

        updated, changed = UNINSTALL.unwrap_existing_away(command)

        self.assertFalse(changed)
        self.assertEqual(updated, command)

    def test_uninstall_unwraps_top_level_notify(self) -> None:
        updated, changed = UNINSTALL.unwrap_existing_away(
            [
                "/python",
                "/runtime/codex-away.py",
                "notify",
                "/original/notify",
            ]
        )

        self.assertTrue(changed)
        self.assertEqual(updated, ["/original/notify"])

    def test_permission_hook_merges_with_existing_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            hooks_path = Path(temporary_directory) / "hooks.json"
            hooks_path.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PermissionRequest": [
                                {"hooks": [{"type": "command", "command": "existing"}]}
                            ],
                            "Stop": [
                                {"hooks": [{"type": "command", "command": "stop"}]}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            INSTALL.update_permission_hook(
                hooks_path, Path("/new/python"), Path("/new/codex-away.py")
            )

            value = json.loads(hooks_path.read_text(encoding="utf-8"))
            serialized = json.dumps(value)
            self.assertIn("existing", serialized)
            self.assertIn("stop", serialized)
            self.assertIn("codex-away.py permission", serialized)

    def test_preflight_does_not_change_real_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            codex_home = Path(temporary_directory)
            config = codex_home / "config.toml"
            hooks = codex_home / "hooks.json"
            config_text = 'notify = ["/existing"]\n[features]\nfoo = true\n'
            hooks_text = '{"hooks": {"Stop": []}}\n'
            config.write_text(config_text, encoding="utf-8")
            hooks.write_text(hooks_text, encoding="utf-8")

            INSTALL.preflight_codex_config(
                codex_home, Path("/new/python"), Path("/new/codex-away.py")
            )

            self.assertEqual(config.read_text(encoding="utf-8"), config_text)
            self.assertEqual(hooks.read_text(encoding="utf-8"), hooks_text)

    def test_disable_replies_keeps_notifications_and_disables_relaunch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            away_home = home / ".codex" / "codex-away"
            bridge_home = home / ".codex" / "codex-feishu-bridge"
            launch_agents = home / "Library" / "LaunchAgents"
            away_home.mkdir(parents=True)
            bridge_home.mkdir(parents=True)
            launch_agents.mkdir(parents=True)
            (away_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "chat_id": "oc_private",
                        "install_mode": "replies",
                    }
                ),
                encoding="utf-8",
            )
            (away_home / "state.json").write_text(
                json.dumps(
                    {
                        "reply_targets": {"om_notice": {"thread_id": "thread"}},
                        "reply_once_threads": ["thread"],
                    }
                ),
                encoding="utf-8",
            )
            plist_path = launch_agents / f"{INSTALL.LABEL}.plist"
            plist_path.write_text("placeholder", encoding="utf-8")

            INSTALL.disable_replies(home, skip_launchctl=True)

            config = json.loads((away_home / "config.json").read_text())
            state = json.loads((away_home / "state.json").read_text())
            self.assertEqual(config["install_mode"], "notify")
            self.assertEqual(state["reply_targets"], {})
            self.assertEqual(state["reply_once_threads"], [])
            self.assertFalse(plist_path.exists())
            self.assertTrue((bridge_home / "disabled-launch-agent.plist").is_file())


if __name__ == "__main__":
    unittest.main()
