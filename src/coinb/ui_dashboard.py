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
st.header("1. 시스템 / 엔진 상태")
col1, col2, col3, col4 = st.columns(4)
col1.metric("모드", heartbeat.get("mode", "paper"))
col2.metric("실거래 활성화 여부", str(heartbeat.get("live_enabled", False)))
col3.metric("최근 WS 이벤트 수", heartbeat.get("last_ws_event_count", 0))
col4.metric("반복 횟수", heartbeat.get("loop_count", 0))

col5, col6, col7, col8 = st.columns(4)
col5.metric("엔진 실행 상태", str(heartbeat.get("running", False)))
col6.metric("엔진 상태", engine_status.get("status", "UNKNOWN"))
col7.metric("마지막 성공 단계", engine_status.get("last_success_step", "None"))
if heartbeat.get("last_update"):
    last_updated_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(heartbeat["last_update"]))
else:
    last_updated_str = "N/A"
col8.metric("마지막 갱신 시간", last_updated_str)

if heartbeat.get("last_error"):
    st.error(f"Last Error: {heartbeat['last_error']}")

# Storage Status
with st.expander("저장공간 상태", expanded=False):
    if storage_status:
        scol1, scol2, scol3, scol4 = st.columns(4)
        scol1.metric("WS Raw Size (MB)", storage_status.get("ws_raw_size_mb", 0))
        scol2.metric("Total Logs Size (MB)", storage_status.get("total_logs_size_mb", 0))
        scol3.metric("Retained Raw Files", storage_status.get("retained_raw_files", 0))
        scol4.metric("Compressed Files", storage_status.get("compressed_files", 0))
        st.json(storage_status)
    else:
        st.info("Storage status not available yet.")

# 2. DDM 손실 방어 관리자
st.header("2. DDM 손실 방어 관리자(Drawdown Defense Manager)")
if os.path.exists("reports/ddm_status.json"):
    ddm = load_json("reports/ddm_status.json")
    status = ddm.get("status", "UNKNOWN")
    
    # Status display with color coding
    if status == "NORMAL":
        st.success(f"DDM 상태: 정상")
    elif status == "CAUTION":
        st.warning(f"DDM 상태: 주의")
    elif status == "BLOCK_NEW_ENTRY":
        st.error(f"DDM 상태: 신규 진입 차단 권고")
    elif status == "DATA_ERROR":
        st.error(f"DDM 상태: 데이터 오류")
    else:
        st.info(f"DDM 상태: {status}")

    col_ddm1, col_ddm2, col_ddm3 = st.columns(3)
    col_ddm1.metric("위험 단계", ddm.get("risk_level", 0))
    col_ddm2.metric("신규 진입 차단 여부", str(ddm.get("should_block_new_entry", False)))
    
    gen_at = ddm.get("generated_at", 0)
    gen_at_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(gen_at)) if gen_at else "N/A"
    col_ddm3.write(f"**생성 시간:** {gen_at_str}")

    summary_text = ddm.get('summary', '요약 정보가 없습니다.')
    # Simple summary translation
    if "System is operating normally" in summary_text:
        summary_text = "시스템이 정상적으로 동작 중입니다."
    elif "Caution advised" in summary_text:
        summary_text = "일부 위험 요소로 인해 주의가 필요합니다."
    elif "Should block new entry" in summary_text:
        summary_text = "위험이 감지되어 신규 진입 차단을 권고합니다."
    elif "System state unreliable" in summary_text:
        summary_text = "데이터 또는 설정 오류가 감지되어 시스템 상태를 신뢰할 수 없습니다."
        
    st.write(f"**요약:** {summary_text}")

    # Risk Items
    risk_items = ddm.get("risk_items", [])
    if risk_items:
        st.subheader("위험 항목")
        df_risk = pd.DataFrame(risk_items)
        df_risk = df_risk.rename(columns={
            "code": "코드",
            "severity": "심각도",
            "message": "내용",
            "source": "출처",
            "actual": "실제값",
            "threshold": "기준값"
        })
        st.dataframe(df_risk, use_container_width=True)

    # Recommendations
    recs = ddm.get("recommendations", [])
    if recs:
        st.subheader("권장 조치")
        for rec in recs:
            rec_kr = rec
            if "Review risk items" in rec:
                rec_kr = "위험 항목을 검토하고 config 후보 조정을 검토하세요."
            elif "Continue monitoring" in rec:
                rec_kr = "계속 모니터링하세요."
            elif "Stop new paper entries" in rec:
                rec_kr = "새로운 페이퍼 진입을 중단하세요."
            elif "Fix heartbeat/engine errors" in rec:
                rec_kr = "heartbeat/엔진 오류를 해결하세요."
            st.markdown(f"- {rec_kr}")
else:
    st.warning("DDM not generated yet")

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
