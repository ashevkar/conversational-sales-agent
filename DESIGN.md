# Design

A local, conversational analytics agent over the Olist e-commerce dataset. A 4B open-weight model turns questions into SQL; DuckDB runs the SQL read-only; every number in an answer comes from that SQL, which is shown with the result table.

## 1. Architecture

```
user message
   │
   ├─ small talk, or only years outside the data ───────────► fixed reply (no LLM call)
   │
   ▼
1. Resolve ── follow-up? (LLM classifier, or a reference found in code)
   │          references ("it", "the second one", "previous year") → resolved in code
   │          from the last result to ONE value, or a clarifying question if ambiguous
   │          rewrite into one standalone question (LLM; sees only the latest answered
   │          question and the resolved value)
   ▼
2. Generate ── LLM: system prompt (live schema + coverage + rules) + standalone question
   │           → exactly one of  SQL / CLARIFY / CANNOT      (no chat history)
   ▼
3. Validate ── code checks on the decision and on the SQL ──► error fed back, up to 4 tries
   │           run read-only in DuckDB; checks on the result shape
   ▼
4. Summarize ─ ≤ 5 rows: written by code;  larger: LLM with exact key facts
   │           numbers and highest/lowest claims checked against the table
   ▼
answer + "interpreted as" question + result table + SQL
```

The pipeline lives in `agent.py`; the code checks in `checks.py`; summary facts in `facts.py`; the prompt (built from the live schema and data coverage) in `prompts.py`.

**No agent framework.** The flow is four steps, and a 4B model needs tight control over every prompt and every retry. Almost every improvement came from moving a decision out of the model into code or the data layer, which is easiest with plain functions. **Vanna** (RAG over schema and example SQL) was considered: it solves "the schema doesn't fit in the prompt", which isn't our problem (3 tables, ~2,000 prompt tokens), and doesn't address multi-turn rewriting, clarify/refuse decisions or grounded summaries. Its training on question→SQL pairs would also blur the line with memorising eval questions.

## 2. Model and runtime

**Qwen 3.5 4B, 4-bit (Q4_K_M), thinking off, served by llama.cpp's `llama-server`.** 4B is well under the 8B limit and fits a 16 GB laptop with room to spare (2.7 GB file; developed on an 8 GB M1). Thinking is disabled per request (`enable_thinking: false`, `--reasoning-budget 0`): with it on, trivial SQL took 3,000+ tokens; off, 7.

The same model at 8-bit gave no accuracy gain and swapped heavily on 8 GB, so precision isn't the bottleneck; Llama 3.2 3B was faster but refused falsely. On the same eval, llama.cpp scored 33/34 in 13.5 min and Ollama 30/34 in 27 min (a different GGUF conversion and engine build), so llama.cpp is the documented runtime and Ollama the alternative. Any OpenAI-compatible server works through `LLM_BASE_URL` / `LLM_MODEL`.

## 3. Data model and assumptions

There is no data dictionary beyond the Kaggle page; `data_checks.py` prints the findings behind each decision.

| View | Grain | Encodes |
|---|---|---|
| `sales` | one row per order item | canceled/unavailable orders excluded; English categories (fallback: Portuguese name, then `unknown`); revenue = item price |
| `order_facts` | one row per order, all statuses | delivery, lateness, payment total, latest review; only joins one-row-per-order sources, and `load_data.py` asserts the row count |
| `payments` | one row per payment | used only for payment-type questions |

**Assumptions**, each stated so a reviewer can disagree with it:
- **Revenue** = sum of item prices; freight and payments are separate measures. *Amount paid* (payments) includes freight and installment interest.
- **Not a sale:** `canceled` and `unavailable` orders. "Canceled" in a question means the `canceled` status only.
- **Late** = delivered after the estimated **date**. The estimate has no time of day, so delivery on that day is on time (a timestamp comparison wrongly marks 1,292 orders late). Undelivered orders are neither late nor on time.
- **Customers** are counted by `customer_unique_id` (`customer_id` is per order).
- **Reviews:** latest review per order; averages are always shown with their order counts, and small groups are flagged rather than hidden.
- **Partial years:** 2016 and 2018 are partial. Coverage is computed from the data, and answers about a partial year get a note written by code.
- **Relative periods** ("last quarter", "last year") are measured from the latest date in the data, not today: last complete quarter = 2018 Q2.
- **"São Paulo"** means the state (SP) unless the user says "city"; the answer says so.

