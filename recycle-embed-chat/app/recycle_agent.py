#!/usr/bin/env python3
"""
smart_recycle.py
Optimized CLI Recycling assistant using OpenAI embeddings + Qdrant

Features:
- Batch embeddings
- Dynamic collection vector size detection
- Chunked upserts
- Simple JSON embedding cache
- Robust HTTP requests with retries/backoff
- Clear IDs (slug + uuid)
"""

import os
import sys
import json
import time
import math
import uuid
import logging
from typing import List, Dict, Any, Iterable
from datetime import datetime, timezone
from slugify import slugify
import requests
from requests.adapters import HTTPAdapter, Retry
from openai import OpenAI

# ---------------------------
# Configuration (env)
# ---------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "recycle_docs")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
TOP_K = int(os.environ.get("TOP_K", "3"))
MIN_SCORE = float(os.environ.get("MIN_SCORE", "0.55"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "32"))
EMBED_CACHE_FILE = os.environ.get("EMBED_CACHE_FILE", "embeddings_cache.json")
UPsert_BATCH = int(os.environ.get("UPSERT_BATCH", "64"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "60"))

# ---------------------------
# Static recycling knowledge
# ---------------------------
RECYCLING_KNOWLEDGE = {
    "plastic": "Plastikflaschen, Verpackungen, Folien → Gelber Sack/Gelbe Tonne. Bitte reinigen.",
    "paper": "Zeitungen, Kartons, Bücher → Blaue Tonne. Sauber und trocken halten.",
    "glass": "Glasflaschen, Konservengläser → Glascontainer (nach Farben sortieren). Deckel entfernen.",
    "organic": "Obstreste, Gemüseabfälle, Kaffeesatz → Biotonne. Keine Plastiktüten verwenden.",
    "hazardous": "Batterien, Farben, Chemikalien → Sondermüll/Wertstoffhof. Nicht in Hausmüll!",
    "residual": "Windeln, Staubsaucgerbeutel, Asche → Restmülltonne (Schwarze Tonne).",
    "electronics": "Handys, Kabel, Kleingeräte → Elektroschrott/Wertstoffhof.",
    "textiles": "Kleidung, Schuhe, Stoffe → Altkleidercontainer (sauber und trocken)."
}

EXAMPLES_MAP = {
    "plastic": ["Plastikflasche", "Joghurtbecher", "Shampooflasche", "Plastiktüte", "Alufolie", "Kunststoffdeckel", "Chipstüte", "PET-Flasche", "Plastikbesteck", "Zahnpasta-Tube"],
    "paper": ["Zeitung", "Karton", "Bücher", "Briefpapier", "Papierverpackung", "Zeitschrift", "Kartonverpackung", "Schachtel", "Pappe", "Papierhandtuch"],
    "glass": ["Weinflasche", "Marmeladenglas", "Parfümflasche", "Saftflasche", "Glasdeckel", "Einmachglas", "Glasbehälter", "Fläschchen", "Konservenglas", "Sektflasche"],
    "organic": ["Bananenschale", "Kaffeesatz", "Eierschalen", "Obstreste", "Gemüsereste", "Teebeutel", "Kochabfälle", "Obstkerne", "Kaffeesatzbeutel", "Blätter"],
    "hazardous": ["Batterie", "Farbeimer", "Medikamente", "Chemikalien", "Spraydose", "Reinigungsmittel", "Lösemittel", "Elektronikbatterie", "Quecksilberthermometer", "Leuchtstoffröhre"],
    "residual": ["Windel", "Staubsaugerbeutel", "Zigarettenasche", "Asche", "Taschentuch", "Kaugummi", "Kerzenreste", "Staub", "Lappen", "Staubsaugerbeutel"],
    "electronics": ["Handy", "Ladekabel", "Taschenlampe", "Fernbedienung", "Kopfhörer", "Kabel", "Stecker", "Maus", "Laptop", "Elektronikgerät"],
    "textiles": ["T-Shirt", "Jeans", "Schuhe", "Pullover", "Jacke", "Socke", "Handtuch", "Stoffreste", "Kleid", "Hose"]
}

