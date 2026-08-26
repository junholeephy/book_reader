# AI-DLC Audit Log

## Initial User Request
**Timestamp**: 2026-08-26T06:28:03Z
**User Input**: "여기서는 ai-dlc 방식으로 개발을 진행하고 싶어. 내가 PDF 파일을 업로드 하면 관련해서 답변을 해줄 수 있어?"
**AI Response**: "Confirmed PDF capability. Inspected workspace: .aidlc-rule-details present, no aidlc-docs, no source code. Explained pdftotext vs page-image reading tradeoffs and asked for the PDF path and its intended role."
**Context**: Pre-workflow capability question

---

## Initial User Request (continued)
**Timestamp**: 2026-08-26T06:28:03Z
**User Input**: "파일은 어거야. 내가 질문을 하면 디테일한 내용까지 책에서 그리고 웹에서 찾아서 상세히 답변해줬으면 좋겠어  '/Users/junho/Desktop/papers/quantum_computing/quantum-computation-and-quantum-information-nielsen-chuang.pdf'"
**AI Response**: "Extracted full text (710 pdf pages, 1.8MB) to refs/nielsen-chuang.txt, derived page offset (pdf = book + 34), extracted TOC to refs/toc-raw.txt, and built refs/nc.sh lookup helper (find/page/layout/pdfpage). Verified with 'Grover iteration' search."
**Context**: Reference asset provisioning — Nielsen & Chuang textbook indexed for retrieval

---

## Scope Change — Build Request
**Timestamp**: 2026-08-26T06:28:03Z
**User Input**: "이걸 그냥 간단한 HTML로 만들어서 내용을 좌측에 띄위 주고  내가 읽으면서 모르는 부분 우측에서 질문하면 관련 답변을 바로바로 해주는걸로 만들면 어때?"
**AI Response**: "Recognized this as a software development request. Initiated AI-DLC workflow: displayed welcome message, executed Workspace Detection, proceeded to Requirements Analysis."
**Context**: Request type changed from Q&A to New Project (greenfield). Triggers full AI-DLC workflow per CLAUDE.md.

---

## Workspace Detection
**Timestamp**: 2026-08-26T06:28:03Z
**AI Response**: "Greenfield project detected. No source code files, no build files, no aidlc-state.md. Only .aidlc-rule-details/ (rules), .omc/ (tooling), CLAUDE.md (instructions), and refs/ (reference assets created this session). brownfield = false. Reverse Engineering SKIPPED. Next: Requirements Analysis."
**Context**: INCEPTION - Workspace Detection complete

---
## Requirements Analysis — Clarifying Questions Presented
**Timestamp**: 2026-08-26T06:29:21Z
**AI Response**: "Created aidlc-docs/inception/requirements/requirement-verification-questions.md with 7 project questions + 3 extension opt-in questions. Intent analysis: Request Type = New Project (greenfield), Clarity = Vague (answer-engine mechanism unspecified), Scope = Multiple Components, Complexity = Moderate. Depth = Standard. Gate: awaiting user answers before Step 7."
**Context**: INCEPTION - Requirements Analysis, Step 6 gate

---
## Requirements Analysis — User Answers Received
**Timestamp**: 2026-08-26T06:39:22Z
**User Input**: "done"
**Answers extracted from requirement-verification-questions.md**:
- Q1 (답변 엔진): "D. 내가 CLI에서 질의 하듯이, HTML에서의 질의를 claude code가 PDF와 웹을 기반으로 답변하면 돼"
- Q2 (본문 표시): "C"
- Q3 (맥락 첨부): "B"
- Q4 (기록 저장): "A. 그리고 내가 만약 HTML을 껏다 다시 키면 이전에 위치부터 시작할 수 있는 기능도 구현해줘"
- Q5 (웹 검색): "B"
- Q6 (답변 스타일): "C"
- Q7 (수명): "A."
- Security Extension: "B"
- Resiliency Extension: "B"
- Property-Based Testing Extension: "C"
**AI Response**: "CONTRADICTION DETECTED on Q1: letter choice D (self-built Python agent calling Anthropic API with user's own key) contradicts the free-text description, which describes option B (Claude Code itself answers using PDF + web). These are mutually exclusive answering engines with materially different cost, capability, and implementation scope. Created requirements-clarification-questions.md. Also noted NEW functional requirement from Q4: resume last reading position on reopen."
**Context**: INCEPTION - Requirements Analysis, Step 6 contradiction detection

---
## Requirements Analysis — Clarification Answers Received
**Timestamp**: 2026-08-26T06:43:24Z
**User Input**: "donw"
**Answers extracted from requirements-clarification-questions.md**:
- Clarification Q1 (답변 주체): "A"  → Claude Code answers (original option B, watch-based low latency)
- Clarification Q2 (세션 오프라인 시): "A" → queue questions, answer when session resumes
- [의견 (선택)]: (empty — Q6 progressive-depth interpretation accepted without objection)
**AI Response**: "Contradiction resolved. Answering engine = Claude Code via local file-watch bridge; no Anthropic API key, no per-question cost. Proceeding to Step 7: generate requirements.md."
**Context**: INCEPTION - Requirements Analysis, contradiction resolved

