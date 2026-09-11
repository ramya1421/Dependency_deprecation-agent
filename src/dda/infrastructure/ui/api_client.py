"""Thin HTTP client for the Streamlit UI to talk to the FastAPI backend.

All pages import from here — no page imports httpx directly.
"""
from typing import Any

import httpx

_BASE = "http://localhost:8000"
_TIMEOUT = 30.0


def _get(path: str) -> dict[str, Any] | list[Any] | None:
    try:
        r = httpx.get(f"{_BASE}{path}", timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except Exception:
        return None


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        r = httpx.post(f"{_BASE}{path}", json=body, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
    except Exception:
        return None


def trigger_scan(repo_path: str, offline: bool = False) -> str | None:
    result = _post("/api/v1/scans", {"repo_path": repo_path, "offline": offline})
    return str(result["scan_id"]) if result else None


def get_scan_status(scan_id: str) -> dict[str, Any] | None:
    result = _get(f"/api/v1/scans/{scan_id}")
    return result if isinstance(result, dict) else None


def get_dependencies(scan_id: str) -> list[dict[str, Any]]:
    result = _get(f"/api/v1/scans/{scan_id}/dependencies")
    return result if isinstance(result, list) else []  # type: ignore[return-value]


def get_findings(scan_id: str) -> list[dict[str, Any]]:
    result = _get(f"/api/v1/scans/{scan_id}/findings")
    return result if isinstance(result, list) else []  # type: ignore[return-value]


def get_migration_plan(scan_id: str, dep_name: str) -> dict[str, Any] | None:
    result = _get(f"/api/v1/scans/{scan_id}/findings/{dep_name}/migration")
    return result if isinstance(result, dict) else None


def get_report(scan_id: str) -> dict[str, Any] | None:
    result = _get(f"/api/v1/scans/{scan_id}/report")
    return result if isinstance(result, dict) else None


def kb_search(query: str, package: str | None, top_k: int = 5) -> list[dict[str, Any]]:
    body: dict[str, Any] = {"query": query, "top_k": top_k}
    if package:
        body["package"] = package
    result = _post("/api/v1/kb/search", body)
    if not result:
        return []
    return result.get("hits", [])  # type: ignore[no-any-return]


def health() -> dict[str, Any]:
    result = _get("/health")
    return result if isinstance(result, dict) else {"status": "unreachable"}
