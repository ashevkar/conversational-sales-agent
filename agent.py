"""Conversational analytics agent.

Per turn:
  1. Resolve: turn the latest message into one standalone question.
     - After a clarifying question, a bare "yes/ok" re-asks it (no LLM call),
       and a real answer is merged using ONLY the clarifying exchange.
     - Otherwise an LLM rewrite carries over filters, periods and groupings.
  2. Generate: the model answers the standalone question with SQL, CLARIFY,
     or CANNOT. SQL generation is stateless (no chat history).
  3. Validate + run: guardrails reject raw tables, duplicate-row results and
     repeated clarifications; errors are fed back up to MAX_SQL_ATTEMPTS.
  4. Summarize: 1-3 sentences from the result table. Every number in the
     summary must appear in the table, SQL or question, or it is rejected.
     Partial-year caveats are added by code, not by the model.
"""
import re
from dataclasses import dataclass

from db import QueryError, connect, format_table, run_sql
from llm import chat
from prompts import build_system_prompt

MAX_SQL_ATTEMPTS = 3
HISTORY_TURNS = 6  # question/reply pairs kept for the rewrite step

SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
TAGGED = re.compile(r"^\s*(CLARIFY|CANNOT)\s*:\s*(.+)", re.DOTALL | re.IGNORECASE | re.MULTILINE)

# Raw tables that the cleaned views replace. Querying them bypasses the
# data-quality rules (e.g. joining customers on customer_unique_id fans out).
RAW_TABLES = {"customers", "products", "sellers", "order_items",
              "category_translation", "reviews"}
TABLE_REF = re.compile(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)

# Replies to a clarifying question that don't actually pick an option.
NON_ANSWERS = {"yes", "no", "ok", "okay", "sure", "y", "n", "yep", "nope", "k", "fine"}

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

FOLLOW_UP_PROMPT = """Decide whether the latest message in an analytics chat depends on the earlier conversation.

FOLLOW_UP: it only makes sense together with earlier turns. It refers back to them, changes a filter, period or grouping of the previous question, or asks for the same thing for something else.
NEW: it is a complete question on its own, or it is not about the data at all (a greeting, a name, random text).

Previous: Which sellers are best? / Assistant asked: by revenue or by number of orders?
Latest: by number of orders -> FOLLOW_UP
Previous: Which sellers are best? / Assistant asked: by revenue or by number of orders?
Latest: How many orders were canceled in 2017? -> NEW

Conversation so far:
{conversation}

Latest message: {message}

Answer with one word: FOLLOW_UP or NEW."""

REWRITE_PROMPT = """You rewrite the latest message in an analytics chat into ONE standalone question that contains everything needed to answer it on its own: the measure, grouping, filters, time period and top-N from earlier turns.

Rules:
- Carry over earlier filters, groupings and time periods unless the user changes or removes them.
- "Break that down by X" means: the previous question, broken down by X.
- "Only count ..." means: add that filter to the previous question.
- "Compare with <period>" means: the previous question with the earlier period and the new period compared side by side. Use the words "compared side by side".
- If the assistant just asked a clarifying question and the user picked an option, merge their choice into that question.
- If the latest message is a new, unrelated question, return it unchanged.
- If the latest message is not a question or request about the data (a name, a greeting, random text), return it unchanged.
- Output only the rewritten question. No explanation, no quotes.

Conversation so far:
{conversation}

Latest message: {message}

Standalone question:"""

SUMMARY_PROMPT = """You explain a database query result to a business user.

Question: {question}

Result table:
{table}

Write 1-3 short sentences that answer the question.
- Quote numbers exactly as they appear in the table. Do not add, subtract, total, average or compute percentages yourself.
- Codes like SP, RJ or MG are Brazilian state codes. Write them exactly as they are; never expand them.
- If the table is empty, say no matching data was found.
- If the table is long, mention only the top few rows.
- If some rows are based on far fewer orders than others, say that their averages are less reliable.
- Do not talk about data coverage or missing periods."""


