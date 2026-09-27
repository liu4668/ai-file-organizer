import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from create_fixtures import NAMES, create

BASE = Path(__file__).resolve().parent.parent
SCRIPT = BASE / "scripts" / "organizer.py"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "建筑项目"
        create(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def plan(self):
        return json.loads((self.root / ".ai-file-organizer" / "plan.json").read_text(encoding="utf-8"))

    def test_1_preview(self):
        self.run_cli("preview", self.root)
        self.assertEqual(len(self.plan()["entries"]), len(NAMES))
        self.assertTrue(all((self.root / name).exists() for name in NAMES))
        self.assertTrue((self.root / ".ai-file-organizer" / "organize_report.md").exists())

    def test_2_apply(self):
        self.run_cli("preview", self.root)
        self.run_cli("apply", self.root, "--confirm", "确认执行整理")
        log = json.loads((self.root / ".ai-file-organizer" / "organize_log.json").read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "complete")
        self.assertEqual(len(list((self.root / "Organized").rglob("*.*"))), len(NAMES))
        self.assertTrue((self.root / "Organized" / "Duplicates" / "Exact").exists())
        self.assertTrue(any("V02" in p.name for p in (self.root / "Organized" / "Design").iterdir()))

    def test_3_undo(self):
        self.run_cli("preview", self.root)
        self.run_cli("apply", self.root, "--confirm", "确认执行整理")
        self.run_cli("undo", self.root)
        self.assertTrue(all((self.root / name).exists() for name in NAMES))
        self.assertEqual(json.loads((self.root / ".ai-file-organizer" / "organize_log.json").read_text(encoding="utf-8"))["status"], "undone")

    def test_4_duplicates_only(self):
        self.run_cli("preview", self.root, "--mode", "duplicates")
        report = (self.root / ".ai-file-organizer" / "duplicate_report.md").read_text(encoding="utf-8")
        self.assertIn("报告副本.pdf", report)
        self.assertFalse((self.root / "Organized").exists())
        self.assertTrue(all((self.root / name).exists() for name in NAMES))

    def test_5_project_mode(self):
        self.run_cli("preview", self.root, "--mode", "project")
        destinations = [Path(e["new_path"]) for e in self.plan()["entries"]]
        self.assertTrue(any("Models" in p.parts for p in destinations))
        self.assertTrue(any("Documents" in p.parts for p in destinations))
        self.assertTrue(any("References" in p.parts for p in destinations))
        self.run_cli("apply", self.root, "--confirm", "确认执行整理")
        self.assertTrue((self.root / "Organized" / "建筑项目" / "Models").is_dir())
        self.assertTrue((self.root / "Organized" / "建筑项目" / "Documents").is_dir())


if __name__ == "__main__":
    unittest.main()
