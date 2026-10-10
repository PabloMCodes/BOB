"""SQLite tables of the hub replica. Every row of rover data belongs to one workspace =
(edge_id, store_epoch); workspaces are never merged."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (ws_id INTEGER PRIMARY KEY AUTOINCREMENT, edge_id TEXT NOT NULL,
    store_epoch TEXT NOT NULL, created_wall_ns INTEGER NOT NULL, archived_wall_ns INTEGER,
    UNIQUE (edge_id, store_epoch));
CREATE TABLE IF NOT EXISTS records (ws_id INTEGER NOT NULL, lane TEXT NOT NULL, seq INTEGER NOT NULL,
    kind TEXT NOT NULL, source_mode TEXT NOT NULL, delivery TEXT NOT NULL, hub_rx_wall_ns INTEGER NOT NULL,
    json TEXT NOT NULL, PRIMARY KEY (ws_id, lane, seq));
CREATE INDEX IF NOT EXISTS records_kind ON records (ws_id, kind, seq);
CREATE TABLE IF NOT EXISTS cursors (ws_id INTEGER NOT NULL, lane TEXT NOT NULL, committed_seq INTEGER NOT NULL,
    PRIMARY KEY (ws_id, lane));
CREATE TABLE IF NOT EXISTS gaps (ws_id INTEGER NOT NULL, lane TEXT NOT NULL, first_seq INTEGER NOT NULL,
    last_seq INTEGER NOT NULL, reason TEXT NOT NULL, detected_wall_ns INTEGER NOT NULL,
    PRIMARY KEY (ws_id, lane, first_seq));
CREATE TABLE IF NOT EXISTS blobs (sha256 TEXT PRIMARY KEY, status TEXT NOT NULL, size INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_wall_ns INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS link (id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS live (id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL,
    hub_rx_wall_ns INTEGER NOT NULL, preview BLOB, preview_sha256 TEXT);
"""
