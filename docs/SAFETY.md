# Safety Contract

This project is paper-only by default. It is not investment advice, not a return guarantee, and not a fixed-yield system.

The target daily return is a validation hurdle for deterministic sample data. Reports always expose `guaranteed=false` and `live_order_enabled=false`.

The live execution path is gated and off by default. It uses `tossctl` only after credentials, `DMT_LIVE_TRADING_ENABLED=true`, `TOSS_ALLOW_LIVE_ORDERS=true`, authenticated Toss state, and `--confirm-risk` are all present. Without those, `trade-live` and `run-live` exit nonzero and write no order artifact.

Successful live executions are logged separately in `.data/live-executions.jsonl`. The paper performance log remains `.data/performance-log.jsonl` and keeps the paper-only validation record distinct from real brokerage actions.
