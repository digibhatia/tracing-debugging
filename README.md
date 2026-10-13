# Nidan — Tracing and Debugging, With Four Incidents You Diagnose Blind

*Nidan (निदान) means "diagnosis" or "root cause." Drishti taught you to
instrument an agent; Nidan assumes that's already done and asks the harder
question — given a trace and nothing else, can you find out what actually
broke?*

## 1. What Changed Since Drishti (the Previous Session)

| | Drishti | Nidan |
|---|---|---|
| Core question | How do I export what the agent is doing as telemetry? | Given telemetry alone, how do I diagnose what went wrong? |
| Span structure | Flat — `agent_turn` with `model_call`/`tool_call` children | Adds real depth — `delegation.py`'s sub-agent produces a `sub_agent_turn` nested two levels deep |
| Correlation | None | `session.id`, `nidan.thread.id`, `enduser.id` attributes tie a long conversation's traces together |
| Comparing runs | `failure_modes.induce_silent_post_update_degradation` (one fixed scenario) | `replay.py` — general-purpose replay N times, or diff any two configs, with a structured field-by-field diff |
| Grading | None | `trajectory_eval.py` — outcome and trajectory graded as two separate, independent verdicts |
| Failure classes | 5, each individually triggerable, name visible in the response | 4, seeded blind — a learner sees only `incident_active: true/false`, never which one, until they call `reveal_incident` themselves |
| New endpoints | `/failure/*` | `/delegate`, `/replay`, `/diff`, `/grade`, `/seed-incident/{n}`, `/incident-status`, `/reveal-incident/{n}` |
| Reused unchanged | — | `loaders.py`, `pii.py`, `chunking.py`, `context.py`, `pricing.py`, `vectorstore.py`, `otel_setup.py`, `genai_conventions.py` (extended), `llm_provider.py`, `tools.py` |

Same 5 documents, same domain, same underlying reference agent — Nidan adds
depth to the trace structure and turns debugging itself into the exercise.

## 2. The Five Documents, Five Formats

Unchanged from Nirikshan/Smriti/Drishti. Regenerate with `python make_documents.py`.

## 3. Multi-Step Trace Structure and Span Hierarchies

Every prior lab's traces were flat: one `agent_turn`, with `model_call` and
`tool_call` spans as its direct children. `delegation.py` adds a second
level: the main agent can delegate a fraud-referral decision to a dedicated
sub-agent, producing a `sub_agent_turn` span *nested inside* the span that
delegated to it — which itself contains its own `model_call`/`tool_call`
children:

```
agent_turn                      (root - the customer's request)
  model_call                    (decides to delegate)
  sub_agent_turn                 (the delegated sub-agent's own turn)
    model_call                   (the sub-agent's own reasoning)
    tool_call                    (the sub-agent's own tool use)
  model_call                    (main agent uses the sub-agent's verdict)
```

Try it: `GET /delegate?amount=9500` (should `REFER` — above the GBP 8,000
threshold) vs `GET /delegate?amount=500` (should `CLEAR`).

## 4. Session, Thread and User Correlation

`memory_store.py` extends Smriti's session store with a `user_id` (the real
customer, stable across visits) and a `thread_id` (a narrower sub-topic
within one long session). All three — `session.id`, `nidan.thread.id`,
`enduser.id` — are set as span attributes on every `/chat` trace, so a
debugging engineer can pull up every trace belonging to one conversation, or
one customer across several conversations, as a connected story instead of
a pile of disconnected traces.

## 5. Replaying and Diffing Runs to Isolate a Change

`replay.py` does two things:

- **`replay_n_times`** — run the identical question N times, see how many
  distinct answers and distinct tool-call sequences come back.
- **`diff_runs`** — run the identical question under two different configs
  (two models, two temperatures) and get back a *structured* diff: did the
  tool sequence change? Did the step count change? Did `finish_reason`
  change? Only then, how similar is the answer text? This is the
  "isolate a change" workflow — you find out exactly which field moved,
  not just that the output "feels different."

Try it: `GET /diff?q=...&temperature_a=0&temperature_b=1`.

## 6. Trajectory Failures Against Outcome Failures

`trajectory_eval.py` grades every run on two independent axes:

- **Outcome** — does the final answer look acceptable?
- **Trajectory** — did the agent use the *expected* tool to get there?

These can disagree. Nidan's incident 2 (`tool_misrouting`) is the concrete
case: `calculate_monthly_repayment` returns a real, correct-looking number
for a question that needed `lookup_policy` instead. Graded on outcome alone,
this passes. `grade_run()` flags it explicitly as `is_trajectory_failure`.

Try it: `GET /grade?q=What is the overdraft EAR on a Premier account?`.

## 7. A Repeatable Trace-Driven Debugging Workflow — the Incident Pack

`incidents.py` holds four seeded incidents. The discipline that makes this
exercise real: **only `lab.incident.active` (true/false) is ever visible on
a span — never which incident number.** The workflow:

1. A facilitator calls `POST /seed-incident/{n}` for one `n` they choose, without telling anyone which.
2. Everyone else runs `/ask`, `/chat`, `/delegate` — whatever seems relevant — and collects `trace_id`s.
3. Examine each trace's **shape first** (span count, nesting, names) before reading any content.
4. Form a hypothesis, write a root-cause note and a remediation.
5. Only then call `GET /reveal-incident/{n}` to check your diagnosis against what was actually seeded.