@dataclass
class Reply:
    kind: str                # "answer" | "clarify" | "cannot" | "error"
    text: str
    question: str = ""       # the standalone question that was actually answered
    sql: str | None = None
    table: str | None = None
    attempts: int = 0


def parse(raw: str) -> tuple[str, str]:
    """Classify a model reply as ('sql'|'clarify'|'cannot'|'none', payload)."""
    block = SQL_BLOCK.search(raw)
    if block:
        return "sql", block.group(1).strip()
    tagged = TAGGED.search(raw)
    if tagged:
        return tagged.group(1).lower(), tagged.group(2).strip()
    stripped = raw.strip()
    if stripped.upper().startswith("SQL:"):
        stripped = stripped[4:].strip()
    first = stripped.split(None, 1)[:1]
    if first and first[0].lower() in ("select", "with"):
        return "sql", stripped
    return "none", raw


def check_sql(sql: str) -> str:
    """Return an error message if the SQL breaks a guardrail, else ''."""
    used = {t.lower() for t in TABLE_REF.findall(sql)}
    raw = sorted(used & RAW_TABLES)
    if raw:
        return (f"Do not use the raw table(s) {', '.join(raw)}. Use the sales view "
                "(it already has customer, seller and category columns) or order_facts "
                "(one row per order, with delivery, payment and review columns).")
    if "sales" in used and "payments" in used:
        return ("Do not join sales with payments: an order with several items and several "
                "payments multiplies rows and inflates totals. For payment questions use "
                "payments joined to order_facts (for dates and status) only.")
    return ""


def _numbers(text: str) -> set[float]:
    out = set()
    for m in NUMBER.findall(text):
        try:
            out.add(round(abs(float(m.replace(",", ""))), 2))
        except ValueError:
            pass
    return out


def untraceable_numbers(summary: str, *sources: str) -> list[float]:
    """Numbers in the summary that don't appear in any source text.

    Small integers (ranks, counts like 'top 5') and years are allowed.
    """
    allowed = set().union(*(_numbers(s) for s in sources))
    bad = []
    for n in _numbers(summary):
        if n in allowed:
            continue
        if n.is_integer() and (n <= 20 or 1900 <= n <= 2100):
            continue
        bad.append(n)
    return bad


