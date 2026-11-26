// A model's summary of a game whose citations quote the game (`clocktower.cited_summaries`). Each
// citation shows as the number of the event it cites: hover it to read the event with the quoted
// words highlighted, press it to open the game beside the summary at that event, the words marked.

import { Suspense } from "react";
import {
  EntityDataError,
  EntityLink,
  isArrayData,
  isEntityID,
  rowsOf,
  unwrap,
  useEntity,
  useEntityLinks,
  useInvocation,
  type ArrayData,
  type EntityID,
  type EntityPanelProps,
  type EntityViewProps,
  type InvocationPanelProps,
  type Spawn,
} from "fxtr-view";
import { DataTable, InvocationHead, InvocationOutcome, Kind, Stat, Stats, formatNumber, layout } from "fxtr-view-kit";
import { GameReader, GameResult, TEAM_COLOR, teamsOf } from "./game";
import { Cite } from "./summary";
import { type CitedSummaryData, type GameData, type GameEvent, type PartData } from "./types";
import styles from "./summary.module.css";

type Ctx = {
  events: Map<number, GameEvent>;
  team: Map<string, "good" | "evil">;
  onPick: (seq: number, quote: string | null) => void;
};

function Claim({ parts, ctx }: { parts: readonly PartData[]; ctx: Ctx }) {
  return (
    <>
      {parts.map((p, i) =>
        p.event === null ? (
          <span key={i}>{p.text}</span>
        ) : (
          <Cite
            key={i}
            seq={p.event}
            quote={p.quote}
            event={ctx.events.get(p.event)}
            team={ctx.team}
            onPick={(seq) => ctx.onPick(seq, p.quote)}
          />
        ),
      )}
    </>
  );
}

function Claims({ claims, ctx }: { claims: readonly (readonly PartData[])[]; ctx: Ctx }) {
  return (
    <ul className={styles.claims}>
      {claims.map((c, i) => (
        <li key={i}>
          <Claim parts={c} ctx={ctx} />
        </li>
      ))}
    </ul>
  );
}

export function CitedSummaryPanel({ id, storage }: EntityPanelProps) {
  const summary = unwrap(useEntity(id as EntityID<CitedSummaryData>));
  const game = unwrap(useEntity(summary.game)) as GameData;
  const links = useEntityLinks();
  const ctx: Ctx = {
    events: new Map(game.events.map((e) => [e.seq, e] as const)),
    team: teamsOf(game),
    onPick: (seq, quote) => links.open(summary.game, quote === null ? { event: seq } : { event: seq, quote }),
  };
  const cached = summary.cache_read_tokens + summary.cache_write_tokens;

  return (
    <div className={layout.panel}>
      <div className={layout.kindLine}>
        <Kind>Game summary</Kind>
      </div>
      <div className={layout.title}>{game.game_id}</div>
      <GameResult game={game} />
      <p className={layout.muted}>
        Picked because: {summary.why_picked} Written by {summary.model}. Each number is an event a claim rests on: hover it to
        read the event with the quoted words highlighted, press it to open the game beside this summary at that event.
      </p>

      <p className={styles.headline}>
        <Claim parts={summary.headline} ctx={ctx} />
      </p>

      <h3 className={layout.subtitle}>what happened</h3>
      {summary.story.map((s, i) => (
        <div key={i}>
          <div className={styles.day}>{s.title}</div>
          <Claims claims={s.claims} ctx={ctx} />
        </div>
      ))}

      <h3 className={layout.subtitle} style={game.winner ? { color: TEAM_COLOR[game.winner as "good" | "evil"] } : undefined}>
        why {game.winner ?? "nobody"} won
      </h3>
      <Claims claims={summary.decisive} ctx={ctx} />

      <h3 className={layout.subtitle}>notable behavior</h3>
      <Claims claims={summary.notable} ctx={ctx} />

      <p className={layout.muted}>
        {summary.answers === 1 ? "Accepted at the first answer" : `${summary.answers} answers, the last accepted`} ·{" "}
        {formatNumber(summary.input_tokens + cached, 0)} input tokens ({formatNumber(summary.cache_read_tokens, 0)} read from the
        cache) and {formatNumber(summary.output_tokens, 0)} output
        {summary.cost_usd !== null ? ` · about $${formatNumber(summary.cost_usd, 2)}` : ""} · every request and answer:{" "}
        <EntityLink id={summary.judgment} />
      </p>

      <h3 className={layout.subtitle}>the game</h3>
      <p className={layout.muted}>
        <EntityLink id={summary.game} />
      </p>
      <GameReader game={game} storage={storage} />
    </div>
  );
}

