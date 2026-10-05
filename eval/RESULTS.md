# Evaluation results

- **Model:** `qwen3.5-4b` served at `http://localhost:8080/v1`
- **Hardware:** Apple M1, 8 GB RAM, Darwin 25.2.0
- **Runs:** 1 (final, 2026-10-04 22:39)
- **Command:** `python eval/run_eval.py --tag <name>` then `python eval/report.py <result files>`
- **Expected values** come from hand-written SQL against the database (see the comments in `eval/cases.py`); the agent hardcodes none of them.

## Score

| Run | Passed | Total time | Avg per case | Avg LLM calls |
|---|---|---|---|---|
| final | **24/25** | 7.9 min | 19.0 s | 3.2 |

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
| top 5 categories 2017 | grounding | ✅ | 4 s | 1.0 |
| late vs on-time reviews | grounding | ✅ | 4 s | 1.0 |
| amount paid by payment type | grounding | ✅ | 11 s | 2.0 |
| worst-reviewed categories | grounding | ✅ | 16 s | 3.0 |
| Sao Paulo last quarter | grounding | ✅ | 31 s | 2.0 |
| summary names the real peak month | grounding | ✅ | 16 s | 3.0 |
| row-level result with identical rows | grounding | ✅ | 13 s | 3.0 |
| assignment chain: top 5 -> state -> delivered -> 2018 | multi-turn | ✅ | 148 s | 15.0 |
| follow-up keeps the top 3 | multi-turn | ✅ | 29 s | 5.0 |
| new question after a clarifying question | multi-turn | ✅ | 12 s | 3.0 |
| best sellers asks to clarify | clarify | ✅ | 2 s | 1.0 |
| clarified best sellers by revenue | clarify | ✅ | 18 s | 4.0 |
| 'yes' to a clarifying question asks again | clarify | ✅ | 4 s | 2.0 |
| profit margin is out of scope | cannot | ✅ | 2 s | 1.0 |
| customer age is not in the data | cannot | ✅ | 1 s | 1.0 |
| year outside the data | cannot | ✅ | 0 s | 0.0 |
| not a data question | cannot | ✅ | 0 s | 0.0 |
| average delivery days by state | held-out | ✅ | 26 s | 3.0 |
| 'it' = the item the previous question asked for | references | ✅ | 22 s | 5.0 |
| 'that seller' | references | ✅ | 12 s | 3.0 |
| 'that category' after a list asks which one | references | ✅ | 3 s | 1.0 |
| 'the second one' | references | ❌ | 35 s | 6.0 |
| 'previous year' with no anchor asks, then answers | references | ✅ | 39 s | 6.0 |
| unrelated new question does not inherit the previous answer | references | ✅ | 8 s | 3.0 |
| naming a different item does not leak the listed ones | references | ✅ | 19 s | 5.0 |

## Failures

- **'the second one'** (final): turn 2: SQL missing ['watches_gifts']; turn 2: kind=error: Sorry, I couldn't build a working query for that, so I won't guess. Last error: 
