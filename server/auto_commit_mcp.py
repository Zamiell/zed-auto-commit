#!/usr/bin/env python3

import fcntl
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class AutoCommitter:
    def __init__(
        self,
        cwd: Path,
        interval_seconds: int,
        message: str,
        include_untracked: bool,
        enabled: bool,
    ) -> None:
        self.cwd = cwd
        self.interval_seconds = interval_seconds
        self.message = message
        self.include_untracked = include_untracked
        self.enabled = enabled
        self.last_commit: str | None = None
        self.last_push: str | None = None
        self.last_error: str | None = None
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._repository_root = self._find_repository_root()
        self._instance_lock_file = None
        self._acquire_instance_lock()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        if self._repository_root is None:
            raise RuntimeError(f"{self.cwd} is not inside a Git repository")
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        result = subprocess.run(
            ["git", *args],
            cwd=self._repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if check and result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise RuntimeError(f"`git {args[0]}` failed: {details}")
        return result

    def _find_repository_root(self) -> Path | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.cwd,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return Path(result.stdout.strip())

    def _acquire_instance_lock(self) -> None:
        if self._repository_root is None:
            return
        try:
            git_dir = self._git("rev-parse", "--absolute-git-dir").stdout.strip()
            lock_path = Path(git_dir) / "zed-auto-commit.lock"
            self._instance_lock_file = lock_path.open("w")
            fcntl.flock(
                self._instance_lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            self._instance_lock_file.write(str(os.getpid()))
            self._instance_lock_file.flush()
        except (OSError, subprocess.SubprocessError) as error:
            self.enabled = False
            self.last_error = f"another Auto Commit process is active: {error}"

    def _operation_in_progress(self) -> str | None:
        markers = {
            "MERGE_HEAD": "merge",
            "rebase-merge": "rebase",
            "rebase-apply": "rebase",
            "CHERRY_PICK_HEAD": "cherry-pick",
            "REVERT_HEAD": "revert",
            "BISECT_LOG": "bisect",
        }
        for marker, operation in markers.items():
            marker_path = self._git("rev-parse", "--git-path", marker).stdout.strip()
            marker_path = Path(marker_path)
            if not marker_path.is_absolute():
                marker_path = self._repository_root / marker_path
            if marker_path.exists():
                return operation
        return None

    def close(self) -> None:
        self._stop.set()
        if self._instance_lock_file is not None:
            self._instance_lock_file.close()
            self._instance_lock_file = None

    def _push_if_ahead(self) -> str | None:
        if self._git("rev-parse", "--verify", "HEAD", check=False).returncode != 0:
            return None

        upstream_result = self._git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
            check=False,
        )
        if upstream_result.returncode != 0:
            raise RuntimeError(
                "cannot push: the current branch has no upstream; configure one with "
                "`git push --set-upstream <remote> <branch>`"
            )

        upstream = upstream_result.stdout.strip()
        ahead = int(self._git("rev-list", "--count", f"{upstream}..HEAD").stdout.strip())
        if ahead == 0:
            return None

        result = self._git("push", "--porcelain")
        destination = result.stderr.strip().splitlines()
        summary = f"Pushed {ahead} commit{'s' if ahead != 1 else ''} to {upstream}"
        if destination:
            summary = f"{summary} ({destination[-1]})"
        self.last_push = summary
        return summary

    def commit_once(self) -> str:
        with self._state_lock:
            if self._repository_root is None:
                raise RuntimeError(f"{self.cwd} is not inside a Git repository")

            operation = self._operation_in_progress()
            if operation is not None:
                return f"Skipped: Git {operation} is in progress"

            status_args = ["status", "--porcelain=v1"]
            if not self.include_untracked:
                status_args.append("--untracked-files=no")
            commit_summary = None
            if self._git(*status_args).stdout:
                self._git("add", "-A" if self.include_untracked else "-u")
                if self._git("diff", "--cached", "--quiet", check=False).returncode != 0:
                    result = self._git(
                        "-c",
                        "commit.gpgSign=false",
                        "commit",
                        "--no-verify",
                        "-m",
                        self.message,
                    )
                    commit_summary = result.stdout.strip().splitlines()[0]
                    self.last_commit = commit_summary

            push_summary = self._push_if_ahead()
            self.last_error = None
            summaries = [
                summary for summary in (commit_summary, push_summary) if summary is not None
            ]
            return "; ".join(summaries) if summaries else "No changes to commit or push"

    def run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if not self.enabled:
                continue
            try:
                result = self.commit_once()
                if result != "No changes to commit or push":
                    print(f"Auto Commit: {result}", file=sys.stderr, flush=True)
            except Exception as error:
                self.last_error = str(error)
                print(f"Auto Commit error: {error}", file=sys.stderr, flush=True)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "repository": (
                str(self._repository_root) if self._repository_root is not None else None
            ),
            "include_untracked": self.include_untracked,
            "last_commit": self.last_commit,
            "last_push": self.last_push,
            "last_error": self.last_error,
        }


