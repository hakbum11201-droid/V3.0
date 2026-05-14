"""
diagnose_reversal_entry_funnel.py

24H Paper에서 수집된 대량의 이벤트(약 39.4만 개) 중 왜 거래 진입(Trades)이 0건이었는지,
진입 조건(Funnel) 병목 지점을 분석하고, Master Dataset의 축소 원인을 진단합니다.
"""

import os
import json
from datetime import datetime
from collections import defaultdict

# =============================================================================
# Constants & Configuration
# =============================================================================
PAPER_EVENTS_JSONL = "logs/paper/reversal_edge_v2_paper_24h_events.jsonl"
CANDIDATE_JSON = "configs/experiments/reversal_edge_candidate_v2_from_36h.json"
PAPER_SUMMARY_JSON = "reports/experiments/reversal_edge_v2_paper_run_summary_20260513_134930.json"

REPORTS_DIR = "reports/experiments"

# =============================================================================
# Functions
# =============================================================================

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] JSON 읽기 실패 {filepath}: {e}")
    return {}

def analyze_events():
    total_lines = 0
    parsed_success = 0
    parsed_failed = 0
    
    market_dist = defaultdict(int)
    raw_type_dist = defaultdict(int)
    norm_type_dist = defaultdict(int)
    
    sol_events = 0
    earliest_ts = float('inf')
    latest_ts = 0.0
    
    if not os.path.exists(PAPER_EVENTS_JSONL):
        print(f"[Error] 파일을 찾을 수 없습니다: {PAPER_EVENTS_JSONL}")
        return None
        
    print(f"[Info] Reading {PAPER_EVENTS_JSONL}...")
    with open(PAPER_EVENTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            total_lines += 1
            try:
                data = json.loads(line)
                parsed_success += 1
                
                # Market
                market = data.get("market", data.get("code", "UNKNOWN"))
                market_dist[market] += 1
                if market == "KRW-SOL":
                    sol_events += 1
                    
                # Type
                e_type = data.get("type", data.get("event_type", "unknown")).lower()
                raw_type_dist[e_type] += 1
                
                norm_type = e_type
                if e_type == "orderbook_sample":
                    norm_type = "orderbook"
                norm_type_dist[norm_type] += 1
                
                # Timestamp
                ts = None
                for t_key in ["timestamp", "trade_timestamp", "ts", "timestamp_ms"]:
                    if t_key in data:
                        ts = float(data[t_key])
                        break
                        
                if ts is not None:
                    if ts > 1e11:
                        ts = ts / 1000.0
                    if ts < earliest_ts: earliest_ts = ts
                    if ts > latest_ts: latest_ts = ts
                    
            except json.JSONDecodeError:
                parsed_failed += 1
                
    if earliest_ts == float('inf'): earliest_ts = 0.0
    
    return {
        "total_lines": total_lines,
        "parsed_success": parsed_success,
        "parsed_failed": parsed_failed,
        "market_distribution": dict(market_dist),
        "sol_events": sol_events,
        "raw_type_distribution": dict(raw_type_dist),
        "norm_type_distribution": dict(norm_type_dist),
        "earliest_ts": earliest_ts,
        "latest_ts": latest_ts
    }

def recursive_find(d, keywords, path=""):
    found = {}
    if isinstance(d, dict):
        for k, v in d.items():
            current_path = f"{path}.{k}" if path else k
            if any(kw in k.lower() for kw in keywords):
                found[current_path] = v
            if isinstance(v, (dict, list)):
                found.update(recursive_find(v, keywords, current_path))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            current_path = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                found.update(recursive_find(v, keywords, current_path))
    return found

def build_diagnostic_report(events_stat, candidate, paper_summary):
    c_market = candidate.get("market", "KRW-SOL")
    c_mode = candidate.get("mode", "STATIC_SOL_ONLY")
    c_cost = candidate.get("cost_floor", 0.20)
    thresholds = candidate.get("thresholds", {})
    
    # Deep inspect candidate
    keywords = ["threshold", "score", "cost", "tp", "sl", "timeout", "mode", "market"]
    found_keys = recursive_find(candidate, keywords)
    
    # 1. 원인 후보 추정 (Funnel)
    reasons = []
    
    if events_stat["sol_events"] == 0 and c_mode == "STATIC_SOL_ONLY":
        reasons.append("KRW-SOL 이벤트가 수집되지 않았음 (데이터 타입 인식 문제 또는 WebSocket 오류)")
        
    orderbook_count = events_stat["norm_type_distribution"].get("orderbook", 0)
    trade_count = events_stat["norm_type_distribution"].get("trade", 0)
    
    if orderbook_count == 0:
        reasons.append("호가(Orderbook) 이벤트 누락: 데이터 타입 인식 문제 (orderbook_sample 등 미매핑)")
    if trade_count == 0:
        reasons.append("체결(Trade) 이벤트 누락: 데이터 타입 인식 문제")
        
    if isinstance(c_cost, str):
        c_cost_val = float(c_cost.replace('%', ''))
    else:
        c_cost_val = float(c_cost)
        
    if c_cost_val >= 0.25:
        reasons.append(f"조건 과엄격 문제: cost_floor({c_cost_val}%)가 높아 수익 필터를 통과하지 못함")
        
    if not thresholds:
        reasons.append("Candidate Schema 문제: thresholds가 {}로 비어있어 기본값이 적용되었거나 조건 매핑이 어긋났을 수 있음")
    else:
        reasons.append(f"조건 과엄격 문제: RANGE 장세에서 Reversal Threshold ({thresholds}) 도달 실패 (시장 레짐 문제)")
        
    # 2. Master Dataset 축소 원인 진단
    master_reasons = [
        "1. 파싱 시 timestamp 단독 키 문제: 동일 밀리초 내 발생한 다수의 호가/체결 데이터가 딕셔너리 키 덮어쓰기로 인해 중복 제거됨.",
        "2. build_master_validation_dataset.py의 키 생성 로직이 market, price, volume 등을 모두 포함하도록 보강되어야 함.",
        "3. orderbook_sample이 Master Dataset 정규화 로직에서 필터링되지 않도록 유효 이벤트로 취급 필요."
    ]
    
    return {
        "candidate_info": {
            "mode": c_mode,
            "market": c_market,
            "cost_floor": c_cost,
            "thresholds": thresholds,
            "deep_found_keys": found_keys
        },
        "funnel_reasons": reasons,
        "master_dataset_reasons": master_reasons
    }

def main():
    print("============================================================")
    print(" Diagnose Reversal Entry Funnel")
    print("============================================================")
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    candidate = load_json(CANDIDATE_JSON)
    paper_summary = load_json(PAPER_SUMMARY_JSON)
    
    events_stat = analyze_events()
    if not events_stat:
        return
        
    report = build_diagnostic_report(events_stat, candidate, paper_summary)
    
    final_summary = {
        "generated_at": datetime.now().isoformat(),
        "events_stat": events_stat,
        "candidate": report["candidate_info"],
        "funnel_reasons": report["funnel_reasons"],
        "master_dataset_reasons": report["master_dataset_reasons"]
    }
    
    json_path = os.path.join(REPORTS_DIR, "reversal_entry_funnel_diagnostics_latest.json")
    txt_path = os.path.join(REPORTS_DIR, "reversal_entry_funnel_diagnostics_latest.txt")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final_summary, f, ensure_ascii=False, indent=2)
        
    e_stat = events_stat
    txt_lines = [
        "============================================================",
        "  Reversal Entry Funnel Diagnostics Report",
        "============================================================",
        f"생성 시각: {final_summary['generated_at']}",
        "",
        "[Events 파싱 요약]",
        f" - 총 라인 수     : {e_stat['total_lines']:,}",
        f" - 파싱 성공      : {e_stat['parsed_success']:,}",
        f" - 파싱 실패      : {e_stat['parsed_failed']:,}",
        f" - KRW-SOL 이벤트 : {e_stat['sol_events']:,}",
        f" - 수집 기간      : {datetime.fromtimestamp(e_stat['earliest_ts'])} ~ {datetime.fromtimestamp(e_stat['latest_ts'])}",
        "",
        "[Event Type 분포 (Raw)]"
    ]
    
    for t_name, t_count in e_stat["raw_type_distribution"].items():
        txt_lines.append(f" - {t_name:15s} : {t_count:,}")
        
    txt_lines.append("\n[Event Type 분포 (Normalized)]")
    for t_name, t_count in e_stat["norm_type_distribution"].items():
        txt_lines.append(f" - {t_name:15s} : {t_count:,}")
        
    txt_lines.extend([
        "",
        "[Candidate 주요 조건 및 심층 탐색 (Schema Inspection)]",
        f" - Mode       : {report['candidate_info']['mode']}",
        f" - Market     : {report['candidate_info']['market']}",
        f" - Cost Floor : {report['candidate_info']['cost_floor']}",
        f" - Thresholds (표면): {report['candidate_info']['thresholds']}",
        "",
        " [심층 탐색된 실제 Key 값들 (keyword-based)]"
    ])
    for k, v in report['candidate_info']['deep_found_keys'].items():
        txt_lines.append(f"  - {k} : {v}")
        
    txt_lines.extend([
        "",
        "[진입 0회 원인 분석 후보 (Funnel Bottleneck)]"
    ])
    
    for i, r in enumerate(report["funnel_reasons"], 1):
        txt_lines.append(f" {i}. {r}")
        
    txt_lines.extend([
        "",
        "[Master Dataset 축소 원인 진단 (394k -> 1.5k)]"
    ])
    
    for r in report["master_dataset_reasons"]:
        txt_lines.append(f" - {r}")
        
    txt_lines.extend([
        "",
        "[다음 조치 제안 (Next Steps)]",
        " 1. Threshold 완화: 현재 장세(RANGE)에 맞춰 V2 후보의 진입 조건을 소폭 완화하여 체결을 유도 (과최적화 주의)",
        " 2. Cost Floor 검토: cost_floor를 0.15%~0.20% 수준으로 하향 테스트",
        " 3. Master Dataset 로직 수정: ts가 중복되거나 동일 원문이더라도 버리지 않도록 중복 판별(Key) 로직 개선",
        " 4. 시장 변동성 대기: 임의 수정 없이 변동성(BULL/BEAR) 장세가 올 때까지 모니터링 연장",
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 원본 코드 및 설정 무단 변경 금지",
        " 🚫 live.enabled=false 철저 유지",
        "------------------------------------------------------------"
    ])
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
        
    print("\n[Done] Diagnostics complete.")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
