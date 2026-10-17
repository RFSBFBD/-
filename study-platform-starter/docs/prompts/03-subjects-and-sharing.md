# Phase 3 — Subjects, Membership, and Same-Subject Sharing

Implement database migrations and the subject UI/API.

Requirements:
- Students can create, rename, archive, and open their subjects.
- Subject IDs are stable UUIDs; names are not identifiers.
- Subject names are unique per owner after normalization, unless the product rules explicitly allow duplicates.
- Add `subject_members` for sharing/collaboration and define who can see each subject.
- Material sharing scope is same-subject only. No cross-subject file discovery, search, duplicate disclosure, or citations.
- Add server-side authorization in every route/service; never trust a submitted user ID.
- Add pagination, validation, empty/loading/error states.
- Tests: user A cannot read/change user B's subject; non-member cannot read shared material; archived subject behavior is consistent.
Acceptance: subject CRUD works with authorization and automated negative tests.
