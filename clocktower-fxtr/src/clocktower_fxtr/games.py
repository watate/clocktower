"""Clocktower games in fxtr: entities for a game and its seats, and two workflows.

- `clocktower.index` takes games already played (imported by `load.py` from the Hugging Face
  dataset, keyed by [batch, game]), and summarizes each into a row: who played, who won, how the
  days went. It returns a `GameSet` for the viewer's results overview.
- `clocktower.play` plays new games, one `play_game` step per matchup (the clocktower engine, run
  as a subprocess; each seat calls its model's API), then indexes them the same way.
"""

import json
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

import anyio
from behaviors.types import AgentRun
from behaviors.types.json import JSONObject
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.entity_defns.dataclass_bases import TaggedDataclass
from fxtr.entity_defns.dataclass_entity import DataclassEntity
from fxtr.experiment.handles import ArrayHandle, ScalarHandle
from fxtr.experiment.steps import StepContext, step
from fxtr.experiment.workflows import WorkflowContext, workflow

from clocktower_fxtr.convert import GameFiles, read_game, to_seat_run

EVIL = {"Imp", "Poisoner", "Spy", "Scarlet Woman", "Baron"}


@dataclass(frozen=True)
class Seat(TaggedDataclass, fxtr_type="local.clocktower_fxtr.Seat.v1"):
    """One player: the character dealt, what they were shown (a Drunk is shown a Townsfolk), and
    the character they ended as (a Scarlet Woman may become the Imp)."""

    name: str
    character: str
    shown: str
    final_character: str
    team: str  # "good" or "evil", by the character dealt
    model: str
    conversation: BoundID[AgentRun] | None  # None for a random bot


@dataclass(frozen=True)
class Game(DataclassEntity, fxtr_type="local.clocktower_fxtr.Game.v1"):
    """One game of Trouble Brewing: its seats, every event in order, and the belief probes."""

    game_id: str  # e.g. v17/f7-astra62-v-astra/game-01
    protocol: str
    good_model: str
    evil_model: str
    winner: str | None  # "good", "evil", or None if the game stopped
    reason: str | None
    days: int
    seed: int
    players: int
    minion: str | None  # the guaranteed Minion of the deal
    cost: float  # USD
    seats: tuple[Seat, ...]  # in seating order, clockwise
    bluffs: tuple[str, ...]  # the three good characters not in play, given to the Demon
    events: tuple[JSONObject, ...]  # events.jsonl
    probes: tuple[JSONObject, ...]  # probes.jsonl
    config: JSONObject
    result: JSONObject


async def build_game(
    game_id: str, files: GameFiles, store: Callable[[AgentRun], Awaitable[BoundID[AgentRun]]]
) -> Game:
    """A Game from a game directory's files, storing each seat's conversation with `store`."""
    config, result = files.config, files.result
    setup = next((e for e in files.events if e.get("kind") == "setup"), None)
    seats_data = setup["data"]["seats"] if setup else [{"name": n, "character": c, "shown": c} for n, c in result["starting"].items()]
    models = result.get("models") or {}
    seats = []
    for s in seats_data:
        name = s["name"]
        run = to_seat_run(game_id, name, files)
        seats.append(
            Seat(
                name=name,
                character=s["character"],
                shown=s.get("shown") or s["character"],
                final_character=(result.get("final") or {}).get(name, s["character"]),
                team="evil" if s["character"] in EVIL else "good",
                model=str(models.get(name) or config.get("model") or ""),
                conversation=await store(run) if run is not None else None,
            )
        )
    return Game(
        game_id=game_id,
        protocol=str(config.get("protocol", "")),
        good_model=str(config.get("good_model") or config.get("model") or ""),
        evil_model=str(config.get("evil_model") or config.get("model") or ""),
        winner=result.get("winner"),
        reason=result.get("reason"),
        days=int(result.get("days") or 0),
        seed=int(result.get("seed") or config.get("seed") or 0),
        players=len(seats),
        minion=config.get("minion"),
        cost=float(result.get("cost") or 0.0),
        seats=tuple(seats),
        bluffs=tuple(result.get("bluffs") or ()),
        events=tuple(files.events),
        probes=tuple(files.probes),
        config=config,
        result=result,
    )


class GameStats(TypedDict):
    """One game's outcome and counts, a row of the index."""

    good_model: str
    evil_model: str
    winner: str | None
    reason: str | None
    days: int
    players: int
    minion: str | None
    cost: float
    whispers: int
    says: int  # town-square speeches
    nominations: int
    good_executed: int  # good players executed by the town
    evil_executed: int
    first_evil_execution_day: int | None


