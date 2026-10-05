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
