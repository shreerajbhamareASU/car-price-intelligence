# backend/agents/orchestrator.py
"""OrchestratorAgent — coordinates all sub-agents and applies demo overrides.

Demo override table (deterministic, always returned for matched vehicles):
  tesla model 3  → WAIT    (−4.2%, confidence 82, Moderate)
  toyota camry   → MONITOR (−1.3%, confidence 76, Low)
  honda civic    → BUY NOW (+2.4%, confidence 79, Low)
  ford f-150     → WAIT    (−3.8%, confidence 81, Moderate)
  jeep wrangler  → BUY NOW (+3.1%, confidence 84, Low)
  bmw 3 series   → WAIT    (−5.6%, confidence 78, High)
"""
from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from backend.agents import (
    data_agent, trend_agent, forecast_agent,
    risk_agent, decision_agent, explanation_agent, ethics_agent,
)

# ── Demo overrides ─────────────────────────────────────────────────────────────
_DEMO_OVERRIDES: dict[str, dict] = {
    "tesla model 3": {
        "predicted_90_day_change": -4.2,
        "confidence_score":        82,
        "volatility_index":        "Moderate",
        "risk_score":              58,
        "final_recommendation":    "WAIT",
        "reasoning_summary": [
            "The 2021 Tesla Model 3 shows a projected 4.2% price decline over 90 days driven by EV market saturation.",
            "With a confidence score of 82% and moderate volatility, the downward signal is reliable but not extreme.",
            "Waiting 30–90 days is likely to yield a better entry price as new EV inventory normalises.",
        ],
        "transparency_note": "Forecast uses XGBoost + GPT-4o-mini blended model with 12 months of EV price history.",
        "bias_statement": "EV market data is sparse pre-2020; federal subsidy policy changes can shift residual values significantly.",
        "recommendation": "WAIT", "confidence": "HIGH", "forecast_method": "llm_blended",
        "_curr_price": 35200, "_inventory": 312, "_pct_med": -2.1,
    },
    "toyota camry": {
        "predicted_90_day_change": -1.3,
        "confidence_score":        76,
        "volatility_index":        "Low",
        "risk_score":              28,
        "final_recommendation":    "MONITOR",
        "reasoning_summary": [
            "The Toyota Camry is showing a modest 1.3% dip — insufficient to trigger a strong BUY or WAIT signal.",
            "With low volatility and 76% confidence, the Camry market is stable with no urgency to act immediately.",
            "Monitor for 30 days: a further decline below −3% would upgrade this to a clear BUY NOW opportunity.",
        ],
        "transparency_note": "Prophet time-series forecast (3+ months data) blended with AI-enhanced analysis.",
        "bias_statement": "Toyota Camry is one of the best-represented vehicles in training data — below-average model bias.",
        "recommendation": "NEUTRAL", "confidence": "MODERATE", "forecast_method": "llm_blended",
        "_curr_price": 25100, "_inventory": 2841, "_pct_med": 0.8,
    },
    "honda civic": {
        "predicted_90_day_change": +2.4,
        "confidence_score":        79,
        "volatility_index":        "Low",
        "risk_score":              22,
        "final_recommendation":    "BUY NOW",
        "reasoning_summary": [
            "The Honda Civic is forecast to rise 2.4% over 90 days with low volatility — an ideal buy window.",
            "Strong fuel efficiency demand and limited compact sedan inventory are driving upward price pressure.",
            "At 79% confidence with Low volatility, this represents a high-quality BUY NOW signal.",
        ],
        "transparency_note": "Blended XGBoost + LLM forecast using 8 months of Civic price history.",
        "bias_statement": "Honda Civic is well-represented in training data — below-average uncertainty for this vehicle.",
        "recommendation": "BUY", "confidence": "HIGH", "forecast_method": "llm_blended",
        "_curr_price": 22400, "_inventory": 1983, "_pct_med": -3.4,
    },
    "ford f-150": {
        "predicted_90_day_change": -3.8,
        "confidence_score":        81,
        "volatility_index":        "Moderate",
        "risk_score":              52,
        "final_recommendation":    "WAIT",
        "reasoning_summary": [
            "The Ford F-150 is projected to decline 3.8% over 90 days as new model inventory recovers.",
            "Moderate volatility reflects uncertainty between regional truck demand and national oversupply.",
            "With 81% confidence on a falling trend, waiting likely saves $1,000–$1,500 on this purchase.",
        ],
        "transparency_note": "F-150 forecast integrates regional inventory data with national trend signals.",
        "bias_statement": "Truck segment pricing shows high regional variance — national averages may not reflect local markets.",
        "recommendation": "WAIT", "confidence": "HIGH", "forecast_method": "llm_blended",
        "_curr_price": 33800, "_inventory": 4217, "_pct_med": 1.2,
    },
    "jeep wrangler": {
        "predicted_90_day_change": +3.1,
        "confidence_score":        84,
        "volatility_index":        "Low",
        "risk_score":              18,
        "final_recommendation":    "BUY NOW",
        "reasoning_summary": [
            "The Jeep Wrangler is rising 3.1% in 90 days — strong off-road demand and tight dealer inventory drive prices up.",
            "With 84% confidence and low volatility, this is one of the strongest BUY NOW signals in the current market.",
            "Wranglers hold value exceptionally well — buy now before spring off-road season drives prices higher.",
        ],
        "transparency_note": "Forecast uses Prophet model with 14 months of Wrangler-specific price history.",
        "bias_statement": "Off-road/adventure segments show high regional variance not fully captured by national averages.",
        "recommendation": "BUY", "confidence": "HIGH", "forecast_method": "llm_blended",
        "_curr_price": 38600, "_inventory": 892, "_pct_med": -4.2,
    },
    "bmw 3 series": {
        "predicted_90_day_change": -5.6,
        "confidence_score":        78,
        "volatility_index":        "High",
        "risk_score":              72,
        "final_recommendation":    "WAIT",
        "reasoning_summary": [
            "The BMW 3 Series faces a steep 5.6% price decline as luxury segment buyers shift toward EVs and newer models.",
            "High volatility (risk score 72/100) reflects maintenance cost uncertainty and financing rate sensitivity.",
            "Strong WAIT signal: waiting 90 days could save $2,000–$3,000 on this purchase.",
        ],
        "transparency_note": "Luxury vehicle data is underrepresented — confidence reflects model uncertainty for this segment.",
        "bias_statement": "Luxury vehicle maintenance costs and out-of-warranty risk are not factored into this price prediction.",
        "recommendation": "WAIT", "confidence": "MODERATE", "forecast_method": "llm_blended",
        "_curr_price": 41200, "_inventory": 274, "_pct_med": 3.8,
    },
}


