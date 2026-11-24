# copilot list

```
python <skill>/scripts/agentmsg copilot list [--name NAME] [--json]
```

Each line is `<id>  [copilot/<host>] '<name>' <status>`.

## One runtime, three hosts

| host     | Where the session lives                   |
| -------- | ----------------------------------------- |
| `app`    | the desktop app                           |
| `cli`    | a standalone CLI that is running a server |
| `vscode` | a VS Code chat on the Copilot harness     |

Every id is a bare UUID, and `send` finds the host on its own. An id may appear under one host only: the App's and the CLI's own sessions, which VS Code can also see on disk, are listed under `app` or `cli`.

## Gotchas

- `--name` matches exactly and may return several sessions. Every one is real.
- Absence means unreachable now, not nonexistent.
