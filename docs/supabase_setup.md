# Supabase deployment

GREENSMECAPT uses Supabase for authentication, PostgreSQL persistence and
private original-document storage. The React application never receives the
database password or service-role key and never reads application tables or
documents directly. It sends the signed Supabase access token to FastAPI,
which applies role and SME-level authorization.

## 1. Create the project and schema

1. Create a Supabase project and save its project URL, public anonymous key,
   service-role key and database password.
2. Configure the backend variables shown in the repository `.env.example`.
3. Start the API once. SQLModel creates the application tables in the selected
   PostgreSQL database.
4. In the Supabase SQL editor, run
   `supabase/migrations/202609200001_platform_security.sql`, then
   `supabase/migrations/202609270001_access_lifecycle.sql`.

The migration creates the private `source-documents` bucket, prevents direct
browser access to the application tables, and installs the controlled role
assignment function.

## 2. Configure authentication

In **Authentication → URL configuration**, add the frontend origin and its
password recovery URL, for example:

```text
http://localhost:5173
http://localhost:5173/settings
```

Create users in Supabase Authentication. Then assign application claims from
the SQL editor:

```sql
select public.set_greensmecapt_access(
    'USER_UUID',
    'reviewer',
    array[]::text[]
);

select public.set_greensmecapt_access(
    'SME_USER_UUID',
    'sme_user',
    array['sme_001']
);
```

Supported roles are `admin`, `reviewer`, `expert`, `investor` and
`sme_user`. Experts are isolated to expert-study work; investors can only
access explicitly published profile snapshots. SME users
must have at least one assigned SME identifier. Sign out and in again after a
claim change so Supabase issues a fresh token.

SME identifiers are immutable. Metadata edits, uploads, document deletions and
lifecycle transitions use the current application revision to prevent stale
writes. Approved or published data cannot be silently changed. Reopening a
published application withdraws it from investor discovery while retaining the
publication history. Hard deletion is limited to empty draft or withdrawn
workspaces; governed records should be archived instead.

After the first administrator is assigned, that administrator can invite
additional users and change their roles or SME assignments from **Profile and
access** in the application. These operations pass through the admin-only
FastAPI endpoints; the service-role key never reaches the browser. The SQL
function remains the secure bootstrap route for the first administrator.

## 3. Configure the backend

Copy the root `.env.example` values into the environment used to start FastAPI.
Set:

- `GREENSMECAPT_DATABASE_URL` to the Supabase PostgreSQL connection string;
- the three `GREENSMECAPT_AUTH_*` values to the project's Auth endpoints;
- `GREENSMECAPT_STORAGE_BACKEND=supabase`;
- `GREENSMECAPT_SUPABASE_URL` and the server-only service-role key;
- `GREENSMECAPT_FRONTEND_URL` for trusted invitation and recovery redirects;
- `GREENSMECAPT_CORS_ORIGINS` to the exact frontend origins.

Never put `GREENSMECAPT_SUPABASE_SERVICE_ROLE_KEY` in a `VITE_*` variable or
commit it to Git. Only the backend process may receive it.

## 4. Configure the frontend

From `frontend/`:

```bash
cp .env.example .env.local
```

Set the project URL and public anonymous key. Keep
`VITE_PREVIEW_MODE=false` for the real authenticated system. The default
`VITE_API_BASE_URL=/api` works behind a reverse proxy; for separate local
servers, use `http://127.0.0.1:8000`.

Then run:

```bash
npm ci
npm run check
npm run dev
```

The settings page supports password recovery and password changes. Document
uploads remain private and travel through the authorized API so integrity,
provenance and audit rules cannot be bypassed.
