# Auto Commit

When enabled, this server creates snapshot commits for the current project and pushes them to the
branch's configured upstream.

- It never pulls, rebases, force-pushes, or guesses which remote branch to use.
- The current branch must have an upstream configured, and credentials must already be available
  non-interactively.
- It skips empty commits and repositories in the middle of a merge, rebase, cherry-pick, revert, or bisect.
- It disables commit signing and hooks so an unattended commit cannot open an interactive prompt.
- Disable the server or set `enabled` to `false` before rebasing or otherwise rewriting history.

This extension currently supports Linux, WSL, and macOS.
