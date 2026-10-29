import io
import os
import re
import csv
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from dotenv import load_dotenv

import database as db

load_dotenv()

app = FastAPI(title="Preflight Round 3 - Brand Compliance Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

router = APIRouter()


# =====================================================================
# PYDANTIC MODELS
# =====================================================================

class RuleUpdateRequest(BaseModel):
    approved: Optional[int] = None
    rule_text: Optional[str] = None
    target_value: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None


class CustomRuleRequest(BaseModel):
    category: str
    rule_text: str
    target_value: str = ""
    severity: str = "warning"
    page_number: int = 1
    section_title: str = "Manual Rule"
    source_quote: str = "Added by user"


class ContentCheckRequest(BaseModel):
    guideline_id: int
    content_title: str = "Marketing Copy Check"
    text: str
    only_approved_rules: bool = True


class SampleCase(BaseModel):
    id: str
    title: str
    content: str
    expected_compliant: bool
    expected_categories: List[str] = []


class BenchmarkRequest(BaseModel):
    guideline_id: int
    samples: Optional[List[SampleCase]] = None


# =====================================================================
# 1. BETTER PDF READING (Multi-page chunking + Provenance Extraction)
# =====================================================================

def extract_pages_from_pdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_data = []

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        raw_page_text = page.extract_text() or ""
        cleaned_text = re.sub(r"[ \t]+", " ", raw_page_text).strip()

        lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
        section_title = f"Page {page_num}"
        for line in lines[:5]:
            if len(line) < 70 and (
                line.isupper()
                or re.match(r"^(\d+\.|\bSection\b|\bChapter\b|\bPart\b)", line, re.I)
                or any(
                    kw in line.lower()
                    for kw in ["tone", "voice", "banned", "vocabulary", "messaging", "claims", "required", "guidelines"]
                )
            ):
                section_title = line
                break

        pages_data.append(
            {
                "page_number": page_num,
                "section_title": section_title,
                "text": cleaned_text,
                "lines": lines,
            }
        )

    return pages_data


def extract_rules_from_pages(pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    rules: List[Dict[str, Any]] = []
    banned_words_set = set()
    required_phrases_set = set()
    tone_descriptors = []

    for page in pages_data:
        page_num = page["page_number"]
        section = page["section_title"]
        text = page["text"]

        if not text:
            continue

        segments = re.split(r"(?<=[.!?])\s+|\n+", text)
        for seg in segments:
            s = seg.strip(" •-*-\t")
            if len(s) < 8:
                continue
            s_lower = s.lower()

            # Banned Words
            banned_match = re.search(
                r"(?:banned words?|never use|avoid using|prohibited terms?|do not use|forbidden words?)\s*[:\-–]\s*(.+)",
                s,
                re.I,
            )
            if banned_match:
                raw_items = banned_match.group(1)
                words = [
                    w.strip(" \"'.,;()[]")
                    for w in re.split(r",|;|\bor\b|\band\b", raw_items)
                    if w.strip(" \"'.,;()[]")
                ]
                for w in words:
                    if 2 <= len(w) <= 40:
                        banned_words_set.add(w.lower())
                        rules.append(
                            {
                                "category": "banned_word",
                                "rule_text": f'Never use the banned word or phrase "{w}".',
                                "target_value": w,
                                "severity": "critical",
                                "page_number": page_num,
                                "section_title": section,
                                "source_quote": s[:220],
                                "approved": 0,
                            }
                        )
                continue

            if any(k in s_lower for k in ["never use", "do not use", "avoid the word", "prohibited", "ban on"]):
                quoted = re.findall(r'["\u201c\u201d\']([^"\u201c\u201d\']{2,35})["\u201c\u201d\']', s)
                if quoted:
                    for q in quoted:
                        banned_words_set.add(q.lower())
                        rules.append(
                            {
                                "category": "banned_word",
                                "rule_text": f'Do not use the restricted term "{q}".',
                                "target_value": q,
                                "severity": "critical",
                                "page_number": page_num,
                                "section_title": section,
                                "source_quote": s[:220],
                                "approved": 0,
                            }
                        )
                    continue

            # Required Phrases
            req_match = re.search(
                r"(?:required phrases?|always include|must include|mandatory phrase|mandatory disclaimer|official tagline)\s*[:\-–]\s*(.+)",
                s,
                re.I,
            )
            if req_match:
                raw_req = req_match.group(1).strip()
                quoted_reqs = re.findall(r'["\u201c\u201d\']([^"\u201c\u201d\']{3,80})["\u201c\u201d\']', raw_req)
                targets = quoted_reqs if quoted_reqs else [
                    p.strip(" \"'.,;") for p in re.split(r",|;", raw_req) if len(p.strip(" \"'.,;")) >= 3
                ]
                for req in targets:
                    required_phrases_set.add(req)
                    rules.append(
                        {
                            "category": "required_phrase",
                            "rule_text": f'All marketing copy must include the phrase "{req}".',
                            "target_value": req,
                            "severity": "critical",
                            "page_number": page_num,
                            "section_title": section,
                            "source_quote": s[:220],
                            "approved": 0,
                        }
                    )
                continue

            if any(k in s_lower for k in ["must include", "always include", "required to state", "always end with"]):
                quoted = re.findall(r'["\u201c\u201d\']([^"\u201c\u201d\']{3,80})["\u201c\u201d\']', s)
                if quoted:
                    for q in quoted:
                        required_phrases_set.add(q)
                        rules.append(
                            {
                                "category": "required_phrase",
                                "rule_text": f'Content must include the required phrase "{q}".',
                                "target_value": q,
                                "severity": "critical",
                                "page_number": page_num,
                                "section_title": section,
                                "source_quote": s[:220],
                                "approved": 0,
                            }
                        )
                    continue

            # Claims
            if any(k in s_lower for k in ["claim", "substantiat", "superlative", "guarantee", "100%", "medical", "scientific", "exaggerat", "competitor"]):
                rules.append(
                    {
                        "category": "claim",
                        "rule_text": s,
                        "target_value": "unverified claims / superlatives",
                        "severity": "critical" if any(w in s_lower for w in ["never", "must", "prohibit", "illegal"]) else "warning",
                        "page_number": page_num,
                        "section_title": section,
                        "source_quote": s[:220],
                        "approved": 0,
                    }
                )
                continue

            # Tone
            if any(k in s_lower for k in ["tone", "voice", "empathetic", "professional", "confident", "slang", "jargon", "aggressive", "fear-mongering", "all-caps", "exclamation"]):
                tone_descriptors.append(s)
                rules.append(
                    {
                        "category": "tone",
                        "rule_text": s,
                        "target_value": "brand tone",
                        "severity": "warning",
                        "page_number": page_num,
                        "section_title": section,
                        "source_quote": s[:220],
                        "approved": 0,
                    }
                )
                continue

            # Messaging
            if any(k in s_lower for k in ["messaging", "brand promise", "value proposition", "customer-first", "sustainability", "transparency", "inclusive"]):
                rules.append(
                    {
                        "category": "messaging",
                        "rule_text": s,
                        "target_value": "brand messaging",
                        "severity": "warning",
                        "page_number": page_num,
                        "section_title": section,
                        "source_quote": s[:220],
                        "approved": 0,
                    }
                )

    unique_rules = []
    seen = set()
    for r in rules:
        key = (r["category"], r["target_value"].lower().strip(), r["rule_text"].lower().strip()[:80])
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)

    if not unique_rules and pages_data:
        first_page = pages_data[0]
        snippet = (first_page["text"] or "Maintain professional, accurate, customer-centric messaging.")[:180]
        unique_rules.append(
            {
                "category": "tone",
                "rule_text": "Maintain a professional, clear, and trustworthy brand tone without unverified hype.",
                "target_value": "professional tone",
                "severity": "warning",
                "page_number": 1,
                "section_title": first_page["section_title"],
                "source_quote": snippet,
                "approved": 0,
            }
        )

    tone_profile = " ".join(tone_descriptors[:3]) if tone_descriptors else "Professional, clear, trustworthy, and customer-focused."

    return {
        "banned_words": sorted(list(banned_words_set)),
        "required_phrases": sorted(list(required_phrases_set)),
        "tone_profile": tone_profile,
        "rules": unique_rules,
    }


# =====================================================================
# 2. BETTER CONTENT CHECKING
# =====================================================================

DEFAULT_CLAIM_TRIGGERS = [
    (r"\b100%\s+(?:guaranteed|effective|safe|cure|proven)\b", "Absolute 100% guarantee claim", "Replace with specific, verifiable performance metrics"),
    (r"\b(?:instant|overnight|miracle)\s+(?:results|cure|success|wealth)\b", "Unrealistic instant/miracle outcome claim", "Describe realistic timelines and typical customer outcomes"),
    (r"\b(?:#1|number one|best in the world|unbeatable)\b", "Unsubstantiated superlative superiority claim", "Cite an independent award/study or focus on specific product strengths"),
    (r"\bno\s+risk\b|\bzero\s+risk\b", "Absolute zero-risk claim", "Clarify the exact terms, warranty, or trial policy"),
]

AGGRESSIVE_TONE_PATTERNS = [
    (r"!!+", "Excessive exclamation marks", "Use a single period or exclamation mark to maintain a composed brand tone."),
    (r"\b[A-Z]{5,}\b", "ALL-CAPS shouting word", "Convert ALL-CAPS words to standard title or sentence case."),
    (r"\b(?:buy now or regret|don't be stupid|you'd be crazy not to|last chance ever|act immediately or lose)\b", "High-pressure urgency language", "Use respectful, benefit-driven calls to action instead of fear-based urgency."),
]


def run_comprehensive_content_check(text: str, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    corrected_text = text

    banned_rules = [r for r in rules if r["category"] == "banned_word" and r.get("target_value")]
    required_rules = [r for r in rules if r["category"] == "required_phrase" and r.get("target_value")]
    tone_rules = [r for r in rules if r["category"] == "tone"]
    claim_rules = [r for r in rules if r["category"] == "claim"]

    smart_replacements = {
        "cheap": "accessible",
        "cheapest": "most cost-effective",
        "guaranteed": "designed to deliver",
        "100% guaranteed": "backed by our satisfaction commitment",
        "miracle": "breakthrough",
        "revolutionary": "modern",
        "crush": "outperform",
        "kill": "eliminate",
        "hack": "streamline",
        "free money": "bonus credit",
        "no-brainer": "smart choice",
        "synergy": "collaboration",
        "disruptive": "innovative",
        "best in the world": "industry-leading",
    }

    # 1. Banned Words
    for r in banned_rules:
        target = r["target_value"].strip()
        if not target:
            continue
        pattern = re.compile(rf"\b{re.escape(target)}\b", re.IGNORECASE)
        matches = list(pattern.finditer(text))
        if matches:
            found_word = matches[0].group(0)
            replacement = smart_replacements.get(target.lower(), "[approved brand term]")
            issues.append(
                {
                    "category": "banned_word",
                    "title": f'Banned Word Detected: "{found_word}"',
                    "severity": r.get("severity") or "critical",
                    "offending_text": found_word,
                    "occurrences": len(matches),
                    "what_is_wrong": f'The term "{found_word}" is explicitly prohibited by the brand guidelines ({r["rule_text"]}). Using restricted vocabulary weakens brand positioning.',
                    "how_to_fix": f'Remove "{found_word}" and replace it with "{replacement}" or neutral, benefit-focused wording.',
                    "suggested_replacement": replacement,
                    "rule_id": r["id"],
                    "page_number": r["page_number"],
                    "section_title": r["section_title"],
                    "source_quote": r["source_quote"],
                }
            )
            corrected_text = pattern.sub(replacement, corrected_text)

    # 2. Required Phrases
    for r in required_rules:
        req_phrase = r["target_value"].strip()
        if not req_phrase:
            continue
        if req_phrase.lower() not in text.lower():
            issues.append(
                {
                    "category": "required_phrase",
                    "title": f'Missing Required Phrase: "{req_phrase}"',
                    "severity": r.get("severity") or "critical",
                    "offending_text": "(Missing from content)",
                    "occurrences": 1,
                    "what_is_wrong": f'The mandatory brand phrase or disclaimer "{req_phrase}" is missing from this content. {r["rule_text"]}',
                    "how_to_fix": f'Append or naturally integrate "{req_phrase}" into the closing call-to-action or footer.',
                    "suggested_replacement": req_phrase,
                    "rule_id": r["id"],
                    "page_number": r["page_number"],
                    "section_title": r["section_title"],
                    "source_quote": r["source_quote"],
                }
            )
            if req_phrase.lower() not in corrected_text.lower():
                corrected_text = corrected_text.rstrip() + f"\n\n{req_phrase}"

    # 3. Claims
    linked_claim_rule = claim_rules[0] if claim_rules else {
        "id": None,
        "page_number": 1,
        "section_title": "Claims & Legal Compliance",
        "source_quote": "All product claims must be substantiated and avoid exaggerated superlatives.",
    }
    for regex_pat, claim_label, fix_advice in DEFAULT_CLAIM_TRIGGERS:
        for match in re.finditer(regex_pat, text, re.IGNORECASE):
            found_claim = match.group(0)
            if any(i["offending_text"].lower() == found_claim.lower() for i in issues):
                continue
            issues.append(
                {
                    "category": "claim",
                    "title": f"Unsubstantiated Claim: {claim_label}",
                    "severity": "critical",
                    "offending_text": found_claim,
                    "occurrences": 1,
                    "what_is_wrong": f'The phrase "{found_claim}" makes an absolute or unverified superiority claim that risks compliance issues.',
                    "how_to_fix": fix_advice,
                    "suggested_replacement": "proven in customer workflows",
                    "rule_id": linked_claim_rule.get("id"),
                    "page_number": linked_claim_rule.get("page_number", 1),
                    "section_title": linked_claim_rule.get("section_title", "Claims"),
                    "source_quote": linked_claim_rule.get("source_quote", ""),
                }
            )
            corrected_text = re.sub(re.escape(found_claim), "proven in customer workflows", corrected_text, flags=re.I)

    # 4. Tone
    linked_tone_rule = tone_rules[0] if tone_rules else {
        "id": None,
        "page_number": 1,
        "section_title": "Brand Voice & Tone",
        "source_quote": "Maintain a calm, respectful, and professional tone without shouting.",
    }
    for regex_pat, tone_label, fix_advice in AGGRESSIVE_TONE_PATTERNS:
        for match in re.finditer(regex_pat, text):
            found_tone = match.group(0)
            if found_tone in {"HTTPS", "GDPR", "HIPAA", "SOCII", "ASCII"}:
                continue
            replacement = found_tone.capitalize() if found_tone.isupper() else "."
            issues.append(
                {
                    "category": "tone",
                    "title": f"Tone Violation: {tone_label}",
                    "severity": "warning",
                    "offending_text": found_tone,
                    "occurrences": 1,
                    "what_is_wrong": f'"{found_tone}" conflicts with the brand tone guidelines.',
                    "how_to_fix": fix_advice,
                    "suggested_replacement": replacement,
                    "rule_id": linked_tone_rule.get("id"),
                    "page_number": linked_tone_rule.get("page_number", 1),
                    "section_title": linked_tone_rule.get("section_title", "Tone"),
                    "source_quote": linked_tone_rule.get("source_quote", ""),
                }
            )
            if found_tone.isupper() and len(found_tone) >= 5:
                corrected_text = corrected_text.replace(found_tone, found_tone.capitalize())
            elif "!!" in found_tone:
                corrected_text = corrected_text.replace(found_tone, "!")

    # Calculate Score
    deductions = 0
    for issue in issues:
        sev = issue["severity"]
        if sev == "critical":
            deductions += 25
        elif sev == "warning":
            deductions += 12
        else:
            deductions += 5

    overall_score = max(0, 100 - deductions)
    critical_count = sum(1 for i in issues if i["severity"] == "critical")

    if overall_score >= 90 and critical_count == 0:
        status = "PASS"
    elif overall_score >= 60 and critical_count == 0:
        status = "NEEDS_REVISION"
    else:
        status = "FAIL"

    summary = (
        f"Content passed all {len(rules)} active brand rules with a score of {overall_score}/100."
        if not issues
        else f"Found {len(issues)} issue(s) ({critical_count} critical) across {len(rules)} active rules. Compliance score: {overall_score}/100."
    )

    return {
        "overall_score": overall_score,
        "status": status,
        "summary": summary,
        "issues": issues,
        "corrected_text": corrected_text,
    }


def build_sample_guideline_pdf() -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Page 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 60, "ACME CLOUD - OFFICIAL BRAND GUIDELINES (2026)")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 90, "Section 1: Core Brand Messaging & Positioning")
    c.setFont("Helvetica", 10)
    p1 = [
        "Our messaging must always remain customer-first, transparent, and empowering.",
        "Required Phrases: \"Built for modern teams\", \"Acme Cloud\"",
        "Always include \"Built for modern teams\" in campaign landing pages and announcements.",
        "Never disparage competitors or use negative fear-mongering messaging.",
    ]
    y = height - 120
    for line in p1:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()

    # Page 2
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 60, "Section 2: Vocabulary & Banned Words Policy")
    c.setFont("Helvetica", 10)
    p2 = [
        "Words matter. Certain words undermine our credibility and are strictly prohibited.",
        "Banned Words: cheap, guaranteed, miracle, synergy, hack, no-brainer, disruptive",
        "Never use \"cheap\" when describing our pricing tiers; use \"accessible\" instead.",
        "Do not use \"hack\" or \"no-brainer\" in enterprise communications.",
    ]
    y = height - 90
    for line in p2:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()

    # Page 3
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 60, "Section 3: Tone of Voice & Style Standards")
    c.setFont("Helvetica", 10)
    p3 = [
        "Our tone of voice is confident, empathetic, clear, and professional.",
        "Avoid ALL-CAPS shouting, excessive exclamation marks (!!), and manipulative urgency.",
    ]
    y = height - 90
    for line in p3:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()

    # Page 4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 60, "Section 4: Product Claims & Legal Compliance")
    c.setFont("Helvetica", 10)
    p4 = [
        "All performance claims must be substantiated by verified customer benchmarks.",
        "Never make 100% guaranteed or zero-risk promises in marketing copy.",
        "Avoid unverified superlative claims such as \"#1 in the world\" or \"instant results\".",
    ]
    y = height - 90
    for line in p4:
        c.drawString(50, y, line)
        y -= 22
    c.save()
    return buffer.getvalue()


