"""
ui_dashboard.py – coinB Control Center | Reversal Edge v2 Paper Monitor
Phase 1: read-only monitoring UI
"""
import json
import os
import time
from collections import Counter

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="coinB Control Center",
    page_icon="🎛️",
    layout="wide",
)

# ── 기본 경로 ──────────────────────────────────────────────────────────────────
_V3_ROOT = r"C:\Users\hakbu\Downloads\coinB_PRO_V3_0_FINAL_ROOT_READY_v3_0\V3.0"
DEFAULT_EVENTS  = os.path.join(_V3_ROOT, r"logs\paper\reversal_edge_v2_paper_24h_events.jsonl")
DEFAULT_TRADES  = os.path.join(_V3_ROOT, r"logs\paper\reversal_edge_v2_paper_24h_trades.jsonl")
DEFAULT_REPORTS = os.path.join(_V3_ROOT, r"reports\paper")

# ── 유틸 ──────────────────────────────────────────────────────────────────────

def load_json(fp):
    if fp and os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_text(fp):
    if fp and os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            return f.read()
    return "File not found."

def load_jsonl_tail(fp, max_lines=100, tail_bytes=1_048_576):
    """seek 방식 tail – readlines() 전체 로드 없음."""
    result = []
    if not fp or not os.path.exists(fp):
        return result
    try:
        size = os.path.getsize(fp)
        rsize = min(tail_bytes, size)
        with open(fp, "rb") as f:
            f.seek(-rsize, 2)
            raw = f.read(rsize)
        text = raw.decode("utf-8", errors="replace")
        if rsize < size:
            idx = text.find("\n")
            if idx != -1:
                text = text[idx + 1:]
        for line in text.splitlines()[-max_lines:]:
            line = line.strip()
            if line:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return result

def file_stat(fp):
    if fp and os.path.exists(fp):
        s = os.stat(fp)
        elapsed = time.time() - s.st_mtime
        return s.st_size, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.st_mtime)), elapsed
    return None, None, None

def count_lines(fp):
    if not fp or not os.path.exists(fp):
        return 0
    c = 0
    try:
        with open(fp, "rb") as f:
            for _ in f:
                c += 1
    except Exception:
        pass
    return c

def find_summary_files(reports_dir):
    """reports_dir 에서 paper summary 파일을 패턴 기준으로 탐색, mtime 내림차순 반환."""
    import fnmatch
    patterns = [
        "reversal_edge_v2_paper_24h_summary.json",
        "reversal_edge_v2_paper_24h_summary.txt",
        "reversal_edge_v2_paper_run_summary_*.json",
        "reversal_edge_v2_paper_run_summary_*.txt",
    ]
    found = []
    if not reports_dir or not os.path.isdir(reports_dir):
        return found
    try:
        for fname in os.listdir(reports_dir):
            for pat in patterns:
                if fnmatch.fnmatch(fname, pat):
                    fpath = os.path.join(reports_dir, fname)
                    found.append((os.path.getmtime(fpath), fpath, fname))
                    break
    except Exception:
        pass
    found.sort(reverse=True)
    return found

def load_text_tail(fp, max_bytes=65536):
    """텍스트 파일 끝부분 max_bytes만 읽기 (대용량 방지)."""
    if not fp or not os.path.exists(fp):
        return "파일 없음"
    try:
        size = os.path.getsize(fp)
        with open(fp, "rb") as f:
            f.seek(-min(max_bytes, size), 2)
            raw = f.read()
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        return f"읽기 오류: {e}"

def promotion_check(summary_data, trades_cnt):
    """보수적 규칙 기반 Promotion 판정 반환 (판정문, 색상, 다음 행동)."""
    if not summary_data:
        return "⏳ 검증 진행 중", "info", "24H Paper Runner가 완료될 때까지 대기하세요."
    if trades_cnt == 0:
        return "⚠️ 데이터 부족 — 조건 미발생", "warning", "24H 추가 관찰 또는 진입 조건 검토를 권장합니다."

    net_pnl = summary_data.get("avg_net_pnl_pct", None)
    win_rate = summary_data.get("win_rate", None)
    sl_cnt   = summary_data.get("sl_count", 0)
    entries  = summary_data.get("paper_entries", trades_cnt)

    sl_ratio = sl_cnt / entries if entries > 0 else 0
    if sl_ratio > 0.6:
        return "🚨 주의 — 리스크 조건 재검토 필요", "error", "SL 비율이 너무 높습니다. SL/진입 조건을 재검토하세요."
    if net_pnl is None:
        return "❓ Net PnL 데이터 없음", "warning", "summary 파일에서 avg_net_pnl_pct를 찾을 수 없습니다."
    if net_pnl < 0:
        return "🔴 보류 — 실패 조건 분석 필요", "error", "Net PnL 음수입니다. 실패 거래 분석(loss-analysis)으로 이동하세요."
    if entries < 5:
        return "🟡 데이터 부족 — 추가 Paper 필요", "warning", "거래 수가 적습니다. 24H~72H 추가 Paper 검증을 권장합니다."
    return "🟢 유망 — 추가 Paper 검증 필요", "success", "Net PnL 양수이며 거래 수가 충분합니다. 3일 Paper 검증을 검토하세요."

def next_action_guide(summary_data, trades_cnt):
    """다음 행동 안내 문구 반환."""
    if not summary_data or trades_cnt == 0:
        return "📌 24H 추가 관찰 또는 진입 조건 완화 검토"
    sl_cnt  = summary_data.get("sl_count", 0)
    entries = summary_data.get("paper_entries", trades_cnt)
    net_pnl = summary_data.get("avg_net_pnl_pct", None)
    sl_ratio = sl_cnt / entries if entries > 0 else 0
    if sl_ratio > 0.6:
        return "📌 SL 조건 및 진입 임계값 재검토"
    if net_pnl is not None and net_pnl < 0:
        return "📌 실패 거래 분석(loss-analysis) 실행 → 실패 패턴 파악"
    if entries < 5:
        return "📌 데이터 부족 → 24H~72H 추가 Paper 실행"
    if entries >= 10 and net_pnl is not None and net_pnl > 0:
        return "📌 3일 Paper 검증 → 결과 재검토 후 승격 검토"
    return "📌 추가 Paper 데이터 축적 후 재판정"

