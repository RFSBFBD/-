# Data Model — target design

This is the planned logical schema. Implement it through versioned migrations; do not create production tables manually without migrations.

## Core identity and subjects
- `profiles(id, clerk_user_id UNIQUE, display_name, role, created_at, updated_at)`
- `subjects(id, created_by, name, normalized_name, created_at, updated_at, archived_at)`
- `subject_members(subject_id, user_id, role, joined_at, UNIQUE(subject_id,user_id))`

## Study sessions
- `study_sessions(id, user_id, subject_id, started_at, ends_at, status, created_at, updated_at)`
- Enforce at most one active session per user with a partial unique index or transaction-safe equivalent.
- Server time is authoritative. Duration is user-selected within configured limits. Do not permit changing `subject_id` while active.
- Browser closure is not preventable; restore the active session on return.

## Files and materials
- `stored_files(id, uploader_id, storage_key, sha256, mime_type, size_bytes, original_filename, created_at)`
- `materials(id, subject_id, stored_file_id, uploader_id, title, material_type, processing_status, created_at, deleted_at)`
- `duplicate_reviews(id, subject_id, candidate_material_id, matched_material_id, similarity_score, status, reviewer_id, reviewed_at, created_at)`
- `materials` is the subject-scoped sharing link. The same physical file can be represented once in storage, but access must be evaluated per material/subject link.
- Exact SHA-256 matches within the same subject should link to or flag the existing material rather than upload another copy.
- Similar but non-identical content should enter manual review. Do not disclose cross-subject matches or metadata.

## AI knowledge and chat (later phases)
- `transcript_segments(id, material_id, subject_id, start_ms, end_ms, text, speaker_label)`
- `knowledge_chunks(id, material_id, subject_id, chunk_index, content, token_count, embedding, metadata_json)`
- `chat_sessions(id, user_id, subject_id, title, created_at, updated_at)`
- `chat_messages(id, chat_session_id, user_id, role, content, citations_json, model_id, usage_json, created_at)`
- `generated_artifacts(id, user_id, subject_id, material_id NULL, artifact_type, input_hash, payload_json, created_at)`
- `quiz_attempts(id, user_id, subject_id, quiz_id, answers_json, score, created_at)`
- `usage_logs(id, user_id, subject_id NULL, provider, model_id, input_tokens, output_tokens, estimated_cost, status, created_at)`
- `mcp_audit_logs(id, user_id, tool_name, subject_id NULL, request_summary, outcome, created_at)`

## Isolation rules
- Subject membership must be checked server-side on every read/write.
- Never accept a subject ID and assume it is authorized.
- All retrieval and artifact reads filter by subject and user permissions.
- Prefer private object storage, opaque object keys, and expiring signed URLs.
