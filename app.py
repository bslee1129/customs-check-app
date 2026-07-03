"""
AI 위해식품 스마트 검사관 - 초상세 주석·인수인계판
===================================================

이 파일은 실제 실행 기능을 유지하면서, 비개발자·초급 개발자·후임 담당자도
전체 처리 흐름과 수정 지점을 이해할 수 있도록 설명을 대폭 확장한 버전입니다.

===============================================================================
1. 프로그램의 역할
===============================================================================
사용자가 휴대전화에서 제품 전면, 후면, 성분표, 바코드 사진을 업로드하면 다음을 수행합니다.

1) 업로드 이미지를 OCR에 적합한 크기와 색상 형식으로 전처리합니다.
2) Gemini 멀티모달 모델에 여러 사진을 한 번에 전달합니다.
3) 브랜드, 제품명, 번역명, 바코드, 성분명, 포장 특징을 JSON으로 추출합니다.
4) OCR 결과를 불법의약품 DB의 제품명·바코드·성분명과 단계적으로 비교합니다.
5) 강한 식별 근거와 약한 후보 근거를 구분해 오탐을 줄입니다.
6) 판정, DB 상세정보, 성분표, 현품 사진, DB 원본 사진을 한 화면에 표시합니다.
7) 결과를 Streamlit 세션에 누적하고 필요 시 이메일로 발송합니다.

===============================================================================
2. Streamlit 실행 특성
===============================================================================
Streamlit은 일반적인 데스크톱 프로그램처럼 한 번 실행되고 계속 대기하는 구조가 아닙니다.
버튼 클릭, 파일 업로드, 입력값 변경이 발생할 때마다 이 파일을 위에서 아래로 다시 실행합니다.

따라서 다음 데이터는 st.session_state에 보관합니다.

- history:
  이미 완료된 검사 결과 목록입니다. rerun 후에도 화면에 계속 표시됩니다.

- uploader_id:
  파일 업로더의 key에 사용하는 번호입니다.
  검사가 끝난 뒤 번호를 증가시키면 이전에 선택한 파일이 업로더에서 초기화됩니다.

- _last_gemini_model_used:
  가장 최근 OCR에 성공한 실제 Gemini 모델명입니다.

- _gemini_attempt_log:
  기본 모델과 대체 모델의 호출 성공·실패 내역을 기록합니다.

===============================================================================
3. OCR 모델 호출 순서
===============================================================================
기본 모델:
- gemini-3.5-flash

자동 대체 모델:
1. gemini-3-flash-preview
2. gemini-2.5-flash
3. gemini-3.1-flash-lite
4. gemini-2.5-flash-lite

전환 조건:
- 503 UNAVAILABLE, high demand
- 429 rate limit
- timeout, deadline exceeded
- 모델 미지원, 403/404
- JSON 응답 파싱 실패
- API 호출은 성공했지만 제품명·바코드·성분이 모두 비어 있는 응답

기본 모델은 일시 오류일 때 한 번 더 재시도합니다.
대체 모델은 불필요한 지연과 비용 증가를 막기 위해 보통 한 번만 시도합니다.

===============================================================================
4. DB 매칭의 안전 원칙
===============================================================================
오매칭 방지를 위해 강한 식별 정보부터 비교합니다.

1순위: 유효한 바코드 완전 일치
2순위: 정규화 제품명 완전 일치
3순위: 제품명 고유사도 90% 이상
4순위: 구체 성분 일치 + 제품명 보조 검증

중요:
- 물, 정제수, 카페인, 젤라틴, 비타민 등 흔한 성분은 단독 매칭 근거에서 제외합니다.
- 성분이 같더라도 OCR 제품명과 DB 제품명이 명확히 다르면 DB 행을 확정하지 않습니다.
- 예: OCR은 EVP 3D인데 DB 후보가 orange +인 경우 DB 상세정보를 연결하지 않습니다.
- 반대로 OCR이 "Sleep & Slim"처럼 브랜드를 빠뜨렸고 DB가
  "LONLIFE Sleep & Slim"인 경우에는 핵심 단어 배열이 완전히 같으므로
  브랜드 접두어 생략형 제품명 일치로 우선 연결합니다.
- 제품명 불일치 상태에서는 성분 후보만 안내하고 '정밀 확인 필요'로 처리합니다.

===============================================================================
5. 판정 코드
===============================================================================
금지:
- 유효 바코드 완전 일치
- 제품명 완전 일치
- 강한 식별 근거로 DB 위해물품이 확정된 경우

제한A:
- 제품명 고유사도 후보
- 성분 일치 후보
- 제품명 또는 바코드 완전 일치가 아니어서 정밀 확인이 필요한 경우

제한B:
- 제품명, 바코드, 성분을 모두 읽지 못한 경우
- 사진 재촬영 또는 수기 확인이 필요한 경우

승인:
- 현재 DB에서 직접 일치하거나 유의미한 후보가 없는 경우
- 단, 최종 통관 판단은 현장 세관공무원이 수행합니다.

===============================================================================
6. 이미지 처리
===============================================================================
OCR 전송 이미지:
- 업로드 사진은 PIL Image로 읽습니다.
- 최대 크기로 축소하여 토큰·전송량·처리 시간을 줄입니다.
- RGB로 변환한 뒤 JPEG 바이트 Part로 Gemini에 전달합니다.

화면 비교 이미지:
- 현품 사진과 DB 사진은 동일한 288px 정사각형 카드에 표시합니다.
- 원본 비율은 object-fit: contain으로 유지합니다.
- 사진이 여러 장이면 한 줄에 배치하고 좌우 스크롤합니다.

===============================================================================
7. JSON 오류 방어
===============================================================================
Gemini가 항상 완전한 JSON을 반환한다고 가정하지 않습니다.

파싱 순서:
1) response.parsed 확인
2) response.text를 그대로 json.loads
3) ```json 코드블록 제거
4) 첫 번째 균형 잡힌 JSON 객체 추출
5) 누락 쉼표, 중복 쉼표, trailing comma 보정
6) 정규식으로 브랜드·제품명·바코드·완성된 성분 행 부분 복구
7) 모두 실패하면 다음 Gemini 모델로 자동 전환

===============================================================================
8. 필요한 파일
===============================================================================
- app.py
  Streamlit Cloud에서 실행되는 메인 코드입니다.

- 불법의약품DB.xlsx
  기본 DB 파일입니다.

- 불법의약품DB.xlsx - Sheet1.csv
  존재하면 Excel보다 먼저 읽는 CSV 대체 파일입니다.

- Emblem_of_the_Korea_Customs_Service.svg.png
  상단 관세청 로고입니다. 없으면 원격 URL을 사용합니다.

- error_log.txt
  API, DB, 메일 오류의 전체 traceback을 기록합니다.

===============================================================================
9. Streamlit Secrets 예시
===============================================================================
GEMINI_API_KEY = "발급받은_API_KEY"
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_FALLBACK_MODELS = "gemini-3-flash-preview,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash-lite"

SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "발신메일주소"
SMTP_PASSWORD = "메일비밀번호"

===============================================================================
10. 유지보수 시 자주 수정하는 위치
===============================================================================
- 사진 비교 크기:
  COMPARE_IMAGE_SIZE_PX

- 기본 OCR 모델:
  OCR_PRIMARY_MODEL

- 대체 모델 순서:
  DEFAULT_GEMINI_FALLBACK_MODELS

- 제품명 별칭:
  normalize_product_name() 내부 alias_map

- 맛·용량·제형 제거 규칙:
  normalize_product_name() 내부 noise_patterns

- 일반 성분 제외 목록:
  COMMON_INGREDIENT_TOKENS

- 제품명 고유사도 확정 기준:
  find_safe_db_match()의 best_fuzzy_score >= 0.90

- 성분 보조 매칭 제품명 기준:
  find_safe_db_match()의 best_ing_product_score >= 0.72

- Gemini 출력 길이:
  build_gemini_generation_config_legacy()의 max_output_tokens

===============================================================================
11. 보안 및 업무상 주의사항
===============================================================================
- GEMINI_API_KEY와 SMTP 비밀번호를 코드에 직접 입력하지 않습니다.
- 반드시 Streamlit Secrets로 관리합니다.
- unsafe_allow_html=True를 사용하는 문자열은 esc()로 이스케이프합니다.
- 외부 DB 이미지 다운로드 시 SSL 검증 비활성화는 제한된 서버 환경을 위한 설정입니다.
- 본 앱 결과는 보조 판단이며 법적·행정적 최종 판정을 자동화하지 않습니다.
"""


# [표준/외부 라이브러리] 화면, 데이터, 이미지, 네트워크, 문자열 처리를 담당합니다.
import streamlit as st          # 웹 UI와 세션 상태 관리
import pandas as pd             # Excel/CSV DB 읽기 및 행 단위 비교
import json                     # Gemini JSON 응답 직렬화/역직렬화
from PIL import Image           # 업로드 이미지 열기, 리사이즈, 포맷 변환
import requests                 # DB 원본 이미지 URL 다운로드
import io                       # 메모리 바이트 버퍼 처리
import urllib3                  # SSL 경고 제어
import time                     # API 재시도 대기 시간
import re                       # 제품명/성분/URL 정규식 처리
import os                       # 로컬 파일 존재 여부 확인
import base64                   # 이미지를 HTML data URL로 변환
import html                     # 사용자/DB 문자열 HTML 이스케이프
import smtplib                  # SMTP 메일 전송
# HTML 검사 리포트를 MIME 형식의 이메일로 구성합니다.
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# [진단/정규화 도구] 예외 추적, 시간 기록, 다국어 정규화, 제품명 유사도 계산에 사용합니다.
import traceback               # 예외의 전체 호출 스택을 error_log.txt에 기록
import datetime                # 오류 발생 시각 기록
import unicodedata             # 전각/반각 및 유니코드 표현 통일(NFKC)
from difflib import SequenceMatcher  # OCR 제품명과 DB 제품명의 문자열 유사도 계산

# [Gemini API] Google GenAI SDK의 클라이언트와 멀티모달 타입을 사용합니다.
from google import genai
from google.genai import types


# ------------------------------------------------------------
# 사진 대조 화면 공통 크기 설정
# - 현품 사진과 DB 원본 이미지를 동일한 카드/이미지 크기로 표시
# - 요청 반영: 기존 96px 대비 3배 크기(288px) 썸네일
# ------------------------------------------------------------
# 현품 사진과 DB 원본 사진 모두 이 값을 사용하므로 두 종류의 사진 크기가 항상 같습니다.
# 화면이 너무 크거나 작으면 이 숫자 하나만 조정하면 됩니다.
# 화면에 표시되는 현품/DB 사진 한 장의 정사각형 기준 크기입니다.
# CSS에서는 이 값을 --thumb-w, --thumb-h로 전달합니다.
# 288 -> 144로 줄이면 절반 크기, 288 -> 384로 늘리면 더 크게 표시됩니다.
# OCR에 보내는 이미지 크기와는 별개이며 API 요금에는 직접 영향을 주지 않습니다.
COMPARE_IMAGE_SIZE_PX = 288

# [보안] 정부 서버 SSL 인증서 미인증 경고 문구 출력 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [설정] 웹 페이지 제목 및 모바일 레이아웃 최적화
# set_page_config는 첫 Streamlit UI 명령 중 하나여야 하므로 상단에서 한 번만 호출합니다.
st.set_page_config(page_title="AI 위해식품 스마트 검사관", layout="centered")

# 모바일 UI 가속 및 결과 화면 가독성 향상을 위한 CSS 주입
st.markdown("""
    <style>
    /* 앱 전체에서 재사용하는 색상 변수 */
    :root {
        --primary: #2563eb;
        --text-main: #1f2937;
        --text-sub: #6b7280;
        --line: #e5e7eb;
        --soft-bg: #f8fafc;
        --card-bg: #ffffff;
        --danger: #ef4444;
        --warning: #f59e0b;
        --success: #10b981;
    }

    /* Streamlit 본문 폭과 상하 여백 */
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2.5rem;
        max-width: 980px;
    }

    /* 사진 업로더와 분석 버튼의 모바일 터치 영역 */
    .stFileUploader {
        padding: 10px;
        background-color: #f8f9fa;
        border-radius: 16px;
        border: 1.5px dashed #93c5fd;
    }
    div[data-testid="stFileUploaderDropzone"] button {
        width: 100% !important;
        height: 58px !important;
        font-size: 17px !important;
        font-weight: 800 !important;
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
        border-radius: 12px !important;
        border: 0 !important;
    }
    .stButton>button {
        width: 100%;
        height: 52px;
        font-size: 17px !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
    }

    /* 관세청 로고와 앱 제목 영역 */
    .app-title-wrap {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        margin: 0 0 8px 0;
        padding: 10px 0 6px 0;
        flex-wrap: nowrap;
        overflow: visible;
        min-height: 50px;
    }
    .app-title-wrap img {
        height: 32px;
        width: auto;
        object-fit: contain;
        flex-shrink: 0;
        margin-top: 4px;
    }
    .app-title-wrap h1, .app-title-text {
        display: block;
        flex: 1 1 auto;
        min-width: 0;
        margin: 0;
        padding: 0;
        font-size: clamp(21px, 4.2vw, 29px);
        font-weight: 850;
        color: #111827;
        line-height: 1.35;
        word-break: keep-all;
        overflow-wrap: break-word;
        white-space: normal;
        overflow: visible;
        letter-spacing: -0.04em;
    }
    .guide-caption {
        color: #6b7280;
        font-size: 0.95rem;
        background: #f8fafc;
        border: 1px solid #edf2f7;
        border-radius: 14px;
        padding: 12px 14px;
        margin: 8px 0 16px 0;
    }

    /* 검사 결과 최상단 요약 카드 */
    .inspection-header {
        border: 1px solid var(--line);
        border-radius: 22px;
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        padding: 20px 22px;
        margin: 22px 0 14px 0;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.07);
    }
    .inspection-topline {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 12px;
    }
    .inspection-title {
        font-size: clamp(25px, 22px + 1.2vw, 38px);
        font-weight: 900;
        color: #111827;
        letter-spacing: -0.055em;
        line-height: 1.08;
        word-break: keep-all;
    }
    .inspection-subtitle {
        margin-top: 6px;
        color: var(--text-sub);
        font-size: 0.96rem;
    }
    .decision-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border-radius: 999px;
        padding: 9px 14px;
        font-weight: 900;
        white-space: nowrap;
        border: 1px solid transparent;
        font-size: 0.98rem;
    }
    .decision-danger { background: #fff1f2; color: #e11d48; border-color: #fecdd3; }
    .decision-warning { background: #fffbeb; color: #b45309; border-color: #fde68a; }
    .decision-success { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
    .mini-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin-top: 14px;
    }
    .mini-stat {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 15px;
        padding: 12px 13px;
        min-height: 70px;
    }
    .mini-label {
        color: #6b7280;
        font-size: 0.78rem;
        font-weight: 750;
        margin-bottom: 5px;
    }
    .mini-value {
        color: #111827;
        font-weight: 850;
        font-size: 0.98rem;
        word-break: break-word;
        line-height: 1.25;
    }
    /* OCR/DB/조치 가이드 공통 카드 */
    .info-card {
        border: 1px solid var(--line);
        border-radius: 18px;
        background: var(--card-bg);
        padding: 16px 17px;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
        margin-bottom: 12px;
    }
    .card-title {
        font-weight: 900;
        color: #111827;
        font-size: 1.03rem;
        margin-bottom: 12px;
        letter-spacing: -0.02em;
    }
    .kv-row {
        display: grid;
        grid-template-columns: 128px minmax(0, 1fr);
        gap: 10px;
        padding: 8px 0;
        border-top: 1px solid #f1f5f9;
        align-items: start;
    }
    .kv-row:first-of-type { border-top: 0; }
    .kv-key {
        color: #64748b;
        font-weight: 800;
        font-size: 0.88rem;
    }
    .kv-value {
        color: #1f2937;
        font-weight: 650;
        word-break: break-word;
        line-height: 1.38;
    }
    .soft-note {
        border-radius: 15px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 12px 14px;
        color: #475569;
        margin: 10px 0;
    }
    .action-list {
        margin: 0;
        padding-left: 1.15rem;
        color: #374151;
        line-height: 1.65;
    }
    .photo-section-title {
        font-size: 1.05rem;
        font-weight: 900;
        color: #111827;
        margin: 6px 0 10px 0;
    }
    .compact-hr {
        margin: 18px 0;
        border: none;
        border-top: 1px solid #e5e7eb;
    }

    /* 현품 사진과 DB 사진을 한 줄 가로 스크롤로 표시 */
    .compare-strip {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        gap: 8px;
        overflow-x: auto;
        overflow-y: hidden;
        padding: 8px 2px 12px 2px;
        margin: 4px 0 12px 0;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: thin;
    }
    .compare-thumb-card {
        flex: 0 0 auto;
        width: var(--thumb-w, 96px);
        min-width: var(--thumb-w, 96px);
        max-width: var(--thumb-w, 96px);
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        background: #ffffff;
        padding: 6px;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
        box-sizing: border-box;
    }
    .compare-thumb-img {
        display: block;
        width: 100%;
        height: var(--thumb-h, 96px);
        min-height: var(--thumb-h, 96px);
        max-height: var(--thumb-h, 96px);
        object-fit: contain;
        border-radius: 9px;
        background: #f8fafc;
    }
    .compare-thumb-caption {
        margin-top: 4px;
        font-size: 0.70rem;
        color: #475569;
        font-weight: 800;
        text-align: center;
        line-height: 1.2;
        word-break: keep-all;
    }
    .compare-thumb-link {
        min-height: 13px;
        margin-top: 2px;
        font-size: 0.68rem;
        text-align: center;
    }
    .compare-thumb-link a {
        color: #2563eb;
        text-decoration: none;
        font-weight: 800;
    }

    div[data-testid="stTabs"] button {
        font-weight: 800;
        border-radius: 10px 10px 0 0;
    }

    @media (max-width: 720px) {
        .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
        .mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .kv-row { grid-template-columns: 92px minmax(0, 1fr); }
        .inspection-header { padding: 16px 15px; border-radius: 18px; }
        .inspection-title { font-size: 28px; }
    }


    /* ---------------- 모바일 현장 사용 최적화 ---------------- */
    .mobile-upload-card {
        border: 1px solid #dbeafe;
        background: linear-gradient(180deg, #eff6ff 0%, #ffffff 100%);
        border-radius: 18px;
        padding: 14px;
        margin: 14px 0 12px 0;
        box-shadow: 0 8px 24px rgba(37, 99, 235, 0.08);
    }
    .mobile-upload-title {
        font-size: 1.1rem;
        font-weight: 900;
        color: #1e3a8a;
        margin-bottom: 8px;
        letter-spacing: -0.03em;
    }
    .mobile-upload-hint {
        color: #475569;
        font-size: 0.92rem;
        line-height: 1.45;
        margin-bottom: 10px;
    }
    /* 휴대폰에서도 작게 보이는 성분 표 */
    .ingredient-table-wrap {
        width: 100%;
        overflow-x: auto;
        margin-top: 8px;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        background: #ffffff;
    }
    .ingredient-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        line-height: 1.28;
        table-layout: fixed;
    }
    .ingredient-table th {
        background: #f8fafc;
        color: #334155;
        font-weight: 900;
        padding: 7px 6px;
        border-bottom: 1px solid #e5e7eb;
        text-align: left;
        white-space: nowrap;
    }
    .ingredient-table td {
        color: #1f2937;
        padding: 7px 6px;
        border-bottom: 1px solid #f1f5f9;
        vertical-align: top;
        word-break: break-word;
    }
    .ingredient-table tr:last-child td {
        border-bottom: 0;
    }
    .ingredient-table .col-no { width: 34px; text-align: center; color: #64748b; }
    .ingredient-table .col-raw { width: 35%; }
    .ingredient-table .col-ko { width: 35%; font-weight: 750; }
    .ingredient-table .col-remark { width: 22%; }
    .ingredient-badge {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 6px;
        background: #f1f5f9;
        color: #334155;
        font-size: 0.72rem;
        font-weight: 850;
        white-space: normal;
    }
    .ingredient-badge-danger {
        background: #fff1f2;
        color: #e11d48;
        border: 1px solid #fecdd3;
    }

    @media (max-width: 480px) {
        html, body, [class*="css"] {
            font-size: 16px;
        }
        .block-container {
            padding-left: 0.65rem !important;
            padding-right: 0.65rem !important;
            padding-top: 1.35rem !important;
            padding-bottom: 6rem !important;
            max-width: 100% !important;
        }
        .app-title-wrap {
            gap: 7px;
            margin-top: 0;
            margin-bottom: 8px;
            padding-top: 8px;
            padding-bottom: 6px;
            align-items: flex-start;
            flex-wrap: nowrap;
            min-height: 46px;
            overflow: visible;
        }
        .app-title-wrap img {
            height: 24px;
            margin-top: 5px;
        }
        .app-title-wrap h1, .app-title-text {
            font-size: 1.08rem;
            line-height: 1.42;
            letter-spacing: -0.035em;
            white-space: normal;
            overflow: visible;
        }
        .guide-caption {
            font-size: 0.86rem;
            padding: 10px 11px;
            border-radius: 13px;
            margin-bottom: 10px;
        }
        .inspection-header {
            padding: 14px 12px;
            border-radius: 16px;
            margin: 16px 0 10px 0;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
        }
        .inspection-topline {
            display: block;
        }
        .inspection-title {
            font-size: 1.45rem !important;
            line-height: 1.22;
            letter-spacing: -0.045em;
            word-break: break-word;
        }
        .inspection-subtitle {
            font-size: 0.86rem;
            margin: 6px 0 10px 0;
        }
        .decision-pill {
            width: 100%;
            justify-content: center;
            font-size: 1rem;
            padding: 10px 12px;
            margin-top: 8px;
        }
        .mini-grid {
            grid-template-columns: 1fr !important;
            gap: 8px;
            margin-top: 12px;
        }
        .mini-stat {
            min-height: auto;
            padding: 10px 11px;
            border-radius: 13px;
        }
        .mini-label {
            font-size: 0.77rem;
            margin-bottom: 3px;
        }
        .mini-value {
            font-size: 0.98rem;
        }
        .info-card {
            padding: 13px 12px;
            border-radius: 15px;
            margin-bottom: 10px;
            box-shadow: none;
        }
        .card-title {
            font-size: 1rem;
            margin-bottom: 8px;
        }
        .kv-row {
            display: block !important;
            padding: 9px 0;
        }
        .kv-key {
            font-size: 0.78rem;
            margin-bottom: 3px;
        }
        .kv-value {
            font-size: 0.95rem;
            line-height: 1.42;
        }
        .action-list {
            padding-left: 1.1rem;
            line-height: 1.55;
            font-size: 0.94rem;
        }
        div[data-testid="stTabs"] button {
            font-size: 0.9rem !important;
            padding: 8px 4px !important;
        }
        div[data-testid="stFileUploaderDropzone"] {
            padding: 10px !important;
        }
        div[data-testid="stFileUploaderDropzone"] button {
            height: 54px !important;
            font-size: 1rem !important;
        }
        .stButton>button {
            min-height: 54px !important;
            height: auto !important;
            font-size: 1rem !important;
            border-radius: 14px !important;
        }
        img {
            max-width: 100%;
            height: auto;
        }
        .ingredient-table {
            font-size: 0.74rem;
            min-width: 420px;
        }
        .ingredient-table th,
        .ingredient-table td {
            padding: 5px 5px;
        }
        .ingredient-badge {
            font-size: 0.68rem;
            padding: 2px 5px;
        }
    }



    /* ---------- 제목 잘림 방지 최종 패치 ---------- */
    .app-title-wrap {
        display: grid !important;
        grid-template-columns: 36px minmax(0, 1fr) !important;
        align-items: center !important;
        gap: 10px !important;
        width: 100% !important;
        height: auto !important;
        min-height: 0 !important;
        margin: 10px 0 12px 0 !important;
        padding: 18px 0 14px 0 !important;
        overflow: visible !important;
        box-sizing: border-box !important;
    }
    .app-title-wrap img {
        width: 32px !important;
        height: 32px !important;
        max-height: 32px !important;
        object-fit: contain !important;
        margin: 0 !important;
        align-self: center !important;
    }
    .app-title-text {
        display: block !important;
        width: 100% !important;
        min-width: 0 !important;
        height: auto !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0.24em 0 0.28em 0 !important;
        color: #0f172a !important;
        font-size: clamp(24px, 5.4vw, 34px) !important;
        font-weight: 900 !important;
        line-height: 1.55 !important;
        letter-spacing: -0.045em !important;
        word-break: keep-all !important;
        overflow-wrap: break-word !important;
        white-space: normal !important;
        overflow: visible !important;
        box-sizing: border-box !important;
        transform: none !important;
        -webkit-font-smoothing: antialiased;
    }
    .app-title-line { display: inline; }

    @media (max-width: 480px) {
        .block-container {
            padding-top: 2.4rem !important;
        }
        .app-title-wrap {
            grid-template-columns: 28px minmax(0, 1fr) !important;
            gap: 8px !important;
            padding-top: 20px !important;
            padding-bottom: 14px !important;
            margin-top: 0 !important;
            margin-bottom: 10px !important;
        }
        .app-title-wrap img {
            width: 26px !important;
            height: 26px !important;
            max-height: 26px !important;
        }
        .app-title-text {
            font-size: clamp(21px, 7.2vw, 29px) !important;
            line-height: 1.62 !important;
            padding-top: 0.30em !important;
            padding-bottom: 0.34em !important;
            letter-spacing: -0.05em !important;
        }
        .app-title-line {
            display: block;
        }
    }

    </style>
""", unsafe_allow_html=True)

