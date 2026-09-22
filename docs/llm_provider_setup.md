# LLM provider setup

GREENSMECAPT supports either a hosted or local OpenAI-compatible chat
completion endpoint. Provider keys belong only in the backend environment;
they must never use the `VITE_` prefix or be placed in frontend files.

## Hosted provider

Copy the language-model section from `.env.example` into the backend runtime
environment. Set the provider endpoint, approved model name and key. Remote
document transmission is refused unless `GREENSMECAPT_SEMANTIC_ALLOW_REMOTE`
is explicitly `true`.

The visual provider is configured separately because an installation may
permit text transmission while prohibiting images, or may use a different
multimodal model.

## Local provider

Point the endpoint at a loopback OpenAI-compatible server such as Ollama or
vLLM. Local endpoints do not require remote approval. If the server does not
require a key, omit `GREENSMECAPT_SEMANTIC_API_KEY_ENV` entirely.

## Processing behavior

The application sends bounded source segments, the allowed metric catalogue,
and policy-governed qualitative questions. Output must satisfy a strict JSON
schema. The backend then independently verifies exact quotations, source
segments, configured identifiers, units and metric bounds.

LLM results are stored as unvalidated evidence. They cannot become accepted
assessment input until an authorized reviewer accepts them. Provider failure
does not erase deterministic OCR/NLP results unless
`GREENSMECAPT_SEMANTIC_REQUIRED=true` is deliberately enabled.

Never commit a real API key. Configure it as a deployment secret.
