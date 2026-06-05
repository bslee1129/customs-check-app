import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import requests
import io
import urllib3
import time
import re
import os
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# [보안] 정부 서버 SSL 인증서 미인증 경고 문구 출력 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [설정] 웹 페이지 제목 및 모바일 레이아웃 최적화
st.set_page_config(page_title="AI 위해식품 스마트 검사관", layout="centered")

# 모바일 UI 가속 및 가독성 향상을 위한 CSS 주입
st.markdown("""
    <style>
    .stFileUploader {
        padding: 10px;
        background-color: #f8f9fa;
        border-radius: 12px;
        border: 2px dashed #007bff;
    }
    div[data-testid="stFileUploaderDropzone"] button {
        width: 100% !important;
        height: 60px !important;
        font-size: 18px !important;
        font-weight: bold !important;
        background-color: #007bff !important;
        color: white !important;
        border-radius: 8px !important;
    }
    .stButton>button {
        width: 100%;
        height: 55px;
        font-size: 18px !important;
        font-weight: bold !important;
    }
    </style>
""", unsafe_allow_html=True)

# 로고와 제목 인라인 배치
logo_path = "Emblem_of_the_Korea_Customs_Service.svg.png"

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

if os.path.exists(logo_path):
    img_src = f"data:image/png;base64,{get_base64_of_bin_file(logo_path)}"
else:
    img_src = "https://raw.githubusercontent.com/bslee1129/customs-check-app/main/Emblem_of_the_Korea_Customs_Service.svg.png"

# 모바일 화면 반응형 타이틀 적용
st.markdown(f"""
    <div style="
        display: flex; 
        align-items: center; 
        gap: 10px; 
        margin-top: 10px; 
        margin-bottom: 5px;
        flex-wrap: wrap;
    ">
        <img src="{img_src}" style="height: 32px; width: auto; object-fit: contain; flex-shrink: 0;">
        <h1 style="
            margin: 0; 
            padding: 0; 
            font-size: clamp(20px, 18px + 1vw, 28px); 
            font-weight: 700; 
            line-height: 1.2;
            word-break: keep-all;
        ">AI 위해식품 스마트 검사관</h1>
    </div>
""", unsafe_allow_html=True)

st.caption("💡 **[촬영 가이드]** 제품의 **전면, 후면, 성분표, 바코드**가 선명하게 보이도록 여러 장을 한 번에 올려주세요. (검사 기록은 계속 누적됩니다.)")

# API 키 설정
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
if gemini_key:
    genai.configure(api_key=gemini_key)
else:
    st.error("⚠️ 오른쪽 하단 Manage app -> Settings -> Secrets에 GEMINI_API_KEY를 등록해 주세요.")

if "history" not in st.session_state:
    st.session_state["history"] = []
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0

# --- 유틸리티 함수 모음 ---
def normalize_product_name(text):
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == 'nan':
        return ""
    val = str(text).lower()
    noise_patterns = [
        r'fruit\s*punch', r'blue\s*raz', r'sour\s*candy',
        r'\d+g', r'\d+\.?\d*oz', r'\d+\s*capsules', r'\d+\s*tablets', r'\d+\s*servings',
        r'capsules', r'tablets', r'powder', r'錠', r'カプセル', r'顆粒', r'액제', r'정제', r'캡슐', r'과립'
    ]
    for pattern in noise_patterns:
        val = re.sub(pattern, '', val)
    val = re.sub(r'[\s\-\./\s:\(\)\+·_\*&%!@#~`=\[\]\{\}\\\|\'\";\?]', '', val)
    return val

def tokenize_text(text):
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == 'nan':
        return []
    tokens = re.split(r'[,/\n;\(\)\+·]', str(text))
    cleaned_tokens = []
    for t in tokens:
        c = t.strip().lower().replace(" ", "").replace("-", "").replace("hcl", "").replace("hydrochloride", "").replace("염산염", "")
        if c:
            cleaned_tokens.append(c)
    return cleaned_tokens

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
        st.error(f"데이터베이스 파일 로드 및 구조 분석 실패: {e}")
        return None

df_db = load_and_standardize_db()

