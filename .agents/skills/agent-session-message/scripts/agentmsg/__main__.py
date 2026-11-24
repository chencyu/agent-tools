"""Command line: ``python <skill>/scripts/agentmsg <sdk> list|send``.

    agentmsg copilot list [--name NAME] [--json]
    agentmsg copilot send <session-id> "text" [--mode immediate|enqueue] [--json]
    agentmsg claude  list [--name NAME] [--json]
    agentmsg claude  send <session-id> "text" [--priority now|next|later] [--json]

The SDK is always named by the caller. ``list`` turns a name into an id; ``send`` takes an id and
nothing else, so there is no name-matching in the send path and nothing to guess at when two
sessions share a title.

The sender is never named on the command line. ``send`` finds the calling agent's own session from
its shell's environment and writes the header in ``message.py`` from it; when that fails the
message still goes, with a warning that the recipient cannot reply.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as a directory, this file's own folder is sys.path[0] and the package is not importable by
# name until its parent is on the path. That is what lets the tool run with no install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentmsg import SDKS  # noqa: E402
from agentmsg.message import Sender, compose  # noqa: E402

AGENTMSG = str(Path(__file__).resolve().parent)


def _identify() -> tuple[Sender | None, str | None]:
    """The calling agent's own session, or None and why it could not be found."""
    found: list[Sender] = []
    problems: list[str] = []
    for name, sdk in SDKS.items():
        try:
            session = sdk.whoami()
        except sdk.SendError as exc:
            problems.append(str(exc))
            continue
        if session is not None:
            found.append(Sender(name, session.id, session.name))
    if len(found) == 1:
        return found[0], None
    if found:
        return None, "this shell belongs to more than one agent session"
    return None, "; ".join(problems) or "not running inside an agent session"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentmsg")
    parser.add_argument("sdk", choices=sorted(SDKS), help="which SDK hosts the target")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="live sessions, with their ids")
    listing.add_argument("--name", default=None, help="only sessions with this exact name")
    listing.add_argument("--json", action="store_true")

    sending = sub.add_parser("send", help="send a message to one session id")
    sending.add_argument("session_id")
    sending.add_argument("text", nargs="?", help="message text; omit or '-' to read stdin")
    sending.add_argument("--priority", choices=("now", "next", "later"), default="now",
                         help="Claude Code only. now (default) preempts at the next tool "
                              "boundary; next waits for its own turn; later defers")
    sending.add_argument("--mode", choices=("immediate", "enqueue"), default="immediate",
                         help="Copilot only. immediate (default) is plain Enter: taken at the "
                              "next boundary with anything else pending. enqueue is Ctrl+Enter: "
                              "the runtime hands over exactly one queued item per turn")
    sending.add_argument("--json", action="store_true")
    return parser


def _list(sdk, args: argparse.Namespace) -> int:
    sessions = sdk.find(args.name)
    if args.json:
        print(json.dumps([{"id": s.id, "name": s.name, "sdk": s.sdk,
                           "host": getattr(s, "host", args.sdk), "status": s.status}
                          for s in sessions], ensure_ascii=False))
        return 0
    for session in sessions:
        print(session.describe())
    if not sessions:
        print("no live sessions", file=sys.stderr)
        return 3
    return 0


def _send(sdk, args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.text in (None, "-") else args.text
    sender, problem = _identify()
    try:
        text = compose(text, sender, AGENTMSG)
    except ValueError as exc:
        raise sdk.SendError(str(exc)) from exc
    option = {"priority": args.priority} if args.sdk == "claude" else {"mode": args.mode}
    message_id = sdk.send(args.session_id, text, **option)
    if problem:
        print(f"warning: {problem}; the recipient cannot reply.", file=sys.stderr)
    if args.json:
        origin = f"{sender.name}@{sender.sdk} {sender.id}" if sender else None
        print(json.dumps({"session_id": args.session_id, "message_id": message_id,
                          "sdk": args.sdk, "from": origin, **option}, ensure_ascii=False))
    else:
        print(f"sent to {args.session_id} (message {message_id})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    sdk = SDKS[args.sdk]
    command = _list if args.command == "list" else _send
    try:
        return command(sdk, args)
    except sdk.SendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
