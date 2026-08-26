#!/bin/bash
# book_reader 설치.
#
#   ./setup.sh <PDF 경로> [--python <인터프리터>]
#
# 하는 일:
#   1. PDF 를 확인하고 페이지 수 · 쪽번호 오프셋 · 목차 범위를 자동 검출
#   2. config.json 생성
#   3. 본문 텍스트와 목차를 refs/ 로 추출  (저장소에는 올라가지 않는다 — 저작물)
#   4. KaTeX 벤더링
#   5. 답변 워커를 홈 디렉터리에 설치
#
# 워커를 홈에 두는 이유: Claude Code 는 CLAUDE.md 를 상위 디렉터리로 거슬러 올라가며
# 찾는다. 워커를 프로젝트 안에 두면 책 질문마다 이 저장소의 개발 규칙이 딸려 들어간다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# SSH 로 명령을 직접 실행하면 로그인 셸이 아니라 /opt/homebrew/bin 이 PATH 에 없다.
# poppler 가 통째로 안 보이므로 알려진 위치를 덧붙인다.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"

PDF="${1:-}"
PY="python3"
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --python) PY="$2"; shift 2 ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done

[ -n "$PDF" ] || { echo "사용법: ./setup.sh <PDF 경로> [--python <인터프리터>]" >&2; exit 2; }
[ -f "$PDF" ] || { echo "PDF 를 찾을 수 없습니다: $PDF" >&2; exit 1; }

echo "==> 필요한 도구 확인"
missing=()
for t in pdftoppm pdftotext pdfinfo curl tar; do
  command -v "$t" >/dev/null || missing+=("$t")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "  없음: ${missing[*]}" >&2
  echo "  poppler 가 필요합니다:  brew install poppler" >&2
  exit 1
fi
command -v "$PY" >/dev/null || { echo "python 을 찾을 수 없습니다: $PY" >&2; exit 1; }
[ -x "$HOME/.local/bin/claude" ] || command -v claude >/dev/null || \
  echo "  경고: claude CLI 를 찾지 못했습니다. 질문 기능이 동작하지 않습니다." >&2

echo "==> PDF 분석 (페이지 수 · 쪽번호 오프셋 · 목차 범위)"
"$PY" - "$ROOT" "$PDF" "$PY" <<'PYEOF'
import json, sys, pathlib
root, pdf, py = sys.argv[1:4]
sys.path.insert(0, str(pathlib.Path(root, "reader")))
import config

total = config.page_count(pdf)
offset = config.detect_offset(pdf, total)
toc = config.detect_toc_pages(pdf, total)

cfg = dict(config.DEFAULTS)
existing = pathlib.Path(root, "config.json")
if existing.exists():
    cfg.update(json.loads(existing.read_text()))
cfg.update({"pdf": pdf, "python": py, "pageCount": total,
            "pageOffset": offset, "tocPages": toc or "1-20",
            "bookTitle": pathlib.Path(pdf).stem.replace("-", " ")})
config.CONFIG_PATH = existing
config.save(cfg)

print(f"  총 페이지 : {total}")
print(f"  쪽번호 오프셋: {offset}   (PDF 페이지 = 책 페이지 + {offset})")
print(f"  목차 범위 : {cfg['tocPages']}")
if offset == 0:
    print("  주의: 오프셋을 확신하지 못했습니다. 지면 번호와 다르면 config.json 에서 고치십시오.")
PYEOF

PDF_PATH=$("$PY" -c "import json;print(json.load(open('$ROOT/config.json'))['pdf'])")
TOC_RANGE=$("$PY" -c "import json;print(json.load(open('$ROOT/config.json'))['tocPages'])")
TOC_FROM="${TOC_RANGE%%-*}"; TOC_TO="${TOC_RANGE##*-}"

echo "==> 본문 텍스트 추출 (검색용)"
mkdir -p "$ROOT/refs"
pdftotext "$PDF_PATH" "$ROOT/refs/book.txt"
echo "  refs/book.txt  ($(du -h "$ROOT/refs/book.txt" | cut -f1))"

