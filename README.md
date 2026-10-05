# Conversational Sales Analytics Agent (Olist)

Ask questions about the [Olist Brazilian e-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) in plain English, in a multi-turn conversation. The agent runs **fully locally**: a 4B open-weight model (Qwen 3.5 4B) writes SQL, DuckDB runs it read-only, and every answer shows the SQL and result table it came from. It asks a clarifying question when a request is genuinely ambiguous, and says so when the data can't answer.

**Eval: 24/25** on an 8 GB Apple M1 ([eval/RESULTS.md](eval/RESULTS.md)). How it works: [DESIGN.md](DESIGN.md). Everything tried along the way: [docs/DEVLOG.md](docs/DEVLOG.md).

```
You: What were our top 5 product categories by revenue in 2017?
Agent: bed_bath_table (revenue 497,970.94); watches_gifts (revenue 486,519.02); ...
You: Break that down by customer state.
(Interpreted as: What were our top 5 product categories by revenue in 2017, broken down by customer state?)
You: Who are our best sellers?
Agent: Do you mean "best" by total revenue generated, number of orders sold, or average review score?
```

## Requirements

- macOS or Linux, 8 GB RAM or more (16 GB recommended), about 4 GB of disk for the model.
- Python 3.12 (3.10+ should work).
- [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`); Ollama works as an alternative.
- Homebrew (macOS, or Linux for llama.cpp), `curl` and an internet connection for the install.

## Setup

**1. Install.** Clone the repository and run the setup script, [`install.sh`](install.sh):

```bash
git clone https://github.com/ashevkar/conversational-sales-agent.git && cd conversational-sales-agent
bash install.sh
```

It installs llama.cpp and the DuckDB CLI (Homebrew, or DuckDB's own installer), creates `.venv` with the packages in `requirements.txt` (including `duckdb`), downloads the Olist CSVs from Kaggle into `data/` (or uses `~/Downloads/archive.zip` if it's there), builds `data/olist.duckdb`, and downloads the model (Qwen 3.5 4B Q4_K_M, about 2.7 GB). Finished steps are skipped, so it's safe to re-run. It falls back to other routes where it can (uv or Homebrew Python, `pip` upgrade, `unzip` or Python's `zipfile`); any step it still can't complete is listed at the end with the command to run by hand.

**2. Start the model server.** It serves the downloaded model on port 8080. Keep it running in its own terminal.

```bash
llama-server -hf lmstudio-community/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj \
  --port 8080 -c 8192 -np 1 --jinja --reasoning-budget 0 --alias qwen3.5-4b
```

`--reasoning-budget 0` turns off Qwen's thinking (otherwise thousands of tokens per answer); `--no-mmproj` skips the image encoder the agent doesn't use; `-np 1` keeps the full 8k context in one slot.

**3. Chat.**

```bash
source .venv/bin/activate
python chat.py               # 'reset' starts a new conversation, 'quit' exits
```

If the model server isn't running or the database is missing, `chat.py` says what to do instead of crashing. Answers take about 3–60 seconds on a laptop.

**4. Web UI.** The same agent in a browser chat, with the model server from step 2 running:

```bash
python ui/server.py          # then open http://127.0.0.1:8000
```

See [ui/README.md](ui/README.md) for what it shows.



## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:8080/v1` | Any OpenAI-compatible local server |
| `LLM_MODEL` | `qwen3.5-4b` | Model name the server knows |
| `LLM_TIMEOUT` | `300` | Seconds before a model call gives up |
| `OLIST_DB` | `data/olist.duckdb` | Database to query (e.g. one built from a variant of the dataset) |
| `OLIST_DATA_DIR` | `data/` | Where `load_data.py` reads the CSVs |

**Using Ollama instead of llama.cpp** (it worked, but scored 30/34 against 33/34 and was about 2× slower in our comparison; see DESIGN.md):

```bash
ollama pull qwen3.5:4b
ollama create qwen3.5-4b-8k -f Modelfile      # 8k context, temperature 0
LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen3.5-4b-8k python chat.py
```

## Project structure

```
conversational-sales-agent/
├── agent.py            pipeline: resolve the question, generate SQL, validate, run, summarise
├── checks.py           code checks on decisions, SQL and results; reference resolution
├── facts.py            summary facts computed in code
├── prompts.py          system prompt from the live schema and data coverage
├── db.py               read-only DuckDB access with SQL guardrails
├── llm.py              client for the local model server
├── chat.py             terminal chat
├── load_data.py        CSVs -> data/olist.duckdb, with the cleaned views
├── data_checks.py      data-quality findings
├── install.sh          one-step setup (llama.cpp, .venv, data, database, model)
├── ui/
│   ├── server.py       web chat server (standard library only)
│   ├── README.md
│   └── static/         index.html, style.css, app.js, vendor/gsap.min.js
├── eval/
│   ├── cases.py        the 25 eval questions (+ regression set)
│   ├── run_eval.py     runs them against the agent
│   ├── report.py       writes RESULTS.md
│   ├── RESULTS.md
│   └── results/final.json
├── tests/              unit tests (no model needed)
├── docs/DEVLOG.md      development log
├── DESIGN.md
├── README.md
├── Modelfile           Ollama model definition (alternative runtime)
├── requirements.txt
└── data/               Olist CSVs and olist.duckdb (downloaded, not in git)
```

| Path | Purpose |
|---|---|
| `install.sh` | One-step setup: llama.cpp, DuckDB CLI, `.venv`, Olist data, database, model |
| `load_data.py` | Loads the CSVs into DuckDB and creates the cleaned views `sales` and `order_facts` |
| `data_checks.py` | Prints the data-quality findings behind the cleaning decisions |
| `prompts.py` | Builds the system prompt from the live schema and data coverage |
| `agent.py` | The pipeline: resolve the question, generate SQL, validate, run, summarise |
| `checks.py` | Code checks on the model's decisions, its SQL and its results; reference resolution |
| `facts.py` | Summary facts computed in code |
| `db.py` | Read-only DuckDB access with SQL guardrails |
| `llm.py` | Client for the local model server, with clear connection errors |
| `chat.py` | Terminal chat |
| `eval/` | Eval questions, runner, report and final results |
| `tests/` | Unit tests for the code checks and error handling |
| `ui/` | Web chat for the same agent ([ui/README.md](ui/README.md)) |
| `Modelfile` | Ollama model definition (alternative runtime) |

## Evaluation and tests

```bash
python eval/run_eval.py --tag mine      # the 25 eval questions, about 10–15 minutes
python eval/report.py eval/results/mine.json   # writes eval/RESULTS.md
for t in tests/test_*.py; do python "$t"; done # 34 unit tests of the code checks, no model needed
```

`python eval/run_eval.py --regression` runs a separate set of 9 older bug cases. Expected values were computed with hand-written SQL against this dataset; on a different dataset the eval's numbers won't match, but the agent itself hardcodes none of them.

**The one failure ('the second one').** The full exchange from the final run:

```
You: Top 5 categories by revenue in 2017
Agent: bed_bath_table (revenue 497,970.94); watches_gifts (revenue 486,519.02); health_beauty (revenue 481,142.73); sports_leisure (revenue 447,546.59); computers_accessories (revenue 400,490.61).
You: What was the average review score of the second one?
(Interpreted as: What was the average review score of watches_gifts in 2017?)
Agent: Sorry, I couldn't build a working query for that, so I won't guess. Last error: Every group has exactly one row, so the query groups by a unique id (such as order_id). Remove it from GROUP BY to aggregate across rows; for one overall number, use no GROUP BY at all.
```

The reference resolved correctly ("the second one" → `watches_gifts`), but none of the model's 4 SQL attempts passed the code checks; the last one grouped by a unique id, so every group had one row. The agent refuses instead of returning a wrong number. The eval marks it failed because no SQL filtering on `watches_gifts` was produced. The eval runner keeps only the first 80 characters of a reply in its failure reason, so the full reply was added to [eval/RESULTS.md](eval/RESULTS.md) by hand.


## Troubleshooting

- **"Can't reach the model server"**: start `llama-server` (step 2) and wait for "server is listening", or set `LLM_BASE_URL`.
- **"Database not found" / "missing order_facts"**: run `python load_data.py` (again after updating the code), or re-run `bash install.sh`.
- **Slow answers or swapping on 8 GB**: close other heavy apps; make sure only one model server is running.

## How AI tools were used

Built step by step with Claude (Anthropic) as a pair programmer: it proposed code, prompts and fixes; every step was run, tested and committed by me on my own machine (later commits made through Claude Code carry a `Co-Authored-By` line), and several suggestions were challenged and changed (the outlier rule, the fixed threshold, the keyword list, the choice of model server). All test runs, failures and numbers come from real runs on my laptop.
