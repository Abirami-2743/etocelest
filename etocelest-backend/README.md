# ÉTOCELEST backend

FastAPI service that runs a structured adversarial review of a space-mission launch date.
Four domain agents (Astro-Weather, Logistics, Crew Readiness, Mission Value) powered by **Groq**
debate in rounds, reading each other's turns. A **Judge** reads the debate after every round and either
rules or sends it back with specific questions. **The Judge always concludes**: at the round cap it is
forced to rule, and if even that call fails a documented mechanical ruling (median of the agents' final
positions) is issued and labelled `fallback`.

## MongoDB (pick one)

- **Atlas (no install):** create a free cluster at https://www.mongodb.com/atlas, add a database user,
  allow your IP under Network Access, copy the connection string into `MONGODB_URI`.
- **Docker:** `docker compose up -d mongo` (uses `docker-compose.yml`), then `MONGODB_URI=mongodb://localhost:27017`.
- **Local install:** MongoDB Community Server from mongodb.com, default URI works.

Collections `missions` and `mission_events` and their indexes are created automatically at startup.
No replica set / transactions are required.

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set GROQ_API_KEY and MONGODB_URI
uvicorn app.main:app_factory --factory --port 8000
```

Docker: `docker build -t etocelest-api . && docker run -p 8000:8000 --env-file .env etocelest-api`

Tests: `pip install -r requirements-dev.txt && pytest` (uses a fake Groq server; no key needed).

## How a review works

The debate is a [LangGraph](https://langchain-ai.github.io/langgraph/) state graph (`app/services/debate_graph.py`).
The graph owns the control flow; `DebateEngine` (`app/services/engine.py`) supplies the work done at each node.

```
START -> ground -> agents -> judge --(objections remain)--> agents
           |                   |
           |                   +--(ruled, or cap reached)--> finalize -> END
           +--(log already holds every round)--> fallback -> finalize
```

- One compiled graph is shared by all concurrent debates; per-run data (mission, brief) travels in LangGraph's
  `context`, never in globals.
- Durability is the persisted **event log**, not a LangGraph checkpointer: it is also what the UI's SSE replay
  reads. A resumed run seeds the graph state from that log and continues at the next round.
- The loop is bounded by construction (the router sends anything at the round cap to `finalize`), and the
  LangGraph step budget is derived from the mission's `max_rounds` plus `GRAPH_STEP_HEADROOM`.

1. `POST /api/missions` stores the mission and starts a background debate.
2. Round *r*: agents speak sequentially (order rotates each round). Each sees the mission brief, grounding data,
   the full transcript so far and the Judge's open questions. Each returns a validated JSON turn: message,
   proposed shift, acceptable range, hard-limit flag.
3. The Judge sees everything plus a **code-computed overlap** of the agents' acceptable ranges. Before
   `MIN_ROUNDS` it may only reopen; after, it may rule; at `MAX_ROUNDS` it must rule.
4. Resolution is derived by code, not self-reported: `consensus` (ruling inside the overlap), `judge_decision`,
   `forced_ruling` (cap reached, no consensus), `fallback` (Judge model unavailable). Confidence is capped
   per resolution (100 / 85 / 75 / 40).

**Grounding:** the Astro-Weather prompt (and all agents) receive the NOAA SWPC *predicted solar cycle*
for the launch month ±2 (sunspot number, F10.7). The forecast covers a limited horizon; outside it the agents
are told no data exists and must not invent numbers. Agents must label any number not in the brief or
grounding as an assumption. Nothing in the debate is canned.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | liveness, DB, models |
| GET | `/api/agents`, `/api/presets` | presets use relative lead times so they never go stale |
| POST | `/api/missions` | `{name, launchDate, context}` → `{missionId}` |
| GET | `/api/missions`, `/api/missions/{id}` | scoped to the caller |
| DELETE | `/api/missions/{id}` | cancels a running debate |
| POST | `/api/missions/{id}/retry` | failed missions only; resumes at the last completed round |
| GET | `/api/missions/{id}/stream` | SSE, replays persisted events then follows live; supports `Last-Event-ID` |

All `/api/missions*` calls require an `X-Client-Id` header (random id generated per browser). It scopes
history to the browser; it is **not authentication**. Put real auth in front before exposing sensitive data.

## Operational notes / known limits

- **Single process.** Debate tasks, the SSE wake-up and rate limiter are in-process; run `--workers 1`.
  Scaling out needs a job queue + pub/sub. On restart unfinished missions resume from the last completed round.
- Storage is MongoDB (PyMongo async). Event ordering uses an atomic per-mission counter; the final ruling
  and `done` event are written before the status flip so a crash in between is repaired on restart.
- Tests use `mongomock-motor` (in-memory); run an integration pass against a real MongoDB before production.
- Groq rate limits (429) are retried honouring `retry-after`; progress is shown to the user as status events.
- Models: defaults to `openai/gpt-oss-120b`. Verify model IDs against Groq's current model list.
