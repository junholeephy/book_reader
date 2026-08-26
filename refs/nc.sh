#!/bin/bash
# 책 조회 헬퍼. 경로와 오프셋은 프로젝트 루트의 config.json 에서 읽는다.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="$ROOT/config.json"
[ -f "$CFG" ] || { echo "config.json 이 없습니다. ./setup.sh <PDF> 를 먼저 실행하세요." >&2; exit 1; }
read -r PDF OFFSET <<< "$(python3 -c "
import json;c=json.load(open('$CFG'));print(c['pdf'], c['pageOffset'])")"
TXT="$ROOT/refs/book.txt"

case "$1" in
  find)                     # nc.sh find <regex>  — 책 페이지 번호와 함께 표시
    shift
    awk -v pat="$*" -v off="$OFFSET" 'BEGIN{RS="\f"}
      $0 ~ pat {
        printf "=== book p.%d (pdf p.%d) ===\n", NR-off, NR
        n=split($0, L, "\n")
        for(i=1;i<=n;i++) if (L[i] ~ pat) print "   " L[i]
      }' "$TXT"
    ;;
  page)                     # nc.sh page <책페이지> [끝페이지]
    a=$(( $2 + OFFSET )); b=$(( ${3:-$2} + OFFSET ))
    pdftotext -f $a -l $b "$PDF" -
    ;;
  layout)                   # 레이아웃 보존 (표에 유용)
    a=$(( $2 + OFFSET )); b=$(( ${3:-$2} + OFFSET ))
    pdftotext -layout -f $a -l $b "$PDF" -
    ;;
  pdfpage)                  # 책 페이지 -> PDF 페이지
    echo $(( $2 + OFFSET ))
    ;;
  *) echo "usage: nc.sh find <regex> | page <bookpage> [end] | layout <bookpage> [end] | pdfpage <bookpage>" ;;
esac
