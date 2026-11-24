# Extensions, PWAs, and experimental tools

Read this only when a task explicitly needs one of these advanced capabilities. Availability depends on daemon startup flags and CLI version.

- **Extensions:** `list_extensions`, `install_extension`, `uninstall_extension`, `reload_extension`, `trigger_extension_action`.
- **Progressive Web Apps:** requires `--categoryPwa=true`; commands include `install_pwa`, `launch_pwa`, `get_os_app_state`, and `uninstall_pwa`.
- **Experimental tools:** disabled by default; enable only the relevant category/feature flag at daemon startup. Examples include coordinate clicks, screencast, WebMCP, and third-party developer tools.

Check `chrome-devtools <command> --help` and the upstream [CLI skill](https://github.com/ChromeDevTools/chrome-devtools-mcp/tree/main/skills/chrome-devtools-cli) before enabling a feature. Avoid enabling unrelated categories.
