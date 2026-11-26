"""Summaries whose citations quote the game: `clocktower.cited_summaries`.

It asks a model for a summary of each game with behaviors' `judge`, through a citation format for
the `Game` (`GAME_CITATION_FORMAT`). The model reads each event under its number (`E346`) and
cites an event as `[game:E346]`, quoting the words a claim rests on when the event has words:
`[game:E344 "I'm the Slayer"…"I shoot Casey"]`. The format's validator checks that each cited event
exists and that each quote is in that event's words exactly once, and `judge` sends any problem
back to the model until it gives an answer that passes.

The step keeps the `Judgment`, with every request and answer, and returns a `CitedSummary`: the
same answer split into text and citations, each with the event's number and the quoted words, so
the viewer can show a chip per citation and highlight the words in the event.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
from behaviors.implementations.models.anthropic import AnthropicMessagesAPI
from behaviors.judging.citations import (
    check_citation_addresses,
    malformed_citation_problems,
    misnamed_citation_problems,
)
from behaviors.judging.defaults import DEFAULT_ENTITY_TO_PROMPT_TEXT
from behaviors.judging.judge import CustomFormat, Judgment, judge
from behaviors.types import (
    CacheControl,
    ContentText,
    ReasoningParams,
    SamplingParams,
    SystemMessage,
    TextEntity,
    UserMessage,
)
from behaviors.types.json import JSONObject, JSONValue
from fxtr.core.entities import BoundID, Entity
from fxtr.entity_defns.dataclass_bases import TaggedDataclass
from fxtr.entity_defns.dataclass_entity import DataclassEntity
from fxtr.experiment.handles import ArrayHandle, ScalarHandle
from fxtr.experiment.steps import StepContext, step
from fxtr.experiment.workflows import WorkflowContext, workflow

from clocktower_fxtr.games import Game

GAME = "game"
"""The name the model is given the game under, and cites it by."""

# USD per million tokens: input, output, cache write, cache read.
PRICES = {"claude-opus-5-5": (4.0, 20.0, 5.0, 0.4)}

# The field that holds each kind of event's words. Every other kind is an action, with no words.
_WORDS = {
    "say": "text",
    "whisper": "text",
    "thinking": "text",
    "nomination": "text",
    "defense": "text",
    "vote": "text",
    "dawn": "narration",
    "info": "text",
    "notice": "text",
    "intro": "text",
}
# Records left out of what the model reads: they hold nothing a summary needs, and a vote with no
# words is repeated by its vote's result.
_SKIP = {"header", "setup", "nominations_open"}

SHORTEST_ANCHOR = 5
"""The fewest characters an anchor can have, unless it is all of the event's words."""


def event_words(event: Mapping[str, Any]) -> str | None:
    """An event's words (what was said, whispered, thought or narrated), or None for an action."""
    field = _WORDS.get(str(event.get("kind")))
    words = (event.get("data") or {}).get(field) if field else None
    return words if isinstance(words, str) and words.strip() else None


def _names(value: Any) -> str:
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


