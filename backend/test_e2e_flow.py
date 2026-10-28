import sys
sys.path.insert(0, 'backend')
import main
import asyncio
from fastapi import UploadFile
import io

async def test_end_to_end_flow():
    print("--- 1. Testing PDF Upload & Rule Extraction ---")
    with open('backend/test_guidelines.pdf', 'rb') as f:
        file_bytes = f.read()
    upload = UploadFile(filename='test_guidelines.pdf', file=io.BytesIO(file_bytes))
    extract_res = await main.extract_brand_guidelines(upload)
    
    print(f"Extracted {len(extract_res.proposed_rules)} proposed rules.")
    assert len(extract_res.proposed_rules) > 0, "Should have extracted at least 1 rule"
    
    proposed = extract_res.proposed_rules[0]
    print(f"Selected Rule: [{proposed.type}] {proposed.name}")
    print(f"Excerpt: \"{proposed.source_excerpt}\"")
    
    # Simulate Admin Approval
    approved_rule = {
        "id": proposed.id,
        "name": proposed.name,
        "description": proposed.description,
        "type": proposed.type,
        "severity": proposed.severity,
        "keywords": proposed.keywords or "cheap, cheapest",
        "suggestedFix": proposed.suggestedFix or "cost-effective",
        "active": True
    }
    print("\n--- 2. Simulated Admin Approval of Proposed Rule ---")
    print(f"Rule '{approved_rule['name']}' approved into active rules set.")

    # Test Content Checking using the approved rule
    print("\n--- 3. Testing Content Checker With Approved Rule ---")
    test_copy = "We provide the cheapest and most reliable platform in the market."
    check_req = main.CheckContentRequest(
        content=test_copy,
        purpose="Homepage hero announcement",
        brand_rules=[main.BrandRuleItem(**approved_rule)]
    )
    
    check_res = await main.check_content(check_req)
    print(f"Review created: {check_res.review_id}")
    print(f"Gemini findings count: {len(check_res.findings)}")
    for f in check_res.findings:
        print(f" - Flagged text: \"{f.problematic_text}\" | Category: {f.category} | Severity: {f.severity}")
        print(f"   Reason: {f.explanation}")
        print(f"   Rewrite: \"{f.suggested_rewrite}\"")

    # Verify review was persisted in SQLite
    print("\n--- 4. Verifying Review Persistence in SQLite ---")
    db_review = main.get_review_by_id(check_res.review_id)
    assert db_review is not None, "Review must be found in SQLite database"
    print(f"Review {db_review['id']} successfully verified in SQLite database with status: {db_review['status']}.")
    print("\nALL END-TO-END TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    asyncio.run(test_end_to_end_flow())
