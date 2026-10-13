"""FastAPI backend for Nidan. Same reference agent as Drishti/Smriti/Nirikshan,
now with: delegated sub-agent calls, session/thread/user correlation, replay
and diff endpoints, trajectory-vs-outcome grading, and a 4-incident seeded
diagnosis exercise."""
import json

from fastapi import FastAPI, Query
from opentelemetry import trace

from otel_setup import get_tracer
from genai_conventions import SESSION_ID, THREAD_ID, ENDUSER_ID, LAB_INCIDENT_ACTIVE
from llm_provider import chat_raw
from tools import TOOL_SPECS, TOOL_FUNCTIONS, calculate_monthly_repayment
from delegation import delegate_to_fraud_check
from memory_store import store
from replay import run_once, diff_runs, replay_n_times
from trajectory_eval import grade_run
import incidents

app = FastAPI(title="Nidan - Tracing and Debugging Reference Agent")

SYSTEM_PROMPT = (
    "You are a customer service assistant for Lloyds Financial (a training scenario). "
    "For ANY question about rates, limits, eligibility, fraud handling, complaints, or "
    "savings products, you MUST call lookup_policy before writing your answer - this "
    "applies even if the question sounds like it needs account-specific data. Use "
    "calculate_monthly_repayment for repayment arithmetic. Keep answers short."
)
MAX_AGENT_STEPS = 6


def _run_traced_agent_turn(question: str, session_id: str = None, user_id: str = "anonymous",
                            thread_id: str = None, history: list = None):
    """history, when given, is prior {role, content} turns from THIS session -
    prepended so the model actually sees earlier context. This is also
    exactly the mechanism incident 4 (session_crosstalk) exploits: if
    memory_store hands back the wrong session's history, it ends up here,
    in the messages sent to the model, indistinguishable from real memory."""
    tracer = get_tracer("nidan.app")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend({"role": t["role"], "content": t["content"]} for t in history)
    messages.append({"role": "user", "content": question})
    with tracer.start_as_current_span("agent_turn") as root_span:
        root_span.set_attribute("lab.question", question[:200])
        root_span.set_attribute(LAB_INCIDENT_ACTIVE, incidents.incident_is_active())
        if session_id:
            root_span.set_attribute(SESSION_ID, session_id)
        if thread_id:
            root_span.set_attribute(THREAD_ID, thread_id)
        root_span.set_attribute(ENDUSER_ID, user_id)

        tool_sequence = []
        steps = 0
        final_answer = None
        for steps in range(1, MAX_AGENT_STEPS + 1):
            # Incident 2: force every question down the wrong tool, regardless
            # of what the model itself would have chosen.
            if incidents.should_misroute_to_repayment_tool() and steps == 1:
                result = calculate_monthly_repayment(principal=200000, annual_rate_pct=19.9, years=1)
                tool_sequence.append("calculate_monthly_repayment")
                final_answer = f"Based on a standard calculation, this comes to approximately GBP {result} per month."
                break

            turn = chat_raw(messages=messages, tools=TOOL_SPECS)
            if not turn.tool_calls:
                final_answer = turn.content
                break
            messages.append({"role": "assistant", "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in turn.tool_calls]})
            for tc in turn.tool_calls:
                tool_sequence.append(tc.name)
                args = json.loads(tc.arguments or "{}")
                fn = TOOL_FUNCTIONS[tc.name]
                result = fn(**args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

        root_span.set_attribute("lab.steps_taken", steps)
        root_span.set_attribute("lab.tool_sequence", ",".join(tool_sequence) or "(none)")
        trace_id = format(root_span.get_span_context().trace_id, "032x")
        return {"answer": final_answer, "steps": steps, "tool_sequence": tool_sequence, "trace_id": trace_id}


@app.get("/")
def root():
    return {"service": "nidan", "docs": "/docs"}


@app.get("/ask")
def ask(q: str = Query(...)):
    return _run_traced_agent_turn(q)


@app.post("/chat")
def chat(session_id: str = Query(...), message: str = Query(...),
          user_id: str = Query("anonymous"), thread_id: str = Query(None)):
    session = store.get_or_create(session_id, user_id=user_id)
    history = [{"role": t["role"], "content": t["content"]} for t in session.turns]
    session.append("user", message, thread_id=thread_id)
    result = _run_traced_agent_turn(message, session_id=session_id, user_id=user_id,
                                     thread_id=session.thread_id, history=history)
    session.append("assistant", result["answer"] or "")
    session.truncate()
    return {"session_id": session_id, "answer": result["answer"], "trace_id": result["trace_id"]}


@app.get("/memory/{session_id}")
def memory(session_id: str):
    return store.inspect(session_id)


@app.post("/memory/{session_id}/reset")
def memory_reset(session_id: str):
    store.reset(session_id)
    return {"session_id": session_id, "reset": True}


@app.get("/delegate")
def delegate(amount: float = Query(9500.0)):
    return delegate_to_fraud_check(amount)


@app.get("/replay")
def replay(q: str = Query(...), n: int = Query(5)):
    runs = replay_n_times(q, SYSTEM_PROMPT, n=n)
    return {
        "n_runs": n,
        "unique_answers": len({r.answer.strip() for r in runs}),
        "unique_tool_sequences": len({tuple(r.tool_sequence) for r in runs}),
        "runs": [{"answer": r.answer, "tool_sequence": r.tool_sequence, "steps": r.steps} for r in runs],
    }


@app.get("/diff")
def diff(q: str = Query(...), model_a: str = Query("gpt-4o-mini"), model_b: str = Query("gpt-4o-mini"),
         temperature_a: float = Query(None), temperature_b: float = Query(None)):
    run_a = run_once(q, SYSTEM_PROMPT, model=model_a, temperature=temperature_a)
    run_b = run_once(q, SYSTEM_PROMPT, model=model_b, temperature=temperature_b)
    return diff_runs(run_a, run_b, label_a="A", label_b="B")


@app.get("/grade")
def grade(q: str = Query(...), expected_tool: str = Query("lookup_policy"),
          must_contain_any: str = Query("19.9,4.10,4.55,90%,8000")):
    result = _run_traced_agent_turn(q)
    keywords = [k.strip() for k in must_contain_any.split(",")]
    verdict = grade_run(result["answer"] or "", result["tool_sequence"], expected_tool, keywords)
    return {
        "answer": result["answer"],
        "tool_sequence": result["tool_sequence"],
        "outcome_correct": verdict.outcome_correct,
        "trajectory_correct": verdict.trajectory_correct,
        "is_trajectory_failure": verdict.is_trajectory_failure,
        "notes": verdict.notes,
    }


# ---------------------------------------------------------------- incident pack
@app.post("/seed-incident/{n}")
def seed_incident(n: int):
    """Facilitator-only in a real session - seeds one of the 4 incidents.
    Does NOT reveal which one in its own response in a real exercise; it's
    left visible here only so this lab's own mock-testing can confirm each
    incident actually changes behaviour."""
    incidents.seed_incident(n)
    return {"seeded": True}


@app.post("/clear-incident")
def clear_incident():
    incidents.clear_incident()
    return {"cleared": True}


@app.get("/incident-status")
def incident_status():
    """What a learner is ALLOWED to see mid-exercise: only whether something
    is active, never which one."""
    return {"incident_active": incidents.incident_is_active()}


@app.get("/reveal-incident/{n}")
def reveal_incident(n: int):
    """The answer key - call only after writing your own diagnosis down."""
    return incidents.reveal_incident(n)
