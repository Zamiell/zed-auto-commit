# Auto Commit for Zed

Auto Commit creates local Git snapshot commits for the project open in Zed. The default interval is
five seconds. It does not push.

Zed does not expose timers or save hooks to extensions, so Auto Commit runs as a lightweight MCP
server. Enabling the server starts the commit loop; disabling it stops the loop.

## Install for development

1. Make the server executable:

   ```sh
   chmod +x server/auto_commit_mcp.py
   ```

2. In Zed, run `zed: install dev extension` and select this repository.
3. Open **Settings > AI > MCP Servers**, install or enable **Auto Commit**, and confirm its status
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
bisections. Commit signing and Git hooks are disabled for snapshot commits to prevent interactive
commands from hanging the background server.

## Requirements

- Zed on Linux, WSL, or macOS
- Python 3
- Git with `user.name` and `user.email` configured

## Test

```sh
python3 -m unittest discover -s tests -v
```

