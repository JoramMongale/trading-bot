"""Analytics warehouse (plan 03-03): the bot's own artifacts in one DuckDB.

The loader ingests every artifact the bot produces — backtest trades,
decision logs, closes, AI-call audit JSONL, market bars — into ``raw_*``
tables in a single local DuckDB database. A dbt project (``dbt/``) turns
those raw tables into queryable marts. Everything downstream (dashboard
03-05, news 03-04) reads the marts; nothing leaves the machine.

DuckDB is an optional extra: import it lazily and error with an actionable
message when it is missing (the base bot stays stdlib + pandas offline).
"""

from warehouse.load import load

__all__ = ["load"]
