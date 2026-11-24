"""The one wire format every message sent through this tool carries, whichever SDK delivers it.

    Message from <session-name>@<sdk>
    Reply with: `python "<agentmsg>" <sdk> send <session-id> "<message>"`
    ---
    <text>

agentmsg builds the header from the sender's own session, so an agent never types its own name or
id. No recipient runtime attributes a message for us: Claude Code shows a raw-pipe message as
coming from an anonymous peer, and the Copilot runtime as a plain user turn. The header is the
only attribution that survives both, and the reply line spares the recipient a name lookup.

A sender that cannot be identified still gets its message through, marked as not answerable:

    Message from an unidentified sender
    Reply: not possible; the sender could not be identified.
    ---
    <text>
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sender:
    sdk: str
    id: str
    name: str


def compose(text: str, sender: Sender | None, agentmsg: str) -> str:
    if not text.strip():
        raise ValueError("refusing to send an empty message")
    if sender is None:
        header = ["Message from an unidentified sender",
                  "Reply: not possible; the sender could not be identified."]
    else:
        header = [f"Message from {sender.name or 'unnamed'}@{sender.sdk}",
                  f'Reply with: `python "{agentmsg}" {sender.sdk} send {sender.id} "<message>"`']
    return "\n".join([*header, "---", text])
