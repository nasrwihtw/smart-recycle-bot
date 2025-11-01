import os, sys, json, re, time
from datetime import datetime, timezone
from slugify import slugify
import requests
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "recycle_docs")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
TOP_K = int(os.environ.get("TOP_K", "3"))
MIN_SCORE = float(os.environ.get("MIN_SCORE", "0.4"))  # HIER WAR DER FEHLER: osviron -> os.environ

# Recycling-Wissensbasis
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

def _die(msg, code=2):
    print(f"Fehler: {msg}", file=sys.stderr)
    sys.exit(code)

def _now():
    return datetime.now(timezone.utc).isoformat()

def ensure_collection():
    r = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=8)
    if r.status_code == 200:
        return
    body = {"vectors": {"size": 1536, "distance": "Cosine"}}
    r = requests.put(f"{QDRANT_URL}/collections/{COLLECTION}",
                     headers={"Content-Type":"application/json"},
                     data=json.dumps(body), timeout=30)
    if r.status_code >= 400:
        _die(f"Collection-Create fehlgeschlagen: {r.status_code} {r.text}")

def embed_texts(client: OpenAI, texts):
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def upsert_points(points):
    payload = {"points": points}
    r = requests.put(f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true",
                     headers={"Content-Type":"application/json"},
                     data=json.dumps(payload), timeout=120)
    if r.status_code >= 400:
        _die(f"Upsert fehlgeschlagen: {r.status_code} {r.text}")

def ingest_recycling_knowledge(client: OpenAI):
    """Befüllt Qdrant mit Recycling-Wissen"""
    points = []
    created_at = _now()
    
    for category, instructions in RECYCLING_KNOWLEDGE.items():
        # Erzeuge Beispiel-Items für jede Kategorie
        examples = {
            "plastic": ["Plastikflasche", "Joghurtbecher", "Shampooflasche"],
            "paper": ["Zeitung", "Karton", "Bücher"],
            "glass": ["Weinflasche", "Marmeladenglas", "Parfümflasche"],
            "organic": ["Bananenschale", "Kaffeesatz", "Eierschalen"],
            "hazardous": ["Batterie", "Farbeimer", "Medikamente"],
            "residual": ["Windel", "Staubsaugerbeutel", "Zigarettenasche"],
            "electronics": ["Handy", "Ladekabel", "Taschenlampe"],
            "textiles": ["T-Shirt", "Jeans", "Schuhe"]
        }
        
        for example in examples.get(category, [f"Beispiel {category}"]):
            content = f"{example}. {instructions}"
            
            points.append({
                "id": int(time.time() * 1000) + len(points),
                "vector": embed_texts(client, [content])[0],
                "payload": {
                    "title": f"{example} - {category}",
                    "content": content,
                    "category": category,
                    "instructions": instructions,
                    "example": example,
                    "created_at": created_at,
                    "source": "recycling_knowledge_base"
                }
            })
    
    upsert_points(points)
    print(f"Recycling-Wissen eingespielt: {len(points)} Einträge in '{COLLECTION}'")

def search(vector):
    body = {"vector": vector, "limit": TOP_K, "with_payload": True, "with_vector": False}
    r = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                      headers={"Content-Type":"application/json"},
                      data=json.dumps(body), timeout=60)
    if r.status_code >= 400:
        _die(f"Search fehlgeschlagen: {r.status_code} {r.text}")
    return r.json().get("result", [])

def get_recycling_advice(hits, user_query):
    if not hits:
        return "❌ Ich weiß nicht, wie man diesen Gegenstand entsorgt. Bitte offizielle Quellen konsultieren."
    
    if hits[0].get("score", 0.0) < MIN_SCORE:
        return "❌ Ich bin unsicher bei dieser Entsorgung. Bitte prüfen Sie bei Ihrer lokalen Entsorgungsstelle."
    
    best_hit = hits[0]
    payload = best_hit.get("payload", {})
    
    response = f"🚮 **{user_query}**\n\n"
    response += f"📦 **Kategorie:** {payload.get('category', 'Unbekannt').upper()}\n"
    response += f"📝 **Anleitung:** {payload.get('instructions', '')}\n\n"
    response += f"💡 **Beispiel:** {payload.get('example', '')}\n"
    
    return response

def run_chat():
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    print("🚮 Smart Recycle Bot - Ihr Assistent für Mülltrennung!")
    print("Beschreiben Sie einen Gegenstand und ich sage Ihnen, wie man ihn entsorgt.")
    print("':exit' zum Beenden\n")
    
    while True:
        try:
            user_input = input("🧐 Was möchten Sie entsorgen? ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Danke fürs Recycling!"); break
            
        if user_input.lower() in {":exit", "exit", ":q", "quit"}:
            print("👋 Danke fürs Recycling!"); break
            
        try:
            vec = embed_texts(client, [user_input])[0]
            hits = search(vec)
            advice = get_recycling_advice(hits, user_input)
            print(f"\n{advice}")
            print("-" * 60)
        except Exception as e:
            print(f"❌ Fehler: {e}")

def main():
    if not OPENAI_API_KEY:
        _die("Bitte OPENAI_API_KEY setzen.")
        
    ensure_collection()
    
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        print("📚 Spiele Recycling-Wissen in Qdrant ein...")
        ingest_recycling_knowledge(OpenAI(api_key=OPENAI_API_KEY))
    else:
        run_chat()

if __name__ == "__main__":
    main()