---
## Requirements Analysis — Complete, Approval Requested
**Timestamp**: 2026-08-26T06:44:36Z
**AI Response**: "Generated aidlc-docs/inception/requirements/requirements.md — 9 functional requirements (FR-1..FR-9), 6 non-functional requirements (NFR-1..NFR-6), extension config (all 3 disabled), out-of-scope list, and 2 open technical decisions (OTD-1 PDF rendering approach, OTD-2 file-watch mechanism) deferred to Application Design. Updated aidlc-state.md. Assessment: User Stories stage recommended SKIP (single-user personal tool, single persona, requirements already crystallized through two clarification rounds). Offering 'Add User Stories' as an option per rule format. Awaiting explicit approval."
**Context**: INCEPTION - Requirements Analysis, Step 9 approval gate

---
## Requirements Change Request — Python Environment
**Timestamp**: 2026-08-26T06:59:15Z
**User Input**: "사용하게 될 파이썬 환경은 항상 여기이고, 이걸 명시해둬 /Users/junho/venv_folders/qc_env"
**AI Response**: "Verified venv exists: Python 3.13.1, only pip installed (clean env). Recorded in requirements.md NFR-1 (fixed interpreter path, all Python execution/installation must use it) and aidlc-state.md (new '## Environment (FIXED)' section). Also persisted to session memory."
**Context**: INCEPTION - Requirements Analysis, change request during approval gate

---

## Design Question — Claude Code Session Availability
**Timestamp**: 2026-08-26T06:59:15Z
**User Input**: "그리고 claude code 세션은 어떻게 띄워둘 생각이야?"
**AI Response**: "Valid challenge to the weakest point of the approved architecture. Investigated and VERIFIED headless invocation as an alternative to keeping a session alive: 'claude -p <prompt> --output-format json --permission-mode dontAsk' from the project directory returned result='SMOKE_OK' in 3.9s wall (2.3s TTFT). Confirmed available flags: -p/--print, --output-format json, --session-id <uuid>, --resume, --permission-mode, --allowedTools, --add-dir, --bare. MEASURED CONCERN: the invocation loaded 22,759 cache-creation tokens on a trivial prompt because the project's large AI-DLC CLAUDE.md is auto-discovered every run — mitigable by running the answer worker from a separate cwd with --add-dir. Raising as OTD-3 for user decision since it materially changes FR-8."
**Context**: INCEPTION - Requirements Analysis, architecture concern raised by user

---
## Requirements Analysis — APPROVED with OTD-3 resolution
**Timestamp**: 2026-08-26T07:03:35Z
**User Input**: "a로 확정하고 승인. 그리고 html에서의 질문은 당연히 ai-dlc쪽이랑은 무관한 질문이어서 이부분 읽는 것은 말이 안돼지. ai-dlc는 개발할 때만 사용하자"
**AI Response**: "Requirements APPROVED. OTD-3 resolved = (a) headless 'claude -p' invocation per question; no long-lived Claude Code session required. User additionally mandated that the answer worker MUST NOT load AI-DLC rules — AI-DLC applies to development only, not to book Q&A. Recorded as new NFR-7. EMPIRICALLY VERIFIED the isolation: identical trivial prompt run from project root = 22,759 cache-creation tokens vs run from a directory outside the project tree = 13,410. Delta ~9,300 tokens = the AI-DLC CLAUDE.md. Therefore the worker cwd must sit OUTSIDE /Users/junho/coding_work/qc_book (CLAUDE.md discovery walks up the tree), with --add-dir granting access to refs/ and the PDF. NOTE: --bare was evaluated and REJECTED as an isolation mechanism because it forces ANTHROPIC_API_KEY auth, violating NFR-5 (no API key / no per-question billing). Proceeding to Workflow Planning."
**Context**: INCEPTION - Requirements Analysis approved; proceeding to Workflow Planning

---
## Workflow Planning — Complete, Approval Requested
**Timestamp**: 2026-08-26T07:05:04Z
**AI Response**: "Created aidlc-docs/inception/plans/execution-plan.md. Risk = Low (easy rollback, no external state). EXECUTE 3 stages: Application Design, Code Generation, Build and Test. SKIP 6 stages with rationale. Mermaid diagram syntax-validated (balanced brackets, no undeclared refs, no unescaped quotes) with text alternative included per content-validation.md. Defined 7 quality gates including QG-1 (worker tool permissions in non-interactive mode — unproven) and QG-2 (NFR-7 rule isolation verified by token count). Extension compliance: all three extensions disabled by user opt-out, therefore N/A at this stage — no blocking findings. Awaiting approval."
**Context**: INCEPTION - Workflow Planning, Step 9 approval gate

