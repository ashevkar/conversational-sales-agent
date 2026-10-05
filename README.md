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

**1. Install.** Clone the repository, save the script below as `install.sh` in the repository folder, and run it:

```bash
git clone https://github.com/ashevkar/conversational-sales-agent.git && cd conversational-sales-agent
bash install.sh
```

It installs llama.cpp and the DuckDB CLI (Homebrew, or DuckDB's own installer), creates `.venv` with the packages in `requirements.txt` (including `duckdb`), downloads the Olist CSVs from Kaggle into `data/` (or uses `~/Downloads/archive.zip` if it's there), builds `data/olist.duckdb`, and downloads the model (Qwen 3.5 4B Q4_K_M, about 2.7 GB). Finished steps are skipped, so it's safe to re-run. It falls back to other routes where it can (uv or Homebrew Python, `pip` upgrade, `unzip` or Python's `zipfile`); any step it still can't complete is listed at the end with the command to run by hand.

<details>
<summary><code>install.sh</code></summary>

```bash
#!/usr/bin/env bash
# Setup for the conversational sales agent. Run from the repository folder.
# Installs llama.cpp and the DuckDB CLI, creates .venv, downloads the Olist data,
# builds data/olist.duckdb and downloads the model. Safe to re-run: finished
# steps are skipped. Failed steps are listed at the end with manual commands.

if [ ! -f requirements.txt ] || [ ! -f load_data.py ]; then
  echo "Run this from the conversational-sales-agent folder."; exit 1
fi
ROOT="$(pwd)"
VENV="$ROOT/.venv"
DATA="$ROOT/data"
MODEL_REPO="lmstudio-community/Qwen3.5-4B-GGUF:Q4_K_M"
KAGGLE_URL="https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"

if [ -t 1 ]; then B=$'\033[1m' G=$'\033[32m' Y=$'\033[33m' R=$'\033[31m' N=$'\033[0m'; else B= G= Y= R= N=; fi
OK=(); FAILED=(); SKIPPED=()
step() { printf '\n%s==> %s%s\n' "$B" "$*" "$N"; }
ok()   { printf '%s  ok%s  %s\n' "$G" "$N" "$*"; }
warn() { printf '%s  !!%s  %s\n' "$Y" "$N" "$*"; }
pass() { OK+=("$1"); }
fail() { FAILED+=("$1|$2"); printf '%s  failed%s  %s\n' "$R" "$N" "$1"; }
skip() { SKIPPED+=("$1|$2"); warn "skipped: $2"; }
has()  { command -v "$1" >/dev/null 2>&1; }

# ---- llama.cpp (model server)
step "llama.cpp"
if has llama-server; then
  ok "already installed"; pass "llama.cpp"
elif has brew && brew install llama.cpp && has llama-server; then
  ok "installed with Homebrew"; pass "llama.cpp"
else
  has brew || warn "Homebrew not found (https://brew.sh)"
  fail "llama.cpp" "brew install llama.cpp   # or a release build from https://github.com/ggml-org/llama.cpp"
fi

# ---- DuckDB CLI (the agent uses the duckdb Python package; the CLI is for browsing the database)
step "DuckDB CLI"
if has duckdb; then
  ok "already installed"; pass "DuckDB CLI"
elif has brew && brew install duckdb && has duckdb; then
  ok "installed with Homebrew"; pass "DuckDB CLI"
elif has curl && curl -fsSL https://install.duckdb.org | sh && [ -x "$HOME/.duckdb/cli/latest/duckdb" ]; then
  ok "installed to ~/.duckdb/cli/latest (add it to your PATH)"; pass "DuckDB CLI"
else
  fail "DuckDB CLI" "brew install duckdb   # or: curl https://install.duckdb.org | sh"
fi

# ---- Python environment (.venv + requirements.txt, which includes duckdb)
step "Python environment"
find_python() {
  for py in python3.12 python3.13 python3.11 python3.10 python3; do
    if has "$py" && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      command -v "$py"; return 0
    fi
  done
  return 1
}
venv_ok()     { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import sys' 2>/dev/null; }
deps_ok()     { "$VENV/bin/python" -c 'import duckdb, openai' 2>/dev/null; }
has_pip()     { "$VENV/bin/python" -m pip --version >/dev/null 2>&1; }
pip_install() { "$VENV/bin/python" -m pip install -q -r requirements.txt && deps_ok; }

PY_READY=0
if venv_ok; then
  ok "reusing .venv ($("$VENV/bin/python" --version 2>&1))"
else
  make_venv() { rm -rf "$VENV"; "$@" && venv_ok; }   # clears a half-made .venv first
  PY="$(find_python)"
  if [ -n "$PY" ] && make_venv "$PY" -m venv "$VENV"; then
    ok "created .venv with $("$PY" --version 2>&1)"
  elif has uv && make_venv uv venv -q --python 3.12 "$VENV"; then
    ok "created .venv with uv (Python 3.12)"
  elif [ "$(uname -s)" = Darwin ] && has brew && brew install python@3.12 \
       && make_venv "$(brew --prefix)/bin/python3.12" -m venv "$VENV"; then
    ok "installed Python 3.12 with Homebrew and created .venv"
  else
    rm -rf "$VENV"
    [ -z "$PY" ] && warn "no Python 3.10+ found"
    fail "Python venv" "python3.12 -m venv .venv   # Debian/Ubuntu may need: apt install python3-venv"
  fi
fi
if venv_ok; then
  echo "  installing requirements.txt (duckdb, openai, ...)"
  # uv makes venvs without pip; ensurepip adds it where the Python ships it.
  has_pip || "$VENV/bin/python" -m ensurepip -q >/dev/null 2>&1
  if has_pip && pip_install; then
    PY_READY=1
  elif has_pip && "$VENV/bin/python" -m pip install -q --upgrade pip && pip_install; then
    PY_READY=1   # pip was too old for the pinned wheels
  elif has uv && uv pip install -q --python "$VENV/bin/python" -r requirements.txt && deps_ok; then
    PY_READY=1
  fi
  if [ "$PY_READY" = 1 ]; then ok "requirements installed"; pass "Python environment"
  else fail "Python packages" "source .venv/bin/activate && pip install -r requirements.txt"; fi
else
  skip "Python packages" "no virtual environment"
fi

# ---- Olist dataset (9 CSVs directly in data/)
step "Olist dataset"
csv_count() { ls "$DATA"/*.csv 2>/dev/null | wc -l | tr -d ' '; }
extract_zip() {   # unzip $1 into data/, flattening any folder inside the zip
  local tmp; tmp="$(mktemp -d)" || return 1
  if has unzip; then unzip -q -o "$1" -d "$tmp"
  else "$(find_python)" -m zipfile -e "$1" "$tmp"; fi || { rm -rf "$tmp"; return 1; }
  mkdir -p "$DATA"
  find "$tmp" -name '*.csv' -not -path '*__MACOSX*' -exec mv -f {} "$DATA"/ \;
  rm -rf "$tmp"
}
DATA_READY=0
if [ "$(csv_count)" -ge 9 ]; then
  ok "data/ already has $(csv_count) CSVs"; DATA_READY=1
else
  # A zip already downloaded from Kaggle (OLIST_ZIP=path overrides), else download it.
  for z in "$OLIST_ZIP" "$HOME/Downloads/archive.zip" "$HOME/Downloads/brazilian-ecommerce.zip"; do
    if [ -n "$z" ] && [ -f "$z" ]; then
      echo "  using $z"
      extract_zip "$z" && [ "$(csv_count)" -ge 9 ] && { DATA_READY=1; break; }
    fi
  done
  if [ "$DATA_READY" = 0 ] && has curl; then
    echo "  downloading from Kaggle (about 45 MB)"
    DL="$(mktemp -d)"
    curl -fL --retry 3 --progress-bar -o "$DL/olist.zip" "$KAGGLE_URL" && extract_zip "$DL/olist.zip" \
      && [ "$(csv_count)" -ge 9 ] && DATA_READY=1
    rm -rf "$DL"
  fi
  if [ "$DATA_READY" = 1 ]; then ok "data/ has $(csv_count) CSVs"
  else fail "Olist dataset" "download the zip from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce to ~/Downloads and re-run"; fi
fi
[ "$DATA_READY" = 1 ] && pass "Olist dataset"

# ---- DuckDB database (rebuilt every run, under a minute, so the views match the code)
step "DuckDB database"
if [ "$PY_READY" = 1 ] && [ "$DATA_READY" = 1 ]; then
  if "$VENV/bin/python" load_data.py; then pass "DuckDB database"
  else fail "DuckDB database" "source .venv/bin/activate && python load_data.py"; fi
else
  skip "DuckDB database" "needs the Python environment and the dataset"
fi

# ---- Model weights. llama-server has no download-only mode: start it on a spare
# port, wait until the model has loaded (so it's in the cache), then stop it.
step "Model weights (Qwen 3.5 4B, about 2.7 GB)"
model_cached() { llama-server --cache-list 2>/dev/null | grep -q "$MODEL_REPO"; }
download_model() {
  local port=8099 log pid i
  log="$(mktemp)"
  llama-server -hf "$MODEL_REPO" --no-mmproj --port "$port" -c 512 -np 1 >"$log" 2>&1 &
  pid=$!
  for i in $(seq 1 3600); do   # up to an hour on a slow connection
    if ! kill -0 "$pid" 2>/dev/null; then tail -5 "$log"; rm -f "$log"; return 1; fi
    if curl -fs "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      kill "$pid"; wait "$pid" 2>/dev/null; rm -f "$log"; return 0
    fi
    [ $((i % 30)) = 0 ] && echo "  still downloading ($((i / 60)) min)"
    sleep 1
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; rm -f "$log"; return 1
}
if ! has llama-server; then
  skip "Model weights" "needs llama.cpp"
elif model_cached; then
  ok "already downloaded"; pass "Model weights"
elif echo "  downloading (one time)" && download_model && model_cached; then
  ok "downloaded"; pass "Model weights"
else
  fail "Model weights" "llama-server -hf $MODEL_REPO --no-mmproj --port 8080   # downloads on first start"
fi

# ---- Summary
step "Summary"
for s in "${OK[@]}"; do ok "$s"; done
for s in "${SKIPPED[@]}"; do [ -n "$s" ] && warn "${s%%|*}: skipped (${s#*|})"; done
if [ "${#FAILED[@]}" -gt 0 ]; then
  printf '\n%sThese steps failed. Run them manually, then re-run the script:%s\n' "$R$B" "$N"
  for f in "${FAILED[@]}"; do printf '  %s- %s%s\n      %s\n' "$B" "${f%%|*}" "$N" "${f#*|}"; done
  exit 1
fi
printf '\n%sSetup complete.%s Next: start the model server (step 2), then: source .venv/bin/activate && python chat.py\n' "$G$B" "$N"
```

</details>

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