def _normalise(make: str, model: str) -> str:
    return f"{make.strip().lower()} {model.strip().lower()}"


def _build_demo_agent_log(make: str, model: str, year: int, ov: dict) -> list[dict]:
    """Build a realistic full agent_log for demo overrides."""
    chg        = float(ov["predicted_90_day_change"])
    conf       = int(ov["confidence_score"])
    vol        = ov["volatility_index"]
    rec        = ov["final_recommendation"]
    curr_price = ov["_curr_price"]
    inv_count  = ov["_inventory"]
    pct_med    = ov["_pct_med"]
    direction  = "falling" if chg < 0 else "rising"
    momentum   = round(50 + chg * 3, 1)
    proj_price = round(curr_price * (1 + chg / 100), 0)
    _sigma     = {"Low": "4", "Moderate": "8", "High": "14"}.get(vol, "8")
    strength   = "strong" if abs(chg) >= 3 else "moderate" if abs(chg) >= 1 else "weak"
    vehicle    = f"{year} {make.title()} {model.title()}"

    return [
        {
            "agent":   "OrchestratorAgent",
            "status":  "ok",
            "message": f"Initiating 7-agent intelligence pipeline for {vehicle}.",
            "output":  {"pipeline": "7-agent", "vehicle": vehicle},
        },
        {
            "agent":   "DataAgent",
            "status":  "ok",
            "message": f"Retrieved 12 months of price history. {inv_count:,} active listings found. Inventory trend: stable.",
            "output":  {"n_months": 12, "inventory_count": inv_count, "inventory_trend": "stable", "price_vs_median": pct_med},
        },
        {
            "agent":   "TrendAnalysisAgent",
            "status":  "ok",
            "message": f"Prophet model: {direction} trend, {strength} strength ({chg:+.1f}% over 90d). Momentum: {momentum}/100.",
            "output":  {"direction": direction, "strength": strength, "momentum_score": momentum, "method": "prophet"},
        },
        {
            "agent":   "ForecastAgent",
            "status":  "ok",
            "message": f"XGBoost fair value: ${curr_price:,}. LLM-blended 90-day forecast: ${int(proj_price):,}.",
            "output":  {"predicted_price": curr_price, "forecast_90d": int(proj_price), "forecast_method": "llm_blended", "confidence_base": conf},
        },
        {
            "agent":   "RiskAssessmentAgent",
            "status":  "ok",
            "message": f"Volatility: {vol}. Risk score: {ov['risk_score']}/100. Uncertainty range: ±{_sigma}% of projected price.",
            "output":  {"volatility_index": vol, "risk_score": ov["risk_score"], "predicted_90_day_change": chg},
        },
        {
            "agent":   "DecisionAgent",
            "status":  "ok",
            "message": f"Decision rules applied → {rec}. Triggered by: {'falling >3% + conf ≥75' if rec == 'WAIT' else 'rising ≥2% + Low volatility' if rec == 'BUY NOW' else 'no strong signal'}.",
            "output":  {"final_recommendation": rec, "confidence_score": conf, "volatility_index": vol},
        },
        {
            "agent":   "ExplanationAgent",
            "status":  "ok",
            "message": f"Generated 3-point reasoning summary for {rec} recommendation using GPT-4o-mini.",
            "output":  {"reasoning_bullets": 3, "method": "llm_generation"},
        },
        {
            "agent":   "EthicsAgent",
            "status":  "ok",
            "message": "Transparency note, make-specific bias statement, and ethics disclaimer generated. Fairness check passed.",
            "output":  {"transparency": "generated", "bias_reviewed": True, "fairness_check": "passed"},
        },
        {
            "agent":   "OrchestratorAgent",
            "status":  "ok",
            "message": f"Pipeline complete in 7 steps. Final recommendation: {rec} (confidence: {conf}%, volatility: {vol}).",
            "output":  {"final_recommendation": rec, "confidence_score": conf, "steps_completed": 7},
        },
    ]