---
## Workflow Planning — APPROVED
**Timestamp**: 2026-08-26T07:09:46Z
**User Input**: "Approve & Continue"
**AI Response**: "Execution plan approved. Proceeding to Application Design."
**Context**: INCEPTION - Workflow Planning approved

---

## Application Design — Empirical Pre-Validation (QG-1, OTD-1, OTD-2)
**Timestamp**: 2026-08-26T07:09:46Z
**AI Response**: "Ran five verification experiments BEFORE designing, resolving the two open technical decisions and the top risk:

TEST A (QG-1, FAILED as suspected): 'claude -p ... --permission-mode dontAsk' with a Bash-requiring prompt was DENIED. permission_denials recorded Bash. Confirms the earlier smoke test only passed because it used no tools.

TEST B (QG-1, PASSED): adding --allowedTools 'Bash Read WebSearch' cleared it. Worker ran refs/nc.sh and returned book pages '250, 251' — matches independently-verified ground truth. permission_denials empty.

TEST C (PASSED): worker read PDF page 286 as an image via Read pages= and returned the Grover rotation-angle formula in LaTeX: cos(theta/2) = sqrt((N-M)/N). Correct (N&C eq. near 6.10-6.12). 6.1s. This means equations lost by text extraction CAN be recovered from the page image.

TEST D/D2 (PASSED): WebSearch executes. First attempt was inconclusive (usage counter showed web_search_requests: 0), so re-tested with a query requiring post-cutoff data; worker returned an item dated 2026-08-25, impossible from training data. Conclusion: the server_tool_use counter does not track the client-side WebSearch tool; the tool itself works.

TEST E (OTD-1 RESOLVED): pdftoppm IS installed (/opt/homebrew/bin/pdftoppm) — not previously verified. Rendered pdf p.286 at 150dpi in 0.209s, 308KB PNG. Visual inspection confirms all equations legible and page header reads '252', re-confirming the +34 offset (QG-3, QG-4 pre-validated).

TEST F (OTD-1 refinement): pdftotext -bbox emits per-word bounding boxes plus page dimensions. This enables an invisible selectable text layer over the PNG — pdf.js-style on-page selection with ZERO JS dependencies. Note: math glyphs emit empty <word> elements, so the text layer has gaps at equations (acceptable; page number still routes the worker to the image).

DECISIONS: OTD-1 = pdftoppm PNG + pdftotext -bbox text overlay (strictly better than either original option). OTD-2 = moot, superseded by OTD-3(a) headless invocation.
Created application-design-plan.md with remaining questions."
**Context**: INCEPTION - Application Design, pre-design validation

---
## Application Design — Answers Received
**Timestamp**: 2026-08-26T07:25:41Z
**User Input**: "done"
**Answers extracted from application-design-plan.md**:
- Q1 (수식 표시): "A. 수식을 읽는데 불편함이 없어야 해"  → KaTeX vendored
- Q2 (맥락 유지): "A"  → fixed --session-id
- Q3 (실행 방식): "A. HTML 실행과 같이 서버가 띄위지면 될 것 같아. 대화 내용도 어디 기록을 해두는 건가?"
- Q4 (논블로킹): "A"
- Q5 (워커 위치): "A"  → ~/.qc-book-tutor/
- Q6 (수식 영역 선택): "B"  → rectangle region selection ADDED (differs from AI recommendation A)
**AI Response**: "Q3 reconciled without a new clarification round: the letter (A, manual) and the description ('server should come up together with launching the HTML' = one action) point to slightly different things, but a single start.sh satisfies both readings — manual and visible, not launchd, yet one step. Documented as the design; user can correct. Q3's embedded question about conversation records answered in the completion message. Ran four more experiments:

TEST (crop): pdftoppm supports -x -y -W -H crop. Cropped the eq. 6.11 region of pdf p.286 in 0.039s / 17KB; visually verified the crop isolates the equation cleanly. Q6=B is implementable with zero new dependencies.

TEST (KaTeX): downloadable from npm registry. Vendoring footprint = katex.min.js 272K + katex.min.css 24K + 20 woff2 fonts 296K = ~592KB (ttf/woff variants droppable). Offline after one download, so NFR-4 holds.

TEST G (structured output + full pipeline rehearsal): --json-schema works and returned a valid object with keys summary/detail/bookPages. Answer quality verified high — correct derivation of the Grover-iteration-as-rotation argument, cited book pages [250,251,252,253,254,262], LaTeX well-formed.

CRITICAL MEASUREMENT: the rehearsal took 144,951 ms (9 turns) — NOT the 10-30s previously estimated to the user. Correcting this and redesigning around it: answers will be produced in two stages (fast summary first, depth on demand) to serve FR-5's progressive structure AND cut perceived latency.

