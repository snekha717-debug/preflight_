import sys
sys.path.insert(0, 'backend')
import main, database, asyncio, io, json
from fastapi import UploadFile, HTTPException

async def test_image_pipeline():
    print("=== TESTING IMAGE BRAND-COMPLIANCE BACKEND ENDPOINT ===")
    
    # 1. Test invalid file format rejection
    print("\n1. Testing invalid image format rejection...")
    try:
        bad_file = UploadFile(filename='creative.svg', file=io.BytesIO(b'<svg></svg>'))
        await main.check_image(file=bad_file, purpose="Display ad", brand_rules="[]")
        print("FAILED: Did not reject .svg")
    except HTTPException as e:
        print(f"PASS: Rejected invalid format (.svg) with code {e.status_code}: {e.detail}")
        assert e.status_code == 400

    # 2. Test oversized image rejection (>5 MB)
    print("\n2. Testing oversized image rejection (>5 MB)...")
    try:
        big_file = UploadFile(filename='large.png', file=io.BytesIO(b'0' * (6 * 1024 * 1024)))
        await main.check_image(file=big_file, purpose="Display ad", brand_rules="[]")
        print("FAILED: Did not reject oversized image")
    except HTTPException as e:
        print(f"PASS: Rejected oversized image with code {e.status_code}: {e.detail}")
        assert e.status_code == 400

    # 3. Test genuine image upload and Gemini multimodal inspection
    print("\n3. Testing valid creative image audit with Gemini...")
    with open('backend/test_creative_ad.png', 'rb') as f:
        img_bytes = f.read()

    active_rules = [
        {
            "name": "No Cheap Wordings",
            "type": "Banned Words",
            "severity": "High",
            "keywords": "cheapest, cheap",
            "suggestedFix": "cost-effective",
            "description": "Never use cheap or cheapest in creatives.",
            "active": True
        },
        {
            "name": "No ROI Guarantees",
            "type": "Factual Claim",
            "severity": "High",
            "keywords": "guarantee 10x ROI",
            "suggestedFix": "accelerate benchmarked returns",
            "description": "Unverified financial outcome promises violate FTC standards.",
            "active": True
        }
    ]

    upload = UploadFile(filename='test_creative_ad.png', file=io.BytesIO(img_bytes))
    res = await main.check_image(
        file=upload,
        purpose="Q4 Enterprise Cloud Display Banner",
        brand_rules=json.dumps(active_rules)
    )

    print(f"SUCCESS: Review ID created: {res.review_id}")
    print(f"Findings detected in image: {len(res.findings)}")
    assert len(res.findings) > 0, "Should have detected rule violations in the creative"

    for idx, f in enumerate(res.findings, 1):
        print(f"\nFinding {idx}: [{f.category}] (Severity: {f.severity})")
        print(f" - Visual Evidence: \"{f.evidence}\"")
        print(f" - Explanation: {f.explanation}")
        print(f" - Suggested Correction: {f.suggested_correction}")
        print(f" - Requires Human Review: {f.requires_human_review}")

    # 4. Verify Review is stored in SQLite
    print("\n4. Verifying persistence in SQLite database...")
    db_rev = database.get_review_by_id(res.review_id)
    assert db_rev is not None, "Image review must be saved in database"
    print(f"PASS: Verified review {db_rev['id']} stored in SQLite with {db_rev['findings_count']} findings.")
    print("\nALL IMAGE COMPLIANCE TESTS COMPLETED SUCCESSFULLY!")

if __name__ == '__main__':
    asyncio.run(test_image_pipeline())
