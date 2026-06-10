import streamlit as st
import pandas as pd
import json
from PIL import Image
import requests
import io
import urllib3
import time
import re
import os
import base64
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# [에러 로깅용 모듈 추가]
import traceback
import datetime
import unicodedata

# [최신 Gemini API] Google GenAI SDK 규격
from google import genai
from google.genai import types


# ------------------------------------------------------------
# 사진 대조 화면 공통 크기 설정
# - 현품 사진과 DB 원본 이미지를 동일한 카드/이미지 크기로 표시
# - 요청 반영: 기존 96px 대비 3배 크기(288px) 썸네일
# ------------------------------------------------------------
COMPARE_IMAGE_SIZE_PX = 288

# [보안] 정부 서버 SSL 인증서 미인증 경고 문구 출력 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [설정] 웹 페이지 제목 및 모바일 레이아웃 최적화
st.set_page_config(page_title="AI 위해식품 스마트 검사관", layout="centered")

# 모바일 UI 가속 및 결과 화면 가독성 향상을 위한 CSS 주입
st.markdown("""
    <style>
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

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2.5rem;
        max-width: 980px;
    }

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

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()


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
# Gemini 최신 모델 설정
# ------------------------------------------------------------
# 기본값: 최신 Flash 계열 모델
# 필요 시 Streamlit Secrets에서 GEMINI_MODEL 값으로 모델 변경 가능
# 기본값: Gemini 3.5 Flash
GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash")

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

if "history" not in st.session_state:
    st.session_state["history"] = []
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0

# --- 유틸리티 함수 모음 ---
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


def pil_image_to_gemini_part(image: Image.Image):
    """
    PIL 이미지를 Gemini API 멀티모달 입력 Part로 변환.
    PIL 객체를 직접 넘기는 방식보다 Streamlit 배포 환경에서 안정적입니다.
    """
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


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


def _gemini_safety_settings():
    """Gemini 안전 설정 공통값."""
    return [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]


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


def _get_fallback_models(primary_model: str) -> list[str]:
    """
    Gemini 3.5 Flash가 일시적 과부하(503)일 때 자동 대체할 모델 목록입니다.
    Streamlit Secrets에 GEMINI_FALLBACK_MODELS="gemini-2.5-flash,gemini-2.5-flash-lite"처럼 지정 가능.
    """
    fallback_secret = st.secrets.get("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite")
    models = [primary_model]
    for item in str(fallback_secret).split(','):
        m = item.strip()
        if m and m not in models:
            models.append(m)
    return models


def _is_retryable_gemini_error(error: Exception) -> bool:
    """503/429/일시 과부하 계열 오류만 재시도 대상으로 판단합니다."""
    error_text = str(error).lower()
    retry_keywords = [
        "503",
        "unavailable",
        "high demand",
        "try again later",
        "temporarily",
        "timeout",
        "deadline",
        "rate limit",
        "429",
        "resource_exhausted",
    ]
    return any(k in error_text for k in retry_keywords)


def generate_content_with_sdk_compatibility(model, contents):
    """
    Gemini 호출 안정화 버전.
    - response_format은 SDK 버전에 따라 오류가 나므로 사용하지 않음
    - response_mime_type="application/json" 방식으로 고정
    - 503 UNAVAILABLE / high demand 발생 시 짧게 재시도 후 fallback 모델로 자동 전환
    """
    last_error = None
    candidate_models = _get_fallback_models(model)

    for model_index, candidate_model in enumerate(candidate_models):
        max_attempts = 2 if model_index == 0 else 1
        for attempt in range(max_attempts):
            try:
                if candidate_model != model:
                    st.info(f"Gemini 기본 모델이 혼잡하여 `{candidate_model}` 모델로 자동 재시도합니다.")

                response = client.models.generate_content(
                    model=candidate_model,
                    contents=contents,
                    config=build_gemini_generation_config_legacy(),
                )
                st.session_state["_last_gemini_model_used"] = candidate_model
                return response

            except Exception as error:
                last_error = error
                if not _is_retryable_gemini_error(error):
                    raise
                if attempt + 1 < max_attempts:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break

    raise last_error

def _strip_markdown_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json|JSON)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    return text


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


def _regex_json_string(text: str, key: str, default: str = "") -> str:
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text or "", re.S)
    if not m:
        return default
    try:
        return json.loads('"' + m.group(1) + '"')
    except Exception:
        return m.group(1)


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


def normalize_barcode(value):
    """barcode가 list/int/None으로 와도 DB 대조 가능한 문자열로 변환합니다."""
    text = ensure_text(value, "")
    if not text or text == "바코드 확인 불가":
        return ""
    # 숫자와 영문만 남김. 하이픈/공백 제거.
    return re.sub(r"[^0-9a-zA-Z]", "", text).lower()

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
            df['norm_barcode'] = df['바코드명'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
            
        return df
    except Exception as e:
        error_details = traceback.format_exc()
        st.error(f"데이터베이스 파일 로드 및 구조 분석 실패: {e}")
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{'='*50}\n[DB LOAD ERROR] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{error_details}")
        return None

df_db = load_and_standardize_db()


# ------------------------------------------------------------
# 결과 화면 렌더링 유틸리티
# ------------------------------------------------------------
def esc(value):
    """HTML 출력용 안전 문자열 변환."""
    if value is None:
        return ""
    return html.escape(str(value))


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

def get_match_display_text(decision_situation, match_type):
    if decision_situation == "금지":
        return f"위해물품 확정 · {match_type}"
    if decision_situation == "제한B":
        return "현품 정보 식별 불가"
    if decision_situation == "승인":
        return "DB 규제 내역 없음"
    return f"확인 요망 · {match_type}"


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
# ------------------------------------------------------------
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
        st.markdown(
            '<div class="soft-note">현재 DB 기준으로 일치하는 위해 규제 이력이 확인되지 않았습니다.</div>',
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
# ------------------------------------------------------------
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
# 🆕 초고속 업로드 및 실시간 렌더링 엔진 (투 페이즈)
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
        prompt = (
            "You are an expert Customs Forensic Intelligence OCR engine for Korean customs inspection. "
            "Inspect all uploaded product images carefully.\n\n"
            "CRITICAL OCR RULES:\n"
            "- Read Japanese, Chinese, Korean, and English labels exactly as printed.\n"
            "- Preserve Katakana, Hiragana, Kanji, Hangul, and Latin product names.\n"
            "- Extract brand names separately.\n"
            "- Include every detected alias, translated name, romanized name, and likely DB name in multilingual_candidates.\n"
            "- Example: メジコン せき止め錠 Pro, Medicon Cough Tablet Pro, 메지콘 기침약 프로 must be treated as candidate aliases.\n"
            "- Extract barcode numbers only when clearly visible.\n"
            "- CRITICAL: Return barcode as one single string only. Never return barcode as an array/list.\n"
            "- Extract all ingredients comprehensively, including sub-ingredients inside parentheses.\n\n"
            "FIELD RULES:\n"
            "1. product_name: core shortest possible product name.\n"
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

        ai_contents = [
            types.Content(
                role="user",
                parts=image_parts + [types.Part.from_text(text=prompt)]
            )
        ]

        brand, product_name, translated_product_name, barcode, translated_ingredients, package_features, multilingual_candidates = '확인 불가', '확인 불가', '', '바코드 확인 불가', [], '', []
        
        status_box.status(f"🚀 1단계: Google Gemini 최신 비전 엔진({GEMINI_MODEL})이 이미지를 판독하고 있습니다...", expanded=False)
        
        try:
            if client is None:
                st.error("API 키가 올바르게 설정되지 않아 AI를 호출할 수 없습니다.")
                st.stop()
                
            response = generate_content_with_sdk_compatibility(
                model=GEMINI_MODEL,
                contents=ai_contents,
            )

            ocr_result = parse_gemini_json_response(response)
            
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
        
        matched_row = None
        match_type = "🟢 매칭되지 않음"
        is_ingredient_only_match = False
        is_ambiguous_multilingual = False
        matched_ingredient_str = ""
        
        if df_db is not None:
            user_norm_candidates = [normalize_product_name(c) for c in multilingual_candidates if c]
            user_main_norm = normalize_product_name(product_name)
            if user_main_norm and user_main_norm not in user_norm_candidates:
                user_norm_candidates.append(user_main_norm)
                
            norm_user_barcode = normalize_barcode(barcode)
            user_ingredient_tokens = []
            for ing in translated_ingredients:
                user_ingredient_tokens.extend(tokenize_text(ing.get('raw_name', '')))
                user_ingredient_tokens.extend(tokenize_text(ing.get('ko_name', '')))
                
            if norm_user_barcode and 'norm_barcode' in df_db.columns:
                b_match = df_db[df_db['norm_barcode'] == norm_user_barcode]
                if not b_match.empty:
                    matched_row = b_match.iloc[0]
                    match_type = "1순위 바코드 일치"

            if matched_row is None and user_norm_candidates and 'norm_product' in df_db.columns:
                for idx_row, row in df_db.iterrows():
                    db_norm = str(row['norm_product'])
                    if db_norm in user_norm_candidates or any(uc == db_norm for uc in user_norm_candidates if uc):
                        matched_row = row
                        match_type = "2/3순위 제품명 다국어 정규화 일치"
                        break

            if matched_row is None and 'norm_product' in df_db.columns:
                for idx_row, row in df_db.iterrows():
                    db_norm = str(row['norm_product'])
                    if not db_norm: continue
                    if any(((uc in db_norm) or (db_norm in uc)) and len(uc) >= 4 for uc in user_norm_candidates if uc):
                        matched_row = row
                        is_ambiguous_multilingual = True
                        match_type = "제품명 파생/부분 포함 (맛, 제형 차이 의심)"
                        break

            if matched_row is None and user_ingredient_tokens and '성분명' in df_db.columns:
                for idx_row, row in df_db.iterrows():
                    db_ing_tokens = tokenize_text(row['성분명'])
                    intersection = set(user_ingredient_tokens) & set(db_ing_tokens)
                    if intersection:
                        matched_row = row
                        is_ingredient_only_match = True
                        matched_ingredient_str = ', '.join(intersection)
                        match_type = "4순위 성분명 토큰 일치"
                        break

            if matched_row is None:
                for idx_row, row in df_db.iterrows():
                    detail_str = str(row.get('상세내용', '')).lower() + str(row.get('관련근거', '')).lower() + str(row.get('통관보류사유내용', '')).lower()
                    if user_main_norm and user_main_norm in detail_str:
                        matched_row = row
                        match_type = "5순위 상세 기재내역 매칭"
                        break

        decision_situation = "승인"
        is_high_risk_ingredient = False
        
        if matched_row is not None:
            reason_pool = str(matched_row.get('통관보류사유내용', '')).lower() + str(matched_row.get('관련근거', '')).lower()
            if any(kw in reason_pool for kw in ['마약', '향정', '향정신성', '대마', '코데인', '디히드로코데인', '반입금지', '반입 금지']):
                is_high_risk_ingredient = True

        is_totally_unreadable = (product_name in ['확인 불가', ''] and barcode in ['바코드 확인 불가', ''] and not translated_ingredients)

        if is_totally_unreadable:
            decision_situation = "제한B"
        elif matched_row is not None and (match_type in ["1순위 바코드 일치", "2/3순위 제품명 다국어 정규화 일치"] or is_high_risk_ingredient):
            decision_situation = "금지"
        elif matched_row is not None and (is_ingredient_only_match or is_ambiguous_multilingual or match_type in ["5순위 상세 기재내역 매칭", "제품명 파생/부분 포함 (맛, 제형 차이 의심)"]):
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
                """, unsafe_allow_html=True)

        status_box.status("⚡ 3단계: 성분 번역 맵 구축 및 조치 표준 가이드를 통합 매핑 중입니다...", expanded=False)
        
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
        }
        
        st.session_state["history"].append(report_data)
        st.session_state["uploader_id"] += 1
        
        status_box.empty()
        st.rerun()
