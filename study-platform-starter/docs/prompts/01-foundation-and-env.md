# Phase 1 — Foundation, Environment Validation, and Service Wiring

Inspect the starter scaffold and implement a robust development foundation.

Tasks:
1. Verify frontend and backend can run locally. Fix dependency/version mismatches without unnecessary upgrades.
2. Add typed environment validation for frontend server-side code and FastAPI settings. Fail fast for required variables in the relevant environment, but allow health endpoints to work in local mode where integrations are intentionally unconfigured.
3. Add a safe `/health` and `/ready` contract. Readiness should report only integration status, never secret values or connection strings.
4. Add request IDs, structured logging, error handling, and CORS restricted to configured origins.
5. Add a frontend API client that handles timeouts, typed JSON responses, and normalized errors.
6. Add tests for health, invalid config, CORS, frontend API failure state, and missing configuration.
7. Confirm `.env*` is gitignored except example files. Do not create populated secret files.
8. Document PowerShell and macOS/Linux setup.

Acceptance:
- `npm run build` passes.
- `npm run lint` passes.
- Backend pytest passes.
- Frontend can reach backend `/health`.
- No secrets are logged or committed.
