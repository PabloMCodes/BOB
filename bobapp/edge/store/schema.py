"""SQLite tables of the edge store."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lane_head (lane TEXT PRIMARY KEY, head_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS records (
    lane TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, wall_ns INTEGER NOT NULL,
    size INTEGER NOT NULL, json TEXT NOT NULL, PRIMARY KEY (lane, seq));
CREATE TABLE IF NOT EXISTS acks (hub_id TEXT NOT NULL, lane TEXT NOT NULL, seq INTEGER NOT NULL,
    PRIMARY KEY (hub_id, lane));
CREATE TABLE IF NOT EXISTS blobs (sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL,
    media_type TEXT NOT NULL, evidence_seq INTEGER);
CREATE TABLE IF NOT EXISTS blob_refs (lane TEXT NOT NULL, seq INTEGER NOT NULL, sha256 TEXT NOT NULL,
    PRIMARY KEY (lane, seq, sha256));
CREATE INDEX IF NOT EXISTS blob_refs_sha ON blob_refs (sha256);
CREATE TABLE IF NOT EXISTS blob_acks (hub_id TEXT NOT NULL, sha256 TEXT NOT NULL,
    PRIMARY KEY (hub_id, sha256));
CREATE TABLE IF NOT EXISTS live (id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL,
    preview BLOB, preview_sha256 TEXT);
CREATE TABLE IF NOT EXISTS profiles (worksite_id TEXT NOT NULL, revision INTEGER NOT NULL,
    sha256 TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY (worksite_id, revision));
CREATE TABLE IF NOT EXISTS inspections (inspection_id TEXT PRIMARY KEY, worksite_id TEXT NOT NULL,
    profile_revision INTEGER NOT NULL, profile_sha256 TEXT NOT NULL, source_mode TEXT NOT NULL,
    started_seq INTEGER NOT NULL, ended_seq INTEGER, end_reason TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_inspection ON inspections ((ended_seq IS NULL)) WHERE ended_seq IS NULL;
"""
