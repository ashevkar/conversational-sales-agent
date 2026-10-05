# Evaluation results

- **Model:** `qwen3.5-4b` served at `http://localhost:8080/v1`
- **Hardware:** Apple M1, 8 GB RAM, Darwin 25.2.0
- **Runs:** 1 (final, 2026-10-05 12:17)
- **Command:** `python eval/run_eval.py --tag <name>` then `python eval/report.py <result files>`
- **Expected values** come from hand-written SQL against the database (see the comments in `eval/cases.py`); the agent hardcodes none of them.

## Score

| Run | Passed | Total time | Avg per case | Avg LLM calls |
|---|---|---|---|---|
| final | **25/25** | 8.0 min | 19.2 s | 3.1 |

## By category

| Category | final |
|---|---|
| grounding | 7/7 |
| multi-turn | 3/3 |
| clarify | 3/3 |
| cannot | 4/4 |
| held-out | 1/1 |
| references | 7/7 |

## Every case

Time and LLM calls are averaged over the runs.

| Case | Category | final | Time | Calls |
|---|---|---|---|---|
| top 5 categories 2017 | grounding | ✅ | 14 s | 1.0 |
| late vs on-time reviews | grounding | ✅ | 4 s | 1.0 |
| amount paid by payment type | grounding | ✅ | 4 s | 1.0 |
| worst-reviewed categories | grounding | ✅ | 17 s | 3.0 |
| Sao Paulo last quarter | grounding | ✅ | 6 s | 1.0 |
| summary names the real peak month | grounding | ✅ | 18 s | 3.0 |
| row-level result with identical rows | grounding | ✅ | 9 s | 2.0 |
| assignment chain: top 5 -> state -> delivered -> 2018 | multi-turn | ✅ | 152 s | 15.0 |
| follow-up keeps the top 3 | multi-turn | ✅ | 24 s | 5.0 |
| new question after a clarifying question | multi-turn | ✅ | 7 s | 3.0 |
| best sellers asks to clarify | clarify | ✅ | 2 s | 1.0 |
| clarified best sellers by revenue | clarify | ✅ | 30 s | 4.0 |
| 'yes' to a clarifying question asks again | clarify | ✅ | 4 s | 2.0 |
| profit margin is out of scope | cannot | ✅ | 2 s | 1.0 |
| customer age is not in the data | cannot | ✅ | 1 s | 1.0 |
| year outside the data | cannot | ✅ | 0 s | 0.0 |
| not a data question | cannot | ✅ | 0 s | 0.0 |
| average delivery days by state | held-out | ✅ | 22 s | 3.0 |
| 'it' = the item the previous question asked for | references | ✅ | 26 s | 5.0 |
| 'that seller' | references | ✅ | 24 s | 5.0 |
| 'that category' after a list asks which one | references | ✅ | 5 s | 1.0 |
| 'the second one' | references | ✅ | 28 s | 5.0 |
| 'previous year' with no anchor asks, then answers | references | ✅ | 42 s | 6.0 |
| unrelated new question does not inherit the previous answer | references | ✅ | 14 s | 4.0 |
| naming a different item does not leak the listed ones | references | ✅ | 22 s | 5.0 |

## Failures

None.
