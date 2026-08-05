from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    text: str
    chunk_id: str
    verified: bool
    entailment_score: float | None
