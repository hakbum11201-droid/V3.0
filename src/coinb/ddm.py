import json
import os
import time
from typing import Any, Dict, List

from .config_loader import load_config
from .jsonl import ensure_parent


def _load_json_safe(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_jsonl_last_n(filepath: str, n: int) -> List[Dict[str, Any]]:
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Parse only last n lines for efficiency
            tail = lines[-n:] if len(lines) > n else lines
            return [json.loads(line) for line in tail if line.strip()]
    except Exception:
        return []


def run_ddm_status(config_path: str, output_path: str) -> Dict[str, Any]:
    now = time.time()
    
    # 1. Load Files
    config = load_config(config_path)
    heartbeat = _load_json_safe("runtime/heartbeat.json")
    engine_status = _load_json_safe("runtime/engine_status.json")
    storage_status = _load_json_safe("reports/storage_status.json")
    micro = _load_json_safe("reports/microstructure_snapshot.json")
    loss_analysis = _load_json_safe("reports/orderflow_loss_analysis.json")
    decisions = _load_jsonl_last_n("logs/orderflow_paper_decisions.jsonl", 100)
    
    # 2. Extract Basic Info
    app_cfg = config.get("app", {})
    live_cfg = config.get("live", {})
    mode = app_cfg.get("default_mode", "unknown")
    live_enabled = live_cfg.get("enabled", False)
    
    risk_items = []
    metrics = {}
    
    # 3. Risk Checks
    # 3.1. live.enabled check
    if live_enabled is True:
        risk_items.append({
            "code": "LIVE_ENABLED_ERROR",
            "severity": "DATA_ERROR",
            "message": "live.enabled is true. Safety block.",
            "source": "config.json",
            "actual": True,
            "threshold": False
        })
        
    # 3.2. default_mode check
    if mode != "paper":
        risk_items.append({
            "code": "INVALID_MODE_ERROR",
            "severity": "DATA_ERROR",
            "message": f"default_mode is {mode}, not paper.",
            "source": "config.json",
            "actual": mode,
            "threshold": "paper"
        })
        
    # 3.3. heartbeat existence
    if not heartbeat:
        risk_items.append({
            "code": "MISSING_HEARTBEAT",
            "severity": "DATA_ERROR",
            "message": "heartbeat.json not found.",
            "source": "runtime",
            "actual": None,
            "threshold": "exists"
        })
    else:
        # 3.4. heartbeat age
        last_update = heartbeat.get("last_update", 0)
        age = now - last_update
        if age >= 120:
            risk_items.append({
                "code": "ENGINE_STALLED",
                "severity": "DATA_ERROR",
                "message": f"Engine heartbeat is too old ({int(age)}s).",
                "source": "heartbeat.json",
                "actual": int(age),
                "threshold": 120
            })
            
        # 3.5. heartbeat/engine_status last_error
        hb_err = heartbeat.get("last_error")
        eng_err = engine_status.get("last_error")
        if hb_err or eng_err:
            risk_items.append({
                "code": "ENGINE_ERROR_DETECTED",
                "severity": "CAUTION",
                "message": "Last error detected in heartbeat or engine status.",
                "source": "engine",
                "actual": hb_err or eng_err,
                "threshold": None
            })

    # 3.6. KRW-BTC price change
    features = micro.get("features", {})
    btc_f = features.get("KRW-BTC", {})
    btc_chg = btc_f.get("price_change_10s_pct", 0.0)
    if btc_chg <= -3.0:
        risk_items.append({
            "code": "BTC_CRASH_SEVERE",
            "severity": "BLOCK_NEW_ENTRY",
            "message": "KRW-BTC dropped over 3.0% in 10s.",
            "source": "microstructure",
            "actual": btc_chg,
            "threshold": -3.0
        })
    elif btc_chg <= -1.5:
        risk_items.append({
            "code": "BTC_CRASH_CAUTION",
            "severity": "CAUTION",
            "message": "KRW-BTC dropped over 1.5% in 10s.",
            "source": "microstructure",
            "actual": btc_chg,
            "threshold": -1.5
        })

    # 3.7. Paper Performance
    summary = loss_analysis.get("summary", {})
    trade_count = summary.get("trade_count", summary.get("total_trades", 0))
    if trade_count == 0:
        metrics["insufficient_trade_data"] = True
    else:
        mdd = summary.get("max_drawdown_pct", 0.0)
        cons_loss = summary.get("consecutive_losses", 0)
        
        if mdd >= 5.0:
            risk_items.append({
                "code": "HIGH_MDD_SEVERE",
                "severity": "BLOCK_NEW_ENTRY",
                "message": f"Max drawdown reached {mdd:.2f}%.",
                "source": "loss_analysis",
                "actual": mdd,
                "threshold": 5.0
            })
        elif mdd >= 3.0:
            risk_items.append({
                "code": "HIGH_MDD_CAUTION",
                "severity": "CAUTION",
                "message": f"Max drawdown reached {mdd:.2f}%.",
                "source": "loss_analysis",
                "actual": mdd,
                "threshold": 3.0
            })
            
        if cons_loss >= 5:
            risk_items.append({
                "code": "CONSECUTIVE_LOSS_SEVERE",
                "severity": "BLOCK_NEW_ENTRY",
                "message": f"Consecutive losses reached {cons_loss}.",
                "source": "loss_analysis",
                "actual": cons_loss,
                "threshold": 5
            })
        elif cons_loss >= 3:
            risk_items.append({
                "code": "CONSECUTIVE_LOSS_CAUTION",
                "severity": "CAUTION",
                "message": f"Consecutive losses reached {cons_loss}.",
                "source": "loss_analysis",
                "actual": cons_loss,
                "threshold": 3
            })

    # 3.8. Low Volume Ratio
    if decisions:
        low_vol_count = sum(1 for d in decisions if d.get("reason") == "LOW_VOLUME")
        ratio = low_vol_count / len(decisions)
        if ratio >= 0.8:
            risk_items.append({
                "code": "HIGH_LOW_VOLUME_REJECTION",
                "severity": "CAUTION",
                "message": f"LOW_VOLUME rejection ratio is {ratio:.1%}.",
                "source": "decisions",
                "actual": ratio,
                "threshold": 0.8
            })

    # 3.9. Storage size
    total_size = storage_status.get("total_logs_size_mb", 0)
    if total_size >= 5000:
        risk_items.append({
            "code": "STORAGE_OVERFLOW_ERROR",
            "severity": "DATA_ERROR",
            "message": f"Total log size is {total_size}MB.",
            "source": "storage",
            "actual": total_size,
            "threshold": 5000
        })
    elif total_size >= 2000:
        risk_items.append({
            "code": "STORAGE_WARNING",
            "severity": "CAUTION",
            "message": f"Total log size is {total_size}MB.",
            "source": "storage",
            "actual": total_size,
            "threshold": 2000
        })

    # 4. Determine Status
    status = "NORMAL"
    should_block = False
    risk_level = 0
    
    # Order of priority: DATA_ERROR > BLOCK_NEW_ENTRY > CAUTION > NORMAL
    severities = [item["severity"] for item in risk_items]
    if "DATA_ERROR" in severities:
        status = "DATA_ERROR"
        risk_level = 3
        should_block = True
    elif "BLOCK_NEW_ENTRY" in severities:
        status = "BLOCK_NEW_ENTRY"
        risk_level = 2
        should_block = True
    elif "CAUTION" in severities:
        status = "CAUTION"
        risk_level = 1
        should_block = False
        
    # 5. Summary & Recommendations
    if status == "NORMAL":
        summary = "All systems normal."
        recs = ["Continue monitoring."]
    elif status == "CAUTION":
        summary = "Caution advised due to minor risk factors."
        recs = ["Review risk items and consider adjusting config candidates."]
    elif status == "BLOCK_NEW_ENTRY":
        summary = "Risk detected. New entries recommended to be blocked."
        recs = ["Stop new paper entries.", "Investigate strategy logic or market conditions."]
    else: # DATA_ERROR
        summary = "Critical data or configuration error. System unreliable."
        recs = ["Fix heartbeat/engine errors.", "Check config.json safety settings."]

    result = {
        "ok": True,
        "status": status,
        "risk_level": risk_level,
        "should_block_new_entry": should_block,
        "generated_at": now,
        "mode": mode,
        "live_enabled": live_enabled,
        "summary": summary,
        "risk_items": risk_items,
        "metrics": metrics,
        "recommendations": recs
    }
    
    # 6. Save Output
    if output_path:
        ensure_parent(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            
    return result