export function CitedSummaryInlineLink({ id }: EntityViewProps) {
  const summary = unwrap(useEntity(id as EntityID<CitedSummaryData>));
  const game = unwrap(useEntity(summary.game)) as GameData;
  return <>summary of {game.game_id.split("/").slice(-2).join("/")}</>;
}

/** A claim's text without its citations, for a line of a table or a preview. */
function plain(parts: readonly PartData[]): string {
  return parts
    .filter((p) => p.event === null)
    .map((p) => p.text)
    .join("")
    .replace(/\s+([.,;:])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function CitedSummaryHoverPreview({ id }: EntityViewProps) {
  const summary = unwrap(useEntity(id as EntityID<CitedSummaryData>));
  return (
    <div className={layout.panel}>
      <div>{plain(summary.headline)}</div>
      <div className={layout.muted}>{summary.why_picked}</div>
    </div>
  );
}

// The results of `clocktower.cited_summaries`: each game's headline and why it was picked.

function asArray(data: unknown): ArrayData {
  if (!isArrayData(data as never)) throw new EntityDataError("expected an array");
  return data as ArrayData;
}

interface Row {
  readonly key: string;
  readonly id: EntityID<CitedSummaryData>;
}

function Headline({ id }: { id: EntityID<CitedSummaryData> }) {
  return <>{plain(unwrap(useEntity(id)).headline)}</>;
}

function Why({ id }: { id: EntityID<CitedSummaryData> }) {
  return <span className={layout.muted}>{unwrap(useEntity(id)).why_picked}</span>;
}

function Totals({ ids }: { ids: readonly EntityID<CitedSummaryData>[] }) {
  const all = ids.map((id) => unwrap(useEntity(id)));
  const cost = all.reduce((a, s) => a + (s.cost_usd ?? 0), 0);
  const cites = all.reduce(
    (a, s) =>
      a +
      [s.headline, ...s.decisive, ...s.notable, ...s.story.flatMap((x) => x.claims)].reduce(
        (b, parts) => b + parts.filter((p) => p.event !== null).length,
        0,
      ),
    0,
  );
  return (
    <>
      <Stat label="citations" value={formatNumber(cites, 0)} />
      <Stat label="cost of the summaries" value={`$${formatNumber(cost, 2)}`} />
    </>
  );
}

function Pending({ spawn }: { spawn: Spawn }) {
  return <InvocationOutcome invocation={unwrap(useInvocation(spawn.ref))} />;
}

function Body({ output }: { output: EntityID<ArrayData> }) {
  const rows: Row[] = rowsOf(asArray(unwrap(useEntity(output)))).flatMap((r) =>
    isEntityID(r.value) ? [{ key: r.key.map(String).join("/"), id: r.value as EntityID<CitedSummaryData> }] : [],
  );
  return (
    <>
      <Stats>
        <Stat label="games summarized" value={formatNumber(rows.length, 0)} />
        <Totals ids={rows.map((r) => r.id)} />
      </Stats>
      <DataTable
        rows={rows}
        rowKey={(r) => r.key}
        columns={[
          { key: "game", label: "summary", value: (r) => r.key, cell: (r) => <EntityLink id={r.id} />, width: 240 },
          { key: "headline", label: "headline", value: (r) => r.key, cell: (r) => <Headline id={r.id} /> },
          { key: "why", label: "why picked", value: (r) => r.key, cell: (r) => <Why id={r.id} />, width: 260 },
        ]}
      />
    </>
  );
}

export function CitedSummariesOverview({ invocations }: InvocationPanelProps) {
  const spawn = invocations[0];
  return (
    <div className={layout.panel}>
      <InvocationHead kind="workflow" name="clocktower game summaries, quoting the game" />
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