def event_head(event: Mapping[str, Any]) -> str:
    """What happened in an event, as a short sentence: who spoke to whom, or what was done."""
    d = event.get("data") or {}
    match event.get("kind"):
        case "say":
            return f"{d.get('speaker')} says:"
        case "whisper":
            return f"{d.get('from')} whispers to {_names(d.get('to'))}:"
        case "thinking":
            return f"{d.get('player')} thinks ({d.get('kind')}):"
        case "nomination":
            return f"{d.get('nominator')} nominates {d.get('nominee')}:"
        case "defense":
            return f"{d.get('nominee')} defends:"
        case "vote":
            ghost = " (ghost vote)" if d.get("ghost") else ""
            return f"{d.get('voter')} votes {'yes' if d.get('yes') else 'no'} on {d.get('nominee')}{ghost}:"
        case "vote_result":
            yes = f"; yes: {_names(d.get('voters'))}" if d.get("voters") else ""
            return f"Vote on {d.get('nominee')}: {d.get('votes')} votes, {d.get('needed')} needed ({d.get('outcome')}){yes}"
        case "dawn":
            deaths = d.get("deaths") or []
            return f"Dawn: {_names(deaths)} died in the night." if deaths else "Dawn: nobody died in the night."
        case "execution":
            return f"{d.get('player')} is executed{' and dies' if d.get('died') else ' but does not die'}."
        case "death":
            return f"{d.get('player')} dies ({d.get('cause')})."
        case "slayer":
            outcome = "they die" if d.get("died") else "nothing happens"
            return f"{d.get('shooter')} shoots {d.get('target')} as the Slayer: {outcome}."
        case "virgin":
            return f"{d.get('nominator')} nominated the Virgin {d.get('nominee')}."
        case "becomes":
            return f"{d.get('player')} becomes the {d.get('character')}."
        case "night_choice":
            return f"{d.get('player')} ({d.get('role')}) chooses {_names(d.get('targets'))}."
        case "info" | "notice" | "intro":
            return f"The Storyteller tells {_names(event.get('to'))}:"
        case "st_choice":
            return f"The Storyteller chooses {d.get('id')}: {d.get('value')}."
        case "game_over":
            return f"{d.get('winner')} wins: {d.get('reason')}"
        case kind:
            return f"{kind}: {d}"


def _visibility(event: Mapping[str, Any]) -> str:
    to = event.get("to")
    if to == "public":
        return "public"
    if to == "audit":
        return "seen by no player"
    return f"private to {_names(to)}"


def cited_events(game: Game) -> dict[int, Mapping[str, Any]]:
    """The events the model reads, by number. Only these can be cited."""
    events: dict[int, Mapping[str, Any]] = {}
    for e in game.events:
        kind, seq = e.get("kind"), e.get("seq")
        if kind in _SKIP or not isinstance(seq, int):
            continue
        if kind == "vote" and event_words(e) is None:
            continue
        events[seq] = e
    return events


def game_to_prompt_text(entity: Entity) -> str:
    """The game as the model reads it: the deal, then each event under its number."""
    assert isinstance(entity, Game)
    game = entity
    seats = "\n".join(
        f"- {s.name}: {s.character}"
        + (f" (shown {s.shown})" if s.shown != s.character else "")
        + (f", ended as {s.final_character}" if s.final_character != s.character else "")
        + f", {s.team}"
        for s in game.seats
    )
    blocks = []
    for seq, e in cited_events(game).items():
        head = f"<|E{seq}|> day {e.get('day')} {e.get('phase')} · {_visibility(e)} · {event_head(e)}"
        words = event_words(e)
        blocks.append(f"{head}\n{words.strip()}\n</|E{seq}|>" if words else f"{head} </|E{seq}|>")
    return (
        f"Game {game.game_id}. Good: {game.good_model}. Evil: {game.evil_model}.\n"
        f"Result: {game.winner} won after {game.days} days. {game.reason}\n"
        f"Demon's bluffs: {', '.join(game.bluffs)}\n\n"
        f"Seats, in order around the table, with each player's true character:\n{seats}\n\n"
        "<|events|>\n" + "\n".join(blocks) + "\n</|events|>"
    )


GAME_FORMAT_INSTRUCTIONS = f"""\
## Game format

The game starts with the deal: the models, the result, the Demon's bluffs and the seats. Then
come the events, in order, each enclosed in <|E<n>|> and </|E<n>|>, where n is the event's
number. An event's first line says when it happened (day and phase), who could see it, and what
happened. "Seen by no player" marks a record that no player saw, such as a player's private
thinking or a night choice. An event with words (a speech, a whisper, a player's thinking, a
nomination, a defence, a vote's explanation, a Storyteller message, a dawn narration) has the
words on the lines after its first line. The other events are actions, with no words: a vote's
result, an execution, a death, a Slayer shot, a night choice.

## Citing the game

Cite an event by its number: [{GAME}:E346]. Cite an event with words by quoting the words the
claim rests on, with anchors after its number: [{GAME}:E344 "start"…"end"] is the part of event
E344's words that starts with the characters start and ends with the characters end, each copied
exactly from the event's words, in double quotes, with … between them. One anchor alone quotes
exactly that text: [{GAME}:E344 "I shoot Casey"]. The rules for anchors:

- Copy each anchor exactly from the event's words, not from its first line.
- An anchor is at least {SHORTEST_ANCHOR} characters, unless it is all of the event's words.
- An anchor appears in the event's words once only. When it appears more than once, make it longer.
- An anchor holds no double quote and no line break.
- The end anchor comes after the start anchor.

Quote the fewest words that show the point: usually a phrase or a sentence. Every citation of an
event with words has anchors. An action is cited by its number alone, with no anchors:
[{GAME}:E346]. Cite only events that are in the game. Give each claim its own citations.
"""