# 로고와 제목 인라인 배치
logo_path = "Emblem_of_the_Korea_Customs_Service.svg.png"


# -----------------------------------------------------------------------------
# 함수: get_base64_of_bin_file
# 목적: 로컬 로고 파일을 HTML <img> 태그에 직접 넣을 수 있는 Base64 문자열로 변환합니다.
# 입력: bin_file - 읽을 이미지 파일 경로
# 출력: Base64로 인코딩된 문자열
# 주의: 파일이 없으면 호출부에서 원격 GitHub 로고 URL을 대신 사용합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   bin_file: 로컬 파일 시스템에 존재하는 이미지 파일 경로입니다.
# 처리:
#   1. 파일을 바이너리 모드로 읽습니다.
#   2. HTML에 직접 삽입 가능한 Base64 문자열로 인코딩합니다.
# 반환값:
#   data:image/... 접두어를 제외한 순수 Base64 문자열입니다.
# 부작용:
#   없음. 파일을 읽기만 합니다.
# 예외:
#   파일이 없거나 읽기 권한이 없으면 FileNotFoundError/PermissionError가 발생할 수 있습니다.
#   호출부에서는 os.path.exists()를 먼저 확인하므로 일반 운영에서는 예외가 발생하지 않습니다.
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()



# -----------------------------------------------------------------------------
# 함수: split_image_urls
# 목적: DB 셀 하나에 섞여 있는 여러 원본 이미지 URL을 안전하게 분리합니다.
# 처리: 쉼표, 줄바꿈, 세미콜론, 파이프(|)를 모두 구분자로 인정합니다.
# 보정: //로 시작하는 주소는 https:를 붙이고 HTTP/HTTPS 주소만 남깁니다.
# 출력: 검증 가능한 URL 문자열 목록
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   url_data: DB 원본이미지URL 셀 값입니다. 문자열, NaN, None 모두 들어올 수 있습니다.
# 처리:
#   - 빈 값, nan, none, null, '확인 불가'는 빈 목록으로 처리합니다.
#   - 쉼표, 세미콜론, 줄바꿈, 파이프 문자를 URL 구분자로 인정합니다.
#   - //example.com/image.jpg 형태는 https:// 주소로 보정합니다.
#   - http 또는 https로 시작하지 않는 값은 보안과 오류 방지를 위해 제외합니다.
# 반환값:
#   유효한 URL 문자열 목록입니다.
# 주의:
#   URL 존재 여부나 실제 이미지 여부까지 네트워크로 검사하지는 않습니다.
def split_image_urls(url_data):
    """DB의 원본이미지URL 값을 안전하게 URL 목록으로 분리합니다."""
    if pd.isna(url_data):
        return []
    text = str(url_data).strip()
    if not text or text.lower() in ["nan", "none", "null", "확인 불가"]:
        return []

    # 쉼표, 줄바꿈, 세미콜론, 파이프 구분 모두 지원
    candidates = re.split(r"[\n\r,;|]+", text)
    urls = []
    for item in candidates:
        url = item.strip().strip('"').strip("'")
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http://") or url.startswith("https://"):
            urls.append(url)
    return urls


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)

# -----------------------------------------------------------------------------
# 함수: fetch_db_image_bytes
# 목적: 외부 DB 이미지가 브라우저 직접 표시를 차단하는 경우 서버가 대신 내려받습니다.
# 캐시: 24시간 동안 같은 URL을 다시 요청하지 않아 속도와 네트워크 비용을 줄입니다.
# 반환: (이미지 바이트, Content-Type) 튜플
# 주의: 현재 빠른 표시 화면에서는 URL 직접 표시가 기본이며 필요 시 재사용할 수 있습니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   url: 다운로드할 외부 이미지 URL입니다.
# 처리:
#   - 브라우저와 유사한 User-Agent/Accept/Referer 헤더를 사용합니다.
#   - 일부 공공기관·외부 서버가 기본 requests 요청을 차단하는 문제를 줄입니다.
#   - 최대 5초 동안 응답을 기다리고 리다이렉트를 허용합니다.
# 캐시:
#   st.cache_data(ttl=24시간)로 같은 URL 재다운로드를 막습니다.
# 반환값:
#   (응답 바이트, Content-Type) 튜플입니다.
# 실패:
#   HTTP 오류, 연결 오류, timeout은 호출부에서 처리해야 합니다.
def fetch_db_image_bytes(url):
    """원본 DB 이미지를 캐시하여 같은 URL은 다시 다운로드하지 않습니다."""
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    })
    res = session.get(url, timeout=5, allow_redirects=True)
    res.raise_for_status()
    return res.content, res.headers.get("Content-Type", "")



# -----------------------------------------------------------------------------
# 함수: image_to_data_url
# 목적: PIL 이미지를 JPEG로 압축하고 Base64 data URL로 바꿔 HTML 가로 사진 목록에 삽입합니다.
# max_size: 브라우저 전송 전에 축소할 최대 크기
# quality: JPEG 압축 품질. 높을수록 선명하지만 세션 메모리 사용량이 증가합니다.
# 실패 시 빈 문자열을 반환하여 전체 화면 렌더링이 중단되지 않게 합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   image_source: PIL.Image.Image 객체가 예상됩니다.
#   max_size: 브라우저 표시용 변환 전 최대 가로·세로 크기입니다.
#   quality: JPEG 압축 품질입니다.
# 처리:
#   - 원본 객체를 직접 변경하지 않도록 copy()를 사용합니다.
#   - 투명도나 팔레트 이미지도 RGB로 변환합니다.
#   - thumbnail()은 원본 비율을 유지하면서 최대 크기 안에 맞춥니다.
#   - JPEG 바이트를 Base64 data URL로 변환합니다.
# 반환값:
#   성공 시 data:image/jpeg;base64,... 문자열, 실패 시 빈 문자열입니다.
# 메모리:
#   data URL은 세션 메모리를 사용하므로 지나치게 큰 max_size는 피해야 합니다.
def image_to_data_url(image_source, max_size=(900, 900), quality=82):
    """PIL 이미지를 브라우저에서 바로 표시 가능한 data URL로 변환합니다."""
    try:
        img = image_source.copy() if hasattr(image_source, "copy") else image_source
        if not isinstance(img, Image.Image):
            return ""
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(max_size)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""



# -----------------------------------------------------------------------------
# 함수: render_horizontal_image_strip
# 목적: 현품 사진과 DB 원본 사진에 공통으로 사용하는 가로 스크롤 썸네일 UI를 생성합니다.
# items 형식: {"src": 이미지주소, "caption": 설명, "link": 원본링크(선택)}
# 보안: 제목·설명·URL은 esc()를 통해 HTML 특수문자를 이스케이프합니다.
# 모바일: 줄바꿈하지 않고 좌우 스크롤되므로 업로드 수만큼 한 줄에 표시됩니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   items: 각 항목이 src, caption, link를 갖는 dict 목록입니다.
#   title: 사진 구역 제목입니다.
#   empty_message: 표시 가능한 사진이 없을 때 보여줄 문구입니다.
#   item_width_px/item_height_px: 사진 카드와 이미지 표시 영역 크기입니다.
# 처리:
#   - 모든 사진 카드를 하나의 flex 컨테이너에 넣습니다.
#   - flex-wrap: nowrap으로 줄바꿈을 막고 overflow-x: auto로 좌우 스크롤을 허용합니다.
#   - src, caption, link는 esc()로 HTML 이스케이프합니다.
# 부작용:
#   Streamlit 화면에 HTML을 렌더링합니다.
# 주의:
#   src가 빈 항목은 건너뛰며, 모든 항목이 빈 경우 empty_message를 표시합니다.
def render_horizontal_image_strip(items, title, empty_message="표시할 이미지가 없습니다.", item_width_px=COMPARE_IMAGE_SIZE_PX, item_height_px=COMPARE_IMAGE_SIZE_PX):
    """
    사진을 탭/세로 나열 없이 가로 스크롤 줄로 표시합니다.
    item_width_px와 item_height_px를 함께 사용하여 현품 사진과 DB 원본 이미지를 동일한 크기로 맞춥니다.
    """
    st.markdown(f'<div class="photo-section-title">{esc(title)}</div>', unsafe_allow_html=True)
    if not items:
        st.info(empty_message)
        return

    cards = []
    for idx, item in enumerate(items, start=1):
        src = item.get("src", "")
        caption = item.get("caption", f"사진 #{idx}")
        link = item.get("link", "")
        if not src:
            continue
        link_html = f"<a href='{esc(link)}' target='_blank'>원본</a>" if link else ""
        cards.append(
            "<div class='compare-thumb-card'>"
            f"<img class='compare-thumb-img' src='{esc(src)}' alt='{esc(caption)}'>"
            f"<div class='compare-thumb-caption'>{esc(caption)}</div>"
            f"<div class='compare-thumb-link'>{link_html}</div>"
            "</div>"
        )

    if not cards:
        st.info(empty_message)
        return

    html = (
        f"<div class='compare-strip' style='--thumb-w:{int(item_width_px)}px; --thumb-h:{int(item_height_px)}px;'>"
        + "".join(cards)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)



# -----------------------------------------------------------------------------
# 함수: render_user_original_images
# 목적: 사용자가 업로드한 모든 현품 사진을 DB 이미지와 동일한 규격으로 표시합니다.
# 처리: 세션에 저장된 PIL 이미지를 data URL로 바꾼 뒤 공통 가로 목록 함수를 호출합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   user_images: 검사 시 세션에 저장한 PIL 이미지 목록입니다.
# 처리:
#   - 각 PIL 이미지를 data URL로 변환합니다.
#   - 현품 #1, 현품 #2 형태의 캡션을 붙입니다.
#   - DB 이미지와 동일한 COMPARE_IMAGE_SIZE_PX 크기로 렌더링합니다.
# 반환값:
#   없음. 화면 렌더링만 수행합니다.
def render_user_original_images(user_images):
    """내가 촬영한 현품 사진을 등록된 개수만큼 모두 가로로 표시합니다."""
    items = []
    for idx, img in enumerate(user_images or [], start=1):
        data_url = image_to_data_url(img, max_size=(COMPARE_IMAGE_SIZE_PX * 4, COMPARE_IMAGE_SIZE_PX * 4))
        if data_url:
            items.append({"src": data_url, "caption": f"현품 #{idx}"})
    render_horizontal_image_strip(
        items,
        "📸 내가 촬영한 현품 사진",
        empty_message="촬영 사진이 없습니다.",
        item_width_px=COMPARE_IMAGE_SIZE_PX,
        item_height_px=COMPARE_IMAGE_SIZE_PX,
    )



# -----------------------------------------------------------------------------
# 함수: render_db_original_images
# 목적: 매칭된 DB 행의 원본이미지URL을 현품 사진과 동일한 크기의 가로 목록으로 표시합니다.
# 원본 링크: 각 카드 아래의 '원본'을 누르면 외부 이미지 주소를 새 창에서 확인할 수 있습니다.
# key_prefix: 과거 radio 위젯 호환용 인자이며 현재 버전에서는 위젯 key를 만들지 않습니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   url_data: 매칭된 DB 행의 원본이미지URL 셀 값입니다.
#   key_prefix: 이전 radio 위젯 버전과의 함수 호출 호환용이며 현재 렌더링에는 사용하지 않습니다.
# 처리:
#   - 여러 URL을 분리합니다.
#   - 각 URL을 브라우저가 직접 읽도록 src에 설정하여 서버 다운로드 지연을 줄입니다.
#   - 각 카드 아래 원본 링크를 제공합니다.
# 보안:
#   http/https URL만 허용하고 HTML 특수문자를 이스케이프합니다.
def render_db_original_images(url_data, key_prefix=None):
    """DB 등록 원본 이미지를 탭/라디오 없이 가로 썸네일로 빠르게 표시합니다."""
    urls = split_image_urls(url_data)
    if not urls:
        st.info("DB에 등록된 원본 사진 URL이 없습니다.")
        return

    items = []
    for idx, url in enumerate(urls, start=1):
        items.append({"src": url, "caption": f"DB #{idx}", "link": url})

    render_horizontal_image_strip(
        items,
        f"🔗 DB 등록 원본 이미지 ({len(urls)}건)",
        empty_message="DB에 등록된 원본 사진 URL이 없습니다.",
        item_width_px=COMPARE_IMAGE_SIZE_PX,
        item_height_px=COMPARE_IMAGE_SIZE_PX,
    )


if os.path.exists(logo_path):
    img_src = f"data:image/png;base64,{get_base64_of_bin_file(logo_path)}"
else:
    img_src = "https://raw.githubusercontent.com/bslee1129/customs-check-app/main/Emblem_of_the_Korea_Customs_Service.svg.png"

# 모바일 화면 반응형 타이틀 적용 
st.markdown(f"""
    <div class="app-title-wrap">
        <img src="{img_src}" alt="Korea Customs Service logo">
        <div class="app-title-text" role="heading" aria-level="1"><span class="app-title-line">AI 위해식품</span><span class="app-title-line">스마트 검사관</span></div>
    </div>
    <div class="guide-caption">
        💡 <b>[촬영 가이드]</b> 제품의 <b>전면, 후면, 성분표, 바코드</b>가 선명하게 보이도록 여러 장을 한 번에 올려주세요. 검사 기록은 계속 누적됩니다.
    </div>
""", unsafe_allow_html=True)

# 최신 Client 객체 방식의 API 연결 설정
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
client = None

# ------------------------------------------------------------
# OCR 사진 판독용 Gemini 모델 및 자동 대체(fallback) 설정
# ------------------------------------------------------------
# OCR 정확도, 다국어 라벨 인식, 성분표 판독을 우선한 순서입니다.
#
# 기본 모델
#   1) gemini-3.5-flash
#
# 자동 대체 모델
#   2) gemini-3-flash-preview   : 멀티모달/이미지 이해 우선
#   3) gemini-2.5-flash         : 안정적인 멀티모달·대량 처리
#   4) gemini-3.1-flash-lite    : 비용·속도 절약형
#   5) gemini-2.5-flash-lite    : 최종 저비용 대체 모델
#
# API 과부하뿐 아니라 JSON 파싱 실패, 빈 OCR 결과가 발생해도
# 동일 모델 재시도 후 다음 모델로 자동 전환합니다.
# Streamlit Secrets에서 순서를 변경할 수도 있습니다.
# Secrets에 GEMINI_MODEL이 있으면 해당 값을 사용하고, 없으면 gemini-3.5-flash를 기본값으로 사용합니다.
OCR_PRIMARY_MODEL = str(
    st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash")
).strip() or "gemini-3.5-flash"

# 기존 코드와의 호환성을 위해 GEMINI_MODEL 별칭을 유지합니다.
GEMINI_MODEL = OCR_PRIMARY_MODEL

# 기본 모델이 과부하·미지원·불완전 응답일 때 아래 순서대로 자동 전환합니다.
# OCR 정확도를 우선하여 Flash 계열을 Lite 계열보다 앞에 배치했습니다.
# 아래 목록은 OCR 기본 모델이 실패했을 때만 사용됩니다.
# 순서는 정확도·안정성·비용을 함께 고려한 것입니다.
# 모델 ID가 계정/지역에서 지원되지 않으면 _is_model_switch_error()가 다음 모델로 넘깁니다.
# Secrets에 GEMINI_FALLBACK_MODELS를 지정하면 이 기본 목록보다 Secrets 값이 우선합니다.
DEFAULT_GEMINI_FALLBACK_MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

if gemini_key:
    try:
        client = genai.Client(api_key=gemini_key)
    except Exception as e:
        error_details = traceback.format_exc()
        st.error(f"API 키 설정 중 오류가 발생했습니다: {e}")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n[API KEY ERROR] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{error_details}")
