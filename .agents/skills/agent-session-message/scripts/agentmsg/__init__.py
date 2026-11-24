"""Find an agent session by name, then send it a message.

Two SDKs, named explicitly and never auto-detected:

    agentmsg.claude_sdk    Claude Code
    agentmsg.copilot_sdk   the Copilot runtime, in any of its three hosts

Both expose ``find(name=None)``, ``send(session_id, text, ...)`` and ``whoami()``. The option that
decides when the recipient reads a message is left in each runtime's own vocabulary -- Claude
Code's ``priority=now|next|later``, the Copilot runtime's ``mode=immediate|enqueue`` -- because the
two mechanisms differ, and a shared word would invent a translation neither runtime performs.
"""

from . import claude_sdk, copilot_sdk

SDKS = {"claude": claude_sdk, "copilot": copilot_sdk}

__all__ = ["SDKS", "claude_sdk", "copilot_sdk"]
