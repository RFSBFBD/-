# AI Study Platform — Starter Scaffold

This repository is the integration foundation for the AI study platform. It is intentionally a **starter**, not a claim that the full product is complete.

## Included
- Next.js App Router + TypeScript frontend starter
- FastAPI backend starter
- Frontend-to-backend health check
- Central integration architecture document
- `.env.example` files for frontend and backend
- Docker Compose for local development
- Model/RAG integration plan designed around a provider adapter (OpenRouter by default)
- Phased coding-agent prompts for completing the product
- Security and acceptance checklist

## Important secrets note
Real credentials from Clerk, Cloudflare, OpenRouter, and your database are **not** included. Do not put secrets in source control or send them to a coding agent. Copy `.env.example` to `.env.local` / `.env` and enter values locally. The scaffold cannot access or verify credentials merely because an account is connected to ChatGPT.

## Proposed stack
- Frontend: Next.js App Router, TypeScript
- Authentication: Supabase Auth (Google sign-in)
- Backend API: FastAPI (Python)
- Database: PostgreSQL; Supabase is an optional managed provider
- Object storage: Cloudflare R2 using S3-compatible API
- AI generation: OpenRouter via a provider adapter
- Embeddings: configurable embedding provider; do not assume the chat model also supports embeddings
- Retrieval: PostgreSQL + pgvector (or a compatible vector store)
- Background work: Redis + Celery/RQ can be added when processing pipelines are implemented

## Start locally
Prerequisites: Node.js LTS, Python 3.11+, Docker Desktop (recommended), and npm.

1. Copy environment examples:
   - `cp .env.example .env.local`
   - `cp backend/.env.example backend/.env`
   On Windows PowerShell, use `Copy-Item .env.example .env.local` and `Copy-Item backend/.env.example backend/.env`.
2. Add your own local credentials and URLs.
3. Start services:
   - `docker compose up --build`
4. Frontend: `http://localhost:3000`
5. Backend docs: `http://localhost:8000/docs`
6. Backend health: `http://localhost:8000/health`

The frontend starter has a basic backend health indicator. Authentication is wired through Clerk; upload flows and AI features are implemented phase by phase.

## Run checks locally

Backend:
- PowerShell / macOS / Linux: `python -m pytest` (from `backend/`)

Frontend (from `frontend/`):
- `npm run lint`
- `npm run test`
- `npm run build`

## Database (PostgreSQL + pgvector)

Local development uses the `postgres` service in `docker-compose.yml` (image `pgvector/pgvector:pg16`).

- Start just the database: `docker compose up -d postgres`
- Connection string (inside Docker): `postgresql+psycopg://study:study@postgres:5432/study`
- Connection string (from the host): `postgresql+psycopg://study:study@localhost:5432/study`

Set `DATABASE_URL` in `backend/.env`. Keep it server-side only; never expose it to the browser.

### Migrations (Alembic)

Run from `backend/` with `DATABASE_URL` configured:

- Apply: `python -m alembic upgrade head`
- Roll back one revision: `python -m alembic downgrade -1`
- Create a new revision (after editing models): `python -m alembic revision --autogenerate -m "message"`

PowerShell / macOS / Linux use the same commands.

## Supabase Auth (Google sign-in) local setup

1. Enable the Google provider in the Supabase dashboard (Authentication → Providers → Google).
2. Copy values into `.env.local` (frontend): `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
3. Copy token-verification values into `backend/.env`: `SUPABASE_URL` (or `SUPABASE_ISSUER`/`SUPABASE_JWKS_URL`), `SUPABASE_AUDIENCE` (default `authenticated`).
   - `SUPABASE_ISSUER` is typically `https://<project-ref>.supabase.co/auth/v1`.
   - `SUPABASE_JWKS_URL` is typically `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`.
4. Restart both apps. `/dashboard` and other private routes redirect to `/sign-in` until authenticated.

When Supabase variables are absent, the app still boots in local mode: the header shows a "Supabase غير مهيأ" badge and protected pages render a setup notice instead of private data. The API returns `503` for token-protected routes while the provider is unconfigured.

## Object storage (uploads)

Files are private and only reachable through subject membership. The backend selects a provider automatically:

- `STORAGE_BACKEND=auto` (default): uses Cloudflare R2 when `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, and `R2_ENDPOINT_URL` are set; otherwise falls back to local disk.
- `STORAGE_BACKEND=r2`: R2 only (required for production; downloads use short-lived presigned URLs).
- `STORAGE_BACKEND=local`: writes under `LOCAL_STORAGE_DIR` and serves HMAC-signed, expiring backend URLs (development/tests only).

Additional settings: `API_PUBLIC_BASE_URL` (base for local signed URLs), `SIGNED_URL_TTL_SECONDS`, `UPLOAD_RATE_LIMIT_PER_MINUTE`, `DUPLICATE_SIMILARITY_THRESHOLD`, `MAX_UPLOAD_SIZE_MB`. Never expose R2 credentials or `INTERNAL_API_SECRET` to the browser.

## AI provider and subject-scoped RAG

Chat and embeddings are provider-agnostic (`app/ai/`). Configure them independently; keys stay server-side.

- Chat: `AI_API_KEY`, `AI_CHAT_MODEL`, `AI_BASE_URL` (any OpenAI-compatible `/chat/completions` provider; model id is configurable, never hardcoded). Works with OpenRouter, Google Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`, e.g. `gemini-flash-latest`), Groq, etc.
- Embeddings: `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL` (any OpenAI-compatible `/embeddings` endpoint), optional `EMBEDDING_DIMENSIONS` (verified against responses; must match the pgvector column). Google Gemini: `gemini-embedding-001` with `EMBEDDING_DIMENSIONS=1536`.
- Behavior/budgeting: `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`, `RAG_TOP_K`, `RAG_MAX_CONTEXT_CHARS`, `RAG_MAX_OUTPUT_TOKENS`, `CHUNK_TARGET_CHARS`, `CHUNK_OVERLAP_CHARS`.

Ingestion (`POST /subjects/{id}/materials/{id}/ingest`) parses the file (PDF via `pypdf`, or text), chunks it, caches embeddings by content hash + model version, and upserts idempotently. Questions (`POST /subjects/{id}/ask`) retrieve with a mandatory `subject_id` filter executed in the database query (pgvector cosine distance on PostgreSQL), return citations to authorized sources, and decline when sources do not support an answer. `EMBEDDING_DIMENSIONS` must match the `vector` column dimension created by migration `0005`; changing to a differently sized embedding model requires a new migration.

Token/context limits are bounded and explicit — there is no unlimited context. Context is capped by `RAG_MAX_CONTEXT_CHARS`, output by `RAG_MAX_OUTPUT_TOKENS`, and retrieval depth by `RAG_TOP_K`. Provider calls are billed per token and free tiers are rate-limited; every embedding and chat call writes a `UsageLog` row (provider, model, input/output tokens) so usage and cost are observable.

## Audio transcription and study artifacts

Audio materials can be transcribed with timestamps, and any material can drive generated study artifacts — all through provider interfaces so no vendor is hardcoded.

- Transcription (`TRANSCRIPTION_PROVIDER`): `""`/`none` disables it; `local` runs a local `faster-whisper` model (`WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_DEFAULT_LANGUAGE`). The heavy dependency is optional: `pip install faster-whisper`. Without it the API returns `503` for transcription while everything else keeps working.
  - `POST /subjects/{id}/materials/{id}/transcribe` — transcribe an audio material; segments carry `start_ms`/`end_ms` and per-segment confidence. Re-running replaces segments atomically; failures mark the material `failed` without destroying prior data.
  - `GET /subjects/{id}/materials/{id}/transcript` — read the stored segments.
- Study artifacts (`notes`, `quiz`, `quiz_explanation`, `revision_cards`, `mind_map`, `code_descriptions`, `concept_alignment`):
  - `POST /subjects/{id}/artifacts` — generate from `material_ids`; notes distinguish source vs. inference and capture teacher emphasis with confidence; citations are assembled server-side from authorized sources (never from model output).
  - Results are cached per `(subject, type, input hash, prompt version, model, settings)`; pass `force: true` to regenerate. `GET /subjects/{id}/artifacts`, `GET /artifacts/{id}`, `POST /artifacts/{id}/regenerate`, `POST /artifacts/{id}/feedback`.
  - Budgeting: `ARTIFACT_MAX_OUTPUT_TOKENS`, `ARTIFACT_MAX_SOURCE_CHARS`.

The subject page includes a **أدوات الدراسة** panel (transcribe, view transcript, generate artifacts, view citations, feedback, regenerate). All authorization is enforced server-side using verified identity and subject membership; non-members receive `404`.

## Coding-agent workflow
Use `docs/prompts/00-master-instructions.md` first, then execute prompts in `docs/prompts/` sequentially. Ask the agent to inspect the current repo and run tests after each phase. Do not ask it to implement every phase in one huge change.

## Product constraints that must not be weakened
- Each student's subject is isolated by a stable `subject_id`.
- Materials and retrieval results are scoped to the current subject.
- Sharing scope is **same subject only**.
- Exact duplicates are detected with SHA-256. Similar-but-not-identical files go to manual review.
- Study session time is server-authoritative and survives refresh/relogin.
- One active study session per student; prevent subject switching within the app while active.
- Browser/device closure cannot be technically prevented. On return, restore the active session and redirect to its subject until it expires.
- Never expose service-role keys or storage secrets to the browser.
- All authorization must be enforced server-side, not only in UI.
