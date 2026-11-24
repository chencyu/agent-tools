# Page snapshots and element UIDs

Read this when you need to understand page structure or obtain targets for browser actions.

```powershell
chrome-devtools take_snapshot 1
chrome-devtools take_snapshot 1 --verbose true
```

The snapshot is an accessibility-tree view. Use its current `uid` values with the input commands; do not invent a UID from page text, an earlier snapshot, or a different page. A UID can become stale after navigation or DOM changes, so take a new snapshot before acting again.

Use `--filePath` to save a large snapshot. For an action's updated state, use `--includeSnapshot true` if that action supports it. Check `chrome-devtools take_snapshot --help` for output options supported by the installed version.
