"""Send a message to a Claude Code session.

Two operations, matching :mod:`copilot_sdk`:

    find(name=None) -> [Session]          live sessions, optionally by name
    send(session_id, text, priority=...)  write a message to the inbox; returns its id

Claude Code publishes one record per live session under ``~/.claude/sessions/<pid>.json``,
naming the named pipe its inbox listens on. The token for that pipe is NOT in the record: it
lives in a sibling ``<pid>.<sha256 of the lowercased pipe path>.key``. A message is one auth line
and one message line, newline-delimited, over that pipe.

Standard library only. Windows only.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

SDK = "claude"
SESSIONS_DIR = Path.home() / ".claude" / "sessions"
#: Set by Claude Code in its agent's shells; the same id ``find`` reports.
ENV_SESSION_ID = "CLAUDE_CODE_SESSION_ID"

#: The inbox drops any frame larger than this, counting the auth line.
LINE_LIMIT = 1_048_576
#: The inbox silently drops a body identical to one it received this many seconds ago. On Windows
#: every sender shares one admission key, so the window spans senders, not just this one.
DEDUP_SECONDS = 30.0
#: Bodies recently written to each inbox, shared by every agentmsg process on this machine.
_RECENT = Path(tempfile.gettempdir()) / "agentmsg-claude-recent.json"


class SendError(RuntimeError):
    pass


@dataclass(frozen=True)
class Session:
    """A live session, identified by ``id``. Everything else is for humans to read."""

    id: str
    name: str
    sdk: str
    pid: int
    address: str
    status: str | None = None

    def describe(self) -> str:
        state = f" {self.status}" if self.status else ""
        return f"{self.id}  [{self.sdk}] {self.name!r}{state} pid={self.pid}"


def _token(pid: int, address: str) -> str | None:
    """The peer token published for this pipe.

    Deliberately the PEER token from the key file, not ``CLAUDE_CODE_MESSAGING_TOKEN``: the
    environment one is the child token, and a message presenting it is marked as self-sent.
    """
    digest = hashlib.sha256(address.lower().encode()).hexdigest()
    try:
        key = json.loads((SESSIONS_DIR / f"{pid}.{digest}.key").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    token = key.get("peerToken") if isinstance(key, dict) else None
    return token if isinstance(token, str) else None


def _session(record_path: Path) -> Session | None:
    """The session a record describes, if its inbox is reachable."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = int(record_path.stem)
    address, session_id = record.get("messagingSocketPath"), record.get("sessionId")
    if not (isinstance(address, str) and isinstance(session_id, str)):
        return None
    if _token(pid, address) is None:
        return None
    return Session(id=session_id, name=record.get("name") or "", sdk=SDK, pid=pid,
                   address=address, status=record.get("status"))


def find(name: str | None = None) -> list[Session]:
    """Live sessions with a reachable inbox, optionally filtered by exact name."""
    sessions = (_session(p) for p in SESSIONS_DIR.glob("*.json") if p.stem.isdigit())
    return [s for s in sessions if s is not None and (name is None or s.name == name)]


def _fingerprint(session_id: str, text: str) -> str:
    return hashlib.sha256(f"{session_id}\0{text}".encode()).hexdigest()


def _recent_bodies() -> dict[str, float]:
    """Body fingerprints still inside the inbox's dedup window, with when each was written."""
    try:
        recent = json.loads(_RECENT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cutoff = time.time() - DEDUP_SECONDS
    return {k: t for k, t in recent.items() if t > cutoff}


def _refuse_duplicate(session_id: str, text: str) -> None:
    written = _recent_bodies().get(_fingerprint(session_id, text))
    if written is None:
        return
    age = time.time() - written
    raise SendError(
        f"this exact message reached {session_id} {age:.0f}s ago, and its inbox silently drops "
        f"a repeat for {DEDUP_SECONDS:.0f}s; reword it or send again in {DEDUP_SECONDS - age:.0f}s"
    )


def _remember(session_id: str, text: str) -> None:
    recent = _recent_bodies()
    recent[_fingerprint(session_id, text)] = time.time()
    try:
        _RECENT.write_text(json.dumps(recent), encoding="utf-8")
    except OSError:
        pass


def _frame(token: str, message_id: str, text: str, priority: str) -> bytes:
    auth = {"type": "auth", "token": token}
    message = {"msgV": 1, "msg_id": message_id, "type": "user",
               "message": {"role": "user", "content": text}, "priority": priority}
    return f"{json.dumps(auth)}\n{json.dumps(message)}\n".encode("utf-8")


def send(session_id: str, text: str, *, priority: str = "now") -> str:
    """Write *text* to the session's inbox. Returns the message id.

    ``priority`` is Claude Code's own field:

        now    preempts at the next tool boundary (the default, like a person typing)
        next   arrives as its own user turn after the current one finishes
        later  defers

    It is not translated into the Copilot runtime's ``immediate``: this one waits for a tool
    boundary, that one interrupts, and a sender choosing between runtimes should see that.
    """
    _refuse_duplicate(session_id, text)
    session = next((s for s in find() if s.id == session_id), None)
    if session is None:
        raise SendError(f"no live Claude Code session with id {session_id!r}")
    token = _token(session.pid, session.address)
    if token is None:
        raise SendError(f"the key file for {session.address} is unreadable")

    message_id = str(uuid.uuid4())
    frame = _frame(token, message_id, text, priority)
    if len(frame) > LINE_LIMIT:
        raise SendError(
            f"message is {len(frame)} bytes and the inbox drops anything over {LINE_LIMIT}"
        )
    try:
        with open(session.address, "r+b", buffering=0) as pipe:
            pipe.write(frame)
    except OSError as exc:
        raise SendError(f"cannot write to {session.address}: {exc}") from exc
    _remember(session_id, text)
    return message_id


def whoami() -> Session | None:
    """The calling agent's own session, or None when not run from a Claude Code agent's shell."""
    session_id = os.environ.get(ENV_SESSION_ID)
    if not session_id:
        return None
    session = next((s for s in find() if s.id == session_id), None)
    if session is None:
        raise SendError(f"your Claude Code session {session_id} has no reachable inbox")
    return session
