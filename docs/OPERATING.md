# Operating Notes

Run the local paper validation loop:

```bash
uv run dual-market-paper-trader run-once --markets KR,US --target-daily-return-pct 5.0 --sample deterministic --evidence-dir .omo/evidence
```

Run the live-order firewall check:

```bash
uv run dual-market-paper-trader trade-live --market KR --symbol 005930.KS --side buy --quantity 1
```

Run live-clock paper validation before any live-order attempt:

```bash
uv run dual-market-paper-trader run-live-paper --market KR --symbol 005930 --side buy --quantity 1 --price 71000 --max-cycles 3 --interval-seconds 30
```

Run a gated Toss live execution loop after all live credentials and confirmations are configured:

```bash
uv run dual-market-paper-trader run-live --market KR --symbol 005930 --side buy --quantity 1 --price 71000 --max-cycles 1 --interval-seconds 30 --confirm-risk
```

Run the dashboard with both persistent logs:

```bash
uv run dual-market-paper-trader dashboard --host 127.0.0.1 --port 8765 --log .data/performance-log.jsonl --live-paper-log .data/live-paper-executions.jsonl --live-log .data/live-executions.jsonl
```

Runtime state stays under `.data/`. Evidence requested by QA can be written under `.omo/evidence/` or the workspace ULW evidence folder.
