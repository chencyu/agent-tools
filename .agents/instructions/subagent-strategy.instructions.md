---
applyTo: '**'
---

# Subagent Strategy

## Dispatch

Subagents run concurrently, and only two things order them: one consumes another's output, or both write the same file. Launch together every subagent whose inputs are ready, and give each a write scope that overlaps no concurrently running subagent's.

**Always launch subagents in background mode.** A finished subagent wakes the dispatcher, so blocking on a foreground one gains nothing over idling; until then, continue any work that needs none of their results.

## Model Selection

When dispatching a task to a subagent, choose its model by the scenarios below.

Expense tier table (not every family may be available):

| Tier       | Description                                | Model family    |
| ---------- | ------------------------------------------ | --------------- |
| Free       | Cheapest, practically free.                | `GPT Luna`      |
| Cheap      | Low cost, well within budget.              | `Claude Haiku`  |
| Affordable | Mid-tier; may overrun budget if unchecked. | `Claude Sonnet` |
| Expensive  | Easily exceeds budget.                     | `Claude Opus`   |

Within a tier, always pick the newest available model of its family.

When dispatching to the `Free` tier, explicitly state: "You are dirt cheap, almost free; budget is no concern. Correctness and completeness of the result are the top priority."
Do not mention this for other tiers (use their default behavior).

If no model in the desired tier is available, move up to the next tier that has one.

### Scenarios

- Translate: Always `Free` tier.
- Semantic search:
  1. Let the `Free` tier dump and read the whole context first and pick the relevant information (file paths, line numbers, sections, ...), keyword search is for saving cost and may miss some details.
  2. Then let the `Cheap` tier run targeted keyword searches using the information extracted by the `Free` tier, accounting for naming conventions and word choices.
- Code tracing: Let the `Free` tier trace every code stack exhaustively. Do not trust function/method/variable names; inspect the internal code and code flow instead. For behavior that does not follow from the name or is unexpected, report the symbol as `originalName (new name based on its actual behavior)`.
- Unlisted: Use the same model as the current main agent.
