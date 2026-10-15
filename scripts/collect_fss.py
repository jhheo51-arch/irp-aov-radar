"""금감원 통합연금포털 '연금통계 > 퇴직연금' 사업자별 상세표를 수집한다.

화면의 '상세보기' 버튼이 호출하는 공개 엔드포인트(listCont.do)를 그대로 사용한다.
로그인이나 개인정보가 필요 없는 공개 통계만 다룬다.

출력: data/raw/fss/fss_retirement_by_provider.csv (long format)
  measure, plan, item, sector, provider, year, value, unit
"""
import csv
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.fss.or.kr/fss/lifeplan/statsRtrmSvings/listCont.do"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "fss" / "fss_retirement_by_provider.csv"

# (unitId, penId) -> (measure, plan, item, unit)
# 화면 버튼의 modalDetail(4, unitId, penId) 값과 표 제목을 대조해 정했다.
TARGETS = {
    (1, 14): ("적립금", "DB", "합계", "억원"),
    (1, 15): ("적립금", "DC", "합계", "억원"),
    (1, 16): ("적립금", "IRP", "합계", "억원"),
    (3, 14): ("계약건수", "DB", "합계", "건"),
    (3, 15): ("계약건수", "DC", "합계", "건"),
    (3, 16): ("계약건수", "IRP", "합계", "건"),
    (5, 26): ("수수료", "IRP", "소계", "백만원"),
    (5, 27): ("수수료", "IRP", "운용관리", "백만원"),
    (5, 28): ("수수료", "IRP", "자산관리", "백만원"),
    (5, 29): ("수수료", "IRP", "펀드총비용", "백만원"),
}


class TableParser(HTMLParser):
    """페이지 안의 모든 <table>을 행 목록으로 모은다."""

    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._in_cell = False
        elif tag == "tr" and self._row and self.tables:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def fetch(unit_id, pen_id):
    body = urllib.parse.urlencode({"statsId": 4, "unitId": unit_id, "penId": pen_id}).encode()
    req = urllib.request.Request(URL, data=body, headers={"User-Agent": "Mozilla/5.0 (irp-aov-radar research)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8", errors="replace")


def to_number(text):
    text = text.replace(",", "").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse(html):
    parser = TableParser()
    parser.feed(html)
    for table in parser.tables:
        if not table or not table[0][0].startswith("금융회사"):
            continue
        header = table[0]
        sector = re.search(r"\((.+)\)", header[0]).group(1)
        years = [int("20" + re.search(r"'(\d{2})", h).group(1)) for h in header[1:] if re.search(r"'(\d{2})", h)]
        for row in table[1:]:
            provider = row[0]
            if provider == "합계":  # 업권별 합계 행은 사업자 행과 중복되므로 버린다
                continue
            for year, cell in zip(years, row[1:1 + len(years)]):
                yield sector, provider, year, to_number(cell)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for (unit_id, pen_id), (measure, plan, item, unit) in TARGETS.items():
        found = list(parse(fetch(unit_id, pen_id)))
        if not found:
            raise RuntimeError(f"표를 찾지 못했습니다: unitId={unit_id}, penId={pen_id}")
        rows += [(measure, plan, item, s, p, y, v, unit) for s, p, y, v in found]
        print(f"{measure}/{plan}/{item}: {len(found)}행")
        time.sleep(1)  # 공공 사이트에 부담을 주지 않도록 요청 간격을 둔다
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["measure", "plan", "item", "sector", "provider", "year", "value", "unit"])
        writer.writerows(rows)
    print(f"저장: {OUT} ({len(rows)}행)")


if __name__ == "__main__":
    main()