echo "==> 목차 추출 (PDF $TOC_FROM-$TOC_TO)"
pdftotext -layout -f "$TOC_FROM" -l "$TOC_TO" "$PDF_PATH" "$ROOT/refs/toc-raw.txt"
ENTRIES=$("$PY" -c "
import sys; sys.path.insert(0,'$ROOT/reader')
from toc import Toc; from pathlib import Path
print(len(Toc.load(Path('$ROOT/refs/toc-raw.txt')).items))")
echo "  목차 항목 $ENTRIES 개"
[ "$ENTRIES" -gt 0 ] || echo "  주의: 목차를 하나도 읽지 못했습니다. config.json 의 tocPages 를 고치십시오." >&2

echo "==> KaTeX 벤더링 (수식 렌더, 오프라인)"
if [ -f "$ROOT/reader/vendor/katex/katex.min.js" ]; then
  echo "  이미 있음 — 건너뜀"
else
  mkdir -p "$ROOT/reader/vendor/katex/fonts"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  curl -sSL --max-time 120 -o "$TMP/katex.tgz" \
    https://registry.npmjs.org/katex/-/katex-0.16.11.tgz
  tar xzf "$TMP/katex.tgz" -C "$TMP" package/dist
  cp "$TMP/package/dist/katex.min.js" "$TMP/package/dist/katex.min.css" "$ROOT/reader/vendor/katex/"
  cp "$TMP"/package/dist/fonts/*.woff2 "$ROOT/reader/vendor/katex/fonts/"
  # woff2 만 남기므로 CSS 의 나머지 폰트 참조를 지운다 (없는 파일 요청 방지)
  "$PY" - "$ROOT/reader/vendor/katex/katex.min.css" <<'PYEOF'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1]); css = p.read_text()
css = re.sub(r',url\([^)]*\.woff\)\s*format\("woff"\)', '', css)
css = re.sub(r',url\([^)]*\.ttf\)\s*format\("truetype"\)', '', css)
p.write_text(css)
PYEOF
  echo "  $(du -sh "$ROOT/reader/vendor/katex" | cut -f1)"
fi

echo "==> 답변 워커 설치"
TUTOR=$("$PY" -c "
import json,os;print(os.path.expanduser(json.load(open('$ROOT/config.json'))['tutorDir']))")
mkdir -p "$TUTOR"
cp "$ROOT/tutor/ask.sh" "$TUTOR/ask.sh"; chmod +x "$TUTOR/ask.sh"
cp "$ROOT/tutor/schema-summary.json" "$ROOT/tutor/schema-detail.json" "$TUTOR/"

"$PY" - "$ROOT" "$TUTOR" <<'PYEOF'
import json, pathlib, sys
root, tutor = sys.argv[1:3]
cfg = json.loads(pathlib.Path(root, "config.json").read_text())
tmpl = pathlib.Path(root, "tutor", "CLAUDE.md.tmpl").read_text()
for k, v in {"{{BOOK_TITLE}}": cfg.get("bookTitle", "이 책"),
             "{{PDF}}": cfg["pdf"],
             "{{OFFSET}}": str(cfg["pageOffset"]),
             "{{REFS}}": str(pathlib.Path(root, "refs"))}.items():
    tmpl = tmpl.replace(k, v)
pathlib.Path(tutor, "CLAUDE.md").write_text(tmpl)

env = "\n".join([
    "# setup.sh 가 생성. 손으로 고치지 말고 ./setup.sh 를 다시 돌리십시오.",
    f'PROJECT="{root}"',
    f'PDFDIR="{pathlib.Path(cfg["pdf"]).parent}"',
    f'PY="{cfg["python"]}"',
    "",
])
pathlib.Path(tutor, "config.env").write_text(env)
PYEOF
echo "  $TUTOR"

mkdir -p "$ROOT/qa/questions" "$ROOT/qa/answers" "$ROOT/qa/crops" "$ROOT/cache/pages"
[ -f "$ROOT/qa/state.json" ] || echo '{"lastBookPage": 1, "sessions": {}}' > "$ROOT/qa/state.json"
[ -f "$ROOT/qa/history.md" ] || printf '# 학습 노트\n\n' > "$ROOT/qa/history.md"

echo
echo "설치 완료.  ./reader/start.sh 로 실행하십시오."