def get_runner_procs():
    procs = []
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                if "python" in (p.info.get("name") or "").lower() or "python" in cmd.lower():
                    if "reversal" in cmd.lower():
                        procs.append({
                            "PID": p.info["pid"],
                            "Process": p.info.get("name", ""),
                            "Command Summary": cmd[:80] + ("..." if len(cmd) > 80 else ""),
                            "_full_cmd": cmd,
                        })
            except Exception:
                pass
    except ImportError:
        pass
    return procs

def _fmt_sec(sec):
    """초 값을 '1h 07m' 형태의 사람 친화적 문자열로 변환."""
    if sec is None:
        return "–"
    sec = int(sec)
    h, m = divmod(sec, 3600)
    m = m // 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"

# ── 사이드바 ──────────────────────────────────────────────────────────────────
st.sidebar.title("🎛️ coinB Control Center")
auto_refresh = st.sidebar.checkbox("30초 자동 새로고침", value=False)
tail_lines   = st.sidebar.slider("tail 줄 수", 20, 500, 100, 10)
with st.sidebar.expander("🗂️ 고급 경로 설정", expanded=False):
    events_path = st.text_input("events.jsonl", value=DEFAULT_EVENTS, key="ev_path")
    trades_path = st.text_input("trades.jsonl", value=DEFAULT_TRADES, key="tr_path")
    reports_dir = st.text_input("reports 폴더", value=DEFAULT_REPORTS, key="rp_dir")
    st.caption("절대 또는 실행 디렉토리 기준 상대 경로")
if "ev_path" not in st.session_state:
    events_path = DEFAULT_EVENTS
    trades_path = DEFAULT_TRADES
    reports_dir = DEFAULT_REPORTS

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
ev_size, ev_mtime, ev_elapsed = file_stat(events_path)
tr_size, tr_mtime, tr_elapsed = file_stat(trades_path)
tr_lines   = count_lines(trades_path)
events_tail = load_jsonl_tail(events_path, tail_lines)
trades_tail = load_jsonl_tail(trades_path, 200)

hb_events = [e for e in events_tail if e.get("event_type") == "heartbeat"]
last_hb   = hb_events[-1] if hb_events else {}

procs = get_runner_procs()
runner_status   = "RUNNING" if procs else "STOPPED"
runner_status_d = "정상 실행 중 🟢" if procs else "실행 없음 ⚫"

ev_ok = ev_elapsed is not None and ev_elapsed < 120
ev_status_txt = "정상 ✅" if ev_ok else ("주의 ⚠️" if ev_elapsed is not None else "파일 없음 ❌")

# 레거시 데이터 (기존 기능 유지)
heartbeat     = load_json("runtime/heartbeat.json")
engine_status = load_json("runtime/engine_status.json")
storage_status= load_json("reports/storage_status.json")
perf          = load_json("reports/paper_performance.json")
perf_summary  = load_text("reports/paper_performance_summary.txt")
equity_curve  = load_jsonl_tail("logs/paper_equity_curve.jsonl", 1000)
decisions     = load_jsonl_tail("logs/orderflow_paper_decisions.jsonl", 100)
micro         = load_json("reports/microstructure_snapshot.json")
loss_analysis = load_json("reports/orderflow_loss_analysis.json")
paper_review  = load_text("reports/paper_review_latest.txt")
config_cands  = load_text("reports/orderflow_config_candidates.txt")

# ══════════════════════════════════════════════════════════════════════════════
# 제목
# ══════════════════════════════════════════════════════════════════════════════
st.title("🎛️ coinB Control Center")
st.caption("Reversal Edge v2 Paper Monitor  |  Read-Only Monitoring  |  Paper Mode Only")

# ══════════════════════════════════════════════════════════════════════════════
# 상단 핵심 카드 (7개)
# ══════════════════════════════════════════════════════════════════════════════
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)

c1.metric("🚦 Runner Status", runner_status, runner_status_d)
c2.metric("🔵 Mode", "PAPER")
c3.metric("🔴 Live Trading", "OFF ✅")
c4.metric("📊 Paper Trades", tr_lines if tr_lines else "0")

if ev_elapsed is not None:
    if ev_elapsed < 60:
        last_upd = f"{int(ev_elapsed)}s 전"
    elif ev_elapsed < 3600:
        last_upd = f"{int(ev_elapsed/60)}m 전"
    else:
        last_upd = f"{ev_elapsed/3600:.1f}h 전"
else:
    last_upd = "파일 없음"
c5.metric("⏱️ Last Update", last_upd)

# Remaining Time – heartbeat remaining_sec 기반
rem_sec = last_hb.get("remaining_sec") if last_hb else None
if rem_sec is not None:
    if rem_sec < 60:
        rem_txt = f"{int(rem_sec)}s"
    elif rem_sec < 3600:
        rem_txt = f"{int(rem_sec/60)}m"
    else:
        rem_txt = f"{rem_sec/3600:.1f}h"
else:
    rem_txt = "–"
c6.metric("⏳ Remaining", rem_txt)
c7.metric("🧪 Candidate", "TESTING 🟡")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Candidate Snapshot + Why Card  (2열)
# ══════════════════════════════════════════════════════════════════════════════
snap_col, why_col = st.columns(2)

with snap_col:
    st.subheader("📋 Candidate Snapshot")
    st.markdown("""
| 항목 | 값 |
|------|-----|
| Strategy | Reversal Edge v2 |
| Candidate | reversal_edge_candidate_v2_from_36h.json |
| Mode | STATIC_SOL_ONLY |
| Market | KRW-SOL |
| TP | 0.4% |
| SL | -0.1% |
| Timeout | 300s |
| Cost Floor | 0.20% |
| Stage | **24H Paper Test** |
| Status | 🟡 **TESTING** |
""")
    st.caption("🟡 TESTING = Paper 검증 중 | 실거래 불가 | 자동 config 반영 없음")

with why_col:
    st.subheader("❓ Why Card – 진입 대기 사유")
    if tr_lines == 0:
        st.info("ℹ️ 현재 상태: **정상 대기** – 전략 조건 미충족 중입니다. 오류가 아닙니다.")
        st.markdown(f"""
- **이유**: Reversal Score 기준 미충족 또는 현재 진입 조건 없음
- **events 수집**: {ev_status_txt}
- **trades**: 0건 (정상 대기 상태)
- **position**: 없음
- **의미**: 시스템이 쉬는 게 아니라 진입 기준을 충족할 때까지 안전하게 기다리는 중입니다.
""")
        st.caption("trades 파일은 아직 거래가 없어 갱신되지 않았습니다. events가 갱신 중이면 정상입니다.")
        if last_hb:
            st.markdown(f"- **Run Elapsed**: {_fmt_sec(last_hb.get('elapsed_sec'))}")
            st.markdown(f"- **Run Remaining**: {_fmt_sec(last_hb.get('remaining_sec'))}")
    else:
        st.success(f"✅ 거래 발생: {tr_lines}건")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# HTF Regime Diagnostics Card
