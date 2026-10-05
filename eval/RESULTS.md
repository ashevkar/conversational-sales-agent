# Evaluation results

- **Model:** `qwen3.5-4b` served at `http://localhost:8080/v1`
- **Hardware:** Apple M1, 8 GB RAM, Darwin 25.2.0
- **Runs:** 1 (final, 2026-10-05 00:11)
- **Command:** `python eval/run_eval.py --tag <name>` then `python eval/report.py <result files>`
- **Expected values** come from hand-written SQL against the database (see the comments in `eval/cases.py`); the agent hardcodes none of them.

## Score

| Run | Passed | Total time | Avg per case | Avg LLM calls |
|---|---|---|---|---|
| final | **24/25** | 14.0 min | 33.7 s | 3.2 |

## By category

| Category | final |
|---|---|
| grounding | 7/7 |
| multi-turn | 3/3 |
| clarify | 3/3 |
| cannot | 4/4 |
| held-out | 1/1 |
| references | 6/7 |

## Every case

Time and LLM calls are averaged over the runs.

| Case | Category | final | Time | Calls |
|---|---|---|---|---|
| top 5 categories 2017 | grounding | ✅ | 9 s | 1.0 |
| late vs on-time reviews | grounding | ✅ | 8 s | 1.0 |
| amount paid by payment type | grounding | ✅ | 19 s | 2.0 |
| worst-reviewed categories | grounding | ✅ | 32 s | 3.0 |
| Sao Paulo last quarter | grounding | ✅ | 61 s | 2.0 |
| summary names the real peak month | grounding | ✅ | 34 s | 3.0 |
| row-level result with identical rows | grounding | ✅ | 24 s | 3.0 |
| assignment chain: top 5 -> state -> delivered -> 2018 | multi-turn | ✅ | 264 s | 15.0 |
| follow-up keeps the top 3 | multi-turn | ✅ | 39 s | 5.0 |
| new question after a clarifying question | multi-turn | ✅ | 16 s | 3.0 |
| best sellers asks to clarify | clarify | ✅ | 2 s | 1.0 |
| clarified best sellers by revenue | clarify | ✅ | 34 s | 4.0 |
| 'yes' to a clarifying question asks again | clarify | ✅ | 8 s | 2.0 |
| profit margin is out of scope | cannot | ✅ | 3 s | 1.0 |
| customer age is not in the data | cannot | ✅ | 2 s | 1.0 |
| year outside the data | cannot | ✅ | 0 s | 0.0 |
| not a data question | cannot | ✅ | 0 s | 0.0 |
| average delivery days by state | held-out | ✅ | 48 s | 3.0 |
| 'it' = the item the previous question asked for | references | ✅ | 46 s | 5.0 |
| 'that seller' | references | ✅ | 21 s | 3.0 |
| 'that category' after a list asks which one | references | ✅ | 6 s | 1.0 |
| 'the second one' | references | ❌ | 61 s | 6.0 |
| 'previous year' with no anchor asks, then answers | references | ✅ | 62 s | 6.0 |
| unrelated new question does not inherit the previous answer | references | ✅ | 14 s | 3.0 |
| naming a different item does not leak the listed ones | references | ✅ | 29 s | 5.0 |

## Failures

- **'the second one'** (final): turn 2: SQL missing ['watches_gifts']; turn 2: kind=error: Sorry, I couldn't build a working query for that, so I won't guess. Last error: Every group has exactly one row, so the query groups by a unique id (such as order_id). Remove it from GROUP BY to aggregate across rows; for one overall number, use no GROUP BY at all.
  The reference resolved correctly ("What was the average review score of watches_gifts in 2017?"), but none of the 4 SQL attempts passed the code checks, so the agent refused instead of guessing. Full exchange and explanation: [README, Evaluation and tests](../README.md#evaluation-and-tests); raw record: [results/final.json](results/final.json).