| # | Name | Signature to look for |
|---|---|---|
| 1 | `retrieval_stale_lock` | `lab.retrieval.mode = "stale"` on every `tool_call` span, even for questions that never asked for stale mode |
| 2 | `tool_misrouting` | `gen_ai.tool.name` is wrong for the question — a trajectory failure, caught by `/grade`, invisible to an outcome-only check |
| 3 | `delegation_loop` | Many repeated `model_call`/`tool_call` pairs nested *inside* one `sub_agent_turn` — the runaway is one level down, not at the top |
| 4 | `session_crosstalk` | A `/chat` response for one `session_id` contains facts only ever mentioned under a *different* `session_id` |

## 8. Architecture — the Full Flow

```
STEP 1 -- make_documents.py, then build_vectorstore.py (run once)

STEP 2 -- docker compose up  (OTel Collector + Jaeger, Terminal 1)
          Jaeger UI: http://localhost:16686

STEP 3 -- app.py  (Terminal 2)

    GET  /ask?q=...
    POST /chat?session_id=...&message=...&user_id=...&thread_id=...
    GET  /memory/{session_id}
    GET  /delegate?amount=...
    GET  /replay?q=...&n=...
    GET  /diff?q=...&model_a=...&model_b=...&temperature_a=...&temperature_b=...
    GET  /grade?q=...&expected_tool=...
    POST /seed-incident/{n}        (facilitator)
    GET  /incident-status           (everyone - true/false only)
    GET  /reveal-incident/{n}       (after you've written a diagnosis)

STEP 4 -- agent.py  (Terminal 3)

    Domain questions, delegation, session correlation, replay/diff,
    trajectory grading, then a full incident-exercise walkthrough
```

## 9. Setup — Step by Step

1. Clone/copy this folder.
2. `cp .env.example .env` and fill in `OPENAI_API_KEY`.
3. `python -m venv .venv && source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `python make_documents.py`
6. `python build_vectorstore.py`
7. **Terminal 1:** `docker compose up`
8. **Terminal 2:** `uvicorn app:app --reload --port 8000`
9. **Terminal 3:** `python agent.py`
10. Open **http://localhost:16686**, service `nidan-lloyds-agent`.

## 10. What to Notice While Running This

- **Depth is information.** A trace two levels deep (delegation) tells you something a flat trace never could — compare `/delegate`'s trace to a plain `/ask` trace.
- **The same `session_id` discipline that enables memory is also what a bug can exploit.** Incident 4 isn't a new mechanism — it's the *same* memory mechanism from Smriti/Nidan, misdirected.
- **A trajectory failure and a clean pass can look byte-for-byte identical in the final answer.** Only `/grade`'s two separate verdicts tell them apart.
- **Diagnosing blind is uncomfortable on purpose.** If `incidents.py` tells you the answer before you've formed a hypothesis from the trace, you've skipped the actual exercise.

## 11. Troubleshooting

| Problem | Likely cause |
|---|---|
| `/ask` or `/chat` fails with "OPENAI_API_KEY is not set" | Copy `.env.example` to `.env` and fill in your key |
| `/chat` follow-up doesn't seem to remember earlier turns | Confirm you're reusing the exact same `session_id` — a new id has no history |
| Incident 4 doesn't seem to leak anything | Confirm an incident is actually seeded (`GET /incident-status`) and that you're hitting two *different* `session_id`s, not the same one twice |
| `/delegate` never resolves | That's incident 3, working as designed — check `/incident-status`, then clear it with `POST /clear-incident` |
| No traces in Jaeger | Confirm `docker compose up` is running; see Drishti's README for the same checklist |

## 12. Sample Assignment Outline (for Participants)

**Assignment: Build Tulna, a General-Purpose Run Comparator**

*(Tulna, तुलना — "comparison": the discipline of asking exactly what changed, not just whether something feels different.)*

1. Starting from a copy of this repo, extend `replay.py`'s `diff_runs()` with a new field: `cost_delta_usd`, the difference in total model-call cost between the two runs (use `pricing.py`).
2. Add a 5th seeded incident of your own design to `incidents.py`, with its own hook wired into the real code path it affects (not just a hardcoded response) — and its own entry in `_ANSWER_KEY`.
3. Extend `trajectory_eval.py`'s `grade_trajectory()` so it can also fail a run that used the *right* tool but in the *wrong order* relative to a second expected tool (e.g. a question that needs `lookup_policy` before `calculate_monthly_repayment`, not after).
4. Run your new incident through the same blind-diagnosis workflow as the original four — have someone else (not you) diagnose it from trace data alone.
5. **Written reflection (150–200 words):** What made your new incident's trace signature easy or hard to tell apart from the original four? If it was hard, what specific span attribute would you add to make it distinguishable?

**Definition of done:**

- `cost_delta_usd` present in every `diff_runs()` result
- A 5th incident, wired into real code, with its own answer-key entry
- An order-sensitive trajectory check added to `grade_trajectory()`
- The new incident diagnosed blind by someone other than its author
- A written reflection answering the question in step 5

## 13. Where This Goes Next

Today's incident pack is four fixed scenarios you already know the answers
to. A real production system doesn't hand you an answer key — M4's
observability platforms give you the dashboard to notice something is wrong
in the first place, and M5's evaluation layer is what catches a trajectory
failure or a stale-data incident automatically, continuously, instead of
waiting for someone to run a blind-diagnosis exercise by hand.
