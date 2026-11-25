// The bundle's entry: what this project contributes to the viewer. `fxtr view` builds it into
// dist/ and serves it, rebuilding it as it changes (`fxtr views build` builds it without the
// viewer); each renderer is for a slot, an entity type (or a step or workflow's name), and has an
// id unique in the viewer.

import { EntityHoverPreview, EntityInlineLink, EntityPanel, InvocationPanel, renderer, type ViewBundle } from "fxtr-view";
import { behaviorsRenderers } from "fxtr-view-behaviors";
import { GameHoverPreview, GameInlineLink, GamePanel } from "./game";
import { GamesOverview } from "./overview";
import { SummariesOverview, SummaryHoverPreview, SummaryInlineLink, SummaryPanel } from "./summary";
import { GAME, GAME_SUMMARY, INDEX_WORKFLOW, PLAY_WORKFLOW, SUMMARIES_WORKFLOW } from "./types";

const bundle: ViewBundle = {
  renderers: [
    // Each seat's conversation is a behaviors AgentRun.
    ...behaviorsRenderers,
    renderer(EntityPanel, GAME, "clocktower-fxtr.GamePanel", GamePanel),
    renderer(EntityInlineLink, GAME, "clocktower-fxtr.GameInlineLink", GameInlineLink),
    renderer(EntityHoverPreview, GAME, "clocktower-fxtr.GameHoverPreview", GameHoverPreview),
    renderer(InvocationPanel, INDEX_WORKFLOW, "clocktower-fxtr.GamesOverview", GamesOverview),
    renderer(InvocationPanel, PLAY_WORKFLOW, "clocktower-fxtr.PlayOverview", GamesOverview),
    renderer(EntityPanel, GAME_SUMMARY, "clocktower-fxtr.SummaryPanel", SummaryPanel),
    renderer(EntityInlineLink, GAME_SUMMARY, "clocktower-fxtr.SummaryInlineLink", SummaryInlineLink),
    renderer(EntityHoverPreview, GAME_SUMMARY, "clocktower-fxtr.SummaryHoverPreview", SummaryHoverPreview),
    renderer(InvocationPanel, SUMMARIES_WORKFLOW, "clocktower-fxtr.SummariesOverview", SummariesOverview),
  ],
};

export default bundle;
