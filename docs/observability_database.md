# Observability Database

`runs/observability.db` is a rebuildable SQLite index over run folders. Run artifacts remain the source of truth.

Indexed artifacts:

- `run_manifest.json`
- `timeline.jsonl`
- `records.jsonl`
- `evidence_bundle.json`
- `repair_packet.json`
- selector evidence paths when present

Commands:

```bash
python main.py --observability-index --runs-dir runs
python main.py --observability-rebuild --runs-dir runs
python main.py --observability-stats --runs-dir runs
python main.py --observability-db-path --runs-dir runs
```

The database stores paths and redacted summaries. It does not store raw screenshots, full DOM snapshots, raw API bodies, or secret values.
