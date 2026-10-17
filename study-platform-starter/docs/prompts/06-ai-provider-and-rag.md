# Phase 6 — AI Provider Adapter, Knowledge Ingestion, and Subject-Scoped RAG

Implement model-agnostic AI interfaces. Use OpenRouter for chat generation when configured; do not hardcode one model throughout the application.

Interfaces:
- `ChatModel`: chat/completion calls with timeout, bounded retry, usage extraction, and configurable model ID.
- `EmbeddingModel`: embedding calls via a separately configurable provider/model; verify vector dimensions.
- `VectorStore`: upsert/search with mandatory `subject_id` filter.
- `Reranker`: optional interface; gracefully disabled if not configured.
- `TranscriptionProvider`: separate provider interface for audio transcription and timestamps.
- `DocumentParser`: PDF/text parsing, OCR adapter for scanned PDFs, and safe failure states.

Ingestion:
1. Validate uploaded file and resolve material/subject.
2. Extract text/transcript with page or timestamp metadata.
3. Normalize, chunk, and store chunks with `subject_id`, `material_id`, provenance, and content hash.
4. Generate embeddings once per unique content/model version; cache by content hash + model/version.
5. Upsert idempotently. Reprocessing must not create duplicate chunks.
6. Record processing status and retries.

RAG:
- Verify identity and subject access before retrieval.
- Filter by `subject_id` in the database query itself before ranking; never rely on prompt instructions alone.
- Return citations to authorized source files/pages/timestamps.
- If sources do not support an answer, say so rather than inventing a source-grounded claim.
- Include token/context budgeting, usage/cost logs, model limits, rate limits, safe retries, and provider error handling.
- Add tests that plant a secret phrase in Subject B and prove a Subject A query never retrieves or cites it.
- Add evaluation fixtures for Arabic, English, and mixed Arabic-English terminology.
Do not claim unlimited tokens. Explain configured model limits and actual billing/free-tier constraints.