# ══════════════════════════════════════════════════════════════════════════════
_HTF_JSON = "reports/experiments/htf_regime_diagnostics_latest.json"
_REGIME_COLOR = {
    "BULL":    "success",
    "RANGE":   "info",
    "BEAR":    "warning",
    "CRASH":   "error",
    "UNKNOWN": "warning",
}
_PERM_COLOR = {
    "ALLOW":             "success",
    "ALLOW_PREFERRED":   "info",
    "RESTRICTED":        "warning",
    "BLOCK":             "error",
    "CAUTION":           "warning",
}

with st.expander("📡 HTF Regime Diagnostics", expanded=True):
    if not os.path.exists(_HTF_JSON):
        st.info("HTF Regime 결과가 아직 없습니다. RUN_HTF_REGIME_DIAGNOSTICS.bat 실행 후 표시됩니다.")
    else:
        try:
            _htf = load_json(_HTF_JSON)
            _regime   = _htf.get("regime", "UNKNOWN")
            _perm     = _htf.get("reversal_permission", "CAUTION")
            _rc       = _REGIME_COLOR.get(_regime, "warning")
            _pc       = _PERM_COLOR.get(_perm, "warning")

            _h1, _h2 = st.columns(2)
            with _h1:
                if _rc == "success":  st.success(f"**HTF Regime: {_regime}**")
                elif _rc == "error":  st.error(f"**HTF Regime: {_regime}**")
                elif _rc == "info":   st.info(f"**HTF Regime: {_regime}**")
                else:                 st.warning(f"**HTF Regime: {_regime}**")
            with _h2:
                if _pc == "success":  st.success(f"**Reversal Permission: {_perm}**")
                elif _pc == "error":  st.error(f"**Reversal Permission: {_perm}**")
                elif _pc == "info":   st.info(f"**Reversal Permission: {_perm}**")
                else:                 st.warning(f"**Reversal Permission: {_perm}**")

            _mc1, _mc2, _mc3, _mc4 = st.columns(4)
            def _fmtpct(v): return f"{v:+.2f}%" if v is not None else "N/A"
            _mc1.metric("BTC 24H",   _fmtpct(_htf.get("btc_change_24h_pct")))
            _mc2.metric("BTC 72H",   _fmtpct(_htf.get("btc_change_72h_pct")))
            _mc3.metric("SOL 24H",   _fmtpct(_htf.get("sol_change_24h_pct")))
            _mc4.metric("XRP 24H",   _fmtpct(_htf.get("xrp_change_24h_pct")))

            _mc5, _mc6, _mc7 = st.columns(3)
            _mc5.metric("Market Up",   f"{_htf.get('market_up_ratio',0)*100:.0f}%")
            _mc6.metric("Market Down", f"{_htf.get('market_down_ratio',0)*100:.0f}%")
            _mc7.metric("Crash Ratio", f"{_htf.get('crash_ratio',0)*100:.0f}%")

            st.caption(f"판단 근거: {_htf.get('reason', '–')}")
        except Exception as _ex:
            st.warning(f"HTF Regime JSON 읽기 오류: {_ex}")
    st.caption("HTF Regime 결과는 참고용입니다. 실거래 반영 금지. config 자동 수정 금지. 사람 승인 전 tiny_live 금지.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Auto Research Report Card
# ══════════════════════════════════════════════════════════════════════════════
_ARR_JSON = "reports/experiments/auto_research_report_latest.json"
_ARR_ACTION_COLOR = {
    "WAIT_FOR_PAPER_RESULT":             "info",
    "NEED_MORE_DATA":                    "warning",
    "NEED_MORE_PAPER_OR_CONDITION_REVIEW": "warning",
    "PROMISING_RUN_3D_PAPER":            "success",
    "HOLD_AND_ANALYZE_FAILURES":         "error",
    "RISK_REVIEW_REQUIRED":              "error",
    "RUN_MORE_OOS_CHUNKS":               "warning",
    "CONTINUE_MONITORING":               "info",
}

with st.expander("🧭 Auto Research Report", expanded=True):
    if not os.path.exists(_ARR_JSON):
        st.info("Auto Research Report 결과가 아직 없습니다. RUN_AUTO_RESEARCH_REPORT.bat 실행 후 표시됩니다.")
    else:
        try:
            _arr = load_json(_ARR_JSON)
            _j   = _arr.get("judgement", {})
            _act = _j.get("action", "UNKNOWN")
            _rsn = _j.get("reason", "–")
            _ac  = _ARR_ACTION_COLOR.get(_act, "warning")

            # Action banner
            if _ac == "success":   st.success(f"🎯 ACTION: **{_act}**")
            elif _ac == "error":   st.error(f"🎯 ACTION: **{_act}**")
            elif _ac == "info":    st.info(f"🎯 ACTION: **{_act}**")
            else:                  st.warning(f"🎯 ACTION: **{_act}**")
            st.caption(f"판단 근거: {_rsn}")

            # Key metrics
            _ps = _arr.get("summary", {}).get("paper", {})
            _os = _arr.get("summary", {}).get("oos", {})
            _trades = _ps.get("paper_entries", _ps.get("total_trades", 0))
            _netpnl = _ps.get("avg_net_pnl_pct", _ps.get("net_pnl_pct", None))
            _wr     = _ps.get("win_rate", None)
            _oos_j  = _os.get("final_judgement", "–")

            _a1, _a2, _a3, _a4 = st.columns(4)
            _a1.metric("Paper Trades",  _trades)
            _a2.metric("Net PnL (%)",   f"{_netpnl:.4f}" if _netpnl is not None else "–")
            _a3.metric("Win Rate (%)",   f"{_wr:.2f}" if _wr is not None else "–")
            _a4.metric("OOS Judgement", str(_oos_j)[:20] if _oos_j else "–")
        except Exception as _ex:
            st.warning(f"Auto Research Report JSON 읽기 오류: {_ex}")
    st.caption("🚫 이 리포트는 실거래 승인이 아닙니다. live.enabled=false 유지. 사람 승인 전 tiny_live 금지.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Research Validation Results Card
# ══════════════════════════════════════════════════════════════════════════════
_VALID_GOOD   = {"HEALTHY", "ROBUST_TO_COST", "PROMISING_BUT_MORE_DATA_REQUIRED", "SURVIVES_COST", "ROBUST"}
_VALID_WARN   = {"NEED_MORE_DATA", "FRAGILE_EDGE", "POSSIBLE_DEGRADATION", "WEAK_SIGNAL", "UNSTABLE", "SURVIVES_BASE_ONLY"}
_VALID_BAD    = {"DEGRADED", "RISK_DEGRADED", "FAILED", "FAILS_COST"}

def _render_verdict(label):
    """Render a coloured badge based on judgement value."""
    if label in _VALID_GOOD:   st.success(f"**{label}**")
    elif label in _VALID_BAD:  st.error(f"**{label}**")
    else:                      st.warning(f"**{label}**")

with st.expander("📊 Research Validation Results", expanded=True):
    _rv1, _rv2, _rv3 = st.columns(3)

    # ── Walk-forward Validation
    _WFV_JSON = "reports/experiments/walk_forward_validation_latest.json"
    with _rv1:
        st.markdown("**🔄 Walk-forward Validation**")
        if not os.path.exists(_WFV_JSON):
            st.info("아직 결과가 없습니다. RUN_WALK_FORWARD_VALIDATION.bat 실행 후 표시됩니다.")
        else:
            try:
                _wfv = load_json(_WFV_JSON)
                _wfv_j = _wfv.get("final_judgement", "UNKNOWN")
                _render_verdict(_wfv_j)
                st.metric("Folds", _wfv.get("total_folds", 0))
                st.metric("PASS", _wfv.get("pass_count", 0))
                st.metric("FAIL", _wfv.get("fail_count", 0))
                st.metric("No Data", _wfv.get("need_more_data_count", 0))
                _wfv_pnl = _wfv.get("avg_net_pnl_pct", None)
                st.metric("Avg Net PnL", f"{_wfv_pnl:+.4f}%" if _wfv_pnl is not None else "–")
                st.metric("Total Trades", _wfv.get("total_trades", 0))
            except Exception as _ex:
                st.warning(f"WFV JSON 오류: {_ex}")

    # ── Cost Randomization Test
    _CRT_JSON = "reports/experiments/cost_randomization_test_latest.json"
    with _rv2:
        st.markdown("**💰 Cost Randomization Test**")
        if not os.path.exists(_CRT_JSON):
            st.info("아직 결과가 없습니다. RUN_COST_RANDOMIZATION_TEST.bat 실행 후 표시됩니다.")
        else:
            try:
                _crt = load_json(_CRT_JSON)
                _crt_j = _crt.get("final_judgement", "UNKNOWN")
                _render_verdict(_crt_j)
                scenarios = _crt.get("scenarios", [])
                survived = [s for s in scenarios if s.get("judgement") in ("SURVIVES_COST", "ROBUST")]
                worst_cost = max((s["cost_pct"] for s in survived), default=None)
                base_pnl = next((s.get("original_avg_net_pnl_pct") for s in scenarios if s.get("cost_pct") == 0.20), None)
                worst_adj = min((s.get("adjusted_avg_net_pnl_pct", 0) for s in scenarios), default=None)
                st.metric("Base Trades", _crt.get("base_trades", 0))
                st.metric("Base Cost", f"{_crt.get('base_cost_pct', 0.20):.2f}%" if "base_cost_pct" not in _crt else f"{_crt.get('base_cost_pct', 0.20):.2f}%")
                st.metric("Max Survived Cost", f"{worst_cost:.2f}%" if worst_cost is not None else "–")
                st.metric("Base Net PnL", f"{base_pnl:+.4f}%" if base_pnl is not None else "–")
                st.metric("Worst Adj PnL", f"{worst_adj:+.4f}%" if worst_adj is not None else "–")
            except Exception as _ex:
                st.warning(f"CRT JSON 오류: {_ex}")

    # ── Strategy Degradation Tracking
    _SDT_JSON = "reports/experiments/strategy_degradation_tracking_latest.json"
    with _rv3:
        st.markdown("**📉 Strategy Degradation Tracking**")
        if not os.path.exists(_SDT_JSON):
            st.info("아직 결과가 없습니다. RUN_STRATEGY_DEGRADATION_TRACKING.bat 실행 후 표시됩니다.")
        else:
            try:
                _sdt = load_json(_SDT_JSON)
                _sdt_j = _sdt.get("judgement", "UNKNOWN")
                _render_verdict(_sdt_j)
                _m = _sdt.get("metrics", {})
                st.metric("Total Trades", _m.get("total_trades", 0))
                _r10p = _m.get("recent_10_avg_net_pnl")
                _r30p = _m.get("recent_30_avg_net_pnl")
                _r10w = _m.get("recent_10_win_rate")
                _r30w = _m.get("recent_30_win_rate")
                st.metric("Recent 10 PnL", f"{_r10p:+.4f}%" if _r10p is not None else "–")
                st.metric("Recent 30 PnL", f"{_r30p:+.4f}%" if _r30p is not None else "–")
                st.metric("Recent 10 WR", f"{_r10w:.2f}%" if _r10w is not None else "–")
                st.metric("Recent 30 WR", f"{_r30w:.2f}%" if _r30w is not None else "–")
                sl_r = _m.get("sl_ratio")
                to_r = _m.get("timeout_ratio")
                st.metric("SL Ratio", f"{sl_r*100:.1f}%" if sl_r is not None else "–")
                st.metric("Timeout Ratio", f"{to_r*100:.1f}%" if to_r is not None else "–")
            except Exception as _ex:
                st.warning(f"SDT JSON 오류: {_ex}")

    st.caption("🚫 이 검증 결과는 실거래 승인이 아닙니다. live.enabled=false 유지. 사람 승인 전 tiny_live 금지.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Runner Process
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔍 Runner 프로세스 감지", expanded=bool(procs)):
    if procs:
        st.success(f"✅ reversal-edge-paper-runner 실행 중 ({len(procs)}개)")
        # 요약 표 (full cmd 제외)
        display_cols = ["PID", "Process", "Command Summary"]
        df_procs = pd.DataFrame(procs)[display_cols]
        st.dataframe(df_procs, use_container_width=True)
        # 전체 명령어는 expander로 접기
        for row in procs:
            with st.expander(f"PID {row['PID']} – Full Command", expanded=False):
                st.code(row["_full_cmd"], language="bash")
    else:
        try:
            import psutil  # noqa: F401
            st.warning("⚠️ reversal-edge-paper-runner 프로세스 없음 (STOPPED)")
        except ImportError:
            st.info("ℹ️ psutil 미설치 – 프로세스 감지 불가 (`pip install psutil`)")
    st.caption("▶ Run / ■ Stop 버튼은 Phase 2에서 구현 예정 (현재 비활성)")
    bc1, bc2, bc3 = st.columns(3)
    bc1.button("▶ Run Paper 6H", disabled=True)
    bc2.button("▶ Run Paper 24H", disabled=True)
    bc3.button("■ Stop Runner", disabled=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# 탭 구조
# ══════════════════════════════════════════════════════════════════════════════
tab_trades, tab_events, tab_reports, tab_safety, tab_legacy = st.tabs([
    "📈 Trades", "📡 Events", "📄 Reports", "🔒 Safety", "🗂️ 기존 대시보드"
])

# ── Trades 탭 ─────────────────────────────────────────────────────────────────
with tab_trades:
    st.header("📈 Paper Trades")
    t1, t2, t3 = st.columns(3)
    t1.metric("파일 크기 (bytes)", f"{tr_size:,}" if tr_size is not None else "없음")
    t2.metric("라인 수 (거래 수)", tr_lines)
    t3.metric("마지막 수정", tr_mtime or "없음")

    if tr_size is None:
        st.error(f"파일 없음: {trades_path}")
    elif tr_size == 0:
        st.warning("⚠️ 아직 거래 없음. 오류가 아니라 조건 미발생일 수 있습니다.")
    else:
        if trades_tail:
            df_tr = pd.DataFrame(trades_tail)
            for col in ["entry_ts", "exit_ts"]:
                if col in df_tr.columns:
                    df_tr[col] = pd.to_datetime(df_tr[col], unit="s", errors="coerce")
            st.subheader("최근 거래 (최대 10건)")
            st.dataframe(df_tr.iloc[::-1].head(10), use_container_width=True)

            # TP/SL/Timeout 통계
            if "exit_type" in df_tr.columns:
                st.subheader("청산 유형별 통계")
                cnt = df_tr["exit_type"].value_counts().reset_index()
                cnt.columns = ["청산 유형", "횟수"]
                st.dataframe(cnt, use_container_width=True)
        else:
            st.info("trades 데이터를 파싱할 수 없습니다.")

# ── Events 탭 ─────────────────────────────────────────────────────────────────
with tab_events:
    st.header("📡 Events")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("파일 크기", f"{ev_size/1024:.1f} KB" if ev_size else "없음")
    e2.metric("마지막 수정", ev_mtime or "없음")
    e3.metric("경과 시간", f"{int(ev_elapsed)}s" if ev_elapsed else "없음")
    e4.metric("수집 상태", ev_status_txt)

    if ev_size is None:
        st.error(f"파일 없음: {events_path}")
    else:
        # Heartbeat
        if last_hb:
            st.subheader("최신 Heartbeat")
            hcols = st.columns(4)
            hcols[0].metric("elapsed_sec", last_hb.get("elapsed_sec", "?"))
            hcols[1].metric("remaining_sec", last_hb.get("remaining_sec", "?"))
            hcols[2].metric("events_count", last_hb.get("events_count", "?"))
            hcols[3].metric("trades_count", last_hb.get("trades_count", "?"))

        # 이벤트 카운트
        with st.expander("이벤트 타입별 카운트", expanded=False):
            for field in ["event_type", "reason", "reject_reason", "block_reason", "status"]:
                vals = [str(e[field]) for e in events_tail if field in e and e[field] is not None]
                if vals:
                    df_c = pd.DataFrame(Counter(vals).most_common(), columns=[field, "횟수"])
                    st.markdown(f"**{field}**")
                    st.dataframe(df_c, use_container_width=True, hide_index=True)

        # 최근 이벤트 표
        st.subheader(f"최근 이벤트 (tail {tail_lines}줄)")
        if events_tail:
            try:
                df_ev = pd.DataFrame(events_tail)
                if "ts" in df_ev.columns:
                    df_ev["ts"] = pd.to_datetime(df_ev["ts"], unit="s", errors="coerce")
                if "raw" in df_ev.columns:
                    df_ev = df_ev.drop(columns=["raw"])
                st.dataframe(df_ev.iloc[::-1].head(200), use_container_width=True)
            except Exception as ex:
                st.warning(f"표 변환 실패, 원문 표시: {ex}")
                for row in events_tail[-20:]:
                    st.text(json.dumps(row, ensure_ascii=False))
        else:
            st.info("이벤트 데이터 없음")

# ── Reports 탭 ────────────────────────────────────────────────────────────────
with tab_reports:
    st.header("📄 Reports – 24H Paper Summary")

    # ① 최신 summary 파일 자동 탐색
    summary_files = find_summary_files(reports_dir)
    latest_summary_data = {}
    latest_summary_path = None

    if not summary_files:
        st.info("⏳ 아직 완료된 summary가 없습니다. Paper Runner가 진행 중일 수 있습니다.")
    else:
        latest_mtime, latest_summary_path, latest_fname = summary_files[0]
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest_mtime))
        fsize = os.path.getsize(latest_summary_path)
        fm1, fm2, fm3 = st.columns(3)
        fm1.metric("최신 파일", latest_fname)
        fm2.metric("마지막 수정", mtime_str)
        fm3.metric("파일 크기", f"{fsize:,} bytes")

        if latest_fname.endswith(".json"):
            latest_summary_data = load_json(latest_summary_path)
            if latest_summary_data:
                st.subheader("📊 주요 지표")
                KEY_LABELS = {
                    "paper_entries": "진입 수",
                    "avg_net_pnl_pct": "평균 Net PnL (%)",
                    "avg_gross_pnl_pct": "평균 Gross PnL (%)",
                    "win_rate": "승률 (%)",
                    "max_loss": "최대 손실 (%)",
                    "tp_count": "TP 청산",
                    "sl_count": "SL 청산",
                    "timeout_count": "Timeout 청산",
                    "forced_count": "Forced 청산",
                    "elapsed_sec": "실행 시간 (초)",
                    "stop_reason": "종료 사유",
                    "mode": "모드",
                }
                kv_rows = []
                for k, label in KEY_LABELS.items():
                    if k in latest_summary_data:
                        val = latest_summary_data[k]
                        if isinstance(val, float):
                            val = f"{val:.4f}"
                        kv_rows.append({"항목": label, "값": str(val)})
                if kv_rows:
                    st.dataframe(pd.DataFrame(kv_rows), use_container_width=True, hide_index=True)
                with st.expander("전체 JSON 보기", expanded=False):
                    st.json(latest_summary_data)
            else:
                st.warning("JSON 파싱 실패 또는 빈 파일")
        elif latest_fname.endswith(".txt"):
            txt_content = load_text_tail(latest_summary_path)
            with st.expander("📄 Summary TXT 내용", expanded=True):
                st.text(txt_content)

        # 다른 파일 목록
        if len(summary_files) > 1:
            with st.expander(f"이전 summary 파일 ({len(summary_files)-1}개)", expanded=False):
                for _, fp, fn in summary_files[1:]:
                    st.caption(fn)

    st.markdown("---")

    # ② Promotion Check 카드
    st.subheader("🏅 Promotion Check")
    st.caption("⚠️ 이 판정은 실거래 승인이 아닙니다. 항상 사람 승인이 필요합니다.")

    verdict, color, action = promotion_check(latest_summary_data, tr_lines)
    next_act = next_action_guide(latest_summary_data, tr_lines)

    if color == "success":
        st.success(verdict)
    elif color == "warning":
        st.warning(verdict)
    elif color == "error":
        st.error(verdict)
    else:
        st.info(verdict)

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("Paper Trades", tr_lines)
    if latest_summary_data:
        net_val = latest_summary_data.get("avg_net_pnl_pct", None)
        win_val = latest_summary_data.get("win_rate", None)
        pc2.metric("Avg Net PnL", f"{net_val:.4f}%" if net_val is not None else "–")
        pc3.metric("Win Rate", f"{win_val:.1f}%" if win_val is not None else "–")
    else:
        pc2.metric("Avg Net PnL", "–")
        pc3.metric("Win Rate", "–")

    st.info(next_act)
    st.error("🚫 실거래 반영 금지 / 사람 승인 필요 / live.enabled=false 유지")

    st.markdown("---")

    # ③ 기존 리포트 탐색기
    with st.expander("📁 전체 리포트 파일 탐색", expanded=False):
        if os.path.isdir(reports_dir):
            rfiles = [f for f in os.listdir(reports_dir) if f.endswith((".txt", ".json"))]
            if rfiles:
                selected = st.selectbox("리포트 파일 선택", sorted(rfiles, reverse=True))
                rpath = os.path.join(reports_dir, selected)
                if selected.endswith(".json"):
                    st.json(load_json(rpath))
                else:
                    st.text_area("내용", load_text_tail(rpath), height=400)
            else:
                st.info(f"리포트 파일 없음: {reports_dir}")
        else:
            st.warning(f"reports 폴더 없음: {reports_dir}")

    with st.expander("로컬 Paper Review", expanded=False):
        st.text_area("paper_review_latest.txt", paper_review, height=300)
    with st.expander("Config Candidates", expanded=False):
        st.text_area("orderflow_config_candidates.txt", config_cands, height=300)

    st.markdown("---")

    # ④ OOS Chunk Results 섹션
    st.subheader("🔬 OOS Chunk Results")
    st.caption("아래 결과는 실거래 승인이 아닙니다. live.enabled=false 유지. 사람 승인 전 실거래 반영 금지.")

    _OOS_KEY_LABELS = {
        "success_count": "성공 Chunk 수", "failed_count": "실패 Chunk 수",
        "total_chunks": "계획 Chunk 수", "elapsed_sec": "경과 시간(초)",
        "input_chunks_count": "입력 Chunk 수", "lines_read": "읽은 줄 수",
        "parse_errors": "파싱 실패 줄", "duplicates_removed": "중복 제거",
        "final_events_count": "최종 이벤트 수",
        "merge_success": "Merge 성공", "backtest_success": "Backtest 성공",
        "final_judgement": "최종 판단",
        "total_trades": "총 거래 수", "net_pnl_pct": "Net PnL (%)",
        "win_rate": "승률 (%)",
    }
    _PIPELINE_VERDICT_MAP = {
        "NEED_MORE_DATA":              ("⚠️ 데이터 부족 — 추가 수집 필요", "warning"),
        "PROMISING_BUT_PAPER_REQUIRED":("🟢 유망 — 추가 Paper 검증 필요", "success"),
        "HOLD_AND_ANALYZE_FAILURES":   ("🔴 보류 — 실패 조건 분석 필요", "error"),
        "FAILED":                      ("❌ 실패 — 원인 확인 필요", "error"),
    }

    def _show_oos_summary(label: str, json_paths: list, txt_paths: list):
        """주어진 파일 목록 중 존재하는 최신 파일을 찾아 표시."""
        found_json, found_txt = None, None
        for p in json_paths:
            if os.path.exists(p):
                found_json = p
                break
        for p in txt_paths:
            if os.path.exists(p):
                found_txt = p
                break

        with st.expander(label, expanded=(found_json is not None or found_txt is not None)):
            if found_json is None and found_txt is None:
                st.info("아직 해당 OOS Chunk 결과가 없습니다.")
                return None

            data = {}
            if found_json:
                try:
                    sz = os.path.getsize(found_json)
                    mt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(found_json)))
                    c1, c2, c3 = st.columns(3)
                    c1.metric("파일", os.path.basename(found_json))
                    c2.metric("수정시각", mt)
                    c3.metric("크기", f"{sz:,} bytes")
                    data = load_json(found_json)
                    if data:
                        rows = []
                        for k, lbl in _OOS_KEY_LABELS.items():
                            if k in data:
                                v = data[k]
                                if isinstance(v, float):
                                    v = f"{v:.4f}"
                                rows.append({"항목": lbl, "값": str(v)})
                        if rows:
                            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                        with st.expander("전체 JSON", expanded=False):
                            st.json(data)
                    else:
                        st.warning("JSON 파싱 실패 또는 빈 파일")
                except Exception as ex:
                    st.warning(f"JSON 읽기 오류: {ex}")

            if found_txt:
                try:
                    txt = load_text_tail(found_txt, max_bytes=65536)
                    with st.expander(f"📄 TXT: {os.path.basename(found_txt)}", expanded=False):
                        st.text(txt)
                except Exception as ex:
                    st.warning(f"TXT 읽기 오류: {ex}")

            return data

    # OOS Chunk Runner
    _show_oos_summary(
        "📦 Chunk Runner 결과",
        ["reports/experiments/reversal_oos_chunk_runner_summary.json",
         "reports/experiments/reversal_oos_chunk_runner_test_summary.json"],
        ["reports/experiments/reversal_oos_chunk_runner_summary.txt",
         "reports/experiments/reversal_oos_chunk_runner_test_summary.txt"],
    )

    # OOS Chunk Merge
    _show_oos_summary(
        "🔀 Chunk Merge 결과",
        ["reports/experiments/reversal_oos_chunk_merge_summary.json",
         "reports/experiments/reversal_oos_chunk_merge_test_summary.json",
         "reports/experiments/reversal_oos_chunk_merge_pipeline_test_summary.json"],
        ["reports/experiments/reversal_oos_chunk_merge_summary.txt",
         "reports/experiments/reversal_oos_chunk_merge_test_summary.txt",
         "reports/experiments/reversal_oos_chunk_merge_pipeline_test_summary.txt"],
    )

    # OOS Pipeline (backtest) – parse final_judgement and show verdict card
    pipeline_data = _show_oos_summary(
        "🏁 Backtest Pipeline 결과",
        ["reports/experiments/reversal_oos_chunk_pipeline_summary.json",
         "reports/experiments/reversal_oos_chunk_pipeline_test_summary.json",
         "reports/experiments/reversal_oos_chunk_backtest_pipeline_test_summary.json"],
        ["reports/experiments/reversal_oos_chunk_pipeline_summary.txt",
         "reports/experiments/reversal_oos_chunk_pipeline_test_summary.txt",
         "reports/experiments/reversal_oos_chunk_backtest_pipeline_test_summary.txt"],
    )

    # Final Judgement 카드
    if pipeline_data:
        raw_verdict = str(pipeline_data.get("final_judgement", ""))
        verdict_key = raw_verdict.split(" ")[0] if raw_verdict else "FAILED"
        verdict_txt, verdict_color = _PIPELINE_VERDICT_MAP.get(
            verdict_key, (f"⚠️ {raw_verdict}", "warning")
        )
        st.subheader("🎯 Pipeline 최종 판단")
        if verdict_color == "success":
            st.success(verdict_txt)
        elif verdict_color == "error":
            st.error(verdict_txt)
        else:
            st.warning(verdict_txt)
        st.error("🚫 실거래 반영 금지 / 사람 승인 필요 / live.enabled=false 유지")

    st.markdown("---")

    # ⑥ Auto Research Report TXT
    st.subheader("🧭 Auto Research Report")
    _ARR_TXT = "reports/experiments/auto_research_report_latest.txt"
    if not os.path.exists(_ARR_TXT):
        st.info("Auto Research Report 결과가 아직 없습니다. RUN_AUTO_RESEARCH_REPORT.bat 실행 후 표시됩니다.")
    else:
        try:
            _arr_txt = load_text_tail(_ARR_TXT, max_bytes=65536)
            with st.expander("Auto Research Report (TXT)", expanded=True):
                st.text(_arr_txt)
        except Exception as _ex:
            st.warning(f"Auto Research Report TXT 읽기 오류: {_ex}")
    st.caption("🚫 이 리포트는 실거래 승인이 아닙니다. live.enabled=false 유지. 사람 승인 전 tiny_live 금지.")

    st.markdown("---")

    # ⑦ Research Validation Reports TXT
    st.subheader("📊 Research Validation Reports")
    _rvtxt_items = [
        ("Walk-forward Validation", "reports/experiments/walk_forward_validation_latest.txt",
         "RUN_WALK_FORWARD_VALIDATION.bat"),
        ("Cost Randomization Test", "reports/experiments/cost_randomization_test_latest.txt",
         "RUN_COST_RANDOMIZATION_TEST.bat"),
        ("Strategy Degradation Tracking", "reports/experiments/strategy_degradation_tracking_latest.txt",
         "RUN_STRATEGY_DEGRADATION_TRACKING.bat"),
    ]
    for _rvtitle, _rvpath, _rvbat in _rvtxt_items:
        if not os.path.exists(_rvpath):
            st.info(f"★ {_rvtitle}: 아직 해당 검증 결과가 없습니다. {_rvbat} 실행 후 표시됩니다.")
        else:
            try:
                _rv_txt_content = load_text_tail(_rvpath, max_bytes=65536)
                with st.expander(f"{_rvtitle}", expanded=False):
                    st.text(_rv_txt_content)
            except Exception as _rv_ex:
                st.warning(f"{_rvtitle} TXT 읽기 오류: {_rv_ex}")
    st.caption("🚫 이 검증 결과는 실거래 승인이 아닙니다. live.enabled=false 유지. 사람 승인 전 tiny_live 금지.")

    st.markdown("---")

    # ⑧ HTF Regime Diagnostics TXT
    st.subheader("📡 HTF Regime Diagnostics Report")
    _HTF_TXT = "reports/experiments/htf_regime_diagnostics_latest.txt"
    if not os.path.exists(_HTF_TXT):
        st.info("HTF Regime 결과가 아직 없습니다. RUN_HTF_REGIME_DIAGNOSTICS.bat 실행 후 표시됩니다.")
    else:
        try:
            _htf_txt = load_text_tail(_HTF_TXT, max_bytes=65536)
            with st.expander("HTF Regime Diagnostics Report", expanded=True):
                st.text(_htf_txt)
        except Exception as _ex:
            st.warning(f"HTF Regime TXT 읽기 오류: {_ex}")
    st.caption("HTF Regime 결과는 참고용입니다. 실거래 반영 금지. config 자동 수정 금지. 사람 승인 전 tiny_live 금지.")

