# Integration Architecture & Environment Contract

## Goal
This document is the source of truth for external integrations and environment variable ownership. Update it whenever a provider or variable changes.

## Components
1. **Next.js web app** — UI, route-level experience, and server-side Clerk integration.
2. **FastAPI service** — authorization-aware API, uploads orchestration, AI orchestration, and long-running processing entry points.
3. **Clerk** — Google sign-in and identity. Verify JWTs on the server/API; never trust a user ID supplied by the browser without verifying the token.
4. **PostgreSQL + pgvector** — relational records and vector retrieval. Use migrations; enforce subject membership and authorization in the data access layer and database where available.
5. **Cloudflare R2** — private object storage. Use short-lived signed URLs or backend-proxied access; do not expose account keys.
6. **OpenRouter** — chat/completion model gateway. Select model by environment configuration and keep the adapter provider-agnostic.
7. **Embedding provider** — separate configuration and lifecycle from chat. The chosen chat model may not expose embeddings.
8. **Redis + worker** — optional queue/cache for transcription, OCR, chunking, embeddings, dedup review, and generated study artifacts.
9. **MCP server** — narrow, permission-checked tools only. MCP tools must use the same authorization layer as the API.

## Environment contract

| Variable | Owner | Exposure | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_APP_URL` | Next.js | Browser-safe | Canonical app URL |
| `NEXT_PUBLIC_API_BASE_URL` | Next.js | Browser-visible | API origin |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Next.js | Browser-safe | Clerk frontend initialization |
| `CLERK_SECRET_KEY` | Next.js server only | Secret | Clerk server SDK |
| `DATABASE_URL` | Server/API only | Secret | PostgreSQL connection |
| `SUPABASE_URL` | Server/API | Usually non-secret | Optional Supabase project URL |
| `SUPABASE_ANON_KEY` | Browser only if RLS is correctly configured | Public key | Optional client-side Supabase use |
| `SUPABASE_SERVICE_ROLE_KEY` | Server only | Secret | Bypasses RLS; avoid unless required |
| `CLOUDFLARE_ACCOUNT_ID` | Backend | Internal | R2 account |
| `R2_ACCESS_KEY_ID` | Backend | Secret | R2 S3-compatible credentials |
| `R2_SECRET_ACCESS_KEY` | Backend | Secret | R2 S3-compatible credentials |
| `R2_BUCKET_NAME` | Backend | Internal | Private bucket |
| `R2_ENDPOINT_URL` | Backend | Internal | S3 API endpoint |
| `OPENROUTER_API_KEY` | Backend only | Secret | LLM gateway key |
| `OPENROUTER_CHAT_MODEL` | Backend | Internal | Explicit model ID |
| `EMBEDDING_PROVIDER` | Backend | Internal | Embedding provider name |
| `EMBEDDING_MODEL` | Backend | Internal | Embedding model ID |
| `EMBEDDING_API_KEY` | Backend | Secret | Embedding provider key |
| `REDIS_URL` | Backend/worker | Secret/internal | Queue and cache |
| `INTERNAL_API_SECRET` | Backend only | Secret | Internal service authentication if needed |

## File policy
- Commit only `.env.example` files with empty placeholders.
- `.env.local` and `backend/.env` remain untracked.
- Never put secret values in prompts, screenshots, logs, client bundles, or source code.
- If a credential was exposed, rotate it at the provider.

## AI/RAG model plan
Use separate interfaces:
- `ChatModel.generate(messages, model, options)` — via OpenRouter initially.
- `EmbeddingModel.embed(texts, model)` — independent provider.
- `Reranker.rank(query, passages)` — optional, provider-agnostic.
- `TranscriptionProvider.transcribe(file, language, timestamps)` — separately configurable; audio processing cost must be measured independently.
- `VectorStore.upsert/search` — always accepts `subject_id` and applies it as a mandatory filter.

Do not assume a model offers infinite context or unlimited tokens. Model limits, price, availability, rate limits, and output constraints vary. Implement usage accounting, max context budgeting, retries with bounded backoff, and clear error states.

## Mandatory retrieval boundary
Every material, chunk, embedding, transcript, note, quiz, and citation must carry `subject_id` and an owner/uploader or sharing policy. Every retrieval query must filter by the active `subject_id` before ranking. Add negative tests proving a question in Subject A cannot retrieve any file/chunk from Subject B.

## Initial integration sequence
1. Validate environment variables at startup without printing secrets.
2. Verify Clerk token issuer/signature/audience/authorized party according to current Clerk guidance.
3. Verify database connectivity and migrations.
4. Verify private R2 bucket access with a small server-side test object.
5. Verify OpenRouter model listing/one low-cost smoke test without logging prompts containing private content.
6. Verify embedding dimensions match the vector column and selected embedding model.
7. Verify background worker and queue.
8. Verify all integration checks in CI/staging before production.
