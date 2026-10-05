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
- A free Kaggle account to download the data.

## Setup

**1. Start the model server.** This downloads Qwen 3.5 4B (Q4_K_M, about 2.7 GB) on the first run, then serves it on port 8080. Keep it running in its own terminal.

```bash
brew install llama.cpp          # Linux: see github.com/ggml-org/llama.cpp for builds
llama-server -hf lmstudio-community/Qwen3.5-4B-GGUF:Q4_K_M --no-mmproj \
  --port 8080 -c 8192 -np 1 --jinja --reasoning-budget 0 --alias qwen3.5-4b
```

`--reasoning-budget 0` turns off Qwen's thinking (otherwise thousands of tokens per answer); `--no-mmproj` skips the image encoder the agent doesn't use; `-np 1` keeps the full 8k context in one slot.

**2. Python environment.**

```bash
git clone https://github.com/ashevkar/conversational-sales-agent.git && cd conversational-sales-agent
python3.12 -m venv .venv && source .venv/bin/activate      # or: uv venv --python 3.12
pip install -r requirements.txt
```

**3. Data.** Download the dataset zip from [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) and put the 9 CSVs directly in `data/`:

```bash
mkdir -p data && unzip ~/Downloads/archive.zip -d data
# if the zip created data/archive/ (and data/__MACOSX/), flatten it:
mv data/archive/*.csv data/ 2>/dev/null; rm -rf data/archive data/__MACOSX
ls data/*.csv | wc -l        # 9
```

**4. Build the database** (`data/olist.duckdb`, under a minute):

```bash
python load_data.py
```

**5. Chat.**

```bash
python chat.py               # 'reset' starts a new conversation, 'quit' exits
```

If the model server isn't running or the database is missing, `chat.py` says what to do instead of crashing. Answers take about 3–60 seconds on a laptop.

## Evaluation and tests

```bash
python eval/run_eval.py --tag mine      # the 25 eval questions, about 10–15 minutes
python eval/report.py eval/results/mine.json   # writes eval/RESULTS.md
for t in tests/test_*.py; do python "$t"; done # 34 unit tests of the code checks, no model needed
```

`python eval/run_eval.py --regression` runs a separate set of 9 older bug cases. Expected values were computed with hand-written SQL against this dataset; on a different dataset the eval's numbers won't match, but the agent itself hardcodes none of them.

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

| Path | Purpose |
|---|---|
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
| `Modelfile` | Ollama model definition (alternative runtime) |

## Troubleshooting

- **"Can't reach the model server"**: start `llama-server` (step 1) and wait for "server is listening", or set `LLM_BASE_URL`.
- **"Database not found" / "missing order_facts"**: run `python load_data.py` (again after updating the code).
- **Slow answers or swapping on 8 GB**: close other heavy apps; make sure only one model server is running.

## How AI tools were used

Built step by step with Claude (Anthropic) as a pair programmer: it proposed code, prompts and fixes; every step was run, tested and committed by me on my own machine (later commits made through Claude Code carry a `Co-Authored-By` line), and several suggestions were challenged and changed (the outlier rule, the fixed threshold, the keyword list, the choice of model server). All test runs, failures and numbers come from real runs on my laptop.