# ── Safety 탭 ─────────────────────────────────────────────────────────────────
with tab_safety:
    st.header("🔒 Safety Guard")
    st.success("✅ 실거래 완전 차단 상태 – 안전한 Paper Mode 전용 시스템")

    s1, s2 = st.columns(2)
    with s1:
        st.markdown("### 시스템 안전 상태")
        st.markdown("""
| 항목 | 상태 |
|------|------|
| Live Trading | 🟢 **OFF** |
| Real Orders | 🟢 **Disabled** |
| API Key Input | 🟢 **Not Available** |
| Auto Config Apply | 🟢 **Disabled** |
| Candidate Auto Apply | 🟢 **Disabled** |
| live.enabled | 🟢 **false (코드 고정)** |
""")
    with s2:
        st.markdown("### 보안 관리 원칙")
        st.markdown("""
- 조회 전용 API Key: 추후 `.env.account` 만 사용
- 주문 권한 Key: 추후 `.env.live` 만 사용 (현재 미사용)
- UI 접속: 로컬 전용 권장 (`http://localhost:8501`)
- 외부 접속/포트포워딩: 사용 금지
- 출금 권한: 절대 사용 금지
""")
    st.info("💡 현재는 실거래 기능이 완전히 차단된 안전한 페이퍼 모드입니다.")

