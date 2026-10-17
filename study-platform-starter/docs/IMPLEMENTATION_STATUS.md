# Implementation Status

Tracks each phase from `docs/prompts/`. Legend: PASS, FAIL, NOT RUN, PARTIAL.

Latest update: Supabase Auth migration (Clerk removed).

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| 1 | Foundation, environment validation, service wiring | PASS | See below |
| 2 | Clerk auth and roles | PASS | See below |
| 3 | Subjects, membership, same-subject sharing | PASS | See below |
| 4 | Mandatory study session engine | PASS | See below |
| 5 | Upload, library, duplicate review | PASS | See below |
| 6 | AI provider adapter and RAG | PASS | See below |
| 7 | Audio, notes, study artifacts | PASS | See below |
| 8 | Chat, quizzes, revision, progress | NOT RUN | — |
| 9 | Permissioned MCP server | NOT RUN | — |
| 10 | Security, QA, deployment | NOT RUN | — |

## Phase 1 — Foundation, Environment Validation, Service Wiring

Acceptance criteria:

| Criterion | Status | Evidence |
|---|---|---|
| `npm run build` passes | PASS | `next build` succeeded (4/4 static pages) |
| `npm run lint` passes | PASS | `eslint .` exited clean |
| Backend pytest passes | PASS | `18 passed` |
| Frontend unit tests | PASS | `vitest run` — 12 passed |
| Frontend can reach backend `/health` | PASS | `GET /health` → 200 JSON with `X-Request-ID` |
| No secrets logged or committed | PASS | `.env*` ignored except `*.example`; readiness reports `configured` flags only |

Changes:

- Fixed ESLint flat-config mismatch (`frontend/eslint.config.mjs`) for the installed `eslint-config-next@15.x` using `FlatCompat`.
- Backend typed settings with environment-aware validation (`backend/app/config.py`): development boots with unconfigured integrations; non-development fails fast, reporting variable names only.
- Structured JSON logging with request correlation (`backend/app/logging_config.py`).
- Pure ASGI request-context middleware with `X-Request-ID` propagation (`backend/app/middleware.py`).
- Normalized error responses that never leak internal details (`backend/app/errors.py`).
- Health/readiness contracts reporting integration configuration only (`backend/app/health.py`).
- CORS restricted to configured origins from `FRONTEND_ORIGIN` (comma-separated).
- Frontend typed env validation and a timeout-aware API client with normalized errors (`frontend/src/lib/env.ts`, `frontend/src/lib/api-client.ts`, `frontend/src/lib/server-env.ts`).
- Frontend test runner (Vitest) and unit tests for env parsing and API client failure states.

Known limitations:

- `/ready` reports whether integrations are *configured*, not *verified*. Connectivity checks are added with each integration phase.
- `server-only` is currently resolved as a transitive dependency of Next.js; it should be promoted to a direct dependency before deployment (Phase 10).

## Phase 2 — Clerk Authentication and Roles

Acceptance: a student cannot call protected API endpoints without a valid verified identity; only authorized admins can access admin endpoints.

| Requirement | Status | Evidence |
|---|---|---|
| Google sign-in/sign-up via Clerk | PASS | `sign-in`/`sign-up` pages use Clerk components; `ClerkProvider` in `layout.tsx` |
| Protect dashboard and private routes | PASS | `src/middleware.ts` protects `/dashboard(.*)` and `/subjects(.*)`; dashboard re-checks `auth()` server-side |
| Create/sync local `profiles` row | PASS | `services/profiles.py` + tests `test_first_login_creates_student_profile`, `test_profile_sync_is_idempotent` |
| Roles student/admin, no client control | PASS | Role assigned server-side only; `test_role_cannot_be_escalated_by_claims` proves claims are ignored |
| Server-side token verification (issuer, JWKS, authorized party) | PASS | `auth/clerk.py`; unit tests for valid/expired/wrong-issuer/wrong-azp/bad-signature |
| Logout and account/session states | PASS | `SiteHeader` uses `UserButton` (sign-out) and `SignedIn`/`SignedOut` |
| Documented local path when Clerk env absent | PASS | README "Clerk local setup"; UI notices; 503 for protected routes while unconfigured |
| Negative tests (unauth, invalid token, wrong issuer/azp, escalation) | PASS | `test_auth_dependencies.py`, `test_clerk_verifier.py` |
| No OAuth secrets in browser | PASS | Only `NEXT_PUBLIC_*` values reach the client; secret key server-side only |

