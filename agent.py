"""Conversational analytics agent.

Per turn:
  0. Small talk and years outside the data are answered in code (no LLM call).
  1. Resolve: turn the latest message into one standalone question.
     - References to the previous answer ("it", "that seller", "the second
       one", "the previous year") are resolved in code from the last result
       (checks.py): to ONE value, which is the only result data the rewrite
       sees, or to a clarifying question when the reference is ambiguous.
     - After a clarifying question, a bare "yes/ok" re-asks it (no LLM call),
       and a real answer is merged using ONLY the clarifying exchange.
     - Otherwise an LLM rewrite carries over filters, periods and groupings.
  2. Generate: the model answers the standalone question with SQL, CLARIFY,
     or CANNOT. SQL generation is stateless (no chat history).
  3. Validate + run: guardrails (checks.py) reject raw tables, joins that
     double count, sellers grouped by state, comparisons not side by side,
     top-N breakdowns that LIMIT the wrong rows, suspicious duplicate rows and
     repeated clarifications; a clarifying question when the measure is
     already given, or a refusal for something the data has, is sent back
     once (checks.py). Errors are fed back up to MAX_SQL_ATTEMPTS.
  4. Summarize (facts.py): empty and small results are summarised in code.
     Larger ones get exact key facts (highest/lowest rows) in the prompt; every
     number must appear in the table, SQL or question, and highest/lowest claims
     must match the facts, or the summary is replaced by the facts.
     Partial-year caveats are added by code, not by the model, and so are
     notes saying how a relative period or a place name was interpreted.
"""
import calendar
import re
import unicodedata
from dataclasses import dataclass

from checks import (VALUE_COLUMNS, cannot_error, check_sql, clarify_error,
                    duplicates_suspicious, empty_period_column, find_reference, main_group_by,
                    outside_coverage, previous_year_anchor, repeated_measures,
                    resolve_reference, small_talk_reply, unknown_values, wrong_result_shape)
from db import QueryError, connect, format_table, run_sql
from facts import (drop_filler, facts_sentence, facts_text, key_facts, small_summary,
                   superlatives_ok)
from llm import chat
from prompts import build_system_prompt, relative_periods

MAX_SQL_ATTEMPTS = 4  # a compound query can trip two independent checks
HISTORY_TURNS = 6  # question/reply pairs kept for the rewrite step

SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
TAGGED = re.compile(r"^\s*(CLARIFY|CANNOT)\s*:\s*(.+)", re.DOTALL | re.IGNORECASE | re.MULTILINE)

# Replies to a clarifying question that don't actually pick an option.
NON_ANSWERS = {"yes", "no", "ok", "okay", "sure", "y", "n", "yep", "nope", "k", "fine"}

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
TIME_GROUPING = re.compile(r"\bpurchase_(year|quarter|month)\b")
RELATIVE = re.compile(r"\b(?:last|previous|past)\s+(quarter|month|year)\b", re.IGNORECASE)

# Brazilian states that share their name with their capital city. The prompt
# reads these as the state; the answer says so (key: accent-free, lowercase).
SAME_NAME_STATES = {"sao paulo": ("São Paulo", "SP"), "rio de janeiro": ("Rio de Janeiro", "RJ")}

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
- If references are resolved below, write their exact values into the question instead of "it", "that ...", "the second one" or "the previous year".
- Output only the rewritten question. No explanation, no quotes.

Conversation so far:
{conversation}

Latest message: {message}
{resolved}
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
    kind: str                # "answer" | "clarify" | "cannot" | "error" | "chat" (small talk)
    text: str
    question: str = ""       # the standalone question that was actually answered
    sql: str | None = None
    table: str | None = None
    attempts: int = 0


