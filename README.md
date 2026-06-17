# Ultra Trading Floor

Paper-only KR/US trading bot prototype. It reuses the safety shape of the existing trading lab while remaining a separate project: deterministic strategies, a paper fill engine, append-only run evidence, and a fail-closed live-order firewall.

## Run

```bash
uv run dual-market-paper-trader run-once --markets KR,US --target-daily-return-pct 5.0 --sample deterministic --evidence-dir .omo/evidence
```

The bundled sample data is deterministic and intentionally local. A report that meets `target_daily_return_pct = 5.0` is validation evidence for the sample, not a real-market profit guarantee.

Every `run-once` appends a durable performance summary to `.data/performance-log.jsonl`.
The full paper report is still written to the selected evidence path.

## Dashboard

```bash
uv run dual-market-paper-trader dashboard --host 127.0.0.1 --port 8765 --log .data/performance-log.jsonl --live-log .data/live-executions.jsonl
```

The WebUI reads the persistent performance log and shows the latest KR/US paper
results, the append-only run history, and the append-only live execution log.

## Live Trading

```bash
uv run dual-market-paper-trader run-live --market KR --symbol 005930 --side buy --quantity 1 --price 71000 --max-cycles 1
```

The live path shells out to `tossctl` using the same safety shape as the existing trading lab: auth status, order preview, confirmation token, then place. It fails closed unless all live-trading preconditions are explicitly present:

- `DMT_LIVE_TRADING_ENABLED=true`
- `DMT_BROKER_API_KEY` and `DMT_BROKER_API_SECRET`
- `TOSS_ALLOW_LIVE_ORDERS=true`
- `--confirm-risk`
- authenticated `tossctl`

Successful live executions append to `.data/live-executions.jsonl`. Paper validation reports still expose `guaranteed=false` and `live_order_enabled=false`; the 5% target is not investment advice and not a fixed-yield claim.

## Verify

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
```
