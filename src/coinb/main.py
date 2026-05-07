from __future__ import annotations
import argparse, json
from .config_loader import load_config
from .backtest import run_backtest
from .report import run_report
from .tuner import run_tuner

def main() -> None:
    p=argparse.ArgumentParser(prog="coinB PRO v3.0")
    p.add_argument("command", choices=["validate-config","backtest","report","tune","paper-check"])
    p.add_argument("--config", default="config/config.json")
    p.add_argument("--csv", default="data/sample_ohlcv.csv")
    args=p.parse_args()
    if args.command == "validate-config":
        cfg=load_config(args.config)
        print(json.dumps({"ok":True,"app":cfg["app"]}, ensure_ascii=False, indent=2))
    elif args.command == "backtest":
        print(json.dumps(run_backtest(args.config,args.csv), ensure_ascii=False, indent=2))
    elif args.command == "report":
        print(json.dumps(run_report(args.config), ensure_ascii=False, indent=2))
    elif args.command == "tune":
        print(json.dumps(run_tuner(args.config,args.csv), ensure_ascii=False, indent=2))
    elif args.command == "paper-check":
        cfg=load_config(args.config)
        print(json.dumps({"ok":True,"mode":"paper_ready","live_trading":"disabled","markets":cfg["markets"]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