Commands run:

- `python -m pytest -q` → `35 passed`
- `npm run lint` → clean
- `npm run test` → `12 passed`
- `npm run build` → success (middleware compiled)
- Alembic upgrade/downgrade validated against a temporary SQLite database

Changes:

- Database layer: SQLAlchemy 2.0 + psycopg (sync), lazy engine (`app/db/`), `Profile` model, `pgvector/pgvector:pg16` service in `docker-compose.yml`.
- Alembic configured (`backend/alembic/`) with migration `0001_create_profiles`.
- Clerk verification and authorization dependencies (`app/auth/`), profile sync service (`app/services/profiles.py`).
- Routes `GET /me` and `GET /admin/ping`.
- Frontend Clerk provider, middleware, sign-in/sign-up, protected dashboard, header auth state.

Known limitations:

- The local `profiles` role defaults to `student`; admin promotion is manual (DB-side) until an admin-management phase adds a controlled path.
- `display_name` is populated from token claims when present; a profile-edit endpoint is not part of this phase.
- Readiness still reports configuration, not verified database connectivity (added in later phases).

## Phase 3 — Subjects, Membership, and Same-Subject Sharing

Acceptance: subject CRUD works with authorization and automated negative tests.

| Requirement | Status | Evidence |
|---|---|---|
| Create/rename/archive/open subjects | PASS | `app/routers/subjects.py`; UI `SubjectsManager.tsx` + `/subjects/[subjectId]` |
| Stable UUID ids; names not identifiers | PASS | `Subject.id` UUID; name changes never affect identity |
| Unique name per owner after normalization | PASS | Partial unique index `uq_subjects_owner_normalized_active`; `test_duplicate_normalized_name_per_owner_conflicts` |
| `subject_members` sharing model | PASS | `models/subject.py`; membership endpoints |
| Same-subject-only scope; no cross-subject disclosure | PASS | Non-members receive `404` (never confirming existence) |
| Server-side authorization on every route | PASS | `get_subject_access` joins on membership; caller identity from verified token |
| Never trust submitted user ID | PASS | Caller profile derived from token; membership `user_id` only used as a target for owners |
| Pagination, validation, empty/loading/error states | PASS | `limit`/`offset` bounded; UI states in `SubjectsManager` |
| Negative tests (A vs B, non-member, archived) | PASS | `tests/test_subjects.py` (10 tests) |

Commands run:

- `python -m pytest -q` → `46 passed`
- `npm run lint` → clean
- `npm run build` → success
- Alembic `upgrade head` / `downgrade base` validated on temporary SQLite (both migrations)

Changes:

- `Subject`, `SubjectMember` models + migration `0002_create_subjects`.
- Normalization + subject services with domain errors mapped to HTTP (`app/services/subjects.py`).
- Subjects router with CRUD, archive/unarchive, member management.
- Frontend subjects list, create/rename/archive, pagination, and subject detail page.

Known limitations:

- Sharing a subject currently targets an existing `profiles.id` (no email invite flow yet). Invitations can be added when user discovery is defined.
- Only `owner`/`member` subject roles exist; finer-grained material permissions arrive with uploads (Phase 5).
- The subject workspace itself is a placeholder (study session lock arrives in Phase 4; materials in Phase 5).

## Phase 4 — Mandatory Study Session Engine

Acceptance: the server is the sole authority on study-session timing and on the one-active-session rule.

