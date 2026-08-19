# Auto Commit

When enabled, this server creates local snapshot commits for the current project.

- It never pushes.
- It skips empty commits and repositories in the middle of a merge, rebase, cherry-pick, revert, or bisect.
- It disables commit signing and hooks so an unattended commit cannot open an interactive prompt.
- Disable the server or set `enabled` to `false` before rebasing or otherwise rewriting history.

This extension currently supports Linux, WSL, and macOS.

