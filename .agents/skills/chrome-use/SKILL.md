---
name: chrome-use
description: Must load before driving Chrome or Edge with Chrome DevTools CLI. Do not drive Chrome or Edge with Chrome DevTools CLI without this skill.
---

# Chrome and Edge through Chrome DevTools CLI

Use the `chrome-devtools` CLI for chromium-based browser actions. It attaches through the DevTools protocol; the same command interface can target Chrome or Chromium-based Edge.

## Before acting

At the start of every browser-use task, read [references/setup.md](references/setup.md) to select and verify the intended browser/profile. Then read the reference for the requested operation:

| Need                                                        | Read                                                               |
| ----------------------------------------------------------- | ------------------------------------------------------------------ |
| Install the CLI                                             | [references/installation.md](references/installation.md)           |
| Find, create, select, navigate, or close pages              | [references/pages-navigation.md](references/pages-navigation.md)   |
| Read the accessibility tree and refresh element UIDs        | [references/snapshots.md](references/snapshots.md)                 |
| Click, drag, hover, fill, or type                           | [references/input.md](references/input.md)                         |
| Handle dialogs or upload files                              | [references/dialogs-and-files.md](references/dialogs-and-files.md) |
| Capture a screenshot                                        | [references/screenshots.md](references/screenshots.md)             |
| Run page JavaScript, inspect styles, console, or Lighthouse | [references/script-console.md](references/script-console.md)       |
| Inspect network traffic                                     | [references/network.md](references/network.md)                     |
| Emulate a device or change viewport                         | [references/emulation.md](references/emulation.md)                 |
| Record or analyze performance                               | [references/performance.md](references/performance.md)             |
| Capture or inspect memory snapshots                         | [references/memory.md](references/memory.md)                       |
| Manage extensions, PWAs, or experimental tools              | [references/advanced-features.md](references/advanced-features.md) |

## Shared operating rules

- When the user expects a visible, persistent, signed-in browser, check `chrome-devtools status` before any page command. If it is not attached to the requested browser, follow [setup](references/setup.md); otherwise an implicit CLI startup may select a different browser/profile.
- Get the current page ID with `chrome-devtools list_pages`. Take a fresh snapshot before acting on an element; UIDs belong to the observed page state and can go stale after navigation or page changes.
- After an action that can change page state, inspect the resulting page before continuing. Use `--includeSnapshot true` when supported, or take another snapshot.
- Do not memorize the command catalogue. Check `chrome-devtools <command> --help` when an argument or command is uncertain; CLI commands and flags can change between releases.
- File paths for upload and output arguments refer to the machine running the browser/CLI daemon.

The upstream [Chrome DevTools CLI skill](https://github.com/ChromeDevTools/chrome-devtools-mcp/tree/main/skills/chrome-devtools-cli) and its [CLI reference](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/cli.md) are the source of command semantics. Consult them when a local CLI version differs from these focused examples.
