"""Summarize chosen games with quoting citations: `uv run python summarize_cited.py`.

Runs `clocktower.cited_summaries` on the games in PICKS (from `data/`, downloaded by `load.py`),
with Claude Opus 5.5 at medium effort, the instructions in prompts/cited_instructions.md and the
rubric in prompts/cited_rubric.md. Each claim cites the events it rests on and quotes their words;
the viewer shows each citation as the event's number and highlights the quoted words in the game.
"""

import sys
from pathlib import Path

import anyio
from behaviors.types import TextEntity
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.project.client import JobNotFinishedError
from fxtr.project.running import open_local_client, run_job

from clocktower_fxtr.cited import cited_summaries
from clocktower_fxtr.convert import read_game
from clocktower_fxtr.games import Game, build_game

HERE = Path(__file__).resolve().parent
GAMES = HERE / "data"
MODEL = "anthropic/claude-opus-5-5"
EFFORT = "medium"

# Five of the ten games of summarize.py: three good wins and two evil wins.
PICKS = {
    "v17/f6b-fable52-v-gpt56sol/game-03-swap": "Evil won when the town executed the Saint on day 6, after five good executions.",
    "v17/f7-astra62-v-opus55/game-01-swap": "Opus 5.5's town executed the Saint on day 4 and never executed an evil player.",
    "v17/f6b-fable52-v-opus55/game-02-swap": "Good won by the Mayor: three players left and no execution on day 6.",
    "v17/f6-fable52-v-gpt55/game-01": "A two-day game with a Slayer kill, a Virgin nomination and a character change.",
    "v17/f6c-fable52-v-fable51/game-01": "Good won on day 1: a Slayer shot killed the Demon.",
}


async def main() -> None:
    instructions = TextEntity(text=(HERE / "prompts" / "cited_instructions.md").read_text())
    rubric = TextEntity(text=(HERE / "prompts" / "cited_rubric.md").read_text())
    async with open_local_client(__file__, max_concurrency=5) as client:
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
            "instructions": Array.scalar(await client.store(instructions), BoundID[TextEntity]),
            "rubric": Array.scalar(await client.store(rubric), BoundID[TextEntity]),
        }
        await run_job(client, cited_summaries, inputs, root="cited-summaries")


if __name__ == "__main__":
    try:
        anyio.run(main)
    except JobNotFinishedError:
        sys.exit(1)
