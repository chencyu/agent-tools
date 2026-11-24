---
name: agent-session-message
description: Must load before messaging another agent session. Do not message another agent session without this skill.
compatibility: Windows. Requires Python 3.10+ and a live target session on the same machine.
---

Use built-in tool instead of this skill while sender/recipient sessions are in same harness.
Github Copilot App <---> Github Copilot App: seek for harness built-in tools and use them.
Github Copilot VSCode (Copilot harness) <---> Github Copilot VSCode (Copilot harness): seek for harness built-in tools and use them.
Claude Code <---> Claude Code: `SendMessage`

# Agent Session Message

Send a message to another live agent session. The recipient takes it as a user turn through its own runtime; nothing is installed, configured, or run on its side.

```
python <skill>/scripts/agentmsg <sdk> <command> [args]
```

`<skill>` is this skill's base directory, stated at the top of this skill's context. `<sdk>` is `claude` or `copilot`, always named by the caller and never detected.

## The header is written for you

`send` finds your own session from your shell and opens every message with it:

```
Message from <session-name>@<sdk>
Reply with: `python "<agentmsg>" <sdk> send <session-id> "<message>"`
---
<text>
```

To answer a message, run its `Reply with` command with your text as `<message>`; for long or multi-line text, pass `-` instead and pipe the text in. If your session cannot be found, `send` still sends, warns you on stderr, and the header tells the recipient that no reply is possible.

## Your own session id

`send` needs none of this. Read it only to give someone your address yourself.

| You are            | Your id                                                                  |
| ------------------ | ------------------------------------------------------------------------ |
| Claude Code        | `CLAUDE_CODE_SESSION_ID` in your shell                                   |
| Copilot App or CLI | `COPILOT_AGENT_SESSION_ID` in your shell                                 |
| Copilot in VS Code | the built-in `get_current_session` tool, minus its `ahp-session:/` prefix |

In VS Code, `COPILOT_AGENT_SESSION_ID` is the runtime's internal id, not your address.

## Address by id, never by name

A name is a label; an id is the address. Several live sessions can carry the same name, so `list` reports every match and `send` accepts only an id. Read the matches and choose one. Nothing here guesses, and a name that resolved earlier may resolve to a different session now.

## Pages

| Step                    | Claude Code      | Copilot           |
| ----------------------- | ---------------- | ----------------- |
| Resolve a name to an id | `claude/list.md` | `copilot/list.md` |
| Send a message          | `claude/send.md` | `copilot/send.md` |

Read only the page for the SDK and command in hand. The flags differ per SDK because the runtimes differ; each page is the authority for its own.

Read the matching page under `diagnosis/` only when a command fails or the user asks you to troubleshoot.