OPERATIONAL FINDING: 'claude -p' stalls ~3s waiting on stdin and emits 'Warning: no stdin data received in 3s' to stderr. The worker MUST redirect '< /dev/null' and MUST NOT merge stderr into stdout (2>&1 corrupts JSON parsing — this is what broke the first attempt at TEST G)."
**Context**: INCEPTION - Application Design, answers analyzed and validated

---
## Application Design — Complete, Approval Requested
**Timestamp**: 2026-08-26T07:28:53Z
**AI Response**: "Generated 5 artifacts in aidlc-docs/inception/application-design/: components.md, component-methods.md, services.md, component-dependency.md, application-design.md. Mermaid in component-dependency.md syntax-validated (10 nodes declared, no undeclared edge targets or style refs, balanced brackets, no odd quotes) with text alternative. Design is grounded in 10 pre-coding measurements rather than assumption. Key design change driven by measurement: answer generation split into two stages (summary 15-30s target, detail on demand) because a single deep question measured 144,951ms — the previously communicated 10-30s estimate was wrong and has been corrected. Requirements traceability table covers FR-1..FR-9 and NFR-1..NFR-7. Four residual risks documented. Awaiting approval."
**Context**: INCEPTION - Application Design, Step 12 approval gate

---
## Application Design — APPROVED
**Timestamp**: 2026-08-26T07:31:14Z
**User Input**: "Approve & Continue"
**AI Response**: "Application Design approved. Proceeding to Code Generation Part 1 (Planning). Unit name = 'reader' (Units Generation was skipped, so this is the single unit)."
**Context**: INCEPTION - Application Design approved; entering CONSTRUCTION phase

---
## Code Generation Part 1 (Planning) — Complete, Approval Requested
**Timestamp**: 2026-08-26T07:32:10Z
**AI Response**: "Created aidlc-docs/construction/plans/reader-code-generation-plan.md — 14 numbered steps with checkboxes, ~12 files, full FR/NFR traceability table. Unit = 'reader'. Code locations documented explicitly: qc_book/reader/ and ~/.qc-book-tutor/ (the latter is outside the workspace by NFR-7 design, not by accident). Tests written in Step 12 using stdlib unittest only (no external test framework installed in qc_env; PBT extension disabled so no property-based tests). Tests are authored here but executed in Build and Test. Awaiting explicit approval of the full plan before generating any code."
**Context**: CONSTRUCTION - Code Generation Part 1, approval gate

---
## Code Generation Part 1 — APPROVED
**Timestamp**: 2026-08-26T07:48:11Z
**User Input**: "Continue to Next Stage"
**AI Response**: "Plan approved. Executed Part 2 (Generation), all 14 steps."
**Context**: CONSTRUCTION - Code Generation Part 1 approved

---

## Code Generation Part 2 — Complete, Approval Requested
**Timestamp**: 2026-08-26T07:48:11Z
**AI Response**: "All 14 steps executed and marked [x]. Created reader/{server.py,index.html,app.js,style.css,start.sh,test_server.py,README.md}, reader/vendor/katex/ (592KB), and ~/.qc-book-tutor/{CLAUDE.md,ask.sh,schema-summary.json,schema-detail.json}.

TWO REAL DEFECTS FOUND AND FIXED BY RUNNING THE CODE, not by reading it:
(1) ask.sh inherited the caller's cwd — no 'cd $TUTOR'. Invoked from the project directory, claude's cwd landed inside the project tree and the AI-DLC CLAUDE.md loaded, defeating NFR-7 entirely. The earlier 20.5s summary measurement was taken in that broken state and is void. Fixed with 'cd $TUTOR' at the top; re-measured at 25.0s.
(2) --session-id cannot be reused — second call failed instantly with 'Session ID ... is already in use'. It CREATES a session; continuation requires --resume. Q2 (context continuity) was completely non-functional. Fixed with a marker file selecting --session-id on first use and --resume after, plus one automatic fallback to the opposite flag when marker and actual state disagree.

MEASURED: summary 25.0s (target 15-30s met), detail 2m52s producing 6,406 chars citing book pp.251-255.

STATIC CHECKS PASSED: py_compile + import for server.py/test_server.py, bash -n for start.sh/ask.sh, node --check for app.js. Unit tests written but NOT YET RUN — deferred to Build and Test per the approved plan."
**Context**: CONSTRUCTION - Code Generation Part 2, approval gate

---
## Code Generation Part 2 — APPROVED
**Timestamp**: 2026-08-26T07:54:10Z
**User Input**: "Continue to Next Stage"
**AI Response**: "Code approved. Proceeding to Build and Test."
**Context**: CONSTRUCTION - Code Generation approved

---

## Build and Test — Complete, Approval Requested
**Timestamp**: 2026-08-26T07:54:10Z
**AI Response**: "Created 5 documents in aidlc-docs/construction/build-and-test/.

