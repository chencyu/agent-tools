# A VS Code chat is missing from the list

The person names a chat open in VS Code, but `copilot list` does not show it.

## Suspect first: the chat runs on the local harness

VS Code runs each chat on one of two harnesses, and only one has an addressable session:

| VS Code harness      | Who drives the agent                        | Reachable               |
| -------------------- | ------------------------------------------- | ----------------------- |
| Copilot harness      | the agent host, running the Copilot runtime | yes, listed as `vscode` |
| legacy local harness | the chat extension itself, with no runtime  | no                      |

A chat on the local harness has no session for any host to deliver into, so it can never appear.

## What to tell the user

Report that the chat is unreachable because it runs on VS Code's local harness, and that only chats on the Copilot harness can receive messages. Then stop; choosing the harness is theirs.