class McpServer:
    def __init__(self, committer: AutoCommitter) -> None:
        self.committer = committer

    @staticmethod
    def _response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _tool_result(text: str, is_error: bool = False) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            protocol_version = request.get("params", {}).get(
                "protocolVersion", "2025-06-18"
            )
            return self._response(
                request_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "zed-auto-commit", "version": "0.1.0"},
                },
            )
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        if method == "ping":
            return self._response(request_id, {})
        if method == "tools/list":
            return self._response(
                request_id,
                {
                    "tools": [
                        {
                            "name": "status",
                            "description": "Show Auto Commit status for this project",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "commit_now",
                            "description": "Create and push a snapshot commit immediately",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "pause",
                            "description": "Pause automatic commits for this session",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "resume",
                            "description": "Resume automatic commits for this session",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            )
        if method == "tools/call":
            name = request.get("params", {}).get("name")
            try:
                if name == "status":
                    result = json.dumps(self.committer.status(), indent=2)
                elif name == "commit_now":
                    result = self.committer.commit_once()
                elif name == "pause":
                    self.committer.enabled = False
                    result = "Automatic commits paused"
                elif name == "resume":
                    self.committer.enabled = True
                    result = "Automatic commits resumed"
                else:
                    return self._response(
                        request_id,
                        self._tool_result(f"Unknown tool: {name}", is_error=True),
                    )
                return self._response(request_id, self._tool_result(result))
            except Exception as error:
                self.committer.last_error = str(error)
                return self._response(
                    request_id,
                    self._tool_result(str(error), is_error=True),
                )

        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main() -> None:
    interval_seconds = int(os.environ.get("ZED_AUTO_COMMIT_INTERVAL_SECONDS", "5"))
    if interval_seconds < 1:
        raise ValueError("ZED_AUTO_COMMIT_INTERVAL_SECONDS must be at least 1")

    message = os.environ.get("ZED_AUTO_COMMIT_MESSAGE", "chore: auto-commit")
    if not message.strip():
        raise ValueError("ZED_AUTO_COMMIT_MESSAGE must not be empty")

    committer = AutoCommitter(
        cwd=Path.cwd(),
        interval_seconds=interval_seconds,
        message=message,
        include_untracked=env_bool("ZED_AUTO_COMMIT_INCLUDE_UNTRACKED", True),
        enabled=env_bool("ZED_AUTO_COMMIT_ENABLED", True),
    )
    threading.Thread(target=committer.run, daemon=True).start()
    server = McpServer(committer)

    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                response = server.handle(request)
                if response is not None:
                    print(json.dumps(response, separators=(",", ":")), flush=True)
            except Exception as error:
                print(f"Auto Commit MCP error: {error}", file=sys.stderr, flush=True)
    finally:
        committer.close()


if __name__ == "__main__":
    main()
