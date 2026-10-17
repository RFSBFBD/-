# Provider Connection Checklist

Use this to check each integration locally without sharing secret values in chat.

## Clerk
- [ ] Google provider enabled in Clerk dashboard
- [ ] Frontend publishable key copied into `.env.local`
- [ ] Secret key copied server-side only
- [ ] Redirect URLs match local and deployed domains
- [ ] Backend token verification configured and tested

## Cloudflare R2
- [ ] Private bucket created
- [ ] Scoped S3-compatible access key created with least privilege
- [ ] Endpoint and bucket name configured
- [ ] CORS rules set only for the chosen upload method/origin
- [ ] Signed upload/download URLs expire and are permission-checked

## Database
- [ ] PostgreSQL database created
- [ ] `DATABASE_URL` configured server-side
- [ ] Migrations applied
- [ ] Subject membership and isolation tests pass
- [ ] pgvector enabled if using vector search

## OpenRouter / chat model
- [ ] API key configured server-side
- [ ] A specific chat model ID selected after checking its current context, cost, availability, and rate limits
- [ ] Small smoke test passes
- [ ] Usage and error tracking enabled
- [ ] No claim of unlimited tokens

## Embeddings
- [ ] Separate embedding provider/model chosen
- [ ] Vector dimensions confirmed
- [ ] Model/version included in embedding cache key
- [ ] Re-embedding plan documented for model changes

## Deployment
- [ ] Production origins set
- [ ] Secrets added to deployment secret manager, not committed
- [ ] Health/readiness probes configured
- [ ] Database backup and restore tested
