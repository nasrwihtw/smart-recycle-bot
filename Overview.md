# Smart Recycle Bot - KI-gestützte Mülltrennung

## 🚮 Projektübersicht

Der **Smart Recycle Bot** ist eine KI-gestützte Anwendung, die Nutzer:innen dabei unterstützt, Abfälle korrekt zu sortieren und zu recyceln. Die Lösung besteht aus zwei Microservices, die moderne AI-Technologie mit einer Vector-Datenbank kombinieren, um präzise Entsorgungsempfehlungen zu geben.

---

## 🏗️ Architektur

```
+------------------------+         +-----------------------+
|  Microservice A        |         |  Microservice B       |
|  recycle-embed-chat    |  HTTP   |  recycle-analytics-api|
|  (CLI RAG-Chat &       |<------->|  (REST API)           |
|   Ingestion Worker)    |         |  /analyze /stats      |
+-----------+------------+         +-----------+-----------+
            |                                  |
            | Qdrant REST (6333)               | Qdrant REST (6333)
            v                                  v
                   +----------------------+
                   |  Qdrant Vector DB    |
                   |  size=1536 Cosine    |
                   +----------------------+
```

---

## 📁 Projektstruktur

```
smart-recycle-bot/
├── qdrant/
│   └── docker-compose.yml
├── recycle-embed-chat/          # Microservice A (CLI)
│   ├── app/
│   │   ├── recycle_agent.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
├── recycle-analytics-api/       # Microservice B (REST API)  
│   ├── app/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
├── k8s/
│   ├── secret-openai.yaml
│   ├── configmap-recycle.yaml
│   ├── deployment-qdrant.yaml
│   ├── service-qdrant.yaml
│   ├── deployment-embedchat.yaml
│   ├── deployment-analyticsapi.yaml
│   └── service-analyticsapi.yaml
└── docker-compose.yml
```

---

## 🎯 Microservices Übersicht

### **Microservice A: recycle-embed-chat**
- **Typ**: CLI-basierte Python-Anwendung
- **Funktion**: Interaktiver Chatbot für Mülltrennungs-Fragen
- **Features**:
  - RAG (Retrieval-Augmented Generation) mit Qdrant Vector DB
  - Einspielen von Recycling-Wissen in die Datenbank
  - Echtzeit-Antworten basierend auf gespeichertem Wissen
  - Fallback-Logik bei unsicheren Erkennungen

### **Microservice B: recycle-analytics-api**  
- **Typ**: REST API mit FastAPI
- **Funktion**: Analytische Auswertungen und erweiterte Entsorgungsanalyse
- **Endpunkte**:
  - `POST /analyze` - Detaillierte Entsorgungsanalyse
  - `GET /stats` - Statistiken und Analytics
  - `POST /ingest` - Hinzufügen neuer Einträge
  - `GET /health` - Health Check

---

## 🔧 Technische Umsetzung

### 1. Qdrant Vector Database
```yaml
# qdrant/docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333", "6334:6334"]
    volumes:
      - qdrant_data:/qdrant/storage
```
Start:
```bash
cd qdrant
docker compose up -d
curl -s http://localhost:6333/ | jq
```

Erfolgsmeldung:
```bash
{
  "title": "qdrant - vector search engine",
  "version": "1.15.5",
  "commit": "48203e414e4e7f639a6d394fb6e4df695f808e51"
}
```

Collection anlegen (1536, Cosine):
```bash
curl -X PUT "http://localhost:6333/collections/recycle_docs"   -H "Content-Type: application/json"   -d '{"vectors":{"size":1536,"distance":"Cosine"}}'
```

Collection query (1536, Cosine):
```bash
curl http://localhost:6333/collections
```

Result
```bash

{"result":{"collections":[{"name":"recycle_docs"}]},"status":"ok","time":0.000048333}% 
```

### 2. Microservice A - recycle-embed-chat
**Kernfunktionen**:
- Embedding-Erzeugung mit OpenAI API
- Vektor-basierte Suche in Qdrant
- Interaktive Chat-Schnittstelle
- Wissensbasis-Management