DEFAULT_BENCHMARK_SAMPLES: List[SampleCase] = [
    SampleCase(
        id="sample-1",
        title="Compliant Product Launch Email",
        content="Discover how Acme Cloud helps engineering and design teams collaborate faster with accessible plans. Built for modern teams.",
        expected_compliant=True,
    ),
    SampleCase(
        id="sample-2",
        title="Banned Words & Missing Required Phrase",
        content="Looking for a cheap cloud tool? This growth hack is a total no-brainer for startups that want disruptive synergy right away.",
        expected_compliant=False,
    ),
    SampleCase(
        id="sample-3",
        title="Exaggerated Claims & Shouting Copy",
        content="ACME CLOUD IS #1 IN THE WORLD!! Get 100% guaranteed instant results with zero risk!! Built for modern teams.",
        expected_compliant=False,
    ),
]


# =====================================================================
# API ROUTER (AVAILABLE AT BOTH / AND /api/)
# =====================================================================

@router.get("/health")
def health_check():
    return {"status": "ok", "round": 3, "timestamp": datetime.utcnow().isoformat()}


@router.post("/guidelines/upload")
async def upload_guideline_pdf(file: UploadFile = File(...), name: Optional[str] = Form(None)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    pages_data = extract_pages_from_pdf(pdf_bytes)
    if not pages_data:
        raise HTTPException(status_code=400, detail="No readable pages found in PDF.")

    extracted = extract_rules_from_pages(pages_data)
    full_text = "\n\n".join([f"--- Page {p['page_number']} ({p['section_title']}) ---\n{p['text']}" for p in pages_data])
    guideline_name = name or file.filename.rsplit(".", 1)[0].replace("_", " ").title()

    guideline_id = db.create_guideline(
        name=guideline_name,
        filename=file.filename,
        total_pages=len(pages_data),
        raw_text=full_text,
        banned_words=extracted["banned_words"],
        required_phrases=extracted["required_phrases"],
        tone_profile=extracted["tone_profile"],
        extracted_rules=extracted["rules"],
    )
    return db.get_guideline_by_id(guideline_id)


@router.post("/guidelines/load-demo")
def load_demo_guideline():
    pdf_bytes = build_sample_guideline_pdf()
    pages_data = extract_pages_from_pdf(pdf_bytes)
    extracted = extract_rules_from_pages(pages_data)
    full_text = "\n\n".join([f"--- Page {p['page_number']} ({p['section_title']}) ---\n{p['text']}" for p in pages_data])

    for r in extracted["rules"]:
        r["approved"] = 1

    guideline_id = db.create_guideline(
        name="Acme Cloud Brand Guidelines (4-Page Demo)",
        filename="acme_cloud_guidelines_v3.pdf",
        total_pages=len(pages_data),
        raw_text=full_text,
        banned_words=extracted["banned_words"],
        required_phrases=extracted["required_phrases"],
        tone_profile=extracted["tone_profile"],
        extracted_rules=extracted["rules"],
    )
    return db.get_guideline_by_id(guideline_id)


@router.get("/guidelines")
def list_guidelines():
    return db.get_guidelines()


@router.get("/guidelines/{guideline_id}")
def get_guideline(guideline_id: int):
    g = db.get_guideline_by_id(guideline_id)
    if not g:
        raise HTTPException(status_code=404, detail="Guideline not found.")
    return g


@router.put("/rules/{rule_id}")
def update_single_rule(rule_id: int, payload: RuleUpdateRequest):
    updated = db.update_rule(
        rule_id=rule_id,
        approved=payload.approved,
        rule_text=payload.rule_text,
        target_value=payload.target_value,
        severity=payload.severity,
        category=payload.category,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return updated


@router.post("/guidelines/{guideline_id}/approve-all")
def approve_all_guideline_rules(guideline_id: int, approved: int = Query(1)):
    count = db.bulk_approve_rules(guideline_id, approved_status=approved)
    return {"guideline_id": guideline_id, "updated_rules": count, "approved": approved}


@router.post("/check-content")
def check_marketing_content(payload: ContentCheckRequest):
    guideline = db.get_guideline_by_id(payload.guideline_id)
    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found.")

    all_rules = guideline.get("rules", [])
    active_rules = [r for r in all_rules if r["approved"] == 1] if payload.only_approved_rules else all_rules

    if not active_rules:
        active_rules = all_rules

    analysis = run_comprehensive_content_check(payload.text, active_rules)
    saved = db.save_content_check(
        guideline_id=payload.guideline_id,
        content_title=payload.content_title,
        submitted_text=payload.text,
        overall_score=analysis["overall_score"],
        status=analysis["status"],
        summary=analysis["summary"],
        issues=analysis["issues"],
        corrected_text=analysis["corrected_text"],
    )
    saved["active_rules_count"] = len(active_rules)
    return saved


@router.get("/checks")
def list_recent_checks(guideline_id: Optional[int] = None):
    return db.get_content_checks(guideline_id)


@router.get("/reports/{check_id}/download")
def download_compliance_report(check_id: int, format: str = Query("md")):
    check = db.get_content_check_by_id(check_id)
    if not check:
        raise HTTPException(status_code=404, detail="Check report not found.")

    guideline = db.get_guideline_by_id(check["guideline_id"]) or {"name": "Brand Guideline"}
    issues = check["issues"]

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Issue #", "Category", "Severity", "Offending Text", "What Is Wrong", "How To Fix", "Suggested Replacement", "Rule Page"])
        for idx, i in enumerate(issues, start=1):
            writer.writerow([idx, i.get("category"), i.get("severity"), i.get("offending_text"), i.get("what_is_wrong"), i.get("how_to_fix"), i.get("suggested_replacement"), f"Page {i.get('page_number', 1)}"])
        return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="preflight_report_{check_id}.csv"'})

    if format == "html":
        html_doc = f"<html><body><h1>Preflight Report #{check_id}</h1><p>Score: {check['overall_score']}/100 ({check['status']})</p><pre>{check['submitted_text']}</pre></body></html>"
        return Response(content=html_doc, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="preflight_report_{check_id}.html"'})

    # Default .md
    md_lines = [
        f"# Preflight Compliance Report (#{check_id})",
        f"- **Guideline:** {guideline['name']}",
        f"- **Score:** {check['overall_score']}/100 ({check['status']})",
        "",
        "## Summary",
        check["summary"],
        "",
        "## Submitted Copy",
        "```text",
        check["submitted_text"],
        "```",
        "",
        f"## Issues Found ({len(issues)})",
    ]
    for idx, i in enumerate(issues, start=1):
        md_lines.append(f"{idx}. [{i.get('severity','').upper()}] {i.get('title','')} (Page {i.get('page_number',1)}): {i.get('what_is_wrong')} -> Fix: `{i.get('suggested_replacement')}`")
    return Response(content="\n".join(md_lines), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="preflight_report_{check_id}.md"'})


@router.post("/benchmark/run")
def run_accuracy_benchmark(payload: BenchmarkRequest):
    guideline = db.get_guideline_by_id(payload.guideline_id)
    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found.")

    active_rules = [r for r in guideline.get("rules", []) if r["approved"] == 1] or guideline.get("rules", [])
    samples = payload.samples or DEFAULT_BENCHMARK_SAMPLES
    results = []
    tp, tn, fp, fn = 0, 0, 0, 0

    for sample in samples:
        check_res = run_comprehensive_content_check(sample.content, active_rules)
        predicted_compliant = check_res["status"] == "PASS" and len(check_res["issues"]) == 0
        is_correct = predicted_compliant == sample.expected_compliant

        if not sample.expected_compliant and not predicted_compliant:
            tp += 1
        elif sample.expected_compliant and predicted_compliant:
            tn += 1
        elif sample.expected_compliant and not predicted_compliant:
            fp += 1
        else:
            fn += 1

        saved = db.save_content_check(
            guideline_id=payload.guideline_id,
            content_title=f"[Benchmark] {sample.title}",
            submitted_text=sample.content,
            overall_score=check_res["overall_score"],
            status=check_res["status"],
            summary=check_res["summary"],
            issues=check_res["issues"],
            corrected_text=check_res["corrected_text"],
        )
        results.append({
            "sample_id": sample.id,
            "check_id": saved["id"],
            "title": sample.title,
            "content": sample.content,
            "is_correct": is_correct,
            "overall_score": check_res["overall_score"],
            "status": check_res["status"],
        })

    total = len(samples)
    accuracy = round((tp + tn) / total * 100, 1) if total else 100.0
    precision = round(tp / (tp + fp) * 100, 1) if (tp + fp) > 0 else 100.0
    recall = round(tp / (tp + fn) * 100, 1) if (tp + fn) > 0 else 100.0
    f1 = round(2 * (precision * recall) / (precision + recall), 1) if (precision + recall) > 0 else 100.0

    return db.save_benchmark_run(
        guideline_id=payload.guideline_id,
        total_samples=total,
        accuracy=accuracy,
        precision_score=precision,
        recall_score=recall,
        f1_score=f1,
        results=results,
    )


# Mount the router at both root and /api for full compatibility
app.include_router(router)
app.include_router(router, prefix="/api")

# Explicit handler alias required for Vercel Python serverless runtime
handler = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
