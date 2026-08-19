# Auto Commit for Zed

Auto Commit creates Git snapshot commits for the project open in Zed and pushes them to the current
branch's configured upstream. The default interval is five seconds.

Zed does not expose timers or save hooks to extensions, so Auto Commit runs as a lightweight MCP
server. Enabling the server starts the commit loop; disabling it stops the loop.

## Install for development

1. In Zed, run `zed: install dev extension` and select the `extension` directory in this repository.
2. Open **Settings > AI > MCP Servers**, install or enable **Auto Commit**, and confirm its status
   indicator is green.

The settings are:

```json
{
  "enabled": true,
  "interval_seconds": 5,
  "commit_message": "chore: auto-commit",
  "include_untracked": true
}
```

Automatic commits skip empty repositories and active merges, rebases, cherry-picks, reverts, and
bisections. Commit signing and Git hooks are disabled for snapshot commits, and pushes cannot prompt
for credentials. The extension never pulls, rebases, force-pushes, or guesses an upstream branch.

## Requirements

- Zed on Linux, WSL, or macOS
- Python 3
- Git with `user.name` and `user.email` configured

## Test

```sh
python3 -m unittest discover -s tests -v
```
