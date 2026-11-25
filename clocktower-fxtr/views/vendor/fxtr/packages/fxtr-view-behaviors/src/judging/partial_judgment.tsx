// A judgment that `judge` is still making: a step's live preview (`ctx.preview`), which `judge`
// publishes as a partial `Judgment` (its `preview` argument, behaviors/judging/judge.py). Its
// attempts leave out their requests, since each one repeats the entities. A finished attempt holds
// its answer (or its failed call) and why the answer was not accepted. The attempt in flight is
// the last one, and holds the answer so far; its reasons are not known yet. The panel lists the
// answers as the judgment's conversation pane does (judgment_panes.tsx), under a header that says
// the judgment is in progress. The line says which attempt it is on and what that attempt waits
// on. When the step stores the judgment, the judgment's own views take its place, with its whole
// conversation.

import shared from "../behaviors.module.css";
import { isDataMap, type DataMap, type EntityData, type PartialEntityInlineProps, type PartialEntityPanelProps } from "fxtr-view";
import { inProgressLabel, partialMessages } from "../entities";
import type { MessageData } from "../types";
import { JudgmentDetail, JudgmentLine } from "./judgment";
import { JudgeMessages, answerEntries, attemptsLine, outcomeOf, type ConversationEntry } from "./judgment_panes";
import { judgmentOf, type AttemptData } from "./types";

/** A judgment still being made, as its preview's views read it: its finished attempts, and the
 *  answer so far of the attempt in flight. `finished` holds each attempt's response alone:
 *  `judge` leaves the requests out of its preview, since each one repeats the entities. Why an
 *  answer was not accepted is read with `reasonsOf` (attempt_outcome.tsx). `replyInFlight` is
 *  empty before the answer starts, and null when no attempt is in flight, as in the last preview
 *  of a step whose call failed. */
export interface JudgmentSoFar {
  readonly finished: readonly Pick<AttemptData, "response">[];
  readonly replyInFlight: readonly MessageData[] | null;
}

/** Read a judgment still being made. The attempt in flight is the last one while its reasons are
 *  not known (null). A finished attempt's reasons are a list, which is empty when nothing was wrong. */
export function judgmentSoFar(value: EntityData): JudgmentSoFar {
  const attempts: readonly DataMap[] = Array.isArray(value["attempts"]) ? value["attempts"].filter(isDataMap) : [];
  const last = attempts.at(-1);
  if (last === undefined || Array.isArray(last["invalid_output_reasons"])) {
    return { finished: attempts as unknown as readonly Pick<AttemptData, "response">[], replyInFlight: null };
  }
  const response = isDataMap(last["response"]) ? last["response"] : null;
  return { finished: attempts.slice(0, -1) as unknown as readonly Pick<AttemptData, "response">[], replyInFlight: partialMessages(response?.["output"]) };
}

/** What the attempt in flight is doing: its answer streaming, or waiting for the model. Once the
 *  step has stopped (`live` false), its answer was cut off, or there was none. */
function inFlightNote(started: boolean, live: boolean): string {
  if (live) return started ? "streaming…" : "waiting for the model…";
  return started ? "answer cut off" : "no answer";
}

/** The answers so far, as the conversation pane lists answers: each finished attempt's answer
 *  with how it went (or its failed call), then the answer being written, or a note that the
 *  attempt waits for the model. */
function entriesSoFar({ finished, replyInFlight }: JudgmentSoFar, live: boolean): ConversationEntry[] {
  const entries = finished.flatMap((attempt, index) => answerEntries(attempt, index));
  if (replyInFlight === null) return entries;
  const note = `attempt ${finished.length + 1} · ${inFlightNote(replyInFlight.length > 0, live)}`;
  if (replyInFlight.length === 0) return [...entries, { pending: note }];
  return [...entries, ...replyInFlight.map((message) => ({ message, note, streaming: true }))];
}

/** A judgment still being made, in a panel. Its header gives its kind, that it is in progress (or
 *  stopped before finishing, once its step has stopped), and how its finished attempts went. Its
 *  answers follow, and end in the answer being written. A finished judgment (a step can publish
 *  one as its preview) shows as a stored one does. */
export function JudgmentPartialPanel({ value, partial, live }: PartialEntityPanelProps) {
  if (!partial) {
    const judgment = judgmentOf(value);
    if (judgment === null) throw new Error("This judgment is in a shape these views do not read.");
    return <section className={shared["panel"]} aria-label="Judgment"><JudgmentDetail judgment={judgment} /></section>;
  }
  const soFar = judgmentSoFar(value);
  return (
    <section className={shared["panel"]} aria-label="Judgment">
      <header className={shared["header"]}>
        <span className={shared["kind"]}>Judgment</span>
        <span className={shared["muted"]}>{inProgressLabel(live)}</span>
        {soFar.finished.length > 0 && <div className={shared["muted"]}>{attemptsLine({ attempts: soFar.finished })}</div>}
      </header>
      <JudgeMessages entries={entriesSoFar(soFar, live)} />
    </section>
  );
}

/** A judgment still being made, in one line: the attempt it is on, how many answers were invalid,
 *  and what the attempt waits on (`Judgment · attempt 2 · 1 invalid · streaming…`). With no
 *  attempt in flight, the line says how the attempts went. This is the last preview of a step
 *  whose call failed. A finished judgment reads as its inline link does. */
export function JudgmentPartialInline({ value, partial, live }: PartialEntityInlineProps) {
  if (!partial) return <JudgmentLine judgment={judgmentOf(value)} />;
  const { finished, replyInFlight } = judgmentSoFar(value);
  if (replyInFlight === null) {
    const parts = [...(finished.length === 0 ? [] : [attemptsLine({ attempts: finished })]), live ? "in progress" : "stopped"];
    return <span>{["Judgment", ...parts].join(" · ")}</span>;
  }
  const invalid = finished.filter((attempt) => outcomeOf(attempt) === "invalid").length;
  const parts = [`attempt ${finished.length + 1}`, ...(invalid > 0 ? [`${invalid} invalid`] : []), inFlightNote(replyInFlight.length > 0, live)];
  return <span>{["Judgment", ...parts].join(" · ")}</span>;
}
