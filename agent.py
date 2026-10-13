"""Terminal client (Terminal 2) - while app.py (Terminal 1) is running."""
import requests

BASE = "http://127.0.0.1:8000"

QUESTIONS = [
    "What is the overdraft EAR on a Premier Current Account?",
    "What LTV can I get on a mortgage with the Standard product?",
    "What savings rate does the Premier Fixed Saver pay?",
]


def ask(q: str):
    r = requests.get(f"{BASE}/ask", params={"q": q})
    data = r.json()
    print(f"Q: {q}")
    print(f"A: {data['answer']}")
    print(f"   steps: {data['steps']}  |  tools: {data['tool_sequence']}  |  trace_id: {data['trace_id']}\n")
    return data


def run_domain_questions():
    print("=== Domain questions ===\n")
    for q in QUESTIONS:
        ask(q)


def bonus_1_delegation():
    print("=== BONUS 1: delegated sub-agent (nested span hierarchy) ===\n")
    for amount in [500, 9500]:
        r = requests.get(f"{BASE}/delegate", params={"amount": amount})
        print(f"amount=GBP{amount} ->", r.json(), "\n")


def bonus_2_session_correlation():
    print("=== BONUS 2: session/thread/user correlation ===\n")
    session_id = "lab-session-nidan-1"
    for msg in ["What's the Premier Easy Saver rate?", "And the fixed one?"]:
        r = requests.post(f"{BASE}/chat", params={
            "session_id": session_id, "message": msg, "user_id": "customer-001", "thread_id": "savings-topic"})
        print(r.json(), "\n")
    print("Memory:", requests.get(f"{BASE}/memory/{session_id}").json(), "\n")


def bonus_3_replay_and_diff():
    print("=== BONUS 3: replay and diff ===\n")
    q = "What is the overdraft EAR on a Premier account?"
    r = requests.get(f"{BASE}/replay", params={"q": q, "n": 3})
    print("replay:", r.json(), "\n")
    r = requests.get(f"{BASE}/diff", params={"q": q, "temperature_a": 0, "temperature_b": 1})
    print("diff (temperature 0 vs 1):", r.json(), "\n")


def bonus_4_trajectory_vs_outcome():
    print("=== BONUS 4: trajectory vs outcome grading ===\n")
    r = requests.get(f"{BASE}/grade", params={"q": "What is the overdraft EAR on a Premier account?"})
    print(r.json(), "\n")


def run_incident_exercise(n: int):
    """Simulates the facilitator seeding incident n, then a learner
    diagnosing blind. In a real session, only the facilitator calls
    seed-incident and reveal-incident; everyone else only sees /ask,
    /chat, /delegate and /incident-status."""
    print(f"=== Incident exercise: seeding incident {n} (facilitator-only in a real run) ===\n")
    requests.post(f"{BASE}/seed-incident/{n}")
    print("incident-status (all a learner would see):", requests.get(f"{BASE}/incident-status").json(), "\n")

    print("Learner's view - 2 normal questions:")
    ask("What is the overdraft EAR on a Premier account?")
    ask("What is the fraud referral threshold for a single transaction?")

    print("Learner's view - delegation:")
    print(requests.get(f"{BASE}/delegate", params={"amount": 9500}).json(), "\n")

    print("Learner's view - two sessions, to catch incident 4:")
    requests.post(f"{BASE}/chat", params={"session_id": "s-A", "message": "My name is Alex and I'm asking about overdrafts."})
    r = requests.post(f"{BASE}/chat", params={"session_id": "s-B", "message": "What's my name?"})
    print("session s-B's answer (should NOT know about Alex):", r.json(), "\n")

    print("--- write your diagnosis now, THEN check the answer key ---")
    print("reveal-incident:", requests.get(f"{BASE}/reveal-incident/{n}").json(), "\n")
    requests.post(f"{BASE}/clear-incident")


if __name__ == "__main__":
    run_domain_questions()
    bonus_1_delegation()
    bonus_2_session_correlation()
    bonus_3_replay_and_diff()
    bonus_4_trajectory_vs_outcome()
    # Facilitator picks ONE of 1-4 without telling anyone else which:
    run_incident_exercise(4)