def parse(raw: str) -> tuple[str, str]:
    """Classify a model reply as ('sql'|'clarify'|'cannot'|'none', payload)."""
    blocks = SQL_BLOCK.findall(raw)
    if blocks:
        # A reply can hold a draft and then a corrected query ("Wait, let me
        # fix it..."): the last block is the model's final answer.
        return "sql", blocks[-1].strip()
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
        # Columns and rows of the last ANSWERED question's result, used only by
        # code to resolve references; the rewrite model never sees these rows.
        self.last_result: tuple[list[str], list[tuple]] | None = None
        # Values a reference in the current message resolved to, and the SQL
        # filters that select them; the SQL must use them.
        self.resolved_values: list[str] = []
        self.resolved_filters: list[str] = []

        # Years that don't cover Jan-Dec, with a fixed caveat sentence.
        self.partial_years = {}
        spans = self.con.execute(
            "SELECT purchase_year, MIN(purchase_ts)::DATE, MAX(purchase_ts)::DATE "
            "FROM sales GROUP BY 1 ORDER BY 1"
        ).fetchall()
        for year, first, last in spans:
            if not (first.month == 1 and first.day <= 7 and last.month == 12 and last.day >= 24):
                self.partial_years[year] = f"{year} is a partial year (data from {first} to {last})"
        self.years = {year for year, _, _ in spans}
        # Real values of filterable text columns, to catch filters like 'Toys'.
        self.known_values = {}
        for table in ("sales", "order_facts", "payments"):
            columns = {c[0] for c in self.con.execute(f"DESCRIBE {table}").fetchall()}
            for col in set(VALUE_COLUMNS) & columns:
                found = {v for (v,) in self.con.execute(
                    f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL").fetchall()}
                self.known_values[col] = self.known_values.get(col, set()) | found
        self.first_date, self.last_date = spans[0][1], spans[-1][2]

        # How relative periods were resolved (from the data's latest date), as
        # (year that must appear in the SQL, note sentence).
        rel = relative_periods(self.con)
        (qy, qn), (my, mn), ly = rel["last_quarter"], rel["last_month"], rel["last_year"]
        self.relative_notes = {
            "quarter": (qy, f"'last quarter' = Q{qn} {qy}, the last complete quarter in the "
                            f"data (latest date {rel['latest']})"),
            "month": (my, f"'last month' = {calendar.month_name[mn]} {my}, the last complete "
                          "month in the data"),
            "year": (ly, f"'last year' = {ly}, the last complete year in the data"),
        }

    def reset(self):
        self.history = []
        self.last_result = None

    def _remember(self, question: str, reply: str):
        self.history.append((question, reply))
        self.history = self.history[-HISTORY_TURNS:]

    def _rewrite(self, message: str, history: list[tuple[str, str]],
                 resolved: list[str] = ()) -> str:
        convo = "\n".join(f"User: {q}\nAssistant: {r}" for q, r in history)
        refs = ("References already resolved:\n" + "\n".join(f"- {r}" for r in resolved)
                + "\n") if resolved else ""
        prompt = (REWRITE_PROMPT
                  .replace("{conversation}", convo)
                  .replace("{message}", message)
                  .replace("{resolved}", refs))
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

    def _resolve_question(self, message: str) -> tuple[str, tuple[str, str] | None]:
        """Return (standalone question, clarification), where clarification is
        (question to remember, clarifying question) when the agent must ask first."""
        if not self.history:
            return message, None
        prev_q, prev_r = self.history[-1]
        if prev_r.startswith("CLARIFY"):
            if message.strip().lower().strip(".!") in NON_ANSWERS:
                return prev_q, None  # didn't pick an option, so ask again
            # "the second one" as the answer to "which one do you mean?"
            ref = find_reference(message)
            if ref and ref["kind"] == "ordinal" and self.last_result:
                outcome = resolve_reference(ref, *self.last_result, prev_q)
                if outcome and outcome[0] == "resolved":
                    message = outcome[1].split(" = ", 1)[1]
            if self._is_follow_up(message, [(prev_q, prev_r)]):
                # Attach the answer to the original question directly. No LLM
                # rewrite, so nothing from older turns can leak in.
                return f"{prev_q} (Clarification: {message.strip()})", None
            return message, None  # user skipped the clarifying question and asked something new
        # Only an answered question can be followed up. Answered questions are
        # stored in standalone form, so the latest one carries the whole
        # conversation state; older turns aren't shown, so they can't leak in.
        answered = [(q, r) for q, r in self.history if r == "Answered."]
        if not answered:
            return message, None
        last = answered[-1:]
        last_q = last[0][0]

        # References to the previous answer are found and resolved in code.
        resolved, must_appear, filters = [], [], []
        ref = find_reference(message)
        if ref and self.last_result:
            outcome = resolve_reference(ref, *self.last_result, last_q)
            if outcome and outcome[0] == "clarify":
                return message, (f"{message} (one item from the answer to: {last_q})", outcome[1])
            if outcome:
                resolved.append(outcome[1])
                must_appear += outcome[2]
                filters += outcome[3]
        year = previous_year_anchor(message, last_q, self.first_date, self.last_date)
        if year and year[0] == "clarify":
            return message, (f"{last_q} (for one specific year)", year[1])
        if year:
            resolved.append(year[1])
            must_appear += year[2]
            filters += year[3]

        # A message with a reference is a follow-up by definition; otherwise ask.
        if not (ref or year) and not self._is_follow_up(message, last):
            return message, None  # a new, self-contained question
        question = self._rewrite(message, last, resolved)
        # The rewrite must carry every resolved value; if it dropped one, add it.
        if not all(value in question for value in must_appear):
            question += " (" + "; ".join(resolved) + ")"
        self.resolved_values, self.resolved_filters = must_appear, filters
        return question, None

    def _interpretation_notes(self, question: str, sql: str) -> list[str]:
        """Say how relative periods and state/city names were read, when the SQL used them."""
        notes = []
        for unit in dict.fromkeys(m.group(1).lower() for m in RELATIVE.finditer(question)):
            year, note = self.relative_notes[unit]
            if str(year) in sql:
                notes.append(note)
        plain = unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode().lower()
        for key, (name, code) in SAME_NAME_STATES.items():
            if key in plain and "city" not in plain and f"'{code}'" in sql:
                notes.append(f"{name} is read as the state ({code}); ask about "
                             f"{name} city for the city only")
        return notes

    def _summarize(self, question: str, result: dict, table: str) -> str:
        sql, columns, rows = result["sql"], result["columns"], result["rows"]
        text = small_summary(columns, rows)
        if text is None:
            facts = key_facts(columns, rows)
            prompt = SUMMARY_PROMPT.replace("{question}", question).replace("{table}", table)
            if facts:
                prompt += ("\n\nKey facts, computed exactly from the full table. Use these for "
                           "any highest or lowest claim:\n" + facts_text(facts))
            text = drop_filler(chat([{"role": "user", "content": prompt}], max_tokens=300))

            bad = untraceable_numbers(text, table, sql, question)
            if bad:
                retry = (prompt + "\n\nYour previous answer used numbers that are not in the "
                         f"table: {', '.join(f'{b:,.2f}' for b in bad)}. Rewrite it using only "
                         "numbers copied from the table.")
                text = drop_filler(chat([{"role": "user", "content": retry}], max_tokens=300))
            if untraceable_numbers(text, table, sql, question) or not superlatives_ok(text, facts):
                text = facts_sentence(facts) or "Here are the results (see the table below)."

        notes = self._interpretation_notes(question, sql)
        # Partial years: the ones the question asks about; for a trend over all
        # the data (grouped by time, no year asked), every partial year.
        years = {int(y) for y in YEAR.findall(question)}
        if not years and TIME_GROUPING.search(main_group_by(sql)):
            years = set(self.partial_years)
        notes += [self.partial_years[y] for y in sorted(years) if y in self.partial_years]
        if notes:
            text += "\nNote: " + "; ".join(notes) + "."
        return text

    def ask(self, message: str) -> Reply:
        # Greetings, thanks and "how are you" get a natural reply; no SQL is generated.
        small_talk = small_talk_reply(message, self.first_date, self.last_date)
        if small_talk:
            self._remember(message, f"CHAT: {small_talk}")
            return Reply("chat", small_talk, question=message)

        self.resolved_values, self.resolved_filters = [], []
        question, clarification = self._resolve_question(message)
        if clarification:
            remembered, text = clarification
            self._remember(remembered, f"CLARIFY: {text}")
            return Reply("clarify", text, question=remembered)

        # Every year asked about is outside the data: say so instead of querying.
        gap = outside_coverage(question, self.years, self.first_date, self.last_date)
        if gap:
            self._remember(question, f"CANNOT: {gap}")
            return Reply("cannot", gap, question=question)

        # At most one clarifying question per request: if we just asked one and
        # the user's answer changed the question, the model must answer now.
        prev_q, prev_r = self.history[-1] if self.history else ("", "")
        no_more_clarify = prev_r.startswith("CLARIFY") and question != prev_q

        messages = [{"role": "system", "content": self.system},
                    {"role": "user", "content": question}]
        last_error = ""
        # A clarifying question or refusal that the checks doubt is sent back
        # once; if the model insists, its decision stands.
        clarify_checked = cannot_checked = False
        duplicates_checked = False  # duplicate rows are questioned at most once
        repeats_checked = False     # so are measures repeated across groups
        empty_checked = False       # and empty period columns in comparisons

        for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
            raw = chat(messages)
            kind, payload = parse(raw)

            if kind == "clarify" and no_more_clarify:
                last_error = ("The user already answered a clarifying question. Do not ask "
                              "another one. Reply with SQL, using all available data for "
                              "anything not specified.")
            elif kind == "clarify" and not clarify_checked and clarify_error(question):
                clarify_checked = True
                last_error = clarify_error(question)
            elif kind == "cannot" and not cannot_checked and cannot_error(question):
                cannot_checked = True
                last_error = cannot_error(question)
            elif kind in ("clarify", "cannot"):
                self._remember(question, f"{kind.upper()}: {payload}")
                return Reply(kind, payload, question=question, attempts=attempt)
            elif kind == "none":
                last_error = "Your reply was not in the SQL / CLARIFY / CANNOT format."
            else:  # sql
                last_error = (check_sql(payload, question)
                              or unknown_values(payload, self.known_values))
                # A resolved reference ("the second one" = watches_gifts) must be a
                # filter in the SQL, not just a row the summary picks out.
                unused = [v for v in self.resolved_values if v not in payload]
                if not last_error and unused:
                    last_error = (f"The question is about {', '.join(unused)} only. Add this "
                                  f"filter: WHERE {' AND '.join(self.resolved_filters)} (inside "
                                  "the subquery if the query has one), so the result covers "
                                  "only that item.")
                if not last_error:
                    try:
                        result = run_sql(self.con, payload)
                    except QueryError as e:
                        last_error = str(e)[:500]
                    else:
                        rows = result["rows"]
                        if (not duplicates_checked and duplicates_suspicious(payload)
                                and len({repr(r) for r in rows}) < len(rows)):
                            duplicates_checked = True
                            last_error = ("The result has duplicate rows, which usually "
                                          "means an unnecessary join. Remove it.")
                        elif wrong_result_shape(question, result["columns"], rows):
                            last_error = wrong_result_shape(question, result["columns"], rows)
                        elif not empty_checked and empty_period_column(
                                question, result["columns"], rows):
                            empty_checked = True
                            last_error = empty_period_column(question, result["columns"], rows)
                        elif not repeats_checked and repeated_measures(payload, rows):
                            repeats_checked = True
                            last_error = ("Several groups show exactly the same values: the "
                                          "breakdown column comes from a joined list of groups "
                                          "that is matched on too few keys. Take the breakdown "
                                          "column (e.g. customer_state) directly from the table "
                                          "you sum, e.g. sales.customer_state, and do not join "
                                          "a separate DISTINCT list of groups.")
                        else:
                            table = format_table(result)
                            text = self._summarize(question, result, table)
                            self._remember(question, "Answered.")
                            self.last_result = (result["columns"], result["rows"])
                            return Reply("answer", text, question=question,
                                         sql=result["sql"], table=table, attempts=attempt)

            # In a turn with a resolved reference, every retry repeats the required
            # filter, so fixing one problem cannot silently drop it.
            keep = (f"\nKeep the filter WHERE {' AND '.join(self.resolved_filters)}."
                    if self.resolved_filters and "Add this filter" not in last_error else "")
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That did not work: {last_error}{keep}\n"
                                            "Fix it and reply again in the required format."},
            ]

        self._remember(question, "Could not answer.")
        return Reply("error",
                     "Sorry, I couldn't build a working query for that, so I won't guess. "
                     f"Last error: {last_error}",
                     question=question, attempts=MAX_SQL_ATTEMPTS)
