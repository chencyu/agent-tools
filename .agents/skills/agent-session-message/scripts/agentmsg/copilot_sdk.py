"""Send a message to a Copilot SDK session.

Two operations, matching :mod:`claude_sdk`:

    find(name=None) -> [Session]      live sessions, optionally by name
    send(session_id, text, mode=...)  queue a message; returns its id

One runtime, three hosts. Each publishes its sessions differently, so a search covers all three:

    app     the desktop app       WebSocket over TCP, ~/.copilot/run/{ws.port,ws.token}
    cli     the standalone CLI    JSON-RPC over TCP with LSP framing, only with --ui-server
    vscode  VS Code's agent host  WebSocket over a named pipe, speaking AHP

VS Code has two harnesses. Only the Copilot harness, whose agent host runs this runtime and names
sessions ``ahp-session:/<uuid>``, has an addressable session; the local harness has none.

Why a CLI session needs ``--ui-server``, established by reading the runtime rather than guessing:
the embedded JSON-RPC server is created only as ``t.uiServer ? {...} : undefined``, from a flag
with no environment binding and no settings key. The App and VS Code satisfy it themselves by
spawning ``copilot --server --stdio``; a CLI a person started by hand has no RPC surface.

Standard library only. Windows only.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
import re
import socket
import struct
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

SDK = "copilot"
COPILOT_HOME = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
RUN_DIR = COPILOT_HOME / "run"
#: Set by every Copilot host in its agent's shells: the runtime's own id for the session.
ENV_SESSION_ID = "COPILOT_AGENT_SESSION_ID"

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_AHP_ROOT = "ahp-root://"
_AHP_VERSION = "0.10.0"
_VSCODE_SCHEME = "ahp-session:/"
_VSCODE_PRODUCTS = ("Code", "Code - Insiders")
#: How long VS Code's agent host gets to echo a dispatched message before the send is failed.
_ECHO_SECONDS = 10.0


class SendError(RuntimeError):
    pass


@dataclass(frozen=True)
class Session:
    """A live session. ``id`` is a bare UUID on every host; ``route`` says how to reach it."""

    id: str
    name: str
    sdk: str
    host: str
    route: dict[str, Any] = field(default_factory=dict, repr=False)
    status: str | None = None

    def describe(self) -> str:
        state = f" {self.status}" if self.status else ""
        return f"{self.id}  [{self.sdk}/{self.host}] {self.name!r}{state}"


# --------------------------------------------------------------------------- #
# transports
# --------------------------------------------------------------------------- #
class _WebSocket:
    """Minimal RFC 6455 text-frame client over a TCP socket or a Windows named pipe."""

    def __init__(self, stream, host_header: str, path: str, origin: str | None = None,
                 timeout: float = 15.0):
        self._s = stream
        self._buf = b""
        self._timeout = timeout
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            f"GET {path} HTTP/1.1", f"Host: {host_header}", "Upgrade: websocket",
            "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13",
        ]
        if origin:
            lines.append(f"Origin: {origin}")
        self._write(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self._read(4096)
            if not chunk:
                raise SendError("connection closed during the WebSocket handshake")
            head += chunk
        header, _, self._buf = head.partition(b"\r\n\r\n")
        status = header.decode("latin1").split("\r\n")[0]
        if "101" not in status:
            raise SendError(f"WebSocket upgrade rejected: {status}")
        expected = base64.b64encode(hashlib.sha1((key + _WS_GUID).encode()).digest()).decode()
        if expected.encode() not in header:
            raise SendError("Sec-WebSocket-Accept mismatch; this is not the peer we expect")

    def _write(self, data: bytes) -> None:
        if isinstance(self._s, socket.socket):
            self._s.sendall(data)
        else:
            self._s.write(data)

    def _read(self, size: int) -> bytes:
        if isinstance(self._s, socket.socket):
            return self._s.recv(size)
        return self._s.read(size)

    def send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            header = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 1 << 16:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        self._write(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def messages(self, timeout: float | None = None) -> Iterator[dict[str, Any]]:
        deadline = time.monotonic() + (self._timeout if timeout is None else timeout)
        while True:
            frame = self._take()
            if frame is None:
                if time.monotonic() >= deadline:
                    return
                try:
                    chunk = self._read(65536)
                except OSError:
                    return
                if not chunk:
                    return
                self._buf += chunk
                continue
            opcode, payload = frame
            if opcode == 0x8:
                return
            if opcode != 0x1:
                continue
            try:
                yield json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

    def _take(self) -> tuple[int, bytes] | None:
        buf = self._buf
        if len(buf) < 2:
            return None
        opcode, length, offset = buf[0] & 0x0F, buf[1] & 0x7F, 2
        if length == 126:
            if len(buf) < 4:
                return None
            length, offset = struct.unpack("!H", buf[2:4])[0], 4
        elif length == 127:
            if len(buf) < 10:
                return None
            length, offset = struct.unpack("!Q", buf[2:10])[0], 10
        if len(buf) < offset + length:
            return None
        self._buf = buf[offset + length:]
        return opcode, buf[offset:offset + length]

    def close(self) -> None:
        try:
            self._write(struct.pack("!BB", 0x88, 0x80) + os.urandom(4))
        except OSError:
            pass
        try:
            self._s.close()
        except OSError:
            pass


class _LspRpc:
    """JSON-RPC 2.0 with ``Content-Length`` framing, as the CLI's server speaks."""

    def __init__(self, sock: socket.socket, timeout: float):
        self._s = sock
        self._buf = b""
        self._ids = itertools.count(1)
        self._s.settimeout(timeout)

    def request(self, method: str, params: dict[str, Any]) -> Any:
        rid = next(self._ids)
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                           "params": params}).encode()
        self._s.sendall(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        while True:
            message = self._next()
            if message.get("id") != rid:
                continue
            if "error" in message:
                raise SendError(f"{method}: {message['error'].get('message')}")
            return message.get("result")

    def _next(self) -> dict[str, Any]:
        while True:
            head, sep, rest = self._buf.partition(b"\r\n\r\n")
            if sep:
                length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                               if line.lower().startswith(b"content-length:")), None)
                if length is not None and len(rest) >= length:
                    self._buf = rest[length:]
                    return json.loads(rest[:length].decode("utf-8"))
            chunk = self._s.recv(65536)
            if not chunk:
                raise SendError("the CLI server closed the connection")
            self._buf += chunk

    def close(self) -> None:
        try:
            self._s.close()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# host: the desktop app
