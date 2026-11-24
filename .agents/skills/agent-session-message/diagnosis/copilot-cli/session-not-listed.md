# A Copilot CLI session is missing from the list

The person says a `copilot` session is running, but `copilot list` does not show it.

## Suspect first: it was started without a server

The CLI only exposes a local RPC surface when it is started with `--ui-server`. Without it the session runs perfectly well and is simply not addressable — there is nothing to connect to, so it cannot appear.

Confirm before saying anything, because a session started correctly looks the same to the person:

```
Get-CimInstance Win32_Process -Filter "Name='copilot.exe'" |
  Select-Object ProcessId, CommandLine
```

A live `copilot.exe` whose command line has no `--server`, `--headless`, or `--ui-server` is the explanation. If no such process exists, the session is not running at all and this page does not apply.

## What to tell the user

Report that the session is unreachable and why, then stop. The fix belongs to them:

```
copilot --ui-server --resume <session-id>
```

**Do not offer a configuration workaround, because none exists.** The flag is hidden from `--help`, has no `settings.json` key, and no environment variable — the runtime creates the server only from that flag. The desktop app and VS Code's agent host escape the requirement only because they spawn the CLI themselves and pass `--server --stdio`; a session a person started by hand has no such parent.

Restarting also loses the session unless `--resume <id>` is used, and `--name` creates a second session rather than reattaching to the old one. Mention that only if they intend to restart.
