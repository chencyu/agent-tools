# Screenshots

Read this when the task needs a visual capture rather than a text/accessibility snapshot.

```powershell
chrome-devtools take_screenshot 1
chrome-devtools take_screenshot 1 --fullPage true --format "jpeg" --quality 80
chrome-devtools take_screenshot 1 --uid "1_3" --filePath "C:\temp\element.png"
```

Use a full-page capture for content beyond the viewport and a UID for an element capture. The CLI returns or saves the image according to the chosen flags; specify `--filePath` when a persistent artifact is needed. Output paths are interpreted on the daemon machine. Check `chrome-devtools take_screenshot --help` for supported formats and options.