Nothing above is hardcoded to these dates or values: schema, coverage, relative periods and valid filter values are read from the database at startup, so a variant dataset gets its own (`OLIST_DB` points at another database).

## 4. Answering from the data

The model never states a number it didn't get from executed SQL:
1. **Every answer shows** the standalone question it answered, the SQL and the result table.
2. **SQL checks in code** reject, with a specific error the model must fix: raw tables; joins that double count (sales × payments, sales × per-order values); sellers grouped by state; comparisons not side by side; top-N questions with no limit, or a limit on the broken-down rows; items counted as orders; grouping by an aggregated column; filter values that don't exist (suggesting the closest real one, e.g. `Toys` → `toys`).
3. **Result checks** reject outputs that are never right: identical period columns, one row per order id, all groups repeating the same values.
4. **Summaries:** small results are summarised by code. For larger ones the model gets exact key facts (highest and lowest rows); any number not in the table, or any "highest/lowest" claim that doesn't match the facts, replaces the summary with the facts.
5. **If no query passes in 4 attempts, the agent says it couldn't answer** rather than guess. A safe refusal is preferred to a plausible wrong number.
6. Safety: read-only connection with file access disabled, a single `SELECT` only, at most 50 rows.

## 5. Conversation and references

The conversation state is the **latest answered question in standalone form**: each follow-up ("break that down by state", "only delivered orders", "compare with 2018") is rewritten into a complete question, so the next follow-up builds on all earlier ones. SQL generation never sees chat history, and the rewrite sees only that one question. Older turns therefore can't leak old filters into new questions.

References to the **previous answer** are resolved in code from the stored result:
- "the second one" → row 2; "it" / "that seller" → the item, when the question asked for one item;
- "that category" after a list, or "the previous year" with no year to anchor on → a clarifying question;
- only the resolved value (e.g. `category = 'watches_gifts'`) reaches the model, and the SQL must filter on it.

Limitation by design: only the latest answer is remembered, and references code can't resolve ("the RJ one") fall back to the plain rewrite.

## 6. Ambiguity and questions it can't answer

- **Clarify** only when a request ranks with a vague word ("best", "top", "most popular") and names no measure. A code check sends back clarifying questions for anything else, so "worst reviews" or "top sellers by number of orders" are answered directly. At most one clarifying question per request; a bare "yes" re-asks it.
- **Can't answer:** topics the data lacks (profit, costs, marketing, customer age) are refused immediately. A refusal for something the data does have is sent back once with the relevant tables. Years outside the data and small talk are answered in code.

## 7. Evaluation

25 questions in `eval/cases.py`: grounding (7), multi-turn including the assignment's 4-turn chain checked at every turn (3), clarify (3), cannot (4), a per-order question with no prompt example (1), and references (7). Expected values come from hand-written SQL; checks also verify the interpreted question and, for references, the SQL filter, so a right number in a wrong query fails. `python eval/run_eval.py` runs them; `eval/report.py` writes [eval/RESULTS.md](eval/RESULTS.md).

**Result: 24/25** on llama.cpp (Apple M1, 8 GB; 3.2 LLM calls and about 20–35 s per question, depending on machine load). The failure is a safe refusal (below). A separate regression set of 9 older bug cases runs with `--regression`, and 34 unit tests cover every code check without needing the model.

## 8. Limitations

- **"The second one" with an average review score:** the reference resolves correctly, but the model can't build the filtered query in 4 attempts, so the agent refuses.
- **Compound top-N breakdowns** ("top 5 categories, broken down by state") are at the edge of the 4B model: when it can't write the top-N subquery within 4 attempts, the agent refuses. Before the top-N check it could silently return every category instead.
- **Run-to-run variation** on long multi-call conversations: earlier full runs ranged from 32 to 34 of 34.
- **Speed:** 3 to 60 s per question on an 8 GB laptop; follow-ups cost 2 extra LLM calls (classify and rewrite).
- **Coverage of the checks** is limited to mistakes seen so far; a new kind of wrong join can still pass, which is why the SQL and table are always shown.
- **English questions** only.

**Next steps:** merge the follow-up classifier and rewrite into one call; retrieve 2–3 verified examples per question instead of a fixed set; a structured query plan (measure, grouping, filters) compiled to SQL for compound questions; a smaller model (2B) for the Raspberry Pi target.
