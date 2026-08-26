# 고지 (Notices)

## 1. 이 도구는 어떤 책도 포함하지 않습니다

`book_reader` 는 **읽는 도구일 뿐** 읽을거리를 제공하지 않습니다.
저장소 어디에도 책의 본문·목차·페이지 이미지가 들어 있지 않습니다.

PDF 는 **사용자가 직접 준비**해야 하며, 그에 대한 정당한 권리(구매·구독·이용 허락 등)를
가지고 있어야 합니다.

## 2. PDF 에서 만들어지는 것들 — 전부 로컬에 머뭅니다

`setup.sh` 와 실행 중에 다음이 생성됩니다. **모두 저작물의 파생물이며 `.gitignore` 대상**입니다.

| 경로 | 무엇 |
|---|---|
| `refs/book.txt` | 책 전문 추출 텍스트 |
| `refs/toc-raw.txt` | 목차 |
| `cache/pages/*.png` | 렌더된 페이지 이미지 |
| `qa/crops/*.png` | 잘라낸 지면 일부 |
| `qa/history.md`, `qa/answers/*` | 책 내용을 인용한 답변 |
| `config.json` | PDF 경로 등 개인 환경 |

이것들을 **커밋하거나 재배포하지 마십시오.** 개인 학습 용도로만 쓰십시오.

### 커밋 전 확인

`.gitignore` 가 실제로 먹는지 확인하는 습관을 권합니다.

```bash
git check-ignore -v refs/book.txt cache/pages/1.png qa/state.json config.json
```

> **주의**: `.gitignore` 는 `#` 을 **줄 맨 앞에서만** 주석으로 봅니다.
> `qa/    # 질문 기록` 처럼 뒤에 주석을 달면 그 줄 전체가 패턴이 되어 **아무것도 걸러지지 않습니다.**
> 이 저장소를 만들 때 실제로 겪은 일이라, 주석은 전부 별도 줄에 두었습니다.

## 3. 답변에 포함되는 인용

답변은 책의 문장·수식을 인용하고 페이지 번호를 밝힙니다.
개인 학습 범위의 인용을 전제로 하며, **답변을 모아 배포하는 용도로 쓰지 마십시오.**

## 4. 제3자 구성 요소

| 구성 요소 | 라이선스 | 이 저장소와의 관계 |
|---|---|---|
| [KaTeX](https://katex.org) | MIT | `setup.sh` 가 npm 레지스트리에서 내려받아 `reader/vendor/` 에 둡니다. **저장소에는 포함되지 않습니다** (gitignore) |
| [Poppler](https://poppler.freedesktop.org) (`pdftoppm`, `pdftotext`, `pdfinfo`) | GPL-2.0 | 외부 명령으로 **호출만** 합니다. 링크하지 않으므로 이 저장소의 코드에 GPL 의무가 전이되지 않습니다. 별도로 설치해야 합니다 (`brew install poppler`) |
| [Claude Code](https://claude.com/claude-code) | Anthropic 이용약관 | 답변 생성에 `claude` CLI 를 호출합니다. 사용자 본인의 계정과 약관이 적용됩니다 |
| `.aidlc-rule-details/` | 표기 없음 | AWS AI-DLC 워크플로 규칙. 이 저장소가 저작권을 주장하지 않으며 MIT 적용 대상이 아닙니다. 원저작자의 조건을 따릅니다 |

## 5. 보증 없음

이 도구는 개인 학습용으로 만들어졌습니다. 답변은 LLM 이 생성하며 **틀릴 수 있습니다.**
중요한 내용은 반드시 원문을 직접 확인하십시오.