@dataclass(frozen=True)
class GameSet(DataclassEntity, fxtr_type="local.clocktower_fxtr.GameSet.v1"):
    """A set of games and a row of stats for each, both keyed by [batch, game]."""

    games: BoundID[Array[BoundID[Game]]]
    stats: BoundID[Array[GameStats]]


@step(name="clocktower.summarize_game")
async def summarize_game(context: StepContext, game: Game) -> GameStats:
    """Count a game's whispers, speeches and nominations, and who the town executed."""
    team = {s.name: s.team for s in game.seats}
    kinds = [e.get("kind") for e in game.events]
    executions: list[tuple[int, str]] = []  # (day, player)
    for e in game.events:
        data, day = e.get("data"), e.get("day")
        if e.get("kind") == "execution" and isinstance(data, dict) and isinstance(day, int):
            executions.append((day, str(data.get("player"))))
    evil_days = [day for day, player in executions if team.get(player) == "evil"]
    return GameStats(
        good_model=game.good_model,
        evil_model=game.evil_model,
        winner=game.winner,
        reason=game.reason,
        days=game.days,
        players=game.players,
        minion=game.minion,
        cost=game.cost,
        whispers=kinds.count("whisper"),
        says=kinds.count("say"),
        nominations=kinds.count("nomination"),
        good_executed=len(executions) - len(evil_days),
        evil_executed=len(evil_days),
        first_evil_execution_day=min(evil_days) if evil_days else None,
    )


@workflow(name="clocktower.index")
async def index(
    context: WorkflowContext,
    games: Annotated[ArrayHandle[BoundID[Game]], "[batch: str, game: str]"],
) -> GameSet:
    """List each game with its models, winner, and how the town voted."""
    stats = context.run_step("summarize_game", summarize_game, {"game": games}, map_over=["batch", "game"])
    return GameSet(
        games=await context.store(await games.observe()),
        stats=await context.store(await stats.observe()),
    )


class Matchup(TypedDict):
    """One game to play: the models for each side and the engine's settings."""

    good_model: str
    evil_model: str
    seed: int
    players: str  # a table size such as "10", or a range such as "10-12" picked by the seed
    effort: str  # reasoning effort for every seat
    max_days: int | None  # stop after this many days (None: the engine's default, 15)
    probes: bool  # ask the belief probes (more calls)


@step(name="clocktower.play_game")
async def play_game(context: StepContext, matchup: Matchup) -> Game:
    """Play one game with the clocktower engine, every seat calling its model's API."""
    game_id = f"played/{matchup['good_model']}-v-{matchup['evil_model']}/seed-{matchup['seed']}"
    with tempfile.TemporaryDirectory(prefix="clocktower-") as tmp:
        out = Path(tmp) / "game"
        cmd = [
            sys.executable, "-m", "clocktower", "run",
            "--good-model", matchup["good_model"],
            "--evil-model", matchup["evil_model"],
            "--seed", str(matchup["seed"]),
            "--players", matchup["players"],
            "--effort", matchup["effort"],
            "--out", str(out),
        ]  # fmt: skip
        if matchup["max_days"] is not None:
            cmd += ["--days", str(matchup["max_days"])]
        if not matchup["probes"]:
            cmd.append("--no-probes")
        context.log(" ".join(cmd[1:]))
        async with await anyio.open_process(cmd, stderr=anyio.subprocess.STDOUT) as proc:
            assert proc.stdout is not None
            tail: list[str] = []
            async for chunk in proc.stdout:
                for line in chunk.decode(errors="replace").splitlines():
                    if line.strip():
                        context.log(line)
                        tail = (tail + [line])[-20:]
            code = await proc.wait()
        if code != 0 or not (out / "result.json").exists():
            raise RuntimeError(f"clocktower run exited with {code}:\n" + "\n".join(tail))
        files = read_game(out)
        if files.result.get("stopped"):
            # A seat failed or the budget ran out: a later attempt might finish, so raise.
            raise RuntimeError(f"game stopped: {json.dumps(files.result.get('stopped'))}")
        return await build_game(game_id, files, context.store)


@workflow(name="clocktower.play")
async def play(
    context: WorkflowContext,
    matchups: Annotated[ArrayHandle[Matchup], "[batch: str, game: str]"],
) -> ScalarHandle[BoundID[GameSet]]:
    """Play every matchup, then list the games with their winners."""
    games = context.run_step("play_game", play_game, {"matchup": matchups}, map_over=["batch", "game"])
    return context.run_child_workflow("index", index, {"games": games})
