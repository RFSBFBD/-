# Phase 2 — Clerk Google Authentication and Roles

Implement Clerk authentication according to the current official Clerk Next.js and backend verification guidance.

Requirements:
- Google sign-in/sign-up through Clerk.
- Protect dashboard and all private routes.
- Create/sync a local `profiles` row using a stable Clerk user ID.
- Roles: `student` and `admin`; no client-controlled role assignment.
- Verify API access tokens server-side in FastAPI using the supported Clerk verification approach (issuer, signature/JWKS, authorized parties as applicable).
- Add logout and account/session states.
- Ensure local development has a documented setup path when Clerk env vars are absent.
- Add tests for unauthenticated access, invalid token, wrong issuer/authorized party, and role escalation attempts.
- Do not store OAuth secrets in the browser.
Acceptance: a student cannot call protected API endpoints without a valid verified identity; only authorized admins can access admin endpoints.