# --------------------------------------------------------------------------- #
def _app_connect(timeout: float = 15.0) -> _WebSocket:
    try:
        port = (RUN_DIR / "ws.port").read_text(encoding="utf-8").split()[0]
        token = (RUN_DIR / "ws.token").read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError) as exc:
        raise SendError(f"the Copilot App is not running ({RUN_DIR} has no port/token)") from exc
    sock = socket.create_connection(("127.0.0.1", int(port)), timeout=timeout)
    ws = _WebSocket(sock, f"127.0.0.1:{port}", f"/?token={token}",
                    origin="tauri://localhost", timeout=timeout)
    for _ in ws.messages(1.0):  # drain the greeting burst
        break
    return ws


def _app_request(ws: _WebSocket, command: str, reply_type: str | None = None,
                 **params: Any) -> dict[str, Any]:
    """Some App replies echo ``request_id``; others carry only their own ``type``.

    ``session_dispatch_state`` events echo ``request_id`` too, but they report
    progress and arrive before the real reply, so they are skipped.
    """
    rid = str(uuid.uuid4())
    ws.send_json({"type": command, "request_id": rid, **params})
    for message in ws.messages():
        if message.get("type") == "error":
            raise SendError(message.get("message", "unknown error"))
        if message.get("type") == "session_dispatch_state":
            continue
        if message.get("request_id") == rid or message.get("type") == reply_type:
            return message
    raise SendError(f"no reply to {command!r}")


