# backend/test_round3_e2e.py
from fastapi.testclient import TestClient
from main import app, build_sample_guideline_pdf

client = TestClient(app)


def run_round3_verification():
    print("=" * 70)
    print("PREFLIGHT ROUND 3 - END-TO-END VERIFICATION SUITE")
    print("=" * 70)

    # 1. Test Multi-Page PDF Upload & Provenance Extraction
    pdf_bytes = build_sample_guideline_pdf()
    files = {"file": ("acme_brand_guidelines.pdf", pdf_bytes, "application/pdf")}
    data = {"name": "Acme Cloud 4-Page Guidelines"}

    res = client.post("/guidelines/upload", files=files, data=data)
    assert res.status_code == 200, f"Upload failed: {res.text}"
    guideline = res.json()
    guideline_id = guideline["id"]
    rules = guideline["rules"]

    print(f"\n[1. Better PDF Reading]")
    print(f"  - Uploaded PDF Pages Read : {guideline['total_pages']} pages")
    print(f"  - Extracted Brand Rules   : {len(rules)} rules")
    print(f"  - Banned Words Found      : {guideline['banned_words']}")
    print(f"  - Required Phrases Found  : {guideline['required_phrases']}")
    for r in rules[:4]:
        print(
            f"    * [Page {r['page_number']} | {r['category']}] {r['rule_text']} "
            f"(Source: \"{r['source_quote'][:60]}...\")"
        )

    # Approve all extracted rules before using them
    approve_res = client.post(f"/guidelines/{guideline_id}/approve-all?approved=1")
    assert approve_res.status_code == 200
    print(f"  - Approved {approve_res.json()['updated_rules']} rules for active checking.")

    # 2. Test Content Checking (Banned words, Missing required phrases, Tone, Claims)
    bad_copy = (
        "STOP PAYING HIGH PRICES!! Our cheap cloud platform is a total no-brainer "
        "that gives you 100% guaranteed instant results overnight!"
    )
    check_res = client.post(
        "/check-content",
        json={
            "guideline_id": guideline_id,
            "content_title": "Q4 Social Media Ad Draft",
            "text": bad_copy,
            "only_approved_rules": True,
        },
    )
    assert check_res.status_code == 200, f"Check failed: {check_res.text}"
    check_data = check_res.json()

    print(f"\n[2. Better Content Checking]")
    print(f"  - Status & Score          : {check_data['status']} ({check_data['overall_score']}/100)")
    print(f"  - Total Violations Found  : {len(check_data['issues'])}")
    for idx, issue in enumerate(check_data["issues"], start=1):
        print(
            f"    {idx}. [{issue['severity'].upper()}] {issue['title']} "
            f"(Page {issue['page_number']}) -> Fix: {issue['suggested_replacement']}"
        )

    # 3. Test Accuracy Benchmark & Downloadable Reports
    bench_res = client.post("/benchmark/run", json={"guideline_id": guideline_id})
    assert bench_res.status_code == 200
    bench_data = bench_res.json()

    print(f"\n[3. Testing & Reports]")
    print(f"  - Samples Tested          : {bench_data['total_samples']}")
    print(f"  - Detection Accuracy      : {bench_data['accuracy']}%")
    print(f"  - Precision / Recall / F1 : {bench_data['precision_score']}% / {bench_data['recall_score']}% / {bench_data['f1_score']}%")

    # Download Markdown Report
    check_id = check_data["id"]
    report_res = client.get(f"/reports/{check_id}/download?format=md")
    assert report_res.status_code == 200
    with open("sample_round3_report.md", "w", encoding="utf-8") as f:
        f.write(report_res.text)
    print(f"  - Saved downloadable report to backend/sample_round3_report.md")
    print("\nALL ROUND 3 CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_round3_verification()