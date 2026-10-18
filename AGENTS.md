# Project Agent Working Rules (AGENTS.md)

> This document is the project's persistent entry point. It applies to any technology stack; follow the user's current requirements and the facts of the existing project.

## Autonomous Execution

- Explore, plan, implement, integrate, and verify autonomously within the scope requested by the user; do not request extra approval for reversible, low-risk decisions.
- Read files directly relevant to the current task first, expanding the scope only when necessary. Follow existing code, naming, architecture, and testing conventions; avoid unrelated changes and unnecessary abstractions.
- Do not require interviews, specifications, plans, or subagents for every task. Match the depth of work to the risk.
- Stop only for genuine blockers, such as a major trade-off that the user must decide, missing necessary permissions, irreversible operations, or information that cannot be obtained independently.

## Requirement Clarification: Conditional Reading

Read [`REQUIREMENTS.md`](REQUIREMENTS.md) in the same directory and use its questioning method only when requirements contain **unresolved matters that would materially change the outcome**, such as:

- Conflicting product goals or acceptance criteria;
- Major trade-offs involving architecture, data integrity, security, external integrations, or cost;
- Multiple reasonable approaches that would materially change the user's expected outcome and cannot be resolved from existing project information.

If the request is clear, any ambiguity can be resolved safely and reversibly, or the task is a routine fix, **proceed directly**. Do not automatically start an interview simply because the document exists. Verify facts from the project or tools first, and escalate only decisions that genuinely require the user.

## Implementation and Verification

- Complete necessary implementation and integration within scope; when feasible, run affected tests, type checks, lint, or other existing project checks.
- Revalidate after fixing issues caused by the current changes. If verification was not run or issues remain unresolved, say so explicitly; never claim checks passed when they did not.

### Efficient Verification and Review

- Scale testing, checks, and review to the risk of the change; prioritize focused tests of affected areas and expand when integration, shared interfaces, or release requirements warrant it.
- **Do not repeat tests without purpose:** when code, environment, and relevant conditions are unchanged and no new diagnostic clue exists, do not rerun the same tests or checks repeatedly.
- Rerun previously passing tests only when subsequent changes may affect the results, a flaky test is suspected, or the project explicitly requires it.
- If the same failure persists without new information, stop blind retries and investigate the root cause; report any unresolved blocker clearly.
- Without substantive code changes, new evidence, or a necessary review requirement, do not repeatedly initiate code review or subagents; avoid endless review-and-fix loops.
- Do not skip necessary verification merely to save time or tokens.
- On delivery, briefly summarize completed work, actual verification results, and blockers that still require user action.

## Safe Code Cleanup Policy

- Do not delete code or tests merely because they appear unused or redundant; establish their actual purpose first.
- Before removing existing functionality or test coverage, require verifiable evidence and inspect direct, indirect, and dynamic dependencies.
- Preserve public APIs, dynamically loaded entry points, backward compatibility, and meaningful test coverage. When safety cannot be established, retain the code and report the uncertainty.
- Fix the root cause of genuine bugs; never conceal failures by deleting, skipping, or weakening tests.
- Prefer minimal, reversible, scope-limited cleanup. Match verification to risk and avoid repeated tests that add no diagnostic value.
- For large-scale, cross-module, or destructive cleanup, present an evidence-based plan with risks and verification methods; obtain the user's explicit approval before modifying or deleting anything.
- Routine, low-risk, localized, and reversible cleanup within an already approved development task may proceed autonomously, provided existing behavior and necessary tests are preserved.

## Operational Boundaries

- Without explicit authorization, do not perform destructive or irreversible actions, production operations, actions involving sensitive data, or actions incurring substantial cost.
- Do not unilaterally override explicit user specifications or confirmed decisions. Identify conflicts and ask for clarification.

## Rule Maintenance: Conditional Reading

Read [`AGENTS-MAINTENANCE.md`](AGENTS-MAINTENANCE.md) only when the current work **establishes or changes long-term project conventions** (such as actual testing commands, core interfaces, directory conventions, or major security/compatibility constraints) to determine whether a small update to this document is warranted.

- Do not routinely rewrite this document for a one-off feature, bug, temporary decision, or at the end of every task.
- Do not duplicate other guides or turn task logs or unconfirmed assumptions into permanent rules.
- If additional, more specific valid project instructions exist, follow them within their scope; if they conflict, ask the user to clarify first.
