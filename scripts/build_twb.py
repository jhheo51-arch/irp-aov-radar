"""data/tableau/의 CSV 4개로 시트 4개가 들어간 Tableau 통합문서(.twb)를 만든다.

출력: data/tableau/irp_aov_radar.twb
대시보드 배치, 색, 참조선, 필터 카드는 Tableau에서 직접 마무리한다(docs/tableau-build-guide.md).
"""
import csv
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tableau"
OUT = DATA / "irp_aov_radar.twb"

# 원본 이름 -> (CSV 파일, 차원으로 둘 숫자 열)
SOURCES = {
    "t1": ("t1_aov_trend.csv", {"year"}),
    "t2": ("t2_heatmap.csv", {"stage_order", "pain_order"}),
    "t3": ("t3_opportunities.csv", {"stage_order"}),
    "t4": ("t4_quality.csv", set()),
}

# 시트 정의: 열/행 선반, 마크, 인코딩, 필터.  필드 표기: (집계, 원본 열)  집계 none = 차원
SHEETS = [
    {
        "name": "1 객단가 격차", "source": "t1", "mark": "Circle",
        "cols": [("sum", "contracts")], "rows": [("sum", "reserve_per_contract_10k_krw")],
        "color": ("none", "highlight"), "size": ("sum", "reserve_100m_krw"), "text": ("none", "provider"),
        "filter": ("year", "2025"),
    },
    {
        "name": "2 불편 히트맵", "source": "t2", "mark": "Square",
        "cols": [("none", "pain_label")], "rows": [("none", "stage_label")],
        "color": ("sum", "reviews"), "text": ("sum", "reviews"),
    },
    {
        "name": "3 기회", "source": "t3", "mark": "Bar",
        "cols": [("sum", "pain_reviews_3co")], "rows": [("none", "lever_label")],
        "color": ("sum", "share_3co"), "text": ("sum", "share_3co"),
        "lod": [("none", "meaning"), ("none", "example_requests"), ("none", "top_pain_type"), ("sum", "pain_reviews_kis")],
    },
    {
        "name": "4 관리", "source": "t4", "mark": "Text",
        "rows": [("none", "area"), ("none", "metric"), ("none", "value")], "cols": [],
        "text": ("none", "note"),
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
    for name, dtype in cols:
        if dtype == "string" or name in dims:
            role, typ = "dimension", ("ordinal" if name in dims else "nominal")
        else:
            role, typ = "measure", "quantitative"
        parts.append(f"      <column datatype='{dtype}' name='[{name}]' role='{role}' type='{typ}' />")
    parts.append("    </datasource>")
    return "\n".join(parts), dict(cols)


def shelf(tag, refs):
    """선반 XML. 필드가 여러 개면 Tableau 형식대로 괄호로 묶고 ' / '로 중첩한다."""
    if not refs:
        return f"<{tag} />"
    body = refs[0] if len(refs) == 1 else "(" + " / ".join(refs) + ")"
    return f"<{tag}>{body}</{tag}>"


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
            dtype = types[col]
            if dtype == "string" or col in dims:
                deps.append(f"            <column datatype='{dtype}' name='[{col}]' role='dimension' type='{'ordinal' if col in dims else 'nominal'}' />")
            else:
                deps.append(f"            <column datatype='{dtype}' name='[{col}]' role='measure' type='quantitative' />")
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
    encodings = []
    for enc in ("color", "size", "text"):
        if enc in sheet:
            encodings.append(f"              <{enc} column='{ref(sheet[enc])}' />")
    for field in sheet.get("lod", []):
        encodings.append(f"              <lod column='{ref(field)}' />")

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
        <style />
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{sheet['mark']}' />
            <encodings>
{chr(10).join(encodings)}
            </encodings>
          </pane>
        </panes>
        {shelf('rows', [ref(f) for f in sheet.get('rows', [])])}
        {shelf('cols', [ref(f) for f in sheet.get('cols', [])])}
      </table>
    </worksheet>"""


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
  <windows source-height='30'>
{windows}
  </windows>
</workbook>
"""
    OUT.write_text(workbook, encoding="utf-8")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
