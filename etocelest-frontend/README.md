# ÉTOCELEST — Space Mission Frontend

A working, standalone frontend for ÉTOCELEST: four domain agents
(Astro-Weather, Logistics, Crew Readiness, Mission Value) debate a launch
plan in rounds, and a Judge sends them back to argue again until every
objection is resolved — or a round cap is hit, in which case it issues a
best-available ruling at reduced confidence.

It talks to the ÉTOCELEST backend (`etocelest-backend`, FastAPI + Groq). Nothing is simulated:
missions, debates, rulings and history all come from the API; the live debate arrives over
Server-Sent Events (`src/lib/api.js`), with automatic reconnect and replay.

Set the backend URL in `.env` (see `.env.example`): `VITE_API_BASE_URL=http://localhost:8000`.

## Pages

- **/** — Overview / landing page
- **/new** — Start a mission review (pick a preset or enter a custom mission)
- **/debate/:sessionId** — Live round-by-round debate with Judge notes, agent positions and a launch-date shift indicator (retry on failure)
- **/verdict/:sessionId** — Full verdict report with the round-by-round reasoning trace + JSON export
- **/history** — Past mission reviews
- **/how-it-works** — Explains the round-based Judge loop

## Extending to more agents

Agent presentation metadata lives in `AGENTS` (`src/lib/api.js`); the agents themselves,
their prompts and roles live in the backend (`app/domain/agents.py`).

## Run it

```bash
npm install
npm run dev
```

Then open the printed local URL (typically http://localhost:5173).

## Build for production

```bash
npm run build
npm run preview
```

## Stack

React 19, React Router 7, Tailwind CSS 3, Framer Motion, lucide-react icons,
Vite 8.
