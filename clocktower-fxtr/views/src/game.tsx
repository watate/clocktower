// A readable view of one game: the result, the seats (character, team, model, fate, and a link to
// each seat's conversation), then every event in order, grouped by night and day. The reader can
// see everything (the Storyteller's view, with every seat's thinking) or the game as one seat saw
// it, and fold away thinking, whispers, or individual votes.

import { useEffect, useRef, type ReactNode } from "react";
import {
  EntityLink,
  EntityPanel,
  declareView,
  unwrap,
  useEntity,
  type EntityID,
  type EntityPanelProps,
  type EntityViewProps,
  type ViewProps,
} from "fxtr-view";
import { Kind, Legend, Segmented, Select, formatNumber, layout, useStoredState } from "fxtr-view-kit";
import { GAME, type GameData, type GameEvent, type SeatData } from "./types";
import styles from "./game.module.css";

/** The game's panel. A link that binds `event` (an event's seq) opens the game scrolled to that
 *  event, and marks it. */
export const GAME_PANEL = declareView(EntityPanel, GAME, "clocktower-fxtr.GamePanel", { params: ["event"] });

export const TEAM_COLOR = { good: "var(--chart-1)", evil: "var(--chart-8)" } as const;

const EVERYONE = "everyone";

type Show = "all" | "talk";

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function names(v: unknown): string[] {
  return Array.isArray(v) ? v.map(str) : [];
}

/** Whether `seat` saw the event (or, for a private record, it is about them). */
function visibleTo(e: GameEvent, seat: string): boolean {
  if (e.to === "public") return true;
  if (Array.isArray(e.to)) return e.to.includes(seat);
  return (e.kind === "thinking" || e.kind === "night_choice") && str(e.data["player"]) === seat;
}

/** How each seat left the game, from the death events. */
function fates(events: readonly GameEvent[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const e of events) {
    if (e.kind !== "death") continue;
    const player = str(e.data["player"]);
    const cause = str(e.data["cause"]) || "died";
    const when = e.phase === "night" ? `night ${e.day}` : `day ${e.day}`;
    if (!out.has(player)) out.set(player, `${cause} · ${when}`);
  }
  return out;
}

export function Name({ name, team }: { name: string; team: Map<string, "good" | "evil"> }) {
  const t = team.get(name);
  return (
    <span className={styles.name} style={t ? { color: TEAM_COLOR[t] } : undefined}>
      {name}
    </span>
  );
}

function List({ items, team }: { items: readonly string[]; team: Map<string, "good" | "evil"> }) {
  return (
    <>
      {items.map((n, i) => (
        <span key={n}>
          {i > 0 && ", "}
          <Name name={n} team={team} />
        </span>
      ))}
    </>
  );
}

function Line({ kind, children, text }: { kind: string; children: ReactNode; text?: string }) {
  return (
    <div className={styles.event} data-kind={kind}>
      <div className={styles.lead}>{children}</div>
      {text ? <div className={styles.text}>{text}</div> : null}
    </div>
  );
}

export function Event({ e, team, showThinking }: { e: GameEvent; team: Map<string, "good" | "evil">; showThinking: boolean }) {
  const d = e.data;
  const N = (n: unknown) => <Name name={str(n)} team={team} />;
  switch (e.kind) {
    case "say":
      return <Line kind="say" text={str(d["text"])}>{N(d["speaker"])}</Line>;
    case "whisper":
      return (
        <Line kind="whisper" text={str(d["text"])}>
          {N(d["from"])} <span className={styles.dim}>whispers to</span> <List items={names(d["to"])} team={team} />
        </Line>
      );
    case "thinking": {
      const text = str(d["text"]);
      return (
        <details className={styles.thinking} open={showThinking}>
          <summary>
            {N(d["player"])} <span className={styles.dim}>thinks · {str(d["kind"])} · {text.split(/\s+/).filter(Boolean).length} words</span>
          </summary>
          <div className={styles.text}>{text}</div>
        </details>
      );
    }
    case "nomination":
      return (
        <Line kind="nomination" text={str(d["text"])}>
          {N(d["nominator"])} <span className={styles.dim}>nominates</span> {N(d["nominee"])}
        </Line>
      );
    case "defense":
      return <Line kind="say" text={str(d["text"])}>{N(d["nominee"])} <span className={styles.dim}>defends</span></Line>;
    case "vote":
      return (
        <Line kind="vote" text={str(d["text"])}>
          {N(d["voter"])} <span className={styles.dim}>votes</span> {d["yes"] ? "yes" : "no"}{" "}
          <span className={styles.dim}>on</span> {N(d["nominee"])}
          {d["ghost"] ? <span className={styles.dim}> (ghost vote)</span> : null}
        </Line>
      );
    case "vote_result":
      return (
        <Line kind="system">
          {N(d["nominee"])}: {str(d["votes"])} votes, {str(d["needed"])} needed ({str(d["outcome"])})
          {names(d["voters"]).length > 0 && (
            <>
              {" "}
              <span className={styles.dim}>· yes:</span> <List items={names(d["voters"])} team={team} />
            </>
          )}
        </Line>
      );
    case "dawn": {
      const deaths = names(d["deaths"]);
      return (
        <Line kind="system" text={str(d["narration"])}>
          Dawn · {deaths.length ? <><List items={deaths} team={team} /> died in the night</> : "nobody died"}
        </Line>
      );
    }
    case "execution":
      return <Line kind="death">{N(d["player"])} is executed{d["died"] ? "" : " but does not die"}</Line>;
    case "death":
      return <Line kind="death">{N(d["player"])} dies <span className={styles.dim}>({str(d["cause"])})</span></Line>;
    case "slayer":
      return <Line kind="death">{N(d["shooter"])} shoots {N(d["target"])} as the Slayer: {d["died"] ? "they die" : "nothing happens"}</Line>;
    case "virgin":
      return <Line kind="death">{N(d["nominator"])} nominated the Virgin {N(d["nominee"])}</Line>;
    case "becomes":
      return <Line kind="system">{N(d["player"])} becomes the {str(d["character"])}</Line>;
    case "night_choice":
      return (
        <Line kind="private">
          {N(d["player"])} <span className={styles.dim}>({str(d["role"])}) chooses</span> <List items={names(d["targets"])} team={team} />
        </Line>
      );
    case "info":
    case "notice":
    case "intro":
      return <Line kind="private" text={str(d["text"])}><span className={styles.dim}>to</span> <List items={names(e.to)} team={team} /></Line>;
    case "st_choice":
      return <Line kind="private"><span className={styles.dim}>Storyteller chooses {str(d["id"])}: {JSON.stringify(d["value"])}</span></Line>;
    case "game_over":
      return <Line kind="over">{str(d["winner"])} wins: {str(d["reason"])}</Line>;
    case "nominations_open":
      return <Line kind="system"><span className={styles.dim}>Nominations open</span></Line>;
    case "setup":
    case "header":
      return null;
    default:
      return <Line kind="system"><span className={styles.dim}>{e.kind}: {JSON.stringify(d)}</span></Line>;
  }
}