| Requirement | Status | Evidence |
|---|---|---|
| Duration chosen within admin bounds | PASS | `POST /study-sessions` validates against `study_session.min_minutes`/`max_minutes`; `GET /study-sessions/limits` |
| Session stored with server time + status + subject | PASS | `StudySession` model; `started_at`/`ends_at` from `app/clock.utcnow()` |
| At most one active session (transaction-safe + DB constraint) | PASS | Partial unique index `uq_study_sessions_active_user` + `IntegrityError` recovery; `test_same_subject_restart_is_idempotent` |
| Client timer is display-only | PASS | `StudySessionPanel` derives countdown from server `ends_at`/`server_now`; expiry decided server-side |
| Expiry finalizes safely | PASS | `get_active_session` marks `completed` on read; `test_expired_session_is_finalized` |
| Reload / concurrent tabs | PASS | `test_active_session_survives_reload_and_concurrent_tabs` |
| Attempted subject switching blocked | PASS | Different-subject start → `409 session_already_active`; UI routes back to active subject |
| Forged client timestamps ignored | PASS | Extra `started_at`/`ends_at` in payload ignored; `test_client_supplied_timestamps_are_ignored` |
| Manual sign-out recovery on return | PASS | State reloaded from `/study-sessions/active` on mount/refresh |
| Admin-configurable bounds + audit events | PASS | `GET/PUT /admin/study-session-settings`; `AuditEvent` on start/complete/cancel/expire |
| Negative tests (race, reload, switching, expiry, forged timestamps) | PASS | `tests/test_study_sessions.py` (13 tests) |

Commands run:

- `python -m pytest -q` → `59 passed`
- `npm run lint` → clean
- `npm run test` → `12 passed`
- `npm run build` → success
- Alembic `upgrade head` / `downgrade base` validated on temporary SQLite (all three migrations)

Changes:

- Models `StudySession`, `AppConfig`, `AuditEvent` + migration `0003_create_study_sessions`.
- Server-authoritative clock (`app/clock.py`) and services `study_sessions.py`, `app_config.py`, `audit.py`.
- Routes: `GET /study-sessions/limits`, `GET /study-sessions/active`, `POST /study-sessions`, `POST /study-sessions/{id}/end`; admin `GET/PUT /admin/study-session-settings`.
- Frontend `StudySessionPanel` (start/stop/countdown, redirect to active subject), `ActiveSessionBanner` on dashboard and subjects list.

Known limitations:

- Navigation blocking is enforced at the API boundary; client-side redirects are best-effort UX. The server never enables cross-subject operations while a session is active.
- Admin bounds have a hard ceiling of 600 minutes; changing the ceiling requires a code change.
- Sessions become `completed` lazily on read (no background scheduler); this is intentional and safe for the current single-service deployment.

## Phase 5 — Private Cloud Upload, Library, and Duplicate Review

Acceptance: files remain private and accessible only through authorized subject membership.