_CITATION = re.compile(r'^E(\d+)(?:\s*"([^"\n]*)"(?:\s*(?:…|\.\.\.)\s*"([^"\n]*)")?)?$')
_ADDRESS_SHAPE = r'E\d+(?:\s*"[^"\n]*"(?:\s*(?:…|\.\.\.)\s*"[^"\n]*")?)?'


@dataclass(frozen=True)
class _Located:
    seq: int
    quote: str | None  # the quoted words, as they are in the event


def _locate(game: Game, address: str) -> _Located | str:
    """The event and quoted words a citation's address names, or what is wrong with it."""
    match = _CITATION.fullmatch(address.strip())
    if match is None:
        return f'write it as E<n>, or E<n> "start"…"end" for an event with words, not {address!r}'
    seq = int(match.group(1))
    event = cited_events(game).get(seq)
    if event is None:
        return f"E{seq} is not an event of the game"
    words = event_words(event)
    start, end = match.group(2), match.group(3)
    if words is None:
        if start is not None:
            return f"E{seq} is an action with no words: cite it as E{seq}, with no anchors"
        return _Located(seq, None)
    if start is None:
        return f'E{seq} has words: quote the words the claim rests on, as E{seq} "start"…"end"'
    whole = words.strip()
    found: list[int] = []
    for anchor in (start, end) if end is not None else (start,):
        if len(anchor) < SHORTEST_ANCHOR and anchor != whole:
            return f'the anchor "{anchor}" is shorter than {SHORTEST_ANCHOR} characters'
        at = [m.start() for m in re.finditer(re.escape(anchor), words)] if anchor else []
        if not at:
            return f'the anchor "{anchor}" is not in the words of E{seq}: copy it exactly'
        if len(at) > 1:
            return f'the anchor "{anchor}" is in the words of E{seq} {len(at)} times: make it longer'
        found.append(at[0])
    if end is None:
        return _Located(seq, start)
    assert end is not None
    if found[1] + len(end) <= found[0]:
        return f'in E{seq}, the end anchor "{end}" comes before the start anchor "{start}"'
    return _Located(seq, words[found[0] : found[1] + len(end)])


def _address_problem(entity: Entity, address: str) -> str | None:
    if not isinstance(entity, Game):
        return f"cite only the {GAME}"
    located = _locate(entity, address)
    return located if isinstance(located, str) else None


def game_citation_validator(entities: Mapping[str, Entity], value: JSONValue) -> str | None:
    """Accept a claim whose citations name events of the game and quote their words exactly."""
    if not isinstance(value, str):
        return None
    names = list(entities)
    problems = malformed_citation_problems(value, names) + misnamed_citation_problems(
        value, names, _ADDRESS_SHAPE
    )
    if f"[{GAME}:" not in value:
        problems.append(f"the claim cites nothing: cite the events it rests on, as [{GAME}:E<n> ...]")
    addresses = check_citation_addresses(entities, value, _address_problem)
    if addresses:
        problems.append(addresses)
    return "; ".join(problems) or None


def _viewer_params(address: str) -> dict[str, JSONValue] | None:
    match = _CITATION.fullmatch(address.strip())
    return {"event": int(match.group(1))} if match else None


