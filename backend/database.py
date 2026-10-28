import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = "preflight.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            total_pages INTEGER DEFAULT 1,
            raw_text TEXT,
            banned_words_json TEXT DEFAULT '[]',
            required_phrases_json TEXT DEFAULT '[]',
            tone_profile TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brand_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guideline_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            rule_text TEXT NOT NULL,
            target_value TEXT DEFAULT '',
            severity TEXT DEFAULT 'warning',
            page_number INTEGER DEFAULT 1,
            section_title TEXT DEFAULT 'General',
            source_quote TEXT DEFAULT '',
            approved INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (guideline_id) REFERENCES guidelines (id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guideline_id INTEGER NOT NULL,
            content_title TEXT NOT NULL,
            submitted_text TEXT NOT NULL,
            overall_score INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            issues_json TEXT NOT NULL,
            corrected_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (guideline_id) REFERENCES guidelines (id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guideline_id INTEGER NOT NULL,
            total_samples INTEGER NOT NULL,
            accuracy REAL NOT NULL,
            precision_score REAL NOT NULL,
            recall_score REAL NOT NULL,
            f1_score REAL NOT NULL,
            results_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def create_guideline(name: str, filename: str, total_pages: int, raw_text: str, banned_words: List[str], required_phrases: List[str], tone_profile: str, extracted_rules: List[Dict[str, Any]]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO guidelines (name, filename, total_pages, raw_text, banned_words_json, required_phrases_json, tone_profile, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, filename, total_pages, raw_text, json.dumps(banned_words), json.dumps(required_phrases), tone_profile, now)
    )
    guideline_id = cursor.lastrowid
    for rule in extracted_rules:
        cursor.execute(
            "INSERT INTO brand_rules (guideline_id, category, rule_text, target_value, severity, page_number, section_title, source_quote, approved, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guideline_id, rule.get("category", "messaging"), rule.get("rule_text", ""), rule.get("target_value", ""), rule.get("severity", "warning"), rule.get("page_number", 1), rule.get("section_title", "General"), rule.get("source_quote", ""), rule.get("approved", 0), now)
        )
    conn.commit()
    conn.close()
    return guideline_id

def get_guidelines() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guidelines ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    for row in rows:
        row["banned_words"] = json.loads(row.get("banned_words_json") or "[]")
        row["required_phrases"] = json.loads(row.get("required_phrases_json") or "[]")
        cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) as approved_count FROM brand_rules WHERE guideline_id = ?", (row["id"],))
        counts = dict(cursor.fetchone())
        row["total_rules"] = counts["total"] or 0
        row["approved_rules"] = counts["approved_count"] or 0
    conn.close()
    return rows

def get_guideline_by_id(guideline_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guidelines WHERE id = ?", (guideline_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    data = dict(row)
    data["banned_words"] = json.loads(data.get("banned_words_json") or "[]")
    data["required_phrases"] = json.loads(data.get("required_phrases_json") or "[]")
    cursor.execute("SELECT * FROM brand_rules WHERE guideline_id = ? ORDER BY page_number ASC, id ASC", (guideline_id,))
    data["rules"] = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return data

def update_rule(rule_id: int, approved: Optional[int] = None, rule_text: Optional[str] = None, target_value: Optional[str] = None, severity: Optional[str] = None, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM brand_rules WHERE id = ?", (rule_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return None
    current = dict(existing)
    cursor.execute(
        "UPDATE brand_rules SET approved = ?, rule_text = ?, target_value = ?, severity = ?, category = ? WHERE id = ?",
        (
            approved if approved is not None else current["approved"],
            rule_text if rule_text is not None else current["rule_text"],
            target_value if target_value is not None else current["target_value"],
            severity if severity is not None else current["severity"],
            category if category is not None else current["category"],
            rule_id
        )
    )
    conn.commit()
    cursor.execute("SELECT * FROM brand_rules WHERE id = ?", (rule_id,))
    updated = dict(cursor.fetchone())
    conn.close()
    return updated

def bulk_approve_rules(guideline_id: int, approved_status: int = 1) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE brand_rules SET approved = ? WHERE guideline_id = ?", (approved_status, guideline_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def save_content_check(guideline_id: int, content_title: str, submitted_text: str, overall_score: int, status: str, summary: str, issues: List[Dict[str, Any]], corrected_text: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO content_checks (guideline_id, content_title, submitted_text, overall_score, status, summary, issues_json, corrected_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (guideline_id, content_title, submitted_text, overall_score, status, summary, json.dumps(issues), corrected_text, now)
    )
    check_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return get_content_check_by_id(check_id)

def get_content_check_by_id(check_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM content_checks WHERE id = ?", (check_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["issues"] = json.loads(data.get("issues_json") or "[]")
    return data

def get_content_checks(guideline_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    if guideline_id:
        cursor.execute("SELECT * FROM content_checks WHERE guideline_id = ? ORDER BY id DESC", (guideline_id,))
    else:
        cursor.execute("SELECT * FROM content_checks ORDER BY id DESC LIMIT 50")
    rows = [dict(r) for r in cursor.fetchall()]
    for r in rows:
        r["issues"] = json.loads(r.get("issues_json") or "[]")
    conn.close()
    return rows

def save_benchmark_run(guideline_id: int, total_samples: int, accuracy: float, precision_score: float, recall_score: float, f1_score: float, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO benchmark_runs (guideline_id, total_samples, accuracy, precision_score, recall_score, f1_score, results_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guideline_id, total_samples, accuracy, precision_score, recall_score, f1_score, json.dumps(results), now)
    )
    run_id = cursor.lastrowid
    conn.commit()
    cursor.execute("SELECT * FROM benchmark_runs WHERE id = ?", (run_id,))
    row = dict(cursor.fetchone())
    row["results"] = json.loads(row["results_json"])
    conn.close()
    return row
