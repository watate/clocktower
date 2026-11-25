// The results overview of `clocktower.index` (and `clocktower.play`, whose result is the index's):
// headline numbers, how often the good side won for each pairing of good and evil model (press a
// cell to list those games), and every game in a table that links to its reader.

import { Suspense } from "react";
import {
  EntityDataError,
  EntityLink,
  isArrayData,
  isEntityID,
  rowsOf,
  scalarEntityId,
  unwrap,
  useEntity,
  useInvocation,
  type ArrayData,
  type EntityData,
  type EntityID,
  type InvocationPanelProps,
  type Spawn,
} from "fxtr-view";
import {
  DataTable,
  InvocationHead,
  InvocationOutcome,
  MISSING,
  ScaleLegend,
  Stat,
  Stats,
  formatNumber,
  formatPercent,
  layout,
  pressable,
  sequentialFill,
  sequentialInk,
  useStoredState,
} from "fxtr-view-kit";
import { TEAM_COLOR } from "./game";
import { type GameSetData, type GameStatsData } from "./types";
import styles from "./overview.module.css";

function asArray(data: EntityData): ArrayData {
  if (!isArrayData(data)) throw new EntityDataError(`expected an array, got ${data.$type}`);
  return data;
}

interface Row extends GameStatsData {
  readonly batch: string;
  readonly game: string;
  readonly id: EntityID;
}

const ALL = "";

function Pending({ spawn }: { spawn: Spawn }) {
  const record = unwrap(useInvocation(spawn.ref));
  return <InvocationOutcome invocation={record} />;
}

function Body({ output, storage }: { output: EntityID<ArrayData>; storage: InvocationPanelProps["storage"] }) {
  const setId = scalarEntityId(asArray(unwrap(useEntity(output)))) as EntityID<GameSetData>;
  const set = unwrap(useEntity(setId));
  const games = rowsOf(asArray(unwrap(useEntity(set.games))));
  const stats = rowsOf(asArray(unwrap(useEntity(set.stats))));
  const statsByKey = new Map(stats.map((r) => [JSON.stringify(r.key), r.value as unknown as GameStatsData]));
  const rows: Row[] = games.flatMap((g) => {
    const s = statsByKey.get(JSON.stringify(g.key));
    return s && isEntityID(g.value) ? [{ ...s, batch: String(g.key[0]), game: String(g.key[1]), id: g.value }] : [];
  });
  const [pick, setPick] = useStoredState<string>(storage, "pairing", ALL);

  const finished = rows.filter((r) => r.winner);
  const goodWins = finished.filter((r) => r.winner === "good").length;
  const goodModels = [...new Set(rows.map((r) => r.good_model))].sort();
  const evilModels = [...new Set(rows.map((r) => r.evil_model))].sort();
  const pairing = (r: Row) => `${r.good_model}|${r.evil_model}`;
  const shown = pick === ALL ? rows : rows.filter((r) => pairing(r) === pick);

  return (
    <>
      <Stats>
        <Stat label="games" value={formatNumber(rows.length, 0)} note={`${rows.length - finished.length} unfinished`} />
        <Stat label="good won" value={formatPercent(finished.length ? goodWins / finished.length : null, 0)} note={`${goodWins} of ${finished.length}`} />
        <Stat label="mean days" value={formatNumber(finished.reduce((a, r) => a + r.days, 0) / Math.max(1, finished.length), 1)} />
        <Stat label="cost" value={`$${formatNumber(rows.reduce((a, r) => a + r.cost, 0), 0)}`} />
      </Stats>

      <h3 className={layout.subtitle}>good side's wins by pairing</h3>
      <p className={layout.muted}>
        Rows: the model playing every good seat. Columns: the model playing every evil seat. Each cell is good's wins of the games
        played; press one to list them below.
      </p>
      <ScaleLegend scale="sequential" low="evil always won" high="good always won" />
      <div className={styles.scroll}>
        <table className={layout.table}>
          <thead>
            <tr>
              <th style={{ color: TEAM_COLOR.good }}>good ↓ · evil →</th>
              {evilModels.map((m) => (
                <th key={m} className={`${layout.num} ${styles.model}`} style={{ color: TEAM_COLOR.evil }}>
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {goodModels.map((g) => (
              <tr key={g}>
                <td className={styles.model} style={{ color: TEAM_COLOR.good }}>{g}</td>
                {evilModels.map((e) => {
                  const cell = finished.filter((r) => r.good_model === g && r.evil_model === e);
                  if (!cell.length) return <td key={e} className={layout.num}>{MISSING}</td>;
                  const wins = cell.filter((r) => r.winner === "good").length;
                  const share = wins / cell.length;
                  const key = `${g}|${e}`;
                  return (
                    <td
                      key={e}
                      className={`${layout.num} ${layout.cellMark}`}
                      style={{ background: sequentialFill(share), color: sequentialInk(share) }}
                      data-picked={pick === key}
                      {...pressable(() => setPick(pick === key ? ALL : key), `${g} good vs ${e} evil: good won ${wins} of ${cell.length}`)}
                    >
                      {wins}/{cell.length}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.head}>
        <h3 className={layout.subtitle}>games</h3>
        {pick !== ALL && (
          <button type="button" className={styles.clear} onClick={() => setPick(ALL)}>
            showing {pick.replace("|", " (good) vs ")} (evil) · show all
          </button>
        )}
      </div>
      <DataTable
        rows={shown}
        rowKey={(r) => `${r.batch}/${r.game}`}
        maxHeight={640}
        columns={[
          { key: "game", label: "game", value: (r) => `${r.batch}/${r.game}`, cell: (r) => <EntityLink id={r.id} />, width: 230 },
          { key: "good", label: "good model", value: (r) => r.good_model },
          { key: "evil", label: "evil model", value: (r) => r.evil_model },
          {
            key: "winner",
            label: "winner",
            value: (r) => r.winner,
            cell: (r) => (r.winner ? <span style={{ color: TEAM_COLOR[r.winner as "good" | "evil"] }}>{r.winner}</span> : MISSING),
            width: 70,
          },
          { key: "minion", label: "minion", value: (r) => r.minion, width: 100 },
          { key: "players", label: "players", numeric: true, value: (r) => r.players, width: 60 },
          { key: "days", label: "days", numeric: true, value: (r) => r.days, width: 50 },
          { key: "good_exec", label: "good executed", numeric: true, value: (r) => r.good_executed, width: 80 },
          { key: "evil_exec", label: "evil executed", numeric: true, value: (r) => r.evil_executed, width: 80 },
          { key: "first_evil", label: "first evil executed", numeric: true, value: (r) => r.first_evil_execution_day, cell: (r) => (r.first_evil_execution_day === null ? MISSING : `day ${r.first_evil_execution_day}`), width: 90 },
          { key: "whispers", label: "whispers", numeric: true, value: (r) => r.whispers, width: 70 },
          { key: "cost", label: "cost", numeric: true, value: (r) => r.cost, cell: (r) => `$${formatNumber(r.cost, 2)}`, width: 70 },
        ]}
      />
    </>
  );
}

export function GamesOverview({ invocations, storage }: InvocationPanelProps) {
  const spawn = invocations[0];
  return (
    <div className={layout.panel}>
      <InvocationHead kind="workflow" name="clocktower games" />
      {!spawn ? (
        <p className={layout.empty}>no run</p>
      ) : spawn.output === null ? (
        <Suspense fallback={null}>
          <Pending spawn={spawn} />
        </Suspense>
      ) : (
        <Body output={spawn.output} storage={storage} />
      )}
    </div>
  );
}
