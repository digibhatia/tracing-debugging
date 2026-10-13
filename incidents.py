"""
Four seeded production incidents, for blind diagnosis from trace data alone.

HOW THIS IS MEANT TO BE RUN:
A facilitator (or a learner playing that role) calls seed_incident(n) for an
n they choose, WITHOUT telling the rest of the group which one. The group
then calls /ask (and, for incident 4, /chat with two different session_ids)
some number of times, pulls the resulting trace_ids, and must diagnose the
incident from the trace data alone - span shapes, attributes, tool sequence,
answer content - exactly the way a real production on-call engineer has
no advance warning of what broke. Only after a diagnosis is written down
does anyone call reveal_incident() to check it.

To keep this honest, lab.incident.active on a span is deliberately only
True/False - never which incident number. If you want the discipline to be
real, don't read incidents.py until after you've diagnosed at least one.

THE FOUR INCIDENTS:
  1. retrieval_stale_lock     - lookup_policy is silently pinned to 'stale'
                                 mode no matter what the caller asks for.
                                 Signature: lab.retrieval.mode = "stale" on
                                 EVERY tool_call span, even normal questions.
  2. tool_misrouting          - calculate_monthly_repayment fires for ANY
                                 question, including ones that needed
                                 lookup_policy. Signature: a trajectory
                                 failure - gen_ai.tool.name is wrong for the
                                 question, but the answer still looks fine.
  3. delegation_loop          - the fraud sub-agent (delegation.py) never
                                 reaches a verdict and keeps re-querying.
                                 Signature: many repeated model_call/
                                 tool_call pairs nested INSIDE one
                                 sub_agent_turn span - not at the top level.
  4. session_crosstalk        - two different session_ids are accidentally
                                 served from the SAME underlying Session
                                 object, so one customer's context leaks
                                 into another's answer. Signature: a /chat
                                 response for session B contains facts that
                                 were only ever mentioned in session A.
"""
from dataclasses import dataclass

CURRENT_INCIDENT = {"n": None}  # None = no incident seeded (normal operation)

_ANSWER_KEY = {
    1: {
        "name": "retrieval_stale_lock",
        "root_cause": (
            "lookup_policy's mode argument is being silently overridden to 'stale' "
            "regardless of what the caller passed, so every retrieval - even ones the "
            "agent intended to run normally - serves the outdated 24.9% EAR fixture "
            "instead of the live 19.9% figure."
        ),
        "remediation": (
            "Remove the override; lookup_policy should only use a non-normal mode when "
            "explicitly requested by the caller (as in the retrieval-stress endpoint), "
            "never as a hidden default."
        ),
    },
    2: {
        "name": "tool_misrouting",
        "root_cause": (
            "The agent is calling calculate_monthly_repayment for questions that need "
            "lookup_policy (e.g. a rate question), producing a well-formed, plausible-"
            "looking number that has nothing to do with the question asked - a "
            "trajectory failure invisible to any outcome-only check."
        ),
        "remediation": (
            "Tighten the tool descriptions in TOOL_SPECS so each tool's purpose is "
            "unambiguous, and add a trajectory check (trajectory_eval.py) to catch this "
            "class of bug automatically rather than relying on someone reading every answer."
        ),
    },
    3: {
        "name": "delegation_loop",
        "root_cause": (
            "The fraud referral sub-agent (delegation.py) never produces a tool-call-free "
            "turn, so it keeps calling lookup_policy indefinitely inside its own "
            "sub_agent_turn span - a runaway loop one level DOWN in the span hierarchy, "
            "invisible if you only look at the top-level agent_turn's step count."
        ),
        "remediation": (
            "Give the sub-agent its own step cap (separate from the main agent's), and "
            "export a specific sub-agent-step-count attribute so this is visible without "
            "having to expand every nested span by hand."
        ),
    },
    4: {
        "name": "session_crosstalk",
        "root_cause": (
            "memory_store.py's get_or_create() returned the wrong Session object - two "
            "different session_id values were sharing one Session instance, so a fact "
            "from customer A's conversation appeared in customer B's answer."
        ),
        "remediation": (
            "Add an assertion (or a test) that get_or_create(session_id) always returns a "
            "Session whose .session_id matches the id requested, and add session_id as a "
            "span attribute on every /chat trace so this class of bug is visible in Jaeger "
            "the moment it happens, not after a customer complains."
        ),
    },
}


def seed_incident(n: int):
    if n not in _ANSWER_KEY:
        raise ValueError(f"no such incident: {n}. Valid: {sorted(_ANSWER_KEY)}")
    CURRENT_INCIDENT["n"] = n


def clear_incident():
    CURRENT_INCIDENT["n"] = None


def effective_retrieval_mode(requested_mode: str) -> str:
    """Called from tools.py. Incident 1 silently overrides whatever mode was
    requested - the whole point being that the CALLER never asked for this."""
    if CURRENT_INCIDENT["n"] == 1:
        return "stale"
    return requested_mode


def should_misroute_to_repayment_tool() -> bool:
    """Incident 2's hook - checked from app.py's main agent loop."""
    return CURRENT_INCIDENT["n"] == 2


def delegation_should_loop_forever() -> bool:
    """Incident 3's hook - checked from delegation.py."""
    return CURRENT_INCIDENT["n"] == 3


def session_crosstalk_active() -> bool:
    """Incident 4's hook - checked from memory_store.py's get_or_create()."""
    return CURRENT_INCIDENT["n"] == 4


def reveal_incident(n: int) -> dict:
    """The answer key. Deliberately a SEPARATE function from seed_incident -
    call this only after you've written your own diagnosis down."""
    return _ANSWER_KEY[n]


def incident_is_active() -> bool:
    return CURRENT_INCIDENT["n"] is not None
