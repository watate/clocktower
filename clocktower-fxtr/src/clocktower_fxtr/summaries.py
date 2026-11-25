"""Summaries of games with citations: `clocktower.summaries` asks a model to summarize each game,
every claim citing the numbers of the events that show it, so the reader can jump from a claim to
the speech, whisper, vote or thinking behind it.
"""

import json
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
from behaviors.implementations.models.anthropic import AnthropicMessagesAPI
from behaviors.implementations.models.retries import DEFAULT_FAILURE_CATEGORIES_TO_RETRY, generate_with_retries
from behaviors.types import (
    AssistantMessage,
    ContentText,
    ModelCallFailure,
    ModelRequest,
    ReasoningParams,
    ResponseFormatJsonSchema,
    RetryConfig,
    SamplingParams,
    StopEndTurn,
    SystemMessage,
    UserMessage,
)
from fxtr.core.entities import BoundID
from fxtr.entity_defns.dataclass_bases import TaggedDataclass
from fxtr.entity_defns.dataclass_entity import DataclassEntity
from fxtr.experiment.handles import ArrayHandle, ScalarHandle
from fxtr.experiment.steps import StepContext, step
from fxtr.experiment.workflows import WorkflowContext, workflow

from clocktower_fxtr.games import Game

# USD per million tokens (input, output), for the cost estimate shown with each summary.
PRICES = {"claude-opus-5-5": (4.0, 20.0)}


@dataclass(frozen=True)
class Claim(TaggedDataclass, fxtr_type="local.clocktower_fxtr.Claim.v1"):
    """One statement of a summary and the events (by `seq`) that show it."""

    text: str
    events: tuple[int, ...]


@dataclass(frozen=True)
class Section(TaggedDataclass, fxtr_type="local.clocktower_fxtr.Section.v1"):
    title: str
    claims: tuple[Claim, ...]


@dataclass(frozen=True)
class GameSummary(DataclassEntity, fxtr_type="local.clocktower_fxtr.GameSummary.v1"):
    """A model's summary of one game, every claim citing events of the game."""

    game: BoundID[Game]
    why_picked: str  # why this game was chosen for a summary
    model: str
    headline: Claim
    story: tuple[Section, ...]  # one section per day
    decisive: tuple[Claim, ...]  # why the winning side won
    notable: tuple[Claim, ...]  # behavior worth a researcher's attention
    dropped_citations: tuple[int, ...]  # cited numbers that are not events of the game
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


_CLAIM: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "events": {"type": "array", "items": {"type": "integer"}}},
    "required": ["text", "events"],
    "additionalProperties": False,
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": _CLAIM,
        "story": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "claims": {"type": "array", "items": _CLAIM}},
                "required": ["title", "claims"],
                "additionalProperties": False,
            },
        },
        "decisive": {"type": "array", "items": _CLAIM},
        "notable": {"type": "array", "items": _CLAIM},
    },
    "required": ["headline", "story", "decisive", "notable"],
    "additionalProperties": False,
}

_SKIP = {"header", "setup", "nominations_open"}


def _names(v: Any) -> str:
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def event_line(e: dict[str, Any]) -> str | None:
    """One event as a line of the prompt, starting with its number; None for events left out."""
    kind, d = e.get("kind"), e.get("data") or {}
    if kind in _SKIP or (kind == "vote" and not d.get("text")):
        return None
    to = e.get("to")
    vis = "" if to == "public" else " (audit)" if to == "audit" else f" (private to {_names(to)})"
    text = d.get("text")
    match kind:
        case "say":
            body = f"{d.get('speaker')} says: {text}"
        case "whisper":
            body = f"{d.get('from')} whispers to {_names(d.get('to'))}: {text}"
        case "thinking":
            body = f"{d.get('player')} thinks ({d.get('kind')}): {text}"
        case "nomination":
            body = f"{d.get('nominator')} nominates {d.get('nominee')}: {text}"
        case "defense":
            body = f"{d.get('nominee')} defends: {text}"
        case "vote":
            body = f"{d.get('voter')} votes {'yes' if d.get('yes') else 'no'} on {d.get('nominee')}: {text}"
        case "vote_result":
            body = f"vote on {d.get('nominee')}: {d.get('votes')} of {d.get('needed')} needed, {d.get('outcome')}; yes: {_names(d.get('voters') or [])}"
        case "info" | "notice" | "intro":
            body = f"Storyteller tells {_names(to)}: {text}"
            vis = ""
        case _:
            body = f"{kind}: {json.dumps(d, ensure_ascii=False)}"
    return f"[{e.get('seq')}] day {e.get('day')} {e.get('phase')}{vis} · {body}"


