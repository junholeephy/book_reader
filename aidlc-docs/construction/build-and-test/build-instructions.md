# Build Instructions

이 프로젝트는 **컴파일 단계가 없습니다.** Python 표준 라이브러리와 바닐라 JS로만 되어 있어
"빌드"는 사전 조건 확인과 자산 준비를 뜻합니다.

## 사전 조건

| 항목 | 요구 | 확인 명령 |
|---|---|---|
| Python | `/Users/junho/venv_folders/qc_env/bin/python` (3.13.1) | `$PY --version` |
| poppler | `pdftoppm`, `pdftotext`, `pdfinfo` | `which pdftoppm pdftotext` |
| Claude CLI | `~/.local/bin/claude` | `claude --version` |
| 원본 PDF | `~/Desktop/papers/quantum_computing/...nielsen-chuang.pdf` | `ls -l` |
| 추출 텍스트 | `refs/nielsen-chuang.txt` | `wc -l` |

poppler가 없으면: `brew install poppler`

**의존성 설치 단계는 없습니다.** `pip install` 을 실행하지 마십시오 — 표준 라이브러리만 씁니다.

## 자산 준비 (최초 1회, 이미 완료됨)

```bash
# KaTeX 벤더링 — reader/vendor/katex/ 에 592KB
curl -sSL -o /tmp/katex.tgz https://registry.npmjs.org/katex/-/katex-0.16.11.tgz
tar xzf /tmp/katex.tgz -C /tmp package/dist
cp /tmp/package/dist/katex.min.{js,css} reader/vendor/katex/
cp /tmp/package/dist/fonts/*.woff2 reader/vendor/katex/fonts/
```

## 빌드 검증

```bash
PY=/Users/junho/venv_folders/qc_env/bin/python
$PY -m py_compile reader/server.py reader/test_server.py   # 문법
$PY -c "import sys; sys.path.insert(0,'reader'); import server"   # 임포트
bash -n reader/start.sh ~/.qc-book-tutor/ask.sh            # 셸
node --check reader/app.js                                 # JS (node 있을 때)
```

**기대 결과**: 출력 없음(성공). 서버는 기동 시 `preflight()` 로 위 사전 조건을 스스로 검사하고,
빠진 것이 있으면 이유를 출력하고 멈춥니다.

## 문제 해결

**`pdftoppm: command not found`** — poppler 미설치. `brew install poppler`
**`기동 실패: 워커 없음`** — `~/.qc-book-tutor/ask.sh` 가 없거나 실행 권한 없음. `chmod +x`
**`포트 8765 가 이미 사용 중`** — `lsof -nP -iTCP:8765 -sTCP:LISTEN` 으로 확인
