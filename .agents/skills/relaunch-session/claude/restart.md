# Relaunch Session — Claude Code

Run with `<sdk>` = `claude`.

- The agent is `$env:CLAUDE_PID`; the session is `$env:CLAUDE_CODE_SESSION_ID`.
- Exit: two Ctrl+C presses (first cancels the turn, second exits); a press is sent only while claude is still running.
- Relaunch line: `claude <kept launch args> <extra args> --resume <session id>`, with `-Prompt` text as claude's positional prompt.
- Dropped launch args: `--resume`, `--continue`, `--session-id`, `--fork-session`, `--from-pr`, `--teleport`, `--cloud`, the hidden `--remote` and `--prefill`, and positional prompts.
- Option arity is read from the installed `claude --help`. A hidden option is looked up by its definition literal in `claude.exe` (`"--agent-id <id>"`), which adds about ten seconds to the call; an option with no such literal takes no value, so a word after it counts as the positional prompt.
- `-ExtraArgs` also rejects `--help`, `--version`, `--print`/`-p`, and the hidden `--init-only`: each ends the launch without an interactive session.
- An extra `--add-dir` takes absolute paths of existing directories. Every `--add-dir` of the relaunch, kept or extra, that no accepted workspace trust covers is trusted for good in `~/.claude.json` (`projects[<repository root or directory>].hasTrustDialogAccepted`) between the exit and the relaunch, so claude starts without asking: an answer at its dialog holds only for that run.
- Beyond those rejections, the extra args' values and combinations go unchecked before the exit: `claude --version` prints without validating them. A combination claude refuses therefore fails in the launching shell after the exit, while the log still reads `Relaunched`; the user must then relaunch by hand.
