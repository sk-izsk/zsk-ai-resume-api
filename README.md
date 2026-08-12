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

Set these environment variables in Render:

```env
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
PORTFOLIO_PROFILE_URL=https://izsk.netlify.app/resume-ai-profile.json
PORTFOLIO_PROFILE_PATH=
ALLOWED_ORIGINS=https://izsk.netlify.app
RATE_LIMIT_MAX_REQUESTS=3
RATE_LIMIT_WINDOW_SECONDS=3600
CACHE_TTL_SECONDS=604800
RATE_LIMIT_ENABLED=true
CACHE_VERSION=professional-first-v2
```
