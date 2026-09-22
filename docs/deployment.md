# Deployment

## Presentation preview

The quickest reproducible demo uses the supplied containers and preview data:

```bash
docker compose up --build
```

Open `http://localhost:4173`. This mode demonstrates the interface and sample
workflow without pretending that preview records are persisted production
data.

## Connected deployment

Deploy the backend container and frontend container as separate services.
Give the backend the server-only values from `.env.example`. Build the frontend
with the public Supabase URL, anonymous key and the public HTTPS API URL.

The backend container includes Tesseract for CPU OCR. PaddleOCR remains an
optional heavier runtime because its full document-structure models need more
memory than small hosting plans normally provide. A larger worker image can
install `.[document-ai]` without changing the application interfaces.

Required backend secrets include the Supabase database URL, service-role key
and any hosted LLM key. Never provide those as frontend build arguments.

Set `GREENSMECAPT_ENV=production` in the deployed API. Production startup then
refuses SQLite/local-storage fallbacks, placeholder secrets, non-HTTPS browser
origins and configured remote AI providers whose key is unavailable.

After deployment:

1. run the Supabase migration in `supabase/migrations`;
2. add the frontend URL and password-recovery URL in Supabase Auth;
3. create an admin account and assign its application role;
4. open **Profile and access** to confirm runtime capabilities;
5. use **Test language-model connection** before processing a real document;
6. upload one digital PDF and one scanned image/PDF as an acceptance test.

Application changes are redeployed by rebuilding the affected container. Data
and documents remain in Supabase, so frontend or backend releases do not erase
them.
