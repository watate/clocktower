// The stored forms of the project's entities (src/clocktower_fxtr/games.py), as the viewer hands
// them over: a map of fields, references as EntityIDs.

import type { ArrayData, DataValue, EntityData, EntityID } from "fxtr-view";

export const GAME = "local.clocktower_fxtr.Game.v1";
export const GAME_SET = "local.clocktower_fxtr.GameSet.v1";
export const INDEX_WORKFLOW = "clocktower.index";
export const PLAY_WORKFLOW = "clocktower.play";

export type SeatData = {
  readonly name: string;
  readonly character: string;
  readonly shown: string;
  readonly final_character: string;
  readonly team: "good" | "evil";
  readonly model: string;
  readonly conversation: EntityID | null;
};

/** One line of events.jsonl. `to` is "public", "audit" (private records: thinking, the
 *  Storyteller's choices, deaths), or the seats that saw it. */
export type GameEvent = {
  readonly seq: number;
  readonly day: number;
  readonly phase: string;
  readonly kind: string;
  readonly data: { readonly [k: string]: DataValue };
  readonly to: "public" | "audit" | readonly string[];
  readonly dead: readonly string[];
};

export interface GameData extends EntityData {
  readonly game_id: string;
  readonly protocol: string;
  readonly good_model: string;
  readonly evil_model: string;
  readonly winner: string | null;
  readonly reason: string | null;
  readonly days: number;
  readonly seed: number;
  readonly players: number;
  readonly minion: string | null;
  readonly cost: number;
  readonly seats: readonly SeatData[];
  readonly bluffs: readonly string[];
  readonly events: readonly GameEvent[];
  readonly probes: readonly ProbeData[];
}

/** One belief probe: at a point of a day, one seat's estimate for every other seat. */
export type ProbeData = {
  readonly day: number;
  readonly point: string;
  readonly player: string;
  readonly team: string;
  readonly alive: boolean;
  readonly players?: { readonly [name: string]: { readonly evil?: number; readonly demon?: number; readonly character?: string } };
};

export interface GameStatsData {
  readonly good_model: string;
  readonly evil_model: string;
  readonly winner: string | null;
  readonly reason: string | null;
  readonly days: number;
  readonly players: number;
  readonly minion: string | null;
  readonly cost: number;
  readonly whispers: number;
  readonly says: number;
  readonly nominations: number;
  readonly good_executed: number;
  readonly evil_executed: number;
  readonly first_evil_execution_day: number | null;
}

export interface GameSetData extends EntityData {
  readonly games: EntityID<ArrayData>;
  readonly stats: EntityID<ArrayData>;
}
