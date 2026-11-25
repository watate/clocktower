# Clocktower: language models playing Blood on the Clocktower

Language models play the social deduction game Blood on the Clocktower (the Trouble Brewing
script) against each other, with a scripted Storyteller. One model plays every good seat and
another every evil seat, so each game pits one model's **detection** (the town finding and
executing the Demon) against another's **deception** (the Demon and its Minions hiding, bluffing
and misleading). A game has 10 to 12 players and runs over several days. Each day has private
time (whispers to one or two players), a town square everyone reads, then nominations and votes;
each night the Demon kills and information characters learn something, possibly false if they
are drunk or poisoned.

The games here come from the Clocktower eval (github.com/dwarkeshsp/clocktower, protocol v17),
whose full logs are the Hugging Face dataset `dwarkesh/clocktower-games`. Each game is shown as:

- **the result**: which side won and why (the Demon died; only two players were left alive);
- **the seats**: each player's character, team and model, and how they died;
- **every event in order**: speeches in the town square, whispers, nominations, defenses and
  votes, deaths, and what each seat was told at night, together with each seat's thinking for
  every turn. The thinking of OpenAI models is the provider's short summary; Claude models'
  is their summarized thinking. "As seen by" restricts the events to what one seat saw;
- **each seat's conversation**: the exact prompts its model received and the JSON replies it
  sent (what to say, whom to whisper, whom to nominate, how to vote).

The overview counts, for each pairing of a good model and an evil model, how often good won,
and per game how many good and evil players the town executed: executing good players is the
town's main mistake, and the day the first evil player was executed shows how fast the town
found evil.

## Summaries with citations

`clocktower.summaries` (launched by `summarize.py`) has Claude Opus 5.5, at medium effort, read
ten chosen games, with every event numbered, and write a summary of each: a headline, the story
day by day, why the winning side won, and notable behavior (deception, reasoning, blunders,
false information from drunk or poisoned players). Every claim cites the events that show it.
In the viewer, hovering a citation shows the event, and pressing it scrolls the game below the
summary to that event. The instructions are in `prompts/summary.md`. The ten games are listed in
`summarize.py` with the reason each was picked: five good wins and five evil wins, chosen for the
ways games end (a Slayer shot, the Saint executed, a Mayor win, a final-two win).