class Agent:
    def __init__(self):
        self.con = connect()
        self.system = build_system_prompt(self.con)
        self.history: list[tuple[str, str]] = []  # (standalone question, short reply)

        # Years that don't cover Jan-Dec, with a fixed caveat sentence.
        self.partial_years = {}
        for year, first, last in self.con.execute(
            "SELECT purchase_year, MIN(purchase_ts)::DATE, MAX(purchase_ts)::DATE "
            "FROM sales GROUP BY 1"
        ).fetchall():
            if not (first.month == 1 and first.day <= 7 and last.month == 12 and last.day >= 24):
                self.partial_years[year] = f"{year} is a partial year (data from {first} to {last})"

    def reset(self):
        self.history = []

    def _remember(self, question: str, reply: str):
        self.history.append((question, reply))
        self.history = self.history[-HISTORY_TURNS:]

    def _rewrite(self, message: str, history: list[tuple[str, str]]) -> str:
        convo = "\n".join(f"User: {q}\nAssistant: {r}" for q, r in history)
        prompt = (REWRITE_PROMPT
                  .replace("{conversation}", convo)
                  .replace("{message}", message))
        out = chat([{"role": "user", "content": prompt}], max_tokens=200)
        out = out.strip().strip('"').strip()
        if out.lower().startswith("standalone question:"):
            out = out.split(":", 1)[1].strip()
        return out or message

    def _is_follow_up(self, message: str, history: list[tuple[str, str]]) -> bool:
        """Narrow LLM classification: does this message depend on history?"""
        convo = "\n".join(f"User: {q}\nAssistant: {r}" for q, r in history)
        prompt = (FOLLOW_UP_PROMPT
                  .replace("{conversation}", convo)
                  .replace("{message}", message))
        out = chat([{"role": "user", "content": prompt}], max_tokens=5)
        return "FOLLOW" in out.upper()

    def _resolve_question(self, message: str) -> str:
        if not self.history:
            return message
        prev_q, prev_r = self.history[-1]
        if prev_r.startswith("CLARIFY"):
            if message.strip().lower().strip(".!") in NON_ANSWERS:
                return prev_q  # didn't pick an option, so ask again
            if self._is_follow_up(message, [(prev_q, prev_r)]):
                # Attach the answer to the original question directly. No LLM
                # rewrite, so nothing from older turns can leak in.
                return f"{prev_q} (Clarification: {message.strip()})"
            return message  # user skipped the clarifying question and asked something new
        # Only an answered question can be followed up. Answered questions are
        # stored in standalone form, so the latest one carries the whole
        # conversation state; older turns aren't shown, so they can't leak in.
        answered = [(q, r) for q, r in self.history if r == "Answered."]
        if not answered:
            return message
        last = answered[-1:]
        if not self._is_follow_up(message, last):
            return message  # a new, self-contained question
        return self._rewrite(message, last)

    def _summarize(self, question: str, sql: str, table: str) -> str:
        prompt = SUMMARY_PROMPT.replace("{question}", question).replace("{table}", table)
        text = chat([{"role": "user", "content": prompt}], max_tokens=300)

        bad = untraceable_numbers(text, table, sql, question)
        if bad:
            retry = (prompt + "\n\nYour previous answer used numbers that are not in the "
                     f"table: {', '.join(f'{b:,.2f}' for b in bad)}. Rewrite it using only "
                     "numbers copied from the table.")
            text = chat([{"role": "user", "content": retry}], max_tokens=300)
            if untraceable_numbers(text, table, sql, question):
                text = "Here are the results (see the table below)."

        years_used = {int(y) for y in YEAR.findall(sql)}
        notes = [self.partial_years[y] for y in sorted(years_used) if y in self.partial_years]
        if notes:
            text += "\nNote: " + "; ".join(notes) + "."
        return text

    def ask(self, message: str) -> Reply:
        question = self._resolve_question(message)

        # At most one clarifying question per request: if we just asked one and
        # the user's answer changed the question, the model must answer now.
        prev_q, prev_r = self.history[-1] if self.history else ("", "")
        no_more_clarify = prev_r.startswith("CLARIFY") and question != prev_q

        messages = [{"role": "system", "content": self.system},
                    {"role": "user", "content": question}]
        last_error = ""

        for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
            raw = chat(messages)
            kind, payload = parse(raw)

            if kind == "clarify" and no_more_clarify:
                last_error = ("The user already answered a clarifying question. Do not ask "
                              "another one. Reply with SQL, using all available data for "
                              "anything not specified.")
            elif kind in ("clarify", "cannot"):
                self._remember(question, f"{kind.upper()}: {payload}")
                return Reply(kind, payload, question=question, attempts=attempt)
            elif kind == "none":
                last_error = "Your reply was not in the SQL / CLARIFY / CANNOT format."
            else:  # sql
                last_error = check_sql(payload)
                if not last_error:
                    try:
                        result = run_sql(self.con, payload)
                    except QueryError as e:
                        last_error = str(e)[:500]
                    else:
                        rows = result["rows"]
                        if len({repr(r) for r in rows}) < len(rows):
                            last_error = ("The result has duplicate rows, which usually "
                                          "means an unnecessary join. Remove it.")
                        else:
                            table = format_table(result)
                            text = self._summarize(question, result["sql"], table)
                            self._remember(question, "Answered.")
                            return Reply("answer", text, question=question,
                                         sql=result["sql"], table=table, attempts=attempt)

            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That did not work: {last_error}\n"
                                            "Fix it and reply again in the required format."},
            ]

        self._remember(question, "Could not answer.")
        return Reply("error",
                     "Sorry, I couldn't build a working query for that, so I won't guess. "
                     f"Last error: {last_error}",
                     question=question, attempts=MAX_SQL_ATTEMPTS)
