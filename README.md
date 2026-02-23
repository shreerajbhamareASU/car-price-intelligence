# Car Price Intelligence

> **Principled AI** · Multi-Agent Decision System · Used-Car Market Intelligence

A production-grade, microservice-style car price intelligence platform. Predicts fair market value, generates 30/90-day price forecasts, and issues deterministic **BUY NOW / WAIT / MONITOR** recommendations — powered by a 7-agent orchestration pipeline with Redis caching, Pub/Sub event dispatch, Circuit Breaker protection, and a full React frontend.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            USER QUERY                                       │
│                    make · model · year · mileage                            │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ HTTPS / REST
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              API GATEWAY  ──  RATE LIMITER                                  │
│          Token Bucket · 60 req/min per IP · HTTP 429 on breach              │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────┐   ┌─────────────────────────┐
│           ORCHESTRATOR AGENT                 │──▶│   Circuit Breaker  ⚡   │
│   State machine · deterministic Python router│   │  CLOSED → OPEN →        │
│   Coordinates all agent phases               │   │  HALF-OPEN on LLM fail  │
└──────────────────────────────┬───────────────┘   └─────────────────────────┘
                               │ dispatch
                               ▼
┌──────────────────────────────────────────────┐   ┌─────────────────────────┐
│           EVENT BUS  (Pub/Sub)               │──▶│   Redis Cache  R        │
│  Topics: analysis_requested · agent_result   │   │  TTL 30 min             │
│          pipeline_complete                   │   │  Key: make+model+yr+st  │
└──────────────────────────────┬───────────────┘   └─────────────────────────┘
                               │
          ─────────────────────────────────────────
           PHASE 1 · SEQUENTIAL
          ─────────────────────────────────────────
                               │
                               ▼
┌──────────────────────────────────────────────┐   ┌─────────────────────────┐
│  DataAgent                                   │──▶│  MongoDB Atlas  🍃      │
│  · Checks Redis cache first (HIT = fast-path)│   │  carmarket DB           │
│  · Fetches listings + price_snapshots        │◀──│  328k listings          │
│  · Writes enriched context back to Redis     │   │  61k price snapshots    │
└──────────────────────────────┬───────────────┘   └─────────────────────────┘
                               │
          ─────────────────────────────────────────
           PHASE 2 · PARALLEL  (×3 simultaneously)
          ─────────────────────────────────────────
               ┌───────────────┼──────────────────┐
               ▼               ▼                  ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  TrendAgent     │  │  ForecastAgent   │  │  RiskAgent       │
│  Prophet model  │  │  XGBoost +       │  │  Volatility idx  │
│  30/90-day      │  │  GPT-4o-mini     │  │  Uncertainty     │
│  forecast       │  │  LLM blend       │  │  range + score   │
│  Yearly         │  │  40/60 · 30/70   │  │  0–100 risk      │
│  seasonality    │  │  weight blend    │  │  Low/Med/High    │
└────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                    │ Circuit Breaker       │
         │                    ▼                       │
         │           ┌────────────────┐               │
         │           │ OpenAI         │               │
         │           │ GPT-4o-mini    │               │
         │           └────────────────┘               │
         │                    │                       │
          ─────────────────────────────────────────────
           PHASE 3 · SEQUENTIAL  (awaits Phase 2)
          ─────────────────────────────────────────────
                    └──────────┬────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DecisionAgent  ·  PHASE 3  ·  NO LLM  ·  Pure Python                     │
│  Applies 3 deterministic ordered rules → BUY NOW / WAIT / MONITOR         │
│  Rule 1: price change ≤ −3% AND confidence ≥ 75%  →  WAIT                 │
│  Rule 2: price change ≥ +2% AND volatility = Low  →  BUY NOW              │
│  Rule 3: price ≤ −10% vs median AND confidence ≥ 75%  →  BUY NOW          │
│  Default: MONITOR                                                           │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
          ─────────────────────────────────────────
           PHASE 4 · PARALLEL  (×2 simultaneously)
          ─────────────────────────────────────────
                    ┌──────────┴────────────────────┐
                    ▼                               ▼
     ┌──────────────────────────┐   ┌───────────────────────────┐
     │  ExplanationAgent        │   │  EthicsAgent              │
     │  GPT-4o-mini             │   │  Pure Python              │
     │  3-sentence AI reasoning │   │  Per-make bias audit      │
     │  Circuit Breaker-wrapped │   │  Transparency note        │
     └──────────────┬───────────┘   │  Fairness disclaimer      │
                    │               └──────────────┬────────────┘
                    ▼                              │
           ┌────────────────┐                     │
           │ OpenAI         │                     │
           │ GPT-4o-mini    │                     │
           └────────────────┘                     │
                    │                              │
                    └──────────────┬───────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       STRUCTURED INTEL REPORT                               │
│   Signal: BUY NOW / WAIT / MONITOR  ·  Fair Value  ·  30/90-day Forecast   │
│   Risk Score  ·  Volatility  ·  SHAP Feature Importance                    │
│   3-sentence Explanation  ·  Ethics & Transparency Note                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Reference

