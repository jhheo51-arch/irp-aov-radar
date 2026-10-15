"""분류된 리뷰를 회사 × 여정 단계 × 불편 유형으로 집계한다 (Tableau 히트맵 원본).

입력: data/processed/review_labels.csv
출력: data/processed/review_heatmap.csv
'연금 무관'과 '불편 없음(칭찬·중립)'은 불편 집계에서 제외하고 건수만 따로 보고한다.
"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "review_labels.csv"
OUT = ROOT / "data" / "processed" / "review_heatmap.csv"

EXCLUDED_STAGE = "연금 무관"
NO_PAIN = "불편 없음(칭찬·중립)"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with SRC.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    relevant = [r for r in rows if r["journey_stage"] != EXCLUDED_STAGE]
    pains = [r for r in relevant if r["pain_type"] != NO_PAIN]
    print(f"전체 {len(rows)} / 연금 여정 관련 {len(relevant)} / 불편 리뷰 {len(pains)}")

    per_company = Counter(r["company"] for r in pains)
    cells = Counter((r["company"], r["journey_stage"], r["pain_type"]) for r in pains)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "journey_stage", "pain_type", "reviews", "share_of_company_pain"])
        for (company, stage, pain), n in sorted(cells.items()):
            writer.writerow([company, stage, pain, n, round(n / per_company[company], 4)])
    print(f"저장: {OUT}")

    for company in sorted(per_company):
        subset = [r for r in pains if r["company"] == company]
        stages = Counter(r["journey_stage"] for r in subset).most_common(3)
        kinds = Counter(r["pain_type"] for r in subset).most_common(3)
        print(f"\n[{company}] 불편 리뷰 {len(subset)}건")
        print("  단계 상위:", ", ".join(f"{k} {v}건({v / len(subset):.0%})" for k, v in stages))
        print("  유형 상위:", ", ".join(f"{k} {v}건({v / len(subset):.0%})" for k, v in kinds))

    requests = Counter(r["feature_request"] for r in pains if r["company"] == "한국투자증권" and r["feature_request"])
    print("\n[한국투자증권] 개선 요청:", ", ".join(f"{k}({v})" for k, v in requests.most_common(10)))


if __name__ == "__main__":
    main()
