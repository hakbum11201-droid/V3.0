"""
htf_regime_diagnostics.py
Higher Timeframe (HTF) Regime Diagnostics Tool.

Evaluates market conditions using public Upbit API to determine if the
current regime is safe for the Reversal Edge strategy.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

MARKETS = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE", "KRW-ADA"]
CRASH_THRESHOLD = -5.0  # -5% or worse is a crash

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[Warning] API Request failed for {url}: {e}")
        return None

def fetch_tickers(markets):
    url = f"https://api.upbit.com/v1/ticker?markets={','.join(markets)}"
    data = fetch_json(url)
    if not data:
        return {}
    
    results = {}
    for item in data:
        market = item['market']
        # signed_change_rate is float, e.g. 0.05 for 5%, -0.01 for -1%
        change_pct = item['signed_change_rate'] * 100
        results[market] = change_pct
    return results

def fetch_btc_72h():
    url = "https://api.upbit.com/v1/candles/days?market=KRW-BTC&count=4"
    data = fetch_json(url)
    if not data or len(data) < 4:
        return None
    
    current_price = data[0]['trade_price']
    price_72h_ago = data[3]['trade_price']
    
    if price_72h_ago == 0:
        return 0.0
        
    return (current_price / price_72h_ago - 1.0) * 100.0

def determine_regime(btc_24h, btc_72h, up_ratio, down_ratio, crash_ratio):
    if btc_24h is None or btc_72h is None:
        return "UNKNOWN", "CAUTION", "데이터 부족으로 레짐 판별 불가"

    if btc_24h <= CRASH_THRESHOLD or crash_ratio >= 0.5:
        return "CRASH", "BLOCK", "BTC 급락 또는 다수 마켓 동반 급락"
        
    if btc_24h < -1.5 and btc_72h < -3.0 or down_ratio >= 0.6:
        return "BEAR", "RESTRICTED", "BTC 지속 하락세 및 시장 전반 하락 우세"
        
    if btc_24h > 1.0 and btc_72h > 2.0 and up_ratio >= 0.6:
        return "BULL", "ALLOW", "BTC 견조한 상승세 및 시장 전반 상승 우세"
        
    return "RANGE", "ALLOW_PREFERRED", "BTC 변화율이 작고 혼조세인 박스권"

def main():
    start_time = datetime.now()
    
    # 1. Fetch data
    tickers = fetch_tickers(MARKETS)
    btc_72h = fetch_btc_72h()
    
    # 2. Process data
    up_count = 0
    down_count = 0
    crash_count = 0
    total = len(MARKETS)
    
    for m in MARKETS:
        change = tickers.get(m)
        if change is not None:
            if change > 0:
                up_count += 1
            elif change < 0:
                down_count += 1
                
            if change <= CRASH_THRESHOLD:
                crash_count += 1
    
    up_ratio = up_count / total if total > 0 else 0
    down_ratio = down_count / total if total > 0 else 0
    crash_ratio = crash_count / total if total > 0 else 0
    
    btc_24h = tickers.get("KRW-BTC")
    sol_24h = tickers.get("KRW-SOL")
    xrp_24h = tickers.get("KRW-XRP")
    
    # 3. Determine Regime
    regime, permission, reason = determine_regime(
        btc_24h, btc_72h, up_ratio, down_ratio, crash_ratio
    )
    
    # 4. Generate Summary Dictionary
    summary = {
        "generated_at": start_time.isoformat(),
        "btc_change_24h_pct": round(btc_24h, 2) if btc_24h is not None else None,
        "btc_change_72h_pct": round(btc_72h, 2) if btc_72h is not None else None,
        "sol_change_24h_pct": round(sol_24h, 2) if sol_24h is not None else None,
        "xrp_change_24h_pct": round(xrp_24h, 2) if xrp_24h is not None else None,
        "market_up_ratio": round(up_ratio, 2),
        "market_down_ratio": round(down_ratio, 2),
        "crash_ratio": round(crash_ratio, 2),
        "regime": regime,
        "reversal_permission": permission,
        "reason": reason,
        "safety_note": "🚫 실거래 반영 금지. config 자동 반영 금지. 사람 승인 전 tiny_live 금지."
    }
    
    # 5. Output Paths
    out_dir = "reports/experiments"
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "htf_regime_diagnostics_latest.json")
    txt_path = os.path.join(out_dir, "htf_regime_diagnostics_latest.txt")
    
    # Write JSON
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to write JSON summary: {e}")
        
    # Format text report
    txt_lines = [
        "============================================================",
        "  HTF Regime Diagnostics (상위 타임프레임 레짐 진단)",
        "============================================================",
        f"생성 시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "[시장 상태 요약]",
        f" - BTC 24H 변화율: {summary['btc_change_24h_pct']}%" if summary['btc_change_24h_pct'] is not None else " - BTC 24H 변화율: 알 수 없음",
        f" - BTC 72H 변화율: {summary['btc_change_72h_pct']}%" if summary['btc_change_72h_pct'] is not None else " - BTC 72H 변화율: 알 수 없음",
        f" - 대상 마켓 상승 비율: {up_ratio*100:.1f}% ({up_count}/{total})",
        f" - 대상 마켓 하락 비율: {down_ratio*100:.1f}% ({down_count}/{total})",
        f" - 급락(>5%) 마켓 비율: {crash_ratio*100:.1f}% ({crash_count}/{total})",
        "",
        "[관심 마켓 상태]",
        f" - SOL 24H 변화율: {summary['sol_change_24h_pct']}%" if summary['sol_change_24h_pct'] is not None else " - SOL 24H 변화율: 알 수 없음",
        f" - XRP 24H 변화율: {summary['xrp_change_24h_pct']}%" if summary['xrp_change_24h_pct'] is not None else " - XRP 24H 변화율: 알 수 없음",
        "",
        "[최종 진단 결과]",
        f" ▣ 레짐 (Regime)           : {regime}",
        f" ▣ Reversal Edge 허용 여부 : {permission}",
        f" ▣ 판단 근거               : {reason}",
        "",
        "------------------------------------------------------------",
        " [안전 경고 및 금지 사항]",
        " 🚫 본 진단은 참고용이며 자동 실거래 반영을 금지합니다.",
        " 🚫 config 자동 반영 금지",
        " 🚫 live.enabled=false 유지",
        " 🚫 사람 승인 전 tiny_live 금지",
        "------------------------------------------------------------"
    ]
    
    # Write TXT
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines) + "\n")
    except Exception as e:
        print(f"Failed to write TXT summary: {e}")
        
    print(f"HTF Regime Diagnostics completed: {regime} -> {permission}")
    print(f"Report saved to: {txt_path}")

if __name__ == "__main__":
    main()
