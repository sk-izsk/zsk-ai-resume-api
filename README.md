# ZSK AI Resume API

FastAPI backend for the portfolio Ask AI feature.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`, then run:

For local development, use the Vite portfolio URL:

```env
PORTFOLIO_PROFILE_URL=http://127.0.0.1:4890/resume-ai-profile.json
PORTFOLIO_PROFILE_PATH=/Volumes/Mac Mini 1tb Ext/Projects/React/zsk-portfolio/public/resume-ai-profile.json
RATE_LIMIT_ENABLED=false
```

For Render production, use the Netlify URL:

```env
PORTFOLIO_PROFILE_URL=https://izsk.netlify.app/resume-ai-profile.json
PORTFOLIO_PROFILE_PATH=
```

```bash
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Self-check:

```bash
python -m unittest discover -s tests
```

Chat:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What are Zeeshan strongest React projects?"}'
```

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

or 

```bash
python -m uvicorn app.main:app --reload --port 8000 
```

Set these environment variables in Render:

```env
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
PRIMARY_LLM_PROVIDER=google
GOOGLE_API_KEY=
GOOGLE_MODEL=gemini-3.5-flash-lite
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
PORTFOLIO_PROFILE_URL=https://izsk.netlify.app/resume-ai-profile.json
PORTFOLIO_PROFILE_PATH=
ALLOWED_ORIGINS=https://izsk.netlify.app
RATE_LIMIT_MAX_REQUESTS=3
RATE_LIMIT_WINDOW_SECONDS=3600
RATE_LIMIT_MAX_REFUSALS=10
CACHE_TTL_SECONDS=604800
PROFILE_TTL_SECONDS=900
NETLIFY_PROXY_SECRET=
RATE_LIMIT_ENABLED=true
CACHE_VERSION=professional-first-v2
```

## Rate limiting and the visitor's IP

Each IP gets `RATE_LIMIT_MAX_REQUESTS` real answers and `RATE_LIMIT_MAX_REFUSALS` off-topic refusals per
`RATE_LIMIT_WINDOW_SECONDS`. Failed replies don't count.

The API never trusts `X-Forwarded-For`, which any client can set. It uses Cloudflare's `CF-Connecting-IP`
(Render sits behind Cloudflare), or, for requests through the site's Netlify proxy, Netlify's
`X-Nf-Client-Connection-Ip`. That header is only trusted when Netlify signed the request:

1. Pick a long random secret.
2. In Netlify, add it as the environment variable `ASK_AI_PROXY_SIGNATURE` (the proxy rule in the site's
   `netlify.toml` signs with it).
3. In Render, set `NETLIFY_PROXY_SECRET` to the same value.

Until `NETLIFY_PROXY_SECRET` is set, the Netlify header is accepted unverified and a warning is logged.

`GET /health` is cheap and doesn't touch Redis; `GET /health?deep=true` also checks Redis.

`GET /usage` returns the visitor's `remaining`, `reset_in_seconds` and `allowed` without using a request, so
the site can show the right count when the chat opens.
