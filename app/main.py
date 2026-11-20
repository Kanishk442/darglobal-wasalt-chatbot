import os
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .rag import Index

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Comma-separated list; tried in order. "openrouter/free" auto-picks a currently available free model.
MODELS = [m.strip() for m in os.getenv("OPENROUTER_MODEL", "openrouter/free").split(",") if m.strip()]

SYSTEM = (
    "You are the assistant for DarGlobal (international luxury real estate developer) and Wasalt "
    "(Saudi AI-backed real estate platform). Answer ONLY from the provided context. "
    "If the context does not contain the answer, say you don't have that information and suggest contacting "
    "DarGlobal or Wasalt directly. Never invent prices, dates or figures. Be concise, and mention which "
    "company you are referring to. Reply in the user's language. "
    "Earlier assistant replies in this conversation were grounded in earlier context that may not be repeated "
    "below; treat them as valid and do not retract them. For follow-up questions, use the conversation so far "
    "together with the context. Keep a helpful tone: if the user asks about buying, explain what the context "
    "says (e.g. branded residences, apartments, penthouses) and point to the sales team for pricing. "
    "If asked for listings, inventory or areas, do not just say you have none: summarise concretely what the "
    "context does cover (named projects with their locations and unit types; Wasalt cities, districts and "
    "property categories such as villas, apartments, lands, for sale or for rent), say that live inventory and "
    "prices are on the platforms or with sales, then ask which city, property type or budget they care about."
)

app = FastAPI(title="DarGlobal & Wasalt Chatbot")
index = Index()
STATIC = Path(__file__).parent / "static"


class Msg(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str
    history: list[Msg] = []


@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(index.docs), "models": MODELS, "llm_configured": bool(API_KEY)}


@app.post("/api/chat")
async def chat(body: ChatIn):
    # Follow-ups like "so can I buy homes?" have few keywords, so also search with recent user turns
    # and the last assistant answer; the current message is repeated to weight it higher.
    recent_user = " ".join(m.content for m in body.history[-4:] if m.role == "user")
    last_bot = next((m.content for m in reversed(body.history) if m.role == "assistant"), "")
    # Generic "what listings / properties / areas do you have" questions share few keywords with the
    # city and category pages, so expand them to pull in the scraped Wasalt location pages.
    wants_listings = any(w in body.message.lower() for w in ("listing", "propert", "available", "inventory", "area", "location", "district", "city", "cities"))
    expansion = " villas apartments lands for sale for rent Riyadh Jeddah Makkah Madinah Dammam district" if wants_listings else ""
    hits = index.search(f"{body.message} {body.message} {recent_user} {last_bot[:300]}{expansion}", k=8 if wants_listings else 6)
    # Always include the core company overview passages so basic facts are never missing.
    have = {h["text"] for h in hits}
    hits += [p for p in index.pinned() if p["text"] not in have]
    sources = list({h["url"]: h for h in hits}.values())
    context = "\n\n".join(f"[{h['source']} | {h['url']}]\n{h['text']}" for h in hits) or "(no relevant context found)"
    src_out = [{"source": h["source"], "url": h["url"]} for h in sources]

    if not API_KEY:
        return {"answer": "LLM key not configured. Top matching passages:\n\n" + context[:1500], "sources": src_out}

    messages = [{"role": "system", "content": SYSTEM + "\n\nContext:\n" + context}]
    messages += [m.model_dump() for m in body.history[-6:]]
    messages.append({"role": "user", "content": body.message})
    headers = {"Authorization": f"Bearer {API_KEY}", "HTTP-Referer": os.getenv("APP_URL", "http://localhost"), "X-Title": "DarGlobal-Wasalt Chatbot"}

    last_err = ""
    async with httpx.AsyncClient(timeout=60) as client:
        for model in MODELS:
            try:
                r = await client.post(OPENROUTER_URL, headers=headers, json={"model": model, "messages": messages, "temperature": 0.2})
                if r.status_code == 200:
                    answer = r.json()["choices"][0]["message"]["content"]
                    if answer:
                        return {"answer": answer.strip(), "sources": src_out, "model": model}
                last_err = f"{model}: HTTP {r.status_code}"
            except Exception as e:  # network / parsing
                last_err = f"{model}: {e}"
    return {"answer": "The free model is busy or rate-limited right now. Please try again in a moment.\n\n" + f"({last_err})", "sources": src_out}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")