UNIT TESTS: 15 passed, 0 failed (0.007s).

INTEGRATION TESTS IT-1..IT-8: all pass. IT-3 FAILED FIRST and exposed a real defect: /api/page/252/words died with 'ParseError: not well-formed (invalid token): line 14, column 82'. Root cause — pdftotext -bbox emits math glyphs as XML-1.0-illegal control characters (\x04 etc), NOT as empty elements as the design document claimed. They only LOOKED empty in the terminal. ET.fromstring rejected the entire document. The unit test missed it because the fixture was hand-written clean XML. Fixed by stripping illegal chars before parsing; added a regression test whose fixture contains real control characters. After fix: 494 words, pageWidth 637.2, first word '252' re-confirming the +34 offset, no control chars remaining.

QUALITY GATES: QG-1 PASS, QG-2 PASS (14,880 tokens vs 22,759 AI-DLC-loaded / 13,410 bare; plus the worker self-reported its tutor CLAUDE.md rule rather than an AI-DLC rule — double confirmation), QG-3 PASS, QG-4 PASS, QG-5 PASS (24s end-to-end; region-only question with no textual hint — worker read the crop image, correctly identified equation 6.11, cited bookPages [252]), QG-6 PARTIAL (server API verified; browser side unverified), QG-7 PASS.

EXPLICITLY NOT VERIFIED: the browser UI has never been opened. Text-layer alignment, region-selection coordinate mapping, KaTeX rendering, resize, and page-key navigation cannot be confirmed from server response bytes. Listed as a human checklist in build-and-test-summary.md. Test server stopped."
**Context**: CONSTRUCTION - Build and Test, approval gate

---
## Build and Test — Change Request: FR-10 + drag selection fix
**Timestamp**: 2026-08-26T08:17:07Z
**User Input**: "좋아 진행하자. 이것과 별개로 HTML에서 아래로 드래그 하면 빈 화면으로 계속 드래그되는데, 문자가 있는 부분까지만 드래그 되는게 좋을 것 같아" / "그외에 부분은 지금까지는 문제없어 보이는 것 같아"
**AI Response**: "User confirmed the rest of the browser UI works — text-layer alignment, KaTeX, region selection, resize, position restore. QG-6 now fully closed; the human verification checklist from build-and-test-summary.md is satisfied.

DRAG FIX: diagnosed with real data rather than guessing. Words occupy only 87% of page height (maxY 735 of pageHeight 843.8); the bottom 13% is page margin. #textLayer carried 'user-select: text' as a whole, so dragging the empty margin selected the entire layer box. Fixed by moving selectability down to the word spans only (user-select: none on #pageScroll and #textLayer, text on span), with -webkit- prefixes.

FR-10 PROGRESS DISPLAY — implemented in three stages, each driven by measurement:
1. Verified stream-json works alongside --json-schema; tool_use events carry full input including pages=286.
2. Switched ask.sh to --output-format stream-json --verbose; server.py now uses Popen and parses the stream live, translating tool calls to Korean labels via describe_tool() (it converts pdf page back to book page using the offset it already owns).
3. FIRST MEASUREMENT EXPOSED A GAP: progress did arrive live (steps at 12s/18s/33s, no buffering) BUT then froze on 'reading page 262' from 33s to 189s — 156 seconds — because the model spends the long tail composing the answer with no tool calls. A prettier label for the same frozen screen would not have solved the user's complaint. Added --include-partial-messages and stream_event handling: content_block_start sets an activity ('생각 정리 중' / '답변 작성 중'), content_block_delta carries estimated_tokens. Writes throttled to 2s since deltas arrive dozens per second.

RE-VERIFIED: display now changes every few seconds throughout. Longest remaining static gap is ~33s (a tool executing, which emits no events) and the elapsed counter still ticks through it. Final detail answer: 247,902ms, 7,887 chars, bookPages [248,269,270,271,272], activity correctly cleared on completion.

Unit tests still 15/15. Syntax checks pass. FR-10 added to requirements.md."
**Context**: CONSTRUCTION - Build and Test, change request implemented and verified

---
## Build and Test — Change Request: 문서 헛스크롤 결함
**Timestamp**: 2026-08-26T08:27:26Z
**User Input**: "그리고 웹화면 스크롤 이슈가 여전히 남아있어"
**AI Response**: "The earlier user-select change addressed selection, not scrolling — a misread of the original report. This time measured instead of guessing: drove real Chrome headless via the DevTools Protocol (node built-in WebSocket, no external packages) and read layout numbers directly.

MEASURED: documentElement scrollHeight 13,493 vs clientHeight 813 — the document scrolled 12,680px into nothing. body, #app, #book, #qa all reported 0 overflow; only the document root was inflated, and its height matched #thread's content height (13,609px).

