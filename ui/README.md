# Web UI

A browser chat for the agent, alongside the terminal chat (`chat.py`).

`server.py` uses only the Python standard library. It imports the agent from the repository root (no agent code is changed) and serves the page in `static/` (plain HTML, CSS and JavaScript; no build step, no Node). [GSAP](https://gsap.com) for the animations is included in `static/vendor/`, so the UI works fully offline.

## Run

1. Start the model server and build the database as in the main [README](../README.md).
2. From the repository root, with the virtualenv active:

   ```bash
   python ui/server.py
   ```

3. Open http://127.0.0.1:8000.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port for the web page |
| `HOST` | `127.0.0.1` | Interface to listen on (local only by default) |
| `AGENT_DIR` | the repository root | Where the agent code lives |
| `LLM_BASE_URL`, `LLM_MODEL`, `OLIST_DB` | see the main README | Passed straight through to the agent |

## What it shows

- **Answers** as a summary plus a card with metric tiles. Every value on a tile is copied from the result table (a single row's values, or the row count and the highest and lowest row); nothing is computed in the browser. "Show result table" expands the full result.
- **Clarifying questions, refusals and errors** as labelled callouts; greetings get a plain friendly reply.
- **Follow up** on the latest answer shows the question you're following up on (and, when the agent expanded it, the full question it understood); the sent question then carries a "Following up on …" quote.
- **Conversations** in the sidebar, saved in the browser's `localStorage` (newest 30, nothing stored on the server). A chat's id is also its server session id, so a reopened chat keeps its follow-up context while `server.py` keeps running.
- **Status**: the sidebar card and header badge check the model server through `/api/health`.
- Light and dark themes (follows the system until you choose), a phone layout with a slide-out sidebar, and animations that switch off when the system asks for reduced motion.

The SQL behind each answer is not shown in the UI; the terminal chat prints it and `eval/results/final.json` records it for every eval answer.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/info` | Model name and server URL |
| `GET /api/health` | Whether the model server is reachable |
| `POST /api/chat` `{session, message}` | The agent's reply: `kind`, `text`, `question`, `sql`, `table`, `attempts`, `elapsed` |
| `POST /api/reset` `{session}` | Clears that conversation |