else:
    st.error("⚠️ 오른쪽 하단 Manage app -> Settings -> Secrets에 GEMINI_API_KEY를 등록해 주세요.")

# Streamlit은 버튼 클릭마다 스크립트를 위에서부터 다시 실행합니다.
# 따라서 검사 결과와 업로더 초기화 번호를 session_state에 보관해야 기록이 유지됩니다.
if "history" not in st.session_state:
    st.session_state["history"] = []
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0

# --- 유틸리티 함수 모음 ---

# -----------------------------------------------------------------------------
# 함수: normalize_product_name
# 목적: OCR 제품명과 DB 제품명을 같은 비교 규칙으로 변환합니다.
# 핵심 처리: NFKC 유니코드 통일 → 소문자화 → 맛/용량/제형 노이즈 제거 → 문장부호 제거.
# 별칭 지도: 일본어/영문/한글 표기가 크게 다른 동일 제품은 alias_map으로 하나의 값에 맞춥니다.
# 결과값은 화면 표시용이 아니라 DB 비교용 내부 문자열입니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   사람이 보는 제품명이 아니라 '동일 제품인지 비교하기 위한 내부 키'를 생성합니다.
# 입력 예:
#   'EVP 3D Fruit Punch 60 Capsules' -> 맛·용량·제형을 제거한 비교 문자열
# 처리 단계:
#   1. NaN/빈 문자열 방어
#   2. NFKC 유니코드 정규화로 전각·반각 통일
#   3. 소문자 변환
#   4. 다국어 alias_map 적용
#   5. 맛, 용량, 제형 등 비교 방해 요소 제거
#   6. 공백과 특수문자 제거
# 반환값:
#   제품명 비교에만 사용하는 압축 문자열입니다.
# 주의:
#   제거 규칙이 너무 넓으면 서로 다른 제품이 같아질 수 있으므로 noise_patterns 수정 시 테스트가 필요합니다.
def normalize_product_name(text):
    """
    제품명 정규화:
    - 영문/한글/일본어/중국어 혼합 라벨 대응
    - 맛, 용량, 제형 등 DB 매칭에 방해되는 노이즈 제거
    - 전각/반각 문자 통일
    """
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == 'nan':
        return ""

    val = unicodedata.normalize("NFKC", str(text)).lower()

    # 자주 발생하는 다국어 별칭 보정
    alias_map = {
        "メジコンせき止め錠pro": "mediconcoughtabletpro",
        "メジコンせき止め錠プロ": "mediconcoughtabletpro",
        "mediconcoughtabletpro": "mediconcoughtabletpro",
        "medikoncoughtabletpro": "mediconcoughtabletpro",
        "메지콘기침약프로": "mediconcoughtabletpro",
        "메디콘기침약프로": "mediconcoughtabletpro",
    }

    compact = re.sub(r'[\s\-\./:\(\)\+·_\*&%!@#~`=\[\]\{\}\\\|\'\";\?]', '', val)
    if compact in alias_map:
        return alias_map[compact]

    noise_patterns = [
        r'fruit\s*punch', r'blue\s*raz(?:z|zberry)?', r'blue\s*raspberry', r'sour\s*candy',
        r'lemon', r'orange', r'grape', r'berry', r'cola', r'mint', r'flavor(?:ed)?',
        r'\d+g', r'\d+\.?\d*oz', r'\d+\s*mg', r'\d+\s*ml',
        r'\d+\s*capsules?', r'\d+\s*tablets?', r'\d+\s*servings?',
        r'capsules?', r'tablets?', r'powder', r'liquid', r'softgels?',
        r'錠', r'カプセル', r'顆粒', r'液', r'액제', r'정제', r'캡슐', r'과립', r'정'
    ]
    for pattern in noise_patterns:
        val = re.sub(pattern, '', val)

    val = re.sub(r'[\s\-\./:\(\)\+·_\*&%!@#~`=\[\]\{\}\\\|\'\";\?]', '', val)
    return alias_map.get(val, val)



# -----------------------------------------------------------------------------
# 함수: tokenize_text
# 목적: 성분명 문자열을 DB 교차 비교 가능한 단위 토큰으로 분리합니다.
# 염 형태 제거 이유: hydrochloride/HCl/염산염처럼 같은 유효성분의 염 표기 차이를 흡수합니다.
# 반환: 중복이 제거된 성분 토큰 목록
# 주의: 일반 성분 제외 여부는 find_safe_db_match()에서 추가로 판단합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   성분명 문자열을 비교 가능한 개별 토큰 목록으로 변환합니다.
# 처리 단계:
#   - 쉼표, 슬래시, 괄호, 줄바꿈 등으로 분리합니다.
#   - hydrochloride/HCl/염산염 등 염 형태 표현을 제거합니다.
#   - 한글, 영문, 숫자, 일본어, 한자 외 문자를 제거합니다.
#   - 길이 2 미만 토큰은 노이즈로 간주합니다.
# 반환값:
#   입력 순서를 유지하면서 중복을 제거한 토큰 목록입니다.
# 주의:
#   이 함수는 '일반 성분'을 제거하지 않습니다.
#   일반 성분 제외는 find_safe_db_match()에서 COMMON_INGREDIENT_TOKENS로 수행합니다.
def tokenize_text(text):
    """
    성분명 토큰화:
    - 염 형태(hcl, hydrochloride, sulfate 등) 제거
    - 전각/반각 통일
    - 너무 짧은 토큰 제외
    """
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == 'nan':
        return []

    normalized = unicodedata.normalize("NFKC", str(text))
    tokens = re.split(r'[,/\n;\(\)\+·]', normalized)
    salt_words = [
        "hcl", "hydrochloride", "염산염", "염산", "sulfate", "sulphate", "황산염",
        "nitrate", "질산염", "acetate", "아세트산염", "tartrate", "주석산염",
        "maleate", "fumarate", "succinate", "citrate", "phosphate", "인산염",
        "sodium", "calcium", "potassium", "magnesium"
    ]

    cleaned_tokens = []
    for t in tokens:
        c = t.strip().lower().replace(" ", "").replace("-", "")
        for word in salt_words:
            c = c.replace(word, "")
        c = re.sub(r'[^0-9a-z가-힣ぁ-んァ-ン一-龥]', '', c)
        if len(c) >= 2:
            cleaned_tokens.append(c)
    return list(dict.fromkeys(cleaned_tokens))



# -----------------------------------------------------------------------------
# 함수: pil_image_to_gemini_part
# 목적: PIL 이미지를 Google GenAI SDK가 받는 types.Part 이미지 입력으로 변환합니다.
# JPEG quality=90은 작은 글씨 OCR 품질과 전송량 사이의 절충값입니다.
# PIL 객체를 직접 넘기지 않고 바이트 Part로 변환하면 Streamlit Cloud 환경 차이를 줄일 수 있습니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   image: RGB 또는 변환 가능한 PIL 이미지입니다.
# 처리:
#   - 메모리 버퍼에 JPEG quality=90으로 저장합니다.
#   - Google GenAI SDK의 types.Part.from_bytes()로 변환합니다.
# 이유:
#   PIL 객체 직접 전달보다 SDK·배포 환경 차이에 덜 민감합니다.
# 반환값:
#   Gemini contents에 넣을 수 있는 이미지 Part 객체입니다.
# 비용 영향:
#   이 함수의 JPEG 품질과 호출 전 thumbnail 크기가 이미지 입력 토큰·전송 속도에 영향을 줍니다.
def pil_image_to_gemini_part(image: Image.Image):
    """
    PIL 이미지를 Gemini API 멀티모달 입력 Part로 변환.
    PIL 객체를 직접 넘기는 방식보다 Streamlit 배포 환경에서 안정적입니다.
    """
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


# Gemini가 반환해야 하는 OCR 결과의 논리적 구조입니다.
# 현재 SDK 호환 문제로 response_schema에 직접 전달하지는 않지만,
# 프롬프트 설계와 향후 Structured Output 전환 시 기준으로 유지합니다.
OCR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "product_name": {"type": "string"},
        "translated_product_name": {"type": "string"},
        "barcode": {"type": "string"},
        "multilingual_candidates": {
            "type": "array",
            "items": {"type": "string"}
        },
        "translated_ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_name": {"type": "string"},
                    "ko_name": {"type": "string"},
                    "remark": {
                        "type": "string",
                        "enum": ["위해성분 의심", "화학명", "식물명", "일반명", "기타 원료", "확인 불가"]
                    }
                },
                "required": ["raw_name", "ko_name", "remark"]
            }
        },
        "package_features": {"type": "string"}
    },
    "required": [
        "brand",
        "product_name",
        "translated_product_name",
        "barcode",
        "multilingual_candidates",
        "translated_ingredients",
        "package_features"
    ]
}



# -----------------------------------------------------------------------------
# 함수: _gemini_safety_settings
# 목적: 의약품·위해성분 명칭이 위험 콘텐츠로 오인되어 차단되지 않도록 안전 임계값을 설정합니다.
# 이 설정은 업무상 제품 라벨을 판독하기 위한 것이며, 불법행위 안내를 생성하는 용도가 아닙니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   의약품명, 마약류 성분명, 위해성분 문자열이 업무상 OCR 과정에서 차단되지 않게 합니다.
# 반환값:
#   GenerateContentConfig.safety_settings에 전달할 SafetySetting 목록입니다.
# 주의:
#   BLOCK_NONE은 업무상 라벨 인식을 위한 설정입니다.
#   모델에게 불법행위 방법을 생성시키는 용도로 사용해서는 안 됩니다.
def _gemini_safety_settings():
    """Gemini 안전 설정 공통값."""
    return [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]



# -----------------------------------------------------------------------------
# 함수: build_gemini_generation_config_legacy
# 목적: 구버전 google-genai SDK에서도 동작하는 JSON 응답 설정을 구성합니다.
# response_format은 설치 버전에 따라 extra_forbidden 오류가 있어 사용하지 않습니다.
# types.GenerateContentConfig 생성 실패 시 동일 내용을 dict로 반환해 호환성을 높입니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   Streamlit Cloud에 설치된 google-genai 버전 차이와 호환되는 생성 설정을 만듭니다.
# 주요 설정:
#   response_mime_type='application/json':
#       설명문이 아니라 JSON 응답을 우선하도록 요청합니다.
#   max_output_tokens=16384:
#       긴 성분표가 중간에 잘리는 가능성을 낮춥니다.
#   safety_settings:
#       업무상 성분명 차단을 줄입니다.
# 호환 처리:
#   Pydantic 모델 생성이 실패하면 같은 내용을 일반 dict로 반환합니다.
#   response_format은 구버전 SDK에서 extra_forbidden 오류가 발생하므로 사용하지 않습니다.
def build_gemini_generation_config_legacy():
    """
    Streamlit Cloud에 설치된 google-genai 버전과 가장 호환성이 높은 설정입니다.
    response_format은 일부 SDK에서 validation error가 발생하므로 사용하지 않습니다.
    """
    try:
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=16384,
            safety_settings=_gemini_safety_settings(),
        )
    except Exception:
        return {
            "response_mime_type": "application/json",
            "max_output_tokens": 16384,
            "safety_settings": _gemini_safety_settings(),
        }



# -----------------------------------------------------------------------------
# 함수: _get_fallback_models
# 목적: 기본 OCR 모델과 자동 대체 모델을 실제 호출 순서대로 합칩니다.
# Secrets에 사용자가 지정한 순서를 우선하며 빈 값과 중복 모델은 제거합니다.
# 반환 순서가 곧 장애 발생 시 다음 모델로 넘어가는 순서입니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   primary_model: 가장 먼저 시도할 기본 모델 ID입니다.
# 처리:
#   - Secrets의 GEMINI_FALLBACK_MODELS가 있으면 해당 순서를 사용합니다.
#   - 없으면 DEFAULT_GEMINI_FALLBACK_MODELS를 사용합니다.
#   - 기본 모델과 대체 모델을 합친 뒤 빈 값과 중복을 제거합니다.
# 반환값:
#   실제 API 호출 우선순서가 담긴 모델 ID 목록입니다.
# 운영 팁:
#   비용 우선이면 Lite 모델을 앞쪽으로, 정확도 우선이면 Flash 모델을 앞쪽으로 배치합니다.
def _get_fallback_models(primary_model: str) -> list[str]:
    """
    Gemini 호출 후보 모델을 우선순위대로 반환합니다.

    OCR 사진 판독 기본 순서:
      1. gemini-3.5-flash
      2. gemini-3-flash-preview
      3. gemini-2.5-flash
      4. gemini-3.1-flash-lite
      5. gemini-2.5-flash-lite

    Streamlit Secrets 예시:
      GEMINI_MODEL = "gemini-3.5-flash"
      GEMINI_FALLBACK_MODELS = "gemini-3-flash-preview,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-2.5-flash-lite"
    """
    fallback_default = ",".join(DEFAULT_GEMINI_FALLBACK_MODELS)
    fallback_secret = st.secrets.get(
        "GEMINI_FALLBACK_MODELS",
        fallback_default,
    )

    models = []
    for item in [primary_model, *str(fallback_secret).split(",")]:
        candidate = str(item).strip()
        if candidate and candidate not in models:
            models.append(candidate)
    return models



# -----------------------------------------------------------------------------
# 함수: _is_retryable_gemini_error
# 목적: 503/429/timeout 같은 일시 장애인지 판단합니다.
# True이면 같은 모델을 잠시 기다린 뒤 한 번 더 호출합니다.
# 영구 오류를 무한 재시도하지 않도록 문자열 키워드를 제한적으로 검사합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   같은 모델에 잠시 후 다시 요청하면 성공할 가능성이 있는 일시 오류를 식별합니다.
# 예:
#   503, high demand, 429, timeout, deadline, resource exhausted
# 반환값:
#   True: 동일 모델 재시도 가능
#   False: 재시도보다 즉시 다음 모델 전환 또는 최종 오류가 적절
# 구현 방식:
#   SDK 버전별 예외 클래스 차이를 피하기 위해 예외 문자열의 키워드를 검사합니다.
def _is_retryable_gemini_error(error: Exception) -> bool:
    """동일 모델을 잠시 기다렸다가 다시 호출할 오류인지 판단합니다."""
    error_text = str(error).lower()
    retry_keywords = [
        "503",
        "unavailable",
        "high demand",
        "try again later",
        "temporarily",
        "timeout",
        "timed out",
        "deadline",
        "rate limit",
        "429",
        "resource_exhausted",
        "internal",
        "500",
        "502",
        "504",
    ]
    return any(keyword in error_text for keyword in retry_keywords)



# -----------------------------------------------------------------------------
# 함수: _is_model_switch_error
# 목적: 현재 모델 ID 또는 권한 문제로 판단되는 오류를 찾아 즉시 다음 모델로 전환합니다.
# 예: 모델 미지원, 지역 제한, 폐기, 403/404 응답.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   현재 모델 자체를 사용할 수 없으므로 동일 모델 재시도가 의미 없는 오류를 식별합니다.
# 예:
#   model not found, unsupported, deprecated, permission denied, 403, 404
# 반환값:
#   True이면 대기하지 않고 다음 fallback 모델로 넘어갑니다.
def _is_model_switch_error(error: Exception) -> bool:
    """
    현재 모델을 더 재시도하지 않고 다음 후보 모델로 전환할 오류인지 판단합니다.

    Preview 모델의 지역/계정 미지원, 모델 폐기, 잘못된 모델 ID처럼
    특정 모델에만 해당할 가능성이 있는 오류를 포함합니다.
    """
    error_text = str(error).lower()
    switch_keywords = [
        "404",
        "not_found",
        "not found",
        "model is not found",
        "model not found",
        "unsupported model",
        "not supported",
        "is not available",
        "not available in your region",
        "permission_denied",
        "permission denied",
        "403",
        "deprecated",
        "shut down",
    ]
    return any(keyword in error_text for keyword in switch_keywords)



# -----------------------------------------------------------------------------
# 예외 클래스: OCRResponseError
# API 통신은 성공했지만 JSON 파싱 또는 필수 OCR 값 검증에 실패했음을 구분하기 위한 전용 예외입니다.
# 이 예외는 자동 대체 로직에서 다음 모델로 전환하는 근거로 사용됩니다.
# -----------------------------------------------------------------------------
class OCRResponseError(ValueError):
    """API 응답은 도착했지만 OCR JSON이 불완전하거나 사용할 수 없을 때 발생합니다."""



# -----------------------------------------------------------------------------
# 함수: _is_usable_ocr_result
# 목적: API 호출은 성공했지만 실제 판독 내용이 비어 있는 응답을 실패로 간주합니다.
# 제품명, 유효 바코드, 성분 중 하나라도 있으면 사용 가능한 OCR 결과입니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   ocr_result: 파싱된 OCR 결과 dict입니다.
# 유효 조건:
#   - 제품명이 확인되었거나
#   - 유효한 바코드가 있거나
#   - 성분 목록이 하나 이상 존재
# 반환값:
#   OCR 결과가 DB 비교에 사용할 최소 정보를 갖추었는지 여부입니다.
# 이유:
#   API 200 응답이라도 빈 JSON 또는 형식만 있는 JSON이면 다음 모델을 시도해야 합니다.
def _is_usable_ocr_result(ocr_result: dict) -> bool:
    """제품명·바코드·성분 중 하나 이상이 식별되었는지 확인합니다."""
    if not isinstance(ocr_result, dict):
        return False

    product_name = ensure_text(ocr_result.get("product_name"), "")
    barcode = normalize_barcode(ocr_result.get("barcode"))
    ingredients = ensure_ingredient_list(ocr_result.get("translated_ingredients"))

    valid_product = product_name not in ["", "확인 불가", "미상", "unknown"]
    return bool(valid_product or barcode or ingredients)



# -----------------------------------------------------------------------------
# 함수: generate_ocr_with_model_fallback
# 목적: OCR 모델 호출, 재시도, 모델 전환, JSON 파싱을 한 곳에서 관리합니다.
# 처리 순서:
#   1) 기본 모델 호출
#   2) 일시 오류면 같은 모델 재시도
#   3) 모델 오류/파싱 실패/빈 OCR이면 다음 후보 모델로 전환
#   4) 성공한 JSON과 실제 사용 모델명을 반환
# 진단: 각 시도 결과는 st.session_state["_gemini_attempt_log"]에 저장됩니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   model: 기본 모델 ID
#   contents: 이미지 Part들과 OCR 프롬프트가 들어 있는 Gemini Content 목록
# 처리 흐름:
#   1. _get_fallback_models()로 후보 모델 순서를 만듭니다.
#   2. 기본 모델은 최대 2회, 대체 모델은 1회 호출합니다.
#   3. API 응답을 parse_gemini_json_response()로 파싱합니다.
#   4. _is_usable_ocr_result()로 실제 OCR 값이 있는지 검증합니다.
#   5. 성공하면 (ocr_result, 실제 모델명)을 반환합니다.
#   6. 실패하면 오류 유형에 따라 재시도 또는 다음 모델 전환을 수행합니다.
# 기록:
#   각 시도의 모델명, 시도 번호, 상태, 오류를 _gemini_attempt_log에 저장합니다.
# 최종 실패:
#   모든 모델이 실패하면 마지막 예외를 다시 발생시킵니다.
def generate_ocr_with_model_fallback(model, contents):
    """
    OCR 사진 판독 전용 Gemini 호출 함수입니다.

    동작 방식
    - 기본 모델은 최대 2회 호출합니다.
    - 대체 모델은 순서대로 1회씩 호출합니다.
    - 503/429/500/timeout은 재시도 후 다음 모델로 전환합니다.
    - 모델 미지원·지역 제한·폐기는 즉시 다음 모델로 전환합니다.
    - JSON 파싱 실패, 응답 잘림, 제품명·바코드·성분이 모두 비어 있는 경우에도
      OCR 실패로 판단하여 다음 모델로 자동 전환합니다.
    - 실제 성공 모델과 시도 이력을 session_state에 저장합니다.
    """
    last_error = None
    candidate_models = _get_fallback_models(model)
    attempt_history = []

    for model_index, candidate_model in enumerate(candidate_models):
        max_attempts = 2 if model_index == 0 else 1

        for attempt in range(max_attempts):
            attempt_no = attempt + 1
            try:
                if model_index > 0 and attempt == 0:
                    st.info(
                        f"OCR 판독을 `{candidate_model}` 모델로 자동 전환합니다."
                    )

                response = client.models.generate_content(
                    model=candidate_model,
                    contents=contents,
                    config=build_gemini_generation_config_legacy(),
                )

                try:
                    ocr_result = parse_gemini_json_response(response)
                except Exception as parse_error:
                    raise OCRResponseError(
                        f"{candidate_model} OCR JSON 파싱 실패: {parse_error}"
                    ) from parse_error

                if not _is_usable_ocr_result(ocr_result):
                    raise OCRResponseError(
                        f"{candidate_model} 응답에서 제품명·바코드·성분을 식별하지 못했습니다."
                    )

                attempt_history.append({
                    "model": candidate_model,
                    "attempt": attempt_no,
                    "status": "success",
                })
                st.session_state["_last_gemini_model_used"] = candidate_model
                st.session_state["_gemini_ocr_attempt_history"] = attempt_history
                return ocr_result, candidate_model

            except OCRResponseError as error:
                last_error = error
                attempt_history.append({
                    "model": candidate_model,
                    "attempt": attempt_no,
                    "status": "ocr_response_error",
                    "error": str(error)[:300],
                })

                # 기본 모델은 같은 모델로 한 번 더 판독한 뒤 다음 모델로 넘어갑니다.
                if attempt + 1 < max_attempts:
                    time.sleep(0.8)
                    continue
                break

            except Exception as error:
                last_error = error
                retryable = _is_retryable_gemini_error(error)
                switchable = _is_model_switch_error(error)
                attempt_history.append({
                    "model": candidate_model,
                    "attempt": attempt_no,
                    "status": "api_error",
                    "error": str(error)[:300],
                })

                if retryable and attempt + 1 < max_attempts:
                    time.sleep(1.5 * attempt_no)
                    continue

                if retryable or switchable:
                    break

                st.session_state["_gemini_ocr_attempt_history"] = attempt_history
                raise

    st.session_state["_gemini_ocr_attempt_history"] = attempt_history
    if last_error is not None:
        raise last_error
    raise RuntimeError("OCR 사진 판독에 사용할 수 있는 Gemini 모델 후보가 없습니다.")


