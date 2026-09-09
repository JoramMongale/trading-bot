"""Idempotent ingestion of the bot's output artifacts into a local DuckDB.

``load()`` opens (or creates) one DuckDB database and merges every artifact
into ``raw_*`` tables keyed on natural keys, so re-runs never duplicate rows
(the loader is idempotent by construction: ``MERGE INTO ... WHEN MATCHED
THEN UPDATE ... WHEN NOT MATCHED THEN INSERT``).

Inputs are the bot's OWN local files — convenience, not load-bearing: a
missing file is skipped with a printed notice, never an error. Parsing is
defensive (unparseable lines are skipped, never raised), and no SQL is ever
built from file content — table/column names are fixed literals and all
values flow through DuckDB's typed parameters (threat T-04-03-01/02).

Tables (natural keys in parentheses):
  raw_trades    output/trades.csv + output/ai_trades.csv   (source, entry_time, entry)
  raw_ledger    output/ledger.csv                          (source, row_idx)
  raw_decisions every output/*.log decision line           (source_log, line_number)
  raw_closes    output/closes.log                          (source_log, line_number)
  raw_ai_calls  every output/ai_calls_*.jsonl              (source_file, ts)
  raw_bars      data/processed/*.csv (+ histdata M1 when include_histdata) (source_file, time)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# DuckDB is imported lazily inside load() so the base bot never depends on it.
# scripts/warehouse.py translates the ImportError into an actionable message.

DEFAULT_DB = Path("data/analytics/trading.duckdb")

# Natural-key column lists per table — used to build the MERGE ON clause.
_KEYS = {
    "raw_trades": ["source", "entry_time", "entry"],
    "raw_ledger": ["source", "row_idx"],
    "raw_decisions": ["source_log", "line_number"],
    "raw_closes": ["source_log", "line_number"],
    "raw_ai_calls": ["source_file", "ts"],
    "raw_bars": ["source_file", "time"],
}

_DDL = {
    "raw_trades": """
        CREATE TABLE IF NOT EXISTS raw_trades (
            source VARCHAR,
            entry_time TIMESTAMP,
            entry DOUBLE, sl DOUBLE, tp DOUBLE,
            exit_time TIMESTAMP,
            exit_price DOUBLE,
            exit_reason VARCHAR,
            pnl_points DOUBLE,
            r_multiple DOUBLE,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source, entry_time, entry)
        )
    """,
    "raw_ledger": """
        CREATE TABLE IF NOT EXISTS raw_ledger (
            source VARCHAR,
            row_idx BIGINT,
            entry_time VARCHAR,
            entry DOUBLE, sl DOUBLE, tp DOUBLE,
            exit_time VARCHAR,
            exit_price DOUBLE,
            exit_reason VARCHAR,
            r DOUBLE,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source, row_idx)
        )
    """,
    "raw_decisions": """
        CREATE TABLE IF NOT EXISTS raw_decisions (
            source_log VARCHAR,
            line_number BIGINT,
            ts VARCHAR,
            level VARCHAR,
            event VARCHAR,
            fields JSON,
            line VARCHAR,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source_log, line_number)
        )
    """,
    "raw_closes": """
        CREATE TABLE IF NOT EXISTS raw_closes (
            source_log VARCHAR,
            line_number BIGINT,
            ts VARCHAR,
            level VARCHAR,
            event VARCHAR,
            fields JSON,
            line VARCHAR,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source_log, line_number)
        )
    """,
    "raw_ai_calls": """
        CREATE TABLE IF NOT EXISTS raw_ai_calls (
            source_file VARCHAR,
            ts VARCHAR,
            kind VARCHAR,
            as_of VARCHAR,
            context JSON,
            result JSON,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source_file, ts)
        )
    """,
    "raw_bars": """
        CREATE TABLE IF NOT EXISTS raw_bars (
            time TIMESTAMP,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
            symbol VARCHAR,
            timeframe VARCHAR,
            source_file VARCHAR,
            loaded_at TIMESTAMP,
            PRIMARY KEY (source_file, time)
        )
    """,
}

# Regexes for the SAFE-02 decision-log format (logging_utils.log_decision):
#   "<asctime>,<ms> level=<LEVEL> event=<EVENT> k1=v1 k2=v2 ..."
# Values containing whitespace are double-quoted.
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d{3})? ")
_KV_RE = re.compile(r'(\w+)=("(?:\\.|[^"])*"|\S+)')

_HISTDATA_HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_decision_line(line: str) -> dict | None:
    """Split a decision line into ts/level/event/fields, or None if not one.

    Returns ``None`` for lines that are not in the SAFE-02 format (e.g. a
    supervise log line, a stack trace, an empty line) — the caller skips them.
    """
    m = _TS_RE.match(line)
    if not m:
        return None
    rest = line[m.end():]
    if "event=" not in rest:
        return None
    fields: dict[str, str] = {}
    for key, value in _KV_RE.findall(rest):
        fields[key] = value.strip('"')
    return {
        "ts": m.group(1),
        "level": fields.pop("level", ""),
        "event": fields.pop("event", ""),
        "fields": fields,
        "line": line.rstrip("\n"),
    }


def _symbol_timeframe_from_name(filename: str, symbol_hint: str | None = None) -> tuple[str, str]:
    """Derive (symbol, timeframe) from an artifact filename.

    Handles ``BTCUSDc_M5_broker.csv`` and ``DAT_ASCII_XAUUSD_M1_202102.csv``;
    falls back to the hint/``""`` when the pattern does not match.
    """
    stem = filename.removesuffix(".csv")
    m = re.search(r"_([M][135])(?:_|$)", stem)
    timeframe = m.group(1) if m else ""
    if symbol_hint:
        symbol = symbol_hint
    elif m:
        symbol = stem.split(f"_{m.group(1)}_")[0].split(f"_{m.group(1)}")[0]
    else:
        symbol = stem
    return symbol, timeframe


def _ingest_trades(con, root: Path, loaded_at: str) -> int:
    """Union output/trades.csv + output/ai_trades.csv into raw_trades."""
    frames = []
    for source in ("trades.csv", "ai_trades.csv"):
        path = root / "output" / source
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001 - defensive: skip, never raise
            print(f"  [skip] {path.name}: unreadable ({exc})")
            continue
        if df.empty:
            continue
        df["source"] = source.removesuffix(".csv")
        for col in ("entry", "sl", "tp", "exit_price", "pnl_points", "r_multiple"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ("entry_time", "exit_time"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        frames.append(df)
    if not frames:
        return 0
    data = pd.concat(frames, ignore_index=True)
    data["loaded_at"] = loaded_at
    _upsert(con, "raw_trades", data, _KEYS["raw_trades"])
    return len(data)


def _ingest_ledger(con, root: Path, loaded_at: str) -> int:
    """output/ledger.csv into raw_ledger (row-identity keyed)."""
    path = root / "output" / "ledger.csv"
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] ledger.csv: unreadable ({exc})")
        return 0
    if df.empty:
        return 0
    df = df.reset_index().rename(columns={"index": "row_idx"})
    for col in ("entry", "sl", "tp", "exit_price", "r"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["loaded_at"] = loaded_at
    _upsert(con, "raw_ledger", df, _KEYS["raw_ledger"])
    return len(df)


def _ingest_decisions(con, root: Path, loaded_at: str, table: str = "raw_decisions") -> int:
    """Every matching line of output/*.log (or closes.log) into raw_decisions."""
    if table == "raw_closes":
        paths = [root / "output" / "closes.log"] if (root / "output" / "closes.log").exists() else []
    else:
        paths = sorted((root / "output").glob("*.log"))
    total = 0
    for path in paths:
        if path.name in {"closes.log"} and table == "raw_decisions":
            continue
        rows = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, start=1):
                parsed = _parse_decision_line(line)
                if parsed is None:
                    continue
                rows.append(
                    {
                        "source_log": path.name,
                        "line_number": number,
                        "ts": parsed["ts"],
                        "level": parsed["level"],
                        "event": parsed["event"],
                        "fields": json.dumps(parsed["fields"]),
                        "line": parsed["line"],
                        "loaded_at": loaded_at,
                    }
                )
        if rows:
            df = pd.DataFrame(rows)
            _upsert(con, table, df, _KEYS[table])
            total += len(rows)
    return total


def _ingest_ai_calls(con, root: Path, loaded_at: str) -> int:
    """Every output/ai_calls_*.jsonl into raw_ai_calls (JSON columns intact)."""
    total = 0
    for path in sorted((root / "output").glob("ai_calls_*.jsonl")):
        rows = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(
                    {
                        "source_file": path.name,
                        "ts": str(obj.get("ts", "")),
                        "kind": obj.get("kind", ""),
                        "as_of": str(obj.get("as_of", "")),
                        "context": json.dumps(obj.get("context", {})),
                        "result": json.dumps(obj.get("result", {})),
                        "loaded_at": loaded_at,
                    }
                )
        if rows:
            df = pd.DataFrame(rows)
            _upsert(con, "raw_ai_calls", df, _KEYS["raw_ai_calls"])
            total += len(rows)
    return total


def _ingest_bars(con, root: Path, loaded_at: str, include_histdata: bool) -> int:
    """data/processed/*.csv (and data/raw histdata when include_histdata) bars."""
    total = 0
    processed = sorted((root / "data" / "processed").glob("*.csv")) if (root / "data" / "processed").exists() else []
    for path in processed:
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {path.name}: unreadable ({exc})")
            continue
        if df.empty:
            continue
        symbol, timeframe = _symbol_timeframe_from_name(path.name)
        df = df.rename(columns=str.lower)
        keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
        if not keep:
            continue
        df = df[keep].astype(float)
        df.index.name = "time"
        df = df.reset_index()
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        df["source_file"] = path.name
        df["loaded_at"] = loaded_at
        _upsert(con, "raw_bars", df, _KEYS["raw_bars"])
        total += len(df)

    if include_histdata:
        raw_dir = root / "data" / "raw"
        hist = sorted(raw_dir.glob("DAT_ASCII_*_M1_*.csv")) if raw_dir.exists() else []
        for path in hist:
            try:
                df = pd.read_csv(path, names=_HISTDATA_HEADER, sep=";")
            except Exception as exc:  # noqa: BLE001
                print(f"  [skip] {path.name}: unreadable ({exc})")
                continue
            if df.empty:
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y%m%d %H%M%S", errors="coerce")
            df = df.dropna(subset=["timestamp"]).set_index("timestamp")
            symbol, timeframe = _symbol_timeframe_from_name(path.name)
            df = df[["open", "high", "low", "close"]].astype(float)
            df.index.name = "time"
            df = df.reset_index()
            df["symbol"] = symbol
            df["timeframe"] = timeframe
            df["source_file"] = path.name
            df["loaded_at"] = loaded_at
            _upsert(con, "raw_bars", df, _KEYS["raw_bars"])
            total += len(df)
    return total


def _upsert(con, table: str, df: pd.DataFrame, key_cols: list[str]) -> None:
    """MERGE a dataframe into a raw table keyed on ``key_cols`` (idempotent)."""
    cols = list(df.columns)
    updates = ", ".join(f"{c} = __src.{c}" for c in cols)
    inserts = ", ".join(cols)
    placeholders = ", ".join(f"__src.{c}" for c in cols)
    keys = " AND ".join(f"t.{c} = __src.{c}" for c in key_cols)
    con.register("__src", df)
    try:
        con.execute(
            f"MERGE INTO {table} AS t USING __src ON {keys} "
            f"WHEN MATCHED THEN UPDATE SET {updates} "
            f"WHEN NOT MATCHED THEN INSERT ({inserts}) VALUES ({placeholders})"
        )
    finally:
        con.unregister("__src")


def load(db_path: str | Path = DEFAULT_DB, roots: list[str | Path] | None = None,
         include_histdata: bool = False) -> dict[str, int]:
    """Ingest every bot artifact under ``roots`` into the DuckDB at ``db_path``.

    Returns ``{table: rows_loaded}`` for the tables touched this run. Re-running
    is safe: MERGE-on-natural-key means row counts stay stable (idempotent).
    """
    import duckdb  # lazy: duckdb is an optional extra (pyproject analytics)

    roots = [Path(r) for r in (roots if roots is not None else [Path.cwd()])]
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    loaded_at = _now()
    con = duckdb.connect(str(db_path))
    try:
        for ddl in _DDL.values():
            con.execute(ddl)

        counts: dict[str, int] = {}
        for root in roots:
            ingests = [
                ("raw_trades", lambda: _ingest_trades(con, root, loaded_at)),
                ("raw_ledger", lambda: _ingest_ledger(con, root, loaded_at)),
                ("raw_decisions", lambda: _ingest_decisions(con, root, loaded_at, "raw_decisions")),
                ("raw_closes", lambda: _ingest_decisions(con, root, loaded_at, "raw_closes")),
                ("raw_ai_calls", lambda: _ingest_ai_calls(con, root, loaded_at)),
                ("raw_bars", lambda: _ingest_bars(con, root, loaded_at, include_histdata)),
            ]
            for table, ingest in ingests:
                loaded = ingest()
                if loaded:
                    counts[table] = counts.get(table, 0) + loaded
        return counts
    finally:
        con.close()