# ── 기존 대시보드 탭 (레거시 – 삭제하지 않음) ────────────────────────────────
with tab_legacy:
    st.header("🗂️ 기존 대시보드 (유지)")
    st.caption("기존 기능은 삭제 없이 이 탭으로 이동됨")

    # 시스템/엔진 상태
    with st.expander("시스템 / 엔진 상태", expanded=False):
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("모드", heartbeat.get("mode", "paper"))
        lc2.metric("실거래 활성화", str(heartbeat.get("live_enabled", False)))
        lc3.metric("WS 이벤트 수", heartbeat.get("last_ws_event_count", engine_status.get("last_ws_event_count", 0)))
        lc4.metric("반복 횟수", heartbeat.get("loop_count", 0))
        lc5, lc6, lc7, lc8 = st.columns(4)
        lc5.metric("엔진 실행", str(heartbeat.get("running", False)))
        lc6.metric("엔진 상태", engine_status.get("status", "UNKNOWN"))
        lc7.metric("마지막 성공 단계", engine_status.get("last_success_step", "None"))
        lu = heartbeat.get("last_update")
        lc8.metric("마지막 갱신", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(lu)) if lu else "N/A")
        if heartbeat.get("last_error"):
            st.error(f"Last Error: {heartbeat['last_error']}")

    # 저장공간
    with st.expander("저장공간 상태", expanded=False):
        if storage_status:
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("WS Raw (MB)", storage_status.get("ws_raw_size_mb", 0))
            sc2.metric("Total Logs (MB)", storage_status.get("total_logs_size_mb", 0))
            sc3.metric("Retained Files", storage_status.get("retained_raw_files", 0))
            sc4.metric("Compressed", storage_status.get("compressed_files", 0))
            st.json(storage_status)
        else:
            st.info("Storage status 미생성")

    # DDM
    with st.expander("DDM 손실 방어 관리자", expanded=False):
        if os.path.exists("reports/ddm_status.json"):
            ddm = load_json("reports/ddm_status.json")
            dstatus = ddm.get("status", "UNKNOWN")
            if dstatus == "NORMAL": st.success("DDM 상태: 정상")
            elif dstatus == "CAUTION": st.warning("DDM 상태: 주의")
            elif dstatus == "BLOCK_NEW_ENTRY": st.error("DDM 상태: 신규 진입 차단")
            elif dstatus == "DATA_ERROR": st.error("DDM 상태: 데이터 오류")
            else: st.info(f"DDM 상태: {dstatus}")
            d1, d2, d3 = st.columns(3)
            d1.metric("위험 단계", ddm.get("risk_level", 0))
            d2.metric("신규 진입 차단", str(ddm.get("should_block_new_entry", False)))
            ga = ddm.get("generated_at", 0)
            d3.write(f"생성: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ga)) if ga else 'N/A'}")
            st.write(f"**요약:** {ddm.get('summary', '없음')}")
            ri = ddm.get("risk_items", [])
            if ri: st.dataframe(pd.DataFrame(ri), use_container_width=True)
        else:
            st.warning("DDM 미생성")

    # Market Board
    with st.expander("Market Board", expanded=False):
        fmap = micro.get("features", {})
        if fmap:
            rows = []
            for mkt, f in fmap.items():
                rows.append({"Market": mkt, "Price": f.get("last_trade_price", 0),
                              "Spread(%)": round(f.get("spread_pct", 0), 4),
                              "Buy(3s)": round(f.get("buy_trade_value_3s", 0), 2),
                              "Sell(3s)": round(f.get("sell_trade_value_3s", 0), 2),
                              "OFI": round(f.get("ofi_score", 0), 2),
                              "Sweep": round(f.get("sweep_score", 0), 2)})
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("마켓 데이터 없음")

    # Paper Performance
    with st.expander("페이퍼 성과판 (Paper Performance)", expanded=False):
        if perf:
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("총 판단 수", f"{perf.get('decision_count', 0):,}")
            p2.metric("총 거래 수", f"{perf.get('trade_count', 0):,}")
            p3.metric("시작 자산", f"{perf.get('starting_cash_krw', 0):,} KRW")
            p4.metric("최종 자산", f"{perf.get('final_equity_krw', 0):,} KRW")
            p5, p6, p7, p8 = st.columns(4)
            p5.metric("실현손익", f"{perf.get('realized_pnl_krw', 0):,} KRW")
            p6.metric("미실현", f"{perf.get('unrealized_pnl_krw', 0):,} KRW")
            p7.metric("총 손익", f"{perf.get('total_pnl_krw', 0):,} KRW")
            p8.metric("MDD", f"{perf.get('max_drawdown_pct', 0):.4f}%")
            if equity_curve:
                df_eq = pd.DataFrame(equity_curve)
                if "timestamp" in df_eq.columns:
                    df_eq["timestamp"] = pd.to_datetime(df_eq["timestamp"], unit="s")
                    df_eq = df_eq.set_index("timestamp")
                    st.line_chart(df_eq["equity"])
        else:
            st.info("성과 데이터 미생성")

    # 판단 로그
    with st.expander("최근 판단 로그 (orderflow)", expanded=False):
        if decisions:
            dec_df = pd.DataFrame(decisions)
            if "timestamp" in dec_df.columns:
                dec_df["timestamp"] = pd.to_datetime(dec_df["timestamp"], unit="s")
            for col in ["diagnostic", "virtual_fill_result"]:
                if col in dec_df.columns:
                    dec_df[col] = dec_df[col].apply(lambda x: str(x) if isinstance(x, dict) else x)
            if "details" in dec_df.columns:
                dec_df = dec_df.drop(columns=["details"])
            st.dataframe(dec_df.iloc[::-1].head(100), use_container_width=True)
        else:
            st.info("판단 로그 없음")

# ── 자동 새로고침 ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(30)
    st.rerun()
