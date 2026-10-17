# Phase 10 — Security, QA, Deployment, and Release Readiness

Perform a full audit and close gaps without weakening requirements.

Checklist:
- Authentication and authorization reviewed on every API, server action, and storage operation.
- Subject isolation tests cover DB queries, vector search, citations, generated artifacts, duplicate review, MCP, and signed URLs.
- Validate uploads and protect against path traversal, spoofed MIME types, oversized files, malicious PDFs, and abandoned upload sessions.
- Rate limits and usage budgets for LLM, embeddings, transcription, upload, and MCP.
- CSRF/CORS/cookie/session configuration reviewed for deployment topology.
- Secrets scan and dependency audit; no secrets in git history or frontend bundles.
- Database migrations, backups/restore instructions, deletion/export policy, retention, and error monitoring.
- Accessibility, responsive behavior, Arabic RTL, English LTR, mixed-language content.
- Unit/integration/e2e tests, lint, type-check, production build, and documented manual smoke tests.
- Add deployment guides for frontend, API, worker, DB, object storage, and MCP separately.
- Add `docs/IMPLEMENTATION_STATUS.md` with every criterion marked PASS/FAIL/NOT RUN and evidence.
Do not call the platform production-ready until deployment-specific checks have actually been performed.
