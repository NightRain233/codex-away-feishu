import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("codex_away_setup", SCRIPTS / "setup.py")
assert SPEC and SPEC.loader
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class SetupTests(unittest.TestCase):
    def test_installation_paths_are_user_scoped(self) -> None:
        home = Path("/Users/friend")
        paths = SETUP.installation_paths(home, "notify")

        self.assertTrue(paths)
        self.assertTrue(all(value.startswith(str(home)) for value in paths))
        self.assertIn(str(home / ".codex" / "config.toml"), paths)
        self.assertIn(str(home / ".codex" / "hooks.json"), paths)
        self.assertNotIn(str(home / ".codex" / "codex-feishu-bridge"), paths)

        reply_paths = SETUP.installation_paths(home, "replies")
        self.assertIn(str(home / ".codex" / "codex-feishu-bridge"), reply_paths)
        self.assertIn(
            str(home / "Applications" / "Codex Feishu Submit.app"), reply_paths
        )

    def test_install_requires_explicit_approval(self) -> None:
        args = argparse.Namespace(yes=False)
        self.assertEqual(SETUP.install_bridge(args), 10)

    def test_install_discovers_ids_without_command_line_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            python = Path(sys.executable)
            lark_cli = Path(temporary_directory) / "lark-cli"
            lark_cli.write_text("#!/bin/sh\n", encoding="utf-8")
            lark_cli.chmod(0o700)
            args = argparse.Namespace(
                yes=True,
                json=False,
                timeout=20,
                lark_cli=str(lark_cli),
                python=str(python),
                skip_codex_config=True,
                skip_launchctl=True,
                recompile_helper=False,
                mode=None,
            )
            preflight = {
                "ready": True,
                "blockers": [],
                "changes": [],
                "mode": "notify",
            }
            recipient = {
                "recipient_open_id": "ou_friend",
                "chat_id": "oc_private",
            }

            with (
                patch.object(SETUP, "collect_preflight", return_value=preflight),
                patch.object(
                    SETUP.installer,
                    "install_home",
                    return_value=Path(temporary_directory),
                ),
                patch.object(
                    SETUP.discover_recipient, "discover", return_value=recipient
                ),
                patch.object(SETUP.installer, "install") as install,
            ):
                self.assertEqual(SETUP.install_bridge(args), 0)

            install_args = install.call_args.args[0]
            self.assertEqual(install_args.recipient_open_id, "ou_friend")
            self.assertEqual(install_args.chat_id, "oc_private")
            self.assertEqual(install_args.lark_cli, str(lark_cli.resolve()))
            self.assertEqual(install_args.mode, "notify")

    def test_notification_install_reuses_authenticated_user_open_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            python = Path(sys.executable)
            lark_cli = Path(temporary_directory) / "lark-cli"
            lark_cli.write_text("#!/bin/sh\n", encoding="utf-8")
            lark_cli.chmod(0o700)
            args = argparse.Namespace(
                yes=True,
                json=False,
                timeout=20,
                lark_cli=str(lark_cli),
                python=str(python),
                skip_codex_config=True,
                skip_launchctl=True,
                recompile_helper=False,
                mode="notify",
            )
            preflight = {
                "ready": True,
                "blockers": [],
                "changes": [],
                "mode": "notify",
            }

            with (
                patch.object(SETUP, "collect_preflight", return_value=preflight),
                patch.object(
                    SETUP.installer,
                    "install_home",
                    return_value=Path(temporary_directory),
                ),
                patch.object(
                    SETUP.discover_recipient,
                    "current_user_open_id",
                    return_value="ou_friend",
                ),
                patch.object(SETUP.discover_recipient, "discover") as discover,
                patch.object(SETUP.installer, "install") as install,
            ):
                self.assertEqual(SETUP.install_bridge(args), 0)

            discover.assert_not_called()
            install_args = install.call_args.args[0]
            self.assertEqual(install_args.recipient_open_id, "ou_friend")
            self.assertIsNone(install_args.chat_id)

    @unittest.skipUnless(sys.platform == "darwin", "macOS installer test")
    def test_guided_install_completes_in_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_codex_app = root / "Codex.app"
            fake_codex_app.mkdir()
            fake_lark = root / "lark-cli"
            fake_lark.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['auth', 'status']:\n"
                "    print(json.dumps({'identities': {'bot': {'status': 'ready', 'available': True}}}))\n"
                "elif args[:2] == ['event', 'consume']:\n"
                "    print(json.dumps({'type': 'im.message.receive_v1', 'sender_type': 'user', 'chat_type': 'p2p', 'sender_id': 'ou_friend', 'chat_id': 'oc_private'}))\n"
                "else:\n"
                "    raise SystemExit(2)\n",
                encoding="utf-8",
            )
            fake_lark.chmod(0o700)
            environment = os.environ.copy()
            environment.update(
                {
                    "CODEX_AWAY_INSTALL_HOME": str(root),
                    "CODEX_AWAY_CODEX_APP": str(fake_codex_app),
                }
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "setup.py"),
                    "install",
                    "--yes",
                    "--lark-cli",
                    str(fake_lark),
                    "--python",
                    sys.executable,
                    "--skip-launchctl",
                ],
                capture_output=True,
                check=False,
                env=environment,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed_config = json.loads(
                (root / ".codex" / "codex-away" / "config.json").read_text()
            )
            self.assertEqual(installed_config["recipient_open_id"], "ou_friend")
            self.assertEqual(installed_config["chat_id"], "oc_private")
            self.assertEqual(installed_config["install_mode"], "notify")
            self.assertTrue((root / ".codex" / "config.toml").is_file())
            self.assertTrue((root / ".codex" / "hooks.json").is_file())
            self.assertFalse(
                (root / "Applications" / "Codex Feishu Submit.app").exists()
            )
            doctor = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "doctor.py"),
                    "--home",
                    str(root),
                    "--mode",
                    "notify",
                    "--skip-launchctl",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertIn("Reply bridge checks skipped", doctor.stdout)

    @unittest.skipUnless(sys.platform == "darwin", "macOS installer test")
    def test_reply_mode_installs_optional_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_codex_app = root / "Codex.app"
            fake_codex_app.mkdir()
            fake_lark = root / "lark-cli"
            fake_lark.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "args = sys.argv[1:]\n"
                "if args[:2] == ['auth', 'status']:\n"
                "    print(json.dumps({'identities': {'bot': {'status': 'ready', 'available': True}}}))\n"
                "elif args[:2] == ['event', 'consume']:\n"
                "    print(json.dumps({'type': 'im.message.receive_v1', 'sender_type': 'user', 'chat_type': 'p2p', 'sender_id': 'ou_friend', 'chat_id': 'oc_private'}))\n"
                "else:\n"
                "    raise SystemExit(2)\n",
                encoding="utf-8",
            )
            fake_lark.chmod(0o700)
            environment = os.environ.copy()
            environment.update(
                {
                    "CODEX_AWAY_INSTALL_HOME": str(root),
                    "CODEX_AWAY_CODEX_APP": str(fake_codex_app),
                }
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "setup.py"),
                    "install",
                    "--yes",
                    "--mode",
                    "replies",
                    "--lark-cli",
                    str(fake_lark),
                    "--python",
                    sys.executable,
                    "--skip-launchctl",
                ],
                capture_output=True,
                check=False,
                env=environment,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed_config = json.loads(
                (root / ".codex" / "codex-away" / "config.json").read_text()
            )
            self.assertEqual(installed_config["install_mode"], "replies")
            self.assertTrue(
                (
                    root / ".codex" / "codex-feishu-bridge" / "codex-feishu-bridge.py"
                ).is_file()
            )
            self.assertTrue(
                (root / "Applications" / "Codex Feishu Submit.app").is_dir()
            )
            self.assertTrue(
                (
                    root
                    / "Library"
                    / "LaunchAgents"
                    / "com.codex-away.feishu-bridge.plist"
                ).is_file()
            )
            doctor = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "doctor.py"),
                    "--home",
                    str(root),
                    "--mode",
                    "replies",
                    "--skip-launchctl",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertIn("Accessibility helper app", doctor.stdout)

    def test_enable_replies_reuses_discovered_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            python = Path(sys.executable)
            lark_cli = root / "lark-cli"
            lark_cli.write_text("#!/bin/sh\n", encoding="utf-8")
            lark_cli.chmod(0o700)
            config_home = root / ".codex" / "codex-away"
            config_home.mkdir(parents=True)
            (config_home / "config.json").write_text(
                json.dumps(
                    {
                        "recipient_open_id": "ou_friend",
                        "chat_id": "oc_private",
                        "install_mode": "notify",
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                yes=True,
                json=False,
                timeout=20,
                lark_cli=str(lark_cli),
                python=str(python),
                skip_codex_config=True,
                skip_launchctl=True,
                recompile_helper=False,
            )
            preflight = {"ready": True, "blockers": [], "mode": "replies"}

            with (
                patch.object(SETUP.installer, "install_home", return_value=root),
                patch.object(SETUP, "collect_preflight", return_value=preflight),
                patch.object(SETUP.discover_recipient, "discover") as discover,
                patch.object(SETUP.installer, "install") as install,
            ):
                self.assertEqual(SETUP.enable_replies(args), 0)

            discover.assert_not_called()
            self.assertEqual(install.call_args.args[0].mode, "replies")


if __name__ == "__main__":
    unittest.main()
