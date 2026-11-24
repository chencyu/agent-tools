# claude list

```
python <skill>/scripts/agentmsg claude list [--name NAME] [--json]
```

Each line is `<id>  [claude] '<name>' <status> pid=<pid>`.

## Gotchas

- Only sessions whose inbox token is readable appear. A running session can be omitted, so absence means unreachable now, not nonexistent.
- The runtime renames a session that claims a name already held by a live one, appending a suffix. A name you did not choose, such as `<base>-d4`, is therefore a collision survivor and may belong to unrelated work — confirm what a session is before messaging it.
- `--name` matches exactly and may return several sessions.