ROOT CAUSE: KaTeX renders a hidden accessibility copy of every formula as <span class='katex-mathml'> with position: absolute + clip. An absolutely positioned element resolves its containing block to the nearest POSITIONED ancestor; #thread had no position, so the containing block became the initial containing block (the document). Such elements are not clipped by an intervening overflow:auto ancestor, so every formula deep in the conversation extended the document's scrollable height. 364 formulas were rendered on the page.

FIX: position: relative on #thread and .qaItem. Re-measured: documentScrollsBy 12,680 -> 0. Page area (315px) and thread now scroll only within themselves.

REGRESSION GUARD: added reader/check_layout.mjs — six assertions over real Chrome metrics (document/body scroll, horizontal overflow, text-layer extent vs image bounds, text layer populated). REVERSE-VERIFIED by temporarily removing position:relative and re-running: it reports documentScrollsBy=12680 and exits 1. Confirms the guard actually catches this regression rather than merely passing.

This class of defect is invisible to both server-response checks and Python unit tests. Documented as IT-9; noted the limitation in unit-test-instructions.md; added the run command to README.md."
**Context**: CONSTRUCTION - Build and Test, second change request resolved

---
## Test Debt Repaid — describe_tool coverage
**Timestamp**: 2026-08-26T08:40:20Z
**User Input**: "FR-10을 추가하면서 describe_tool()에 테스트를 안 붙였습니다 -> 부탁해"
**AI Response**: "Added TestDescribeTool — 18 tests, total 15 -> 33. The function matters because it performs the SECOND offset conversion in the codebase (pdf page back to book page); the first one was already pinned but this one was introduced by the FR-10 change with no coverage.

Two complementary styles were used deliberately: hardcoded anchors verified by eye (book 6->40, 166->200, 252->286) and a round-trip check against to_pdf_page. Changing only the constant keeps the round-trip self-consistent, so the anchors catch it; changing only the conversion logic is caught by the round-trip. Inputs use shapes actually observed in the live stream (quoted nc.sh find piped to head, pages as int and as range string, crop paths).

MUTATION-VERIFIED rather than assumed: deliberately broke the code four ways and confirmed the suite fails each time — sign flip in the inverse conversion (6 failures), offset constant 34->33 (6), returning a string instead of None for unknown tools (1), removing crop detection (1). Restored: 33 pass. Passing tests are not evidence of regression detection; this is.

Docs updated: unit-test-instructions.md (coverage table + mutation-check section), code-summary.md, build-and-test-summary.md, README.md."
**Context**: CONSTRUCTION - Build and Test, test coverage gap closed

---
## Scope Addition — FR-11/12/13 (search, TOC, question anchoring)
**Timestamp**: 2026-08-26T08:43:51Z
**User Input**: "B — 테스트 + 검색/목차까지 지금 진행. 그리고 특정페이지에서 했던 질문들을 특정 페이지로 이동하면 해당 질문만 보이게 하는 기능이 있었으면 좋겠어.  단위가 페이지가 아니라 세부 쳅터이면 더 좋겠다. 어떻게 생각해?  여러가지 질문이 있을 것 같아. 특정 페이지에 대한 질문, 특정 챕터에 대한 질문 등"
**AI Response**: "Agreed with the user's instinct that page is the wrong grouping unit, with evidence: Grover iteration spans pp.250-255, so a question asked on p.252 disappears when returning to p.251 despite being the same material. Page breaks are typesetting artifacts; section breaks are semantic.

But reframed the design: 'which unit' is the wrong question. Sections nest (p.252 in 6.1.3 in 6.1 in ch.6), so storing ONE anchor yields every level free. The feature is a LENS SELECTOR (page / section / chapter / all, default section), not a fixed unit. This also answers the user's own observation that questions come in different kinds — a fixed unit misfiles cross-cutting questions ('difference between Grover and Shor') under wherever the reader happened to be standing; a lens just widens.

Additional proposal: index by answer evidence too. Answers already return bookPages, so a question asked on p.252 whose answer cited pp.250-262 should surface while reading p.258. Free with existing data.

Decided to DERIVE section from bookPage via the TOC index rather than storing it on the question — keeps a single source of truth and retro-fits the 4 existing questions with no migration.

VERIFIED THE DATA BEFORE PROMISING: wrote and ran a TOC parser against refs/toc-raw.txt. 233 entries (12 chapters / 65 sections / 156 subsections), page numbers monotonically increasing, p.252 resolves to '6.1.3 Geometric visualization' exactly. Found an edge case the first parse missed: appendices use different numbering ('Appendix 1: ... 608', 'A2.1.1 Generators 611') and without handling them every page past 593 wrongly mapped to 12.6.5. Also found titles wrap across lines ('5.4 General applications of the quantum Fourier' / 'transform 234'), so the parser must join continuation lines.

FR-11, FR-12, FR-13 added to requirements.md. All three share one TOC index."
**Context**: CONSTRUCTION - scope addition after Build and Test

