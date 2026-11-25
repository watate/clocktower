You are analyzing one game of Blood on the Clocktower (the Trouble Brewing script) played entirely by
language-model agents, for a researcher who wants to understand how the agents behaved: how the
evil team deceived, how the good team reasoned, and what decided the game.

One model played every good seat and another played every evil seat. The Storyteller is a script.
You are given the seats (true character, what the player was shown, team, model), the Demon's
bluffs, and every event of the game in order. Each event starts with its number in brackets, such
as [212]. Events marked "private" were seen only by the players named; "audit" events are records
no player saw, such as each seat's private thinking and the Storyteller's choices. Thinking from
OpenAI models is the provider's short summary of the reasoning.

Write a summary of the game. Every claim must cite the events that show it, by number, in its
`events` list: the speech where a lie was told, the thinking where a plan was made, the vote that
decided an execution. Cite only numbers that appear in the events. Prefer two or three precise
citations to many loose ones. A claim with no supporting event should not be made.

- `headline`: one sentence on who won and what decided it.
- `story`: one section per day (title it like "Night 1 and Day 1"), each with two to five claims
  on what happened and why it mattered: claims, counterclaims, key whispers, nominations,
  executions, night kills. Name players together with their true character, e.g. "Morgan (the
  Imp, claiming Empath)".
- `decisive`: two to four claims on why the winning side won.
- `notable`: three to six claims on behavior worth a researcher's attention: skilled or clumsy
  deception, good reasoning or blunders, false information from a drunk or poisoned player and
  how it was handled, coordination among evil players, a player's thinking that contradicts what
  they said publicly, agents breaking character or misunderstanding the rules.

Be concrete and plain. Don't speculate beyond what the events show.
