"""Import clocktower games into fxtr: `uv run python load.py 'v17/f7-*' ['v17/f6*' ...] [--name NAME]`.

Downloads the matching game folders from the Hugging Face dataset `dwarkesh/clocktower-games` into
the repository's `games/` (as `python -m clocktower fetch` does; `--no-fetch` uses what is there),
converts each finished game into a `Game` with each seat's conversation, stores them in the
project array `games_<name>` keyed by [batch, game], and runs `clocktower.index` on a snapshot of
it so the games can be read in the viewer.
"""

import argparse
import fnmatch
import sys
from pathlib import Path

import anyio
from fxtr.core.entities import BoundID
from fxtr.entity_defns.array import Array
from fxtr.project.client import JobNotFinishedError
from fxtr.project.running import open_local_client, run_job

from clocktower_fxtr.convert import read_game
from clocktower_fxtr.games import Game, build_game, index

GAMES = Path(__file__).resolve().parent.parent / "games"
REPO = "dwarkesh/clocktower-games"


def fetch(patterns: list[str]) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(REPO, repo_type="dataset", local_dir=GAMES, allow_patterns=[p.rstrip("/") + "/**" for p in patterns])


def game_dirs(patterns: list[str]) -> list[Path]:
    """Finished game directories (with logs, not just the config and result git keeps) under the patterns."""
    found = []
    for result in sorted(GAMES.glob("**/result.json")):
        d = result.parent
        rel = d.relative_to(GAMES).as_posix()
        batch = rel.rsplit("/", 1)[0]
        if any(fnmatch.fnmatch(batch, p) or fnmatch.fnmatch(rel, p) for p in patterns) and (d / "events.jsonl").exists():
            found.append(d)
    return found


async def main(args: argparse.Namespace) -> None:
    if not args.no_fetch:
        print(f"fetching {args.patterns} from {REPO} ...")
        fetch(args.patterns)
    dirs = game_dirs(args.patterns)
    if not dirs:
        raise SystemExit(f"no game logs under {GAMES} match {args.patterns}")
    array = f"games_{args.name}"
    schema = ("[batch: str, game: str]", BoundID[Game])
    async with open_local_client(__file__, max_concurrency=32) as client:
        items = []
        for i, d in enumerate(dirs):
            rel = d.relative_to(GAMES).as_posix()
            batch, game = rel.rsplit("/", 1)
            files = read_game(d)
            if files.result.get("winner") is None:
                print(f"  skipping {rel}: unfinished ({files.result.get('stopped')})")
                continue
            items.append(((batch, game), await client.store(await build_game(rel, files, client.store))))
            if (i + 1) % 20 == 0:
                print(f"  stored {i + 1} of {len(dirs)} games")
        print(f"stored {len(items)} games from {len({k[0] for k, _ in items})} batches")
        if array not in {info.name for info in await client.list_arrays()}:
            await client.create_array(array, schema)
        await client.replace_array(array, Array.from_items(items, schema))
        snapshot = await client.snapshot_array(array)
        await run_job(client, index, {"games": snapshot.array}, root=f"index-{args.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("patterns", nargs="+", help="batch globs in the dataset, such as 'v17/f7-*'")
    p.add_argument("--name", default="main", help="the project array to fill: games_<name>")
    p.add_argument("--no-fetch", action="store_true", help="use the logs already in games/")
    try:
        anyio.run(main, p.parse_args())
    except JobNotFinishedError:
        sys.exit(1)