# 기존 검사 기록 화면 출력 (상단 누적부)
for idx, data in enumerate(st.session_state["history"]):
    st.markdown("---")
    st.markdown(f"## 📦 [검사 기록 #{idx+1}] {data['product_name'] if data['product_name'] != '확인 불가' else '미상 물품'}")
    
    user_images = data["user_images"]
    brand = data["brand"]
    product_name = data["product_name"]
    translated_product_name = data["translated_product_name"]
    barcode = data["barcode"]
    translated_ingredients = data["translated_ingredients"]
    matched_row = data["matched_row"]
    match_type = data["match_type"]
    decision_situation = data["decision_situation"]
    is_ingredient_only_match = data["is_ingredient_only_match"]
    is_ambiguous_multilingual = data["is_ambiguous_multilingual"]
    matched_ingredient_str = data["matched_ingredient_str"]
    
    if decision_situation == "금지":
        final_decision = "🔴 반입 금지"
        display_func = st.error
        match_badge = 'background-color: #fff5f5; color: #fa5252; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
    elif decision_situation == "제한A":
        final_decision = "⚠️ 제한 - 성분 기반 검토 및 정밀검사 필요"
        display_func = st.warning
        match_badge = 'background-color: #fff9db; color: #fab005; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
    elif decision_situation == "제한B":
        final_decision = "⚠️ 제한 - 현품 식별 불가 / 정보 보완 필요"
        display_func = st.warning
        match_badge = 'background-color: #fff9db; color: #fab005; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'
    else:
        final_decision = "🟢 통관 가능"
        display_func = st.success
        match_badge = 'background-color: #ebfbee; color: #40c057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;'

    display_func(f"결과: {final_decision}")
        
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **1. OCR 분석 정보 (사진 {len(user_images)}장 취합 결과)**
        * 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{brand}</span>
        * 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{product_name}</span>
        * 식별된 번역명: <span style="background-color: #faf0f6; color: #ae3ec9; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{translated_product_name if translated_product_name else '해당없음'}</span>
        * 식별된 바코드: <span style="background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{barcode}</span>
        """, unsafe_allow_html=True)
    with col2:
        reg_num = str(matched_row['등록번호']).split('.')[0] if matched_row is not None and '등록번호' in matched_row and pd.notna(matched_row['등록번호']) else "등록번호 확인 불가"
        display_match_text = f"🔴 [{match_type}] 위해물품 확정" if "🔴" in match_badge or decision_situation=="금지" else f"⚠️ [{match_type}] 확인 요망"
        if decision_situation == "승인": display_match_text = "🟢 DB 규제 내역 없음"
        if decision_situation == "제한B": display_match_text = "⚠️ 현품 정보 식별 불가"
            
        st.markdown(f"""
        **2. DB 대조 결과**
        * 등록번호: <span style="background-color: #e8f7ff; color: #1c7ed6; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{reg_num}</span>
        * DB 매칭 상태: <span style="{match_badge}">{display_match_text}</span>
        """, unsafe_allow_html=True)

    if translated_ingredients:
        st.markdown("---")
        suspicious_count = sum(1 for ing in translated_ingredients if any(kw in str(ing.get('remark', '')).lower() for kw in ['위해', '의심', 'danger']))
        expander_title = f"🧪 [성분 번역 결과] 총 {len(translated_ingredients)}개 성분 검출"
        if suspicious_count > 0: expander_title += f" (⚠️ 위해성분 의심 {suspicious_count}건 포함)"
            
        with st.expander(expander_title, expanded=(suspicious_count > 0)):
            table_html = "<table style='width:100%; border-collapse: collapse; font-size: 13px; font-family: sans-serif;'>"
            table_html += "<tr style='background-color: #f1f3f5;'><th style='padding: 6px; border: 1px solid #dee2e6; text-align: left;'>원문 성분명</th><th style='padding: 6px; border: 1px solid #dee2e6; text-align: left;'>한글 번역명</th><th style='padding: 6px; border: 1px solid #dee2e6; text-align: center; width: 105px;'>비고</th></tr>"
            
            for ing in translated_ingredients:
                raw = ing.get('raw_name', '확인 불가')
                ko = ing.get('ko_name', '확인 불가')
                rem = ing.get('remark', '').strip()
                if not rem or rem.lower() == 'nan': rem = '일반명'
                
                if "위해" in rem or "의심" in rem:
                    row_bg, badge_style, display_rem = "#fff5f5", "background-color: #ffe3e3; color: #fa5252; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 12px;", f"🚨 {rem}"
                elif "기타" in rem or "원료" in rem:
                    row_bg, badge_style, display_rem = "#ffffff", "background-color: #f1f3f5; color: #868e96; padding: 2px 6px; border-radius: 4px; font-size: 12px;", f"📦 {rem}"
                elif "식물" in rem:
                    row_bg, badge_style, display_rem = "#ffffff", "background-color: #ebfbee; color: #2b8a3e; padding: 2px 6px; border-radius: 4px; font-size: 12px;", f"🌿 {rem}"
                else:
                    row_bg, badge_style, display_rem = "#ffffff", "background-color: #e3fafc; color: #0c8599; padding: 2px 6px; border-radius: 4px; font-size: 12px;", f"⚗️ {rem}"
                
                table_html += f"<tr style='background-color: {row_bg};'><td style='padding: 6px; border: 1px solid #dee2e6;'>{raw}</td><td style='padding: 6px; border: 1px solid #dee2e6; font-weight: bold;'>{ko}</td><td style='padding: 6px; border: 1px solid #dee2e6; text-align: center;'><span style='{badge_style}'>{display_rem}</span></td></tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
                    
    st.markdown("---")
    st.markdown("**3. 불법의약품DB 상세 정보 (본 DB 기준 최우선)**")
    if matched_row is not None:
        st.write(f"• **제품명(DB):** {get_clean_db_value(matched_row, '제품명')}")
        st.write(f"• **성분명(DB):** {get_clean_db_value(matched_row, '성분명')}")
        st.write(f"• **정보 출처:** {get_clean_db_value(matched_row, '정보출처')}")
        st.write(f"• **통관 보류 사유:** {get_clean_db_value(matched_row, '통관보류사유내용')}")
        st.write(f"• **상세 내용:** {get_clean_db_value(matched_row, '상세내용')}")
        st.write(f"• **법적 관련 근거:** {get_clean_db_value(matched_row, '관련근거')}")
    else:
        st.write("• 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.")

    st.markdown("---")
    st.markdown("## 📋 현장 조치 가이드")
    
    if decision_situation == "금지":
        st.markdown(f"""