| Requirement | Status | Evidence |
|---|---|---|
| Upload checks auth, membership, type/size, rate limits | PASS | `POST /subjects/{id}/materials`; `test_non_member_cannot_upload`, `test_upload_rate_limit`, `test_unsupported_file_type_is_rejected` |
| Signed/proxied access; no R2 secrets exposed | PASS | `StorageProvider` abstraction; R2 presigned URLs, local HMAC-signed proxy; secrets server-side only |
| Server-computed SHA-256 (never trust client) | PASS | `materials.create_material` hashes bytes; browser hash ignored |
| Exact duplicates scoped to subject; link not re-store | PASS | `_find_exact_duplicate`; `test_exact_duplicate_is_linked_not_re_stored` (1 stored file) |
| Similar non-identical → manual review; never auto-delete | PASS | `_find_similar` + `duplicate_reviews`; `test_similar_content_enters_manual_review` |
| No cross-subject matches/names disclosure | PASS | `test_cross_subject_privacy` (same bytes → separate material, 404 on other subject's material) |
| Library fields | PASS | `MaterialOut`: filename, subject, uploader, type, size, date, processing/duplicate status |
| Malware/content-type hooks, limits, orphan cleanup, audit | PASS | `upload_validation.get_malware_scanner`, `cleanup_orphan_stored_files`, `AuditEvent`; `test_orphan_cleanup_removes_unreferenced_files` |
| Negative tests (unauth, dup, privacy, review, expired URL) | PASS | `tests/test_materials.py` (18 tests) |

Commands run:

- `python -m pytest -q` → `77 passed`
- `npm run lint` → clean
- `npm run test` → `13 passed`
- `npm run build` → success
- Alembic `upgrade head` / `downgrade base` + `alembic check` (no drift) on temporary SQLite (all four migrations)

Changes:

- Models `StoredFile`, `Material`, `DuplicateReview` + migration `0004_create_materials`.
- Storage abstraction `app/storage/` with `LocalStorageProvider` (HMAC-signed backend-proxied downloads) and `R2StorageProvider` (boto3 presigned URLs); `auto` backend selects R2 when configured.
- Upload validation with magic-byte sniffing, allow-list, malware scanner hook (`app/services/upload_validation.py`).
- In-memory per-user upload rate limiter (`app/services/rate_limit.py`).
- Material/dedup/review services (`app/services/materials.py`) and routers (`materials`, backend-proxied `storage`).
- Frontend `MaterialsLibrary` (upload/list/download/delete + duplicate review) on the subject page; API client now supports multipart uploads.

Known limitations:

- Malware scanning is a no-op hook until a real scanner (e.g. ClamAV) is wired in.
- The rate limiter is in-process; move to Redis when the API scales horizontally.
- Orphan cleanup is exposed as a service function and must be scheduled (no worker yet).
- Similarity uses normalized-title sequence matching until embeddings arrive (Phase 6).

## Phase 6 — AI Provider Adapter, Knowledge Ingestion, and Subject-Scoped RAG

Acceptance: models are provider-agnostic; ingestion is idempotent and embedding-cached; retrieval is subject-scoped in the query and never leaks cross-subject sources.

| Requirement | Status | Evidence |
|---|---|---|
| `ChatModel` interface (timeout, bounded retry, usage, configurable model id) | PASS | `app/ai/base.py`, `app/ai/openrouter_chat.py` (`OpenRouterChatModel`) |
| `EmbeddingModel` separately configurable + dimension verification | PASS | `app/ai/embeddings.py` (`OpenAICompatibleEmbeddingModel`), `EmbeddingDimensionError` |
| `VectorStore` with mandatory `subject_id` filter | PASS | `app/rag/vector_store.py` filters `subject_id` in SQL before ranking |
| `Reranker` optional, gracefully disabled | PASS | `get_reranker()` returns `None`; RAG over-fetches then trims only when configured |
| `TranscriptionProvider` interface | PASS | Protocol defined in `app/ai/base.py` (adapter wired in Phase 7) |
| `DocumentParser` with OCR hook + safe failure | PASS | `app/ai/documents.py` (pypdf + text; `OcrUnavailable`; failures → `failed`) |
| Validate file, resolve material/subject | PASS | `ingest_material` uses `materials.get_material` (membership enforced) |
| Extract with page/timestamp metadata | PASS | `ParsedPage.page_number`/`start_ms`/`end_ms` preserved in chunk provenance |
| Normalize/chunk/store with subject, material, provenance, hash | PASS | `app/rag/chunking.py`; `KnowledgeChunk` columns |
| Embed once per content hash + model version (cache) | PASS | `_cached_embeddings`; `test_ingestion_chunks_and_is_idempotent` (1 embed call for 2 ingests) |
| Idempotent upsert; no duplicate chunks on reprocess | PASS | Unique `uq_knowledge_chunks_dedupe`; second ingest `inserted_count == 0` |
| Processing status + retries | PASS | `PROCESSING_*` transitions; provider errors recorded and surfaced as safe states |
| Verify identity/subject before retrieval | PASS | `get_subject_access` before embedding/search |
| Filter `subject_id` in DB query, not prompt | PASS | `SqlVectorStore.search`; `test_vector_store_search_filters_by_subject` |
| Citations to authorized sources | PASS | `CitationOut` with material/page/timestamp |
| Say when sources don't support an answer | PASS | `NO_SOURCES_ANSWER`; prompt instructs refusal; `test_answer_without_sources_short_circuits` |
| Token/context budgeting, usage/cost logs, retries, error handling | PASS | `RAG_MAX_CONTEXT_CHARS`/`RAG_MAX_OUTPUT_TOKENS`; `UsageLog` rows; `test_answer_uses_sources_and_logs_usage` |
| Cross-subject isolation test (secret in B never retrieved/cited by A) | PASS | `test_cross_subject_secret_is_never_retrieved_or_cited` |
| Evaluation fixtures (Arabic, English, mixed) | PASS | `test_multilingual_fixtures_retrieve_matching_language`; bilingual system prompt |

Commands run:

- `python -m pytest -q` → `85 passed`
- Alembic `upgrade head` / `downgrade base` + `alembic check` (no drift) on temporary SQLite (all five migrations)

Changes:

- Provider-agnostic AI interfaces (`app/ai/`) and factory (`get_chat_model`, `get_embedding_model`, `get_reranker`).
- OpenRouter chat adapter and OpenAI-compatible embeddings adapter with timeouts, bounded retry with backoff, usage extraction, and normalized errors.
- Document parser (`app/ai/documents.py`) for PDF (pypdf) and text, with an OCR hook and safe failure states.
- Models `KnowledgeChunk`, `UsageLog` + dialect-aware `Vector` type (`app/db/types.py`) + migration `0005_create_knowledge` (enables pgvector on PostgreSQL).
- Vector store (`app/rag/vector_store.py`): pgvector cosine distance on PostgreSQL, Python cosine fallback on SQLite; subject filter in SQL.
- Chunking/normalization (`app/rag/chunking.py`) and ingestion service (`app/services/ingestion.py`) with embedding cache and idempotent upsert.
- RAG service (`app/services/rag.py`) with context budgeting, citations, usage logging, and refusal when unsupported.
- Routes: `POST /subjects/{id}/materials/{id}/ingest`, `POST /subjects/{id}/ask`.

Known limitations:

- `EMBEDDING_DIMENSIONS` must match the column dimension used when the migration ran; changing embedding models with a different dimension requires a new migration.
- The pgvector column cannot be validated against a live PostgreSQL in this environment; SQLite exercises the Python cosine path. Dimension verification happens in the adapter.
- Token counts are character-based estimates for budgeting, not exact tokenizer counts.
- Reranking and audio transcription are interfaces only; concrete adapters arrive with later phases.
- Ingestion runs inline in the request; move to a worker queue when scaling (a worker is planned with the study artifacts phase).

## Phase 7 — Audio Transcription, Detailed Notes, and Study Artifacts

Acceptance: audio is transcribed with timestamps through a provider-agnostic adapter; study artifacts are generated server-side from authorized sources, cached by content/prompt/model, cite their sources, and never leak cross-subject material.

| Requirement | Status | Evidence |
|---|---|---|
| `TranscriptionProvider` adapter (local `faster-whisper`), lazy dependency | PASS | `app/ai/transcription.py` (`LocalWhisperTranscriptionProvider`), `get_transcription_provider()` in `app/ai/factory.py`; heavy import deferred so the app boots without it |
| Transcribe audio with segment timestamps | PASS | `POST /subjects/{id}/materials/{id}/transcribe`; `TranscriptionSegmentOut` with `start_ms`/`end_ms`; `test_transcription_overwrites_and_preserves_timestamps` |
| Per-segment confidence + metadata | PASS | `confidence` derived from `avg_logprob`; segment `metadata` retained; achieved in `app/services/transcription.py` |
| Non-audio rejected; provider-disabled → 503 | PASS | `test_non_audio_material_is_rejected` (422), `test_transcribe_when_provider_disabled_returns_503` |
| Invalid timestamps → safe failure, non-destructive | PASS | `test_invalid_timestamps_mark_failed` (502 + material `failed`); prior segments untouched |
| Provider failure recovery on retry | PASS | `test_failed_transcription_can_be_retried` |
| Idempotent re-transcription (replace, not duplicate) | PASS | Unique `uq_transcript_segments_material_index`; `TranscriptSegment` model |
| Artifact generation (`ChatModel`) from authorized sources | PASS | `app/services/artifacts.py` `generate_artifact`; sources assembled server-side |
| Detailed notes with source-vs-inference split | PASS | `ARTIFACT_SPECS["notes"]` with `kind: source|inference`; `test_notes_artifact_separates_source_and_inference` |
| Emphasis + confidence captured from signals | PASS | `_EMPHASIS` prompt spec → `emphasis` entries (phrase, timestamp_ms, confidence, evidence) |
| Link transcript/PDF provenance in citations | PASS | Citations include material, page number or `start_ms`/`end_ms`; built from our source list, never model output |
| Quizzes, explanations, revision cards, mind map, code descriptions, concept alignment | PASS | `ARTIFACT_TYPES` (7 types); `test_all_artifact_types_generate` |
| Cache by input hash + prompt version + model + settings | PASS | Unique `uq_generated_artifacts_cache`; `test_artifact_cache_hit_then_force_regenerate` (no second model call) |
| Cache invalidation when model changes | PASS | `test_cache_key_changes_with_model_id` |
| Feedback + regenerate | PASS | `POST /artifacts/{id}/feedback` (upsert per user), `POST /artifacts/{id}/regenerate` (`force=True`); `ArtifactFeedback` model |
| Never leak cross-subject material | PASS | Non-member → 404; `test_cross_subject_artifact_is_isolated` |
| Invalid model output → safe failure (502) | PASS | `test_invalid_artifact_json_returns_502` |
| No usable sources → refused (422) | PASS | `test_artifact_without_sources_is_refused` |
| Usage/cost logging | PASS | Each generation writes a `UsageLog` row |
| Evaluation fixtures (Arabic, English, mixed) | PASS | `test_transcription_handles_arabic_and_mixed`; bilingual artifact prompts |
| Frontend tools panel (transcribe, view transcript, generate, feedback, regenerate) | PASS | `frontend/src/components/StudyToolsPanel.tsx` wired into `/subjects/[subjectId]` |

Commands run:

- `python -m pytest tests/test_transcription.py -q` → `6 passed`
- `python -m pytest tests/test_artifacts.py -q` → `9 passed`
- `python -m pytest -q` → `101 passed`
- `npm run lint` → clean
- `npm run test` → `13 passed`
- `npm run build` → success (subject route bundle now includes `StudyToolsPanel`)
- Alembic `upgrade head` / `downgrade base` + `alembic check` (no drift) on temporary SQLite (all seven migrations)

Changes:

- AI: `TranscriptionProvider` implementation `app/ai/transcription.py`; factory `get_transcription_provider`; `ParsedPage.metadata` added to `app/ai/base.py`.
- Models `TranscriptSegment` (`app/models/transcript.py`) and `GeneratedArtifact` + `ArtifactFeedback` (`app/models/artifact.py`) with migrations `0006_create_transcripts` and `0007_create_artifacts`.
- Services `app/services/transcription.py` (replace-on-success, safe failure) and `app/services/artifacts.py` (server-side source assembly, 7 artifact specs, prompt versioning, cache key, feedback).
- Schemas `app/schemas/transcript.py`, `app/schemas/artifact.py`; routers `app/routers/transcription.py`, `app/routers/artifacts.py` registered in `app/main.py`.
- Config: `transcription_provider`, `whisper_*` and `artifact_*` settings with validators; `transcription` reported in `GET /health` integration status.
- Docs/env: `.env.example`, `backend/.env.example`, `docker-compose.yml` updated; `faster-whisper` documented as an optional dependency in `backend/requirements.txt`.

Known limitations:

- The local `faster-whisper` engine is optional and not installed by default (heavy `torch`/`ctranslate2`); transcription is disabled until `TRANSCRIPTION_PROVIDER=local` and the package is installed.
- Transcription runs inline in the request; long audio should move to a worker queue when scaling.
- Emphasis and confidence are model-produced best-effort signals from source text, not a separate acoustic classifier.

## Integration updates

AI provider configuration was generalized and a real provider was verified end-to-end:

- Chat settings renamed from vendor-specific `OPENROUTER_*` to `AI_PROVIDER`, `AI_API_KEY`, `AI_BASE_URL`, `AI_CHAT_MODEL` (`app/config.py`, `app/ai/factory.py`, `app/health.py`). This also prevents a machine-level `OPENROUTER_API_KEY` environment variable from silently overriding the project config.
- Embedding adapter now sends the optional `dimensions` parameter (`app/ai/embeddings.py`) so Matryoshka models can match the pgvector column width.
- Chat adapter tolerates providers that omit text content (returns a clear `AIProviderError` instead of a `KeyError`).
- Verified against Google Gemini's OpenAI-compatible endpoint: chat `gemini-flash-latest` returns text; embeddings `gemini-embedding-001` with `dimensions=1536` matches the column width. `GET /ready` reports `ai_chat` and `embeddings` as configured.
- New adapter unit tests (`tests/test_ai_adapters.py`, 5 tests) cover the `dimensions` payload, dimension mismatch, provider errors, and chat parsing. Full backend suite: `106 passed`.

Still pending (external, user-supplied): Neon `DATABASE_URL` (real connection string), and the Supabase Auth migration (replacing Clerk), which the user selected.







