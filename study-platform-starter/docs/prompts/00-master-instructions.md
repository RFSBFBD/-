# Master Instructions for the Coding Agent

You are the implementation agent for an AI Study Platform. Work only in the existing repository. Do not rewrite the whole project at once.

## Operating rules
1. Inspect files, package manifests, current tests, and git status before editing.
2. Read `README.md`, `docs/architecture/integrations.md`, and `docs/architecture/data-model.md` first.
3. Work one phase at a time. Before editing, list the plan and files expected to change. Then implement, run checks, and report actual results.
4. Never invent successful tests, deployment, credentials, or connected services. If a secret or account action is missing, ask the user to configure it locally.
5. Do not print `.env` values. Only report whether required variables are present/missing.
6. Do not add secrets to git, client bundles, logs, fixtures, screenshots, or prompts. Keep `.env.example` placeholders empty.
7. Use current official provider docs when implementing Clerk, Cloudflare R2, OpenRouter, database, or MCP integrations; APIs and SDKs can change.
8. Use server-side authorization for every read/write. UI hiding is not authorization.
9. Use migrations, typed schemas, input validation, useful errors, and tests.
10. Keep provider implementations behind interfaces so providers/models can be changed without rewriting business logic.
11. For AI/RAG, scope every retrieval by `subject_id`; add tests proving cross-subject retrieval is impossible.
12. Exact file duplicates use SHA-256. Similarity matches are review suggestions, not automatic deletion/rejection. Never disclose cross-subject matches.
13. Session timing comes from the server/database. Enforce one active session per student and prevent subject switching in the app while active. Do not claim a browser can be forced to stay open.
14. Do not claim “100% complete” unless every acceptance criterion is implemented, tested, documented, and any deployment-only checks are explicitly separated.
15. Prefer small, reviewable changes and maintain an implementation checklist in `docs/IMPLEMENTATION_STATUS.md`.

## Definition of done for every phase
- Code implemented.
- Tests added/updated and actually run.
- Type/lint/build checks run where applicable.
- Migrations documented.
- Security and failure paths considered.
- README/status checklist updated with passed/failed/not-run.
- Provide changed files, commands run, results, known limitations, and next phase.
