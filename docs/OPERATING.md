# Operating Notes

Run the local paper validation loop:

```bash
uv run dual-market-paper-trader run-once --markets KR,US --target-daily-return-pct 5.0 --sample deterministic --evidence-dir .omo/evidence
```

Interpret the paper validation result:

- `validation_status=pass` means the selected candidate met target return, traded every market, stayed non-negative per market, stayed inside the configured drawdown limit, repeated across the primary training and validation scenarios, and did not require fallback.
- `validation_status=fallback` means no candidate passed every gate; the selected strategy is the best available paper fallback and `target_met=false`.
- fallback output is analysis evidence only, not readiness for live orders.

Run the live-order firewall check:

```bash
uv run dual-market-paper-trader trade-live --market KR --symbol 005930.KS --side buy --quantity 1
```

Run live-clock paper validation before any live-order attempt:

```bash
uv run dual-market-paper-trader run-live-paper --market KR --symbol 005930 --side buy --quantity 1 --max-cycles 3 --interval-seconds 30
```

`run-live-paper` fetches the latest Yahoo Finance 1-minute close for paper fills. `--price` is optional; when present, it is only a requested reference price in the log, not the paper fill price. The command exits nonzero if the market price cannot be fetched.

Run the live-refreshing paper performance loop when the dashboard should update paper performance in real time:

```bash
uv run dual-market-paper-trader run-paper-loop --markets KR,US --target-daily-return-pct 5.0 --sample deterministic --max-cycles 10000 --interval-seconds 30 --evidence-dir .omo/evidence/realtime --performance-log .data/performance-log.jsonl
```

Run a gated Toss live execution loop after all live credentials and confirmations are configured:

```bash
uv run dual-market-paper-trader run-live --market KR --symbol 005930 --side buy --quantity 1 --price <LIMIT_PRICE> --max-cycles 1 --interval-seconds 30 --confirm-risk
```

Run the dashboard with both persistent logs:

```bash
uv run dual-market-paper-trader dashboard --host 127.0.0.1 --port 8765 --log .data/performance-log.jsonl --live-paper-log .data/live-paper-executions.jsonl --live-log .data/live-executions.jsonl --refresh-seconds 5
```

The dashboard auto-refreshes and reads append-only files for paper performance, real-time paper orders, and gated live executions.
The served dashboard fetches Yahoo Finance 1-minute candles for the active KR/US paper symbols and overlays the latest paper entry, target exit, and stop loss marker for each symbol. The chart source label reads `YAHOO REAL 1M` when real candles are present and `FALLBACK 1M` only when the real fetch is unavailable.
`Live paper PnL` uses paper fills against the latest chart close. `Sample validation` remains the deterministic validation-loop result.

Runtime state stays under `.data/`. Evidence requested by QA can be written under `.omo/evidence/` or the workspace ULW evidence folder.
