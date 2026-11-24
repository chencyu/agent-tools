---
name: relaunch-session
description: Must load before exiting or restarting the running agent session. Do not exit or restart this session without this skill.
compatibility: Windows only; Claude Code or Copilot CLI launched from an interactive PowerShell prompt.
---

# Relaunch Session

The agent exits gracefully on Ctrl+C, which on Windows exists only as a console control event on the console the agent runs in; the tool shell sits on a different, hidden console. A restart is the launching shell running the launch again with `--resume <this session>`. `scripts/restart.ps1` (relative to this skill's directory) does both: it starts a windowless worker that, once the tool call running the script has finished, sends Ctrl+C to the agent's console until the agent exits and, once it is gone, types the relaunch line into the launching PowerShell prompt. Input typed while that shell is still returning to its prompt can be discarded, so the worker first types a probe key and sends the line only after the shell has echoed it.

`<sdk>` is `claude` or `copilot`, always named by the caller and never detected.

## Run

- Restart: `& "<skill dir>\scripts\restart.ps1" <sdk>`
- Restart and keep working: `& "<skill dir>\scripts\restart.ps1" <sdk> -Prompt '<next step>'`. The text arrives as the resumed session's first user message, so the agent continues without the user; name the concrete next step: the resumed agent sees the full history but takes this message as its turn's instruction. Any text, including newlines and non-ASCII, passes intact.
- Restart with added options: `-ExtraArgs '<option>', '<value>', ...`. They follow the kept launch args, so the agent's own parser settles a repeat: a single-value option takes the added value, a repeatable one keeps both. An original arg cannot be removed. Pass nothing but options, each with its values. Positionals, `--`, session-selection options, and those your sdk page lists are rejected before the agent exits.
- Relaunch later: add `-DelaySeconds <n>`. The launching shell waits between the exit and the relaunch, shows the user the relaunch time, and cancels the relaunch if the user presses Ctrl+C during the wait.
- Exit without relaunch: `& "<skill dir>\scripts\restart.ps1" <sdk> -ExitOnly`

Make it the last tool call of the turn and say everything to the user before it: the exit follows the call's return and cuts off whatever comes after.

## Pages

Read the page for your sdk before running: `claude/restart.md` or `copilot/restart.md`.

## Gotchas

- Do not look up, reconstruct, or re-pass the launch args; `-ExtraArgs` carries only what to add. The script reads the agent's own command line, drops what chose or seeded the conversation (session-selection options, initial prompt), and appends the extra args and `--resume <session id>`.
- Do not use `Stop-Process` or `taskkill`: they skip the graceful shutdown. Do not propose a wrapper, alias, or profile change: the relaunch is typed into the prompt that already launched the agent.
- If the script refuses because the agent's parent is not PowerShell, report that; exiting anyway would leave nothing to relaunch.
- After resuming, find your own outcome in `%TEMP%\relaunch-session.log`: each line is `<time> <sdk> <session id> <result> <typed line>`, and several sessions share the file, so match your session id rather than reading the last line. Results: `Relaunched`, `Exited`, `AttachFailed`, `StillRunning`, `ShellNotReading`, `InputFailed`. A `TrustFailed` line, whose last field is the error, precedes the result when trust for an extra arg could not be granted; the relaunch then runs and the agent asks for that trust itself.
- `Relaunched` means the shell echoed the probe and the line was typed, not that the line ran. With `-Prompt`, the line deletes `%TEMP%\<sdk>-restart-<session id>.prompt` as it runs; if that file still exists, the line never executed.
