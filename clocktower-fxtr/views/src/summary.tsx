// A model's summary of a game with citations. Each claim ends with the numbers of the events that
// show it: hover one to read the event, press it to jump to the event in the game below, which is
// marked and shown whatever the reader's filters hide.

import { Suspense, useState } from "react";
import {
  EntityDataError,
  EntityLink,
  isArrayData,
  isEntityID,
  rowsOf,
  unwrap,
  useEntity,
  useInvocation,
  type ArrayData,
  type EntityID,
  type EntityPanelProps,
  type EntityViewProps,
  type InvocationPanelProps,
  type Spawn,
} from "fxtr-view";
import { DataTable, InvocationHead, InvocationOutcome, Kind, Stat, Stats, formatNumber, layout } from "fxtr-view-kit";
import { Event, GameReader, GameResult, TEAM_COLOR, teamsOf } from "./game";
import { type ClaimData, type GameData, type GameEvent, type GameSummaryData } from "./types";
import styles from "./summary.module.css";

type Team = Map<string, "good" | "evil">;

function Cite({ seq, event, team, onPick }: { seq: number; event: GameEvent | undefined; team: Team; onPick: (seq: number) => void }) {
  return (
    <span className={styles.cite}>
      <button type="button" className={styles.chip} onClick={() => onPick(seq)} aria-label={`go to event ${seq}`}>
        {seq}
      </button>
      {event && (
        <span className={styles.pop} role="tooltip">
          <Event e={event} team={team} showThinking />
        </span>
      )}
    </span>
  );
}

function Claim({ claim, events, team, onPick }: { claim: ClaimData; events: Map<number, GameEvent>; team: Team; onPick: (seq: number) => void }) {
  return (
    <>
      {claim.text}
      {claim.events.length > 0 && " "}
      {claim.events.map((seq) => (
        <Cite key={seq} seq={seq} event={events.get(seq)} team={team} onPick={onPick} />
      ))}
    </>
  );
}

function Claims({ claims, ...rest }: { claims: readonly ClaimData[]; events: Map<number, GameEvent>; team: Team; onPick: (seq: number) => void }) {
  return (
    <ul className={styles.claims}>
      {claims.map((c, i) => (
        <li key={i}>
          <Claim claim={c} {...rest} />
        </li>
      ))}
    </ul>
  );
}

export function SummaryPanel({ id, storage }: EntityPanelProps) {
  const summary = unwrap(useEntity(id as EntityID<GameSummaryData>));
  const game = unwrap(useEntity(summary.game)) as GameData;
  const [focus, setFocus] = useState<number | null>(null);
  const events = new Map(game.events.map((e) => [e.seq, e] as const));
  const ctx = { events, team: teamsOf(game), onPick: setFocus };

  return (
    <div className={layout.panel}>
      <div className={layout.kindLine}>
        <Kind>Game summary</Kind>
      </div>
      <div className={layout.title}>{game.game_id}</div>
      <GameResult game={game} />
      <p className={layout.muted}>
        Picked because: {summary.why_picked} Written by {summary.model}. Numbers are the events each claim rests on: hover to
        read one, press to jump to it in the game below.
      </p>

      <p className={styles.headline}>
        <Claim claim={summary.headline} {...ctx} />
      </p>

      <h3 className={layout.subtitle}>what happened</h3>
      {summary.story.map((s, i) => (
        <div key={i}>
          <div className={styles.day}>{s.title}</div>
          <Claims claims={s.claims} {...ctx} />
        </div>
      ))}

      <h3 className={layout.subtitle} style={game.winner ? { color: TEAM_COLOR[game.winner as "good" | "evil"] } : undefined}>
        why {game.winner ?? "nobody"} won
      </h3>
      <Claims claims={summary.decisive} {...ctx} />

      <h3 className={layout.subtitle}>notable behavior</h3>
      <Claims claims={summary.notable} {...ctx} />

      <p className={layout.muted}>
        {formatNumber(summary.input_tokens, 0)} input and {formatNumber(summary.output_tokens, 0)} output tokens
        {summary.cost_usd !== null ? ` · about $${formatNumber(summary.cost_usd, 2)}` : ""}
        {summary.dropped_citations.length > 0 ? ` · dropped citations to events that don't exist: ${summary.dropped_citations.join(", ")}` : ""}
      </p>

      <h3 className={layout.subtitle}>the game</h3>
      <p className={layout.muted}>
        <EntityLink id={summary.game} />
      </p>
      <GameReader game={game} storage={storage} focus={focus} />
    </div>
  );
}

