"""FR-SPINE.4 — the store. Reference implementation over stdlib ``sqlite3`` (DEVIATIONS.md: DuckDB /
Postgres are drop-in adapters behind this same shape). Zero dependencies, zero setup: an in-memory
store (``:memory:``) is the default so tests and the ``demo`` verb need no files.

Logical tables (LLD §6, subset the spine exercises): ``feed_status``, ``signal_feature_week``,
``category_event_prior``, ``category_event_measured``, ``company_profile``,
``prior_calibration_report``. JSON-bearing columns are stored as TEXT."""
from __future__ import annotations

import json
import sqlite3
from typing import List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feed_status (
  feed TEXT PRIMARY KEY, status TEXT, as_of TEXT, rows INTEGER, source TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS signal_feature_week (
  feed TEXT, region_key TEXT, iso_week TEXT, values_json TEXT, source TEXT, as_of TEXT,
  is_forecast INTEGER DEFAULT 0, PRIMARY KEY (feed, region_key, iso_week));
CREATE TABLE IF NOT EXISTS category_event_prior (
  id TEXT PRIMARY KEY, category TEXT, signal_type TEXT, signal_id TEXT, region_key TEXT,
  direction TEXT, band_json TEXT, lead_days INTEGER, tail_days INTEGER,
  research_confidence REAL, citations_json TEXT, status TEXT, reviewed_by TEXT, provenance_json TEXT);
CREATE TABLE IF NOT EXISTS category_event_measured (
  id TEXT PRIMARY KEY, company_key TEXT, category TEXT, signal_type TEXT, signal_id TEXT,
  region_key TEXT, direction TEXT, point REAL, low REAL, high REAL, years INTEGER, n_obs INTEGER,
  events_observed INTEGER, method TEXT, bar_json TEXT, provenance_json TEXT);
CREATE TABLE IF NOT EXISTS company_profile (
  company_key TEXT PRIMARY KEY, display_name TEXT, category_mix_json TEXT, taxonomy TEXT,
  geographies_json TEXT, evidence TEXT, provenance_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS prior_calibration_report (
  company_key TEXT, run_at TEXT, auto_accepted INTEGER, contradicted INTEGER, rate REAL,
  spot_checked INTEGER, recommendation TEXT, PRIMARY KEY (company_key, run_at));
"""


class SqliteStore:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── feed_status (FR-SPINE.3) ──────────────────────────────────────────────────────────────────
    def upsert_feed_status(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO feed_status(feed,status,as_of,rows,source,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(feed) DO UPDATE SET status=excluded.status, as_of=excluded.as_of, "
            "rows=excluded.rows, source=excluded.source, updated_at=excluded.updated_at",
            (row["feed"], row["status"], row["as_of"], row["rows"], row["source"], row["updated_at"]))
        self._conn.commit()

    def get_feed_statuses(self) -> List[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM feed_status ORDER BY feed")]

    # ── signal_feature_week (the ARS-facing feed) ─────────────────────────────────────────────────
    def upsert_signal_features(self, rows: List[dict]) -> int:
        n = 0
        for r in rows:
            self._conn.execute(
                "INSERT INTO signal_feature_week(feed,region_key,iso_week,values_json,source,as_of,is_forecast) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(feed,region_key,iso_week) DO UPDATE SET "
                "values_json=excluded.values_json, source=excluded.source, as_of=excluded.as_of, "
                "is_forecast=excluded.is_forecast",
                (r["feed"], r["region_key"], r["iso_week"], json.dumps(r["values"]),
                 r["source"], r["as_of"], 1 if r.get("is_forecast") else 0))
            n += 1
        self._conn.commit()
        return n

    def get_signal_features(self, feed: str, region_keys: List[str], from_week: Optional[str] = None,
                            to_week: Optional[str] = None) -> List[dict]:
        q = "SELECT * FROM signal_feature_week WHERE feed=? AND region_key IN ({})".format(
            ",".join("?" for _ in region_keys))
        params = [feed, *region_keys]
        if from_week:
            q += " AND iso_week>=?"; params.append(from_week)
        if to_week:
            q += " AND iso_week<=?"; params.append(to_week)
        q += " ORDER BY region_key, iso_week"
        out = []
        for r in self._conn.execute(q, params):
            d = dict(r)
            d["values"] = json.loads(d.pop("values_json"))
            d["is_forecast"] = bool(d["is_forecast"])
            out.append(d)
        return out

    # ── category_event_prior (the prior library + review queue) ───────────────────────────────────
    def upsert_prior(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO category_event_prior(id,category,signal_type,signal_id,region_key,direction,"
            "band_json,lead_days,tail_days,research_confidence,citations_json,status,reviewed_by,provenance_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "direction=excluded.direction, band_json=excluded.band_json, research_confidence=excluded.research_confidence, "
            "citations_json=excluded.citations_json, status=excluded.status, reviewed_by=excluded.reviewed_by",
            (row["id"], row["category"], row["signal_type"], row["signal_id"], row["region_key"],
             row["direction"], json.dumps(row.get("band")), row["lead_days"], row["tail_days"],
             row.get("research_confidence"), json.dumps(row.get("citations", [])), row["status"],
             row.get("reviewed_by"), json.dumps(row.get("provenance", {}))))
        self._conn.commit()

    def list_priors(self, status: Optional[str] = None) -> List[dict]:
        q = "SELECT * FROM category_event_prior"
        params: list = []
        if status:
            q += " WHERE status=?"; params.append(status)
        q += " ORDER BY id"
        return [self._prior_row(r) for r in self._conn.execute(q, params)]

    def set_prior_status(self, prior_id: str, status: str, reviewed_by: Optional[str]) -> None:
        self._conn.execute("UPDATE category_event_prior SET status=?, reviewed_by=? WHERE id=?",
                           (status, reviewed_by, prior_id))
        self._conn.commit()

    @staticmethod
    def _prior_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["band"] = json.loads(d.pop("band_json")) if d["band_json"] else None
        d["citations"] = json.loads(d.pop("citations_json") or "[]")
        d["provenance"] = json.loads(d.pop("provenance_json") or "{}")
        return d

    # ── category_event_measured ───────────────────────────────────────────────────────────────────
    def upsert_measured(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO category_event_measured(id,company_key,category,signal_type,signal_id,region_key,"
            "direction,point,low,high,years,n_obs,events_observed,method,bar_json,provenance_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "direction=excluded.direction, point=excluded.point, low=excluded.low, high=excluded.high",
            (row["id"], row["company_key"], row["category"], row["signal_type"], row["signal_id"],
             row["region_key"], row["direction"], row.get("point"), row.get("low"), row.get("high"),
             row.get("years"), row.get("n_obs"), row.get("events_observed"), row.get("method"),
             json.dumps(row.get("bar", {})), json.dumps(row.get("provenance", {}))))
        self._conn.commit()

    def list_measured(self, company_key: Optional[str] = None) -> List[dict]:
        q = "SELECT * FROM category_event_measured"
        params: list = []
        if company_key:
            q += " WHERE company_key=?"; params.append(company_key)
        return [dict(r) for r in self._conn.execute(q, params)]

    # ── company_profile ───────────────────────────────────────────────────────────────────────────
    def upsert_profile(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO company_profile(company_key,display_name,category_mix_json,taxonomy,geographies_json,"
            "evidence,provenance_json,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(company_key) DO UPDATE SET "
            "category_mix_json=excluded.category_mix_json, evidence=excluded.evidence, updated_at=excluded.updated_at",
            (row["company_key"], row["display_name"], json.dumps(row["category_mix"]), row["taxonomy"],
             json.dumps(row["geographies"]), row["evidence"], json.dumps(row.get("provenance", {})),
             row["updated_at"]))
        self._conn.commit()

    def get_profile(self, company_key: str) -> Optional[dict]:
        r = self._conn.execute("SELECT * FROM company_profile WHERE company_key=?", (company_key,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        d["category_mix"] = json.loads(d.pop("category_mix_json"))
        d["geographies"] = json.loads(d.pop("geographies_json"))
        d["provenance"] = json.loads(d.pop("provenance_json") or "{}")
        return d

    # ── prior_calibration_report ──────────────────────────────────────────────────────────────────
    def upsert_calibration_report(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO prior_calibration_report(company_key,run_at,auto_accepted,contradicted,rate,"
            "spot_checked,recommendation) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(company_key,run_at) DO UPDATE SET rate=excluded.rate",
            (row["company_key"], row["run_at"], row["auto_accepted"], row["contradicted"], row["rate"],
             row["spot_checked"], row["recommendation"]))
        self._conn.commit()
