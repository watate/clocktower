# clocktower-fxtr

A fxtr project: steps and workflows in `src/clocktower_fxtr/`, run as jobs on a Postgres database and
watched in the experiment viewer.
It depends on the fxtr checkout at `/Users/walter-transluce/Documents/GitHub/fxtr3`.
[Project configuration](https://docs.transluce.ai/fxtr/reference/project-configuration) explains
each part of this layout.

Coding agents learn fxtr from its skills, which carry a copy of that documentation.
Install the fxtr plugin in Claude Code:

```
/plugin marketplace add TransluceAI/claude-code-plugins
/plugin install fxtr@transluce-plugins
```

or in Codex, from a terminal:

```bash
codex plugin marketplace add TransluceAI/codex-plugins
codex plugin add fxtr@transluce-plugins
```

## Install dependencies

Install the project's Python dependencies and create its `uv.lock`:

```bash
uv sync
```

## Set up renderers

`views/` is the project's renderer package (`[tool.fxtr.views]`). Register renderers in
`views/src/bundle.ts` to customize how the viewer shows your data. Follow the JavaScript setup in the fxtr
checkout's `README.md` to select Node, then install dependencies with
`pnpm install` in `views/`. `uv run fxtr view` builds the renderers when it starts and rebuilds
them whenever you change them, and the open viewer shows each build without a reload. To build
them without the viewer:

```bash
uv run fxtr views build
```

`views/pnpm-workspace.yaml` gives this package its own installation and lockfile. Commit `views/pnpm-lock.yaml` along with the project
before launching jobs.

`views/vendor/fxtr/` is a copy of the fxtr TypeScript packages the renderers use, made from the
fxtr this project was created with; commit it with the project. After upgrading fxtr, refresh it
and reinstall:

```bash
uv run fxtr views vendor
(cd views && pnpm install) && uv run fxtr views build
```

## Configure the database

Say where this machine reaches the project's database. The server that `postgres_env/` in the
fxtr checkout runs is reached this way:

```bash
uv run fxtr init --database-url postgresql+asyncpg://fxtr:fxtr@localhost:55433/fxtr
```

## Add API keys

Put the API keys of the model providers your experiments call, such as `ANTHROPIC_API_KEY` and
`OPENAI_API_KEY`, in `.env`. Every launch, `fxtr run`, and `fxtr resume` reads it into the
environment, overriding variables set in your shell (an empty value sets nothing). `.env` is
gitignored: never commit it, and never put keys in experiment inputs or entities, which the
database stores.

## Write your first experiment

This project starts without experiment code or a launcher. Define your steps and workflows in
`src/clocktower_fxtr/`, add their module names to `[tool.fxtr] modules` in `pyproject.toml`, and
write a launcher at the project root. Commit your code before launching: every job records
the commit it runs, and checks that the venv matches `uv.lock`.

[Your first experiment](https://docs.transluce.ai/fxtr/first-experiment) walks you through
designing and running an experiment of your own in this project, with your coding agent as a
guide.

## Watching jobs

Build the viewer once in the fxtr checkout (`cd /Users/walter-transluce/Documents/GitHub/fxtr3 && pnpm install && pnpm --filter
fxtr-ide build`), then `uv run fxtr view` serves it with this project's jobs and opens it in a
browser. Keep it running: each launch shows its job in the viewer's open tabs, or in a new tab
when none is open.

## Layout

```
pyproject.toml        the project, and [tool.fxtr]: the modules that register its steps and workflows
.env                  API keys, read into the environment of each launch; gitignored
src/clocktower_fxtr/
    __init__.py       the Python package
views/                the renderer package: src/bundle.ts is what it contributes to the viewer
    vendor/fxtr/      the fxtr TypeScript packages it links, copied by `fxtr views vendor`
```