# -----------------------------------------------------------------------------
# 함수: _strip_markdown_fences
# 목적: 모델이 JSON을 ```json 코드블록으로 감쌌을 때 양쪽 마크다운 표식을 제거합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   모델이 JSON 앞뒤에 ```json ... ``` 마크다운 코드펜스를 붙였을 때 제거합니다.
# 반환값:
#   앞뒤 공백과 코드펜스가 제거된 문자열입니다.
def _strip_markdown_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json|JSON)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    return text



# -----------------------------------------------------------------------------
# 함수: _extract_first_balanced_json_object
# 목적: 설명문이 섞인 응답에서 첫 번째 완전한 JSON 객체만 추출합니다.
# 문자열 내부의 { }는 구조 깊이 계산에서 제외하여 오검출을 방지합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   응답에 설명문이나 여러 텍스트가 섞였을 때 첫 번째 완성된 JSON 객체 범위를 찾습니다.
# 알고리즘:
#   - 첫 '{'부터 문자별로 순회합니다.
#   - 문자열 안의 중괄호는 구조로 계산하지 않습니다.
#   - escape된 따옴표도 고려합니다.
#   - 중괄호 깊이가 다시 0이 되는 지점까지 잘라냅니다.
# 실패 대응:
#   응답이 중간에서 잘리면 가능한 마지막 '}'까지 또는 남은 문자열을 반환합니다.
def _extract_first_balanced_json_object(text: str) -> str:
    """
    응답 안에서 첫 번째 완전한 JSON 객체만 추출합니다.
    문자열 내부의 중괄호는 무시합니다.
    """
    text = text or ""
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\" and in_string:
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    # 응답이 중간에 잘렸으면 마지막 } 기준으로라도 후보를 만든다.
    end = text.rfind("}")
    if end > start:
        return text[start:end + 1]
    return text[start:]



# -----------------------------------------------------------------------------
# 함수: _repair_json_common
# 목적: 긴 성분표에서 자주 발생하는 쉼표 누락·중복 쉼표·trailing comma를 보정합니다.
# 보정은 흔한 패턴에만 제한하며, 원문을 과도하게 변경하지 않습니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   긴 성분 JSON에서 자주 발생하는 단순 문법 오류만 제한적으로 자동 보정합니다.
# 보정 예:
#   } {        -> }, {
#   ] "key": -> ], "key":
#   중복 쉼표  -> 쉼표 하나
#   },]        -> }]
# 주의:
#   의미를 추측해 새로운 데이터를 만들지 않고 JSON 구문 오류만 최소한으로 고칩니다.
def _repair_json_common(text: str) -> str:
    """
    Gemini가 긴 성분 배열을 만들 때 드물게 누락하는 쉼표를 보정합니다.
    - } 다음 { 사이 쉼표 누락
    - ] 다음 "field": 사이 쉼표 누락
    - "value" 다음 "field": 사이 쉼표 누락
    - 닫는 괄호 앞 trailing comma 제거
    """
    s = _strip_markdown_fences(text)
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = _extract_first_balanced_json_object(s)

    # 객체 배열 원소 사이 쉼표 누락: } \n {  -> }, \n {
    s = re.sub(r'(\})\s*(\n\s*\{)', r'\1,\2', s)

    # 배열/객체/문자열 값 뒤 다음 필드 쉼표 누락 보정
    s = re.sub(r'([\}\]"0-9])\s*(\n\s*"[A-Za-z0-9_가-힣]+"\s*:)', r'\1,\2', s)

    # 실수로 생긴 중복 쉼표와 trailing comma 보정
    s = re.sub(r',\s*,+', ',', s)
    s = re.sub(r',\s*([\}\]])', r'\1', s)
    return s



# -----------------------------------------------------------------------------
# 함수: _regex_json_string
# 목적: 전체 JSON 파싱이 실패했을 때 특정 문자열 필드 하나를 정규식으로 회수합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   전체 JSON 파싱이 실패한 상황에서 특정 key의 문자열 값만 복구합니다.
# 입력값:
#   text: 원본 모델 응답
#   key: 찾을 JSON 필드명
#   default: 찾지 못했을 때 반환할 값
# 반환값:
#   escape 문자를 복원한 문자열 또는 기본값입니다.
def _regex_json_string(text: str, key: str, default: str = "") -> str:
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text or "", re.S)
    if not m:
        return default
    try:
        return json.loads('"' + m.group(1) + '"')
    except Exception:
        return m.group(1)



# -----------------------------------------------------------------------------
# 함수: _salvage_partial_ocr_json
# 목적: 응답이 중간에서 잘려도 브랜드·제품명·바코드와 완성된 성분 행을 최대한 복구합니다.
# 완전히 아무 정보도 얻지 못하면 예외를 발생시켜 다음 모델로 넘어가게 합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   출력 토큰 부족이나 쉼표 누락으로 JSON 전체가 깨져도 활용 가능한 필드를 최대한 회수합니다.
# 복구 대상:
#   brand, product_name, translated_product_name, barcode, package_features
#   multilingual_candidates의 완성된 문자열
#   translated_ingredients의 완성된 객체
# 반환값:
#   표준 OCR dict입니다.
# 실패:
#   제품명·브랜드·바코드·성분 등 어떤 정보도 회수하지 못하면 예외를 발생시킵니다.
def _salvage_partial_ocr_json(text: str) -> dict:
    """
    최후 방어: JSON 전체 파싱이 실패해도 화면이 중단되지 않도록
    정규식으로 확인 가능한 OCR 필드와 완성된 성분 행만 회수합니다.
    """
    raw = _strip_markdown_fences(text or "")
    result = {
        "brand": _regex_json_string(raw, "brand", "확인 불가"),
        "product_name": _regex_json_string(raw, "product_name", "확인 불가"),
        "translated_product_name": _regex_json_string(raw, "translated_product_name", ""),
        "barcode": _regex_json_string(raw, "barcode", "바코드 확인 불가"),
        "multilingual_candidates": [],
        "translated_ingredients": [],
        "package_features": _regex_json_string(raw, "package_features", ""),
    }

    cand_block = re.search(r'"multilingual_candidates"\s*:\s*\[(.*?)\]', raw, re.S)
    if cand_block:
        result["multilingual_candidates"] = re.findall(r'"((?:\\.|[^"\\])*)"', cand_block.group(1))

    for m in re.finditer(
        r'\{\s*"raw_name"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"ko_name"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*"remark"\s*:\s*"((?:\\.|[^"\\])*)"',
        raw,
        re.S,
    ):
        try:
            raw_name = json.loads('"' + m.group(1) + '"')
            ko_name = json.loads('"' + m.group(2) + '"')
            remark = json.loads('"' + m.group(3) + '"')
        except Exception:
            raw_name, ko_name, remark = m.group(1), m.group(2), m.group(3)
        result["translated_ingredients"].append({
            "raw_name": raw_name,
            "ko_name": ko_name,
            "remark": remark,
        })

    has_any = any([
        result["brand"] != "확인 불가",
        result["product_name"] != "확인 불가",
        result["barcode"] != "바코드 확인 불가",
        result["multilingual_candidates"],
        result["translated_ingredients"],
    ])
    if not has_any:
        raise ValueError("부분 OCR 결과도 회수하지 못했습니다.")
    return result



# -----------------------------------------------------------------------------
# 함수: parse_gemini_json_response
# 목적: Gemini 응답을 단계적으로 파싱하는 핵심 방어 함수입니다.
# 우선순위: response.parsed → 순수 JSON → 코드블록 제거 → 객체 추출 → JSON 보정 → 부분 복구.
# 모든 단계가 실패하면 응답 일부를 포함한 오류를 발생시켜 원인 분석을 돕습니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   response: Google GenAI SDK의 GenerateContentResponse 객체입니다.
# 파싱 단계:
#   1. response.parsed가 dict/Pydantic 객체인지 확인
#   2. response.text 원문 파싱
#   3. 코드펜스 제거 문자열 파싱
#   4. 균형 JSON 객체 추출 후 파싱
#   5. 흔한 JSON 오류 보정 후 파싱
#   6. 정규식 기반 부분 복구
# 반환값:
#   최상위 dict 형태의 OCR 결과입니다.
# 실패:
#   디버깅을 위해 응답 앞부분을 포함한 ValueError를 발생시킵니다.
# 보안:
#   화면에는 일부 응답만 보여주며 API 키 등 비밀정보는 응답에 포함되지 않아야 합니다.
def parse_gemini_json_response(response):
    """
    Gemini JSON 응답 파싱 안정화 버전.
    1) response.parsed 우선
    2) 순수 JSON / 코드블록 제거 JSON
    3) 균형 잡힌 JSON 객체 추출
    4) 쉼표 누락 등 흔한 JSON 오류 자동 보정
    5) 최후에는 정규식으로 필드와 성분 행만 회수
    """
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    if parsed is not None:
        try:
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()
            if isinstance(parsed, str):
                return json.loads(parsed)
        except Exception:
            pass

    raw_text = getattr(response, "text", "") or ""
    if not raw_text.strip():
        raise ValueError("Gemini 응답이 비어 있습니다.")

    clean_text = _strip_markdown_fences(raw_text)
    candidates = [
        raw_text.strip(),
        clean_text,
        _extract_first_balanced_json_object(clean_text),
        _repair_json_common(clean_text),
    ]

    last_error = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
            raise ValueError("Gemini JSON 최상위 값이 객체(dict)가 아닙니다.")
        except Exception as e:
            last_error = e

    try:
        return _salvage_partial_ocr_json(raw_text)
    except Exception:
        debug_text = raw_text[:1600].replace("`", "'")
        raise ValueError(f"Gemini JSON 응답 파싱 실패: {last_error}\n--- 응답 일부 ---\n{debug_text}")



# -----------------------------------------------------------------------------
# 함수: ensure_text
# 목적: Gemini가 문자열 대신 list/dict/int/None을 반환해도 화면과 DB 비교에 안전한 문자열로 변환합니다.
# barcode list로 인해 .replace()가 실패했던 문제를 이 계층에서 방지합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   모델 응답의 자료형이 예상과 달라도 안전한 단일 문자열로 변환합니다.
# 입력 처리:
#   list/tuple: 첫 번째 유효 항목 사용
#   dict: 한글 보존 JSON 문자열로 변환
#   int/float: str() 변환
#   None/NaN/빈 값: default 반환
# 대표 해결 오류:
#   barcode가 list로 반환되어 .replace() 호출 시 AttributeError가 발생하는 문제를 방지합니다.
def ensure_text(value, default="확인 불가"):
    """
    Gemini 응답값을 안전한 문자열로 변환합니다.
    - list/tuple이면 첫 번째 유효값 사용
    - dict이면 JSON 문자열화
    - None/빈값/nan이면 기본값 반환
    """
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        for item in value:
            converted = ensure_text(item, "")
            if converted:
                return converted
        return default
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() in ["nan", "none", "null", "[]", "{}"]:
        return default
    return text