**1. 통관 보류 및 유치**
- 사진 속 제품명, 바코드, 등록번호, 성분명 중 하나가 금지 정보와 명확히 일치하는 경우 통관을 보류하고 유치 절차로 전환한다.

**2. 유치 사유 기록 (연동 데이터)**
- **DB 등록번호:** `{reg_num}`
- **DB 제품명:** `{get_clean_db_value(matched_row, '제품명')}`
- **이미지 인식 제품명:** `{product_name}`
- **통관보류사유내용:** `{get_clean_db_value(matched_row, '통관보류사유내용')}`

**3. 현품 및 증빙 확보**
- 제품 전면 사진, 성분표, 바코드 영역을 촬영하여 증빙 보관.
""", unsafe_allow_html=True)
    elif decision_situation == "제한A":
        if is_ingredient_only_match:
            st.warning("⚠️ **제품명/바코드는 DB와 일치하지 않으나, 성분표 내 성분명이 DB의 위해 성분명과 일치하므로 검토 및 정밀검사가 필요합니다.**")
        st.markdown("**1. 즉시 승인 금지**\n- 해당 물품은 “성분 기반 위해 가능성 확인 대상”으로 분류.\n**2. 분석의뢰 검토**\n- 성분 함유 여부가 불명확한 경우 전자통관시스템을 통한 분석의뢰 절차 검토.", unsafe_allow_html=True)
    elif decision_situation == "제한B":
        st.markdown("**1. 통관 판단 보류 및 재촬영 요청**\n- 흐리거나 정보가 누락된 경우 승인을 단정하지 말고 보완 요청.\n**2. 수기 입력 대체**\n- 라벨 훼손 시 제품명, 바코드 등을 수기로 확인하여 대조.", unsafe_allow_html=True)
    elif decision_situation == "승인":
        st.markdown("**1. 수량 및 자가사용 기준 확인**\n- 건강기능식품 및 의약품 자가사용 목적 인정 범위(원칙적 6병 이내) 확인.\n**2. 최종 안내**\n- 본 판정은 보조 판단이며, 실제 통관 허용 여부는 현장 세관공무원의 요건 확인에 따름.", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔍 [현장 촬영 사진 확인 및 교차 검증]")
    
    st.info("📸 내가 촬영한 현품 사진")
    if user_images:
        user_cols = st.columns(len(user_images))
        for u_idx, u_img in enumerate(user_images):
            with user_cols[u_idx]:
                st.image(u_img, width=200)

    st.markdown("<hr style='margin: 25px 0; border-top: 2px solid #007bff;'>", unsafe_allow_html=True)
    
    if matched_row is not None and decision_situation != "제한B":
        url_data = str(matched_row.get('원본이미지URL', ''))
        if url_data and url_data.lower() != 'nan' and url_data.strip():
            st.warning("🔗 DB 등록 원본 이미지 (비교 대조용)")
            urls = [u.strip() for u in url_data.split(',') if u.strip()]
            db_cols = st.columns(len(urls))
            with requests.Session() as session:
                session.verify = False
                session.headers.update({"User-Agent": "Mozilla/5.0"})
                for idx_url, url in enumerate(urls):
                    try:
                        res = session.get(url, timeout=2)
                        if res.status_code == 200:
                            db_img = Image.open(io.BytesIO(res.content))
                            db_img.thumbnail((400, 400))
                            with db_cols[idx_url]:
                                st.image(db_img, width=200)
                    except: pass
        else:
            st.info("❌ **해당 위해물품은 DB에 등록된 원본 사진이 없습니다.**")
    else:
        if decision_situation == "승인":
            st.success("✅ **통관 가능 (안전 물품)으로 판정되어 대조할 DB 위해사진이 없습니다.**")
        else:
            st.info("❌ **대조할 DB 원본 사진이 없습니다.**")

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
                            st.error(f"❌ 메일 발송 중 오류가 발생했습니다: {e}")
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

uploaded_files = st.file_uploader(
    "눌러서 카메라 촬영 또는 사진 선택", 
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"cam_uploader_{st.session_state['uploader_id']}",
    label_visibility="collapsed"
)

if uploaded_files:
    st.info(f"📁 {len(uploaded_files)}장의 새 화물 사진이 접수되었습니다.")
    if st.button("🔍 위해물품 통합 분석 시작", type="primary", use_container_width=True):
        
        status_box = st.empty()       
        decision_box = st.empty()     
        info_col_box = st.empty()     
        
        user_images = []
        ai_contents = []
        
        for uploaded_file in uploaded_files:
            src_image = Image.open(uploaded_file)
            src_image.thumbnail((1024, 1024))
            if src_image.mode != 'RGB':
                src_image = src_image.convert('RGB')
            user_images.append(src_image)
            ai_contents.append(src_image)

        # JSON 형식이 파이썬에서 깨지지 않도록 무조건 큰따옴표(\")를 쓰도록 지시문 유지
        prompt = (
            "You are an expert Customs Forensic Intelligence OCR engine. Inspect the images carefully.\n"
            "1. Extract ONLY the core, shortest possible product name (e.g., 'EVP 3D') into 'product_name'.\n"
            "2. CRITICAL: Add the FULL product name including ALL flavors, taglines, and modifiers (e.g., 'EVP 3D Sour Candy', 'EVP 3D Tropic Thunder') into the 'multilingual_candidates' array. This is absolutely required for database matching.\n"
            "3. Extract all ingredients comprehensively including sub-ingredients inside parentheses.\n"
            "4. Categorize remarks strictly into: '위해성분 의심', '화학명', '식물명', '일반명', '기타 원료', '확인 불가'.\n\n"
            "Respond ONLY in a strict JSON format with these exact keys (Use double quotes for JSON):\n"
            "{\n  \"brand\": \"string\",\n  \"product_name\": \"string\",\n  \"translated_product_name\": \"string\",\n  \"barcode\": \"string\",\n  \"multilingual_candidates\": [\"string\"],\n  \"translated_ingredients\": [ {\"raw_name\": \"string\", \"ko_name\": \"string\", \"remark\": \"string\"} ],\n  \"package_features\": \"string\"\n}"
        )
        ai_contents.append(prompt)

        brand, product_name, translated_product_name, barcode, translated_ingredients, package_features, multilingual_candidates = '확인 불가', '확인 불가', '', '바코드 확인 불가', [], '', []
        
        status_box.status("🚀 1단계: 구글 Gemini 최신 비전 엔진이 이미지를 판독하고 있습니다...", expanded=True)
        
        try:
            # [🔥 모델 적용 완료] 사용자가 요청한 최신 안정화 버전 (gemini-3.5-flash) 적용 완료
            model = genai.GenerativeModel(model_name="gemini-3.5-flash")
            
            # 건강기능식품 성분명이 구글 유해성 필터에 차단되지 않도록 안전 설정 전면 해제 유지
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            response = model.generate_content(
                contents=ai_contents, 
                generation_config={"response_mime_type": "application/json"},
                safety_settings=safety_settings
            )
            
            clean_json_str = response.text.replace('```json', '').replace('```', '')
            ocr_result = json.loads(clean_json_str)
            
            brand = ocr_result.get('brand', '확인 불가')
            product_name = ocr_result.get('product_name', '확인 불가')
            translated_product_name = ocr_result.get('translated_product_name', '')
            barcode = ocr_result.get('barcode', '바코드 확인 불가')
            translated_ingredients = ocr_result.get('translated_ingredients', [])
            package_features = ocr_result.get('package_features', '')
            multilingual_candidates = ocr_result.get('multilingual_candidates', [])
        except Exception as e:
            st.error(f"비전 엔진 통합 판독 중 예외 발생: {e}")

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
                st.info("⏳ 2단계: 식약처 위해물품 DB와 교차 검증을 대조 중입니다...")

        status_box.status("🔍 2단계: 위해 의약품 DB와 교차 검증을 대조하고 있습니다...", expanded=True)
        
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
                
            norm_user_barcode = barcode.replace(" ", "").lower() if barcode != '바코드 확인 불가' else ""
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

        status_box.status("⚡ 3단계: 성분 번역 맵 구축 및 조치 표준 가이드를 통합 매핑 중입니다...", expanded=True)
        
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
