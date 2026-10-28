import sys
sys.path.insert(0, 'backend')
import main
import asyncio
from fastapi import UploadFile, HTTPException
import io

async def test_extract():
    print("Testing blank/unreadable PDF validation...")
    try:
        with open('backend/test_blank.pdf', 'rb') as f:
            blank_bytes = f.read()
        upload_blank = UploadFile(filename='test_blank.pdf', file=io.BytesIO(blank_bytes))
        await main.extract_brand_guidelines(upload_blank)
        print("ERROR: Blank PDF should have raised 422!")
    except HTTPException as e:
        print(f"PASS: Blank PDF rejected as expected with code {e.status_code}: {e.detail[:50]}...")

    print("\nTesting valid Brand Guidelines PDF extraction with Gemini...")
    with open('backend/test_guidelines.pdf', 'rb') as f:
        file_bytes = f.read()
    upload = UploadFile(filename='test_guidelines.pdf', file=io.BytesIO(file_bytes))
    res = await main.extract_brand_guidelines(upload)
    print(f"SUCCESS: Extracted {len(res.proposed_rules)} proposed rules using {res.model_used}!")
    for idx, r in enumerate(res.proposed_rules, 1):
        print(f"{idx}. [{r.type}] {r.name} (Severity: {r.severity})")
        print(f"   Excerpt: \"{r.source_excerpt}\"")
        print(f"   Description: {r.description}")

if __name__ == '__main__':
    asyncio.run(test_extract())
