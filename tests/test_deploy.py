"""Unit-level checks from deploy/TODO-testing.md. They need no services.

Run from the repo root:

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "buildingdepot"))
sys.path.insert(0, os.path.join(REPO_ROOT, "deploy"))
sys.path.insert(0, os.path.join(REPO_ROOT, "deploy", "shared"))

import env  # noqa: E402
import install  # noqa: E402
import template  # noqa: E402


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env_path = os.path.join(tmp.name, ".env")
        env.provision_env(
            install.ENV_EXAMPLE, self.env_path, generate=install.GENERATE_SECRETS
        )

    def load_config(self, **environ: str) -> dict[str, object]:
        environ["BD_ENV"] = self.env_path
        with mock.patch.dict(os.environ, environ, clear=True):
            sys.modules.pop("bd_config", None)
            return importlib.import_module("bd_config").CONFIG

    def test_reads_env_named_by_bd_env(self) -> None:
        values = env.read_env(self.env_path)
        config = self.load_config()
        for key, value in config.items():
            if key in values:
                self.assertEqual(str(value), values[key], key)

    def test_blank_required_key_raises(self) -> None:
        env.update_env(self.env_path, {"REDIS_PWD": ""})
        message = f"REDIS_PWD is missing .* {re.escape(self.env_path)}"
        with self.assertRaisesRegex(RuntimeError, message):
            self.load_config()

    def test_process_environment_wins_over_file(self) -> None:
        config = self.load_config(REDIS_PWD="from-environment")
        self.assertEqual(config["REDIS_PWD"], "from-environment")

    def test_compose_variables_are_in_env_example(self) -> None:
        with open(install.COMPOSE_FILE, encoding="utf-8") as handle:
            names = set(re.findall(r"\$\{(\w+)\}", handle.read()))
        self.assertTrue(names)
        self.assertLessEqual(names, set(env.read_env(install.ENV_EXAMPLE)))


class DeployTest(unittest.TestCase):
    def test_install_help(self) -> None:
        result = subprocess.run(
            [sys.executable, os.path.join(install.DEPLOY_DIR, "install.py"), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_systemd_units_render(self) -> None:
        variables = {"WORKING_DIRECTORY": REPO_ROOT, "UV_BIN": sys.executable}
        with tempfile.TemporaryDirectory() as tmp:
            units = []
            for name in install.SERVICES:
                unit = os.path.join(tmp, f"{name}.service")
                template.render_file(
                    os.path.join(install.SYSTEMD_DIR, f"{name}.service.template"),
                    unit,
                    variables,
                )
                units.append(unit)
            if shutil.which("systemd-analyze") is None:
                self.skipTest("systemd-analyze not installed")
            result = subprocess.run(
                ["systemd-analyze", "verify", *units], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
