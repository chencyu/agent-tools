# Heap snapshots

Read this only for browser memory investigations.

```powershell
chrome-devtools take_heapsnapshot 1 "C:\temp\page.heapsnapshot"
```

Memory-debugging commands require the daemon to be started with `--memoryDebugging=true`. They can summarize or compare snapshots and inspect classes, nodes, edges, dominators, retainers, retaining paths, object details, and duplicate strings. Use `chrome-devtools <command> --help` for the installed version's exact command names and arguments.

Heap snapshots can contain page data. Save them only to an appropriate location and close loaded snapshots when finished.
