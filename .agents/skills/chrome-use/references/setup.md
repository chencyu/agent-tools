# Start and attach to a browser

Read this at the start of every browser-use task to use the configured browser preference and verify the intended profile.

## Windows launcher

Set the preferred browser once per machine: copy [`scripts/start-browser.example.psd1`](../scripts/start-browser.example.psd1) to `scripts/start-browser.psd1` and set `Browser = 'Chrome'` or `Browser = 'Edge'`. Each key there names a launcher parameter and supplies its value whenever that parameter is omitted. Without the file or its `Browser` key, the launcher uses the system default browser and fails if that is neither Chrome nor Edge. Then start the launcher without `-Browser`:

```powershell
.\scripts\start-browser.ps1
```

Pass `-Browser Chrome` or `-Browser Edge` only to override the preference for a single run. Both browsers use port `9222` by default. Their persistent profile directories are:

| Browser | Default profile                                   |
| ------- | ------------------------------------------------- |
| Chrome  | `$HOME\.cache\chrome-devtools-mcp\chrome-profile` |
| Edge    | `$HOME\.cache\chrome-devtools-mcp\msedge-profile` |

The profile persists cookies and sign-ins between runs. On this machine, Edge policy sends a new profile to `edge://force-signin`; complete that first sign-in interactively before relying on the profile for signed-in tasks.

Override the port and profile together when needed:

```powershell
.\scripts\start-browser.ps1 -Port 9223 -ProfileDir "$HOME\.cache\chrome-devtools-mcp\chrome-work"
```

Use the same port for the CLI connection. `-Executable` can select a non-standard browser installation.

## Attach the CLI

```powershell
chrome-devtools status
chrome-devtools start --browserUrl http://127.0.0.1:9222
chrome-devtools list_pages
```

Only run `start` when attaching or repairing is intentional: it can replace the daemon's current browser connection. Confirm the requested browser is attached before acting. If `status` shows no `--browser-url` argument, the daemon may be controlling its own default browser instead of the profile you launched.

The launcher refuses to reuse a port owned by another process or browser profile. If the intended browser is already serving that port and profile, it reports success without opening another window.

## Non-Windows setup

Start Chrome or Edge yourself with a dedicated `--user-data-dir` and `--remote-debugging-port`, then attach with `chrome-devtools start --browserUrl http://127.0.0.1:<port>`. Keep the selected browser and port consistent. Edge is not an officially supported browser for this CLI.
