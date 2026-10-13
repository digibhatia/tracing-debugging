"""Manual cost calculation - no API returns cost directly, so we maintain our own table."""

PRICES_PER_MILLION_TOKENS_USD = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    prices = PRICES_PER_MILLION_TOKENS_USD.get(model)
    if prices is None:
        return 0.0
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
