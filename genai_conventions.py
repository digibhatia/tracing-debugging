"""
GenAI semantic-convention attribute names (OpenTelemetry's gen_ai.* namespace)
and the redaction wrapper for anything that touches a span.

WHY A SHARED CONVENTION INSTEAD OF HOUSE NAMES:
An in-house scheme ("llm.model", "ai_tokens_in", "promptText"...) works fine
until you plug in a second vendor's dashboard, a second team's collector
config, or a managed observability backend that ships GenAI-aware views out
of the box (cost-by-model, token-burn-rate alerts, trace-to-eval links).
Those all key off gen_ai.* attribute names. Every house name you invented is
now a mapping layer someone has to build and maintain - that's the "cost
later" the brief is pointing at. Using the real convention from day one means
a backend you haven't chosen yet can still understand your traces.

Reference: https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""
from pii import redact

# --- request-side attributes --------------------------------------------
GEN_AI_SYSTEM = "gen_ai.system"                     # e.g. "openai"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"     # "chat", "embeddings", "execute_tool"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"

# --- response-side attributes --------------------------------------------
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# --- tool-call attributes --------------------------------------------
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"

# --- correlation attributes (OTel general semantic conventions, not GenAI-
#     specific) - what ties every trace from the SAME long-running
#     conversation, the same narrower thread within it, and the same real
#     person together, across requests that each get their own trace_id.
SESSION_ID = "session.id"        # the whole multi-turn conversation
THREAD_ID = "nidan.thread.id"    # a sub-thread within a session (e.g. one topic)
ENDUSER_ID = "enduser.id"        # the real customer, stable across sessions

# --- attributes that are NOT part of the convention, kept in our own
#     namespace deliberately, because they are cost/ops facts the spec does
#     not (yet) define a slot for -------------------------------------------
LAB_COST_USD = "lab.cost_usd"
LAB_RETRIEVAL_MODE = "lab.retrieval.mode"
LAB_RETRIEVAL_HIT_COUNT = "lab.retrieval.hit_count"
LAB_DELEGATED_TO = "lab.delegated_to"          # name of the sub-agent a span delegated to
LAB_TRAJECTORY_TOOL = "lab.trajectory.tool_used"
LAB_TRAJECTORY_EXPECTED = "lab.trajectory.tool_expected"
LAB_TRAJECTORY_CORRECT = "lab.trajectory.correct"
LAB_OUTCOME_CORRECT = "lab.outcome.correct"
LAB_INCIDENT_ACTIVE = "lab.incident.active"    # true/false - NEVER which incident number


# --- what NEVER goes on a span, even redacted -----------------------------
# API keys, raw customer PII before redaction, full session memory dumps.
# A span attribute is exported to a backend outside your process boundary -
# treat it like a log line a third party might read, not a debugger variable.
NEVER_ON_A_SPAN = [
    "the raw OPENAI_API_KEY or any other secret",
    "unredacted customer PII (emails, phone numbers, sort codes)",
    "the full conversation memory for a session, turn by turn",
    "anything a regulator would call 'customer data at rest'",
]


def safe_prompt_attribute(text: str, max_len: int = 300) -> str:
    """Redact PII, then truncate. This is what actually gets set on a span -
    never the raw prompt/response string."""
    redacted = redact(text).text
    if len(redacted) > max_len:
        redacted = redacted[:max_len] + "...[TRUNCATED]"
    return redacted
