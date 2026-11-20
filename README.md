# DarGlobal & Wasalt Chatbot

RAG chatbot over the public websites of DarGlobal and Wasalt.

- **Scraping**: `app/scraper.py` crawls both sites politely (robots.txt, 1s delay, same-domain only) into `data/scraped.json`. A curated `data/seed.json` is always loaded too, so the bot works even if a site blocks the crawler or is JS-rendered.
- **Retrieval**: dependency-free BM25 over ~900-character chunks (`app/rag.py`).
- **LLM**: OpenRouter free model (default `openrouter/free`, which auto-selects an available free model; override with `OPENROUTER_MODEL`, comma-separated fallbacks). Answers are grounded in retrieved context and cite source pages.
- **Stack**: FastAPI + a single-page chat UI. Docker image is `python:3.12-slim`.

## Run locally

```bash
cp .env.example .env            # add your OpenRouter key (free at openrouter.ai/keys)
docker build -t dg-chatbot .
docker run --rm -p 8000:8000 --env-file .env dg-chatbot
# open http://localhost:8000
```

Without Docker: `pip install -r requirements.txt && python -m app.scraper && uvicorn app.main:app --port 8000`

## Deploy (pick one)

### Option A: Render (easiest, free web service, gives a public URL)
1. Push this folder to a new GitHub repo.
2. Render dashboard > New > Blueprint (or Web Service) > select the repo. `render.yaml` is picked up automatically; runtime is Docker.
3. Set the env var `OPENROUTER_API_KEY`. Deploy.
4. Your URL: `https://darglobal-wasalt-chatbot.onrender.com`. Free instances sleep after inactivity, so open it once before sending the link (first load takes ~30s).

### Option B: Hugging Face Spaces (Docker, no sleep-wake delay for visitors)
1. Create a Space > SDK: Docker.
2. Push the files, and add this to the top of `README.md` of the Space repo:
   ```
   ---
   title: DarGlobal Wasalt Chatbot
   sdk: docker
   app_port: 8000
   ---
   ```
3. Settings > Variables and secrets > add secret `OPENROUTER_API_KEY`.
4. URL: `https://<user>-<space>.hf.space`

## Endpoints
- `GET /` chat UI
- `POST /api/chat` `{ "message": "...", "history": [...] }`
- `GET /health` status, chunk count, whether an LLM key is configured

## Notes and limitations
- Free OpenRouter models are rate limited and change over time; the app tries each model in `OPENROUTER_MODEL` and shows a friendly message if all fail.
- Only public pages are scraped; prices are not published by DarGlobal so the bot is instructed not to invent them.
- If scraping at build time is blocked, re-run `python -m app.scraper` from a machine that can reach the sites and rebuild.
