# Page input and interaction

Read this for clicking, dragging, hovering, keyboard input, or filling controls. Obtain fresh element UIDs from a [page snapshot](references/snapshots.md) first.

```powershell
chrome-devtools click 1 "1_3"
chrome-devtools drag 1 "1_3" "1_8"
chrome-devtools hover 1 "1_3"
chrome-devtools fill 1 "1_5" "some text"
chrome-devtools press_key 1 "Control+A"
chrome-devtools type_text 1 "replacement text"
```

`fill` targets an input, textarea, or select control; for a select, pass the option's visible text. `type_text` types into the currently focused control, so focus it first when needed. `press_key` accepts key names and combinations such as `Enter`, `Escape`, or `Control+A`.

Use `--includeSnapshot true` on supported actions to inspect the resulting page in the same call. Re-snapshot after navigation or any structural change before reusing UIDs. Consult each command's `--help` for options such as double-clicking or submitting with a key.
