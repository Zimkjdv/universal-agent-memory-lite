# AGENTS.md Maintenance Guide (AGENTS-MAINTENANCE.md)

> Read this guide **only when a durable project rule may have changed**. It is not an end-of-task checklist.

## When to Consider Updating

- The project establishes or changes real build, run, test, lint, or type-check commands.
- Stable directory structure, core module interfaces, data formats, naming, or compatibility conventions are adopted or revised.
- New durable security, privacy, deployment, data integrity, or backward-compatibility requirements become binding.
- Existing `AGENTS.md` content is obsolete, incorrect, contradictory, or obstructs normal work.
- The user explicitly requests a change to project agent instructions.

## When Not to Update

- One-off features, bug fixes, experiments, meeting notes, or unapproved proposals.
- Reporting what happened during a task, how many times tests passed, or current progress.
- Restating generic behaviors the agent already knows or copying `REQUIREMENTS.md`.
- Speculation, temporary workarounds, or technology choices not yet adopted.

## Update Procedure

1. **Verify facts:** Use code, configuration, test output, or decisions confirmed by the user. Do not infer instructions from guesses.
2. **Classify information:** Place durable operating instructions in `AGENTS.md`, requirement details in specs, history in changelogs/ADRs, and temporary context outside standing rules.
3. **Make the smallest change:** Edit the existing section, remove obsolete content, and avoid duplicates or sprawling workflows.
4. **Preserve user intent:** Never silently remove or weaken important user-authored boundaries. Ask when rules conflict.
5. **Validate usability:** Check that commands, paths, conditions, and referenced files exist. Avoid machine-specific absolute paths.
6. **Report actual updates:** If modified, briefly state the durable rule added or corrected and why. No extra maintenance report is needed if nothing changed.

## Project vs. Global Instructions

- **Global instructions:** Cross-project preferences and safety boundaries.
- **Project `AGENTS.md`:** Durable, actionable facts and restrictions unique to this repository.
- If global instructions exist, avoid copying them verbatim. This template must also work without any global configuration.

## Maintenance Principle

**Shorter is easier to maintain; more specific is easier to execute.** Add what the project genuinely needs, not a new rule after every task.
