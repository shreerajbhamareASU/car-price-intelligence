"""
agent.py — Car Market Analyst Agent
Uses OpenAI GPT-4o-mini with tool-calling to analyse a car query and return
a structured BUY / WAIT / NEUTRAL recommendation with a plain-English explanation.

Tools (called by the LLM in order):
  1. get_price_history      → MongoDB price_snapshots time series
  2. run_forecast           → Prophet 30 / 90-day price forecast
  3. run_price_prediction   → XGBoost inference + top-3 SHAP factors
  4. get_market_context     → Inventory count, trend, regional range
  5. synthesize_recommendation → Rule-based BUY/WAIT/NEUTRAL (not an LLM call)

Environment variables required (.env):
  OPENAI_API_KEY
  MONGO_URI
"""

from __future__ import annotations

import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")          # suppress XGBoost GPU/CPU device warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

# ── Project imports ───────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.model_utils import predict_price, explain_prediction

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv(_ROOT / ".env")

_oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
_db  = MongoClient(os.environ["MONGO_URI"])["carmarket"]

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are a car market analyst. When given a car query, call the available "
    "tools in order, then write a 3-sentence plain English explanation of your "
    "recommendation citing specific numbers from tool outputs. "
    "Be direct. Do not hedge excessively."
)


# ══════════════════════════════════════════════════════════════════════════════
# Tool implementations
# ══════════════════════════════════════════════════════════════════════════════

def get_price_history(make: str, model: str, year: int) -> list[dict]:
    """Query MongoDB price_snapshots for (make, model, year) time series."""
    cursor = _db["price_snapshots"].find(
        {"make": make.lower(), "model": model.lower(), "year": year},
        {"_id": 0, "year_month": 1, "avg_price": 1, "median_price": 1, "listing_count": 1},
    ).sort("year_month", 1)

    history = [
        {
            "date":          doc["year_month"],
            "avg_price":     round(doc.get("avg_price", 0), 2),
            "median_price":  round(doc.get("median_price", 0), 2),
            "listing_count": doc.get("listing_count", 0),
        }
        for doc in cursor
    ]
    return history if history else [{"error": f"No price history for {year} {make} {model}"}]


def run_forecast(make: str, model: str, year: int) -> dict:
    """
    Fetch price history from MongoDB then run Facebook Prophet.
    Accepts make/model/year directly so the LLM doesn't need to pipe
    raw data between tool calls.
    """
    try:
        from prophet import Prophet  # lazy import — heavy dep
    except ImportError:
        return {"error": "prophet not installed. Run: pip install prophet"}

    price_history = get_price_history(make, model, year)
    if not price_history or "error" in price_history[0]:
        return {"error": f"No price history for {year} {make} {model}"}
    if len(price_history) < 3:
        return {"error": f"Only {len(price_history)} months of data — need >= 3 for forecast"}

    df = pd.DataFrame(price_history)
    df["ds"] = pd.to_datetime(df["date"], format="%Y-%m", errors="coerce")
    df["y"]  = pd.to_numeric(df["avg_price"], errors="coerce")
    df = df.dropna(subset=["ds", "y"])

    m = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.3,
    )
    m.fit(df[["ds", "y"]])

    future   = m.make_future_dataframe(periods=90, freq="D")
    forecast = m.predict(future)

    last_price = float(df["y"].iloc[-1])
    last_date  = df["ds"].max()

    def _price_at(days: int) -> float:
        target = last_date + timedelta(days=days)
        idx    = (forecast["ds"] - target).abs().idxmin()
        return round(float(forecast.loc[idx, "yhat"]), 2)

    fc_30 = _price_at(30)
    fc_90 = _price_at(90)

    pct_30 = round((fc_30 - last_price) / last_price * 100, 2)
    pct_90 = round((fc_90 - last_price) / last_price * 100, 2)

    # Seasonality note: find the month with the highest yhat in the next 90 days
    future_fc = forecast[forecast["ds"] > last_date].copy()
    peak_month = future_fc.loc[future_fc["yhat"].idxmax(), "ds"].strftime("%B")

    return {
        "last_known_price":   round(last_price, 2),
        "forecast_30d":       fc_30,
        "forecast_90d":       fc_90,
        "trend_direction":    "rising" if pct_30 > 0 else "falling",
        "trend_pct_change":   pct_30,
        "trend_pct_90d":      pct_90,
        "seasonality_note":   f"Prices expected to peak around {peak_month} in the forecast window",
    }


def run_price_prediction(
    make: str,
    model: str,
    year: int,
    mileage: int,
    condition: str,
    region: str,
) -> dict:
    """Load XGBoost model, predict price, return top-3 SHAP factors."""
    row = {
        "make":        make.lower(),
        "model":       model.lower(),
        "year":        year,
        "odometer":    mileage,
        "condition":   condition.lower(),
        "region":      region.lower(),
        "fuel":        "gas",          # reasonable default
        "transmission": "automatic",
        "drive":       "fwd",
        "type":        "sedan",
        "title_status": "clean",
        "cylinders":   "4 cylinders",
        "paint_color": "white",
        "state":       region[:2].lower(),
    }
    predicted = predict_price(row)
    shap_factors = explain_prediction(row)

    return {
        "predicted_price": round(predicted, 2),
        "shap_factors":    shap_factors,   # [{feature, value, impact, direction}]
    }