def _app_find() -> list[Session]:
    """Project sessions and general chats; the App lists the two separately."""
    try:
        ws = _app_connect()
    except (OSError, SendError):
        return []
    try:
        workspaces = _app_request(ws, "list_workspaces").get("workspaces") or []
        chats = _app_request(ws, "list_general_chat_sessions",
                             reply_type="general_chat_sessions_list").get("sessions") or []
    except (OSError, SendError):
        return []
    finally:
        ws.close()
    projects = [(w.get("name"), w.get("session") or {}) for w in workspaces]
    entries = [(name, s.get("sessionId"), s.get("isRunning")) for name, s in projects]
    entries += [(c.get("title"), c.get("id"), c.get("isRunning")) for c in chats]
    return [Session(id=sid, name=name or "", sdk=SDK, host="app",
                    status="in-progress" if running else "idle")
            for name, sid, running in entries if isinstance(sid, str)]


def _app_send(session: Session, text: str, mode: str) -> str:
    # Waking a cold session restarts its runtime first, which can outlast the default wait.
    ws = _app_connect(timeout=30.0)
    try:
        reply = _app_request(ws, "send_message", session_id=session.id, prompt=text,
                             delivery_mode=mode)
    finally:
        ws.close()
    message_id = reply.get("message_id")
    if not message_id:
        raise SendError(f"the App returned no message id: {reply}")
    return message_id


# --------------------------------------------------------------------------- #
# host: the standalone CLI, started with --ui-server
# --------------------------------------------------------------------------- #
def _cli_endpoints() -> list[tuple[str, int]]:
    """TCP ports listened on by processes that hold a session open.

    A session's runtime holds ``session-state/<id>/inuse.<pid>.lock``; its ``--ui-server`` is
    whichever port that pid listens on. Nothing else publishes the port.
    """
    pids = {
        int(m["pid"])
        for lock in COPILOT_HOME.glob("session-state/*/inuse.*.lock")
        if (m := re.fullmatch(r"inuse\.(?P<pid>\d+)\.lock", lock.name))
    }
    if not pids:
        return []
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    endpoints = []
    for line in out.splitlines():
        # proto, local, foreign, state, pid. A listener's foreign address is port 0; matching
        # on that rather than the state column survives a localised netstat.
        parts = line.split()
        if len(parts) != 5 or not parts[2].endswith(":0") or not parts[4].isdigit():
            continue
        host, _, port = parts[1].rpartition(":")
        if int(parts[4]) in pids and port.isdigit():
            endpoints.append((host.strip("[]"), int(port)))
    return endpoints


def _cli_connect(host: str, port: int, timeout: float = 8.0) -> _LspRpc:
    rpc = _LspRpc(socket.create_connection((host, port), timeout=timeout), timeout)
    rpc.request("connect", {})
    return rpc


def _cli_name(session_id: str) -> str:
    """The session's name as the runtime records it in ``workspace.yaml``.

    ``session.getMetadata`` answers ``{}`` for a live session, so the file is the only source.
    The runtime writes a long name as a YAML block scalar, ``name: |-`` with the text indented on
    the lines after it.
    """
    path = COPILOT_HOME / "session-state" / session_id / "workspace.yaml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for i, line in enumerate(lines):
        if not line.startswith("name:"):
            continue
        value = line.removeprefix("name:").strip()
        if value not in {"|", "|-", ">", ">-"}:
            return value.strip("'\"")
        block = itertools.takewhile(lambda l: l.startswith((" ", "\t")) or not l, lines[i + 1:])
        return (" " if value.startswith(">") else "\n").join(l.strip() for l in block).strip()
    return ""


def _cli_find() -> list[Session]:
    sessions = []
    for host, port in _cli_endpoints():
        try:
            rpc = _cli_connect(host, port, timeout=5.0)
        except (OSError, SendError):
            continue
        try:
            foreground = rpc.request("session.getForeground", {}) or {}
        except (OSError, SendError):
            continue
        finally:
            rpc.close()
        session_id = foreground.get("sessionId")
        if session_id:
            sessions.append(Session(id=session_id, name=_cli_name(session_id), sdk=SDK,
                                    host="cli", route={"addr": (host, port)}))
    return sessions