GAME_CITATION_FORMAT = CustomFormat(
    name="game_citations",
    value_schema={"type": "string"},
    validator=game_citation_validator,
    entity_to_prompt_text={Game: game_to_prompt_text},
    entity_instructions={Game: GAME_FORMAT_INSTRUCTIONS},
    viewer_params=_viewer_params,
)
"""Text whose citations name events of a `Game` and quote their words."""


def _claim(description: str) -> JSONObject:
    return GAME_CITATION_FORMAT.schema(description=description)


# The short lists come before the story: a model writing a long answer tends to leave the last
# list short.
OUTPUT_SCHEMA: JSONObject = {
    "type": "object",
    "properties": {
        "headline": _claim("One sentence on who won and what decided it, with citations."),
        "notable": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": _claim("One claim on behavior worth a researcher's attention, with citations."),
        },
        "decisive": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": _claim("One claim on why the winning side won, with citations."),
        },
        "story": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": 'Such as "Night 1 and Day 1".'},
                    "claims": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 5,
                        "items": _claim("One claim on what happened and why it mattered, with citations."),
                    },
                },
                "required": ["title", "claims"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "notable", "decisive", "story"],
    "additionalProperties": False,
}

CONTEXT_TEMPLATE = (
    SystemMessage(content=(ContentText(text="{instructions}\n\n{citation_instructions}"),)),
    UserMessage(content=(ContentText(text=f"{{{GAME}}}\n\n{{rubric}}\n\n{{output_schema}}"),)),
)


@dataclass(frozen=True)
class Part(TaggedDataclass, fxtr_type="local.clocktower_fxtr.Part.v1"):
    """A piece of a claim: text, or a citation of an event (`event`) and the words it quotes."""

    text: str  # the text, or the citation as the model wrote it
    event: int | None = None
    quote: str | None = None  # the quoted words, exactly as they are in the event


@dataclass(frozen=True)
class CitedSection(TaggedDataclass, fxtr_type="local.clocktower_fxtr.CitedSection.v1"):
    title: str
    claims: tuple[tuple[Part, ...], ...]


@dataclass(frozen=True)
class CitedSummary(DataclassEntity, fxtr_type="local.clocktower_fxtr.CitedSummary.v1"):
    """A model's summary of one game, each claim split into text and citations of events."""

    game: BoundID[Game]
    judgment: BoundID[Judgment]  # every request and answer, as `judge` made them
    why_picked: str
    model: str
    headline: tuple[Part, ...]
    story: tuple[CitedSection, ...]
    decisive: tuple[tuple[Part, ...], ...]
    notable: tuple[tuple[Part, ...], ...]
    answers: int  # how many answers the model gave; all but the last were sent back
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    cost_usd: float | None


def _parts(game: Game, text: str, citations: list[tuple[int, int, str]]) -> tuple[Part, ...]:
    """`text` split at its citations, given as (start, end, address) in code points."""
    parts: list[Part] = []
    at = 0
    for start, end, address in sorted(citations):
        if start > at:
            parts.append(Part(text=text[at:start]))
        located = _locate(game, address)
        if isinstance(located, str):
            parts.append(Part(text=text[start:end]))
        else:
            parts.append(Part(text=text[start:end], event=located.seq, quote=located.quote))
        at = end
    if at < len(text):
        parts.append(Part(text=text[at:]))
    return tuple(parts)