def get_market_context(make: str, model: str, year: int) -> dict:
    """Return inventory count, trend, price-vs-median, and regional range."""
    make_l  = make.lower()
    model_l = model.lower()
    filter_ = {"make": make_l, "model": model_l, "year": year}

    # Current listing count from listings collection
    total_count = _db["listings"].count_documents(filter_)

    # Inventory trend: compare snapshot listing_count across most recent 2 periods
    recent = list(
        _db["price_snapshots"]
        .find(filter_, {"_id": 0, "year_month": 1, "listing_count": 1, "avg_price": 1})
        .sort("year_month", -1)
        .limit(2)
    )

    inventory_trend = "unknown"
    price_vs_median_pct = 0.0
    if len(recent) == 2:
        curr_cnt  = recent[0].get("listing_count", 0)
        prev_cnt  = recent[1].get("listing_count", 1)
        inventory_trend = "rising" if curr_cnt >= prev_cnt else "falling"

    # Overall median price for this make/model/year
    pipeline = [
        {"$match": filter_},
        {"$group": {
            "_id": None,
            "overall_avg": {"$avg": "$avg_price"},
            "min_price":   {"$min": "$avg_price"},
            "max_price":   {"$max": "$avg_price"},
        }},
    ]
    agg = list(_db["price_snapshots"].aggregate(pipeline))
    if agg:
        overall_avg = agg[0]["overall_avg"] or 0
        min_price   = round(agg[0]["min_price"], 2)
        max_price   = round(agg[0]["max_price"], 2)
        # latest avg vs overall avg → negative means currently below market
        latest_avg  = recent[0].get("avg_price", overall_avg) if recent else overall_avg
        price_vs_median_pct = round((latest_avg - overall_avg) / overall_avg * 100, 2) if overall_avg else 0.0
    else:
        min_price = max_price = 0.0

    return {
        "current_inventory_count": total_count,
        "inventory_trend":         inventory_trend,
        "price_vs_median_pct":     price_vs_median_pct,   # negative = below market (good deal)
        "regional_price_range":    {"min": min_price, "max": max_price},
    }


def synthesize_recommendation(
    trend_direction: str,
    trend_pct_change: float,
    price_vs_median_pct: float,
    inventory_trend: str,
    predicted_price: float,
) -> dict:
    """
    Rule-based BUY / WAIT / NEUTRAL logic. Not an LLM call.

    BUY    — forecast rising AND price below market median
    WAIT   — forecast falling by more than 2 %
    NEUTRAL — everything else
    """
    trend_pct = float(trend_pct_change)
    pct_vs_med = float(price_vs_median_pct)

    if trend_direction == "rising" and pct_vs_med < 0:
        signal     = "BUY"
        confidence = "HIGH" if pct_vs_med < -5 else "MODERATE"
        rationale  = (
            f"Prices are rising ({trend_pct:+.1f}% over 30 days) and this listing "
            f"is {abs(pct_vs_med):.1f}% below the market median — buy before prices climb further."
        )
    elif trend_direction == "falling" and trend_pct < -2:
        signal     = "WAIT"
        confidence = "HIGH" if trend_pct < -5 else "MODERATE"
        rationale  = (
            f"Prices are falling ({trend_pct:+.1f}% over 30 days) — waiting could "
            f"save you money in the near term."
        )
    else:
        signal     = "NEUTRAL"
        confidence = "LOW"
        rationale  = (
            f"Market trend is flat ({trend_pct:+.1f}%) and this listing is "
            f"{pct_vs_med:+.1f}% vs the median — no strong signal either way."
        )

    return {
        "recommendation": signal,
        "confidence":     confidence,
        "rationale":      rationale,
        "predicted_price": predicted_price,
    }


