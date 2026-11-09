"""Runs the node tests of the offline till's logic (tests/js). Skipped when node is not installed."""

import shutil
import subprocess
import unittest
from pathlib import Path

JS_TESTS = Path(__file__).parent / "js"


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestOfflineCoreJs(unittest.TestCase):
	def test_node_tests_pass(self):
		for test in sorted(JS_TESTS.glob("test_*.js")):
			run = subprocess.run(["node", str(test)], capture_output=True, text=True, timeout=60)
			self.assertEqual(run.returncode, 0, f"{test.name}\n{run.stdout}\n{run.stderr}")
