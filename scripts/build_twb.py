"""data/tableau/의 CSV 4개로 Tableau 통합문서(.twb)를 만든다.

출력: data/tableau/irp_aov_radar.twb
시트 4개와 대시보드(배치, 제목, 한글 필드명, 색, 레이블)가 들어 있다.
이미지 내보내기와 Tableau Public 저장만 Tableau에서 직접 한다(docs/tableau-build-guide.md).
"""
import csv
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tableau"
OUT = DATA / "irp_aov_radar.twb"

DASHBOARD = "IRP 객단가 레이더"
KIS_ORANGE = "#E8541F"

# 원본 이름 -> (CSV 파일, 차원으로 둘 숫자 열)
SOURCES = {
    "t1": ("t1_aov_trend.csv", {"year"}),
    "t2": ("t2_heatmap.csv", {"stage_order", "pain_order"}),
    "t3": ("t3_opportunities.csv", {"stage_order"}),
    "t4": ("t4_quality.csv", set()),
}

# 화면에 보일 한글 필드명 (축 제목, 머리글, 도구 설명에 쓰인다)
CAPTIONS = {
    "provider": "증권사", "year": "연도", "contracts": "IRP 계약 수(건)", "reserve_100m_krw": "적립금(억 원)",
    "reserve_per_contract_10k_krw": "계약 1건당 적립금(만 원)", "market_avg_per_contract_10k_krw": "전 업권 평균(만 원)",
    "highlight": "구분", "kis_flag": "한국투자증권", "company": "증권사", "stage_label": "여정 단계", "pain_label": "불편 유형",
    "reviews": "불편 리뷰(건)", "lever_label": "커머스 방식", "pain_reviews_3co": "3사 불편 리뷰(건)",
    "share_label": "비중", "meaning": "의미", "example_requests": "고객 요청 예", "top_pain_type": "가장 많은 불편",
    "pain_reviews_kis": "한국투자증권(건)", "area": "영역", "metric": "항목", "value": "값", "note": "설명", "blank": " ",
}

# 시트 정의: 열/행 선반, 마크, 인코딩, 필터, 색.  필드 표기: (집계, 원본 열)  집계 none = 차원
SHEETS = [
    {
        "name": "1 객단가 격차", "source": "t1", "mark": "Circle",
        "cols": [("sum", "contracts")], "rows": [("sum", "reserve_per_contract_10k_krw")],
        # 범주형 색 지정은 Tableau가 적용하지 않아, 한국투자증권만 1인 측정값을 순차 색상으로 칠한다
        "color": ("sum", "kis_flag"), "size": ("sum", "reserve_100m_krw"), "text": ("none", "provider"),
        "filter": ("year", "2025"), "sequential": "orange_10_0",
    },
    {
        "name": "2 불편 히트맵", "source": "t2", "mark": "Square",
        "cols": [("none", "pain_label")], "rows": [("none", "stage_label")],
        "color": ("sum", "reviews"), "text": ("sum", "reviews"), "sequential": "orange_10_0",
    },
    {
        "name": "3 기회", "source": "t3", "mark": "Bar",
        "cols": [("sum", "pain_reviews_3co")], "rows": [("none", "lever_label")],
        "color": ("sum", "pain_reviews_3co"), "text": ("none", "share_label"), "sequential": "orange_10_0",
        "lod": [("none", "meaning"), ("none", "example_requests"), ("none", "top_pain_type"), ("sum", "pain_reviews_kis")],
    },
    {
        "name": "4 관리", "source": "t4", "mark": "Text",
        "rows": [("none", "area"), ("none", "metric"), ("none", "value")], "cols": [],
        "text": ("none", "blank"), "lod": [("none", "note")],
    },
]


def infer_type(values):
    def ok(cast):
        try:
            for v in values:
                if v != "":
                    cast(v)
            return True
        except ValueError:
            return False
    if not any(values):  # 값이 모두 비어 있으면 문자열로 본다 (빈 텍스트 열)
        return "string"
    if ok(int):
        return "integer"
    if ok(float):
        return "real"
    return "string"


def schema(filename):
    with (DATA / filename).open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    return [(name, infer_type([r[i] for r in body])) for i, name in enumerate(header)]


def ds_name(key):
    return f"federated.irp_{key}"


def instance(agg, col, dims):
    """Tableau 열 인스턴스 이름. 차원은 none, 측정값은 sum."""
    if agg == "none":
        kind = "ok" if col in dims else "nk"
        return f"[none:{col}:{kind}]"
    return f"[{agg}:{col}:qk]"