# ══════════════════════════════════════════════════════════════════════════════
# OpenAI tool schema definitions
# ══════════════════════════════════════════════════════════════════════════════

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Fetch monthly average price history for a specific make/model/year from MongoDB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "make":  {"type": "string", "description": "Car manufacturer, e.g. 'toyota'"},
                    "model": {"type": "string", "description": "Car model, e.g. 'camry'"},
                    "year":  {"type": "integer", "description": "Model year, e.g. 2018"},
                },
                "required": ["make", "model", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_forecast",
            "description": "Fetch price history from MongoDB and run a Prophet time-series forecast. Returns 30/90-day forecasts and trend direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "make":  {"type": "string",  "description": "Car manufacturer, e.g. 'toyota'"},
                    "model": {"type": "string",  "description": "Car model, e.g. 'camry'"},
                    "year":  {"type": "integer", "description": "Model year, e.g. 2018"},
                },
                "required": ["make", "model", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_price_prediction",
            "description": "Run XGBoost model inference to predict fair market price and return top-3 SHAP factors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "make":      {"type": "string"},
                    "model":     {"type": "string"},
                    "year":      {"type": "integer"},
                    "mileage":   {"type": "integer", "description": "Odometer reading in miles"},
                    "condition": {"type": "string",  "description": "e.g. good, excellent, fair"},
                    "region":    {"type": "string",  "description": "US state or region, e.g. california"},
                },
                "required": ["make", "model", "year", "mileage", "condition", "region"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_context",
            "description": "Fetch inventory count, trend (rising/falling), price-vs-median %, and regional price range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "make":  {"type": "string"},
                    "model": {"type": "string"},
                    "year":  {"type": "integer"},
                },
                "required": ["make", "model", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "synthesize_recommendation",
            "description": (
                "Rule-based BUY/WAIT/NEUTRAL signal. "
                "Call this last, after collecting forecast and market context outputs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trend_direction":    {"type": "string",  "description": "'rising' or 'falling' from run_forecast"},
                    "trend_pct_change":   {"type": "number",  "description": "trend_pct_change from run_forecast"},
                    "price_vs_median_pct":{"type": "number",  "description": "price_vs_median_pct from get_market_context (negative = below market)"},
                    "inventory_trend":    {"type": "string",  "description": "'rising' or 'falling' from get_market_context"},
                    "predicted_price":    {"type": "number",  "description": "predicted_price from run_price_prediction"},
                },
                "required": [
                    "trend_direction", "trend_pct_change",
                    "price_vs_median_pct", "inventory_trend", "predicted_price",
                ],
            },
        },
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# Tool dispatcher
# ══════════════════════════════════════════════════════════════════════════════

_TOOL_FN_MAP = {
    "get_price_history":       get_price_history,
    "run_forecast":            run_forecast,
    "run_price_prediction":    run_price_prediction,
    "get_market_context":      get_market_context,
    "synthesize_recommendation": synthesize_recommendation,
}


def _dispatch(tool_name: str, args: dict) -> Any:
    fn = _TOOL_FN_MAP.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return fn(**args)


# ══════════════════════════════════════════════════════════════════════════════
# Agent loop
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(user_query: str, max_tool_rounds: int = 10) -> dict:
    """
    Run the full tool-calling agent loop for a user car query.

    Parameters
    ----------
    user_query     : Natural-language query, e.g. "Should I buy a 2018 Toyota Camry
                     with 45k miles in good condition in California?"
    max_tool_rounds: Safety cap on tool-call iterations.

    Returns
    -------
    {
      "recommendation": "BUY" | "WAIT" | "NEUTRAL",
      "confidence":     "HIGH" | "MODERATE" | "LOW",
      "explanation":    str,   # 3-sentence plain-English from GPT-4o-mini
      "predicted_price": float,
      "tool_outputs":   dict,  # raw output from every tool called
    }
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_query},
    ]

    tool_outputs: dict = {}
    recommendation_result: dict = {}

    for _ in range(max_tool_rounds):
        response = _oai.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # ── No more tool calls → final answer ────────────────────────────────
        if not msg.tool_calls:
            explanation = msg.content or ""
            return {
                "recommendation":  recommendation_result.get("recommendation", "NEUTRAL"),
                "confidence":      recommendation_result.get("confidence", "LOW"),
                "explanation":     explanation,
                "predicted_price": recommendation_result.get("predicted_price", 0.0),
                "tool_outputs":    tool_outputs,
            }

        # ── Execute each requested tool call ─────────────────────────────────
        messages.append(msg)   # append assistant's tool-call message

        for tc in msg.tool_calls:
            args   = json.loads(tc.function.arguments)
            result = _dispatch(tc.function.name, args)

            # Capture synthesize_recommendation output for top-level return
            if tc.function.name == "synthesize_recommendation":
                recommendation_result = result

            tool_outputs[tc.function.name] = result

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result, default=str),
            })

    return {
        "recommendation": recommendation_result.get("recommendation", "NEUTRAL"),
        "confidence":     recommendation_result.get("confidence", "LOW"),
        "explanation":    "Max tool rounds reached without final LLM response.",
        "predicted_price": recommendation_result.get("predicted_price", 0.0),
        "tool_outputs":   tool_outputs,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows UTF-8 fix

    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Should I buy a 2018 Toyota Camry with 45,000 miles in good condition in California?"
    )
    sep = "-" * 60
    print(f"\nQuery: {query}\n{sep}")
    result = run_agent(query)

    print(f"Recommendation : {result['recommendation']}  ({result['confidence']} confidence)")
    print(f"Predicted price: ${result['predicted_price']:,.0f}")
    print(f"\nExplanation:\n{result['explanation']}")
    print(f"\n{sep}\nTool outputs:")
    print(json.dumps(result["tool_outputs"], indent=2, default=str))
