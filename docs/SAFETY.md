# Safety Contract

This project is paper-only by default. It is not investment advice, not a return guarantee, and not a fixed-yield system.

The target daily return is a validation hurdle for deterministic sample data. Reports always expose `guaranteed=false` and `live_order_enabled=false`.

`validation_status=pass` is required before treating a paper run as validated. `validation_status=fallback` means no candidate met every required criterion; the reported strategy is only the best available evidence candidate and is not live-ready.

Live-paper validation is the first live-clock procedure. `run-live-paper` uses the same order intent fields as the live path, runs on a real-time cycle, and writes only paper fills to `.data/live-paper-executions.jsonl`. Paper fills use the latest Yahoo Finance 1-minute close; a supplied `--price` is only the requested reference price. It does not require broker credentials and never places a brokerage order.

Multi-symbol scanner trading is paper-only. `scan-trade-paper` ranks KR/US candidate symbols from Yahoo Finance 1-minute candles, logs decisions to `.data/screener-decisions.jsonl`, and appends newly selected paper fills to `.data/live-paper-executions.jsonl`; within one running scanner process, already entered symbols are not bought again on later cycles. It does not call the broker path.

The live execution path is gated and off by default. It uses `tossctl` only after credentials, `DMT_LIVE_TRADING_ENABLED=true`, `TOSS_ALLOW_LIVE_ORDERS=true`, authenticated Toss state, and `--confirm-risk` are all present. Without those, `trade-live` and `run-live` exit nonzero and write no order artifact.

Successful live executions are logged separately in `.data/live-executions.jsonl`. The paper performance log remains `.data/performance-log.jsonl` and keeps the paper-only validation record distinct from real brokerage actions.
