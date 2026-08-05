CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    repo_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    name TEXT NOT NULL,
    ecosystem TEXT NOT NULL,
    declared_spec TEXT NOT NULL,
    resolved_version TEXT,
    is_direct INTEGER NOT NULL,
    is_dev INTEGER NOT NULL,
    manifest_path TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dependencies_scan_id ON dependencies(scan_id);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dependency_name TEXT NOT NULL,
    source TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_dependency_name ON signals(dependency_name);

CREATE TABLE IF NOT EXISTS usage_sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    package TEXT NOT NULL,
    symbol TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    column_number INTEGER NOT NULL,
    usage_kind TEXT NOT NULL,
    confidence TEXT NOT NULL,
    snippet TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_sites_scan_id ON usage_sites(scan_id);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    dependency_name TEXT NOT NULL,
    risk_total REAL NOT NULL,
    risk_components TEXT NOT NULL,
    risk_rationale TEXT NOT NULL,
    migration_plan TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES findings(id),
    chunk_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    verified INTEGER NOT NULL,
    entailment_score REAL
);

CREATE INDEX IF NOT EXISTS idx_citations_finding_id ON citations(finding_id);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    node_name TEXT NOT NULL,
    state_snapshot TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS http_cache (
    cache_key TEXT PRIMARY KEY,
    response_body TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    cached_at TEXT NOT NULL,
    ttl_seconds INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variant TEXT NOT NULL,
    metrics TEXT NOT NULL,
    created_at TEXT NOT NULL
);