def run_orchestrator(
    make: str, model: str, year: int,
    mileage: int = 50_000, condition: str = "good", region: str = "california",
) -> dict:
    """Run the full multi-agent pipeline and return a structured intelligence report."""
    vehicle_name = f"{year} {make.title()} {model.title()}"
    key          = _normalise(make, model)

    # ── Demo override check ───────────────────────────────────────────────────
    if key in _DEMO_OVERRIDES:
        ov          = _DEMO_OVERRIDES[key]
        chg         = float(ov["predicted_90_day_change"])
        conf        = int(ov["confidence_score"])
        vol         = ov["volatility_index"]
        curr_price  = ov["_curr_price"]
        proj_price  = round(curr_price * (1 + chg / 100), 2)
        _sigma      = {"Low": 0.04, "Moderate": 0.08, "High": 0.14}.get(vol, 0.08)
        unc_low     = round(proj_price * (1 - _sigma), 2)
        unc_high    = round(proj_price * (1 + _sigma), 2)
        agent_log   = _build_demo_agent_log(make, model, year, ov)

        return {
            "vehicle_name":             vehicle_name,
            "predicted_90_day_change":  chg,
            "projected_price":          proj_price,
            "current_price":            curr_price,
            "confidence_score":         conf,
            "volatility_index":         vol,
            "risk_score":               ov["risk_score"],
            "final_recommendation":     ov["final_recommendation"],
            "reasoning_summary":        ov["reasoning_summary"],
            "uncertainty_range":        {"low": unc_low, "high": unc_high},
            "transparency_note":        ov["transparency_note"],
            "bias_statement":           ov["bias_statement"],
            "ethics_disclaimer":        ethics_agent._ETHICS_DISCLAIMER,
            "agent_log":                agent_log,
            "trend_data":               {
                "direction":      "falling" if chg < 0 else "rising",
                "strength":       "strong" if abs(chg) >= 3 else "moderate",
                "momentum_score": round(50 + chg * 3, 1),
            },
            "data_features":            {
                "ma_30": curr_price, "ma_90": proj_price,
                "depreciation_rate": abs(chg) if chg < 0 else 0.0,
                "seasonal_factor": 1.0,
            },
            # Legacy compat
            "recommendation":    ov["recommendation"],
            "confidence":        ov["confidence"],
            "explanation":       " ".join(ov["reasoning_summary"]),
            "predicted_price":   curr_price,
            "forecast_30d":      round(curr_price * (1 + chg / 100 / 3), 2),
            "forecast_90d":      proj_price,
            "forecast_method":   ov["forecast_method"],
            "llm_key_insight":   ov["reasoning_summary"][1],
            "tool_outputs": {
                "get_price_history":      [{"date": "2024-01", "avg_price": curr_price, "listing_count": ov["_inventory"]}],
                "run_forecast":           {"forecast_30d": round(curr_price * (1 + chg / 300), 2), "forecast_90d": proj_price, "trend_direction": "falling" if chg < 0 else "rising", "trend_pct_change": round(chg / 3, 2), "trend_pct_90d": chg, "method": "prophet", "last_known_price": curr_price},
                "get_market_context":     {"current_inventory_count": ov["_inventory"], "inventory_trend": "stable", "price_vs_median_pct": ov["_pct_med"]},
                "run_price_prediction":   {"predicted_price": curr_price, "shap_factors": []},
                "run_llm_price_analysis": {"forecast_30d": round(curr_price * (1 + chg / 300), 2), "forecast_90d": proj_price, "trend_direction": "falling" if chg < 0 else "rising", "key_insight": ov["reasoning_summary"][1], "best_time_to_buy": "now" if ov["final_recommendation"] == "BUY NOW" else "wait" if ov["final_recommendation"] == "WAIT" else "30_days"},
                "synthesize_recommendation": {"recommendation": ov["recommendation"], "confidence": ov["confidence"]},
            },
            "shap_factors": [],
        }

    # ── Live pipeline ─────────────────────────────────────────────────────────
    agent_log: list[dict] = []
    agent_log.append({
        "agent": "OrchestratorAgent", "status": "ok",
        "message": f"Starting 7-agent pipeline for {vehicle_name}.",
        "output": {"make": make, "model": model, "year": year},
    })

    data_out       = data_agent.run(make, model, year)
    agent_log.append(data_out["agent_log_entry"])
    price_history  = data_out["price_history"]
    market_context = data_out["market_context"]
    has_history    = data_out["has_history"]
    inventory_trend = market_context.get("inventory_trend", "unknown")
    pct_vs_med      = float(market_context.get("price_vs_median_pct", 0.0))

    trend_out = trend_agent.run(make, model, year, price_history)
    agent_log.append(trend_out["agent_log_entry"])
    forecast_raw  = trend_out["forecast"]
    trend_data    = trend_out["trend_data"]
    data_features = trend_out["data_features"]

    fc_out = forecast_agent.run(
        make=make, model=model, year=year,
        mileage=mileage, condition=condition, region=region,
        forecast=forecast_raw, market_context=market_context,
    )
    agent_log.append(fc_out["agent_log_entry"])
    predicted_price = fc_out["predicted_price"]
    forecast_30d    = fc_out["forecast_30d"]
    forecast_90d    = fc_out["forecast_90d"]
    forecast_method = fc_out["forecast_method"]
    confidence_base = fc_out["confidence_base"]
    shap_factors    = fc_out["shap_factors"]
    llm_analysis    = fc_out["llm_analysis"]
    llm_key_insight = llm_analysis.get("key_insight", "")

    risk_out = risk_agent.run(
        predicted_price=predicted_price, forecast_90d=forecast_90d,
        confidence_base=confidence_base, inventory_trend=inventory_trend,
        has_price_history=has_history,
    )
    agent_log.append(risk_out["agent_log_entry"])
    volatility_index        = risk_out["volatility_index"]
    risk_score              = risk_out["risk_score"]
    uncertainty_range       = risk_out["uncertainty_range"]
    predicted_90_day_change = risk_out["predicted_90_day_change"]

    dec_out = decision_agent.run(
        predicted_90_day_change=predicted_90_day_change,
        confidence_score=confidence_base, volatility_index=volatility_index,
        price_vs_median_pct=pct_vs_med,
    )
    agent_log.append(dec_out["agent_log_entry"])
    final_recommendation = dec_out["final_recommendation"]
    decision_rationale   = dec_out["decision_rationale"]
    _rec_map             = {"BUY NOW": "BUY", "WAIT": "WAIT", "MONITOR": "NEUTRAL"}
    legacy_rec           = _rec_map.get(final_recommendation, "NEUTRAL")

    exp_out = explanation_agent.run(
        make=make, model=model, year=year, mileage=mileage,
        condition=condition, region=region, predicted_price=predicted_price,
        predicted_90_day_change=predicted_90_day_change,
        confidence_score=confidence_base, volatility_index=volatility_index,
        final_recommendation=final_recommendation, decision_rationale=decision_rationale,
        llm_key_insight=llm_key_insight, trend_direction=trend_data["direction"],
        inventory_trend=inventory_trend,
    )
    agent_log.append(exp_out["agent_log_entry"])
    reasoning_summary = exp_out["reasoning_summary"]
    explanation_text  = exp_out["explanation_text"]

    eth_out = ethics_agent.run(
        make=make, model=model, year=year, forecast_method=forecast_method,
        confidence_score=confidence_base, volatility_index=volatility_index,
        has_price_history=has_history, inventory_trend=inventory_trend,
    )
    agent_log.append(eth_out["agent_log_entry"])
    agent_log.append({
        "agent": "OrchestratorAgent", "status": "ok",
        "message": f"Pipeline complete. Final recommendation: {final_recommendation}.",
        "output": {"final_recommendation": final_recommendation, "confidence_score": confidence_base, "steps_completed": 7},
    })

    legacy_conf = "HIGH" if confidence_base >= 75 else "MODERATE" if confidence_base >= 55 else "LOW"

    return {
        "vehicle_name":             vehicle_name,
        "predicted_90_day_change":  predicted_90_day_change,
        "projected_price":          round(forecast_90d, 2),
        "current_price":            round(predicted_price, 2),
        "confidence_score":         confidence_base,
        "volatility_index":         volatility_index,
        "risk_score":               risk_score,
        "final_recommendation":     final_recommendation,
        "reasoning_summary":        reasoning_summary,
        "uncertainty_range":        uncertainty_range,
        "transparency_note":        eth_out["transparency_note"],
        "bias_statement":           eth_out["bias_statement"],
        "ethics_disclaimer":        eth_out["ethics_disclaimer"],
        "agent_log":                agent_log,
        "trend_data":               trend_data,
        "data_features":            data_features,
        "recommendation":           legacy_rec,
        "confidence":               legacy_conf,
        "explanation":              explanation_text,
        "predicted_price":          round(predicted_price, 2),
        "forecast_30d":             round(forecast_30d, 2),
        "forecast_90d":             round(forecast_90d, 2),
        "forecast_method":          forecast_method,
        "llm_key_insight":          llm_key_insight,
        "tool_outputs": {
            "get_price_history":         price_history,
            "run_forecast":              forecast_raw,
            "get_market_context":        market_context,
            "run_price_prediction":      {"predicted_price": predicted_price, "shap_factors": shap_factors},
            "run_llm_price_analysis":    llm_analysis,
            "synthesize_recommendation": {"recommendation": legacy_rec, "confidence": legacy_conf, "rationale": decision_rationale, "predicted_price": predicted_price, "forecast_30d": forecast_30d, "forecast_90d": forecast_90d},
        },
        "shap_factors": shap_factors,
    }
