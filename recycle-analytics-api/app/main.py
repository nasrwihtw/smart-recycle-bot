from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import requests
import os
import json
from openai import OpenAI

# Konfiguration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "recycle_docs")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")

app = FastAPI(title="Recycle Analytics API", version="1.0")

class AnalyzeRequest(BaseModel):
    item_description: str
    user_location: Optional[str] = "general"

class AnalyticsResponse(BaseModel):
    item: str
    predicted_category: str
    confidence_score: float
    disposal_instructions: str
    similar_items: List[str]
    environmental_impact: str

class StatsResponse(BaseModel):
    total_queries: int
    categories_breakdown: Dict[str, int]
    most_common_items: List[str]
    recycling_rate: float

# Analytics-Dummy-Daten (in Produktion würde das aus DB kommen)
analytics_data = {
    "total_queries": 0,
    "categories": {},
    "common_items": []
}

def embed_text(client: OpenAI, text: str):
    """Erzeugt Embedding für einen Text"""
    resp = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding

def qdrant_search(vector, limit=3):
    """Sucht in Qdrant nach ähnlichen Vektoren"""
    body = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False
    }
    
    response = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
        headers={"Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30
    )
    
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Qdrant search failed")
        
    return response.json().get("result", [])

def get_environmental_impact(category: str) -> str:
    """Gibt Umweltauswirkung basierend auf Kategorie zurück"""
    impacts = {
        "plastic": "Recycling spart Erdöl und reduziert Meeresverschmutzung",
        "paper": "Recycling schützt Wälder und spart Wasser",
        "glass": "Glasrecycling spart Energie und ist unendlich möglich", 
        "organic": "Kompostierung erzeugt nährstoffreiche Erde",
        "hazardous": "Sichere Entsorgung schützt Grundwasser",
        "residual": "Verbrennung mit Energiegewinnung möglich"
    }
    return impacts.get(category, "Positive Umweltwirkung durch korrekte Entsorgung")

@app.get("/")
async def root():
    return {"message": "♻️ Smart Recycle Bot Analytics API"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "recycle-analytics-api"}

@app.post("/analyze", response_model=AnalyticsResponse)
async def analyze_item(request: AnalyzeRequest):
    """Analysiert einen Gegenstand und gibt detaillierte Entsorgungsempfehlung"""
    
    # Analytics tracking
    analytics_data["total_queries"] += 1
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        # Embedding für den Gegenstand
        vector = embed_text(client, request.item_description)
        
        # Suche in Qdrant
        hits = qdrant_search(vector)
        
        if not hits:
            raise HTTPException(status_code=404, detail="Keine Entsorgungsinformationen gefunden")
        
        best_hit = hits[0]
        payload = best_hit.get("payload", {})
        
        # Sammle ähnliche Gegenstände
        similar_items = [hit.get("payload", {}).get("item", "") for hit in hits[:3]]
        
        # Aktualisiere Analytics
        category = payload.get("category", "unknown")
        if category in analytics_data["categories"]:
            analytics_data["categories"][category] += 1
        else:
            analytics_data["categories"][category] = 1
        
        return AnalyticsResponse(
            item=request.item_description,
            predicted_category=category,
            confidence_score=best_hit.get("score", 0.0),
            disposal_instructions=payload.get("instructions", "Keine spezifischen Anleitungen verfügbar"),
            similar_items=similar_items,
            environmental_impact=get_environmental_impact(category)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyse fehlgeschlagen: {str(e)}")

@app.get("/stats", response_model=StatsResponse)
async def get_statistics():
    """Gibt Analytics-Statistiken zurück"""
    total = analytics_data["total_queries"]
    categories = analytics_data["categories"]
    
    # Berechne Recycling-Rate (alles außer residual)
    recycled_categories = sum(count for cat, count in categories.items() if cat != "residual")
    recycling_rate = (recycled_categories / total * 100) if total > 0 else 0
    
    # Meistgesuchte Items (vereinfacht)
    common_items = list(categories.keys())[:5]
    
    return StatsResponse(
        total_queries=total,
        categories_breakdown=categories,
        most_common_items=common_items,
        recycling_rate=round(recycling_rate, 1)
    )

@app.post("/ingest")
async def ingest_custom_item(item: dict):
    """Fügt benutzerdefinierte Items zur Wissensbasis hinzu"""
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        content = f"{item['item']}. {item['instructions']} Kategorie: {item['category']}"
        vector = embed_text(client, content)
        
        point = {
            "id": int(time.time() * 1000),
            "vector": vector,
            "payload": {
                "item": item["item"],
                "category": item["category"],
                "instructions": item["instructions"],
                "content": content,
                "source": "user_contribution"
            }
        }
        
        response = requests.put(
            f"{QDRANT_URL}/collections/{COLLECTION}/points",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"points": [point]}),
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Ingest failed")
            
        return {"status": "success", "message": "Item added to knowledge base"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)