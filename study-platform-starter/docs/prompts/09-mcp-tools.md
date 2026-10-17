# Phase 9 — Permissioned MCP Server

Build a private MCP server exposing only narrow, explicit tools, using the current MCP SDK and current official guidance.

Initial tools:
- `list_subjects`
- `search_materials`
- `get_lesson_notes`
- `create_quiz`
- `get_progress`
- `save_revision_note`

Requirements:
- Authenticate each MCP session/request and bind it to a verified user identity.
- Reuse the same authorization/data-access services as the normal API.
- Every subject-specific tool checks membership and filters by subject.
- Validate arguments, constrain output size, and rate-limit expensive tools.
- No raw SQL tool, arbitrary filesystem access, unrestricted URL fetch, or direct object-store credential exposure.
- Audit tool name, user, subject, outcome, and bounded metadata without storing secrets.
- Document local MCP client setup and deployment transport/auth choices.
- Tests: unauthenticated tool call, cross-subject access, malformed args, oversized results, audit records.