---
## FR-11/12/13 — Implemented and Verified
**Timestamp**: 2026-08-26T08:50:37Z
**User Input (mid-turn)**: "내 우려사항은 pdf를 읽다보면 질문이 계속 쌓일텐데, 특정 페이지로 돌아갔을때 나의 질의 사항을 찾기가 어려울까봐 그래"
**AI Response**: "The stated concern is exactly the design driver, and it showed that filtering alone is insufficient — the reader also has to SEE where questions exist without remembering. Added question-count badges on the TOC in response.

BUILT: reader/toc.py (shared index for all three features), /api/toc and /api/search endpoints, TOC sidebar, search panel, and the lens filter.

TOC PARSING — three real edge cases found by inspecting the data, not assumed:
1. Titles wrap across lines ('5.4 General applications of the quantum Fourier' / 'transform 234') — continuation lines must be joined.
2. Appendices use different numbering ('Appendix 2: Group theory', 'A2.1.1 Generators'); without handling them every page past 593 mapped wrongly to 12.6.5.
3. The original toc-raw.txt only covered pdf pages 6-16, truncating the TOC mid-appendix. Re-extracted 6-17, which also surfaced unnumbered top-level entries (Bibliography 649, Index 665) — without those, every page past 649 mapped to the last appendix.
Final index: 254 entries (20 top-level / 72 sections / 162 subsections), monotonic, p.252 -> '6.1.3 Geometric visualization' exactly.

BROWSER-VERIFIED via CDP: TOC renders 254 entries with badges (ch.6 = 5 questions, 6.1.3 = 2), current position highlighted. Lens on p.252: page 3/5, section 3/5, chapter 5/5, all 5/5 — the page lens showing 3 rather than 2 confirms evidence-page indexing works (a third question cites p.252 in its answer). Search 'Schmidt decomposition' returns 12 hits with section labels, p.109 -> 2.5.

TESTS: 54 unit tests (33 -> 54; new TestSearchBook 7, test_toc.py 14). Layout check extended to 9 assertions including TOC load and lens presence; caught its own bug during development (window.tocItems is undefined because a 'let' declaration does not create a window property).

Docs updated: reader/README.md gained a '내 질문 다시 찾기' section explaining why section is the default lens; README.md tree, metrics, limitations, and FR range."
**Context**: CONSTRUCTION - FR-11/12/13 complete

---
## FR-12 refinement — side panel no longer covers the page
**Timestamp**: 2026-08-26T09:23:39Z
**User Input**: "좋은 것 같은데 목차포함한 탭이 감춰지는 기능도 있었으면 좋겠어. 지금은 해당 탭이 본문을 가리고 있어"
**AI Response**: "Hiding already existed (T / Esc / toggle / close button); the real complaint was the panel OVERLAYING the text. Changed it from position:absolute to an in-flow flex sibling inside a new #bookBody row, so opening it pushes the page aside instead of covering it. Measured: closed image left=16 width=820; open panel occupies 0-300, image left=316 width=535, overlaps=false; closing restores 820.

Also added: auto-close after choosing a TOC/search entry (with a '고정' checkbox to keep it open), and a redraw of the transparent text layer on every panel toggle — without it the image resizes while the layer keeps old coordinates and drag selection silently misaligns.

FIXED A SECOND BUG FOUND IN THE SCREENSHOT: the TOC did not scroll to the current position in a 254-entry list. Cause was the selector '.toc-item.here:last-of-type', which means 'last div among siblings', not 'last .here' — it matched nothing. Replaced with an explicit last-of-collection. Verified: at p.252 the chain 6 / 6.1 / 6.1.3 is highlighted and 6.1.3 is scrolled into view (scrollTop 2604, visible).

THE LAYOUT CHECK BROKE ITSELF: adding the panel test inline made '텍스트 레이어가 생성되었다' fail with 0 spans, because openSide() redraws the layer asynchronously and the measurement landed mid-redraw. Separated measurement from mutation — the main probe is now side-effect free and the panel test runs as its own step after waiting for the redraw. Added a 12th assertion '패널 토글 후 텍스트 레이어가 다시 그려진다' to guard the misalignment regression.

Final: 54 unit tests pass, 12 layout assertions pass."
**Context**: CONSTRUCTION - FR-12 refinement

---

## FR-1 revised — continuous scroll
**Timestamp**: 2026-08-26T09:54:20Z
**User Input**: "지금은 PDF파일 페이지를 직접 클릭으로 하위 페이지로 이동하는데, 이걸 스크롤다운 하는 기능도 추가해줄 수 있을까? 자연스럽게 앞뒤 페이지를 함께 볼 수 있으면 좋을 것 같아"
**User Input (mid-turn)**: "스크롤이 걸쳐있는 상태에서 질의를 하면 어떤 페이지의 질문이라고 판단하게 되는거야?"
**AI Response**: "Rewrote the book pane from single-page swapping to continuous scroll.

