# Phase 5 — Private Cloud Upload, Library, and Duplicate Review

Implement private Cloudflare R2 storage and the shared library.

Requirements:
- Upload initiation checks authentication, subject membership, file type/size limits, and rate limits.
- Use short-lived signed upload/download URLs or backend-proxied access; never expose R2 secrets.
- Compute SHA-256 on trusted server-side processing. Do not trust a browser-supplied hash alone.
- Exact duplicate detection is scoped to the same subject. Reuse/link the existing material or show a safe duplicate warning; avoid storing the same physical bytes twice where feasible.
- Similar-but-not-identical file/content matches go to manual review. Similarity must never automatically delete or reject the candidate.
- Do not reveal cross-subject matches, file names, or whether a matching file exists elsewhere.
- Library fields: filename, subject, uploader, type, size, upload date, processing status, duplicate/review status.
- Add malware/content-type validation hooks, upload limits, cleanup of abandoned multipart uploads, and audit events.
- Tests: unauthorized upload/download, same-subject exact duplicate, cross-subject privacy, manual similarity review, expired signed URL.
Acceptance: files remain private and accessible only through authorized subject membership.
