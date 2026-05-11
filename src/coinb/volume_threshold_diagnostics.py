import json
import os
import argparse
from datetime import datetime
from collections import deque, defaultdict
from . import report_io

def calculate_percentiles(values):
    if not values: return {k: 0 for k in ["count", "mean", "p50", "p75", "p90", "p95", "p99", "max"]}
    s_v = sorted(values); n = len(s_v)
    def get_p(p): return s_v[min(int(n * p / 100), n - 1)]
    return {"count": n, "mean": sum(values) / n, "p50": get_p(50), "p75": get_p(75), "p90": get_p(90), "p95": get_p(95), "p99": get_p(99), "max": s_v[-1]}

def run_diagnostics(ws_path, output_json, output_txt):
    if not os.path.exists(ws_path): return {"ok": False}
    t_m = defaultdict(list)
    with open(ws_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get("event_type") == "trade":
                    r = d.get("raw", {})
                    ts = r.get("trade_timestamp")
                    if ts: t_m[d["market"]].append({"ts": ts/1000.0, "value": r.get("trade_price",0)*r.get("trade_volume",0), "is_buy": (r.get("ask_bid") or r.get("side")) == "BID"})
            except: continue

    m_stats, a3, a10 = {}, [], []
    th = {"conservative": 3000000, "moderate": 1500000, "aggressive": 750000}
    for m, trades in t_m.items():
        trades.sort(key=lambda x: x["ts"])
        v3, v10 = [], []
        w3, w10 = deque(), deque()
        s3, s10 = 0.0, 0.0
        for tr in trades:
            if tr["is_buy"]:
                w3.append((tr["ts"], tr["value"])); s3 += tr["value"]
                w10.append((tr["ts"], tr["value"])); s10 += tr["value"]
            while w3 and w3[0][0] < tr["ts"] - 3: s3 -= w3.popleft()[1]
            while w10 and w10[0][0] < tr["ts"] - 10: s10 -= w10.popleft()[1]
            c3, c10 = max(0, s3), max(0, s10)
            v3.append(c3); v10.append(c10); a3.append(c3); a10.append(c10)
        
        def rates(v): return {k: sum(1 for x in v if x >= t)/len(v)*100 if v else 0 for k, t in th.items()}
        m_stats[m] = {"buy_trade_value_3s": calculate_percentiles(v3), "pass_rates_3s": rates(v3)}

    full_report = {"ok": True, "generated_at": datetime.now().isoformat(), "thresholds": th, "global": {"buy_trade_value_3s": calculate_percentiles(a3), "pass_rates_3s": {k: sum(1 for x in a3 if x >= t)/len(a3)*100 if a3 else 0 for k, t in th.items()}}, "markets": m_stats}
    report_io.write_json_report(output_json, full_report)

    lines = []
    lines.append("=== 체결대금 임계값 진단 리포트 ===")
    lines.append(f"분석 일시: {full_report['generated_at']} | 대상 로그: {ws_path}\n")
    g3 = full_report["global"]["buy_trade_value_3s"]
    lines.append(f"--- 3초 Buy Value 분포 (통합) ---")
    lines.append(f"샘플 수: {g3['count']} | 평균: {g3['mean']:,.0f} | P50: {g3['p50']:,.0f} | P90: {g3['p90']:,.0f}\n")
    pr3 = full_report["global"]["pass_rates_3s"]
    lines.append(f"--- 임계값별 통과율 ---")
    for k, v in pr3.items(): lines.append(f"- {k.capitalize()} ({th[k]:,}): {v:.2f}%")
    lines.append("\n(본 리포트는 진단용이며 설정 변경은 수동 검토 후 진행하십시오.)")
    report_io.write_text_report(output_txt, "\n".join(lines))
    return full_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ws", required=True); parser.add_argument("--output-json", required=True); parser.add_argument("--output-txt", required=True)
    args = parser.parse_args(); run_diagnostics(args.ws, args.output_json, args.output_txt)
