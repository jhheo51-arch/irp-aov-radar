"""증권 3사 앱의 구글 플레이 리뷰를 수집하고 연금 관련 리뷰를 걸러낸다.

개인정보 보호:
- 작성자 이름, 프로필 이미지, 리뷰 ID는 저장하지 않는다.
- 원문 리뷰(data/raw/reviews)는 .gitignore로 GitHub에 올리지 않는다.
- 공개 산출물에는 분류 결과와 집계만 남긴다.

출력:
  data/raw/reviews/reviews_all.csv      전체 리뷰(비공개)
  data/raw/reviews/reviews_pension.csv  연금 키워드 리뷰(비공개, 분류 입력)
"""
import csv
import re
import sys
import time
from pathlib import Path

from google_play_scraper import Sort, reviews

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "reviews"

APPS = {
    "한국투자증권": ["com.truefriend.neosmartarenewal", "com.truefriend.smartnewa"],
    "미래에셋증권": ["com.miraeasset.trade"],
    "삼성증권": ["com.samsungpop.android.mpop"],
}
MAX_PER_APP = 30_000

# 연금 여정과 직접 관련된 표현만 고른다. 'DC'처럼 짧은 영문은 단어 경계로 제한한다.
PENSION = re.compile(r"연금|IRP|아이알피|퇴직|세액\s*공제|연말\s*정산|디폴트\s*옵션|실물\s*이전|\bDC\b|\bDB\b", re.IGNORECASE)


def fetch(app_id):
    rows, token = [], None
    while len(rows) < MAX_PER_APP:
        batch, token = reviews(app_id, lang="ko", country="kr", sort=Sort.NEWEST, count=200, continuation_token=token)
        rows += batch
        if not token or not batch:
            break
        time.sleep(0.5)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["company", "app_id", "date", "score", "thumbs_up", "app_version", "content"]
    all_rows = []
    for company, app_ids in APPS.items():
        for app_id in app_ids:
            try:
                fetched = fetch(app_id)
            except Exception as error:  # 앱 ID가 바뀌었거나 스토어 응답이 없을 때
                print(f"{company} {app_id}: 수집 실패 ({error})")
                continue
            for r in fetched:
                all_rows.append({
                    "company": company, "app_id": app_id, "date": r["at"].date().isoformat(),
                    "score": r["score"], "thumbs_up": r["thumbsUpCount"],
                    "app_version": r.get("reviewCreatedVersion") or "",
                    "content": (r["content"] or "").replace("\n", " ").strip(),
                })
            print(f"{company} {app_id}: {len(fetched):,}건")

    pension = [r for r in all_rows if PENSION.search(r["content"])]
    for name, rows in (("reviews_all.csv", all_rows), ("reviews_pension.csv", pension)):
        with (OUT_DIR / name).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\n전체 {len(all_rows):,}건 / 연금 관련 {len(pension):,}건")
    for company in APPS:
        n_all = sum(r["company"] == company for r in all_rows)
        n_pen = sum(r["company"] == company for r in pension)
        print(f"  {company}: 전체 {n_all:,} / 연금 {n_pen:,}")


if __name__ == "__main__":
    main()
