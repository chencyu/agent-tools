# Pages and navigation

Read this for page IDs, tabs, or navigation; read [snapshots](references/snapshots.md) before selecting page elements.

```powershell
chrome-devtools list_pages
chrome-devtools new_page "https://example.com"
chrome-devtools select_page 1
chrome-devtools navigate_page 1 --url "https://example.com"
chrome-devtools navigate_page 1 --type "reload" --ignoreCache true
chrome-devtools close_page 1
```

Use the current `pageId` returned by `list_pages`; do not assume IDs stay fixed after creating or closing pages. `select_page` changes the context for later calls, and `--bringToFront true` can foreground that page. `new_page` accepts a URL and can create a background page with `--background true`.

For back/forward navigation, timeout, before-unload handling, isolated contexts, or other flags, check `chrome-devtools navigate_page --help` or `chrome-devtools new_page --help`.