def _cli_send(session: Session, text: str, mode: str) -> str:
    rpc = _cli_connect(*session.route["addr"])
    try:
        rpc.request("session.resume", {"sessionId": session.id})
        result = rpc.request("session.send", {
            "sessionId": session.id, "prompt": text, "mode": mode,
        }) or {}
    finally:
        rpc.close()
    message_id = result.get("messageId")
    if not message_id:
        raise SendError(f"the CLI returned no message id: {result}")
    return message_id


# --------------------------------------------------------------------------- #
# host: VS Code's agent host (the Copilot harness)
# --------------------------------------------------------------------------- #
def _vscode_entries() -> list[dict[str, Any]]:
    """One endpoint record per running VS Code window's agent host."""
    appdata = Path(os.environ["APPDATA"])
    entries = []
    for product in _VSCODE_PRODUCTS:
        for path in sorted((appdata / product / "agent-host/local-endpoint/entries").glob("*.json")):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if entry.get("schemaVersion") == 2 and isinstance(entry.get("connectionToken"), str):
                entries.append(entry)
    return entries


def _vscode_connect(entry: dict[str, Any], timeout: float = 15.0) -> _WebSocket:
    pipe = open(entry["endpoint"]["path"], "r+b", buffering=0)
    return _WebSocket(pipe, "localhost", f"/?tkn={entry['connectionToken']}", timeout=timeout)


