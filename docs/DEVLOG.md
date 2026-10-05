# Development log

Everything in the order it happened, including mistakes, failed attempts and dead ends.

## Phase 0: Starting point

- Received the take-home brief (dated Sep 29, 2026): conversational agent, local model of 8B or fewer, Olist data, multi-turn, traceable numbers, clarifying questions, admit when it can't answer, eval set, DESIGN.md.
- Already downloaded: **LM Studio** and **Qwen 3.5 4B** (GGUF, Q4_K_M, 3.38 GB).
- Reference article used: [Talk to Your Database with a Local LLM](https://localaimaster.com/blog/talk-to-your-database-local-llm). It describes two approaches: **Vanna** (RAG over schema) and a **schema-in-prompt** pattern. We chose schema-in-prompt because Olist has only about 8 tables and the article recommends it for small schemas. The article uses Ollama; LM Studio's OpenAI-compatible server is used instead.

## Phase 1: Getting the model server working

| # | What we tried | What happened | Fix / outcome |
|---|---|---|---|
| 1 | `curl http://localhost:1234/v1/models` | **Failed**: `Couldn't connect to server`. Downloading a model doesn't start the server. | `~/.lmstudio/bin/lms server start` printed "Server is now running on port 1234". |
| 2 | Asked whether we needed to `cd` into a folder | No: `lms` commands work from anywhere. | |
| 3 | `lms load qwen3.5-4b --context-length 8192` | **Failed**: "Model loading was stopped due to insufficient system resources ... requires approximately 3.73 GB". | Investigated with `lms ps`. |
| 4 | `lms ps` | Showed **two copies** loaded: `qwen3.5-4b` (context 16384, loaded earlier from the LM Studio app) and `qwen3.5-4b:2` (context 8192, from our command). | `lms unload qwen3.5-4b:2`. Kept the 16384-context copy. |
| 5 | `curl .../v1/models` | **Worked**. Listed `qwen3.5-4b` and `text-embedding-nomic-embed-text-v1.5` (bundled with LM Studio, not used). | |
| 6 | First chat completion ("count rows in orders, return only SQL") | Took a long time with no output at first (model was thinking). Then returned the correct `SELECT COUNT(*) FROM orders;` **but used 3,386 reasoning tokens**, mostly arguing with itself about whether to use markdown backticks. | Answer is cleanly in `content`; thinking goes to a separate `reasoning_content` field. Too slow, so thinking had to be turned off. |
| 7 | Added `/no_think` to the prompt | **Failed**: still 988 reasoning tokens. The model treated `/no_think` as part of the question. Qwen 3.5 doesn't support that switch. | |
| 8 | LM Studio: My Models → gear → found **"Reasoning"** (not called "Thinking"; there was no "Inference" section), set it **Off**, reloaded | **Failed**: still 2,211 reasoning tokens. The toggle seems to affect only LM Studio's own chat window, not API requests. | |
| 9 | Added `"reasoning_effort": "none"` and `"chat_template_kwargs": {"enable_thinking": false}` to the request body | **Worked**: `reasoning_tokens: 0`, 7 completion tokens, `reasoning_content: ""`. | Both fields are sent by `llm.py` on every request. (The prompt-template edit fallback was never needed.) |

## Phase 2: Project, Python and git setup

| # | What we tried | What happened | Fix / outcome |
|---|---|---|---|
| 1 | Plan was `~/olist-analytics-agent` | Project was actually created at `~/Desktop/conversational-sales-agent`. Kept that. | |
| 2 | `python3 -m venv .venv` | **Failed**: `ensurepip ... returned non-zero exit status 1` with **Python 3.14** (Homebrew). | Deleted `.venv`, installed **uv** (`brew install uv`), ran `uv venv --python 3.12` (CPython 3.12.15). From then on: `uv pip install ...`. |
| 3 | `.gitignore` (`.venv/`, `data/`, `*.db`, `*.duckdb`, `__pycache__/`, `.DS_Store`), `git init` | Worked. First commit `7d0a212` "Initial commit: project setup and gitignore". | |

## Phase 3: Data download

| # | What we tried | What happened | Fix / outcome |
|---|---|---|---|
| 1 | Downloaded `archive.zip` from Kaggle, `unzip ~/Downloads/archive.zip -d data` | Unzipped into an extra `data/archive/` folder plus a macOS junk folder `data/__MACOSX/`. `ls data` showed only those two folders. | `mv data/archive/*.csv data/` and `rm -rf data/archive data/__MACOSX`. |
| 2 | `ls -lh data` | 9 CSVs: customers 8.6M, geolocation 58M, order_items 15M, payments 5.5M, reviews 14M, orders 17M, products 2.3M, sellers 171K, category translation 2.6K. | |
| 3 | `git status` | "nothing to commit, working tree clean": data correctly ignored. | |

## Phase 4: Database and data-quality checks

| # | What we did | Outcome |
|---|---|---|
| 1 | Chose **DuckDB** (single file, no server, built for analytics, reads CSVs directly). `uv pip install duckdb`. | |
| 2 | `load_data.py`: one table per CSV with short names (easier for a small model); geolocation skipped. | All row counts matched expectations, including the reviews file (multi-line comments loaded fine). Commit `1f7c97e`. |
| 3 | `data_checks.py`: 12 checks (statuses, years, sparse months, orders without items or payments, payment mismatch, payment types, missing categories, untranslated categories, customer IDs, duplicate reviews, delivered without date). | Findings and decisions in [DESIGN.md](../DESIGN.md#3-data-model-and-assumptions). Commit `2f04e6b`. |
| 4 | Added the cleaned views `sales` (112,101 rows) and `order_reviews` (98,673 rows) to `load_data.py`. Idea: move cleaning decisions out of the model and into the data layer, so a 4B model doesn't have to join 7 tables correctly every time. | Sanity check of top 5 categories 2017 matched expectations. Commit `00fc8d3`. |
| 5 | Mistake: pasted the previous step's terminal output again instead of running the next step. | No harm; continued. |

## Phase 5: Building blocks (LLM client, safe SQL runner)

| # | What we did | Outcome |
|---|---|---|
| 1 | `uv pip install openai` (installed openai 3.24.0 plus 13 dependencies). | |
| 2 | Mistake: typed `requirements.txt` and `update requirements.txt` as shell commands (`zsh: command not found`) because my instructions summarized a step instead of giving the command. | Used `uv pip freeze > requirements.txt` (pins exact versions). |
| 3 | `llm.py` with thinking disabled. Test: `Reply with just the word OK` → `OK`. | Worked. |
| 4 | `db.py`: read-only connection, SELECT-only, single statement, forbidden keywords, 50-row cap, table formatter. Test: correct 3-row table; `DROP TABLE orders` → "Blocked as expected: Only SELECT queries are allowed." | Worked. |

## Phase 6: System prompt and first agent

| # | What we did | Outcome |
|---|---|---|
| 1 | `prompts.py`: schema read live via `DESCRIBE`, coverage computed live, rules, the `SQL:` / `CLARIFY:` / `CANNOT:` reply format, examples. | First question produced **exactly the right SQL**. Commit `72f472b`. |
| 2 | `agent.py` (generate, parse, run, retry up to 3 times, summarize, remember past SQL) and `chat.py`. | Commit `b0731ed`. |

## Phase 7: Test-and-fix iterations

Each run used the assignment's conversation ("top 5 categories 2017" → "break down by customer state" → "only delivered" → "compare with 2018") plus clarify and cannot-answer checks.

### Run 1: first full conversation

| Turn | Failure |
|---|---|
| Break down by state | Dropped the category column **and** added an unnecessary `JOIN order_reviews`, which silently drops orders without a review, so the **numbers were wrong**. |
| Compare with 2018 | SQL reasonable, but the summary claimed "2018 covers Q3 only" (2018 runs Jan to early Sep). |
| Summaries | **Invented numbers**: "combined total of 4,369,008.16" (real sum 4,359,010.94), "654,532.36 across 1,907 orders" (real: 654,533.36 and 2,317 orders). |
| Best sellers | Didn't clarify; guessed revenue and carried over 2017 + delivered from the previous chat. |
| Marketing spend | Correctly refused. |
| All | Every summary rambled about "2016-Q3 with only 2 orders". |

**Fix (prompt):** join `order_reviews` only for review questions; clarify when a ranking word ("best", "top") has no measure, even mid-conversation; explicit follow-up rules; a follow-up example (seller state by quarter, deliberately different from the eval questions); per-year coverage with "PARTIAL YEAR" tags.

### Run 2

| Turn | Failure |
|---|---|
| Break down by state | Still dropped category; this time **joined the raw `customers` table** (not even in the schema) on `customer_unique_id`, which duplicates rows: SP showed 2,375,243.35 instead of 2,171,490.16. |
| Best sellers | Clarify **worked** (2 seconds). |
| "yes" | Guessed, then wrote a query joining `sales` back onto itself: **50 identical rows**. |

**Lesson:** a 4B model is bad at editing its own previous SQL across turns, but good at single, fully specified questions.
**Fix (architecture):** rewrite each follow-up into a **standalone question**, then generate SQL with **no chat history**; show `(Interpreted as: ...)`; code guardrails blocking raw tables and rejecting duplicate-row results.

Accident: typed `python chat.py` **inside** the running chat. The agent answered with all-time totals (13,494,400.74 revenue, 98,199 orders, 94,983 customers) instead of saying it didn't understand. Logged as a test case.

### Run 3

| Turn | Failure |
|---|---|
| Compare with 2018 | The rewrite was right, but the SQL **added the two years together** (`purchase_year IN (2017, 2018)`) instead of side by side. |
| Best sellers → "by revenue" | **Clarification loop**: asked about the time period, then asked the same thing again. |

**Fix:** the rewrite must say "compared side by side"; a side-by-side example (conditional aggregation, one column per year); clarify only about the measure, never the period; rule "no period means all data"; code guard allowing **at most one clarifying question per request**; off-topic messages get `CANNOT`.

### Run 4 (reset was skipped by accident, which exposed a bug)

| Turn | Failure |
|---|---|
| Compare with 2018 | Per-state top 5 with both years mixed (accepted as a known limitation). |
| "yes" | Jumped back to the **old category question**: the rewriter saw the whole history. |
| "by revenue" | Old filters leaked in (delivered, 2017 vs 2018, by state) and it used `product_id` instead of `seller_id`. |
| "aishwarya" | Repeated the last answer. |
| Summary | Called AL "Alabama" and CE "California" (they are Brazilian states). |

**Fix:** clarification answers handled in code (bare "yes / ok / no" re-asks with no LLM call); rewriter returns non-questions unchanged; **summary number check** (unit-tested: a correct summary passes, an invented total of 3,012,758.67 is caught); no arithmetic; never expand state codes; **partial-year note added by code**.

### Run 5

| Turn | Failure |
|---|---|
| "by revenue" | Rewritten oddly ("compared side by side, broken down by revenue"); the SQL **inner-joined the top 10 by revenue with the top 10 by orders**, silently dropping sellers in only one list. |

**Fix:** attach the answer directly: `Who are our best sellers? (Clarification: by revenue)`.

Problem applying it: `git commit` said `agent.py` had no changes, so the patch had **never run**. It also revealed that `chat.py` and `prompts.py` changes from earlier steps had **never been committed**. Committed them, re-ran the patch, confirmed with `grep`.

### Side task: looking inside the database

- Installed the DuckDB CLI: `brew install duckdb`.
- Opened it with `duckdb -readonly data/olist.duckdb`; useful commands `.tables`, `DESCRIBE sales;`, `.mode line`, `.mode box`, `.quit`. The browser UI also exists: `duckdb -ui data/olist.duckdb`.
- Rule: close DuckDB sessions before re-running `load_data.py`.
- Wrote "join questions" to test multi-table queries: worst reviews by category, late deliveries vs reviews, delivery time by state, revenue by payment type (the fan-out trap).

### Run 6: join questions (no reset, on purpose)

| Turn | Failure |
|---|---|
| Worst reviews | Rewritten as "...compared side by side with their performance in 2017" (old context leaked), and it **clarified unnecessarily** ("average score or number of orders?"). |
| Result | Tiny categories ranked worst (`home_comfort_2`: 7 reviews). |
| Summary | Said diapers "dropped from 1.00 to 3.92" (that's a rise) and "only one order each year" (2018 had 24). Every number existed in the table, so the number check passed. |

**First fix proposed:** a keyword list to detect follow-ups, plus `HAVING COUNT(*) >= 30`.

**My pushback and changes:**

1. I changed the rule to "exclude outliers". Discussion: wrong concept, since the problem is sample size, not outliers, and the *worst* categories are the extremes; a vague instruction also makes a 4B model behave differently each run. Back to an explicit rule.
2. I then asked not to quantify at all. **Final decision:** never hide groups behind a threshold. Every per-group average must include an **order count column**, nothing is filtered out unless the user asks, and the summary says when some rows are based on far fewer orders (relative, no number). The user can then ask "only categories with at least 100 orders", making the cutoff an explicit, visible choice.
3. I rejected the keyword list as brittle and suggested "be extra careful when inferring follow-ups". Discussion: emphasis rarely changes a small model's behavior (the rewriter already had a "return unrelated questions unchanged" rule and ignored it). **Final decision:** a separate, narrow **LLM classifier** (FOLLOW_UP or NEW, with examples) before the rewrite. Lesson: small models fail at compound instructions, so split them into single-purpose calls.

### Ollama + Llama 3.2 experiment (later dropped)

| # | What we did | Outcome |
|---|---|---|
| 1 | Checked Ollama: `which ollama` → `/opt/homebrew/bin/ollama`, version 0.35.0, `ollama list` → `llama3.2:3b` (2.0 GB, downloaded earlier). | Already installed. |
| 2 | Unloaded LM Studio (`lms unload --all`) to free RAM; curl test against `http://localhost:11434/v1/chat/completions`. | Worked; Ollama ignored the thinking fields, so `llm.py` needed no change. |
| 3 | Created `Modelfile.llama` (`num_ctx 8192`, `temperature 0`) → `ollama create llama3.2-3b-8k`. Reason: Ollama's default context can silently truncate long prompts. | Measured the system prompt: **1,599 tokens** (fits). |
| 4 | Ran the agent on Llama (`LLM_BASE_URL=... LLM_MODEL=llama3.2-3b-8k python chat.py`). | Turns 1–3 same as Qwen and **faster** (7–14 s vs 14–35 s). Turn 4: **false refusal** ("categories table does not exist"), then a `UNION ALL` where the 2017 and 2018 columns held **identical numbers**. Summaries ignored the length rule and wrote lists. |
| 5 | That run exposed a **bug in our code**: after a `CLARIFY`, every new message was treated as its answer, so "Who are our best sellers?" and "What was our marketing spend?" got glued on as `(Clarification: ...)`. | **Fix:** the classifier decides whether a message after a clarifying question answers it or is a new question; two classifier examples for that case. The first patch attempt failed its own safety check (example text didn't match) and changed nothing; a more robust version worked. |
| 6 | Retest on Qwen: clarify → new question → clarify → "by number of orders". | All correct. Found the summary **mangled a seller ID** (dropped "744"). **Fix:** summaries never copy long IDs; refer to rows by rank. |
| 7 | Asked whether a better model exists. Researched: a June 2026 BIRD benchmark study (Qwen2.5-Coder dominates CodeLlama at 7B; self-correction is a near-free win, which supports our retry loop), OmniSQL, SQLCoder. SQL-only models would likely break clarify / cannot / summary, since the agent uses one model for four jobs. Qwen2.5-Coder 7B was the best candidate. | |
| 8 | Machine is an **M1 with 8 GB**. A 7B model (about 5.5 GB+) would likely swap or refuse to load. | **Decision:** stay with Qwen 3.5 4B; Qwen2.5-Coder 7B listed as a next step for 16 GB machines. Qwen2.5-Coder was **not downloaded**. |
| 9 | Decided **not to use Ollama**: `ollama stop llama3.2-3b-8k`, quit the Ollama app, removed `Modelfile.llama` from git and disk (`Modelfile.qwencoder` deleted too, if created). | Commit `f7602b6`. That `git commit -am` also included pending `agent.py` changes, so its message was incomplete (amend suggested). The `llama3.2:3b` and `llama3.2-3b-8k` models are still in Ollama's local store (not deleted). |

### Run 7: full 16-input regression test

| Test | Result |
|---|---|
| Top 5 categories 2017 | ✅ Exact |
| Break down, delivered | ✅ (top-5-combinations limitation) |
| Compare with 2018 | ⚠️ Known limitation; summary credited ES's 17,757.75 to SP |
| Worst reviews | ✅ No rewrite, no clarify, count column, small-sample warning |
| ≥ 100 orders | ✅ `HAVING ... >= 100` |
| Clarify, "yes", marketing | ✅ |
| Best sellers (second time) | ❌ Rewritten into "...current period compared side by side with last year" (old context leaked) |
| aishwarya, profit margin | ✅ |
| Late deliveries | ⚠️ Avg 2.55 / 4.17 with 7,826 / 90,373 orders; truth is **2.57 / 4.29** with **7,661 / 88,163**. Joined item-level `sales`, and undelivered orders counted as "on time". |
| Payment type | ❌ Rewritten into an invented 2017 vs 2018 comparison, and **joined `sales` with `payments`** (fan-out). |

**Fix:** classifier and rewriter see **only the latest answered question** (it's standalone, so it carries the state); if nothing was answered yet, skip the rewrite; rule 6 broadened to all per-order values; rule 11 for delivery and payment questions; code guardrail **blocking `sales` + `payments`**.

Mistake: pasted SQL straight into zsh (`command not found: SELECT`). SQL only runs inside DuckDB; switched to `duckdb -readonly data/olist.duckdb -c "..."`.

### Run 8

| Test | Result |
|---|---|
| Clarify → new question → clarify → "by number of orders" | ✅ No leaking; but ranked **seller states** instead of sellers (the prompt examples mention "seller state" three times). |
| Late deliveries | ⚠️ Counts now exactly right (7,661 / 88,163) but averages 2.55 / 4.21 vs **2.57 / 4.29**: still averaged over item-level `sales` rows. |
| Payment type | ⚠️ Guardrail blocked the bad join three times and the agent **honestly refused**. Correct behavior, but no answer. |
| "Break that down by customer state" **typed twice** | ❌ The rewriter **invented** "compared side by side with an earlier period, filtered to only count specific items" (parroting phrases from its own rules). |
| Then "only delivered" | ❌ Followed the invented question; reply was rambling model text ("Wait, I misread..."). |

**Planned fix (Step 18; applied in Phase 8 below):**

- New view **`order_facts`**: one row per order, all statuses, with `delivery_days`, `is_late` and the review score, so per-order questions can't average over items. Raw `orders` gets blocked like the other raw tables.
- Two examples: a payment question (`payments JOIN order_facts`) and a late-delivery question.
- Rule: "sellers" means `seller_id` unless the user says "seller state".
- Rewriter switched from rules to **examples**, including "already there → return unchanged" and "never add anything the user didn't ask for".
- Parser takes the model's **last** `CLARIFY:` / `CANNOT:` line, so rambling before it is ignored.

## Phase 8: Runtime, eval set, and moving decisions into code (Oct 4)

| # | What we did | Outcome |
|---|---|---|
| 1 | Switched the model server from LM Studio to Ollama (commit `5b564d0`), then checked that thinking really is off. | It is: 7 completion tokens in about 1 s, against 3,463 tokens and 260 s with thinking on. The ~25 s per question came from 3–4 LLM calls per turn, not from thinking. |
| 2 | Tried Qwen 3.5 4B at 8-bit (5.2 GB) to see whether 4-bit precision caused the wrong answers. | On 8 GB it ran 45% on the CPU and swapped heavily (100 to 2,700 s per question). It fixed one case and broke another. **Precision isn't the bottleneck**, so the model was deleted. |
| 3 | Set the edge target: a Raspberry Pi 5 with 4 GB or less, so small models and few calls. Switched to **llama.cpp** with LM Studio's text-only GGUF (2.7 GB, against Ollama's 3.4 GB file with the vision encoder bundled). | Same 6/9 on the early benchmark, about 20% faster. |
| 4 | Security review: the read-only DuckDB connection could still read files (`read_text`, `glob`, `SELECT * FROM 'file.csv'`). | `enable_external_access=False`; all six attempts now fail. |
| 5 | Built the eval harness (`eval/cases.py`, `eval/run_eval.py`); expected values from hand-written SQL. | Baseline **6/12**. |
| 6 | Applied Step 18 as the **`order_facts` view**: one row per order, lateness by date (an estimate has no time of day). The model first wrote `ELSE 'On-time'` (undelivered counted as on time), then read an "IS NOT NULL" rule as the definition of late, so a `delivery_status` label was added. | **12/15**; all per-order cases with no prompt example pass. |
| 7 | Relative periods from the data's latest date ("last quarter" = last complete quarter); São Paulo = the state unless "city"; split `is_canceled` (status only) from `is_sale`. | My own naming bug: `is_canceled` had included `unavailable`, so "canceled in 2017" gave 722 instead of 265. |
| 8 | Moved decisions into code (`checks.py`): clarify only for a vague ranking with no measure, refusals for things the data has sent back once, small talk and out-of-range years answered without the model; SQL structure checks (double counting, seller grouping, side by side, top-N); summary facts computed in code (`facts.py`). | **15 → 19 → 22 → 24/24.** Each prompt edit had shifted unrelated cases from run to run; the code checks didn't. |
| 9 | References to the previous answer ("it", "that seller", "the second one", "the previous year") resolved in code to one value; only that value reaches the rewrite model; ambiguous references get a clarifying question. | New eval cases exposed more wrong answers, each now caught by a check: filter values not in the data (`'Toys'`), identical period columns, one row per order id, grouping by an aggregated column, items counted as orders. |
| 10 | Friendly errors for a missing database or model server; data paths independent of the working folder; `OLIST_DB` for a variant dataset. | No more stack traces on setup mistakes. |
| 11 | Compared Ollama and llama.cpp on the full eval. | llama.cpp 33/34 in 812 s; Ollama 30/34 in 1,631 s (3 extra wrong answers). Different GGUF files and engine builds. **llama.cpp is the documented runtime.** |
| 12 | Trimmed the eval to 25 cases (the assignment asks for 15–25); 9 older bug cases kept as a separate regression set. | Final: **24/25** ([eval/RESULTS.md](../eval/RESULTS.md)). |

## Recurring lessons

1. **Rules half-work on a 4B model; data shape, examples and code checks work.** Most successful fixes moved a decision out of the prompt and into a view, an example or a guardrail.
2. **One narrow job per LLM call** (classify, rewrite, generate SQL, summarize) beats one call doing everything.
3. **The standalone question is the conversation state.**
4. **Plausible-but-wrong numbers are the real danger** (4.17 vs 4.29, inflated SP revenue). Hand-checked ground truth catches them; eyeballing doesn't.
5. **Show, don't hide**: sample sizes, interpreted questions, SQL and tables are always visible.
6. **A check that fires only once lets the same wrong SQL through on the next attempt.** Results that are never correct (identical period columns, one row per id) must be rejected every time; the agent then says it couldn't answer instead of showing a wrong number.
7. **Eval checks must be strict.** Several wrong answers passed by coincidence (the top seller is also the only seller in its city; a 4.14 somewhere in an unfiltered table) until the checks required the seller id and the filter in the SQL.

## Commits so far (known hashes)

| Hash | Message |
|---|---|
| `7d0a212` | Initial commit: project setup and gitignore |
| `1f7c97e` | Add data loader: CSVs into DuckDB |
| `2f04e6b` | Add data-quality checks |
| `00fc8d3` | Add cleaned sales and order_reviews views encoding data-quality rules |
| `72f472b` | Add schema-aware system prompt with live data coverage |
| `b0731ed` | Add agent loop with retries, clarify/cannot handling, memory, and terminal chat |
| `8e42f3c` | Code-level clarification handling, traceable summaries with number check, deterministic partial-year notes |
| `f7602b6` | Remove Ollama Modelfile; LM Studio + Qwen 3.5 4B is the supported setup |

Later commits (order_facts, eval set, code checks, references, error handling, final results) are in `git log --oneline`.

## Ground-truth numbers checked by hand

Verified with hand-written SQL in DuckDB. The eval's expected values (`eval/cases.py`) come from the same kind of SQL.

| Question | Correct answer |
|---|---|
| Top 5 categories by revenue, 2017 | bed_bath_table 497,970.94; watches_gifts 486,519.02; health_beauty 481,142.73; sports_leisure 447,546.59; computers_accessories 400,490.61 |
| Same, broken down by state (delivered, top combinations) | SP: bed_bath_table 204,224.73; watches_gifts 175,097.73; sports_leisure 163,351.59; health_beauty 154,878.74; computers_accessories 132,612.88 |
| Late vs on-time review score (delivered orders) | late **2.27** (6,381 orders); on time **4.29** (89,443 orders). Late = delivered after the estimated **date**; the estimate has no time of day, so delivery on the day is on time. (A timestamp comparison gives 2.57 / 7,661 and wrongly counts 1,292 same-day deliveries as late.) |
| Amount paid by payment type (excl. canceled / unavailable) | credit_card 12,350,042.56; boleto 2,826,802.30; voucher 349,874.40; debit_card 212,417.75 |
| Top sellers by number of orders | 6560211a19b47992c3666cc44a7e94c0: 1,847; 4a3ca9315b744ce9f8e9374361493884: 1,804; cc419e0650a3c5ba77189a1882b7556a: 1,697 |
| Top seller by revenue (all data) | 4869f7a5dfa277a7dca6462dcf3b52b2: 229,237.63 |