export function SummaryInlineLink({ id }: EntityViewProps) {
  const summary = unwrap(useEntity(id as EntityID<GameSummaryData>));
  const game = unwrap(useEntity(summary.game)) as GameData;
  return <>summary of {game.game_id.split("/").slice(-2).join("/")}</>;
}

export function SummaryHoverPreview({ id }: EntityViewProps) {
  const summary = unwrap(useEntity(id as EntityID<GameSummaryData>));
  return (
    <div className={layout.panel}>
      <div>{summary.headline.text}</div>
      <div className={layout.muted}>{summary.why_picked}</div>
    </div>
  );
}

// The results of `clocktower.summaries`: each game's headline and why it was picked.

function asArray(data: unknown): ArrayData {
  if (!isArrayData(data as never)) throw new EntityDataError("expected an array");
  return data as ArrayData;
}

interface Row {
  readonly key: string;
  readonly id: EntityID<GameSummaryData>;
}

function Headline({ id }: { id: EntityID<GameSummaryData> }) {
  const s = unwrap(useEntity(id));
  return <>{s.headline.text}</>;
}

function Why({ id }: { id: EntityID<GameSummaryData> }) {
  const s = unwrap(useEntity(id));
  return <span className={layout.muted}>{s.why_picked}</span>;
}

function Cost({ ids }: { ids: readonly EntityID<GameSummaryData>[] }) {
  const all = ids.map((id) => unwrap(useEntity(id)));
  const cost = all.reduce((a, s) => a + (s.cost_usd ?? 0), 0);
  return <Stat label="cost of the summaries" value={`$${formatNumber(cost, 2)}`} />;
}

function Pending({ spawn }: { spawn: Spawn }) {
  return <InvocationOutcome invocation={unwrap(useInvocation(spawn.ref))} />;
}

function Body({ output }: { output: EntityID<ArrayData> }) {
  const rows: Row[] = rowsOf(asArray(unwrap(useEntity(output)))).flatMap((r) =>
    isEntityID(r.value) ? [{ key: r.key.map(String).join("/"), id: r.value as EntityID<GameSummaryData> }] : [],
  );
  return (
    <>
      <Stats>
        <Stat label="games summarized" value={formatNumber(rows.length, 0)} />
        <Cost ids={rows.map((r) => r.id)} />
      </Stats>
      <DataTable
        rows={rows}
        rowKey={(r) => r.key}
        columns={[
          { key: "game", label: "summary", value: (r) => r.key, cell: (r) => <EntityLink id={r.id} />, width: 260 },
          { key: "headline", label: "headline", value: (r) => r.key, cell: (r) => <Headline id={r.id} /> },
          { key: "why", label: "why picked", value: (r) => r.key, cell: (r) => <Why id={r.id} />, width: 300 },
        ]}
      />
    </>
  );
}

export function SummariesOverview({ invocations }: InvocationPanelProps) {
  const spawn = invocations[0];
  return (
    <div className={layout.panel}>
      <InvocationHead kind="workflow" name="clocktower game summaries" />
      {!spawn ? (
        <p className={layout.empty}>no run</p>
      ) : spawn.output === null ? (
        <Suspense fallback={null}>
          <Pending spawn={spawn} />
        </Suspense>
      ) : (
        <Body output={spawn.output} />
      )}
    </div>
  );
}
