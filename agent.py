"""Conversational analytics agent: question -> SQL -> run -> answer.

Each turn the model must reply with SQL, CLARIFY, or CANNOT. SQL is run
read-only; failures are fed back to the model for up to MAX_SQL_ATTEMPTS.
Conversation memory stores each past question with the SQL that answered it,
so follow-ups can modify the previous query instead of starting over.
"""
import re
from dataclasses import dataclass

from db import QueryError, connect, format_table, run_sql
from llm import chat
from prompts import build_system_prompt, describe_coverage

MAX_SQL_ATTEMPTS = 3
HISTORY_TURNS = 4  # keep the last N question/answer pairs

SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
TAGGED = re.compile(r"^\s*(CLARIFY|CANNOT)\s*:\s*(.+)", re.DOTALL | re.IGNORECASE | re.MULTILINE)


@dataclass
class Reply:
    kind: str                # "answer" | "clarify" | "cannot" | "error"
    text: str
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
    if stripped.split(None, 1)[:1] and stripped.split(None, 1)[0].lower() in ("select", "with"):
        return "sql", stripped
    return "none", raw


class Agent:
    def __init__(self):
        self.con = connect()
        self.system = build_system_prompt(self.con)
        self.coverage = describe_coverage(self.con)
        self.history: list[dict] = []

    def reset(self):
        self.history = []

    def _remember(self, question: str, answer: str):
        self.history += [{"role": "user", "content": question},
                         {"role": "assistant", "content": answer}]
        self.history = self.history[-2 * HISTORY_TURNS:]

    def _summarize(self, question: str, sql: str, table: str) -> str:
        prompt = (
            "You explain database query results to a business user.\n\n"
            f"Question: {question}\n\nSQL that was run:\n{sql}\n\n"
            f"Result:\n{table}\n\nData coverage:\n{self.coverage}\n\n"
            "Write a short answer (1-3 sentences) using ONLY numbers that appear "
            "in the result. Do not invent or estimate numbers. If the result is "
            "empty, say no matching data was found. If the question compares "
            "periods and one of them is incomplete according to the coverage, say so."
        )
        return chat([{"role": "user", "content": prompt}], max_tokens=300)

    def ask(self, question: str) -> Reply:
        messages = [{"role": "system", "content": self.system},
                    *self.history,
                    {"role": "user", "content": question}]
        last_error = ""

        for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
            raw = chat(messages)
            kind, payload = parse(raw)

            if kind in ("clarify", "cannot"):
                self._remember(question, raw)
                return Reply(kind, payload, attempts=attempt)

            if kind == "none":
                last_error = "Your reply was not in the SQL / CLARIFY / CANNOT format."
            else:
                try:
                    result = run_sql(self.con, payload)
                except QueryError as e:
                    last_error = str(e)[:500]
                else:
                    table = format_table(result)
                    text = self._summarize(question, result["sql"], table)
                    self._remember(question,
                                   f"SQL:\n```sql\n{result['sql']}\n```\nAnswer: {text}")
                    return Reply("answer", text, sql=result["sql"], table=table,
                                 attempts=attempt)

            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That did not work: {last_error}\n"
                                            "Fix it and reply again in the required format."},
            ]

        return Reply("error",
                     "Sorry, I couldn't build a working query for that, so I won't guess. "
                     f"Last error: {last_error}",
                     attempts=MAX_SQL_ATTEMPTS)
