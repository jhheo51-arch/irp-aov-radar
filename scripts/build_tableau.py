"""Tableau Public 대시보드용 데이터 4종을 만든다 (공개 가능한 집계값만).

출력: data/tableau/
  t1_aov_trend.csv       화면 1 객단가 격차: 증권사 IRP 계약 수·적립금·계약 1건당 적립금 (2017~2025)
  t2_heatmap.csv         화면 2 불편 히트맵: 회사 × 여정 단계 × 불편 유형 (정렬용 순서 열 포함)
  t3_opportunities.csv   화면 3 객단가를 올릴 기회: 여정 단계를 커머스 방식에 대응시킨 집계
  t4_quality.csv         화면 4 데이터·AI 관리 패널: 검증 지표
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "data" / "tableau"
FOCUS = ["한국투자증권", "미래에셋증권", "삼성증권"]
MIN_CONTRACTS = 50_000

STAGE_ORDER = ["가입·계좌개설", "첫 납입·입금", "정기 납입·자동투자", "상품 선택·운용", "수익률·잔고 조회",
               "타사 연금 이전", "세액공제·서류", "인출·해지·수령", "연금 일반(단계 불명)"]
PAIN_ORDER = ["오류·장애", "화면·사용성", "기능 부재", "정보 부족", "절차·서류·대면 요구", "수수료·비용", "상품·수익"]
# 히트맵 열 머리글이 잘리지 않도록 쓰는 짧은 이름
PAIN_SHORT = {"오류·장애": "오류", "화면·사용성": "화면", "기능 부재": "기능", "정보 부족": "안내",
              "절차·서류·대면 요구": "절차", "수수료·비용": "비용", "상품·수익": "상품"}

# 여정 단계 -> (커머스 방식, 객단가와의 관계)
LEVERS = {
    "가입·계좌개설": ("결제 이탈 방지", "첫 계좌를 여는 순간의 마찰"),
    "첫 납입·입금": ("첫 구매 전환", "개설 후 첫 돈이 들어오는가"),
    "정기 납입·자동투자": ("정기배송", "매달 자동으로 쌓이는가"),
    "상품 선택·운용": ("상품 큐레이션", "넣은 돈을 굴릴 상품을 쉽게 고르는가"),
    "수익률·잔고 조회": ("마이페이지·재방문", "내 계좌가 커지는 것이 보이는가"),
    "타사 연금 이전": ("장바구니 합치기", "다른 곳의 연금을 한곳으로 모으는가"),
    "세액공제·서류": ("증빙 셀프서비스", "연말에 다시 찾아올 이유"),
    "인출·해지·수령": ("해지 방어", "돈이 빠져나가는 순간"),
}


def read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(name, fields, rows):
    # BOM 없이 저장한다. Tableau 텍스트 커넥터가 첫 열 이름에 BOM을 붙여 읽는 것을 막기 위해서다.
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{name}: {len(rows)}행")


def build_aov():
    rows = [r for r in read(PROC / "irp_aov_by_provider.csv") if r["plan"] == "IRP" and r["reserve_per_contract_krw"]]
    market = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        market[r["year"]][0] += float(r["reserve_100m_krw"])
        market[r["year"]][1] += float(r["contracts"])
    out = []
    for r in rows:
        if r["sector"] != "증권":
            continue
        reserve, contracts = market[r["year"]]
        out.append({
            "provider": r["provider"], "year": r["year"],
            "contracts": int(float(r["contracts"])), "reserve_100m_krw": float(r["reserve_100m_krw"]),
            "reserve_per_contract_10k_krw": round(float(r["reserve_per_contract_krw"]) / 10_000),
            "market_avg_per_contract_10k_krw": round(reserve * 100_000_000 / contracts / 10_000),
            "highlight": r["provider"] if r["provider"] in FOCUS else "기타 증권사",
            "kis_flag": 1 if r["provider"] == "한국투자증권" else 0,  # 색 강조용 (한국투자증권만 진하게)
        })
    # 계약 수가 아주 적은 소형사는 1건당 적립금이 튀어 축을 왜곡하므로 2025년 5만 건 이상인 회사만 남긴다
    major = {r["provider"] for r in out if r["year"] == "2025" and r["contracts"] >= MIN_CONTRACTS}
    out = [r for r in out if r["provider"] in major]
    write("t1_aov_trend.csv", list(out[0]), out)


def build_heatmap():
    out = []
    for r in read(PROC / "review_heatmap.csv"):
        if r["journey_stage"] not in STAGE_ORDER:
            continue
        stage_no, pain_no = STAGE_ORDER.index(r["journey_stage"]) + 1, PAIN_ORDER.index(r["pain_type"]) + 1
        # 번호를 붙인 라벨은 Tableau에서 별도 정렬 설정 없이 여정·불편 순서대로 놓이게 한다
        out.append({**r, "stage_order": stage_no, "pain_order": pain_no,
                    "stage_label": f"{stage_no}. {r['journey_stage']}", "pain_label": f"{pain_no} {PAIN_SHORT[r['pain_type']]}"})
    write("t2_heatmap.csv", list(out[0]), out)


def build_opportunities(labels):
    pains = [r for r in labels if r["journey_stage"] in LEVERS and r["pain_type"] != "불편 없음(칭찬·중립)"]
    total = len(pains)
    out = []
    for stage, (lever, meaning) in LEVERS.items():
        subset = [r for r in pains if r["journey_stage"] == stage]
        kis = sum(r["company"] == "한국투자증권" for r in subset)
        requests = Counter(r["feature_request"] for r in subset if r["feature_request"]).most_common(3)
        top_pain = Counter(r["pain_type"] for r in subset).most_common(1)
        out.append({
            "journey_stage": stage, "stage_order": STAGE_ORDER.index(stage) + 1,
            "commerce_lever": lever, "meaning": meaning,
            "pain_reviews_3co": len(subset), "share_3co": round(len(subset) / total, 4) if total else 0,
            "pain_reviews_kis": kis, "top_pain_type": top_pain[0][0] if top_pain else "",
            "share_label": f"{len(subset) / total:.0%}" if total else "0%",
            "example_requests": " / ".join(k for k, _ in requests),
        })
    for rank, row in enumerate(sorted(out, key=lambda r: -r["pain_reviews_3co"]), 1):
        row["lever_label"] = f"{rank}. {row['commerce_lever']}"  # 불편 많은 순으로 놓이게 하는 라벨
    write("t3_opportunities.csv", list(out[0]), out)


def build_quality(labels):
    pains = [r for r in labels if r["journey_stage"] != "연금 무관" and r["pain_type"] != "불편 없음(칭찬·중립)"]
    out = [
        {"area": "공시 데이터", "metric": "공식 합계 대조 오차", "value": "0.25%", "note": "IRP·DC 적립금과 계약 수, 2025년 말 기준"},
        {"area": "공시 데이터", "metric": "기준일", "value": "2025년 말", "note": "금감원 통합연금포털 연금통계"},
        {"area": "공시 데이터", "metric": "표기 원칙", "value": "계약 1건당", "note": "계약 수는 계좌 수이므로 '1인당'으로 쓰지 않음"},
        {"area": "리뷰 데이터", "metric": "수집 / 연금 리뷰", "value": "33,667 / 349", "note": "구글 플레이 공개 리뷰, 작성자 정보 미수집"},
        {"area": "리뷰 데이터", "metric": "분석한 불편 리뷰", "value": str(len(pains)), "note": "연금 무관·칭찬 제외"},
        {"area": "리뷰 데이터", "metric": "한투 불편 리뷰", "value": str(sum(r['company'] == '한국투자증권' for r in pains)), "note": "표본이 작아 3사 비교의 보조 지표로만 사용"},
        {"area": "AI 분류", "metric": "검수 일치율(단계/유형)", "value": "96% / 100%", "note": "무작위 50건, 별도 AI 검수자"},
        {"area": "AI 분류", "metric": "프롬프트 버전", "value": "v1", "note": "결과 파일에 모델·버전 기록"},
        {"area": "보안·개인정보", "metric": "공개 범위", "value": "집계값만", "note": "리뷰 원문·근거 인용은 GitHub와 Tableau Public에 올리지 않음"},
        {"area": "보안·개인정보", "metric": "개인정보 리뷰", "value": "1건 제외", "note": "앱 리뷰가 아닌 개인 글"},
        {"area": "보안·개인정보", "metric": "내부 도입 전제", "value": "내부망 배치", "note": "고객 계좌 데이터 결합 시 개인신용정보 → 망분리 예외 범위 확인 필요"},
    ]
    areas = list(dict.fromkeys(r["area"] for r in out))
    for i, r in enumerate(out, 1):
        r["area"] = f"{areas.index(r['area']) + 1}. {r['area']}"  # 영역 순서 고정
        r["metric"] = f"{i:02d} {r['metric']}"  # 항목 순서 고정
        r["blank"] = ""  # 값은 행 머리글로 보여 주고(너비 자동), 텍스트 마크는 비워 둔다
    write("t4_quality.csv", list(out[0]), out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    labels = read(PROC / "review_labels.csv")
    build_aov()
    build_heatmap()
    build_opportunities(labels)
    build_quality(labels)


if __name__ == "__main__":
    main()
