import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "server" / "auto_commit_mcp.py"
SPEC = importlib.util.spec_from_file_location("auto_commit_mcp", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AutoCommitterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)
        self.repo = temp_root / "repo"
        self.remote = temp_root / "remote.git"
        self.repo.mkdir()
        subprocess.run(["git", "init", "--bare", "-q", self.remote], check=True)
        self.git("init", "-q")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        self.git("remote", "add", "origin", str(self.remote))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def committer(self, include_untracked: bool = True):
        committer = MODULE.AutoCommitter(
            cwd=self.repo,
            interval_seconds=5,
            message="test: snapshot",
            include_untracked=include_untracked,
            enabled=False,
        )
        self.addCleanup(committer.close)
        return committer

    def test_commits_and_pushes_changes_then_skips_empty_sync(self) -> None:
        (self.repo / "note.txt").write_text("one\n")
        self.git("add", "note.txt")
        self.git("commit", "-q", "-m", "initial")
        self.git("push", "-q", "--set-upstream", "origin", "HEAD")
        (self.repo / "note.txt").write_text("two\n")
        committer = self.committer()

        result = committer.commit_once()

        self.assertIn("test: snapshot", result)
        self.assertIn("Pushed 1 commit", result)
        self.assertEqual(self.git("log", "-1", "--pretty=%s").stdout.strip(), "test: snapshot")
        local_head = self.git("rev-parse", "HEAD").stdout
        remote_head = self.git("rev-parse", "@{upstream}").stdout
        self.assertEqual(local_head, remote_head)
        self.assertEqual(committer.commit_once(), "No changes to commit or push")

    def test_can_ignore_untracked_files(self) -> None:
        (self.repo / "untracked.txt").write_text("draft\n")
        committer = self.committer(include_untracked=False)

        self.assertEqual(committer.commit_once(), "No changes to commit or push")
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.repo,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_skips_merge_in_progress(self) -> None:
        (self.repo / "tracked.txt").write_text("initial\n")
        self.git("add", "tracked.txt")
        self.git("commit", "-q", "-m", "initial")
        (self.repo / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n")
        (self.repo / "tracked.txt").write_text("changed\n")
        committer = self.committer()

        self.assertEqual(committer.commit_once(), "Skipped: Git merge is in progress")
        self.assertEqual(self.git("status", "--porcelain").stdout, " M tracked.txt\n")

    def test_reports_missing_upstream_after_committing(self) -> None:
        (self.repo / "note.txt").write_text("one\n")
        committer = self.committer()

        with self.assertRaisesRegex(RuntimeError, "current branch has no upstream"):
            committer.commit_once()

        self.assertEqual(self.git("log", "-1", "--pretty=%s").stdout.strip(), "test: snapshot")


if __name__ == "__main__":
    unittest.main()
