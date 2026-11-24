# A Copilot App session is missing from the list

The person names a session they use in the GitHub Copilot desktop app, but `copilot list` does not show it, and `send` to its id fails with `no live Copilot session`.

## Suspect first: the App is not running

The App is the only route to its own sessions. VS Code's agent host can see them on disk but does not run them, so `list` omits them there. While the App is closed, none of its sessions is reachable.

Confirm:

```
Test-Path ~/.copilot/run/ws.port
```

`False` means the App is not running.

## What to tell the user

Report that the session is unreachable because the App is closed, then stop. Opening the App makes every one of its sessions reachable again, idle ones included; the App starts a session's runtime when a message arrives.
