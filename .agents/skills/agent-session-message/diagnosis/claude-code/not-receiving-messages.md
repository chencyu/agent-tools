# Claude Code is not receiving messages

`send` returned a `message_id`, yet nothing reached the target's transcript. The inbox never acknowledges, so the causes below all look like a successful send from the sender's side. `send` already refuses an identical message to the same session within 30 seconds, so a duplicate is not the cause.

## Suspect first: inbound is held

Claude Code gates peer messages behind `crossSessionInbound`. Only `accept` puts a message straight into the session; under `hold` it waits for the recipient to review and approve it.

Read `~/.claude/settings.json` and look for:

```json
"crossSessionInbound": "accept"
```

Absent or `"hold"` explains the symptom. **Report this to the user; do not edit their settings.** Their own file may also be overridden, and the runtime distinguishes three sources, so tell them which one applies:

| Source                        | Effect                                                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- |
| user `settings.json`          | the normal place to set `accept`                                                                              |
| repository settings           | may only tighten, so a repo `hold` defeats a user `accept`; removable, or excludable with `--setting-sources` |
| organization managed settings | outranks everything; only an admin can change it                                                              |

## If inbound is already `accept`

The recipient dropped the message on admission, for one of two reasons nobody outside it can observe:

| Cause                                       | Note                                                                                                                     |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| its rate limit is exhausted                 | on Windows every sender shares one limit, because admission is keyed on the peer process id and that check is POSIX-only |
| its pending queue already holds 50 messages | the recipient has not reached a boundary to drain it                                                                     |

Both clear with time. Report that the recipient is saturated; a later message, worded differently, can go once it has caught up.