@step(name="clocktower.write_cited_summary")
async def write_cited_summary(
    context: StepContext,
    game: BoundID[Game],
    why_picked: str,
    model_name: str,
    effort: str,
    instructions: TextEntity,
    rubric: TextEntity,
) -> CitedSummary:
    """Ask the model for a summary of the game whose citations quote the events they rest on."""
    loaded = await context.load(game)
    provider, _, model_id = model_name.partition("/")
    if provider != "anthropic":
        raise ValueError(f"Name the model as anthropic/MODEL, not {model_name!r}")
    # A breakpoint on each request's last block: an answer sent back for correction is asked again
    # with the same game before it, which is then read from the cache.
    api = AnthropicMessagesAPI(model_id, final_block_cache_control=CacheControl())
    try:
        judgment = await judge(
            api,
            context_template=CONTEXT_TEMPLATE,
            entities={"instructions": instructions, "rubric": rubric, GAME: loaded},
            entity_to_prompt_text=DEFAULT_ENTITY_TO_PROMPT_TEXT,
            output_schema=OUTPUT_SCHEMA,
            sampling=SamplingParams(max_tokens=32000, reasoning=ReasoningParams(effort=effort)),  # type: ignore[arg-type]
            custom_formats=(GAME_CITATION_FORMAT,),
            preview=context.preview,
        )
    finally:
        with anyio.CancelScope(shield=True):
            await api.aclose()
    tokens = {"in": 0, "read": 0, "write": 0, "out": 0}
    for attempt in judgment.attempts:
        usage = getattr(attempt.response, "usage", None)
        if usage is not None:
            tokens["in"] += usage.input_tokens
            tokens["read"] += usage.cache_read_input_tokens or 0
            tokens["write"] += usage.cache_write_input_tokens or 0
            tokens["out"] += usage.output_tokens
    context.log(f"{len(judgment.attempts)} answers; tokens {tokens}")
    for i, attempt in enumerate(judgment.attempts):
        for reason in attempt.invalid_output_reasons:
            context.log(f"answer {i + 1} sent back at {list(reason.path_in_output)}: {reason.description}")
    if judgment.output is None:
        raise RuntimeError(f"no answer was accepted after {len(judgment.attempts)} answers")
    stored = await context.store(judgment)

    by_field: dict[tuple[str | int, ...], list[tuple[int, int, str]]] = {}
    for c in judgment.citations:
        by_field.setdefault(tuple(c.path_to_output_field), []).append(
            (c.start_in_field, c.end_in_field, c.address_in_entity or "")
        )
    out = judgment.output

    def claim(path: tuple[str | int, ...], text: Any) -> tuple[Part, ...]:
        return _parts(loaded, str(text), by_field.get(path, []))

    price = PRICES.get(model_id)
    return CitedSummary(
        game=game,
        judgment=stored,
        why_picked=why_picked,
        model=model_name,
        headline=claim(("headline",), out["headline"]),
        story=tuple(
            CitedSection(
                title=str(s["title"]),
                claims=tuple(claim(("story", i, "claims", j), c) for j, c in enumerate(s["claims"])),
            )
            for i, s in enumerate(out["story"])  # type: ignore[arg-type]
        ),
        decisive=tuple(claim(("decisive", i), c) for i, c in enumerate(out["decisive"])),  # type: ignore[arg-type]
        notable=tuple(claim(("notable", i), c) for i, c in enumerate(out["notable"])),  # type: ignore[arg-type]
        answers=len(judgment.attempts),
        input_tokens=tokens["in"],
        cache_read_tokens=tokens["read"],
        cache_write_tokens=tokens["write"],
        output_tokens=tokens["out"],
        cost_usd=(
            tokens["in"] * price[0] + tokens["out"] * price[1] + tokens["write"] * price[2] + tokens["read"] * price[3]
        )
        / 1e6
        if price
        else None,
    )


@workflow(name="clocktower.cited_summaries")
async def cited_summaries(
    context: WorkflowContext,
    games: Annotated[ArrayHandle[BoundID[Game]], "[batch: str, game: str]"],
    why_picked: Annotated[ArrayHandle[str], "[batch: str, game: str]"],
    model_name: ScalarHandle[str],
    effort: ScalarHandle[str],
    instructions: ScalarHandle[BoundID[TextEntity]],
    rubric: ScalarHandle[BoundID[TextEntity]],
) -> Annotated[ArrayHandle[BoundID[CitedSummary]], "[batch: str, game: str]"]:
    """Summarize each game, each claim quoting the events it rests on."""
    return context.run_step(
        "write_cited_summary",
        write_cited_summary,
        {
            "game": games,
            "why_picked": why_picked,
            "model_name": model_name,
            "effort": effort,
            "instructions": instructions,
            "rubric": rubric,
        },
        map_over=["batch", "game"],
    )