| Agent | Phase | LLM | Responsibility |
|---|---|---|---|
| **OrchestratorAgent** | Router | No | State machine that sequences all phases, dispatches via Pub/Sub, aggregates results |
| **DataAgent** | 1 · Sequential | No | Checks Redis cache → fetches listings + price_snapshots from MongoDB → enriches context |
| **TrendAnalysisAgent** | 2 · Parallel | No | Facebook Prophet 30-day + 90-day forecasts, yearly seasonality, momentum score |
| **ForecastAgent** | 2 · Parallel | Yes | XGBoost regressor inference + GPT-4o-mini blend (40/60 or 30/70 weights) |
| **RiskAssessmentAgent** | 2 · Parallel | No | Volatility index (Low/Moderate/High), sigma-based uncertainty range, 0–100 risk score |
| **DecisionAgent** | 3 · Sequential | No | Three deterministic Python rules → BUY NOW / WAIT / MONITOR — never calls LLM |
| **ExplanationAgent** | 4 · Parallel | Yes | GPT-4o-mini generates a 3-sentence plain-English justification of the recommendation |
| **EthicsAgent** | 4 · Parallel | No | Per-make bias statement, data-freshness disclaimer, principled AI transparency note |

---

## Infrastructure Components

| Component | Role | Detail |
|---|---|---|
| **API Gateway** | Single entry point | HTTPS/REST, validates all inbound requests |
| **Rate Limiter** | Abuse protection | Token bucket · 60 req/min per IP · HTTP 429 on breach |
| **Circuit Breaker** | LLM fault isolation | CLOSED → OPEN → HALF-OPEN state machine wrapping all GPT-4o-mini calls |
| **Event Bus (Pub/Sub)** | Agent dispatch | 3 topics: `analysis_requested`, `agent_result`, `pipeline_complete` |
| **Redis Cache** | Hot-path caching | TTL 30 min · key = `make:model:year:state` hash · HIT skips DataAgent re-fetch |
| **MongoDB Atlas** | Primary data store | `carmarket` DB · `listings` collection (328k docs) · `price_snapshots` (61k docs) · 175 MB |
| **OpenAI GPT-4o-mini** | External LLM | Used only in ForecastAgent + ExplanationAgent — never for routing or decisions |

---

## Decision Rules

DecisionAgent applies three ordered deterministic rules in pure Python — zero LLM, zero randomness. Every recommendation traces to exact numerical thresholds.

| Rule | Condition | Signal |
|---|---|---|
| 1 | `price_change ≤ −3%` AND `confidence ≥ 75` | **WAIT** — price declining with high confidence |
| 2 | `price_change ≥ +2%` AND `volatility = Low` | **BUY NOW** — rising prices, stable market |
| 3 | `listing_price ≤ −10% vs median` AND `confidence ≥ 75` | **BUY NOW** — strong below-market deal |
| * | All other scenarios | **MONITOR** — no strong signal |

---

## ML Model

| Property | Value |
|---|---|
| Algorithm | XGBoost Regressor |
| Target | `log1p(price)` → `expm1` at inference |
| Training data | ~262k listings (80% chronological split) |
| Test data | ~66k listings (most recent 20% by date) |
| Split method | Chronological — zero data leakage |
| Features | 19 total: `car_age`, `log_odometer`, `make`, `model`, `condition`, `fuel`, `type`, `state`, `cylinders`, `drive` … |

### Top SHAP Feature Importances

| Rank | Feature | Direction | Importance |
|---|---|---|---|
| 1 | `log_odometer` | ↓ decreases price | 0.381 |
| 2 | `car_age` | ↓ decreases price | 0.294 |
| 3 | `model` | ↑ increases price | 0.120 |
| 4 | `make` | ↑ increases price | 0.099 |
| 5 | `condition` | ↑ increases price | 0.073 |
| 6 | `fuel` | ↑ increases price | 0.052 |
| 7 | `type` | ↑ increases price | 0.042 |
| 8 | `state` | ↑ increases price | 0.031 |

---

## Data Stack

| Source | Detail | Tag |
|---|---|---|
| Craigslist Dataset | Kaggle · ~426k listings · 26 columns | Primary |
| Cleaning Pipeline | Colab T4 · 5-step clean → 328k rows | Processed |
| MongoDB Atlas | `carmarket` DB · listings + price_snapshots · 175 MB | Storage |
| OpenAI GPT-4o-mini | ExplanationAgent + ForecastAgent LLM blend | LLM |
| Facebook Prophet | 30/90-day price forecasting · yearly seasonality | Forecast |
| Multi-Agent Orchestrator | 7 modular Python agents · deterministic pipeline | Architecture |
| EthicsAgent | Transparency notes · bias audit · principled AI layer | Ethics |
| Dataset snapshot | Jan 2024 · static for demo · update on demand | Freshness |

---

## Project Structure

