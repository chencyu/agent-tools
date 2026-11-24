# Dialogs and file upload

Read this only when a browser dialog must be handled or a file input must receive a file.

```powershell
chrome-devtools handle_dialog 1 accept
chrome-devtools handle_dialog 1 dismiss --promptText "text"
chrome-devtools upload_file 1 "1_5" "C:\path\to\file.txt"
```

Use `accept` or `dismiss` according to the user's intent; a prompt can receive `--promptText`. Find the file input UID from a fresh snapshot before uploading.

Upload paths are resolved on the machine running the browser daemon, not necessarily the agent's machine. The CLI may restrict file access to the OS temporary directory; check the daemon's configured path permissions before using a path outside it. Check `chrome-devtools upload_file --help` for current path and permission options.