**Beispiel-Usage**:
```bash
## Start with Dockerfile
## Mircoservice A: recycle-analytics
cd ./smart-recycle-bot/recycle-embed-chat/app 

docker build -t recycle-embed-chat:latest .

# to create a collection on qdrant
docker run --rm -it \                 
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e QDRANT_URL="http://host.docker.internal:6333" \
  recycle-embed-chat:latest ingest

## use instead of $OPENAI_API_KEY the open ai you have
docker run --rm -it \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e QDRANT_URL="http://host.docker.internal:6333" \
  recycle-embed-chat:latest

  🚮 Smart Recycle Bot - Ihr Assistent für Mülltrennung!
Beschreiben Sie einen Gegenstand und ich sage Ihnen, wie man ihn entsorgt.
':exit' zum Beenden

🧐 Was möchten Sie entsorgen? Zeitung

🚮 **Zeitung**

📦 **Kategorie:** PAPER
📝 **Anleitung:** Zeitungen, Kartons, Bücher → Blaue Tonne. Sauber und trocken halten.

💡 **Beispiel:** Zeitung
------------------------------------------------------------
🧐 Was möchten Sie entsorgen? Bananenschale

🚮 **Bananenschale**

📦 **Kategorie:** ORGANIC
📝 **Anleitung:** Obstresten, Gemüseabfälle, Kaffeesatz → Biotonne. Keine Plastiktüten verwenden.

💡 **Beispiel:** Bananenschale
------------------------------------------------------------
🧐 Was möchten Sie entsorgen? :exit
👋 Danke fürs Recycling!



## Mircoservice B: recycle-analytics
cd ../../recycle-analytics-api/app
docker build -t recycle-analytics-api:latest .
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e QDRANT_URL="http://host.docker.internal:6333" \
  recycle-analytics-api:latest

  
## use the instead of $OPENAI_API_KEY the open AI key you have
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e QDRANT_URL="http://host.docker.internal:6333" \
  recycle-analytics-api:latest

   docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e QDRANT_URL="http://host.docker.internal:6333" \
  recycle-analytics-api:latest

#Erfolgsmeldung:

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080

#API testen (in neuem Terminal)
# Health Check
curl -s http://localhost:8080/health | jq

#Erfolgsmeldung:
{
  "status": "healthy",
  "service": "recycle-analytics-api"
}

### Analyse eines Gegenstands
curl -s -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"item_description": "Plastikflasche"}' | jq

#Erwartete Antwort:
  {
  "item": "Plastikflasche",
  "category": "plastic",
  "confidence": 0.823456,
  "instructions": "Plastikflaschen, Verpackungen, Folien → Gelber Sack/Gelbe Tonne. Bitte reinigen.",
  "similar_items": ["Plastikflasche", "Joghurtbecher", "Shampooflasche"],
  "environmental_tip": "Recycling spart Erdöl und reduziert Meeresverschmutzung um 80%"
}

# Weitere Tests
curl -s -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"item_description": "Batterie"}' | jq

curl -s -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"item_description": "Glasflasche"}' | jq

  ## diese Commands ausführen nach der Erstellung docker compose.yaml to start the two Mircoservices

  cd ./smart-recycle-bot/

  export OPENAI_API_KEY="ihr-openai-key-hier"

  # Images bauen

docker compose build

# Services starten
docker compose up -d


docker compose exec recycle-chat python recycle_agent.py ingest


#Erfolgsmeldung:
📚 Spiele Recycling-Wissen in Qdrant ein...
Recycling-Wissen eingespielt: 24 Einträge in 'recycle_docs'

## then run
docker compose exec -it embedchat python recycle_agent.py

🧐 Was möchten Sie entsorgen? Plastikflasche

🚮 **Plastikflasche**

📦 **Kategorie:** PLASTIC
📝 **Anleitung:** Plastikflaschen, Verpackungen, Folien → Gelber Sack/Gelbe Tonne. Bitte reinigen.

💡 **Beispiel:** Plastikflasche
------------------------------------------------------------

# test the second Microservice 
curl -s http://localhost:8080/health

#Erfolgsanwort:
{"status":"healthy","service":"recycle-analytics-api"}%  

curl -s -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"item_description": "Batterie"}' | jq

## Erwartete Anwort
{
  "item": "Batterie",
  "predicted_category": "hazardous",
  "confidence_score": 0.568787,
  "disposal_instructions": "Batterien, Farben, Chemikalien → Sondermüll/Wertstoffhof. Nicht in Hausmüll!",
  "similar_items": [
    "",
    "",
    ""
  ],
  "environmental_impact": "Sichere Entsorgung schützt Grundwasser"
}


```

### 3. Microservice B - recycle-analytics-api  
**API-Endpunkte**:
```python
# Detaillierte Analyse
POST /analyze
{
  "item_description": "plastic bottle",
  "user_location": "berlin"
}

# Statistiken
GET /stats
{
  "total_queries": 150,
  "categories_breakdown": {"plastic": 45, "paper": 38},
  "recycling_rate": 85.3
}
```

---

## 🐳 Docker Deployment