```
car-price-intelligence/
├── backend/
│   ├── main.py                      # FastAPI app — all API routes
│   ├── agent.py                     # Legacy single-agent (superseded)
│   ├── car_catalog.py               # Static make/model catalog (20 makes)
│   ├── agents/
│   │   ├── orchestrator.py          # OrchestratorAgent — state machine router
│   │   ├── data_agent.py            # DataAgent — MongoDB + Redis fetch
│   │   ├── trend_agent.py           # TrendAnalysisAgent — Prophet forecasts
│   │   ├── forecast_agent.py        # ForecastAgent — XGBoost + LLM blend
│   │   ├── risk_agent.py            # RiskAssessmentAgent — volatility + uncertainty
│   │   ├── decision_agent.py        # DecisionAgent — deterministic 3-rule engine
│   │   ├── explanation_agent.py     # ExplanationAgent — GPT-4o-mini reasoning
│   │   └── ethics_agent.py          # EthicsAgent — bias audit + transparency
│   └── utils/
│       ├── smoothing.py             # Moving average + EMA helpers
│       ├── scenario_adjustments.py  # 4 macro scenario multipliers
│       └── validation.py            # Input validation at API boundary
│
├── frontend/
│   └── src/
│       ├── App.jsx                  # Router + AppContext
│       ├── api.js                   # Axios wrappers
│       ├── components/
│       │   └── MicroserviceFlowDiagram.jsx  # Animated architecture diagram
│       └── pages/
│           ├── AnalyzePage.jsx      # Car form → agent pipeline → intel report
│           ├── MarketTrendsPage.jsx # Market trends, forecasts, segment heatmap
│           ├── TechPage.jsx         # Architecture diagram + model card + SHAP
│           ├── PrincipledAIPage.jsx # HITL flow, fairness audit, 4 pillars
│           ├── DecisionReportPage.jsx # Downloadable report + RadarChart
│           └── EconomicImpactPage.jsx # Scale calculator + segment explorer
│
├── models/
│   ├── car_price_model.pkl          # Trained XGBoost regressor
│   ├── feature_meta.pkl             # Category codes + feature names + geo medians
│   └── shap_data.pkl                # TreeExplainer + 500-row SHAP sample
│
├── scripts/
│   ├── mongo_ingest.py              # Ingest cleaned_cars.csv → MongoDB Atlas
│   └── model_utils.py               # predict_price() + explain_prediction()
│
├── Cleaning/
│   └── craigslist_cleaning.ipynb    # Colab T4 — 5-step data cleaning pipeline
│
├── notebooks/
│   └── car_price_model.ipynb        # Colab T4 — feature eng + XGBoost + SHAP
│
├── docs/
│   └── mongo_setup.md               # Atlas + .env setup guide
│
└── .env                             # Local secrets — never committed
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/cars` | All makes/models from MongoDB + static catalog fallback |
| `POST` | `/api/predict` | Full 7-agent pipeline → Intel Report JSON |
| `GET` | `/api/market-overview` | Market stats, best buys, segment trends |
| `GET` | `/api/shap-importance` | Global SHAP feature importances |

### `POST /api/predict` — Request

```json
{
  "make": "toyota",
  "model": "camry",
  "year": 2019,
  "odometer": 45000,
  "condition": "good",
  "fuel": "gas",
  "type": "sedan",
  "state": "ca"
}
```

### `POST /api/predict` — Response

```json
{
  "signal": "BUY NOW",
  "fair_value": 18400,
  "confidence": 81,
  "forecast_30d": 18850,
  "forecast_90d": 19200,
  "price_change_pct": 2.4,
  "risk_score": 28,
  "volatility": "Low",
  "uncertainty_range": [17200, 19600],
  "explanation": "This 2019 Camry is priced 9% below the California median for similar mileage...",
  "ethics_note": "Toyota listings show consistent pricing patterns across regions...",
  "agent_log": [ ... ]
}
```

---

## Quick Start

```bash
git clone <repo-url>
cd car-price-intelligence

# Backend
pip install fastapi uvicorn motor pymongo python-dotenv \
            openai prophet xgboost shap joblib \
            scikit-learn pandas numpy
uvicorn backend.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev   # → http://localhost:5173
```

`.env` (project root):

```
MONGO_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/carmarket
OPENAI_API_KEY=sk-...
```

---

## Principled AI Design

- **LLM used surgically** — GPT-4o-mini is called only in ForecastAgent (blend) and ExplanationAgent (language). It never controls routing, decisions, or tool selection.
- **Deterministic decisions** — DecisionAgent applies three auditable Python rules. Every recommendation traces to exact numerical thresholds with no stochastic element.
- **Bias audit on every response** — EthicsAgent emits a per-make bias statement and data-freshness disclaimer on every single prediction.
- **Circuit Breaker** — All LLM calls are wrapped in a Circuit Breaker. On repeated failures the system degrades gracefully: XGBoost-only forecast, rule-only decision, templated explanation.
- **Transparent SHAP** — Global and local SHAP values are surfaced in the UI so users understand exactly what drives each price estimate.
- **Rate limiting** — API Gateway enforces 60 req/min per IP to prevent abuse and ensure fair access.

---

*Branch: `user/Shreeraj` · Author: shreerajbhamareASU · ASU Hackathon 2026*