VERIFIED PAGE UNIFORMITY FIRST, because the whole layout math depends on it: sampled 45 pages. Rendered sizes are uniform at 1328x1758 EXCEPT pdf page 1 (the cover) at 1005x1545. So boxes get a default aspect and self-correct when the image loads — only the cover shifts, negligible. Note pdfinfo reports ~482x741pt for every page while pdftoppm and pdftotext -bbox both produce 637x843 for content pages; the render is what matters here, so the aspect is taken from the actual PNG.

DESIGN: 710 fixed-height placeholder boxes give the scrollbar a true full-book length; an IntersectionObserver fills only boxes near the viewport and empties the rest. Measured: scrollHeight 797,362px with only 3-4 images in the DOM at any time.

THE STRADDLE QUESTION (asked mid-turn) exposed a weak rule. The original 'page whose center is nearest the viewport center' flips arbitrarily at the exact half-and-half moment. Changed to 'page with the largest visible area', which matches the intuition of 'the page I am mostly looking at'. Selection still wins over both: if the reader dragged a sentence or a region, the question anchors to THAT page even when the viewport is centered elsewhere. Verified at 30/50/70% straddle positions — all resolve to 252 with the correct hint text. The decision is always visible (green outline on the current box, plus the composer hint).

ADDED zoom (40-140%) because at readable width a full page is taller than the viewport, so two pages cannot both fit. At 60% both p.252 and p.253 are visible at once with the boundary marker between them — screenshot-confirmed.

REGRESSION CAUGHT DURING THE REWRITE: the large block replacement silently deleted clearSelection, the selectionchange handler, setupRegionSelect, toggleRegionMode and renderChips — node --check still passed because the syntax stayed valid. Found by listing defined functions and diffing against expected. Restored all five, adapted to per-page boxes.

check_layout.mjs updated for the new DOM (it referenced #pageImg / #textLayer which no longer exist) and grew to 14 assertions, adding 'all page slots exist' and 'offscreen pages are freed from memory'.

54 unit tests pass; 14 layout assertions pass."
**Context**: CONSTRUCTION - FR-1 revised to continuous scroll

---

## Bug fix — TOC navigation did nothing
**Timestamp**: 2026-08-26T10:06:47Z
**User Input**: "지금 사이즈 좋은것 같아. 그리고 목차에서 특정 챕터 골라도 그페이지로 이동이 안되는 것 같아"
**AI Response**: "Zoom sizing confirmed good by the user. Fixed the navigation bug.

CAUSE: goto() scrolled correctly, then the panel closed, which widened the page area and recomputed the height of all 710 boxes — invalidating the scroll offset that had just been set. In continuous scroll, changing the width changes the entire coordinate system. Three more sites had the same latent defect: panel toggle while reading, divider drag, and window resize all silently moved the reader to a different page.

FIX: relayoutKeeping() restores the current page after any relayout; applied at all four sites. TOC clicks additionally close the panel first so the layout is settled before navigating.

VERIFIED all four entry points: TOC (chapter 6->248, chapter 11->500, section 2.5->109, appendix A2.1->610), pinned mode (keeps panel open, still navigates to 399), search result (->109), evidence badge (->252), and window resize 1500->1100px preserving p.300.

REVERSE-VERIFICATION CORRECTED A FALSE GUARD: the first mutation attempt (swapping the click order back) PASSED, which would have left a regression check that does not actually check anything — openSide() already restores position, so the ordering was secondary. Mutating the real fix instead (removing position restoration) made it fail with '목차 p.248 -> 도착 p.139'. A mutation that passes is evidence the guard is absent, not that the code is safe.

check_layout.mjs now has 15 assertions. 54 unit tests pass. Documented as IT-10."
**Context**: CONSTRUCTION - continuous scroll bug fix

---

## User Confirmation — TOC navigation
**Timestamp**: 2026-08-26T10:13:46Z
**User Input**: "목차 이동 확인했어, 잘 되네"
**AI Response**: "Confirmed by user in the browser. All change requests from this session are implemented and verified. Build and Test remains the open approval gate; Operations is a placeholder, so approval closes the workflow."
**Context**: CONSTRUCTION - Build and Test, awaiting final approval

---
## Build and Test — APPROVED / Workflow Complete
**Timestamp**: 2026-08-26T10:19:42Z
**User Input**: "Approve & Continue"
**AI Response**: "Build and Test approved. Operations is a placeholder with no deployment or monitoring work in scope for a local personal tool, so the AI-DLC workflow closes here. Final state: FR-1..FR-13 and NFR-1..NFR-7 delivered; 54 unit tests, 15 browser layout assertions, IT-1..IT-10 integration procedures documented; three known limitations recorded in README. aidlc-state.md marked COMPLETE."
**Context**: OPERATIONS - workflow complete

---
