"""격차는 언제 벌어졌나: 증권사 IRP 연도별 추이를 계산한다.

입력: data/processed/irp_aov_by_provider.csv
출력: data/processed/irp_trend.csv

지표
- 계약 1건당 적립금, 전 업권 평균 대비 배율
- 증권업권 안에서의 계약 점유율과 적립금 점유율
- 순증 1건당 적립금 = (올해 적립금 - 작년 적립금) / (올해 계약 수 - 작년 계약 수)
  새로 늘어난 계좌의 크기를 가늠하는 추정치다. 기존 계좌의 운용수익, 추가 납입, 해지가 함께 섞이므로
  실제 신규 계좌의 평균과 같지 않다. 회사 간 같은 방식으로 비교하는 용도로만 쓴다.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "irp_aov_by_provider.csv"
OUT = ROOT / "data" / "processed" / "irp_trend.csv"
FOCUS = ["한국투자증권", "미래에셋증권", "삼성증권"]


def man_won(reserve_100m, contracts):
    """억 원과 건수로 1건당 만 원을 계산한다."""
    return reserve_100m * 100_000_000 / contracts / 10_000


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with SRC.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["plan"] == "IRP" and r["contracts"] and r["reserve_100m_krw"]]

    market = defaultdict(lambda: [0.0, 0.0])
    securities = defaultdict(lambda: [0.0, 0.0])
    data = defaultdict(dict)
    for r in rows:
        year, contracts, reserve = int(r["year"]), float(r["contracts"]), float(r["reserve_100m_krw"])
        market[year][0] += contracts
        market[year][1] += reserve
        if r["sector"] == "증권":
            securities[year][0] += contracts
            securities[year][1] += reserve
            data[r["provider"]][year] = (contracts, reserve)

    out = []
    for provider in FOCUS:
        previous = None
        for year in sorted(data[provider]):
            contracts, reserve = data[provider][year]
            per = man_won(reserve, contracts)
            market_per = man_won(market[year][1], market[year][0])
            row = {
                "provider": provider, "year": year, "contracts": int(contracts), "reserve_100m_krw": reserve,
                "per_contract_10k_krw": round(per), "market_per_contract_10k_krw": round(market_per),
                "vs_market": round(per / market_per, 3),
                "contract_share_in_securities": round(contracts / securities[year][0], 4),
                "reserve_share_in_securities": round(reserve / securities[year][1], 4),
                "net_new_contracts": "", "net_new_reserve_100m_krw": "", "net_new_per_contract_10k_krw": "",
            }
            if previous:
                new_contracts, new_reserve = contracts - previous[0], reserve - previous[1]
                row["net_new_contracts"] = int(new_contracts)
                row["net_new_reserve_100m_krw"] = new_reserve
                if new_contracts > 0:
                    row["net_new_per_contract_10k_krw"] = round(man_won(new_reserve, new_contracts))
            out.append(row)
            previous = (contracts, reserve)

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"저장: {OUT} ({len(out)}행)\n")

    by = {(r["provider"], r["year"]): r for r in out}
    print("계약 1건당 적립금(만 원)과 전 업권 평균 대비 배율")
    for year in (2017, 2020, 2021, 2025):
        cells = "  ".join(f"{p[:2]} {by[(p, year)]['per_contract_10k_krw']:>5,}({by[(p, year)]['vs_market']:.2f}배)" for p in FOCUS)
        print(f"  {year}: {cells}")
    print("\n순증 1건당 적립금(만 원, 추정) 2023~2025 평균")
    for p in FOCUS:
        values = [by[(p, y)]["net_new_per_contract_10k_krw"] for y in (2023, 2024, 2025)]
        print(f"  {p}: {sum(values) / len(values):,.0f}  ({' / '.join(f'{v:,}' for v in values)})")


if __name__ == "__main__":
    main()
