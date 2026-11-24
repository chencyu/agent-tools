# copilot send

```
python <skill>/scripts/agentmsg copilot send <id> "text" [--mode immediate|enqueue] [--json]
```

The sender header is added for you; see the skill's main page.

Text may be `-` to read stdin, which is how anything long or multi-line should be passed.

## Mode decides when the message is read

`--mode` is the input box's own choice, and the default is what plain Enter does.

| mode                  | Input box  | Delivery                                                                          |
| --------------------- | ---------- | --------------------------------------------------------------------------------- |
| `immediate` (default) | Enter      | taken at the target's next boundary, together with everything else pending for it |
| `enqueue`             | Ctrl+Enter | waits, and the runtime then hands the agent exactly one queued item per turn      |

Measured on a live session: three messages sent with `enqueue` produced one delivery and left two waiting, while a burst sent with `immediate` arrived together in one turn. So `enqueue` turns a burst into a backlog that drains slower than it fills.

Keep the default. Choose `enqueue` only when the message is genuinely lower priority than whatever the target is doing, and never for several messages in a row.