def build_embedding_text(example, category, instructions):
    """
    Erzeugt einen stark semantisch angereicherten Text für deutlich bessere Embeddings.
    """

    # manuelle Synonyme (du kannst sie später erweitern)
    SYNONYMS = {
        "Obstreste": ["Obstabfälle", "Fruchtreste", "Apfelschalen", "Bananenschalen", "Bio-Küchenabfälle"],
        "Gemüsereste": ["Gemüseabfälle", "Küchenabfälle", "Schalenreste"],
        "Kaffeesatz": ["Kaffeereste", "gemahlener Kaffee"],
        "Teebeutel": ["Teesäckchen", "Teereste", "Teefilter"],
        "Tee": ["loser Tee", "Teeblätter"],
        "Staubsaugerbeutel": ["Filterbeutel", "Staubbeutel"],
        "Lappen": ["Putztuch", "Reinigungslappen", "Stofftuch"],
        "Hose": ["Jeans", "Beinkleidung", "Textil"],
        "Papier": ["Schreibpapier", "Druckpapier"],
        "Eimer": ["Kübel", "Behälter"],
    }

    synonyms = SYNONYMS.get(example, [])
    synonyms_text = ", ".join(synonyms) if synonyms else "Keine bekannten Synonyme"

    # Zusatzbeispiele (stärken Semantik des Clusters)
    EXTRA_EXAMPLES = {
        "organic": ["Obstreste", "Gemüsereste", "Kaffeesatz", "Teebeutel", "Eierschalen"],
        "paper": ["Papier", "Zeitung", "Pappe", "Kartons"],
        "plastic": ["Plastikflasche", "Verpackungen"],
        "textile": ["Kleidung", "Stoffreste", "Hose", "Lappen"],
        "metal": ["Dosen", "Metallverpackungen", "Alufolie"],
        "general": ["Restmüll", "Staubsaugerbeutel", "Keramikreste"],
    }

    extra = ", ".join(EXTRA_EXAMPLES.get(category, []))

    # Erklärung, warum die Kategorie passt (Semantik-Booster)
    CATEGORY_REASONING = {
        "organic": "weil er biologisch abbaubar, kompostierbar und typischer Küchenabfall ist",
        "paper": "weil es sich um einen aus Zellstoff bestehenden Wertstoff handelt",
        "plastic": "weil es ein synthetisches Polymermaterial ist",
        "textile": "weil es aus Stoff oder Fasern besteht",
        "metal": "weil es ein metallischer Abfallstoff ist",
        "general": "weil er nicht recycelbar und nicht verwertbar ist",
    }

    reasoning = CATEGORY_REASONING.get(category, "weil es typisch für diese Kategorie ist")

    # Finaler optimierter Embedding-Text
    text = (
        f"{example}: {instructions}. "
        f"Dieser Gegenstand gehört eindeutig zur Kategorie '{category}', "
        f"{reasoning}. "
        f"Synonyme: {synonyms_text}. "
        f"Verwandte Beispiele: {extra}. "
        f"Entsorgungsregel: {instructions}. "
        f"Beschreibung: {example} ist ein typischer Vertreter der Kategorie '{category}'."
    )

    return text


# ---------------------------
# Logging & helpers
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("smart_recycle")

def _die(msg: str, code: int = 2):
    logger.error(msg)
    sys.exit(code)

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

# ---------------------------
# Requests session with retries
# ---------------------------
def make_session(retries: int = 3, backoff: float = 0.5) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "PUT", "POST", "DELETE", "HEAD", "OPTIONS"],
        backoff_factor=backoff
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

SESSION = make_session()

