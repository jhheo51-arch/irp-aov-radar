"""사업자별 IRP '객단가'(계약 1건당 적립금)를 계산하고 공식 합계와 대조한다.

입력: data/raw/fss/fss_retirement_by_provider.csv
출력: data/processed/irp_aov_by_provider.csv  (Tableau 원본)

객단가 = 적립금(억원) * 1억 / 계약건수  -> 원 단위
계약건수는 '계좌 수'에 가깝고 '사람 수'가 아니다. 한 사람이 여러 금융사에
IRP를 가질 수 있으므로 화면과 문서에는 '계약 1건당 적립금'으로 표기한다.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "fss" / "fss_retirement_by_provider.csv"
OUT = ROOT / "data" / "processed" / "irp_aov_by_provider.csv"

# 금감원 연금통계 메인 화면에 표시된 2025년 말 시장 합계 (수집 결과 검증용)
OFFICIAL_2025 = {
    ("적립금", "IRP"): 130.9 * 10_000,      # 조원 -> 억원
    ("계약건수", "IRP"): 704.4 * 10_000,    # 만건 -> 건
    ("적립금", "DC"): 141.6 * 10_000,
    ("계약건수", "DC"): 49.9 * 10_000,
}
TOLERANCE = 0.01  # 반올림 차이를 고려해 1%까지 허용


def load():
    with RAW.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def validate(rows):
    totals = defaultdict(float)
    for r in rows:
        if r["year"] == "2025" and r["item"] == "합계" and r["value"]:
            totals[(r["measure"], r["plan"])] += float(r["value"])
    ok = True
    for key, official in OFFICIAL_2025.items():
        gap = abs(totals[key] - official) / official
        status = "OK" if gap <= TOLERANCE else "불일치"
        ok &= gap <= TOLERANCE
        print(f"[검증] {key[0]}/{key[1]} 2025: 수집 {totals[key]:,.0f} / 공식 {official:,.0f} ({gap:.2%}) {status}")
    return ok


def build(rows):
    table = defaultdict(dict)
    for r in rows:
        if r["item"] == "합계" and r["value"]:
            table[(r["plan"], r["sector"], r["provider"], int(r["year"]))][r["measure"]] = float(r["value"])
    out = []
    for (plan, sector, provider, year), m in sorted(table.items()):
        reserve, contracts = m.get("적립금"), m.get("계약건수")
        aov = reserve * 100_000_000 / contracts if reserve and contracts else None
        out.append({
            "plan": plan, "sector": sector, "provider": provider, "year": year,
            "reserve_100m_krw": reserve, "contracts": contracts,
            "reserve_per_contract_krw": round(aov) if aov else None,
        })
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = load()
    if not validate(rows):
        raise SystemExit("공식 합계와 맞지 않아 중단합니다. 수집 대상(penId) 매핑을 확인하세요.")
    out = build(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"저장: {OUT} ({len(out)}행)")

    top = [r for r in out if r["plan"] == "IRP" and r["sector"] == "증권" and r["year"] == 2025 and r["contracts"]]
    print("\n[2025 증권사 IRP] 계약건수 상위 6")
    for r in sorted(top, key=lambda r: -r["contracts"])[:6]:
        print(f"  {r['provider']:<8} 계약 {r['contracts']:>9,.0f}  적립금 {r['reserve_100m_krw']:>9,.0f}억  1건당 {r['reserve_per_contract_krw'] / 10_000:>6,.0f}만원")


if __name__ == "__main__":
    main()
