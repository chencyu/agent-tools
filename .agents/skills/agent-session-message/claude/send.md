# claude send

```
python <skill>/scripts/agentmsg claude send <id> "text" [--priority now|next|later] [--json]
```

The sender header is added for you; see the skill's main page.

Text may be `-` to read stdin, which is how anything long or multi-line should be passed.

## Priority decides when the message is read

| priority        | Delivery                                                |
| --------------- | ------------------------------------------------------- |
| `now` (default) | preempts at the recipient's next tool boundary          |
| `next`          | arrives as its own user turn after the current one ends |
| `later`         | defers                                                  |

`now` waits for a tool boundary; it does not interrupt mid-inference.
