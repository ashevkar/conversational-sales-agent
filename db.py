"""Read-only access to the Olist DuckDB database, with guardrails."""
import os
import re
from pathlib import Path

import duckdb

# Resolved from this file, so the agent runs from any folder. OLIST_DB points it
# at another database (e.g. one built from a variant of the dataset).
DB_PATH = os.getenv("OLIST_DB", str(Path(__file__).resolve().parent / "data" / "olist.duckdb"))
MAX_ROWS = 50  # never hand the model (or the user) more than this many rows

# Defense in depth: the connection is already read-only, but we also reject
# anything that isn't a plain query, including file-reading functions.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|"
    r"install|load|export|read_csv\w*|read_parquet|read_json\w*)\b",
    re.IGNORECASE,
)


# Views the agent queries; a database built by an older load_data.py lacks some.
REQUIRED_VIEWS = ("sales", "order_facts", "payments")


class QueryError(Exception):
    """Raised when SQL is rejected or fails to run."""


class DatabaseError(Exception):
    """Raised when the database is missing or out of date (message says how to fix it)."""


def connect():
    if not os.path.exists(DB_PATH):
        raise DatabaseError(f"Database not found at {DB_PATH}. Build it with: python load_data.py "
                            "(the Olist CSVs must be in data/; see the README).")
    # enable_external_access=False blocks reading any file other than the
    # database itself (read_text, glob, SELECT * FROM 'file.csv', ...).
    con = duckdb.connect(DB_PATH, read_only=True, config={"enable_external_access": False})
    present = {name for (name,) in con.execute(
        "SELECT table_name FROM information_schema.tables").fetchall()}
    missing = [v for v in REQUIRED_VIEWS if v not in present]
    if missing:
        con.close()
        raise DatabaseError(f"The database is missing {', '.join(missing)} (built by an older "
                            "version). Rebuild it with: python load_data.py")
    return con


def run_sql(con, sql: str) -> dict:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Empty query.")
    if sql.split(None, 1)[0].lower() not in ("select", "with"):
        raise QueryError("Only SELECT queries are allowed.")
    if ";" in sql:
        raise QueryError("Only one statement is allowed.")
    if FORBIDDEN.search(sql):
        raise QueryError("Query uses a forbidden keyword.")

    try:
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
    except duckdb.Error as e:
        raise QueryError(str(e)) from e

    return {
        "sql": sql,
        "columns": columns,
        "rows": rows[:MAX_ROWS],
        "truncated": len(rows) > MAX_ROWS,
    }


def format_table(result: dict) -> str:
    """Render a result as a plain-text table (for the terminal and the model)."""
    def fmt(v):
        if isinstance(v, float):
            return f"{v:,.2f}"
        return "NULL" if v is None else str(v)

    cols = result["columns"]
    rows = [[fmt(v) for v in r] for r in result["rows"]]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c)
              for i, c in enumerate(cols)]
    line = lambda vals: " | ".join(v.ljust(w) for v, w in zip(vals, widths))
    out = [line(cols), "-+-".join("-" * w for w in widths), *map(line, rows)]
    if not rows:
        out.append("(no rows)")
    if result["truncated"]:
        out.append(f"... (showing first {MAX_ROWS} rows)")
    return "\n".join(out)
