# GREENSMECAPT frontend

The frontend is a React, TypeScript and Vite application for SME onboarding,
private document upload, processing progress, evidence review, adaptive
assessment and multi-method ranking.

## Local preview

Use the supplied preview data without authentication or a backend:

```bash
cp .env.example .env.local
```

Set `VITE_PREVIEW_MODE=true`, then run:

```bash
npm ci
npm run dev
```

## Connected platform

Set `VITE_PREVIEW_MODE=false` and supply the Supabase project URL and public
anonymous key in `.env.local`. Set `VITE_API_BASE_URL` to the FastAPI origin,
or keep `/api` when both applications are behind the same reverse proxy.

The frontend uses Supabase only for identity and session management. SME data,
documents, evidence and assessments pass through FastAPI so authorization and
audit rules remain centralized. See `docs/supabase_setup.md` at the repository
root for the complete deployment procedure.

## Verification

Use Node 22 or newer:

```bash
npm ci
npm run check
```
