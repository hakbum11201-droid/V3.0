import glob
import gzip
import json
import logging
import os
import shutil
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict

from coinb.config_loader import load_config
from coinb.ddm import run_ddm_status
from coinb.jsonl import append_jsonl, ensure_parent
from coinb.learning_log import build_learning_dataset
from coinb.microstructure import build_microstructure_report
from coinb.orderflow_loss_analyzer import build_orderflow_loss_analysis
from coinb.orderflow_paper import run_orderflow_paper_step
from coinb.paper_review import build_paper_review
from coinb.upbit_ws import collect_upbit_ws_events

logger = logging.getLogger(__name__)

class PaperEngine:
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.loop_count = 0
        self.last_error = ""
        self.last_success_step = ""
        self.last_ws_event_count = 0
        
        self.ws_raw_dir = "logs/ws_raw"
        self.micro_samples_path = "logs/microstructure_samples.jsonl"
        
        for d in ["logs", "reports", "runtime", self.ws_raw_dir]:
            os.makedirs(d, exist_ok=True)
            
        self._write_engine_status("INITIALIZING")
            
    def run_cycle(self):
        self.loop_count += 1
        self._write_engine_status("RUNNING")
        
        try:
            self._run_collect()
            self._run_microstructure()
            self._run_orderflow()
            self._run_learning()
            self._run_loss_analysis()
            self._run_review()
            self._run_ddm()
            self._cleanup_logs()
            
            self.last_error = ""
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(f"Cycle Error: {self.last_error}")
            
        self._write_heartbeat()
        self._write_engine_status("SLEEPING")
        
    def _run_collect(self):
        self.last_success_step = "collect-ws"
        now_str = datetime.now().strftime("%Y-%m-%d_%H")
        self.current_ws_path = os.path.join(self.ws_raw_dir, f"{now_str}.jsonl")
        
        markets = self.config.get("markets", [])
        result = collect_upbit_ws_events(
            markets=markets,
            output_path=self.current_ws_path,
            seconds=30,
            include_trade=True,
            include_orderbook=True,
        )
        self.last_ws_event_count = result.get("event_count", 0)

    def _run_microstructure(self):
        self.last_success_step = "microstructure"
        build_microstructure_report(
            input_path=self.current_ws_path,
            output_path="reports/microstructure_snapshot.json",
        )
        self._append_micro_samples()

    def _append_micro_samples(self):
        if not os.path.exists("reports/microstructure_snapshot.json"):
            return
            
        with open("reports/microstructure_snapshot.json", "r", encoding="utf-8") as f:
            snap = json.load(f)
            
        features = snap.get("features", {})
        now_ts = time.time()
        
        for market, f in features.items():
            sample = {
                "timestamp": now_ts,
                "market": market,
                "last_trade_price": f.get("last_trade_price", 0.0),
                "spread_pct": f.get("spread_pct", 0.0),
                "buy_trade_value_3s": f.get("buy_trade_value_3s", 0.0),
                "sell_trade_value_3s": f.get("sell_trade_value_3s", 0.0),
                "bid_ask_depth_ratio_5": f.get("bid_ask_depth_ratio_5", 0.0),
                "ofi_score": f.get("ofi_score", 0.0),
                "sweep_score": f.get("sweep_score", 0.0),
                "absorption_score": f.get("absorption_score", 0.0),
                "continuation_score": f.get("continuation_score", 0.0)
            }
            append_jsonl(self.micro_samples_path, sample)

    def _run_orderflow(self):
        self.last_success_step = "orderflow-paper"
        run_orderflow_paper_step(
            config_path=self.config_path,
            microstructure_path="reports/microstructure_snapshot.json",
            state_path="runtime/orderflow_paper_state.json",
            decisions_path="logs/orderflow_paper_decisions.jsonl",
            trades_path="logs/orderflow_paper_trades.jsonl",
        )

    def _run_learning(self):
        self.last_success_step = "learning-log"
        build_learning_dataset(
            decisions_path="logs/orderflow_paper_decisions.jsonl",
            trades_path="logs/orderflow_paper_trades.jsonl",
            output_path="logs/orderflow_learning_dataset.jsonl",
            summary_path="reports/orderflow_learning_summary.json",
        )

    def _run_loss_analysis(self):
        self.last_success_step = "loss-analysis"
        build_orderflow_loss_analysis(
            decisions_path="logs/orderflow_paper_decisions.jsonl",
            trades_path="logs/orderflow_paper_trades.jsonl",
            output_path="reports/orderflow_loss_analysis.json",
        )

    def _run_review(self):
        self.last_success_step = "paper-review"
        build_paper_review(
            loss_analysis_path="reports/orderflow_loss_analysis.json",
            output_path="reports/paper_review_latest.txt",
        )

    def _run_ddm(self):
        self.last_success_step = "ddm-update"
        run_ddm_status(
            config_path=self.config_path,
            output_path="reports/ddm_status.json",
        )

    def _cleanup_logs(self):
        self.last_success_step = "cleanup"
        now = datetime.now()
        raw_files = glob.glob(os.path.join(self.ws_raw_dir, "*.jsonl"))
        gz_files = glob.glob(os.path.join(self.ws_raw_dir, "*.jsonl.gz"))
        
        retained = 0
        deleted = 0
        compressed = 0
        
        for f in raw_files:
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
            age_hours = (now - mtime).total_seconds() / 3600
            
            if age_hours > 6:
                gz_path = f + ".gz"
                with open(f, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(f)
                compressed += 1
            else:
                retained += 1
                
        for f in gz_files:
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
            age_hours = (now - mtime).total_seconds() / 3600
            if age_hours > 24:
                os.remove(f)
                deleted += 1
                
        self._write_storage_status(retained, deleted, compressed)

    def _write_storage_status(self, retained, deleted, compressed):
        def get_dir_size_mb(path):
            total = 0
            if os.path.exists(path):
                for dirpath, _, filenames in os.walk(path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp):
                            total += os.path.getsize(fp)
            return total / (1024 * 1024)
            
        def get_file_size_mb(path):
            if os.path.exists(path):
                return os.path.getsize(path) / (1024 * 1024)
            return 0.0

        status = {
            "ws_raw_size_mb": round(get_dir_size_mb(self.ws_raw_dir), 2),
            "total_logs_size_mb": round(get_dir_size_mb("logs"), 2),
            "retained_raw_files": retained,
            "deleted_old_files": deleted,
            "compressed_files": compressed,
            "last_cleanup_time": time.time(),
            "microstructure_samples_size_mb": round(get_file_size_mb(self.micro_samples_path), 2)
        }
        
        with open("reports/storage_status.json", "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)

    def _write_heartbeat(self):
        app_cfg = self.config.get("app", {})
        live_cfg = self.config.get("live", {})
        
        hb = {
            "running": True,
            "last_update": time.time(),
            "loop_count": self.loop_count,
            "last_error": self.last_error,
            "last_ws_event_count": self.last_ws_event_count,
            "mode": app_cfg.get("default_mode", "paper"),
            "live_enabled": live_cfg.get("enabled", False)
        }
        with open("runtime/heartbeat.json", "w", encoding="utf-8") as f:
            json.dump(hb, f, ensure_ascii=False, indent=2)

    def _write_engine_status(self, status: str):
        st = {
            "engine_name": "coinB_paper_engine",
            "status": status,
            "started_at": time.time() if self.loop_count == 0 else None, # Needs persistence ideally, but good enough for now
            "last_cycle_at": time.time(),
            "current_cycle": self.loop_count,
            "last_success_step": self.last_success_step,
            "last_error": self.last_error,
            "raw_log_path": self.ws_raw_dir,
            "microstructure_path": "reports/microstructure_snapshot.json",
            "decisions_path": "logs/orderflow_paper_decisions.jsonl",
            "trades_path": "logs/orderflow_paper_trades.jsonl",
            "review_path": "reports/paper_review_latest.txt",
        }
        
        # Preserve started_at
        if os.path.exists("runtime/engine_status.json"):
            try:
                with open("runtime/engine_status.json", "r", encoding="utf-8") as f:
                    old = json.load(f)
                    if old.get("started_at"):
                        st["started_at"] = old["started_at"]
            except Exception:
                pass
                
        with open("runtime/engine_status.json", "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)

def main():
    engine = PaperEngine()
    print("Paper Engine Started...")
    while True:
        engine.run_cycle()
        time.sleep(2) # Rest between cycles (already waits 30s in collect-ws)

if __name__ == "__main__":
    main()