### Lokale Entwicklung
```bash
# 1. Images bauen
docker build -t recycle-chat:latest ./recycle-embed-chat/app
docker build -t recycle-api:latest ./recycle-analytics-api/app

# 2. Services starten
export OPENAI_API_KEY="your-key-here"
docker compose up -d

# 3. Wissensbasis initialisieren
docker compose exec recycle-chat python recycle_agent.py ingest

# 4. Chat testen
docker compose exec -it recycle-chat python recycle_agent.py

# 5. API testen
curl http://localhost:8080/health
curl -s -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"item_description": "plastic bottle"}' | jq
```

---

## ☸️ Kubernetes Deployment

### Manifests anwenden
```bash
# Alle Komponenten deployen
kubectl apply -f k8s/

# Wissensbasis initialisieren
kubectl exec -it deployment/recycle-chat -- python recycle_agent.py ingest

# API Zugriff
kubectl port-forward service/recycle-api 8080:8080
```

### Kubernetes Komponenten
- **Secret**: `secret-openai.yaml` - OpenAI API Key
- **ConfigMap**: `configmap-recycle.yaml` - Konfiguration
- **Deployments**: Qdrant, Chat-Service, API-Service
- **Services**: Netzwerk-Zugriff

---

## 🎪 Features & Innovation

### 🤖 Intelligente Erkennung
- **Vektor-basierte Similarity Search** für robuste Erkennung
- **Kontextuelles Verständnis** durch Embeddings
- **Fallback-Mechanismen** bei Unsicherheiten

### 📊 Analytics & Monitoring
- **Echtzeit-Statistiken** zur Nutzung
- **Recycling-Rate Tracking**
- **Kategorie-basierte Analytics**

### 🔒 Sicherheit & Zuverlässigkeit
- **Container-isolierte Services**
- **Health Checks** und Monitoring
- **Error Handling** mit klaren Fehlermeldungen

---

## 🌱 Umweltwirkung

### Direkter Impact
- **Reduzierte Fehlwürfe** durch präzise Erkennung
- **Höhere Recycling-Quoten** durch bessere Trennung
- **Bildungseffekt** durch erklärende Antworten

### Kategorien & Beispiele
```python
RECYCLING_DATA = {
    "plastic": ["plastic bottle", "food packaging", "shampoo bottle"],
    "paper": ["newspaper", "cardboard", "magazine"],
    "glass": ["glass bottle", "jam jar", "wine bottle"],
    "organic": ["fruit peel", "vegetable scraps", "coffee grounds"],
    "hazardous": ["battery", "paint can", "chemicals"],
    "residual": ["diapers", "broken glass", "vacuum cleaner bags"]
}
```

---

## 🚀 Quick Start

### Voraussetzungen
- Docker & Docker Compose
- OpenAI API Key
- Kubernetes (optional)

### In 5 Minuten lauffähig
1. **Repository klonen**
2. **API Key setzen**: `export OPENAI_API_KEY="your-key"`
3. **Docker starten**: `docker compose up -d`
4. **Daten einspielen**: `docker compose exec recycle-chat python recycle_agent.py ingest`
5. **Testen**: Chat oder API nutzen

### Test-Beispiele
```
🧐 Was möchten Sie entsorgen? plastic bottle
🧴 **plastic bottle** gehört in: **PLASTIC**
📝 **Anleitung:** In den Gelben Sack/Gelbe Tonne. Bitte reinigen und trennen.
```

---

## 📈 Zukunftsvision

### Kurzfristige Erweiterungen
- **Bilderkennung** für visuelle Müll-Identifikation
- **Mehrsprachigkeit** für internationale Nutzung
- **Lokale Anpassungen** für regionsspezifische Regeln

### Langfristige Ziele
- **Integration in Smart City Infrastruktur**
- **Maschinenlernen** für kontinuierliche Verbesserung
- **IoT-Anbindung** für intelligente Mülltonnen

---

## 🎯 Bewertungsrelevante Features

✅ **Zwei Microservices** mit klarer Aufgabentrennung  
✅ **AI-Komponente** mit OpenAI Embeddings und RAG  
✅ **Docker Containerisierung** aller Services  
✅ **Kubernetes Deployment** mit multiplen Pods  
✅ **REST API** mit dokumentierten Endpunkten  
✅ **Vector Database** für semantische Suche  
✅ **Dummy-Daten** für sofortige Funktionsfähigkeit  
✅ **Umfassende Dokumentation** und Examples  

---

## 💡 Besonderheiten

- **"Weiß ich nicht"-Antworten** bei niedriger Confidence
- **Umwelt-Bildungskomponente** mit Impact-Erklärungen
- **Modulare Architektur** für einfache Erweiterbarkeit
- **Production-Ready** mit Health Checks und Monitoring

---

**♻️ Smart Recycle Bot - Making recycling smarter, one item at a time!**