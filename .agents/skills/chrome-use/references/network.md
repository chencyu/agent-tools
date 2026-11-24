# Network requests

Read this when diagnosing requests made by a page.

```powershell
chrome-devtools list_network_requests 1
chrome-devtools list_network_requests 1 --pageSize 50 --pageIdx 0
chrome-devtools get_network_request 1 --reqid 1
```

Use the request ID from the current page's network list. Pagination uses a zero-based page index. Filters such as resource type and preserved requests, and options to save request/response data, vary by CLI version; check the matching command's `--help`.