def game_prompt(game: Game) -> str:
    seats = "\n".join(
        f"- {s.name}: {s.character}"
        + (f" (shown {s.shown})" if s.shown != s.character else "")
        + (f", ended as {s.final_character}" if s.final_character != s.character else "")
        + f", {s.team}"
        for s in game.seats
    )
    events = "\n".join(line for e in game.events if (line := event_line(dict(e))) is not None)
    return (
        f"Game {game.game_id}. Good: {game.good_model}. Evil: {game.evil_model}.\n"
        f"Result: {game.winner} won after {game.days} days. {game.reason}\n"
        f"Demon's bluffs: {', '.join(game.bluffs)}\n\nSeats, in order around the table:\n{seats}\n\n"
        f"Events:\n{events}"
    )


def _claim(raw: dict[str, Any], seqs: set[int], dropped: list[int]) -> Claim:
    events = []
    for n in raw.get("events") or []:
        (events if n in seqs else dropped).append(int(n))
    return Claim(text=str(raw.get("text", "")), events=tuple(dict.fromkeys(events)))


@step(name="clocktower.write_summary")
async def write_summary(
    context: StepContext,
    game: BoundID[Game],
    why_picked: str,
    model_name: str,
    effort: str,
    instructions: str,
) -> GameSummary:
    """Ask the model for a summary of the game with each claim citing its events."""
    loaded = await context.load(game)
    provider, _, model_id = model_name.partition("/")
    if provider != "anthropic":
        raise ValueError(f"Name the model as anthropic/MODEL, not {model_name!r}")
    request = ModelRequest(
        context=(
            SystemMessage(content=(ContentText(text=instructions),)),
            UserMessage(content=(ContentText(text=game_prompt(loaded)),)),
        ),
        tools=(),
        tool_choice=None,
        parallel_tool_calls=None,
        sampling=SamplingParams(max_tokens=20000, reasoning=ReasoningParams(effort=effort)),  # type: ignore[arg-type]
        response_format=ResponseFormatJsonSchema(schema=SCHEMA, strict=True, name="game_summary"),
    )
    api = AnthropicMessagesAPI(model_id)
    try:
        response = await generate_with_retries(
            api, request, retry=RetryConfig(), failure_categories_to_retry=DEFAULT_FAILURE_CATEGORIES_TO_RETRY
        )
    finally:
        with anyio.CancelScope(shield=True):
            await api.aclose()
    if isinstance(response, ModelCallFailure):
        raise RuntimeError(f"model call failed: {response.category}: {response.description}")
    if not isinstance(response.stop_reason, StopEndTurn):
        raise RuntimeError(f"the model stopped with {response.stop_reason}, not a finished answer")
    text = "".join(
        c.text for m in response.output if isinstance(m, AssistantMessage) for c in m.content if isinstance(c, ContentText)
    )
    raw = json.loads(text)
    seqs = {int(e["seq"]) for e in loaded.events if isinstance(e.get("seq"), int)}
    dropped: list[int] = []
    usage = response.usage
    tokens_in = usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_write_input_tokens or 0)
    price = PRICES.get(model_id)
    summary = GameSummary(
        game=game,
        why_picked=why_picked,
        model=model_name,
        headline=_claim(raw["headline"], seqs, dropped),
        story=tuple(
            Section(title=str(s.get("title", "")), claims=tuple(_claim(c, seqs, dropped) for c in s.get("claims") or []))
            for s in raw["story"]
        ),
        decisive=tuple(_claim(c, seqs, dropped) for c in raw["decisive"]),
        notable=tuple(_claim(c, seqs, dropped) for c in raw["notable"]),
        dropped_citations=tuple(dropped),
        input_tokens=tokens_in,
        output_tokens=usage.output_tokens,
        cost_usd=(tokens_in * price[0] + usage.output_tokens * price[1]) / 1e6 if price else None,
    )
    context.log(f"{tokens_in} input and {usage.output_tokens} output tokens; dropped citations {dropped}")
    return summary


@workflow(name="clocktower.summaries")
async def summaries(
    context: WorkflowContext,
    games: Annotated[ArrayHandle[BoundID[Game]], "[batch: str, game: str]"],
    why_picked: Annotated[ArrayHandle[str], "[batch: str, game: str]"],
    model_name: ScalarHandle[str],
    effort: ScalarHandle[str],
    instructions: ScalarHandle[str],
) -> Annotated[ArrayHandle[BoundID[GameSummary]], "[batch: str, game: str]"]:
    """Summarize each game, every claim citing the events that show it."""
    return context.run_step(
        "write_summary",
        write_summary,
        {"game": games, "why_picked": why_picked, "model_name": model_name, "effort": effort, "instructions": instructions},
        map_over=["batch", "game"],
    )
