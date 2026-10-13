# Production deployment runbook

## Target architecture

- **Frontend:** Cloudflare Pages, built from `frontend/`.
- **API:** Google Cloud Run, built from the repository `Dockerfile`.
- **Identity, PostgreSQL and private documents:** Supabase.
- **Scanned-document recovery:** Google Document AI OCR in `eu`.
- **Schema-guided extraction:** Gemini on Vertex AI.

This preserves the current application interfaces. A frontend or API release
does not erase PostgreSQL data or Supabase Storage objects.

## Backend deployment

The Cloud Run service account needs these IAM roles on the Google project:

- Document AI API User (`roles/documentai.apiUser`)
- Vertex AI User (`roles/aiplatform.user`)

Store the Supabase database URL and service-role key in Secret Manager. Then
deploy the API from the repository root. Use one instance during a live demo
and instance-based CPU because document jobs continue after the enqueue
request returns:

```bash
gcloud run deploy greensmecapt-api \
  --source . \
  --region europe-west1 \
  --service-account greensmecapt-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min-instances 1 \
  --no-cpu-throttling \
  --memory 2Gi \
  --timeout 900 \
  --set-secrets GREENSMECAPT_DATABASE_URL=greensmecapt-database-url:latest,GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY=greensmecapt-supabase-service-role:latest \
  --set-env-vars GREENSMECAPT_ENV=production,GREENSMECAPT_STORAGE_BACKEND=supabase,GREENSMECAPT_STRUCTURED_OCR_PROVIDER=google_document_ai,GREENSMECAPT_GOOGLE_DOCUMENT_AI_PROJECT_ID=PROJECT_ID,GREENSMECAPT_GOOGLE_DOCUMENT_AI_LOCATION=eu,GREENSMECAPT_GOOGLE_DOCUMENT_AI_OCR_PROCESSOR_ID=PROCESSOR_ID,GREENSMECAPT_SEMANTIC_PROVIDER=vertex_gemini,GREENSMECAPT_SEMANTIC_ALLOW_REMOTE=true,GREENSMECAPT_SEMANTIC_REQUIRED=true,GREENSMECAPT_READINESS_DEMATEL_SCENARIO=config/dematel_scenario.development.json,GREENSMECAPT_AUTH_ISSUER=https://SUPABASE_REF.supabase.co/auth/v1,GREENSMECAPT_AUTH_AUDIENCE=authenticated,GREENSMECAPT_AUTH_JWKS_URL=https://SUPABASE_REF.supabase.co/auth/v1/.well-known/jwks.json,GREENSMECAPT_SUPABASE_URL=https://SUPABASE_REF.supabase.co,GREENSMECAPT_SUPABASE_STORAGE_BUCKET=source-documents,GREENSMECAPT_FRONTEND_URL=https://APP_DOMAIN,GREENSMECAPT_CORS_ORIGINS=https://APP_DOMAIN
```

`--allow-unauthenticated` exposes the HTTPS endpoint, but application data is
still protected by Supabase JWT authorization inside the API. After expert
calibration, replace the explicit development scenario variable with
`GREENSMECAPT_READINESS_DEMATEL_RESULT=config/dematel_result.approved.json`.

Set `--min-instances 0` after the live demonstration if lower idle cost is
more important than avoiding cold starts. Keep `--no-cpu-throttling` while the
current in-process document-job runner is used.

## Frontend deployment

Create a Cloudflare Pages project connected to the repository with:

- Root directory: `frontend`
- Build command: `npm ci && npm run build`
- Output directory: `dist`
- Node version: `22`

Set these public build variables:

```text
VITE_PREVIEW_MODE=false
VITE_API_BASE_URL=https://API_SERVICE_URL
VITE_SUPABASE_URL=https://SUPABASE_REF.supabase.co
VITE_SUPABASE_ANON_KEY=PUBLIC_SUPABASE_ANON_KEY
```

Add the final Pages/custom domain to Supabase Auth redirect URLs and to the API
variables `GREENSMECAPT_FRONTEND_URL` and `GREENSMECAPT_CORS_ORIGINS`, then
redeploy the API.

## Release acceptance

1. `GET https://API_SERVICE_URL/health` returns `{"status":"ready"}`.
2. Sign-up, sign-in and role routing work at the public frontend URL.
3. **Profile and access** confirms the configured providers.
4. Upload and process one native PDF and one image-only PDF.
5. Prepare, publish and compare two SME profiles.
6. Confirm Cloud Run and Google Cloud billing alerts before the live demo.

Normal updates are straightforward: push the frontend change for a Pages
rebuild; redeploy Cloud Run from the repository root for backend changes.