def column_xml(name, dtype, dims, indent):
    if dtype == "string" or name in dims:
        role, typ = "dimension", ("ordinal" if name in dims else "nominal")
    else:
        role, typ = "measure", "quantitative"
    caption = quoteattr(CAPTIONS.get(name, name))
    return f"{indent}<column caption={caption} datatype='{dtype}' name='[{name}]' role='{role}' type='{typ}' />"


def datasource_xml(key):
    filename, dims = SOURCES[key]
    cols = schema(filename)
    table = filename.replace(".csv", "#csv")
    parts = [f"    <datasource caption={quoteattr(filename[:-4])} inline='true' name='{ds_name(key)}' version='18.1'>",
             "      <connection class='federated'>",
             "        <named-connections>",
             f"          <named-connection caption={quoteattr(filename[:-4])} name='textscan.irp_{key}'>",
             f"            <connection class='textscan' directory={quoteattr(DATA.as_posix())} filename={quoteattr(filename)} password='' server='' />",
             "          </named-connection>",
             "        </named-connections>",
             f"        <relation connection='textscan.irp_{key}' name={quoteattr(filename)} table='[{table}]' type='table'>",
             "          <columns character-set='UTF-8' header='yes' locale='ko_KR' separator=','>"]
    for i, (name, dtype) in enumerate(cols):
        parts.append(f"            <column datatype='{dtype}' name={quoteattr(name)} ordinal='{i}' />")
    parts += ["          </columns>", "        </relation>", "      </connection>"]
    parts += [column_xml(name, dtype, dims, "      ") for name, dtype in cols]
    parts.append("    </datasource>")
    return "\n".join(parts), dict(cols)


def shelf(tag, refs):
    """선반 XML. 필드가 여러 개면 Tableau 형식대로 괄호로 묶고 ' / '로 중첩한다."""
    if not refs:
        return f"<{tag} />"
    body = refs[0] if len(refs) == 1 else "(" + " / ".join(refs) + ")"
    return f"<{tag}>{body}</{tag}>"


def color_style(sheet, ref):
    """색 지정: 범주형은 회사별 색, 연속형은 순차 색상."""
    if "palette" in sheet:
        maps = "\n".join(f"              <map to='{hex_}'>\n                <bucket>&quot;{escape(name)}&quot;</bucket>\n              </map>"
                         for name, hex_ in sheet["palette"].items())
        return ("<style>\n          <style-rule element='mark'>\n"
                f"            <encoding attr='color' field='{ref(sheet['color'])}' type='palette'>\n{maps}\n"
                "            </encoding>\n          </style-rule>\n        </style>")
    if "sequential" in sheet:
        return ("<style>\n          <style-rule element='mark'>\n"
                f"            <encoding attr='color' field='{ref(sheet['color'])}' palette='{sheet['sequential']}' type='interpolated' />\n"
                "          </style-rule>\n        </style>")
    return "<style />"


def worksheet_xml(sheet, types):
    key = sheet["source"]
    ds = ds_name(key)
    dims = SOURCES[key][1]
    used = list(sheet.get("cols", [])) + list(sheet.get("rows", []))
    for enc in ("color", "size", "text"):
        if enc in sheet:
            used.append(sheet[enc])
    used += sheet.get("lod", [])
    if "filter" in sheet:
        used.append(("none", sheet["filter"][0]))

    deps = []
    seen_cols, seen_inst = set(), set()
    for agg, col in used:
        if col not in seen_cols:
            seen_cols.add(col)
            deps.append(column_xml(col, types[col], dims, "            "))
        inst = instance(agg, col, dims)
        if inst not in seen_inst:
            seen_inst.add(inst)
            derivation = "None" if agg == "none" else "Sum"
            typ = ("ordinal" if col in dims else "nominal") if agg == "none" else "quantitative"
            deps.append(f"            <column-instance column='[{col}]' derivation='{derivation}' name='{inst}' pivot='key' type='{typ}' />")

    ref = lambda field: f"[{ds}].{instance(field[0], field[1], dims)}"
    filter_xml = ""
    if "filter" in sheet:
        col, member = sheet["filter"]
        inst = instance("none", col, dims)
        filter_xml = (f"          <filter class='categorical' column='[{ds}].{inst}'>\n"
                      f"            <groupfilter function='member' level='{inst}' member='{member}' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />\n"
                      f"          </filter>\n"
                      f"          <slices>\n            <column>[{ds}].{inst}</column>\n          </slices>\n")
    encodings = [f"              <{enc} column='{ref(sheet[enc])}' />" for enc in ("color", "size", "text") if enc in sheet]
    encodings += [f"              <lod column='{ref(field)}' />" for field in sheet.get("lod", [])]

    return f"""    <worksheet name={quoteattr(sheet['name'])}>
      <table>
        <view>
          <datasources>
            <datasource name='{ds}' />
          </datasources>
          <datasource-dependencies datasource='{ds}'>
{chr(10).join(deps)}
          </datasource-dependencies>
{filter_xml}          <aggregation value='true' />
        </view>
        {color_style(sheet, ref)}
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{sheet['mark']}' />
            <encodings>
{chr(10).join(encodings)}
            </encodings>
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='true' />
                <format attr='mark-labels-cull' value='false' />
              </style-rule>
            </style>
          </pane>
        </panes>
        {shelf('rows', [ref(f) for f in sheet.get('rows', [])])}
        {shelf('cols', [ref(f) for f in sheet.get('cols', [])])}
      </table>
    </worksheet>"""


