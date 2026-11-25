"""Summarize chosen games with citations: `uv run python summarize.py`.

Runs `clocktower.summaries` on the games in PICKS (from `data/`, downloaded by `load.py`), with
Claude Opus 5.5 at medium effort and the instructions in prompts/summary.md. Each summary's claims
cite the events that show them; the viewer links each citation to its event.
"""

import sys
from pathlib import Path

import anyio
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.project.client import JobNotFinishedError
from fxtr.project.running import open_local_client, run_job

from clocktower_fxtr.convert import read_game
from clocktower_fxtr.games import Game, build_game
from clocktower_fxtr.summaries import summaries

HERE = Path(__file__).resolve().parent
GAMES = HERE / "data"
MODEL = "anthropic/claude-opus-5-5"
EFFORT = "medium"

# Five good wins and five evil wins, chosen for the ways games end and for cross-model matchups.
PICKS = {
    "v17/f6c-fable52-v-fable51/game-01": "Good won on day 1: a Slayer shot killed the Demon.",
    "v17/f6c-fable52-v-fable51/game-01-swap": "Evil (Fable 5.2) won without a single evil player executed.",
    "v17/f6b-fable52-v-gpt56sol/game-03-swap": "Evil won when the town executed the Saint on day 6, after five good executions.",
    "v17/f7-astra62-v-opus55/game-01-swap": "Opus 5.5's town executed the Saint on day 4 and never executed an evil player.",
    "v17/f6b-fable52-v-opus55/game-02-swap": "Good won by the Mayor: three players left and no execution on day 6.",
    "v17/f6-fable52-v-astra/game-01": "GPT-6 Astra's evil beat Fable 5.2's town over six days, reaching the final two.",
    "v17/f6-fable52-v-gpt55/game-01": "A two-day game with a Slayer kill, a Virgin nomination and a character change.",
    "v17/f7-astra62-v-sol61/game-04": "Six days, three good and three evil executed, with a Drunk, a Recluse and a Virgin.",
    "v17/f7-astra62-v-sol61/game-01-swap": "Good won on day 6 despite executing four good players first.",
    "v17/f7c-astra62-v-fable52/game-02-swap": "Fable 5.2's town executed two evil players, then the Saint on day 6.",
}


async def main() -> None:
    instructions = (HERE / "prompts" / "summary.md").read_text()
    async with open_local_client(__file__, max_concurrency=10) as client:
        games, why = [], []
        for game_id, reason in PICKS.items():
            batch, game = game_id.rsplit("/", 1)
            built = await build_game(game_id, read_game(GAMES / game_id), client.store)
            games.append(((batch, game), await client.store(built)))
            why.append(((batch, game), reason))
        dims = "[batch: str, game: str]"
        inputs = {
            "games": Array.from_items(games, (dims, BoundID[Game])),
            "why_picked": Array.from_items(why, (dims, str)),
            "model_name": Array.scalar(MODEL, str),
            "effort": Array.scalar(EFFORT, str),
            "instructions": Array.scalar(instructions, str),
        }
        await run_job(client, summaries, inputs, root="summaries")


if __name__ == "__main__":
    try:
        anyio.run(main)
    except JobNotFinishedError:
        sys.exit(1)
