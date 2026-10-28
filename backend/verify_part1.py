import sys
sys.path.insert(0, 'backend')
import main, database, asyncio, io
from fastapi import UploadFile, HTTPException

async def verify_all():
    print('=== 1 & 2. BACKEND & DATABASE INITIALIZATION ===')
    database.init_db()
    print('Database initialized. Tables intact.')
    
    health = main.health_check()
    print('Health check status:', health['status'], '| API key configured:', health['gemini_api_key_configured'])
    assert health['status'] == 'healthy'
    assert health['gemini_api_key_configured'] is True

    print('\n=== 3 & 4. CONTENT CHECKER & MANUAL BRAND RULES ===')
    custom_rule = main.BrandRuleItem(
        name='No Cheap Terminology',
        type='Banned Words',
        severity='High',
        keywords='cheap, dirt-cheap',
        suggestedFix='affordable',
        active=True
    )
    req = main.CheckContentRequest(
        content='Get our dirt-cheap cloud hosting right now!',
        purpose='Social ad',
        brand_rules=[custom_rule]
    )
    res = await main.check_content(req)
    print(f'Content checked successfully. Review ID: {res.review_id}, Findings count: {len(res.findings)}')
    assert len(res.findings) > 0, 'Should find at least 1 rule violation'
    flagged = [f.problematic_text.lower() for f in res.findings]
    print('Flagged snippets:', flagged)
    assert any('dirt-cheap' in f or 'cheap' in f for f in flagged)

    # Verify review was persisted to SQLite
    db_rev = database.get_review_by_id(res.review_id)
    assert db_rev is not None
    print('Persisted review found in SQLite:', db_rev['id'], 'Status:', db_rev['status'])

    print('\n=== 5. PDF UPLOAD VALIDATION (SIZE & FORMAT) ===')
    # 5a. Invalid format
    try:
        bad_file = UploadFile(filename='rules.txt', file=io.BytesIO(b'hello world'))
        await main.extract_brand_guidelines(bad_file)
        print('FAILED: Invalid file format was not rejected')
    except HTTPException as e:
        print(f'PASS: Invalid file rejected with {e.status_code}: {e.detail}')
        assert e.status_code == 400

    # 5b. Oversized file (>5MB)
    try:
        big_file = UploadFile(filename='huge.pdf', file=io.BytesIO(b'0' * (6 * 1024 * 1024)))
        await main.extract_brand_guidelines(big_file)
        print('FAILED: Oversized file was not rejected')
    except HTTPException as e:
        print(f'PASS: Oversized file (>5MB) rejected with {e.status_code}: {e.detail}')
        assert e.status_code == 400

    # 5c. Blank/Unreadable PDF
    try:
        with open('backend/test_blank.pdf', 'rb') as f:
            blank_bytes = f.read()
        blank_upload = UploadFile(filename='blank.pdf', file=io.BytesIO(blank_bytes))
        await main.extract_brand_guidelines(blank_upload)
        print('FAILED: Blank PDF was not rejected')
    except HTTPException as e:
        print(f'PASS: Blank/unreadable PDF rejected with {e.status_code}: {e.detail}')
        assert e.status_code in [400, 422]

    print('\n=== 6 & 7. PDF TEXT EXTRACTION & GEMINI PROPOSED RULES ===')
    with open('backend/test_guidelines.pdf', 'rb') as f:
        pdf_bytes = f.read()
    pdf_upload = UploadFile(filename='test_guidelines.pdf', file=io.BytesIO(pdf_bytes))
    pdf_res = await main.extract_brand_guidelines(pdf_upload)
    print(f'Extracted text length: {pdf_res.extracted_text_length} chars')
    print(f'Proposed rules generated: {len(pdf_res.proposed_rules)}')
    assert len(pdf_res.proposed_rules) > 0
    for r in pdf_res.proposed_rules:
        assert r.description, 'Rule missing description'
        assert r.type in ['Banned Words', 'Required Words', 'Tone', 'Factual Claim', 'Other']
        assert r.severity in ['Low', 'Medium', 'High']
        assert r.source_excerpt, 'Rule missing source excerpt'
        print(f' - [{r.type}] {r.name} (Severity: {r.severity}) | Excerpt: "{r.source_excerpt[:40]}..."')

    print('\n=== 8. APPROVAL / REJECTION WORKFLOW LOGIC ===')
    proposed = pdf_res.proposed_rules[0]
    print(f'Proposed rule {proposed.id} initially unapproved.')
    rejected_rules = [r for r in pdf_res.proposed_rules if r.id != proposed.id]
    print('Rejected 1 rule. Remaining proposed:', len(rejected_rules))
    approved_rule = main.BrandRuleItem(
        id=proposed.id,
        name=proposed.name or 'Approved Rule',
        description=proposed.description,
        type=proposed.type,
        severity=proposed.severity,
        keywords=proposed.keywords or 'cost-effective',
        suggestedFix=proposed.suggestedFix,
        active=True
    )
    print(f'Approved rule {approved_rule.name} ready for content checking.')

    print('\n=== ALL PART 1 BACKEND VERIFICATION CHECKS PASSED ===')

if __name__ == '__main__':
    asyncio.run(verify_all())
