"""공개 전 점검: 저장소에 올라갈 파일에 비밀 정보나 리뷰 원문이 섞이지 않았는지 검사한다.

push할 때마다 GitHub Actions에서 돌고, refresh.py도 스냅샷을 남기기 전에 이 검사를 통과해야 한다.
하나라도 걸리면 종료 코드 1로 멈춘다.

검사 항목
  1. 금지 경로   .env, 리뷰 원문 폴더, 원문이 든 분류·검수 파일이 올라가 있지 않은가
  2. 비밀 정보   API 키·토큰·개인 키 형식의 문자열이 없는가
  3. 금지 열     공개 CSV에 원문·근거 인용·작성자 정보 열이 없는가
  4. 원문 조각   공개 파일에 리뷰 원문과 같은 25자 조각이 없는가
                 (원문은 내 PC에만 있으므로 원문 파일이 있을 때만 검사한다. CI에서는 건너뛴다)

검사 대상은 Git이 추적하는 파일과, 아직 추가하지 않았지만 .gitignore에 걸리지 않는 파일이다.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_REVIEWS = ROOT / "data" / "raw" / "reviews"
WINDOW = 25

FORBIDDEN_PATHS = [
    (re.compile(r"(^|/)\.env$"), ".env는 API 키가 들어가는 파일"),
    (re.compile(r"^data/raw/reviews/"), "리뷰 원문 폴더"),
    (re.compile(r"_full\.csv$"), "원문이 포함된 분류 결과"),
    (re.compile(r"audit_sample"), "원문이 포함된 검수 표본"),
]

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API 키"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub 토큰"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{30,}"), "GitHub 토큰"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS 액세스 키"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "개인 키"),
    (re.compile(r"(?i)\b(app_?key|app_?secret|api_?key|secret|token)\b\s*[=:]\s*['\"]?[A-Za-z0-9+/_\-]{24,}"), "키 값 대입"),
]

# 공개 CSV에 있으면 안 되는 열: 원문, 근거 인용, 작성자 정보
FORBIDDEN_COLUMNS = {"content", "evidence", "username", "user_name", "userimage", "reviewid", "review_id", "author"}

TEXT_SUFFIXES = {".md", ".py", ".csv", ".json", ".html", ".twb", ".txt", ".yml", ".yaml", ".example", ".gitignore"}


def public_files():
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p and (ROOT / p).is_file())


def read_text(path):
    if Path(path).suffix not in TEXT_SUFFIXES and Path(path).name not in TEXT_SUFFIXES:
        return None
    return (ROOT / path).read_text(encoding="utf-8-sig", errors="replace")


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def raw_windows():
    """내 PC에 있는 연금 리뷰 원문과 근거 인용에서 25자 조각을 모두 만든다."""
    windows = set()
    for name, column in [("reviews_pension.csv", "content"), ("review_labels_full.csv", "evidence")]:
        path = RAW_REVIEWS / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                text = normalize(row.get(column) or "")
                windows.update(text[i:i + WINDOW] for i in range(len(text) - WINDOW + 1))
    return windows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = public_files()
    problems = []

    for path in files:
        for pattern, why in FORBIDDEN_PATHS:
            if pattern.search(path):
                problems.append(f"[금지 경로] {path} — {why}")

    texts = {p: t for p in files if (t := read_text(p)) is not None}

    for path, text in texts.items():
        for pattern, why in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"[비밀 정보] {path}:{line} — {why} 형식의 문자열")

    for path, text in texts.items():
        if path.endswith(".csv"):
            header = next(csv.reader([text.splitlines()[0]]), []) if text else []
            bad = {h.strip().lower() for h in header} & FORBIDDEN_COLUMNS
            if bad:
                problems.append(f"[금지 열] {path} — {', '.join(sorted(bad))}")

    windows = raw_windows()
    if windows:
        for path, text in texts.items():
            flat = normalize(text)
            hits = {flat[i:i + WINDOW] for i in range(len(flat) - WINDOW + 1)} & windows
            if hits:
                problems.append(f"[원문 조각] {path} — 리뷰 원문과 같은 {WINDOW}자 조각 {len(hits)}개 (예: {next(iter(hits))!r})")
        fragment_note = f"리뷰 원문 {WINDOW}자 조각 {len(windows):,}개와 대조"
    else:
        fragment_note = "원문 파일이 없어 원문 조각 대조는 건너뜀 (CI에서는 정상)"

    print(f"공개 전 점검: 파일 {len(files)}개 (텍스트 {len(texts)}개), {fragment_note}")
    if problems:
        print(f"실패: {len(problems)}건")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    checked = "금지 경로·비밀 정보·금지 열" + ("·원문 조각" if windows else "")
    print(f"통과: {checked} 0건")


if __name__ == "__main__":
    main()
