import json
import os
import time

import pandas as pd
import streamlit as st

st.set_page_config(page_title="coinB PRO V3.1 Dashboard", layout="wide")

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_text(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return "File not found."

def load_jsonl(filepath, max_lines=100):
    lines_data = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-max_lines:]:
                if line.strip():
                    lines_data.append(json.loads(line))
    return lines_data

# Data loading
config = load_json("config/config.json")
micro = load_json("reports/microstructure_snapshot.json")
loss_analysis = load_json("reports/orderflow_loss_analysis.json")
paper_review = load_text("reports/paper_review_latest.txt")
config_candidates = load_text("reports/orderflow_config_candidates.txt")
decisions = load_jsonl("logs/orderflow_paper_decisions.jsonl", 100)
trades = load_jsonl("logs/orderflow_paper_trades.jsonl", 100)

heartbeat = load_json("runtime/heartbeat.json")
engine_status = load_json("runtime/engine_status.json")
storage_status = load_json("reports/storage_status.json")

st.title("coinB PRO V3.1 Dashboard")

# 1. 상단 상태바
st.header("1. System & Engine Status")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Mode", heartbeat.get("mode", "paper"))
col2.metric("Live Enabled", str(heartbeat.get("live_enabled", False)))
col3.metric("Last WS Event Count", heartbeat.get("last_ws_event_count", 0))
col4.metric("Loop Count", heartbeat.get("loop_count", 0))

col5, col6, col7, col8 = st.columns(4)
col5.metric("Engine Running", str(heartbeat.get("running", False)))
col6.metric("Engine Status", engine_status.get("status", "UNKNOWN"))
col7.metric("Last Success Step", engine_status.get("last_success_step", "None"))
if heartbeat.get("last_update"):
    last_updated_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(heartbeat["last_update"]))
else:
    last_updated_str = "N/A"
col8.metric("Last Update", last_updated_str)

if heartbeat.get("last_error"):
    st.error(f"Last Error: {heartbeat['last_error']}")

# Storage Status
with st.expander("Storage Status", expanded=False):
    if storage_status:
        scol1, scol2, scol3, scol4 = st.columns(4)
        scol1.metric("WS Raw Size (MB)", storage_status.get("ws_raw_size_mb", 0))
        scol2.metric("Total Logs Size (MB)", storage_status.get("total_logs_size_mb", 0))
        scol3.metric("Retained Raw Files", storage_status.get("retained_raw_files", 0))
        scol4.metric("Compressed Files", storage_status.get("compressed_files", 0))
        st.json(storage_status)
    else:
        st.info("Storage status not available yet.")

# 2. DDM 영역
st.header("2. DDM (Drawdown Defense Manager)")
if os.path.exists("reports/ddm_status.json"):
    ddm = load_json("reports/ddm_status.json")
    st.json(ddm)
else:
    st.warning("Not implemented yet")

# 3. 마켓 보드
st.header("3. Market Board")
features_by_market = micro.get("features", {})
if features_by_market:
    market_data = []
    for mkt, f in features_by_market.items():
        market_data.append({
            "Market": mkt,
            "Price": f.get("last_trade_price", 0),
            "Spread(%)": round(f.get("spread_pct", 0), 4),
            "Buy Value(3s)": round(f.get("buy_trade_value_3s", 0), 2),
            "Sell Value(3s)": round(f.get("sell_trade_value_3s", 0), 2),
            "Depth Ratio(5)": round(f.get("bid_ask_depth_ratio_5", 0), 2),
            "OFI": round(f.get("ofi_score", 0), 2),
            "Sweep": round(f.get("sweep_score", 0), 2),
            "Absorption": round(f.get("absorption_score", 0), 2),
            "Continuation": round(f.get("continuation_score", 0), 2)
        })
    st.dataframe(pd.DataFrame(market_data), use_container_width=True)
else:
    st.info("No market data available.")

# 4. Paper 성과판 & Rejection Reason
st.header("4. Paper Performance & Rejections")
col1, col2 = st.columns([1, 2])
with col1:
    summary = loss_analysis.get("summary", {})
    st.subheader("Performance summary")
    st.json(summary)

with col2:
    st.subheader("Top Rejection Reasons")
    reason_summary = loss_analysis.get("reason_summary", {})
    if reason_summary:
        r_list = []
        for key, val in reason_summary.items():
            r_list.append({
                "Reason": val.get("reason"),
                "Count": val.get("count"),
                "Action": val.get("action")
            })
        st.dataframe(pd.DataFrame(r_list).sort_values("Count", ascending=False), use_container_width=True)
    else:
        st.info("No rejections recorded.")

# 5. 최근 판단 로그
st.header("5. Recent Decisions (Top 100)")
if decisions:
    dec_df = pd.DataFrame(decisions)
    if "timestamp" in dec_df.columns:
        dec_df["timestamp"] = pd.to_datetime(dec_df["timestamp"], unit="s")
    # Simplify diagnostic for display
    if "diagnostic" in dec_df.columns:
        dec_df["diagnostic"] = dec_df["diagnostic"].apply(lambda x: str(x) if isinstance(x, dict) else x)
    if "virtual_fill_result" in dec_df.columns:
        dec_df["virtual_fill_result"] = dec_df["virtual_fill_result"].apply(lambda x: str(x) if isinstance(x, dict) else x)
    if "details" in dec_df.columns:
        dec_df = dec_df.drop(columns=["details"])
    st.dataframe(dec_df.iloc[::-1].head(100), use_container_width=True) # Reverse to show latest first
else:
    st.info("No decisions recorded.")

# 6. 리포트 표시
st.header("6. Reports")
tab1, tab2 = st.tabs(["Paper Review", "Config Candidates"])
with tab1:
    st.text_area("Paper Review Latest", paper_review, height=400)
with tab2:
    st.text_area("Config Candidates", config_candidates, height=400)
