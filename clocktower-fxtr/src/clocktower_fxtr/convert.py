"""Convert one clocktower game directory into fxtr entities.

A game directory (written by `python -m clocktower run`, or fetched from the Hugging Face dataset
`dwarkesh/clocktower-games`) holds:

- `config.json`, `result.json`: the game's settings and outcome (winner, roles, models, cost);
- `events.jsonl`: every event in order, each with who could see it (`to`: "public", "audit" for
  the Storyteller's and players' private records such as thinking, or a list of seat names);
- `probes.jsonl`: belief probes, out-of-game questions asked of each seat at dawn and dusk;
- `conversations/<seat>.json`: each seat's whole API conversation (Anthropic Messages or OpenAI
  Responses format).

`read_game` turns these into plain data; `to_seat_run` turns one conversation into a behaviors
`AgentRun`, so the viewer's conversation renderers show exactly what each seat's model saw and
said. OpenAI's encrypted reasoning is dropped (only its summary is readable); Anthropic thinking
blocks keep their text.

Only launchers and the `play_game` step (on the directory it just wrote) call this.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from behaviors.types import (
    AgentRun,
    AssistantMessage,
    ContentReasoning,
    ContentText,
    SystemMessage,
    Transcript,
    UserMessage,
)


@dataclass(frozen=True)
class GameFiles:
    """One game directory's contents, read and parsed."""

    config: dict[str, Any]
    result: dict[str, Any]
    events: list[dict[str, Any]]
    probes: list[dict[str, Any]]
    conversations: dict[str, dict[str, Any]]  # by seat name


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_game(directory: Path) -> GameFiles:
    conv_dir = directory / "conversations"
    conversations = (
        {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(conv_dir.glob("*.json"))}
        if conv_dir.is_dir()
        else {}
    )
    return GameFiles(
        config=json.loads((directory / "config.json").read_text(encoding="utf-8")),
        result=json.loads((directory / "result.json").read_text(encoding="utf-8")),
        events=_jsonl(directory / "events.jsonl"),
        probes=_jsonl(directory / "probes.jsonl"),
        conversations=conversations,
    )


def _block_text(content: Any) -> str:
    """The text of a message's content: a string, or a list of blocks with `text`."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))
    return ""


def _pretty(text: str) -> str:
    """A seat's reply is one JSON object (say, whispers, nominate, vote, ...): indent it to read."""
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return text


def _messages(conversation: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    system = conversation.get("system")
    if isinstance(system, str) and system:
        out.append(SystemMessage(content=(ContentText(text=system),)))
    pending: list[Any] = []  # an assistant turn's blocks, until its next user message

    def flush() -> None:
        if pending:
            out.append(AssistantMessage(content=tuple(pending)))
            pending.clear()

    for m in conversation.get("messages", []):
        kind, role = m.get("type"), m.get("role")
        if kind == "reasoning":  # OpenAI Responses: encrypted, with a readable summary
            summary = "\n\n".join(s.get("text", "") for s in m.get("summary") or [] if isinstance(s, dict))
            pending.append(ContentReasoning(text=summary, form="summary" if summary else "redacted"))
        elif role in ("developer", "system"):
            flush()
            out.append(SystemMessage(content=(ContentText(text=_block_text(m.get("content"))),)))
        elif role == "user":
            flush()
            out.append(UserMessage(content=(ContentText(text=_block_text(m.get("content"))),)))
        elif role == "assistant":
            content = m.get("content")
            if isinstance(content, str):
                pending.append(ContentText(text=_pretty(content)))
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "thinking":  # Anthropic
                    pending.append(ContentReasoning(text=b.get("thinking") or "", form="summary"))
                elif b.get("type") == "redacted_thinking":
                    pending.append(ContentReasoning(text="", form="redacted"))
                elif isinstance(b.get("text"), str):
                    pending.append(ContentText(text=_pretty(b["text"])))
            flush()
    flush()
    return out


def to_seat_run(game_id: str, seat: str, files: GameFiles) -> AgentRun | None:
    """One seat's conversation as an AgentRun, or None for a seat with none (a random bot)."""
    conversation = files.conversations.get(seat)
    if conversation is None:
        return None
    result = files.result
    return AgentRun(
        name=f"{game_id} · {seat}",
        description=f"{seat}'s conversation with the Storyteller",
        transcripts=(Transcript(name=seat, description=None, messages=tuple(_messages(conversation)), metadata={}),),
        groups=(),
        metadata={
            "game": game_id,
            "seat": seat,
            "character": (result.get("starting") or {}).get(seat),
            "model": (result.get("models") or {}).get(seat),
        },
    )
