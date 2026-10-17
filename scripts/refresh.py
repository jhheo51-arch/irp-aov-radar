"""명령 하나로 데이터를 갱신하고, 핵심 지표를 날짜별로 남기고, 지난번과 달라진 점을 기록한다.

사용:
  python scripts/refresh.py                 # 공시 다시 수집 + 기존 리뷰 분류로 집계 (API 키 불필요)
  python scripts/refresh.py --reviews       # 리뷰도 새로 수집하고 Claude API로 다시 분류 (.env 필요)
  python scripts/refresh.py --offline       # 수집 없이 현재 파일로 계산·스냅샷만 (점검용)

출력:
  data/snapshots/<YYYY-MM-DD>/metrics.json  핵심 지표 (공개 가능한 집계값만)
  data/snapshots/<YYYY-MM-DD>/*.csv         그날의 공개 결과 사본
  docs/data-changelog.md                    직전 스냅샷과의 비교 기록 (맨 위에 추가)
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROC = ROOT / "data" / "processed"
SNAPSHOTS = ROOT / "data" / "snapshots"
CHANGELOG = ROOT / "docs" / "data-changelog.md"

PUBLIC_OUTPUTS = ["irp_aov_by_provider.csv", "irp_trend.csv", "review_heatmap.csv", "review_labels.csv"]
FOCUS = {"한국투자증권": "kis", "미래에셋증권": "mirae", "삼성증권": "samsung"}

# 지표 이름, 단위, 높을수록 좋은가 (변화 기록의 해석용)
LABELS = {
    "latest_year": ("공시 기준 연도", "", None),
    "kis_contracts": ("한국투자증권 IRP 계약 수", "건", None),
    "kis_per_contract": ("한국투자증권 계약 1건당 적립금", "만 원", True),
    "mirae_per_contract": ("미래에셋증권 계약 1건당 적립금", "만 원", None),
    "samsung_per_contract": ("삼성증권 계약 1건당 적립금", "만 원", None),
    "kis_vs_mirae": ("한국투자증권 / 미래에셋증권", "배", True),
    "kis_vs_market": ("한국투자증권 / 전 업권 평균", "배", True),
    "kis_net_new_per_contract": ("한국투자증권 순증 1건당 적립금(추정)", "만 원", True),
    "pension_reviews": ("분류한 연금 리뷰", "건", None),
    "pain_reviews": ("불편 리뷰", "건", None),
    "post_join_share": ("불편 중 가입 이후 단계 비중", "%", False),
    "kis_pain_reviews": ("한국투자증권 불편 리뷰", "건", None),
    "kis_error_share": ("한국투자증권 불편 중 오류·장애 비중", "%", False),
}


def run(script, *args):
    print(f"\n▶ {script} {' '.join(args)}", flush=True)
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"{script} 실행 실패 (종료 코드 {result.returncode}). 스냅샷을 만들지 않고 멈춥니다.")


def read(name):
    with (PROC / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def collect_metrics():
    trend = read("irp_trend.csv")
    latest = max(int(r["year"]) for r in trend)
    now = {r["provider"]: r for r in trend if int(r["year"]) == latest}
    metrics = {"latest_year": latest}
    for provider, key in FOCUS.items():
        metrics[f"{key}_per_contract"] = int(now[provider]["per_contract_10k_krw"])
    kis = now["한국투자증권"]
    metrics["kis_contracts"] = int(kis["contracts"])
    metrics["kis_vs_mirae"] = round(metrics["kis_per_contract"] / metrics["mirae_per_contract"], 3)
    metrics["kis_vs_market"] = float(kis["vs_market"])
    metrics["kis_net_new_per_contract"] = int(kis["net_new_per_contract_10k_krw"] or 0)

    labels = read("review_labels.csv")
    pains = [r for r in labels if r["journey_stage"] != "연금 무관" and r["pain_type"] != "불편 없음(칭찬·중립)"]
    post = {"수익률·잔고 조회", "상품 선택·운용"}
    kis_pains = [r for r in pains if r["company"] == "한국투자증권"]
    metrics.update({
        "pension_reviews": len(labels),
        "pain_reviews": len(pains),
        "post_join_share": round(100 * sum(r["journey_stage"] in post for r in pains) / len(pains), 1),
        "kis_pain_reviews": len(kis_pains),
        "kis_error_share": round(100 * sum(r["pain_type"] == "오류·장애" for r in kis_pains) / len(kis_pains), 1) if kis_pains else 0,
        "prompt_versions": sorted({r["prompt_version"] for r in labels}),
        "models": sorted({r["model"] for r in labels}),
    })
    return metrics


def previous_snapshot(today):
    if not SNAPSHOTS.exists():
        return None, None
    dates = sorted(p.name for p in SNAPSHOTS.iterdir() if (p / "metrics.json").exists() and p.name < today)
    if not dates:
        return None, None
    return dates[-1], json.loads((SNAPSHOTS / dates[-1] / "metrics.json").read_text(encoding="utf-8"))


def fmt(value, unit):
    if isinstance(value, float):
        text = f"{value:,.1f}" if unit == "%" else f"{value:,.3f}" if unit == "배" else f"{value:,}"
    else:
        text = f"{value:,}" if isinstance(value, int) and unit != "" else str(value)
    return f"{text}{unit if unit in ('%', '배') else (' ' + unit if unit else '')}"


def changelog_entry(today, metrics, prev_date, prev):
    lines = [f"## {today}", ""]
    if prev is None:
        lines += ["첫 스냅샷입니다. 이후 실행부터 이 값과 비교합니다.", "", "| 지표 | 값 |", "|---|---:|"]
        lines += [f"| {LABELS[k][0]} | {fmt(metrics[k], LABELS[k][1])} |" for k in LABELS]
    else:
        lines += [f"직전 스냅샷({prev_date})과 비교했습니다.", "", "| 지표 | 직전 | 이번 | 변화 |", "|---|---:|---:|---|"]
        for key, (name, unit, higher_is_better) in LABELS.items():
            old, new = prev.get(key), metrics[key]
            if old is None or old == new:
                change = "같음" if old == new else "새 지표"
            elif isinstance(new, (int, float)) and isinstance(old, (int, float)):
                diff = new - old
                direction = "" if higher_is_better is None else (" (개선)" if (diff > 0) == higher_is_better else " (악화)")
                shown = fmt(round(diff, 3) if isinstance(diff, float) else diff, unit)
                if unit == "%":
                    shown = shown[:-1] + "%p"  # 비중의 차이는 퍼센트포인트
                change = f"{'+' if diff > 0 else ''}{shown}{direction}"
            else:
                change = "변경"
            lines.append(f"| {name} | {fmt(old, unit) if old is not None else '-'} | {fmt(new, unit)} | {change} |")
        if prev.get("prompt_versions") != metrics["prompt_versions"]:
            lines += ["", f"분류 기준이 바뀌었습니다: {prev.get('prompt_versions')} → {metrics['prompt_versions']}. 리뷰 지표는 기준 변경의 영향을 함께 받습니다."]
    lines += ["", f"리뷰 분류: 프롬프트 {', '.join(metrics['prompt_versions'])} / 모델 {', '.join(metrics['models'])}", ""]
    return "\n".join(lines)


def write_changelog(entry):
    header = "# 데이터 변경 기록\n\n`scripts/refresh.py`가 실행할 때마다 맨 위에 추가합니다. 공개 가능한 집계값만 기록합니다.\n\n"
    body = CHANGELOG.read_text(encoding="utf-8").split("\n\n", 2)[-1] if CHANGELOG.exists() else ""
    today_heading = entry.split("\n", 1)[0]
    if body.startswith(today_heading):  # 같은 날 다시 실행하면 그날 기록을 바꾼다
        body = body.split("\n## ", 1)[1] if "\n## " in body else ""
        body = ("## " + body) if body else ""
    CHANGELOG.write_text(header + entry + ("\n" + body if body else ""), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", action="store_true", help="리뷰를 새로 수집하고 Claude API로 다시 분류")
    parser.add_argument("--offline", action="store_true", help="수집 없이 계산과 스냅샷만")
    args = parser.parse_args()

    if not args.offline:
        run("collect_fss.py")
    run("build_aov.py")
    run("analyze_trend.py")
    if args.reviews and not args.offline:
        run("collect_reviews.py")
        run("classify_reviews.py")
    run("summarize_reviews.py")
    run("build_tableau.py")
    run("build_twb.py")
    run("check_public.py")  # 공개 전 점검을 통과해야 스냅샷을 남긴다

    today = date.today().isoformat()
    metrics = collect_metrics()
    prev_date, prev = previous_snapshot(today)

    folder = SNAPSHOTS / today
    folder.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_OUTPUTS:
        shutil.copy2(PROC / name, folder / name)
    (folder / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_changelog(changelog_entry(today, metrics, prev_date, prev))

    print(f"\n스냅샷: {folder}")
    print(f"변경 기록: {CHANGELOG}")
    print(f"한국투자증권 계약 1건당 {metrics['kis_per_contract']:,}만 원 (미래에셋의 {metrics['kis_vs_mirae']:.0%}), "
          f"불편 중 가입 이후 {metrics['post_join_share']}%")


if __name__ == "__main__":
    main()
