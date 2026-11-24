# Performance traces

Read this when recording or analyzing page performance.

```powershell
chrome-devtools performance_start_trace 1 --reload true --autoStop true --filePath "C:\temp\trace.json.gz"
chrome-devtools performance_stop_trace 1
chrome-devtools performance_analyze_insight 1 "1" "LCPBreakdown"
```

Use `performance_stop_trace` when recording with `--autoStop false`. Analyze an insight using the IDs and name returned by the trace; don't assume example IDs apply to another trace. Check `--help` for current trace, output, and analysis options. Performance tools may retrieve CrUX field data; see the upstream [privacy and configuration notes](https://github.com/ChromeDevTools/chrome-devtools-mcp#disclaimers) before running an audit where external data use matters.