# ---------------------------
# Embedding cache (very simple JSON file)
# ---------------------------
def load_cache(path: str) -> Dict[str, List[float]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(path: str, data: Dict[str, List[float]]):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning("Konnte Embed-Cache nicht speichern: %s", e)

EMBED_CACHE = load_cache(EMBED_CACHE_FILE)

# ---------------------------
# OpenAI embedding helpers
# ---------------------------
def chunked(iterable: Iterable, n: int):
    it = list(iterable)
    for i in range(0, len(it), n):
        yield it[i:i+n]

def embed_texts(client: OpenAI, texts: List[str], batch_size: int = BATCH_SIZE) -> List[List[float]]:
    """
    Batch embeddings, use local cache for repeated texts.
    Returns list of vectors in same order as texts.
    """
    res_vectors: List[List[float]] = []
    to_request = []
    idx_map = {}  # map local index -> position in to_request

    # first check cache
    for i, t in enumerate(texts):
        key = t.strip()
        if key in EMBED_CACHE:
            res_vectors.append(EMBED_CACHE[key])
        else:
            res_vectors.append(None)
            idx_map[i] = len(to_request)
            to_request.append(key)

    if not to_request:
        return res_vectors  # all cached

    # request in batches
    for batch in chunked(to_request, batch_size):
        try:
            # OpenAI client (python SDK) embeddings create
            resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
            # resp.data is list of objects with .embedding
            for item, text in zip(resp.data, batch):
                vec = item.embedding
                EMBED_CACHE[text] = vec
        except Exception as e:
            _die(f"Embedding request failed: {e}")

    # Save cache async-ish (best effort)
    try:
        save_cache(EMBED_CACHE_FILE, EMBED_CACHE)
    except Exception:
        pass

    # fill results
    for i, t in enumerate(texts):
        key = t.strip()
        res_vectors[i] = EMBED_CACHE[key]

    return res_vectors

# ---------------------------
# Qdrant helpers
# ---------------------------
def ensure_collection(client: OpenAI, session: requests.Session):
    """
    Ensure the Qdrant collection exists and has vector size matching the embedding model.
    If collection does not exist, create it using dynamic dimension detection.
    """
    url = f"{QDRANT_URL}/collections/{COLLECTION}"
    try:
        r = session.get(url, timeout=8)
    except Exception as e:
        _die(f"Could not reach Qdrant at {QDRANT_URL}: {e}")

    if r.status_code == 200:
        logger.info("Collection '%s' exists.", COLLECTION)
        return

    # determine embedding dimension by creating a single embedding
    logger.info("Collection not found — determining embedding dimension from model '%s'...", EMBED_MODEL)
    try:
        sample_vec = embed_texts(client, ["test-embedding-vector-dimension"], batch_size=1)[0]
        dim = len(sample_vec)
    except Exception as e:
        _die(f"Could not get embedding to determine vector size: {e}")

    body = {"vectors": {"size": dim, "distance": "Cosine"}}
    logger.info("Creating collection '%s' with vector size %d", COLLECTION, dim)
    url_put = f"{QDRANT_URL}/collections/{COLLECTION}"
    r = session.put(url_put, json=body, timeout=30)
    if r.status_code >= 400:
        _die(f"Collection create failed: {r.status_code} {r.text}")
    logger.info("Collection created.")

def upsert_points(points: List[Dict[str, Any]], session: requests.Session):
    """
    Upsert points in chunks to Qdrant
    """
    if not points:
        return
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true"
    for chunk in chunked(points, UPsert_BATCH):
        payload = {"points": chunk}
        try:
            r = session.put(url, json=payload, timeout=REQUEST_TIMEOUT)
            if r.status_code >= 400:
                _die(f"Upsert failed: {r.status_code} {r.text}")
        except Exception as e:
            _die(f"Upsert request failed: {e}")

def search(vector: List[float], session: requests.Session, top_k: int = TOP_K) -> List[Dict[str, Any]]:
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points/search"
    body = {"vector": vector, "limit": top_k, "with_payload": True, "with_vector": False}
    try:
        r = session.post(url, json=body, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        _die(f"Search request failed: {e}")
    if r.status_code >= 400:
        _die(f"Search failed: {r.status_code} {r.text}")
    return r.json().get("result", [])

# ---------------------------
# Ingest function (batch embeddings + upsert)
# ---------------------------
def ingest_recycling_knowledge(client: OpenAI, session: requests.Session):
    """
    Optimierter Ingest-Prozess mit semantisch angereicherten Embeddings.
    """
    created_at = _now_iso()
    items = []

    for category, instructions in RECYCLING_KNOWLEDGE.items():
        examples = EXAMPLES_MAP.get(category, [f"Unbekanntes Beispiel {category}"])
        for example in examples:
            content = build_embedding_text(example, category, instructions)
            items.append({
                "category": category,
                "instructions": instructions,
                "example": example,
                "content": content,
                "title": f"{example} - {category}"
            })

    # Embeddings erzeugen
    texts = [it["content"] for it in items]
    vectors = embed_texts(client, texts, batch_size=BATCH_SIZE)

    points = []
    for i, it in enumerate(items):
        unique_id = str(uuid.uuid4())
        points.append({
            "id": unique_id,
            "vector": vectors[i],
            "payload": {
                "title": it["title"],
                "content": it["content"],
                "category": it["category"],
                "instructions": it["instructions"],
                "example": it["example"],
                "created_at": created_at,
                "source": "recycling_knowledge_base"
            }
        })

    upsert_points(points, session)
    logger.info("Ingest completed: %d items in '%s'", len(points), COLLECTION)



# ---------------------------
# Advice / Chat functions
# ---------------------------
def get_recycling_advice(hits: List[Dict[str, Any]], user_query: str) -> str:
    if not hits:
        return "❌ Ich weiß nicht, wie man diesen Gegenstand entsorgt. Bitte offizielle Quellen konsultieren."

    best = hits[0]

    # Qdrant kann "score" = similarity ODER distance liefern
    raw_score = best.get("score", 0.0)

    # Normalize score depending on type
    if isinstance(raw_score, dict):
        # newer Qdrant returns { "score": { "distance": X } }
        if "distance" in raw_score:
            distance = float(raw_score["distance"])
            score = 1 - distance  # convert to similarity
        elif "value" in raw_score:
            score = float(raw_score["value"])
        else:
            score = float(raw_score)  # fallback
    else:
        score = float(raw_score)

    # MIN_SCORE-Check
    if score < MIN_SCORE:
        return f"⚠️ Ich bin mir nicht ganz sicher (Score={score:.3f}). Bitte lokale Entsorgungsstelle prüfen."

    payload = best.get("payload", {})

    resp = []
    resp.append(f"🚮 **{user_query}**")
    resp.append(f"📦 **Kategorie:** {payload.get('category', 'Unbekannt').upper()}")
    resp.append(f"📝 **Anleitung:** {payload.get('instructions', '')}")
    resp.append(f"💡 **Beispiel:** {payload.get('example', '')}")
    resp.append(f"(Ähnlichkeits-Score: {score:.3f})")

    return "\n\n".join(resp)


def run_chat(client: OpenAI, session: requests.Session):
    print("🚮 Smart Recycle Bot - Ihr Assistent für Mülltrennung!")
    print("Beschreiben Sie einen Gegenstand und ich sage Ihnen, wie man ihn entsorgt.")
    print("':exit' zum Beenden\n")
    while True:
        try:
            user_input = input("🧐 Was möchten Sie entsorgen? ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Danke fürs Recycling!")
            break

        if user_input.lower() in {":exit", "exit", ":q", "quit"}:
            print("👋 Danke fürs Recycling!")
            break
        # Kurze Wörter abfangen
        if len(user_input) < 3:
            print("❌ Bitte genauer beschreiben (z.B. 'Teebeutel' statt 'Tee').")
            continue

        try:
            vec = embed_texts(client, [user_input], batch_size=1)[0]
            hits = search(vec, session)
            advice = get_recycling_advice(hits, user_input)
            print("\n" + advice)
            print("-" * 60)
        except Exception as e:
            logger.exception("Fehler beim Verarbeiten der Anfrage: %s", e)
            print(f"❌ Fehler: {e}")

# ---------------------------
# Main
# ---------------------------
def main():
    if not OPENAI_API_KEY:
        _die("Bitte OPENAI_API_KEY setzen (env OPENAI_API_KEY).")

    client = client = OpenAI()
    session = SESSION

    # ensure qdrant available & collection exists (create with correct dimension if missing)
    ensure_collection(client, session)

    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        logger.info("Ingesting recycling knowledge into Qdrant...")
        ingest_recycling_knowledge(client, session)
    else:
        run_chat(client, session)

if __name__ == "__main__":
    main()