# -----------------------------------------------------------------------------
# 함수: ensure_text_list
# 목적: multilingual_candidates를 항상 중복 없는 문자열 리스트로 정규화합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   multilingual_candidates를 항상 list[str] 형태로 맞춥니다.
# 처리:
#   문자열 하나면 1개짜리 목록으로 변환합니다.
#   기타 자료형도 목록으로 감싼 뒤 ensure_text()를 적용합니다.
#   빈 값과 중복 후보를 제거합니다.
def ensure_text_list(value):
    """Gemini 응답값을 문자열 리스트로 정규화합니다."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    elif not isinstance(value, list):
        value = [value]

    result = []
    for item in value:
        text = ensure_text(item, "")
        if text and text not in result:
            result.append(text)
    return result



# -----------------------------------------------------------------------------
# 함수: ensure_ingredient_list
# 목적: 성분 응답이 dict/string/list/None 중 어떤 형태여도 표준 list[dict]로 변환합니다.
# 각 성분 dict는 raw_name, ko_name, remark 세 필드를 항상 갖도록 보정합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   translated_ingredients를 항상 list[dict] 구조로 정규화합니다.
# 입력별 처리:
#   dict -> 1개짜리 목록
#   string -> 쉼표/슬래시/줄바꿈으로 나눈 최소 성분 객체 목록
#   list -> 각 항목을 표준 dict로 보정
# 출력 필드:
#   raw_name, ko_name, remark
# 주의:
#   모델이 불완전한 값을 주더라도 키가 누락되지 않도록 기본값을 채웁니다.
def ensure_ingredient_list(value):
    """translated_ingredients가 None/string/dict/list 어떤 형태로 와도 표준 list[dict]로 변환합니다."""
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    elif isinstance(value, str):
        # 모델이 문자열로 성분을 반환한 경우 콤마 기준으로 최소 구조화
        value = [{"raw_name": x.strip(), "ko_name": "확인 불가", "remark": "확인 불가"} for x in re.split(r"[,/;\n]+", value) if x.strip()]
    elif not isinstance(value, list):
        return []

    result = []
    for item in value:
        if isinstance(item, dict):
            result.append({
                "raw_name": ensure_text(item.get("raw_name"), "확인 불가"),
                "ko_name": ensure_text(item.get("ko_name"), "확인 불가"),
                "remark": ensure_text(item.get("remark"), "확인 불가"),
            })
        else:
            text = ensure_text(item, "")
            if text:
                result.append({"raw_name": text, "ko_name": "확인 불가", "remark": "확인 불가"})
    return result



# -----------------------------------------------------------------------------
# 함수: normalize_barcode
# 목적: 바코드를 DB 비교용 소문자 영숫자 문자열로 정리합니다.
# 공백·하이픈·기타 기호를 제거하며 '확인 불가'나 빈 값은 빈 문자열로 처리합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   화면 표시용 바코드를 DB 비교용 키로 변환합니다.
# 처리:
#   ensure_text()로 자료형을 문자열화한 뒤 숫자·영문 이외 문자를 제거하고 소문자로 변환합니다.
# 반환값:
#   비교 가능한 바코드 문자열 또는 빈 문자열입니다.
# 주의:
#   유효 길이 판정은 is_valid_barcode()에서 별도로 수행합니다.
def normalize_barcode(value):
    """barcode가 list/int/None으로 와도 DB 대조 가능한 문자열로 변환합니다."""
    text = ensure_text(value, "")
    if not text or text == "바코드 확인 불가":
        return ""
    # 숫자와 영문만 남김. 하이픈/공백 제거.
    return re.sub(r"[^0-9a-zA-Z]", "", text).lower()


# 제품명 또는 성분명만으로 잘못된 DB 행이 연결되는 것을 방지하기 위한 공통 설정
# 여러 건강식품·의약품에 광범위하게 등장하는 일반 성분 목록입니다.
# 이 성분 하나만 일치한다고 같은 제품으로 보면 오탐이 크게 증가합니다.
# 따라서 성분 단독 매칭 단계에서 이 목록의 토큰은 비교 대상에서 제외합니다.
# 실제 위해성분이 이 목록에 잘못 포함되지 않도록 수정 시 반드시 DB 사례를 검토합니다.
COMMON_INGREDIENT_TOKENS = {
    "water", "정제수", "purifiedwater", "aqua", "물",
    "gelatin", "젤라틴", "glycerin", "글리세린", "glycerol",
    "cellulose", "셀룰로오스", "starch", "전분", "silica", "이산화규소",
    "magnesiumstearate", "스테아린산마그네슘", "stearicacid", "스테아르산",
    "sugar", "설탕", "glucose", "포도당", "fructose", "과당",
    "flavor", "flavour", "향료", "color", "colour", "착색료",
    "salt", "소금", "sodium", "나트륨", "calcium", "칼슘",
    "potassium", "칼륨", "magnesium", "마그네슘",
    "caffeine", "카페인", "vitamin", "비타민",

    # 아래 값은 특정 성분명이 아니라 여러 식물 원료에 반복되는 일반 부위·가공 표현입니다.
    # bark/leaf 하나만 같다는 이유로 전혀 다른 제품(Marathon21 등)이 선택되는 것을 방지합니다.
    "bark", "껍질", "수피",
    "leaf", "leaves", "잎", "엽",
    "root", "roots", "뿌리", "근",
    "seed", "seeds", "씨앗", "종자",
    "stem", "stems", "줄기",
    "flower", "flowers", "꽃",
    "fruit", "fruits", "과실",
    "herb", "herbs", "허브",
    "extract", "extracts", "추출물",
    "powder", "분말",
    "peel", "껍질추출물",
}



# -----------------------------------------------------------------------------
# 함수: is_valid_barcode
# 목적: 빈 값, nan, 지나치게 짧은 값이 DB 바코드와 우연히 일치하는 문제를 차단합니다.
# 실제 비교는 이 검사를 통과한 바코드에 대해서만 수행합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   빈 값, nan, none, 확인 불가, 지나치게 짧은 OCR 값을 바코드 매칭에서 제외합니다.
# 반환값:
#   현재 기준을 통과하는 바코드이면 True입니다.
# 이유:
#   DB의 빈 셀을 문자열 'nan'으로 변환한 값과 OCR 빈 값이 우연히 일치하는 오탐을 방지합니다.
def is_valid_barcode(value: str) -> bool:
    """빈값·N/A·nan 등 가짜 바코드가 DB의 빈 행과 일치하는 것을 방지합니다."""
    barcode = normalize_barcode(value)
    if not barcode or barcode in {"nan", "none", "null", "na", "nobarcode", "unknown"}:
        return False
    # 일반적인 UPC/EAN/GTIN 길이를 포함하되, 문자 혼합 코드도 일부 허용
    if not 8 <= len(barcode) <= 18:
        return False
    return sum(ch.isdigit() for ch in barcode) >= 6



# -----------------------------------------------------------------------------
# 함수: product_name_similarity
# 목적: 정규화된 두 제품명이 표기 차이·맛/제형 차이를 가진 동일 제품인지 점수화합니다.
# SequenceMatcher 점수와 부분 포함 길이 비율을 함께 사용합니다.
# 1.0은 완전 일치이며, 확정 임계값은 find_safe_db_match()에서 결정합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   left/right: 이미 normalize_product_name()을 거친 문자열이 권장됩니다.
# 계산:
#   - SequenceMatcher 전체 문자열 유사도
#   - 한 문자열이 다른 문자열을 포함하는 경우 길이 비율
#   두 점수 중 큰 값을 반환합니다.
# 반환 범위:
#   0.0 ~ 1.0
# 주의:
#   임계값은 이 함수가 아니라 find_safe_db_match()에서 업무 기준에 맞게 결정합니다.
def product_name_similarity(left: str, right: str) -> float:
    """정규화 제품명 두 개의 보수적인 유사도를 계산합니다."""
    a = normalize_product_name(left)
    b = normalize_product_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    sequence_score = SequenceMatcher(None, a, b).ratio()

    # 부분 포함은 짧은 문자열이 충분히 길고 전체 이름의 상당 부분을 차지할 때만 인정
    containment_score = 0.0
    if len(shorter) >= 5 and shorter in longer:
        length_ratio = len(shorter) / max(len(longer), 1)
        if length_ratio >= 0.65:
            containment_score = 0.86 + min(0.13, (length_ratio - 0.65) * 0.35)

    return max(sequence_score, containment_score)



# -----------------------------------------------------------------------------
# 함수: build_user_product_candidates
# 목적: OCR의 원문명·번역명·다국어 후보·브랜드+제품명 조합을 모두 제품명 비교 후보로 만듭니다.
# 각 후보는 normalize_product_name()을 거치고 중복·너무 짧은 값은 제거됩니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   한 제품에 대해 OCR이 제공한 여러 표현을 DB 비교 후보로 만듭니다.
# 후보:
#   - product_name
#   - translated_product_name
#   - multilingual_candidates
#   - brand + product_name
# 처리:
#   모든 후보를 정규화하고 길이 3 미만, 빈 값, 중복을 제거합니다.
# 반환값:
#   정규화된 제품명 후보 목록입니다.
def build_user_product_candidates(brand, product_name, translated_product_name, multilingual_candidates):
    """OCR 결과에서 제품명 비교에 사용할 후보를 중복 없이 생성합니다."""
    raw_candidates = []
    raw_candidates.extend(ensure_text_list(multilingual_candidates))
    raw_candidates.extend([
        ensure_text(product_name, ""),
        ensure_text(translated_product_name, ""),
    ])

    brand_text = ensure_text(brand, "")
    product_text = ensure_text(product_name, "")
    if brand_text and product_text:
        raw_candidates.append(f"{brand_text} {product_text}")

    normalized = []
    for candidate in raw_candidates:
        norm = normalize_product_name(candidate)
        if len(norm) >= 3 and norm not in normalized:
            normalized.append(norm)
    return normalized



# -----------------------------------------------------------------------------
# 함수: _best_product_similarity
# 목적: 여러 OCR 제품명 후보 중 특정 DB 제품명과 가장 높은 유사도를 반환합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   여러 OCR 제품명 후보와 DB 제품명 한 개를 비교해 가장 높은 점수만 반환합니다.
# 반환값:
#   후보가 없으면 0.0, 있으면 최대 유사도입니다.
# 사용처:
#   바코드 중복 행 선택, 전체 DB fuzzy 후보 선택, 성분 후보의 제품명 보조 검증
def _best_product_similarity(user_candidates, db_product_norm):
    if not db_product_norm:
        return 0.0
    return max((product_name_similarity(candidate, db_product_norm) for candidate in user_candidates), default=0.0)


# -----------------------------------------------------------------------------
# 함수: build_user_product_raw_candidates
# 목적:
#   제품명 정규화 과정에서 공백과 단어 경계가 사라지기 전에 OCR 원문 후보를 보존합니다.
#
# 왜 필요한가:
#   OCR 결과가 "Sleep & Slim"이고 DB가 "LONLIFE Sleep & Slim"인 경우,
#   compact 정규화 결과는 각각 "sleepslim", "lonlifesleepslim"입니다.
#   기존 일반 유사도만 사용하면 앞의 브랜드 글자 때문에 점수가 낮아질 수 있습니다.
#   따라서 원문 단어 배열을 별도로 비교하여
#   "DB 브랜드 접두어 + OCR 핵심 제품명" 구조를 식별합니다.
# -----------------------------------------------------------------------------
def build_user_product_raw_candidates(
    brand,
    product_name,
    translated_product_name,
    multilingual_candidates,
):
    """
    OCR이 반환한 제품명 표현을 원문 형태로 모아 중복 제거합니다.

    후보 구성:
    1. OCR 핵심 제품명
    2. 번역 제품명
    3. multilingual_candidates
    4. 브랜드 + 핵심 제품명 조합

    반환값:
        사람이 읽는 원문 형태의 문자열 목록입니다.
        DB의 원문 제품명과 단어 단위로 비교할 때 사용합니다.
    """
    raw_candidates = [
        ensure_text(product_name, ""),
        ensure_text(translated_product_name, ""),
    ]
    raw_candidates.extend(ensure_text_list(multilingual_candidates))

    brand_text = ensure_text(brand, "")
    product_text = ensure_text(product_name, "")
    if brand_text and product_text:
        raw_candidates.append(f"{brand_text} {product_text}")

    result = []
    seen = set()
    for candidate in raw_candidates:
        candidate = str(candidate).strip()
        if not candidate:
            continue

        # NFKC 및 casefold는 전각/반각과 영문 대소문자 차이를 줄이기 위한 중복 키입니다.
        dedupe_key = unicodedata.normalize("NFKC", candidate).casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(candidate)

    return result


# 제품명 단어 비교에서 의미가 거의 없는 용량·제형 단어입니다.
# 예: "Sleep & Slim 60 Capsules"와 "Sleep & Slim"을 같은 핵심 이름으로 비교합니다.
PRODUCT_WORD_NOISE = {
    "capsule", "capsules", "tablet", "tablets", "softgel", "softgels",
    "powder", "liquid", "serving", "servings", "count", "pack", "packs",
    "mg", "ml", "g", "oz",
    "정", "정제", "캡슐", "과립", "액제",
    "錠", "カプセル", "顆粒",
}


# -----------------------------------------------------------------------------
# 함수: normalize_product_words
# 목적:
#   제품명에서 단어 경계를 유지한 비교 토큰을 만듭니다.
#
# 예:
#   "LONLIFE Sleep & Slim" -> ["lonlife", "sleep", "slim"]
#   "Sleep & Slim"         -> ["sleep", "slim"]
#   "sleep formula"        -> ["sleep", "formula"]
#
# 이 결과를 사용하면 "Sleep & Slim"은 DB 이름의 마지막 두 단어와 정확히 일치하지만
# "sleep formula"와는 두 번째 단어가 달라 명확하게 구분할 수 있습니다.
# -----------------------------------------------------------------------------
def normalize_product_words(text):
    """제품명의 단어 경계를 보존하면서 비교용 토큰 목록을 생성합니다."""
    if text is None:
        return []

    try:
        if pd.isna(text):
            return []
    except Exception:
        pass

    value = unicodedata.normalize("NFKC", str(text)).casefold().strip()
    if not value or value in {"nan", "none", "null", "확인 불가"}:
        return []

    # 영문·숫자·한글·일본어·한자 덩어리를 개별 단어로 추출합니다.
    words = re.findall(r"[0-9a-z가-힣ぁ-んァ-ン一-龥]+", value)

    cleaned = []
    for word in words:
        if word in PRODUCT_WORD_NOISE:
            continue

        # 숫자 단독 토큰은 대부분 용량·수량이므로 핵심 제품명 비교에서 제외합니다.
        if word.isdigit():
            continue

        # 60capsules, 500mg 같은 결합 용량 토큰도 제외합니다.
        if re.fullmatch(r"\d+(?:\.\d+)?(?:mg|ml|g|oz|capsules?|tablets?)", word):
            continue

        cleaned.append(word)

    return cleaned


# -----------------------------------------------------------------------------
# 함수: is_db_brand_prefix_core_match
# 목적:
#   OCR이 브랜드를 누락했더라도 DB가 "브랜드 + 핵심 제품명" 구조이면 강하게 매칭합니다.
#
# 성공 사례:
#   OCR: "Sleep & Slim"
#   DB : "LONLIFE Sleep & Slim"
#
# 실패 사례:
#   OCR: "Sleep & Slim"
#   DB : "sleep formula"
#
# 안전 조건:
#   - OCR 핵심 이름은 최소 2개 단어여야 합니다.
#   - compact 문자열 길이는 최소 8자여야 합니다.
#   - OCR 단어 배열이 DB 제품명의 마지막 단어 배열과 완전히 같아야 합니다.
#   - DB 앞에 추가된 브랜드 접두어는 최대 3개 단어까지만 허용합니다.
# -----------------------------------------------------------------------------
def is_db_brand_prefix_core_match(user_product_name, db_product_name):
    """
    DB 제품명의 앞부분에 브랜드만 추가된 경우인지 확인합니다.

    반환값:
        True  : DB가 브랜드 접두어 + OCR 핵심 제품명 구조
        False : 핵심 이름이 다르거나 조건이 충분하지 않음
    """
    user_words = normalize_product_words(user_product_name)
    db_words = normalize_product_words(db_product_name)

    # "sleep"처럼 한 단어만으로는 너무 일반적이어서 강한 매칭으로 인정하지 않습니다.
    if len(user_words) < 2:
        return False

    # DB 쪽에 브랜드 접두어가 실제로 하나 이상 있어야 합니다.
    if len(db_words) <= len(user_words):
        return False

    # OCR의 전체 단어 순서가 DB 이름의 끝부분과 정확히 같아야 합니다.
    if db_words[-len(user_words):] != user_words:
        return False

    prefix_words = db_words[:-len(user_words)]

    # 지나치게 많은 앞 단어가 붙은 경우에는 단순 브랜드 접두어로 보지 않습니다.
    if not 1 <= len(prefix_words) <= 3:
        return False

    user_compact = normalize_product_name(user_product_name)
    db_compact = normalize_product_name(db_product_name)

    # 짧고 일반적인 이름의 오탐을 줄입니다.
    if len(user_compact) < 8:
        return False

    # compact 비교에서도 DB 이름이 OCR 핵심명으로 끝나는지 이중 확인합니다.
    if not db_compact.endswith(user_compact):
        return False

    # 브랜드 접두어 부분이 비정상적으로 긴 경우는 제외합니다.
    extra_length = len(db_compact) - len(user_compact)
    if not 2 <= extra_length <= 30:
        return False

    return True


# -----------------------------------------------------------------------------
# 함수: find_unique_brand_prefix_core_match
# 목적:
#   전체 DB에서 "브랜드 접두어 + OCR 핵심 제품명" 후보를 찾고,
#   후보가 여러 개면 OCR 브랜드가 일치하는 행을 우선 선택합니다.
#
# 안전 원칙:
#   브랜드 정보 없이 동일 핵심 제품명이 여러 DB 행에 존재하면 임의로 첫 행을 확정하지 않습니다.
# -----------------------------------------------------------------------------
def find_unique_brand_prefix_core_match(
    df,
    brand,
    product_name,
    translated_product_name,
    multilingual_candidates,
):
    """
    브랜드 접두어 생략형 제품명 매칭 결과를 반환합니다.

    반환값:
        (matched_row, confidence)
        - 유일하거나 OCR 브랜드로 특정 가능한 경우: pandas Series, 0.99
        - 후보가 없거나 여러 행이 모호한 경우: None, 0.0
    """
    if df is None or df.empty or "제품명" not in df.columns:
        return None, 0.0

    raw_candidates = build_user_product_raw_candidates(
        brand,
        product_name,
        translated_product_name,
        multilingual_candidates,
    )

    matches = []
    for row_index, row in df.iterrows():
        db_name = ensure_text(row.get("제품명"), "")
        if not db_name:
            continue

        for candidate in raw_candidates:
            if is_db_brand_prefix_core_match(candidate, db_name):
                matches.append((row_index, row, candidate))
                break

    if not matches:
        return None, 0.0

    # 같은 DB 행이 중복 후보명으로 여러 번 잡히는 경우 행 기준으로 중복 제거합니다.
    unique_matches = {}
    for row_index, row, candidate in matches:
        unique_matches[row_index] = (row, candidate)

    if len(unique_matches) == 1:
        only_row, _ = next(iter(unique_matches.values()))
        return only_row, 0.99

    # 동일 핵심 제품명이 여러 브랜드로 DB에 존재할 수 있으므로 OCR 브랜드로 한 번 더 구분합니다.
    brand_norm = normalize_product_name(brand)
    if brand_norm:
        brand_matches = []
        for row, _candidate in unique_matches.values():
            db_norm = normalize_product_name(row.get("제품명", ""))
            if db_norm.startswith(brand_norm):
                brand_matches.append(row)

        if len(brand_matches) == 1:
            return brand_matches[0], 0.99

    # 여러 후보가 남았는데 브랜드로 특정할 수 없으면 잘못된 DB 행을 고르지 않습니다.
    return None, 0.0





# =============================================================================
# 고유 모델코드 기반 제품명 보조 매칭
# =============================================================================
#
# 필요한 이유
# -----------------------------------------------------------------------------
# 포장 전면에는 다음처럼 표시되는 경우가 많습니다.
#
#   브랜드: ROCK STAR
#   모델명: R80
#   설명문: Thermogenic Hyper-Metabolizer
#
# OCR은 글자 크기와 배치 때문에 이를 다음처럼 읽을 수 있습니다.
#
#   product_name = "R80 Thermogenic Hyper-Metabolizer"
#
# 반면 DB 제품명은 다음처럼 브랜드와 모델명만 등록될 수 있습니다.
#
#   "ROCK STAR R80"
#
# 일반 문자열 유사도만 사용하면 공통 문자가 적어 점수가 낮아지고,
# 뒤의 성분 단계에서 bark, leaf 같은 일반 단어가 일치한 엉뚱한 DB 행이 선택될 수 있습니다.
#
# 아래 함수들은 R80처럼 영문과 숫자가 함께 있는 식별코드를 추출하고,
# 그 코드가 DB 제품명에서 유일하게 발견될 때 제품 식별의 강한 근거로 사용합니다.
#
# 안전 원칙
# -----------------------------------------------------------------------------
# 1. 숫자만 있는 값은 모델코드로 인정하지 않습니다.
# 2. 영문만 있는 일반 단어도 모델코드로 인정하지 않습니다.
# 3. 영문과 숫자가 모두 포함된 3~14자 토큰만 사용합니다.
# 4. 동일 코드가 여러 DB 행에 있으면 OCR 브랜드 또는 제품명 유사도로 한 번 더 구분합니다.
# 5. 그래도 하나로 특정되지 않으면 임의로 첫 행을 선택하지 않습니다.
# =============================================================================

# 모델코드처럼 보이지만 의약품 성분·비타민·용량 표현으로 자주 등장하는 값입니다.
# 이 목록은 강한 제품 식별코드에서 제외합니다.
MODEL_CODE_STOPWORDS = {
    "b12", "b6", "b1", "b2", "b3", "b5", "b7", "b9",
    "d2", "d3", "k1", "k2",
    "5htp", "coq10", "q10",
    "h2o", "omega3", "omega6", "omega9",
    "100mg", "200mg", "500mg", "1000mg",
}


def extract_distinctive_model_codes(text):
    """
    제품명에서 R80처럼 영문과 숫자가 함께 들어간 고유 모델코드를 추출합니다.

    처리 예:
        "R80 Thermogenic Hyper-Metabolizer" -> {"r80"}
        "ROCK STAR R80"                     -> {"r80"}
        "EVP 3D"                            -> {"evp3d"}
        "X-50 MAX"                          -> {"x50"}

    반환값:
        소문자 compact 모델코드 집합(set[str])

    주의:
        이 함수는 제품명/브랜드 문자열에만 사용합니다.
        바코드나 성분표 전체에 적용하면 불필요한 숫자 코드가 포함될 수 있습니다.
    """
    if text is None:
        return set()

    try:
        if pd.isna(text):
            return set()
    except Exception:
        pass

    value = unicodedata.normalize("NFKC", str(text)).casefold().strip()
    if not value or value in {"nan", "none", "null", "확인 불가"}:
        return set()

    # 하이픈·슬래시 등으로 나뉜 코드도 복원할 수 있도록 영숫자 덩어리를 추출합니다.
    raw_tokens = re.findall(r"[a-z0-9]+", value)
    candidates = set()

    def add_candidate(token):
        compact = re.sub(r"[^a-z0-9]", "", token.casefold())

        # 지나치게 짧거나 긴 값은 식별코드로 보기 어렵습니다.
        if not 3 <= len(compact) <= 14:
            return

        # 영문과 숫자가 모두 있어야 합니다.
        if not re.search(r"[a-z]", compact):
            return
        if not re.search(r"\d", compact):
            return

        # 숫자가 너무 많으면 바코드·용량값일 가능성이 높습니다.
        if sum(ch.isdigit() for ch in compact) > 6:
            return

        if compact in MODEL_CODE_STOPWORDS:
            return

        # 500mg, 100ml 등 명백한 용량 표현은 제외합니다.
        if re.fullmatch(r"\d+(?:mg|ml|g|kg|oz|lb)", compact):
            return

        candidates.add(compact)

    # R80, Marathon21처럼 한 덩어리로 읽힌 코드
    for token in raw_tokens:
        add_candidate(token)

    # R-80, X 50, EVP 3D처럼 OCR/인쇄상 분리된 인접 토큰을 결합합니다.
    for i in range(len(raw_tokens) - 1):
        left = raw_tokens[i]
        right = raw_tokens[i + 1]
        combined = left + right

        # 왼쪽이 짧은 브랜드/모델 문자이고 오른쪽에 숫자가 있을 때만 결합합니다.
        if (
            1 <= len(left) <= 5
            and len(right) <= 5
            and re.search(r"[a-z]", combined)
            and re.search(r"\d", combined)
        ):
            add_candidate(combined)

    return candidates


def _collect_ocr_model_codes(
    brand,
    product_name,
    translated_product_name,
    multilingual_candidates,
):
    """
    OCR의 브랜드·제품명·번역명·다국어 후보 전체에서 모델코드를 모읍니다.

    브랜드 자체가 'R80'처럼 잘못 분리되어도 놓치지 않도록 모든 필드를 검사합니다.
    """
    sources = [
        ensure_text(brand, ""),
        ensure_text(product_name, ""),
        ensure_text(translated_product_name, ""),
    ]
    sources.extend(ensure_text_list(multilingual_candidates))

    codes = set()
    for source in sources:
        codes.update(extract_distinctive_model_codes(source))
    return codes


def _product_word_overlap_score(user_raw_candidates, db_product_name):
    """
    OCR 제품명 원문 후보와 DB 제품명의 단어 교집합 비율을 계산합니다.

    모델코드가 여러 DB 행에 중복될 때 보조 정렬 기준으로만 사용합니다.
    모델코드 자체는 비교에서 제외하여 일반 설명 단어의 실제 겹침 정도를 봅니다.
    """
    db_words = set(normalize_product_words(db_product_name))
    if not db_words:
        return 0.0

    best = 0.0
    for candidate in user_raw_candidates:
        user_words = set(normalize_product_words(candidate))
        if not user_words:
            continue

        # 모델코드 토큰을 제거한 일반 제품명 단어끼리 비교합니다.
        user_codes = extract_distinctive_model_codes(candidate)
        db_codes = extract_distinctive_model_codes(db_product_name)

        filtered_user = {
            word for word in user_words
            if word not in user_codes and word not in PRODUCT_WORD_NOISE
        }
        filtered_db = {
            word for word in db_words
            if word not in db_codes and word not in PRODUCT_WORD_NOISE
        }

        if not filtered_user or not filtered_db:
            continue

        intersection = filtered_user & filtered_db
        score = len(intersection) / max(len(filtered_user), 1)
        best = max(best, score)

    return best


def find_unique_model_code_match(
    df,
    brand,
    product_name,
    translated_product_name,
    multilingual_candidates,
):
    """
    OCR 모델코드가 DB 제품명에서 유일하게 일치하는 행을 찾습니다.

    대표 사례:
        OCR: "R80 Thermogenic Hyper-Metabolizer"
        DB : "ROCK STAR R80"
        결과: R80 코드 완전 일치로 DB 행 선택

    반환값:
        {
            "row": pandas.Series 또는 None,
            "code": 일치한 모델코드,
            "confidence": 0.0~1.0,
            "warning": 모호한 경우 설명
        }
    """
    empty_result = {
        "row": None,
        "code": "",
        "confidence": 0.0,
        "warning": "",
    }

    if df is None or df.empty or "제품명" not in df.columns:
        return empty_result

    ocr_codes = _collect_ocr_model_codes(
        brand,
        product_name,
        translated_product_name,
        multilingual_candidates,
    )
    if not ocr_codes:
        return empty_result

    # 각 DB 행에 포함된 모델코드를 미리 계산하고 OCR 코드와 교집합을 찾습니다.
    candidate_rows = []
    for row_index, row in df.iterrows():
        db_name = ensure_text(row.get("제품명"), "")
        db_codes = extract_distinctive_model_codes(db_name)
        common_codes = ocr_codes & db_codes

        for code in common_codes:
            candidate_rows.append({
                "row_index": row_index,
                "row": row,
                "code": code,
                "db_name": db_name,
            })

    if not candidate_rows:
        return empty_result

    # 동일 행·동일 코드 중복을 제거합니다.
    deduped = {}
    for item in candidate_rows:
        deduped[(item["row_index"], item["code"])] = item
    candidate_rows = list(deduped.values())

    # 코드별로 몇 개 DB 행에 등장하는지 계산합니다.
    code_to_rows = {}
    for item in candidate_rows:
        code_to_rows.setdefault(item["code"], []).append(item)

    # DB에서 유일하게 발견되는 코드가 있으면 가장 안전한 강한 매칭입니다.
    unique_code_candidates = [
        items[0] for code, items in code_to_rows.items()
        if len({item["row_index"] for item in items}) == 1
    ]

    if len(unique_code_candidates) == 1:
        chosen = unique_code_candidates[0]
        return {
            "row": chosen["row"],
            "code": chosen["code"],
            "confidence": 0.99,
            "warning": "",
        }

    # 유일 코드 후보가 여러 개면 더 긴 코드를 우선합니다.
    # 예: x5와 rx500이 동시에 추출됐다면 rx500이 식별력이 더 높습니다.
    if unique_code_candidates:
        unique_code_candidates.sort(key=lambda item: len(item["code"]), reverse=True)
        if (
            len(unique_code_candidates) == 1
            or len(unique_code_candidates[0]["code"]) > len(unique_code_candidates[1]["code"])
        ):
            chosen = unique_code_candidates[0]
            return {
                "row": chosen["row"],
                "code": chosen["code"],
                "confidence": 0.98,
                "warning": "",
            }

    # 같은 모델코드가 여러 DB 행에 있으면 OCR 브랜드로 먼저 구분합니다.
    brand_norm = normalize_product_name(brand)
    if brand_norm:
        brand_matches = []
        for item in candidate_rows:
            db_norm = normalize_product_name(item["db_name"])
            if db_norm.startswith(brand_norm) or brand_norm in db_norm:
                brand_matches.append(item)

        unique_brand_rows = {}
        for item in brand_matches:
            unique_brand_rows[item["row_index"]] = item

        if len(unique_brand_rows) == 1:
            chosen = next(iter(unique_brand_rows.values()))
            return {
                "row": chosen["row"],
                "code": chosen["code"],
                "confidence": 0.98,
                "warning": "",
            }

    # 마지막으로 제품명 유사도와 단어 겹침을 조합해 한 행이 명확히 앞서는지 확인합니다.
    user_candidates = build_user_product_candidates(
        brand,
        product_name,
        translated_product_name,
        multilingual_candidates,
    )
    user_raw_candidates = build_user_product_raw_candidates(
        brand,
        product_name,
        translated_product_name,
        multilingual_candidates,
    )

    ranked = []
    unique_rows = {}
    for item in candidate_rows:
        unique_rows[item["row_index"]] = item

    for item in unique_rows.values():
        db_norm = normalize_product_name(item["db_name"])
        name_score = _best_product_similarity(user_candidates, db_norm)
        word_score = _product_word_overlap_score(user_raw_candidates, item["db_name"])
        combined_score = (name_score * 0.65) + (word_score * 0.35)
        ranked.append((combined_score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)

    if ranked:
        best_score, best_item = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0

        # 가장 높은 후보가 두 번째보다 충분히 앞설 때만 확정합니다.
        if best_score >= 0.55 and (best_score - second_score) >= 0.10:
            return {
                "row": best_item["row"],
                "code": best_item["code"],
                "confidence": min(0.97, max(0.90, best_score)),
                "warning": "",
            }

    return {
        "row": None,
        "code": "",
        "confidence": 0.0,
        "warning": (
            "OCR에서 고유 모델코드를 확인했지만 동일 코드가 여러 DB 제품에 존재하여 "
            "브랜드 또는 바코드 확인이 필요합니다."
        ),
    }


# -----------------------------------------------------------------------------
# 함수: find_safe_db_match
# 목적: EVP 3D가 orange +로 연결되는 것과 같은 DB 오매칭을 방지하면서 최적 행을 찾습니다.
# 매칭 우선순위:
#   1) 유효 바코드 완전 일치
#   2) 정규화 제품명 완전 일치
#   3) 브랜드가 빠진 핵심 제품명 완전 일치
#   4) R80 같은 고유 모델코드 완전 일치
#   5) 전체 DB 중 제품명 고유사도(90% 이상)
#   6) 구체 성분 일치 + 제품명 보조 검증
# 안전 원칙: 성분만 같고 제품명이 명확히 다르면 matched_row를 None으로 유지합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   df: 표준화된 불법의약품 DB DataFrame
#   brand/product_name/translated_product_name/barcode:
#       OCR 핵심 식별값
#   multilingual_candidates:
#       원문·로마자·번역명 등 추가 제품명 후보
#   translated_ingredients:
#       OCR 성분 목록
# 반환 dict:
#   matched_row:
#       확정 또는 보조 연결 가능한 DB 행. 제품명 모순 시 None
#   match_type:
#       어떤 규칙으로 매칭했는지 설명
#   is_ingredient_only_match:
#       제품명·바코드가 아니라 성분 후보가 있었는지 여부
#   is_ambiguous_multilingual:
#       제품명 고유사도/파생 매칭 여부
#   matched_ingredient_str:
#       실제 교집합 성분 문자열
#   ingredient_candidate_name:
#       성분으로 발견된 DB 후보 제품명
#   match_warning:
#       제품명 불일치 등 현장 확인 문구
#   match_confidence:
#       0.0~1.0 내부 신뢰도
# 안전 임계값:
#   - fuzzy 제품명 0.90 이상: DB 행 연결
#   - 성분 후보 + 제품명 0.72 이상: 제한A 보조 연결
#   - 성분은 같지만 제품명 0.72 미만: matched_row=None 유지
# 오탐 방지:
#   EVP 3D와 orange +처럼 제품명이 명백히 다르면 성분 후보만 표시하고 DB 상세정보를 숨깁니다.
def find_safe_db_match(
    df,
    brand,
    product_name,
    translated_product_name,
    barcode,
    multilingual_candidates,
    translated_ingredients,
):
    """
    DB 오탐 방지형 매칭.

    핵심 원칙:
    1. 유효한 바코드 완전 일치
    2. 제품명 완전 일치
    3. 매우 높은 제품명 유사도
    4. 성분 단독 일치는 제품명이 모순되지 않을 때만 DB 행을 확정

    성분은 일치하지만 제품명이 전혀 다른 경우에는 DB 상세 행을 연결하지 않고
    '정밀 확인 필요' 후보로만 남깁니다. 따라서 EVP 3D가 orange + 행으로
    잘못 표시되는 유형의 오탐을 차단합니다.
    """
    result = {
        "matched_row": None,
        "match_type": "🟢 매칭되지 않음",
        "is_ingredient_only_match": False,
        "is_ambiguous_multilingual": False,
        "matched_ingredient_str": "",
        "ingredient_candidate_name": "",
        "ingredient_candidate_ingredient": "",
        "match_warning": "",
        "match_confidence": 0.0,
    }

    if df is None or df.empty:
        return result

    user_candidates = build_user_product_candidates(
        brand, product_name, translated_product_name, multilingual_candidates
    )

    # 단어 경계를 보존한 원문 후보는 "LONLIFE Sleep & Slim"처럼
    # DB에 브랜드 접두어가 있고 OCR에는 핵심 제품명만 있는 사례를 찾는 데 사용합니다.
    user_raw_candidates = build_user_product_raw_candidates(
        brand, product_name, translated_product_name, multilingual_candidates
    )

    user_main_norm = normalize_product_name(product_name)
    norm_user_barcode = normalize_barcode(barcode)

    # 1순위: 바코드 완전 일치
    # 바코드는 제품명보다 식별력이 높지만, DB의 빈 값/nan이 서로 일치하는 오탐을 막기 위해
    # OCR과 DB 양쪽 모두 is_valid_barcode()를 통과한 값만 비교합니다.
    if is_valid_barcode(norm_user_barcode) and "norm_barcode" in df.columns:
        valid_mask = df["norm_barcode"].fillna("").astype(str).map(is_valid_barcode)
        barcode_matches = df[valid_mask & (df["norm_barcode"].astype(str) == norm_user_barcode)]
        if not barcode_matches.empty:
            # 동일 바코드가 여러 행이면 제품명 유사도가 가장 높은 행 선택
            best_index = None
            best_score = -1.0
            for idx_row, row in barcode_matches.iterrows():
                score = _best_product_similarity(user_candidates, ensure_text(row.get("norm_product"), ""))
                if score > best_score:
                    best_index, best_score = idx_row, score
            result.update({
                "matched_row": df.loc[best_index],
                "match_type": "1순위 바코드 완전 일치",
                "match_confidence": 1.0,
            })
            return result

    # 2순위: 정규화 제품명 완전 일치
    # 맛·용량·제형·문장부호를 제거한 뒤 완전히 같으면 동일 제품으로 확정합니다.
    if user_candidates and "norm_product" in df.columns:
        exact_rows = df[df["norm_product"].fillna("").astype(str).isin(user_candidates)]
        if not exact_rows.empty:
            result.update({
                "matched_row": exact_rows.iloc[0],
                "match_type": "2순위 제품명 완전 일치",
                "match_confidence": 1.0,
            })
            return result

    # 2.5순위: DB 브랜드 접두어 + OCR 핵심 제품명 완전 일치
    #
    # 대표 사례:
    #   OCR 제품명: Sleep & Slim
    #   DB 제품명 : LONLIFE Sleep & Slim
    #
    # 기존 문자열 유사도만 사용하면 "LONLIFE" 때문에 전체 점수가 낮아져
    # 성분 단계에서 "sleep formula" 같은 잘못된 후보가 선택될 수 있습니다.
    # 이 단계에서는 OCR 단어 배열이 DB 이름의 마지막 단어 배열과 정확히 같을 때만 인정합니다.
    brand_prefix_row, brand_prefix_confidence = find_unique_brand_prefix_core_match(
        df=df,
        brand=brand,
        product_name=product_name,
        translated_product_name=translated_product_name,
        multilingual_candidates=multilingual_candidates,
    )

    if brand_prefix_row is not None:
        result.update({
            "matched_row": brand_prefix_row,
            "match_type": "2순위 핵심 제품명 완전 일치 · DB 브랜드 접두어 허용",
            "match_confidence": brand_prefix_confidence,
        })
        return result

    # 2.7순위: 영문+숫자 고유 모델코드 완전 일치
    #
    # 대표 사례:
    #   OCR 제품명: R80 Thermogenic Hyper-Metabolizer
    #   DB 제품명 : ROCK STAR R80
    #
    # R80은 일반 설명문보다 식별력이 높은 고유 코드입니다.
    # DB에서 R80이 유일하게 한 행에만 존재하면 제품명 강한 일치로 처리합니다.
    model_code_result = find_unique_model_code_match(
        df=df,
        brand=brand,
        product_name=product_name,
        translated_product_name=translated_product_name,
        multilingual_candidates=multilingual_candidates,
    )

    if model_code_result["row"] is not None:
        result.update({
            "matched_row": model_code_result["row"],
            "match_type": (
                f"2순위 고유 모델코드 완전 일치 "
                f"({model_code_result['code'].upper()})"
            ),
            "match_confidence": model_code_result["confidence"],
        })
        return result

    # 모델코드가 여러 DB 행에 있어 확정하지 못한 경우에는 경고만 보존합니다.
    # 이후 제품명 고유사도와 성분 비교를 계속 수행합니다.
    if model_code_result["warning"]:
        result["match_warning"] = model_code_result["warning"]

    # 3순위: 제품명 고유사도 비교
    # DB를 위에서부터 훑어 첫 포함 행을 선택하면 unrelated 제품이 걸릴 수 있으므로,
    # 전체 DB의 점수를 계산한 후 가장 높은 행 하나만 후보로 남깁니다.
    best_fuzzy_row = None
    best_fuzzy_score = 0.0
    if user_candidates and "norm_product" in df.columns:
        for _, row in df.iterrows():
            db_norm = ensure_text(row.get("norm_product"), "")
            if len(db_norm) < 3:
                continue
            score = _best_product_similarity(user_candidates, db_norm)
            if score > best_fuzzy_score:
                best_fuzzy_score = score
                best_fuzzy_row = row

    # 0.90 이상만 제품명 파생/표기 차이 후보로 인정
    # 90% 기준은 제품명 오타·로마자 표기 차이는 허용하되,
    # 전혀 다른 짧은 제품명이 부분적으로 겹쳐 연결되는 것을 막기 위한 보수적 임계값입니다.
    # DB 품질과 현장 테스트 결과에 따라 0.88~0.95 범위에서 조정할 수 있으나,
    # 값을 낮추면 오탐이 증가하므로 변경 전 대표 사례 회귀 테스트가 필요합니다.
    if best_fuzzy_row is not None and best_fuzzy_score >= 0.90:
        result.update({
            "matched_row": best_fuzzy_row,
            "match_type": f"3순위 제품명 고유사도 일치 ({best_fuzzy_score:.0%})",
            "is_ambiguous_multilingual": True,
            "match_confidence": best_fuzzy_score,
        })
        return result

    # 4순위: 성분 비교
    # 물·카페인·비타민 등 흔한 원료는 여러 제품에 반복되므로 단독 매칭 근거에서 제외하고,
    # 길이가 충분한 구체 성분 토큰만 사용합니다.
    user_ingredient_tokens = []
    for ing in translated_ingredients or []:
        user_ingredient_tokens.extend(tokenize_text(ing.get("raw_name", "")))
        user_ingredient_tokens.extend(tokenize_text(ing.get("ko_name", "")))
    user_ingredient_tokens = list(dict.fromkeys(
        token for token in user_ingredient_tokens
        if len(token) >= 4 and token not in COMMON_INGREDIENT_TOKENS
    ))

    best_ingredient_row = None
    best_intersection = set()
    best_ing_product_score = 0.0

    if user_ingredient_tokens and "성분명" in df.columns:
        user_set = set(user_ingredient_tokens)
        for _, row in df.iterrows():
            db_tokens = {
                token for token in tokenize_text(row.get("성분명", ""))
                if len(token) >= 4 and token not in COMMON_INGREDIENT_TOKENS
            }
            intersection = user_set & db_tokens
            if not intersection:
                continue

            product_score = _best_product_similarity(
                user_candidates,
                ensure_text(row.get("norm_product"), ""),
            )

            # 더 많은 구체 성분 일치 > 더 긴 성분명 > 제품명 유사도 순으로 선택
            current_rank = (
                len(intersection),
                max((len(token) for token in intersection), default=0),
                product_score,
            )
            best_rank = (
                len(best_intersection),
                max((len(token) for token in best_intersection), default=0),
                best_ing_product_score,
            )
            if current_rank > best_rank:
                best_ingredient_row = row
                best_intersection = intersection
                best_ing_product_score = product_score

    if best_ingredient_row is not None:
        matched_ingredients = ", ".join(sorted(best_intersection))
        candidate_name = ensure_text(best_ingredient_row.get("제품명"), "확인 불가")
        result.update({
            "is_ingredient_only_match": True,
            "matched_ingredient_str": matched_ingredients,
            "ingredient_candidate_name": candidate_name,
            "ingredient_candidate_ingredient": ensure_text(best_ingredient_row.get("성분명"), "확인 불가"),
        })

        # 성분이 같더라도 제품명이 명확히 다르면 DB 상세 행을 연결하지 않습니다.
        # 제품명이 읽히지 않았거나 72% 이상 유사할 때만 성분 보조 매칭으로 행을 연결합니다.
        product_unreadable = not user_main_norm or product_name in {"확인 불가", ""}
        # 제품명을 읽지 못한 경우에는 성분을 보조 근거로 DB 행을 연결할 수 있습니다.
        # 제품명이 읽힌 경우에는 최소 72% 이상 유사해야만 성분 보조 연결을 허용합니다.
        # 72% 미만이면 EVP 3D ↔ orange + 유형의 오매칭 가능성이 높다고 보고 matched_row를 비웁니다.
        if product_unreadable or best_ing_product_score >= 0.72:
            result.update({
                "matched_row": best_ingredient_row,
                "match_type": "4순위 성분 일치 + 제품명 보조 확인",
                "match_confidence": max(0.72, best_ing_product_score),
                "match_warning": "제품명 또는 바코드 완전 일치가 아니므로 현품 성분표를 다시 확인해야 합니다.",
            })
        else:
            result.update({
                "matched_row": None,
                "match_type": "성분 후보 일치 · 제품명 불일치",
                "match_confidence": 0.0,
                "match_warning": (
                    f"OCR 제품명 '{ensure_text(product_name, '확인 불가')}'과 DB 제품명 "
                    f"'{candidate_name}'이 서로 달라 DB 상세정보를 확정 연결하지 않았습니다. "
                    f"성분 후보({matched_ingredients})만 별도 확인하세요."
                ),
            })
        return result

    # 상세내용의 임의 부분문자열 매칭은 오탐 위험이 높아 확정 매칭에서 제외
    return result


# -----------------------------------------------------------------------------
# 함수: get_clean_db_value
# 목적: DB 셀의 NaN/빈 값을 사용자에게 표시할 기본 문구로 보정합니다.
# 법적 근거·정보 출처·보류 사유는 업무 화면이 비지 않도록 항목별 기본값을 제공합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   DB 셀이 비어 있어도 결과 카드와 이메일에 이해 가능한 문구를 표시합니다.
# 입력값:
#   row: pandas Series 또는 dict 유사 객체
#   column_name: 표준 DB 컬럼명
# 반환값:
#   원본 셀 문자열 또는 항목별 기본 문구입니다.
# 주의:
#   기본 법적 근거 문구는 운영 정책 변경 시 담당자가 검토해야 합니다.
def get_clean_db_value(row, column_name):
    if row is None: return "해당 없음"
    val = row.get(column_name)
    if pd.isna(val) or str(val).strip().lower() == 'nan' or not str(val).strip():
        if column_name == '통관보류사유내용': return "위해 성분 검출 및 함유로 인한 현장 통관 보류 대상 물품"
        elif column_name == '정보출처': return "식품의약품안전처(식약처) 위해식품 반입차단 목록"
        elif column_name == '관련근거': return "수입식품안전관리 특별법 제25조의3 (위해식품등의 반입 차단)"
        return "확인 불가"
    return str(val)

@st.cache_data

# -----------------------------------------------------------------------------
# 함수: load_and_standardize_db
# 목적: CSV 또는 Excel DB를 읽고 서로 다른 컬럼명을 표준 컬럼명으로 통일합니다.
# 추가 컬럼: norm_product(제품명 비교용), norm_barcode(바코드 비교용).
# 캐시: 파일이 바뀌지 않는 동안 매 rerun마다 다시 읽지 않습니다.
# 실패 시 화면·로그에 오류를 기록하고 None을 반환합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 파일 탐색 순서:
#   1. 불법의약품DB.xlsx - Sheet1.csv
#   2. 불법의약품DB.xlsx
# 처리:
#   - 여러 기관·버전에서 다른 컬럼명을 표준명으로 rename합니다.
#   - norm_product를 생성해 제품명 비교를 빠르게 합니다.
#   - norm_barcode를 생성하되 NaN 문자열 오탐을 막기 위해 normalize_barcode()를 사용합니다.
# 캐시:
#   st.cache_data로 rerun마다 파일을 다시 읽지 않습니다.
# 반환값:
#   성공 시 DataFrame, 실패 시 None입니다.
# 오류:
#   화면에 간단한 오류를 표시하고 error_log.txt에는 전체 traceback을 기록합니다.
def load_and_standardize_db():
    try:
        try:
            df = pd.read_csv("불법의약품DB.xlsx - Sheet1.csv")
        except:
            df = pd.read_excel("불법의약품DB.xlsx")
            
        synonyms = {
            '등록번호': ['등록번호'],
            '제품명': ['제품명', '품명', '물품명', '상품명'],
            '성분명': ['성분명', '위해성분명', '성분', '원료명'],
            '바코드명': ['바코드명', '바코드', 'barcode', 'upc', 'ean', '제품코드', '상품코드'],
            '통관보류사유내용': ['통관보류사유내용'],
            '상세내용': ['상세내용'],
            '관련근거': ['관련근거'],
            '원본이미지URL': ['원본이미지URL']
        }
        renamed_cols = {}
        for std_key, synonym_list in synonyms.items():
            for col in df.columns:
                if col.strip().lower() in [s.strip().lower() for s in synonym_list]:
                    renamed_cols[col] = std_key
                    break
        df = df.rename(columns=renamed_cols)
        
        if '제품명' in df.columns:
            df['norm_product'] = df['제품명'].apply(normalize_product_name)
        if '바코드명' in df.columns:
            # NaN을 문자열 'nan'으로 바꾸지 않고, OCR과 동일한 규칙으로 정규화
            df['norm_barcode'] = df['바코드명'].apply(normalize_barcode)
            
        return df
    except Exception as e:
        error_details = traceback.format_exc()
        st.error(f"데이터베이스 파일 로드 및 구조 분석 실패: {e}")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n[DB LOAD ERROR] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{error_details}")
        return None

# 앱 시작 시 DB를 한 번 로드합니다. @st.cache_data 덕분에 rerun 시에는 캐시를 재사용합니다.
df_db = load_and_standardize_db()


# ------------------------------------------------------------
# 결과 화면 렌더링 유틸리티
# ------------------------------------------------------------

# -----------------------------------------------------------------------------
# 함수: esc
# 목적: OCR/DB 문자열이 HTML 태그로 해석되지 않도록 안전하게 이스케이프합니다.
# 이전에 <div class=...>가 원문으로 보이거나 레이아웃을 깨는 문제를 예방합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   OCR/DB 텍스트에 <, >, &, 따옴표가 포함돼도 HTML 태그나 속성으로 실행되지 않게 합니다.
# 반환값:
#   html.escape()가 적용된 문자열입니다.
# 사용 원칙:
#   unsafe_allow_html=True로 출력하는 모든 외부 데이터는 반드시 esc()를 거쳐야 합니다.
def esc(value):
    """HTML 출력용 안전 문자열 변환."""
    if value is None:
        return ""
    return html.escape(str(value))



# -----------------------------------------------------------------------------
# 함수: decision_meta
# 목적: 내부 판정 코드(금지/제한A/제한B/승인)를 화면용 라벨·아이콘·CSS·설명으로 변환합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   내부 판정 코드와 화면 표현을 분리합니다.
# 입력:
#   금지, 제한A, 제한B, 승인
# 반환:
#   label, icon, CSS class, subtitle을 가진 dict
# 장점:
#   판정 로직을 건드리지 않고 화면 문구와 색상을 수정할 수 있습니다.
def decision_meta(decision_situation):
    if decision_situation == "금지":
        return {
            "label": "반입 금지",
            "icon": "🔴",
            "class": "decision-danger",
            "subtitle": "DB 금지 정보와 명확히 일치하거나 고위험 성분이 확인되었습니다.",
        }
    if decision_situation in ["제한A", "제한B"]:
        subtitle = "성분 기반 검토 또는 현품 정보 보완이 필요한 물품입니다."
        if decision_situation == "제한B":
            subtitle = "제품명·성분·바코드 식별이 부족하여 보완 확인이 필요합니다."
        return {
            "label": "정밀 확인 필요",
            "icon": "⚠️",
            "class": "decision-warning",
            "subtitle": subtitle,
        }
    return {
        "label": "통관 가능",
        "icon": "🟢",
        "class": "decision-success",
        "subtitle": "현재 DB 기준으로 직접 일치하는 위해 규제 이력이 확인되지 않았습니다.",
    }



# -----------------------------------------------------------------------------
# 함수: render_kv_card
# 목적: 제목과 (항목명, 값) 목록을 공통 정보 카드 HTML로 렌더링합니다.
# 문자열을 한 줄씩 연결해 Markdown의 들여쓰기 코드블록 오인 문제를 방지합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   title: 카드 제목
#   rows: (항목명, 값) 튜플 목록
#   icon: 제목 앞 아이콘
# 처리:
#   각 값을 esc() 처리한 뒤 kv-row HTML로 조립합니다.
# 이유:
#   여러 줄 들여쓰기 HTML을 Markdown에 전달하면 코드블록으로 오인될 수 있어 문자열을 연속 연결합니다.
def render_kv_card(title, rows, icon=""):
    """정보 카드를 HTML이 원문으로 노출되지 않도록 공백 없이 렌더링합니다."""
    row_html = []
    for key, value in rows:
        row_html.append(
            f'<div class="kv-row">'
            f'<div class="kv-key">{esc(key)}</div>'
            f'<div class="kv-value">{esc(value)}</div>'
            f'</div>'
        )

    html = (
        '<div class="info-card">'
        f'<div class="card-title">{esc(icon)} {esc(title)}</div>'
        + "".join(row_html)
        + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 함수: render_result_header
# 목적: 각 검사 기록의 제품명·판정·브랜드·바코드·등록번호·매칭 방식을 상단 요약 카드로 표시합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   검사 기록의 가장 중요한 정보를 첫 화면에서 즉시 확인하게 합니다.
# 표시:
#   제품명, 판정 배지, 브랜드, 바코드, DB 등록번호, 매칭 방식
# idx:
#   0부터 시작하므로 화면에는 idx+1로 표시합니다.
def render_result_header(idx, product_name, decision_situation, brand, barcode, reg_num, match_type):
    meta = decision_meta(decision_situation)
    display_name = product_name if product_name and product_name != "확인 불가" else "미상 물품"
    html = (
        '<div class="inspection-header">'
        '<div class="inspection-topline">'
        '<div>'
        f'<div class="inspection-title">📦 [검사 기록 #{idx + 1}] {esc(display_name)}</div>'
        f'<div class="inspection-subtitle">{esc(meta["subtitle"])}</div>'
        '</div>'
        f'<div class="decision-pill {meta["class"]}">{meta["icon"]} {esc(meta["label"])}</div>'
        '</div>'
        '<div class="mini-grid">'
        f'<div class="mini-stat"><div class="mini-label">브랜드</div><div class="mini-value">{esc(brand)}</div></div>'
        f'<div class="mini-stat"><div class="mini-label">바코드</div><div class="mini-value">{esc(barcode)}</div></div>'
        f'<div class="mini-stat"><div class="mini-label">DB 등록번호</div><div class="mini-value">{esc(reg_num)}</div></div>'
        f'<div class="mini-stat"><div class="mini-label">매칭 방식</div><div class="mini-value">{esc(match_type)}</div></div>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 함수: get_match_display_text
# 목적: 내부 매칭 상태를 사용자에게 이해하기 쉬운 한 줄 문구로 변환합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   내부 판정 상태와 매칭 방식을 한 줄의 업무용 표현으로 변환합니다.
# 반환 예:
#   '위해물품 확정 · 1순위 바코드 완전 일치'
#   '확인 요망 · 성분 후보 일치 · 제품명 불일치'
#   'DB 규제 내역 없음'
def get_match_display_text(decision_situation, match_type):
    if decision_situation == "금지":
        return f"위해물품 확정 · {match_type}"
    if decision_situation == "제한B":
        return "현품 정보 식별 불가"
    if decision_situation == "승인":
        return "DB 규제 내역 없음"
    return f"확인 요망 · {match_type}"



# -----------------------------------------------------------------------------
# 함수: render_action_guide
# 목적: 판정 상태별 현장 후속 조치를 카드형 목록으로 안내합니다.
# 금지 확정과 성분 후보 일치를 구분하여 과도한 조치를 방지합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 목적:
#   AI 결과 자체보다 중요한 현장 후속조치를 판정별로 안내합니다.
# 금지:
#   통관 보류, 유치 사유 기록, 증빙 확보
# 제한A:
#   즉시 승인 금지, 성분 재확인, 필요 시 분석의뢰
# 제한B:
#   재촬영 또는 수기 확인
# 승인:
#   수량·자가사용 기준과 최종 현장 판단 확인
# 주의:
#   법령·매뉴얼 변경 시 이 문구도 함께 업데이트해야 합니다.
def render_action_guide(decision_situation, reg_num, matched_row, product_name, is_ingredient_only_match=False):
    if decision_situation == "금지":
        rows = [
            "통관을 보류하고 유치 절차로 전환합니다.",
            f"유치 사유에 DB 등록번호({reg_num})와 이미지 인식 제품명({product_name})을 함께 기록합니다.",
            "제품 전면, 성분표, 바코드 영역 사진을 증빙으로 보관합니다.",
        ]
    elif decision_situation == "제한A":
        rows = [
            "즉시 승인하지 않고 성분 기반 위해 가능성 확인 대상으로 분류합니다.",
            "성분 함유 여부가 불명확하면 전자통관시스템 분석의뢰를 검토합니다.",
        ]
        if is_ingredient_only_match:
            rows.insert(0, "제품명/바코드는 불일치하나 성분명이 DB 위해 성분명과 일치합니다.")
    elif decision_situation == "제한B":
        rows = [
            "통관 판단을 보류하고 제품 전면, 후면, 성분표, 바코드를 재촬영합니다.",
            "라벨 훼손 또는 식별 불가 시 제품명·바코드·성분을 수기로 확인해 DB와 다시 대조합니다.",
        ]
    else:
        rows = [
            "건강기능식품 및 의약품 자가사용 목적 인정 범위 등 수량 기준을 확인합니다.",
            "본 판정은 보조 판단이며 실제 통관 허용 여부는 현장 세관공무원의 최종 요건 확인에 따릅니다.",
        ]

    items = "".join(f"<li>{esc(item)}</li>" for item in rows)
    html = (
        '<div class="info-card">'
        '<div class="card-title">📋 현장 조치 가이드</div>'
        f'<ul class="action-list">{items}</ul>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 함수: render_ingredients_table
# 목적: OCR 성분을 휴대폰에서도 작게 볼 수 있는 4열 표로 표시합니다.
# 위해/의심 remark에는 별도 위험 배지 CSS를 적용합니다.
# -----------------------------------------------------------------------------
# [초상세 함수 설명]
# 입력값:
#   표준화된 translated_ingredients list[dict]
# 표시 열:
#   번호, 원문 성분명, 한글명, 비고
# 모바일:
#   표가 너무 넓으면 ingredient-table-wrap에서 가로 스크롤됩니다.
# 강조:
#   remark에 위해/의심/danger가 포함되면 위험 배지를 적용합니다.
def render_ingredients_table(translated_ingredients):
    """성분 화면을 모바일에서도 작게 보이는 압축 표 형태로 렌더링합니다."""
    if not translated_ingredients:
        st.info("성분표에서 추출된 성분 정보가 없습니다.")
        return

    rows = [
        '<div class="ingredient-table-wrap">'
        '<table class="ingredient-table">'
        '<thead><tr>'
        '<th class="col-no">#</th>'
        '<th class="col-raw">원문</th>'
        '<th class="col-ko">한글명</th>'
        '<th class="col-remark">비고</th>'
        '</tr></thead><tbody>'
    ]

    for idx, ing in enumerate(translated_ingredients, start=1):
        raw = ensure_text(ing.get("raw_name"), "확인 불가")
        ko = ensure_text(ing.get("ko_name"), "확인 불가")
        remark = ensure_text(ing.get("remark"), "일반명")
        danger_class = " ingredient-badge-danger" if any(kw in remark for kw in ["위해", "의심", "danger", "Danger"]) else ""
        rows.append(
            '<tr>'
            f'<td class="col-no">{idx}</td>'
            f'<td class="col-raw">{esc(raw)}</td>'
            f'<td class="col-ko">{esc(ko)}</td>'
            f'<td class="col-remark"><span class="ingredient-badge{danger_class}">{esc(remark)}</span></td>'
            '</tr>'
        )

    rows.append('</tbody></table></div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


# ------------------------------------------------------------
# 기존 검사 기록 화면 출력 (상단 누적부) - 카드형 디자인
# 실행 시점:
#   Streamlit rerun이 시작될 때마다 업로드 영역보다 먼저 실행됩니다.
# 데이터 출처:
#   분석 완료 직전에 st.session_state["history"]에 저장한 report_data 목록입니다.
# 화면 순서:
#   결과 헤더 -> OCR/DB 카드 -> DB 상세 -> 현장 조치 -> 성분표 -> 사진 대조
# 중요:
#   과거 세션에 잘못 매칭된 결과가 남아 있을 수 있으므로 매칭 로직을 변경한 뒤에는
#   '모든 검사 기록 삭제'를 누르고 새 사진으로 다시 검사해야 합니다.
# ------------------------------------------------------------
# 누적된 과거 검사 결과를 최신 업로드 영역보다 먼저 순서대로 렌더링합니다.
# 각 data 항목은 분석 완료 시 report_data 형태로 저장된 딕셔너리입니다.
for idx, data in enumerate(st.session_state["history"]):
    user_images = data.get("user_images", [])
    brand = data.get("brand", "확인 불가")
    product_name = data.get("product_name", "확인 불가")
    translated_product_name = data.get("translated_product_name", "")
    barcode = data.get("barcode", "바코드 확인 불가")
    translated_ingredients = data.get("translated_ingredients", [])
    matched_row = data.get("matched_row")
    match_type = data.get("match_type", "🟢 매칭되지 않음")
    decision_situation = data.get("decision_situation", "승인")
    is_ingredient_only_match = data.get("is_ingredient_only_match", False)
    is_ambiguous_multilingual = data.get("is_ambiguous_multilingual", False)
    matched_ingredient_str = data.get("matched_ingredient_str", "")
    ingredient_candidate_name = data.get("ingredient_candidate_name", "")
    ingredient_candidate_ingredient = data.get("ingredient_candidate_ingredient", "")
    match_warning = data.get("match_warning", "")
    match_confidence = float(data.get("match_confidence", 0.0) or 0.0)

    reg_num = (
        str(matched_row["등록번호"]).split(".")[0]
        if matched_row is not None and "등록번호" in matched_row and pd.notna(matched_row["등록번호"])
        else "등록번호 확인 불가"
    )
    display_match_text = get_match_display_text(decision_situation, match_type)

    render_result_header(idx, product_name, decision_situation, brand, barcode, reg_num, match_type)

    # 탭 분리 없이 결과 전체를 한 화면에 순서대로 표시합니다.
    st.markdown('<hr class="compact-hr">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        render_kv_card(
            "OCR 분석 정보",
            [
                ("촬영 사진", f"{len(user_images)}장"),
                ("식별 브랜드", brand),
                ("식별 제품명", product_name),
                ("식별 번역명", translated_product_name if translated_product_name else "해당없음"),
                ("식별 바코드", barcode),
            ],
            icon="🔎",
        )
    with col2:
        render_kv_card(
            "DB 대조 결과",
            [
                ("등록번호", reg_num),
                ("매칭 상태", display_match_text),
                ("성분 단독 매칭", "예" if is_ingredient_only_match else "아니오"),
                ("부분/파생 매칭", "예" if is_ambiguous_multilingual else "아니오"),
                ("일치 성분", matched_ingredient_str if matched_ingredient_str else "해당없음"),
                ("성분 후보 DB", ingredient_candidate_name if ingredient_candidate_name else "해당없음"),
                ("매칭 신뢰도", f"{match_confidence:.0%}" if match_confidence else "확정 안 함"),
            ],
            icon="🧾",
        )

    if matched_row is not None:
        render_kv_card(
            "불법의약품DB 상세 정보",
            [
                ("제품명(DB)", get_clean_db_value(matched_row, "제품명")),
                ("성분명(DB)", get_clean_db_value(matched_row, "성분명")),
                ("정보 출처", get_clean_db_value(matched_row, "정보출처")),
                ("통관 보류 사유", get_clean_db_value(matched_row, "통관보류사유내용")),
                ("상세 내용", get_clean_db_value(matched_row, "상세내용")),
                ("법적 관련 근거", get_clean_db_value(matched_row, "관련근거")),
            ],
            icon="📚",
        )
    else:
        if match_warning:
            st.warning(match_warning)
            if ingredient_candidate_name:
                render_kv_card(
                    "성분 기준 확인 후보 (DB 상세 확정 아님)",
                    [
                        ("후보 제품명(DB)", ingredient_candidate_name),
                        ("후보 성분명(DB)", ingredient_candidate_ingredient or "확인 불가"),
                        ("일치 성분", matched_ingredient_str or "확인 불가"),
                        ("처리", "제품명 불일치로 DB 상세정보·원본 이미지는 연결하지 않음"),
                    ],
                    icon="⚠️",
                )
        else:
            st.markdown(
                '<div class="soft-note">현재 DB 기준으로 제품명 또는 유효 바코드가 일치하는 위해 규제 이력이 확인되지 않았습니다.</div>',
                unsafe_allow_html=True,
            )

    render_action_guide(decision_situation, reg_num, matched_row, product_name, is_ingredient_only_match)

    suspicious_count = sum(
        1
        for ing in translated_ingredients
        if any(kw in str(ing.get("remark", "")).lower() for kw in ["위해", "의심", "danger"])
    )
    st.markdown('<hr class="compact-hr">', unsafe_allow_html=True)
    st.markdown(
        f"**🧪 성분 추출 결과:** 총 {len(translated_ingredients)}개"
        + (f" / 위해성분 의심 {suspicious_count}건" if suspicious_count else "")
    )
    render_ingredients_table(translated_ingredients)

    st.markdown('<hr class="compact-hr">', unsafe_allow_html=True)
    st.markdown("**📷 사진 대조**")
    render_user_original_images(user_images)

    if matched_row is not None and decision_situation != "제한B":
        render_db_original_images(matched_row.get("원본이미지URL", ""), key_prefix=f"history_{idx}")
    else:
        if decision_situation == "승인":
            st.success("통관 가능 판정으로 대조할 DB 위해사진이 없습니다.")
        else:
            st.info("대조할 DB 원본 사진이 없습니다.")


# ------------------------------------------------------------
# 📧 검사 결과 리포트 상세 내용 발송
# 이 구역은 history가 한 건 이상 있을 때만 표시됩니다.
# 이메일 본문은 누적된 모든 검사 건을 하나의 HTML 문서로 조립합니다.
# SMTP 정보는 Streamlit Secrets에서 읽으며 코드에 비밀번호를 저장하지 않습니다.
# 메일 발송 실패는 사용자 화면에 요약 오류를, error_log.txt에는 전체 traceback을 기록합니다.
# ------------------------------------------------------------
# 검사 기록이 한 건 이상 있을 때만 이메일 전송 UI를 보여줍니다.
# 리포트에는 OCR 정보, DB 매칭, 성분, 현장 조치가 포함됩니다.
if st.session_state["history"]:
    st.markdown("---")
    with st.expander("📧 전체 검사 리포트 메일로 전송하기 (공직자 통합메일)"):
        st.write("누적된 전체 검사 내용(성분, 조치 가이드 포함)을 `@korea.kr` 메일 주소로 발송합니다.")
        m_col1, m_col2 = st.columns([3, 1])
        with m_col1:
            email_id = st.text_input("아이디 입력", placeholder="예: user123", label_visibility="collapsed")
        with m_col2:
            st.markdown("<div style='margin-top: 10px; font-weight: bold; font-size: 16px;'>@korea.kr</div>", unsafe_allow_html=True)
            
        if st.button("📤 전체 상세 메일 발송", use_container_width=True):
            if not email_id.strip():
                st.warning("메일 아이디를 입력해주세요.")
            else:
                target_email = f"{email_id.strip()}@korea.kr"
                with st.spinner(f"'{target_email}' 주소로 상세 리포트를 전송 중입니다..."):
                    
                    html_content = f"""
                    <div style="font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: auto;">
                        <h2 style="color: #004d99; border-bottom: 2px solid #004d99; padding-bottom: 5px;">
                            📋 AI 위해식품 스마트 검사 결과 상세 리포트
                        </h2>
                        <p style="font-size: 14px;">본 리포트에는 현장 검사 앱에서 분석한 <b>총 {len(st.session_state["history"])}건</b>의 검사 기록 전체가 포함되어 있습니다.</p>
                    """
                    
                    for i, item in enumerate(st.session_state["history"]):
                        decision = item['decision_situation']
                        if decision == "금지": decision_badge = "<span style='color: white; background-color: #fa5252; padding: 4px 8px; border-radius: 4px;'>🔴 반입 금지</span>"
                        elif decision in ["제한A", "제한B"]: decision_badge = "<span style='color: white; background-color: #fab005; padding: 4px 8px; border-radius: 4px;'>⚠️ 제한 - 정밀 확인 필요</span>"
                        else: decision_badge = "<span style='color: white; background-color: #40c057; padding: 4px 8px; border-radius: 4px;'>🟢 통관 가능</span>"
                        
                        reg_num = str(item['matched_row']['등록번호']).split('.')[0] if item.get('matched_row') is not None and '등록번호' in item['matched_row'] and pd.notna(item['matched_row']['등록번호']) else "확인 불가"
                        
                        html_content += f"""
                        <div style="background-color: #ffffff; padding: 20px; margin-bottom: 25px; border-radius: 8px; border: 1px solid #ced4da; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                            <h3 style="margin-top: 0; color: #212529; border-bottom: 1px solid #dee2e6; padding-bottom: 10px;">
                                [검사 #{i+1}] {item['product_name']}
                            </h3>
                            <div style="margin-bottom: 15px;">
                                <b>판정 결과:</b> {decision_badge}
                            </div>
                            
                            <h4 style="margin-bottom: 5px; color: #0056b3;">1. OCR 분석 정보</h4>
                            <ul style="background-color: #f8f9fa; padding: 10px 10px 10px 30px; border-radius: 4px;">
                                <li><b>브랜드:</b> {item['brand']}</li>
                                <li><b>제품명:</b> {item['product_name']}</li>
                                <li><b>번역명:</b> {item['translated_product_name'] if item['translated_product_name'] else '해당없음'}</li>
                                <li><b>바코드:</b> {item['barcode']}</li>
                            </ul>

                            <h4 style="margin-bottom: 5px; color: #0056b3;">2. DB 대조 결과</h4>
                            <ul style="background-color: #f8f9fa; padding: 10px 10px 10px 30px; border-radius: 4px;">
                                <li><b>등록번호:</b> {reg_num}</li>
                                <li><b>DB 매칭 상태:</b> {item['match_type']}</li>
                                <li><b>성분 후보 DB:</b> {item.get('ingredient_candidate_name') or '해당없음'}</li>
                                <li><b>대조 설명:</b> {item.get('match_warning') or '해당없음'}</li>
                            </ul>
                        """
                        
                        if item.get('translated_ingredients'):
                            html_content += f"<h4 style='margin-bottom: 5px; color: #0056b3;'>▶ 성분 번역 결과 (총 {len(item['translated_ingredients'])}개)</h4>"
                            html_content += "<table style='width:100%; border-collapse: collapse; font-size: 13px; text-align: left; margin-bottom: 15px;'>"
                            html_content += "<tr style='background-color: #e9ecef;'><th style='padding: 8px; border: 1px solid #dee2e6;'>원문 성분명</th><th style='padding: 8px; border: 1px solid #dee2e6;'>한글 번역명</th><th style='padding: 8px; border: 1px solid #dee2e6;'>비고</th></tr>"
                            for ing in item['translated_ingredients']:
                                rem = str(ing.get('remark', '')).strip()
                                if not rem or rem.lower() == 'nan': rem = '일반명'
                                html_content += f"<tr><td style='padding: 8px; border: 1px solid #dee2e6;'>{ing.get('raw_name', '')}</td><td style='padding: 8px; border: 1px solid #dee2e6;'><b>{ing.get('ko_name', '')}</b></td><td style='padding: 8px; border: 1px solid #dee2e6;'>{rem}</td></tr>"
                            html_content += "</table>"
                            
                        html_content += "<h4 style='margin-bottom: 5px; color: #0056b3;'>3. 불법의약품DB 상세 정보</h4>"
                        if item.get('matched_row') is not None:
                            html_content += f"""
                            <ul style="background-color: #f8f9fa; padding: 10px 10px 10px 30px; border-radius: 4px; font-size: 13px;">
                                <li><b>제품명(DB):</b> {get_clean_db_value(item['matched_row'], '제품명')}</li>
                                <li><b>성분명(DB):</b> {get_clean_db_value(item['matched_row'], '성분명')}</li>
                                <li><b>정보 출처:</b> {get_clean_db_value(item['matched_row'], '정보출처')}</li>
                                <li><b>통관보류사유:</b> {get_clean_db_value(item['matched_row'], '통관보류사유내용')}</li>
                                <li><b>상세 내용:</b> {get_clean_db_value(item['matched_row'], '상세내용')}</li>
                                <li><b>관련 근거:</b> {get_clean_db_value(item['matched_row'], '관련근거')}</li>
                            </ul>
                            """
                        else:
                            html_content += "<p style='font-size: 13px; color: #495057;'>특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.</p>"
                        
                        guide_text = ""
                        if decision == "금지": guide_text = "<b>1. 통관 보류 및 유치 절차 전환</b><br><b>2. 유치 사유 기록 (위 DB 정보 연동)</b><br><b>3. 현품 및 증빙(사진) 확보 유지</b>"
                        elif decision == "제한A": guide_text = "<b>1. 즉시 승인 금지 (성분 기반 위해 가능성 확인)</b><br><b>2. 분석의뢰 절차 검토 요망</b>"
                        elif decision == "제한B": guide_text = "<b>1. 통관 판단 보류 및 정보 보완(재촬영) 요청</b><br><b>2. 현품 수기 확인 대조 필수</b>"
                        elif decision == "승인": guide_text = "<b>1. 수량 및 자가사용 목적(6병 이내 등) 기준 확인</b><br><b>2. 세관공무원 최종 요건 확인 후 승인 처리</b>"
                        
                        html_content += f"""
                            <h4 style="margin-bottom: 5px; color: #0056b3;">4. 현장 조치 가이드</h4>
                            <div style="background-color: #e3fafc; padding: 10px; border-radius: 4px; font-size: 14px; border-left: 4px solid #0c8599;">
                                {guide_text}
                            </div>
                        </div>
                        """
                        
                    html_content += "<hr><p style='font-size: 12px; color: #868e96; text-align: center;'>본 메일은 AI 위해식품 스마트 검사관 시스템에서 자동 발송되었습니다.</p></div>"
                    
                    smtp_server = st.secrets.get("SMTP_SERVER", "")
                    smtp_user = st.secrets.get("SMTP_USER", "")
                    smtp_pass = st.secrets.get("SMTP_PASSWORD", "")
                    smtp_port = st.secrets.get("SMTP_PORT", 587)
                    
                    if smtp_server and smtp_user and smtp_pass:
                        try:
                            msg = MIMEMultipart()
                            msg['From'] = smtp_user
                            msg['To'] = target_email
                            msg['Subject'] = f"[현장보고] AI 스마트 검사관 누적 결과 및 조치사항 ({len(st.session_state['history'])}건)"
                            msg.attach(MIMEText(html_content, 'html'))
                            
                            server = smtplib.SMTP(smtp_server, smtp_port)
                            server.starttls()
                            server.login(smtp_user, smtp_pass)
                            server.send_message(msg)
                            server.quit()
                            st.success(f"✅ 성공적으로 **{target_email}**로 전체 상세 리포트를 발송했습니다.")
                        except Exception as e:
                            error_details = traceback.format_exc()
                            st.error(f"❌ 메일 발송 중 오류가 발생했습니다: {e}")
                            with open("error_log.txt", "a", encoding="utf-8") as f:
                                f.write(f"\n{'='*50}\n[EMAIL SEND ERROR] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{error_details}")
                    else:
                        time.sleep(1)
                        st.info(f"💡 **(안내)** 시스템 우측 하단 `Manage app -> Settings -> Secrets`에 Gmail SMTP 정보를 등록해 주세요.")

# ------------------------------------------------------------
# 🆕 사진 업로드 및 OCR·DB 통합 분석 실행 구역
# 사용자가 업로드한 파일이 있을 때만 분석 버튼을 표시합니다.
# 분석 버튼 클릭 후 처리 순서:
#   1. 이미지 열기·회전 보정·축소·RGB 변환
#   2. Gemini 이미지 Part 생성
#   3. OCR 프롬프트와 함께 API 호출
#   4. JSON 파싱 및 자료형 표준화
#   5. DB 안전 매칭
#   6. 판정 상태 계산
#   7. report_data를 history에 저장
#   8. st.rerun()으로 결과 화면 재구성 (투 페이즈)
# ------------------------------------------------------------
st.markdown("---")

if st.session_state["history"]:
    if st.button("🗑️ 모든 검사 기록 삭제 (메모리 정리)", use_container_width=True):
        st.session_state["history"] = []
        for key in list(st.session_state.keys()):
            if key.startswith("cam_uploader_"):
                del st.session_state[key]
        st.session_state["uploader_id"] += 1
        st.rerun()

st.markdown(
    """
    <div class="mobile-upload-card">
        <div class="mobile-upload-title">📱 사진 선택</div>
        <div class="mobile-upload-hint">휴대폰에서는 먼저 <b>전면·후면·성분표·바코드</b>를 촬영해 둔 뒤, 아래에서 여러 장을 한 번에 선택하는 방식이 가장 안정적입니다.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Take Photo 전용 위젯은 사용하지 않고, 파일 업로더에서 여러 사진을 한 번에 선택합니다.
# 모바일에서는 운영체제의 사진 선택기/카메라 선택 메뉴가 열릴 수 있습니다.
uploaded_files = st.file_uploader(
    "사진 여러 장 선택", 
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"cam_uploader_{st.session_state['uploader_id']}",
    help="전면, 후면, 성분표, 바코드 사진을 함께 선택하면 정확도가 올라갑니다.",
)

input_files = list(uploaded_files) if uploaded_files else []

if input_files:
    st.info(f"📁 {len(input_files)}장의 새 화물 사진이 접수되었습니다.")
    if st.button("🔍 위해물품 통합 분석 시작", type="primary", use_container_width=True):
        
        status_box = st.empty()       
        decision_box = st.empty()     
        info_col_box = st.empty()     
        
        user_images = []
        image_parts = []

        for uploaded_file in input_files:
            src_image = Image.open(uploaded_file)
            src_image.thumbnail((1024, 1024))
            if src_image.mode != 'RGB':
                src_image = src_image.convert('RGB')
            user_images.append(src_image)
            image_parts.append(pil_image_to_gemini_part(src_image))
        # JSON 형식이 파이썬에서 깨지지 않도록 무조건 큰따옴표(\")를 쓰도록 지시문 유지
        # 모델 출력이 DB 비교에 바로 사용되므로 필드명과 자료형을 엄격히 지시합니다.
        # 특히 barcode는 list가 아닌 단일 문자열, multilingual_candidates는 여러 언어 후보 배열로 요구합니다.
        prompt = (
            "You are an expert Customs Forensic Intelligence OCR engine for Korean customs inspection. "
            "Inspect all uploaded product images carefully.\n\n"
            "CRITICAL OCR RULES:\n"
            "- Read Japanese, Chinese, Korean, and English labels exactly as printed.\n"
            "- Preserve Katakana, Hiragana, Kanji, Hangul, and Latin product names.\n"
            "- Extract brand names separately.\n"
            "- Preserve distinctive model codes exactly, including letter-number codes such as R80, X50, RX500, or EVP 3D.\n"
            "- When a package contains brand + model code + marketing descriptor, keep the model code in product_name and move generic phrases such as Thermogenic Hyper-Metabolizer to package_features when appropriate.\n"
            "- Include every detected alias, translated name, romanized name, likely DB name, and brand+model combination in multilingual_candidates.\n"
            "- Example: a package printed as ROCK STAR / R80 / Thermogenic Hyper-Metabolizer should include 'R80', 'ROCK STAR R80', and the full printed phrase as candidates.\n"
            "- Example: メジコン せき止め錠 Pro, Medicon Cough Tablet Pro, 메지콘 기침약 프로 must be treated as candidate aliases.\n"
            "- Extract barcode numbers only when clearly visible.\n"
            "- CRITICAL: Return barcode as one single string only. Never return barcode as an array/list.\n"
            "- Extract all ingredients comprehensively, including sub-ingredients inside parentheses.\n\n"
            "FIELD RULES:\n"
            "1. product_name: core shortest possible commercial product name or distinctive model code; do not use only a generic marketing/category phrase.\n"
            "2. translated_product_name: Korean translated product name if possible.\n"
            "3. multilingual_candidates: FULL product names including flavors, taglines, modifiers, original scripts, romanization, and translated variants.\n"
            "4. translated_ingredients: all ingredients. Categorize remark strictly as one of: "
            "'위해성분 의심', '화학명', '식물명', '일반명', '기타 원료', '확인 불가'.\n\n"
            "Respond ONLY as ONE valid JSON object. Do not use markdown. Do not add explanations. "
            "Never omit commas between array items or fields. Use double quotes only.\n"
            "{\n"
            "  \"brand\": \"string\",\n"
            "  \"product_name\": \"string\",\n"
            "  \"translated_product_name\": \"string\",\n"
            "  \"barcode\": \"single string only\",\n"
            "  \"multilingual_candidates\": [\"string\"],\n"
            "  \"translated_ingredients\": [ {\"raw_name\": \"string\", \"ko_name\": \"string\", \"remark\": \"string\"} ],\n"
            "  \"package_features\": \"string\"\n"
            "}"
        )

        # 여러 이미지 Part와 하나의 텍스트 프롬프트를 동일한 user Content로 묶어 전송합니다.
        ai_contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part.from_text(text=prompt)]
            )
        ]

        brand, product_name, translated_product_name, barcode, translated_ingredients, package_features, multilingual_candidates = '확인 불가', '확인 불가', '', '바코드 확인 불가', [], '', []
        
        status_box.status(f"🚀 1단계: OCR 비전 모델 `{OCR_PRIMARY_MODEL}`이 제품 사진을 판독하고 있습니다...", expanded=False)
        
        try:
            if client is None:
                st.error("API 키가 올바르게 설정되지 않아 AI를 호출할 수 없습니다.")
                st.stop()
                
            # 기본 모델부터 순서대로 OCR을 시도하며 성공한 모델명도 함께 받습니다.
            ocr_result, used_gemini_model = generate_ocr_with_model_fallback(
                model=OCR_PRIMARY_MODEL,
                contents=ai_contents,
            )
            status_box.status(
                f"✅ 1단계 완료: `{used_gemini_model}` 모델이 이미지를 판독했습니다.",
                expanded=False,
                state="complete",
            )
            
            # 모델이 예상과 다른 자료형을 반환해도 안전하게 표준 문자열/목록으로 변환합니다.
            brand = ensure_text(ocr_result.get('brand'), '확인 불가')
            product_name = ensure_text(ocr_result.get('product_name'), '확인 불가')
            translated_product_name = ensure_text(ocr_result.get('translated_product_name'), '')
            barcode = ensure_text(ocr_result.get('barcode'), '바코드 확인 불가')
            translated_ingredients = ensure_ingredient_list(ocr_result.get('translated_ingredients'))
            package_features = ensure_text(ocr_result.get('package_features'), '')
            multilingual_candidates = ensure_text_list(ocr_result.get('multilingual_candidates'))
            
        except Exception as e:
            # [🔥 에러 로깅 추가] 에러 발생 시 파일 저장 및 화면에 상세 내역 펼침창 제공
            error_details = traceback.format_exc()
            st.error(f"⚠️ 비전 엔진 통합 판독 중 예외 발생: {e}")
            with st.expander("🛠️ 상세 오류 내역 보기 (디버깅용)"):
                st.code(error_details, language="python")
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n{'='*50}\n[VISION AI ERROR] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{error_details}")
            st.stop() # 에러 시 무리하게 2단계를 진행하지 않고 즉시 중단

        with info_col_box.container():
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                **1. OCR 분석 정보 (1단계 완료)**
                * 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{brand}</span>
                * 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{product_name}</span>
                * 식별된 바코드: <span style="background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{barcode}</span>
                """, unsafe_allow_html=True)
            with col2:
                st.info("⏳ 2단계: 식약처 위해물품 DB와 교차 검증 중입니다...")

        status_box.status("🔍 2단계: 위해 의약품 DB와 교차 검증하고 있습니다...", expanded=False)
        
        # OCR 결과를 안전 매칭 함수에 전달합니다.
        # 이 함수는 성분 하나만 같다는 이유로 임의의 DB 행을 확정하지 않습니다.
        match_result = find_safe_db_match(
            df=df_db,
            brand=brand,
            product_name=product_name,
            translated_product_name=translated_product_name,
            barcode=barcode,
            multilingual_candidates=multilingual_candidates,
            translated_ingredients=translated_ingredients,
        )

        matched_row = match_result["matched_row"]
        match_type = match_result["match_type"]
        is_ingredient_only_match = match_result["is_ingredient_only_match"]
        is_ambiguous_multilingual = match_result["is_ambiguous_multilingual"]
        matched_ingredient_str = match_result["matched_ingredient_str"]
        ingredient_candidate_name = match_result["ingredient_candidate_name"]
        ingredient_candidate_ingredient = match_result["ingredient_candidate_ingredient"]
        match_warning = match_result["match_warning"]
        match_confidence = match_result["match_confidence"]

        # 제품명·바코드·성분이 모두 없으면 통관 가능으로 오판하지 않고 재촬영이 필요한 제한B로 분류합니다.
        is_totally_unreadable = (
            product_name in ["확인 불가", ""]
            and barcode in ["바코드 확인 불가", ""]
            and not translated_ingredients
        )

        # 판정 원칙: 약한 성분 후보 또는 제품명 불일치만으로 '반입 금지' 확정 금지
        if is_totally_unreadable:
            decision_situation = "제한B"
        elif matched_row is not None and match_type in [
            "1순위 바코드 완전 일치",
            "2순위 제품명 완전 일치",
            "2순위 핵심 제품명 완전 일치 · DB 브랜드 접두어 허용",
        ] or (
            matched_row is not None
            and str(match_type).startswith("2순위 고유 모델코드 완전 일치")
        ):
            # 브랜드가 OCR에서 빠졌더라도 핵심 제품명이 DB 이름의 끝부분과 단어 단위로
            # 완전히 일치한 경우에는 일반 fuzzy가 아니라 강한 제품명 식별 근거로 처리합니다.
            decision_situation = "금지"
        elif matched_row is not None or is_ingredient_only_match:
            decision_situation = "제한A"
        else:
            decision_situation = "승인"

        if decision_situation == "금지":
            decision_box.error("결과: 🔴 반입 금지")
            match_badge = 'background-color: #fff5f5; color: #fa5252; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
            display_match_text = f"🔴 [{match_type}] 위해물품 확정"
        elif decision_situation in ["제한A", "제한B"]:
            decision_box.warning("결과: ⚠️ 제한 - 정밀 확인 필요")
            match_badge = 'background-color: #fff9db; color: #fab005; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
            display_match_text = "⚠️ 현품 정보 식별 불가" if decision_situation == "제한B" else f"⚠️ [{match_type}] 확인 요망"
        else:
            decision_box.success("결과: 🟢 통관 가능")
            match_badge = 'background-color: #ebfbee; color: #40c057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
            display_match_text = "🟢 DB 규제 내역 없음"

        reg_num = str(matched_row['등록번호']).split('.')[0] if matched_row is not None and '등록번호' in matched_row and pd.notna(matched_row['등록번호']) else "등록번호 확인 불가"

        with info_col_box.container():
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                **1. OCR 분석 정보 (최종 확인)**
                * 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{brand}</span>
                * 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{product_name}</span>
                * 식별된 번역명: <span style="background-color: #faf0f6; color: #ae3ec9; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{translated_product_name if translated_product_name else '해당없음'}</span>
                * 식별된 바코드: <span style="background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{barcode}</span>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                **2. DB 대조 결과**
                * 등록번호: <span style="background-color: #e8f7ff; color: #1c7ed6; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{reg_num}</span>
                * DB 매칭 상태: <span style="{match_badge}">{display_match_text}</span>
                * 매칭 신뢰도: <span style="background-color: #f1f5f9; color: #334155; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{f"{match_confidence:.0%}" if match_confidence else "확정 안 함"}</span>
                """, unsafe_allow_html=True)
            # match_warning은 report_data에 저장한 뒤 rerun된 최종 결과 화면에서 한 번만 표시합니다.
            # 여기에서도 st.warning()을 호출하면 처리 직후 화면과 누적 결과 화면에서
            # 같은 문구가 연속으로 보일 수 있으므로 임시 표시를 생략합니다.

        status_box.status("⚡ 3단계: 성분 번역 맵 구축 및 조치 표준 가이드를 통합 매핑 중입니다...", expanded=False)
        
        # 화면 rerun 후에도 결과를 재표시할 수 있도록 OCR·DB·판정·이미지를 한 딕셔너리로 저장합니다.
        report_data = {
            "user_images": user_images,
            "brand": brand,
            "product_name": product_name,
            "translated_product_name": translated_product_name,
            "barcode": barcode,
            "translated_ingredients": translated_ingredients,
            "matched_row": matched_row,
            "match_type": match_type,
            "decision_situation": decision_situation,
            "is_ingredient_only_match": is_ingredient_only_match,
            "is_ambiguous_multilingual": is_ambiguous_multilingual,
            "matched_ingredient_str": matched_ingredient_str,
            "ingredient_candidate_name": ingredient_candidate_name,
            "ingredient_candidate_ingredient": ingredient_candidate_ingredient,
            "match_warning": match_warning,
            "match_confidence": match_confidence,
            "gemini_model_used": used_gemini_model,
        }
        
        # 새 검사 기록을 누적한 뒤 업로더 key를 변경하여 이전 선택 파일을 초기화합니다.
        st.session_state["history"].append(report_data)
        st.session_state["uploader_id"] += 1
        
        status_box.empty()
        st.rerun()
