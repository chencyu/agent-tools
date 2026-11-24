# Emulation and viewport

Read this when changing viewport size, device-like conditions, or browser emulation.

```powershell
chrome-devtools emulate 1 --colorScheme "dark" --viewport "1920x1080"
chrome-devtools emulate 1 --networkConditions "Offline"
chrome-devtools resize_page 1 1920 1080
```

`emulate` changes emulated page conditions; `resize_page` changes the browser page's dimensions. To restore conditions or set CPU throttling, geolocation, or user agent, check `chrome-devtools emulate --help` and apply only the settings needed for the task.
