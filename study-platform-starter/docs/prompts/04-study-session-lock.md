# Phase 4 — Mandatory Study Session Engine

Implement the server-authoritative study-session rules.

Requirements:
- Before entering a study workspace, user chooses a custom duration within admin-configurable minimum/maximum bounds.
- Create the session using database/server time and store `started_at`, `ends_at`, `status`, `subject_id`.
- Enforce at most one active session per user using transaction-safe logic and a database constraint where supported.
- While active, block subject switching and other in-app navigation that would leave the active subject workspace; route back to the active subject on refresh/new tab/relogin.
- A client timer is display-only. Server time determines expiry.
- At expiry, mark session complete safely and allow normal navigation.
- Handle concurrent tabs, clock skew, API retries, expired sessions, and manual sign-out.
- Do not claim to prevent closing the browser/device; recover state on return.
- Admin-configurable bounds and audit events.
Tests must cover race conditions, reload, concurrent tabs, attempted subject switching, time expiry, and forged client timestamps.
