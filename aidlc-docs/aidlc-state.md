# AI-DLC State Tracking

## Project Information
- **Project Type**: Greenfield
- **Start Date**: 2026-08-26T06:28:03Z
- **Current Stage**: INCEPTION - Requirements Analysis (awaiting approval)

## Workspace State
- **Existing Code**: No
- **Programming Languages**: None detected
- **Build System**: None detected
- **Project Structure**: Empty
- **Reverse Engineering Needed**: No
- **Workspace Root**: /Users/junho/coding_work/qc_book

## Reference Assets (created pre-workflow)
- `refs/nielsen-chuang.txt` — full text extract, 710 pdf pages / 1.8MB
- `refs/toc-raw.txt` — layout-preserved table of contents
- `refs/nc.sh` — lookup helper (find / page / layout / pdfpage)
- **Page mapping**: pdf page = book page + 34
- **Source PDF**: /Users/junho/Desktop/papers/quantum_computing/quantum-computation-and-quantum-information-nielsen-chuang.pdf

## Environment (FIXED)
- **Python venv**: `/Users/junho/venv_folders/qc_env`
- **Interpreter**: `/Users/junho/venv_folders/qc_env/bin/python` — Python 3.13.1
- **Rule**: ALL Python execution and package installation for this project MUST use this venv.
  Never use system `python3` or any other environment.
- **Current packages**: pip only (clean env)

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis |
| Resiliency Baseline | No | Requirements Analysis |
| Property-Based Testing | No | Requirements Analysis |

## Execution Plan Summary
- **Total Stages**: 9 (+1 placeholder)
- **Stages to Execute**: Application Design, Code Generation, Build and Test
- **Stages to Skip**: Reverse Engineering (greenfield), User Stories (single persona),
  Units Generation (YAGNI, tightly coupled small system), Functional Design (absorbed by App Design),
  NFR Requirements (already fixed in requirements.md), NFR Design (dependent skip),
  Infrastructure Design (no cloud/deployment)

## Key Decisions
- **OTD-3 RESOLVED (a)**: headless `claude -p` per question. No long-lived session to babysit.
- **NFR-7**: answer worker must NOT load AI-DLC rules. Worker cwd lives OUTSIDE the project tree.
  Measured: 22,759 cache-creation tokens from project root vs 13,410 from outside (~9,300 = AI-DLC CLAUDE.md).
- **`--bare` REJECTED**: forces ANTHROPIC_API_KEY auth, violating NFR-5.
- **OTD-1 RESOLVED**: pdftoppm PNG + pdftotext -bbox transparent text layer. Beats both original options —
  on-page drag selection with ZERO JS deps. Plus pdftoppm crop (-x -y -W -H) for region selection.
- **QG-1 RESOLVED**: --allowedTools "Bash Read WebSearch" is MANDATORY; --permission-mode dontAsk alone denies all tools.
- **Worker call must use `< /dev/null`** (else 3s stall) and must NOT merge stderr into stdout (corrupts JSON).
- **Answer generation split into 2 stages** after measuring 144,951ms for a single deep question.
- **KaTeX vendored (~592KB)** — the project's only external JS dependency, chosen explicitly by the user.

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Reverse Engineering (SKIPPED — greenfield)
- [x] Requirements Analysis (APPROVED)
- [x] User Stories (SKIP)
- [x] Workflow Planning (awaiting approval)
- [x] Application Design - COMPLETE (APPROVED)
- [ ] Units Generation - SKIP

### 🟢 CONSTRUCTION PHASE
- [ ] Functional Design - SKIP
- [ ] NFR Requirements - SKIP
- [ ] NFR Design - SKIP
- [ ] Infrastructure Design - SKIP
- [x] Code Generation - COMPLETE (APPROVED)
- [x] Build and Test - COMPLETE (APPROVED)

### 🟡 OPERATIONS PHASE
- [x] Operations - PLACEHOLDER (해당 없음)

## Current Status
- **Lifecycle Phase**: COMPLETE
- **Current Stage**: 워크플로 종료 (2026-08-26)
- **Status**: 전 단계 승인 완료. Operations 는 placeholder 라 해당 없음

## Delivered Scope
- FR-1 (연속 스크롤로 개정) ~ FR-13, NFR-1 ~ NFR-7 전부 구현·검증
- 단위 테스트 54개 / 레이아웃 점검 15개 (실제 Chrome 계측) / 통합 검증 IT-1~IT-10
- 사용자 확인 완료: 텍스트 레이어 정렬, KaTeX, 영역 선택, 위치 복원, 스크롤,
  패널 비덮음, 폭 조절, 목차 이동