class _Ahp:
    def __init__(self, ws: _WebSocket):
        self.ws = ws
        self._ids = itertools.count(1)

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        rid = next(self._ids)
        self.ws.send_json({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        for message in self.ws.messages():
            if message.get("id") != rid:
                continue
            if "error" in message:
                raise SendError(f"{method}: {message['error'].get('message')}")
            return message.get("result") or {}
        raise SendError(f"no reply to {method!r}")

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.ws.send_json({"jsonrpc": "2.0", "method": method, "params": params})

    def sessions(self) -> list[dict[str, Any]]:
        items, cursor = [], None
        while True:
            params: dict[str, Any] = {"channel": _AHP_ROOT, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            result = self.request("listSessions", params)
            items.extend(result.get("items") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                return items


def _ahp_open(entry: dict[str, Any], timeout: float = 15.0) -> _Ahp:
    ahp = _Ahp(_vscode_connect(entry, timeout))
    try:
        ahp.request("initialize", {
            "channel": _AHP_ROOT, "protocolVersions": [_AHP_VERSION],
            "clientId": f"agentmsg-{uuid.uuid4()}",
            "clientInfo": {"name": "agentmsg", "version": "3.0.0"},
        })
    except BaseException:
        ahp.ws.close()
        raise
    return ahp


def _describe_status(value: Any) -> str | None:
    """The agent host's status bitfield: 1 idle, 8 in progress, 16 with 8 input needed,
    64 archived."""
    if not isinstance(value, int):
        return None
    if value & 24 == 24:
        return "input-needed"
    state = "in-progress" if value & 8 else "idle" if value & 1 else None
    return state and state + (" archived" if value & 64 else "")


def _vscode_find() -> list[Session]:
    sessions = []
    for entry in _vscode_entries():
        try:
            ahp = _ahp_open(entry, timeout=8.0)
        except (OSError, SendError):
            continue
        try:
            summaries = ahp.sessions()
        except (OSError, SendError):
            continue
        finally:
            ahp.ws.close()
        for summary in summaries:
            uri, chat = summary.get("resource"), summary.get("defaultChat")
            if not (isinstance(uri, str) and uri.startswith(_VSCODE_SCHEME)
                    and isinstance(chat, str)):
                continue
            # The App's and CLI's sessions show up here too, flagged external: the agent host
            # only read them from disk, and a message sent through it is accepted and then lost.
            # Their own host is the only route, so they are reachable only while it runs.
            if (summary.get("_meta") or {}).get("vscode.external"):
                continue
            sessions.append(Session(
                id=uri.removeprefix(_VSCODE_SCHEME), name=summary.get("title") or "", sdk=SDK,
                host="vscode", route={"entry": entry, "chat": chat},
                status=_describe_status(summary.get("status")),
            ))
    return sessions


def _vscode_runtime_ids(session: Session) -> set[str]:
    """Runtime session ids seen in this chat's model-call metadata -- the only place the agent
    host relates its own id to the ``COPILOT_AGENT_SESSION_ID`` its agent's shells carry."""
    try:
        ahp = _ahp_open(session.route["entry"])
    except (OSError, SendError):
        return set()
    try:
        snapshot = json.dumps(ahp.request("subscribe", {"channel": session.route["chat"]}))
    except (OSError, SendError):
        return set()
    finally:
        ahp.ws.close()
    return set(re.findall(r'"sdkSessionId": "([^"]+)"', snapshot))


def _echoed(ws: _WebSocket, action_id: str, timeout: float) -> bool:
    """Whether the agent host broadcast the dispatched action back, which it does only once it
    has applied the action to the chat.

    The wait runs on a thread because a read on a Windows named pipe has no timeout.
    """
    seen = threading.Event()

    def watch() -> None:
        for message in ws.messages(timeout):
            params = message.get("params")
            action = params.get("action") if isinstance(params, dict) else None
            if isinstance(action, dict) and action.get("id") == action_id:
                seen.set()
                return

    threading.Thread(target=watch, daemon=True).start()
    return seen.wait(timeout)


def _vscode_send(session: Session, text: str, mode: str) -> str:
    channel = session.route["chat"]
    ahp = _ahp_open(session.route["entry"])
    try:
        ahp.request("subscribe", {"channel": channel})
        message_id = str(uuid.uuid4())
        ahp.notify("dispatchAction", {
            "channel": channel, "clientSeq": 1,
            "action": {
                "type": "chat/pendingMessageSet",
                "kind": "steering" if mode == "immediate" else "queued",
                "id": message_id,
                "message": {"text": text, "origin": {"kind": "agent"}},
            },
        })
        if not _echoed(ahp.ws, message_id, _ECHO_SECONDS):
            raise SendError(f"VS Code's agent host did not accept the message within "
                            f"{_ECHO_SECONDS:.0f}s")
        return message_id
    finally:
        ahp.ws.close()


# --------------------------------------------------------------------------- #
# the operations
# --------------------------------------------------------------------------- #
_SENDERS: dict[str, Callable[[Session, str, str], str]] = {
    "app": _app_send, "cli": _cli_send, "vscode": _vscode_send,
}


def find(name: str | None = None) -> list[Session]:
    """Live sessions across all three Copilot hosts, optionally filtered by exact name."""
    sessions = _app_find() + _cli_find() + _vscode_find()
    return [s for s in sessions if name is None or s.name == name]


def send(session_id: str, text: str, *, mode: str = "immediate") -> str:
    """Queue *text* for the session with this id. Returns the message id.

    ``mode`` is the runtime's own word, and the default matches plain Enter in the input box:

        immediate  "steer" -- taken at the target's next boundary, together with every other
                   pending steer.
        enqueue    "queue" -- Ctrl+Enter. The runtime hands the agent exactly ONE queued item per
                   turn, so a burst becomes a backlog.
    """
    session_id = session_id.removeprefix(_VSCODE_SCHEME)
    session = next((s for s in find() if s.id == session_id), None)
    if session is None:
        raise SendError(f"no live Copilot session with id {session_id!r}")
    return _SENDERS[session.host](session, text, mode)


def whoami() -> Session | None:
    """The calling agent's own session, or None when not run from a Copilot agent's shell.

    The App and the CLI address a session by its runtime id. VS Code's agent host uses an id of
    its own, so there the runtime id has to be found inside a running chat instead.
    """
    runtime_id = os.environ.get(ENV_SESSION_ID)
    if not runtime_id:
        return None
    sessions = find()
    for session in sessions:
        if session.id == runtime_id:
            return session
    for session in sessions:
        running = session.host == "vscode" and (session.status or "").startswith("in-progress")
        if running and runtime_id in _vscode_runtime_ids(session):
            return session
    raise SendError(f"your Copilot session {runtime_id} is not among the reachable sessions")
