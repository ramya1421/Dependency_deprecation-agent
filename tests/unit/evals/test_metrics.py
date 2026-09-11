"""Unit tests for eval metrics — no LLM, no network."""
import math

from evals.metrics.faithfulness import extract_claims, hallucination_rate
from evals.metrics.latency import p50, p95, summarise
from evals.metrics.retrieval import mean_precision, mean_recall, precision_at_k, recall_at_k


# ---------------------------------------------------------------------------
# retrieval metrics
# ---------------------------------------------------------------------------

def test_precision_at_k_perfect_retrieval() -> None:
    assert precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == 1.0


def test_precision_at_k_no_hits() -> None:
    assert precision_at_k(["x", "y", "z"], ["a", "b"], k=3) == 0.0


def test_precision_at_k_partial() -> None:
    result = precision_at_k(["a", "x", "b", "y"], ["a", "b"], k=4)
    assert math.isclose(result, 0.5, abs_tol=1e-6)


def test_precision_empty_relevant_returns_zero() -> None:
    assert precision_at_k(["a", "b"], [], k=2) == 0.0


def test_recall_at_k_all_found() -> None:
    assert recall_at_k(["a", "b", "c"], ["a", "b"], k=5) == 1.0


def test_recall_at_k_none_found() -> None:
    assert recall_at_k(["x", "y"], ["a", "b"], k=2) == 0.0


def test_mean_precision_skips_entries_without_labels() -> None:
    results = [
        {"retrieved_chunk_ids": ["a"], "relevant_chunk_ids": ["a"]},
        {"retrieved_chunk_ids": ["b"], "relevant_chunk_ids": []},  # skip
    ]
    # Only one labelled entry, perfect hit → 1.0
    assert mean_precision(results, k=1) == 1.0


def test_mean_precision_empty_results() -> None:
    assert mean_precision([], k=5) == 0.0


def test_mean_recall_aggregates() -> None:
    results = [
        {"retrieved_chunk_ids": ["a", "b"], "relevant_chunk_ids": ["a"]},
        {"retrieved_chunk_ids": ["c"], "relevant_chunk_ids": ["c", "d"]},
    ]
    r = mean_recall(results, k=5)
    # First: 1/1 = 1.0, second: 1/2 = 0.5 → mean = 0.75
    assert math.isclose(r, 0.75, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# faithfulness / hallucination
# ---------------------------------------------------------------------------

def test_hallucination_zero_when_all_citations_present() -> None:
    answer = "Use dayjs [abcdef1234567890] instead of moment."
    available = {"abcdef1234567890"}
    assert hallucination_rate(answer, available) == 0.0


def test_hallucination_one_when_no_citations() -> None:
    assert hallucination_rate("No citations here.", {"abc"}) == 1.0


def test_hallucination_partial() -> None:
    answer = "Step [aaaaaaaaaaaaaaaa] and step [bbbbbbbbbbbbbbbb]."
    available = {"aaaaaaaaaaaaaaaa"}
    # One of two cited chunks is missing → 0.5
    assert math.isclose(hallucination_rate(answer, available), 0.5, abs_tol=1e-6)


def test_extract_claims_finds_cited_sentences() -> None:
    answer = (
        "Replace .format() calls. [abcdef1234567890] "
        "Install dayjs separately. [1234567890abcdef]"
    )
    chunk_map = {
        "abcdef1234567890": None,
        "1234567890abcdef": None,
    }
    claims = extract_claims(answer, chunk_map)
    assert len(claims) == 2
    assert claims[0]["chunk_id"] == "abcdef1234567890"
    assert claims[1]["chunk_id"] == "1234567890abcdef"


def test_extract_claims_empty_when_no_citations() -> None:
    claims = extract_claims("No citations here.", {})
    assert claims == []


# ---------------------------------------------------------------------------
# latency
# ---------------------------------------------------------------------------

def test_p50_odd_length() -> None:
    assert p50([1.0, 2.0, 3.0]) == 2.0


def test_p50_even_length() -> None:
    assert p50([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_p95_returns_near_max() -> None:
    lats = list(range(1, 21))  # 1..20
    # 95th percentile of 20 values → index 18 (0-indexed) → value 19
    assert p95([float(x) for x in lats]) == 19.0


def test_p50_empty() -> None:
    assert p50([]) == 0.0


def test_summarise_keys() -> None:
    result = summarise([1.0, 2.0, 3.0, 10.0])
    assert set(result.keys()) == {"p50", "p95", "mean", "max"}
    assert result["max"] == 10.0