function SeatTable({ game, fate }: { game: GameData; fate: Map<string, string> }) {
  return (
    <div className={styles.scroll}>
      <table className={layout.table}>
        <thead>
          <tr>
            <th>seat</th>
            <th>character</th>
            <th>model</th>
            <th>fate</th>
            <th>conversation</th>
          </tr>
        </thead>
        <tbody>
          {game.seats.map((s) => (
            <tr key={s.name}>
              <td>
                <span className={styles.name} style={{ color: TEAM_COLOR[s.team] }}>{s.name}</span>
              </td>
              <td>
                {s.character}
                {s.shown !== s.character && <span className={styles.dim}> (thinks {s.shown})</span>}
                {s.final_character !== s.character && <span className={styles.dim}> → {s.final_character}</span>}
              </td>
              <td className={styles.mono}>{s.model}</td>
              <td>{fate.get(s.name) ?? <span className={styles.dim}>alive</span>}</td>
              <td>{s.conversation ? <EntityLink id={s.conversation} /> : <span className={styles.dim}>none</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function teamsOf(game: GameData): Map<string, "good" | "evil"> {
  return new Map(game.seats.map((s: SeatData) => [s.name, s.team] as const));
}

/** The result line under a game's title: the models of each side and who won. */
export function GameResult({ game }: { game: GameData }) {
  return (
    <div className={styles.result}>
      <span style={{ color: TEAM_COLOR.good }}>{game.good_model}</span> <span className={styles.dim}>(good) vs</span>{" "}
      <span style={{ color: TEAM_COLOR.evil }}>{game.evil_model}</span> <span className={styles.dim}>(evil)</span>
      {" · "}
      {game.winner ? <b style={{ color: TEAM_COLOR[game.winner as "good" | "evil"] }}>{game.winner} wins</b> : "unfinished"}
      {game.reason ? <span className={styles.dim}> · {game.reason}</span> : null}
    </div>
  );
}

export function GamePanel({ id, storage, params }: ViewProps<typeof GAME_PANEL>) {
  const game = unwrap(useEntity(id as EntityID<GameData>));
  const focus = typeof params?.event === "number" ? params.event : null;
  return (
    <div className={layout.panel}>
      <div className={layout.kindLine}>
        <Kind>Game</Kind>
      </div>
      <div className={layout.title}>{game.game_id}</div>
      <GameResult game={game} />
      <GameReader game={game} storage={storage} focus={focus} />
    </div>
  );
}

/** Centre `element` in the nearest box that scrolls it up and down. `scrollIntoView` is not
 *  used, because it scrolls every box around the element, sideways too, and so moves the
 *  viewer's panes. */
function centreInPane(element: HTMLElement): void {
  let pane = element.parentElement;
  while (pane && !(/(auto|scroll)/.test(getComputedStyle(pane).overflowY) && pane.scrollHeight > pane.clientHeight)) pane = pane.parentElement;
  if (!pane) return;
  const top = element.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  pane.scrollTo({ top: top - Math.max(0, (pane.clientHeight - element.offsetHeight) / 2), behavior: "smooth" });
}

/** The seats and every event of a game, with the reader's controls. `focus` is an event's seq to
 *  scroll to and mark (shown whatever the filters hide). */
export function GameReader({ game, storage, focus = null }: { game: GameData; storage: EntityPanelProps["storage"]; focus?: number | null }) {
  const team = teamsOf(game);
  const [view, setView] = useStoredState<string>(storage, "view", EVERYONE);
  const [show, setShow] = useStoredState<Show>(storage, "show", "all", (v): v is Show => v === "all" || v === "talk");
  const [thinking, setThinking] = useStoredState<"open" | "folded" | "hidden">(storage, "thinking", "folded");
  const [votes, setVotes] = useStoredState<"each" | "totals">(storage, "votes", "totals");
  const seat = game.seats.some((s) => s.name === view) ? view : EVERYONE;
  const fate = fates(game.events);

  // A ref, not a document id: two readers of one game can be on the page at once.
  const focused = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = focused.current;
    if (focus === null || !element) return;
    // A pane that is just opening lays its content out over its first moments. A scroll made
    // before then goes nowhere, so the scroll is made again until the pane has settled.
    const scroll = () => centreInPane(element);
    scroll();
    const timers = [50, 200, 500].map((delay) => setTimeout(scroll, delay));
    return () => timers.forEach(clearTimeout);
  }, [focus]);

  const events = game.events.filter((e) => {
    if (e.seq === focus) return true;
    if (seat !== EVERYONE && !visibleTo(e, seat)) return false;
    if (e.kind === "thinking") return thinking !== "hidden";
    if (e.kind === "vote") return votes === "each" || str(e.data["text"]) !== "";
    if (show === "talk") return ["say", "whisper", "nomination", "defense", "thinking", "header", "dawn", "execution", "game_over", "vote_result", "slayer"].includes(e.kind);
    return true;
  });

  // Group the events under the night and day headers.
  const sections: { title: string; events: GameEvent[] }[] = [{ title: "setup", events: [] }];
  for (const e of events) {
    if (e.kind === "header") sections.push({ title: str(e.data["text"]), events: [] });
    else sections[sections.length - 1]!.events.push(e);
  }
  const me = game.seats.find((s) => s.name === seat);

  return (
    <>
      <div className={layout.muted}>
        {game.days} days · {game.players} players · minion {game.minion ?? "by seed"} · Demon's bluffs {game.bluffs.join(", ")} · seed {game.seed} ·{" "}
        {game.protocol} · ${formatNumber(game.cost, 2)}
      </div>

      <h3 className={layout.subtitle}>seats</h3>
      <Legend items={[{ label: "good", color: TEAM_COLOR.good }, { label: "evil", color: TEAM_COLOR.evil }]} />
      <SeatTable game={game} fate={fate} />

      <h3 className={layout.subtitle}>events</h3>
      <div className={styles.controls}>
        <Select
          label="as seen by"
          value={seat}
          onChange={setView}
          options={[{ value: EVERYONE, label: "everyone (Storyteller)" }, ...game.seats.map((s) => ({ value: s.name, label: `${s.name} · ${s.character}` }))]}
        />
        <Segmented label="events" value={show} onChange={setShow} options={[{ value: "all", label: "all" }, { value: "talk", label: "talk only" }]} />
        <Segmented
          label="thinking"
          value={thinking}
          onChange={setThinking}
          options={[{ value: "open", label: "open" }, { value: "folded", label: "folded" }, { value: "hidden", label: "hidden" }]}
        />
        <Segmented label="votes" value={votes} onChange={setVotes} options={[{ value: "totals", label: "totals" }, { value: "each", label: "each" }]} />
      </div>
      {me && (
        <p className={layout.muted}>
          What {me.name} ({me.shown}, {me.team}) saw and sent, with {me.name}'s own thinking.
        </p>
      )}
      {sections
        .filter((s) => s.events.length > 0)
        .map((s, i) => (
          <section key={i} className={styles.section}>
            <div className={styles.header}>{s.title}</div>
            {s.events.map((e) => (
              <div key={e.seq} ref={e.seq === focus ? focused : undefined} className={styles.anchor} data-focus={e.seq === focus}>
                <Event e={e} team={team} showThinking={thinking === "open" || e.seq === focus} />
              </div>
            ))}
          </section>
        ))}
    </>
  );
}

export function GameInlineLink({ id }: EntityViewProps) {
  const game = unwrap(useEntity(id as EntityID<GameData>));
  return (
    <>
      {game.game_id.split("/").slice(-2).join("/")} · {game.winner ? `${game.winner} won` : "unfinished"}
    </>
  );
}

export function GameHoverPreview({ id }: EntityViewProps) {
  const game = unwrap(useEntity(id as EntityID<GameData>));
  return (
    <div className={layout.panel}>
      <div className={layout.title}>{game.game_id}</div>
      <div>
        {game.good_model} (good) vs {game.evil_model} (evil)
      </div>
      <div className={layout.muted}>
        {game.winner ? `${game.winner} won` : "unfinished"} · {game.days} days · {game.players} players
      </div>
    </div>
  );
}
