"""Summary facts computed in code from the query result.

The model is good at phrasing and bad at reading tables: it attaches a number
to the wrong row ("highest = October") and adds filler about "the table".
So small results are summarised in code, larger ones get exact key facts in
the prompt, and any highest/lowest claim the model makes is checked against
those facts.
"""
import re

TIME_COLUMNS = re.compile(r"(^|_)(year|quarter|month)$")
COUNT_COLUMNS = re.compile(r"(^|_)(orders?|count|n_items|n|reviews?|customers?|sellers?|items?)$")
FILLER = re.compile(r"\b(the (result |results |data )?table|calculations?|estimates?|computed|"
                    r"figures? (represents?|shown)|no further|as shown)\b", re.I)
HIGH = re.compile(r"\b(highest|peak|peaked|largest|maximum|most|top|best|leads?|leading)\b", re.I)
LOW = re.compile(r"\b(lowest|least|smallest|minimum|fewest|worst|bottom)\b", re.I)
NUMBER = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\d+")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def fmt(v) -> str:
    """Numbers as the result table shows them, with thousands separators."""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return "NULL" if v is None else str(v)


def humanize(col: str) -> str:
    return col.replace("_", " ")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def roles(columns, rows):
    """Split columns into label columns (text, time) and measure columns (numbers)."""
    labels, measures = [], []
    for i, col in enumerate(columns):
        values = [r[i] for r in rows if r[i] is not None]
        if TIME_COLUMNS.search(col.lower()) or not values or not all(_is_number(v) for v in values):
            labels.append(i)
        else:
            measures.append(i)
    return labels, measures


def label(columns, row, labels) -> str:
    parts = []
    for i in labels:
        col, v = columns[i].lower(), row[i]
        if col.endswith("month") and isinstance(v, int) and 1 <= v <= 12:
            parts.append(MONTHS[v - 1])
        elif col.endswith("quarter") and isinstance(v, int):
            parts.append(f"Q{v}")
        elif col.endswith("year") and isinstance(v, int):
            parts.append(str(v))  # 2018, not "2,018"
        else:
            parts.append(fmt(v))
    return " ".join(parts) or "total"


def small_group_note(columns, rows, measures) -> str:
    """Warn when averages rest on very different group sizes."""
    counts = [i for i in measures if COUNT_COLUMNS.search(columns[i].lower())
              and all(isinstance(r[i], int) for r in rows if r[i] is not None)]
    has_average = any(isinstance(r[i], float) for i in measures if i not in counts for r in rows)
    for i in counts:
        values = [r[i] for r in rows if r[i]]
        if has_average and len(values) > 1 and min(values) < 0.1 * max(values):
            return (f"Some groups have far fewer {humanize(columns[i])} than others (as few as "
                    f"{min(values):,}), so their averages are less reliable.")
    return ""


def small_summary(columns, rows) -> str | None:
    """Summary written in code for empty and small (<= 5 row) results, else None."""
    if not rows:
        return "No matching data was found."
    if len(rows) > 5:
        return None
    labels, measures = roles(columns, rows)
    if not measures or (not labels and len(rows) > 1):
        return None  # nothing to quote, or no way to tell the rows apart
    if len(rows) == 1 and not labels:
        text = "; ".join(f"{humanize(columns[i])}: {fmt(rows[0][i])}" for i in measures) + "."
    else:
        items = []
        for row in rows:
            values = ", ".join(f"{humanize(columns[i])} {fmt(row[i])}" for i in measures)
            items.append(f"{label(columns, row, labels)} ({values})")
        text = "; ".join(items) + "."
    note = small_group_note(columns, rows, measures)
    return text + (" " + note if note else "")


def key_facts(columns, rows) -> list[dict]:
    """Highest and lowest row for up to 3 measure columns (counts only if nothing else)."""
    labels, measures = roles(columns, rows)
    main = [i for i in measures if not COUNT_COLUMNS.search(columns[i].lower())] or measures
    facts = []
    for i in main[:3]:
        valued = [r for r in rows if r[i] is not None]
        if not valued:
            continue
        hi, lo = max(valued, key=lambda r: r[i]), min(valued, key=lambda r: r[i])
        facts.append({"column": humanize(columns[i]),
                      "high": (label(columns, hi, labels), fmt(hi[i])),
                      "low": (label(columns, lo, labels), fmt(lo[i]))})
    return facts


def facts_text(facts: list[dict]) -> str:
    return "\n".join(f"- Highest {f['column']}: {f['high'][0]} ({f['high'][1]}); "
                     f"lowest {f['column']}: {f['low'][0]} ({f['low'][1]})" for f in facts)


def facts_sentence(facts: list[dict]) -> str:
    return " ".join(f"Highest {f['column']}: {f['high'][0]} ({f['high'][1]}); lowest: "
                    f"{f['low'][0]} ({f['low'][1]})." for f in facts)


def superlatives_ok(text: str, facts: list[dict]) -> bool:
    """The first number after a highest/lowest word must be a real highest/lowest value."""
    highs = {f["high"][1] for f in facts}
    lows = {f["low"][1] for f in facts}
    for pattern, allowed in ((HIGH, highs), (LOW, lows)):
        for m in pattern.finditer(text):
            after = NUMBER.search(text, m.end())
            # Skip ranks and small counts ("top 3"); check real measure values only.
            if after and ("," in after.group() or "." in after.group()):
                if after.group() not in allowed:
                    return False
    return True


def drop_filler(text: str) -> str:
    """Remove sentences about the table or calculations instead of the business answer."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [s for s in sentences if not FILLER.search(s)]
    return " ".join(kept) if kept else text