def text_zone(zone_id, x, y, w, h, text, size, bold=False):
    weight = " bold='true'" if bold else ""
    return (f"        <zone h='{h}' id='{zone_id}' type-v2='text' w='{w}' x='{x}' y='{y}'>\n"
            f"          <formatted-text>\n            <run fontsize='{size}'{weight}>{escape(text)}</run>\n          </formatted-text>\n"
            f"        </zone>")


def dashboard_xml():
    """1200 x 1000 고정 크기. 좌표는 Tableau 대시보드 단위(전체 = 100000)."""
    subtitle = ("한국투자증권은 IRP 계약 수 1위(47.3만 건)지만 계약 1건당 적립금은 1,572만 원으로 "
                "미래에셋증권(3,736만 원)의 42%, 전 업권 평균(1,858만 원)보다 낮습니다. "
                "증권 3사 연금 리뷰의 불편 59%는 가입 이후 단계에 몰려 있습니다.")
    footer = ("출처: 금융감독원 통합연금포털 연금통계(2025년 말), 구글 플레이 공개 리뷰(증권 3사 연금 관련 349건). "
              "화면 1은 IRP 계약 5만 건 이상 증권사(주황: 한국투자증권), 화면 2·3은 3사 합계입니다. "
              "리뷰 원문은 공개하지 않으며, 투자 권유가 아닌 서비스 기획 분석입니다.")
    grid = [(SHEETS[0]["name"], 0, 11000), (SHEETS[1]["name"], 50000, 11000),
            (SHEETS[2]["name"], 0, 53000), (SHEETS[3]["name"], 50000, 53000)]
    zones = [text_zone(2, 0, 0, 100000, 5000, DASHBOARD, 20, bold=True),
             text_zone(3, 0, 5000, 100000, 6000, subtitle, 11)]
    for i, (name, x, y) in enumerate(grid, start=4):
        zones.append(f"        <zone h='42000' id='{i}' name={quoteattr(name)} w='50000' x='{x}' y='{y}' />")
    zones.append(text_zone(8, 0, 95000, 100000, 5000, footer, 9))
    return f"""  <dashboards>
    <dashboard name={quoteattr(DASHBOARD)}>
      <style />
      <size maxheight='1000' maxwidth='1200' minheight='1000' minwidth='1200' />
      <zones>
      <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
{chr(10).join(zones)}
      </zone>
      </zones>
    </dashboard>
  </dashboards>"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sources, types = [], {}
    for key in SOURCES:
        xml, cols = datasource_xml(key)
        sources.append(xml)
        types[key] = cols
    sheets = [worksheet_xml(s, types[s["source"]]) for s in SHEETS]
    windows = "\n".join(
        f"    <window class='worksheet' name={quoteattr(s['name'])}>\n      <cards>\n        <edge name='left'>\n          <strip size='160'>\n            <card type='pages' />\n            <card type='filters' />\n            <card type='marks' />\n          </strip>\n        </edge>\n      </cards>\n    </window>"
        for s in SHEETS)
    viewpoints = "\n".join(f"        <viewpoint name={quoteattr(s['name'])} />" for s in SHEETS)
    workbook = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2023.1.0 (20231.23.0310.1045)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{chr(10).join(sources)}
  </datasources>
  <worksheets>
{chr(10).join(sheets)}
  </worksheets>
{dashboard_xml()}
  <windows source-height='30'>
{windows}
    <window class='dashboard' maximized='true' name={quoteattr(DASHBOARD)}>
      <viewpoints>
{viewpoints}
      </viewpoints>
      <active id='-1' />
    </window>
  </windows>
</workbook>
"""
    OUT.write_text(workbook, encoding="utf-8")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
