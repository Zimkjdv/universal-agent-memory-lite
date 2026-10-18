# Requirements Clarification Guide (REQUIREMENTS.md)

> This guide is an **on-demand interview procedure**, not a required step for every task. Use it only when the material ambiguity triggers in `AGENTS.md` apply or the user explicitly requests a deep requirements interview.

## Purpose

Resolve decisions that would change the goal, architecture, risk, or acceptance criteria before implementation, without delaying work over minor details.

## Procedure

1. **Check facts first:** Inspect relevant code, documentation, and available tools. Do not ask the user for facts you can retrieve yourself.
2. **Sketch a compact decision tree:** Identify unresolved high-impact decisions and their dependencies. Ask only questions whose prerequisites are settled.
3. **Ask in rounds:** Group a small number of independent questions per round. For each, explain the context, key alternatives, **your recommendation and why**, and meaningful tradeoffs. A recommendation is not an approved decision.
4. **Update after answers:** Reassess the tree and ask follow-ups only when the answer exposes material new decisions. Do not revisit settled choices without new evidence.
5. **Converge promptly:** Stop interviewing once goals, acceptance criteria, major tradeoffs, and irreversible risks are clear enough to proceed safely. Use explicit, reversible defaults for minor choices.
6. **Summarize and act:** Briefly restate confirmed decisions and any nonblocking assumptions. Pause for confirmation only if a consequential decision truly requires formal approval; otherwise continue the original task.

## Worth Asking

- What outcome matters, and what counts as done?
- Which constraints or existing behavior must remain unchanged?
- Which alternatives materially change data, architecture, security, cost, or maintainability?
- Which tradeoffs must the user decide rather than the agent infer?

## Not Worth Asking

- Objective facts available in code or authoritative documentation.
- Low-impact implementation details that are easy to reverse.
- Speculative branches asked only to exhaust every imaginable path.

## Suggested Question Format

**Decision:** [What needs a choice]

**Why now:** [Why it affects implementation]

**Options:** [Only the significant alternatives]

**Recommendation:** [Preferred option, brief reasoning, and cost/tradeoff]

> If the user explicitly requests a full Grill Me-style interview, explore more deeply while respecting dependencies, discovery costs, and their wish to stop.
