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

# 🚨 [디자인 수정] 로고와 제목을 한 줄에 동일한 크기로 나란히 배치 (Base64 인코딩 기법)
logo_path = "Emblem_of_the_Korea_Customs_Service.svg.png"

# 이미지를 HTML 안에 직접 쏘아넣기 위한 함수
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

if os.path.exists(logo_path):
    img_src = f"data:image/png;base64,{get_base64_of_bin_file(logo_path)}"
else:
    img_src = "https://raw.githubusercontent.com/bslee1129/customs-check-app/main/Emblem_of_the_Korea_Customs_Service.svg.png"

# Flexbox를 사용하여 로고 높이(42px)와 텍스트 크기를 완벽하게 일치시키고 나란히 정렬
st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 5px;">
        <img src="{img_src}" style="height: 42px; width: auto; object-fit: contain;">
        <h1 style="margin: 0; padding: 0; font-size: 32px; font-weight: 700; line-height: 1.2;">AI 위해식품 스마트 검사관</h1>
    </div>
""", unsafe_allow_html=True)

st.caption("💡 스마트폰 촬영본을 바탕으로 DB 5단계 대조 및 성분 교차 검증을 수행합니다.")

# API 키 설정
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
if gemini_key:
    genai.configure(api_key=gemini_key)
else:
    st.error("⚠️ 오른쪽 하단 Manage app -> Settings -> Secrets에 GEMINI_API_KEY를 등록해 주세요.")

# 세션 상태(State) 관리 엔진 정의
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0
if "start_analysis" not in st.session_state:
    st.session_state["start_analysis"] = False

# [대조원칙] 제품명 정규화 처리 함수
def normalize_product_name(text):
    if pd.isna(text) or not str(text).strip() or str(text).strip().lower() == 'nan':
        return ""
    val = str(text).lower()
    noise_patterns = [
        r'fruit\s*punch', r'blue\s*raz', r'sour\s*candy',
        r'\d+g', r'\d+\.?\d*oz', r'\d+\s*capsules', r'\d+\s*tablets', r'\d+\s*servings',
        r'capsules', r'tablets', r'powder', r'錠', r'カプセル', r'顆粒', r'液', r'정제', r'캡슐', r'과립', r'액제'
    ]
    for pattern in noise_patterns:
        val = re.sub(pattern, '', val)
    val = re.sub(r'[\s\-\./\s:\(\)\+·_\*&%!@#~`=\[\]\{\}\\\|\'\";\?]', '', val)
    return val

# [대조원칙] 성분명 분리 기준 기호 기반 토큰화 및 정규화 함수
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

# 모바일 카메라/갤러리 다중 파일 업로더
uploaded_files = st.file_uploader(
    "눌러서 카메라 촬영 또는 사진 선택", 
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"cam_uploader_{st.session_state['uploader_id']}",
    label_visibility="collapsed"
)

if uploaded_files:
    if not st.session_state["start_analysis"]:
        st.info(f"📁 현재 {len(uploaded_files)}장의 사진이 업로드 대기 중입니다. 준비가 완료되면 아래 버튼을 눌러주세요.")
        if st.button("🔍 위해물품 통합 분석 시작", type="primary", use_container_width=True):
            st.session_state["start_analysis"] = True
            st.rerun()

# 분석 연산 시동
if uploaded_files and st.session_state["start_analysis"]:
    
    ai_contents = []
    prompt = (
        "You are an expert Customs Forensic Intelligence OCR engine. Inspect the images carefully.\n"
        "1. Single Ingredient Sheet Handling: Even if the image only shows the ingredient facts label without brand/product names or barcodes, DO NOT stop analysis. Extract everything possible.\n"
        "2. Comprehensive Ingredient Extraction: Check zones like Active Ingredients, Other Ingredients, Supplement Facts, Drug Facts, Ingredients, Proprietary Blend, Performance Matrix, Complex, and Blend.\n"
        "3. Multilingual Candidates Generation: Generate alternative matching names under 'multilingual_candidates' using romanization and dictionary expansions.\n"
        "4. Categorize remarks strictly into: '위해성분 의심', '화학명', '식물명', '일반명', '기타 원료', '확인 불가'.\n\n"
        "Respond ONLY in a strict JSON format with these exact keys:\n"
        "{\n"
        "  'brand': 'string',\n"
        "  'product_name': 'string',\n"
        "  'translated_product_name': 'string',\n"
        "  'barcode': 'string',\n"
        "  'multilingual_candidates': ['string'],\n"
        "  'translated_ingredients': [\n"
        "     {\n"
        "       'raw_name': 'string',\n"
        "       'ko_name': 'string',\n"
        "       'remark': 'string'\n"
        "     }\n"
        "  ],\n"
        "  'package_features': 'string'\n"
        "}"
    )
    ai_contents.append(prompt)
    
    user_images = []
    is_low_res_detected = False
    for uploaded_file in uploaded_files:
        src_image = Image.open(uploaded_file)
        user_images.append(src_image)
        
        w, h = src_image.size
        if w < 500 or h < 500:
            is_low_res_detected = True
            
        img_for_ai = src_image.copy()
        img_for_ai.thumbnail((1024, 1024))
        ai_contents.append(img_for_ai)

    brand, product_name, translated_product_name, barcode, translated_ingredients, package_features, multilingual_candidates = '확인 불가', '확인 불가', '', '바코드 확인 불가', [], '', []
    
    with st.spinner("구글 Gemini 최신 비전 엔진이 촬영본을 통합 분석 중입니다..."):
        try:
            model = genai.GenerativeModel(model_name="gemini-3.5-flash")
            response = model.generate_content(
                contents=ai_contents,
                generation_config={"response_mime_type": "application/json"}
            )
            ocr_result = json.loads(response.text)
            brand = ocr_result.get('brand', '확인 불가')
            product_name = ocr_result.get('product_name', '확인 불가')
            translated_product_name = ocr_result.get('translated_product_name', '')
            barcode = ocr_result.get('barcode', '바코드 확인 불가')
            translated_ingredients = ocr_result.get('translated_ingredients', [])
            package_features = ocr_result.get('package_features', '')
            multilingual_candidates = ocr_result.get('multilingual_candidates', [])
        except Exception as e:
            st.error(f"비전 엔진 통합 판독 중 예외 발생: {e}")

    # 5단계 우선순위 매칭 알고리즘
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

        if matched_row is None and '제품명' in df_db.columns:
            for idx_row, row in df_db.iterrows():
                db_raw = str(row['제품명']).lower()
                if any(uc in db_raw and len(uc) >= 3 for uc in user_norm_candidates if uc):
                    matched_row = row
                    is_ambiguous_multilingual = True
                    match_type = "다국어 유사 판단"
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
    elif matched_row is not None and (is_ingredient_only_match or is_ambiguous_multilingual or match_type in ["5순위 상세 기재내역 매칭", "다국어 유사 판단"]):
        decision_situation = "제한A"
    else:
        decision_situation = "승인"

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

    st.subheader("📋 세관 검사 판정 보고서")
    display_func(f"결과: {final_decision}")
        
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
**1. OCR 분석 정보 (사진 {len(uploaded_files)}장 취합 결과)**
* 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{brand}</span>
* 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{product_name}</span>
* 식별된 번역명: <span style="background-color: #faf0f6; color: #ae3ec9; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{translated_product_name if translated_product_name else '해당없음'}</span>
* 식별된 바코드: <span style="background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{barcode}</span>
""", unsafe_allow_html=True)
    with col2:
        if matched_row is not None and '등록번호' in matched_row and pd.notna(matched_row['등록번호']):
            reg_num = str(matched_row['등록번호']).split('.')[0]
        else:
            reg_num = "등록번호 확인 불가"
            
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
        if suspicious_count > 0:
            expander_title += f" (⚠️ 위해성분 의심 {suspicious_count}건 포함)"
            
        with st.expander(expander_title, expanded=(suspicious_count > 0)):
            table_html = "<table style='width:100%; border-collapse: collapse; font-size: 13px; font-family: sans-serif;'>"
            table_html += "<tr style='background-color: #f1f3f5;'><th style='padding: 6px; border: 1px solid #dee2e6; text-align: left;'>원문 성분명</th><th style='padding: 6px; border: 1px solid #dee2e6; text-align: left;'>한글 번역명</th><th style='padding: 6px; border: 1px solid #dee2e6; text-align: center; width: 105px;'>비고</th></tr>"
            
            for ing in translated_ingredients:
                raw = ing.get('raw_name', '확인 불가')
                ko = ing.get('ko_name', '확인 불가')
                rem = ing.get('remark', '').strip()
                
                if not rem or rem.lower() == 'nan':
                    rem = '일반명'
                
                if "위해" in rem or "의심" in rem:
                    row_bg = "#fff5f5"
                    badge_style = "background-color: #ffe3e3; color: #fa5252; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 12px;"
                    display_rem = f"🚨 {rem}"
                elif "기타" in rem or "원료" in rem:
                    row_bg = "#ffffff"
                    badge_style = "background-color: #f1f3f5; color: #868e96; padding: 2px 6px; border-radius: 4px; font-size: 12px;"
                    display_rem = f"📦 {rem}"
                elif "식물" in rem:
                    row_bg = "#ffffff"
                    badge_style = "background-color: #ebfbee; color: #2b8a3e; padding: 2px 6px; border-radius: 4px; font-size: 12px;"
                    display_rem = f"🌿 {rem}"
                else:
                    row_bg = "#ffffff"
                    badge_style = "background-color: #e3fafc; color: #0c8599; padding: 2px 6px; border-radius: 4px; font-size: 12px;"
                    display_rem = f"⚗️ {rem}"
                
                table_html += f"<tr style='background-color: {row_bg};'><td style='padding: 6px; border: 1px solid #dee2e6;'>{raw}</td><td style='padding: 6px; border: 1px solid #dee2e6; font-weight: bold;'>{ko}</td><td style='padding: 6px; border: 1px solid #dee2e6; text-align: center;'><span style='{badge_style}'>{display_rem}</span></td></tr>"
            
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
                    
    st.markdown("---")
    st.markdown("**3. 불법의약품DB 상세 정보 (본 DB 기준 최우선)**")
    
    def get_clean_db_value(row, column_name):
        if row is None: return "해당 없음"
        val = row.get(column_name)
        if pd.isna(val) or str(val).strip().lower() == 'nan' or not str(val).strip():
            if column_name == '통관보류사유내용': return "위해 성분 검출 및 함유로 인한 현장 통관 보류 대상 물품"
            elif column_name == '정보출처': return "식품의약품안전처(식약처) 위해식품 반입차단 목록"
            elif column_name == '관련근거': return "수입식품안전관리 특별법 제25조의3 (위해식품등의 반입 차단)"
            return "확인 불가"
        return str(val)

    if matched_row is not None:
        st.write(f"• **제품명(DB):** {get_clean_db_value(matched_row, '제품명')}")
        st.write(f"• **성분명(DB):** {get_clean_db_value(matched_row, '성분명')}")
        st.write(f"• **정보 출처:** {get_clean_db_value(matched_row, '정보출처')}")
        st.write(f"• **통관 보류 사유:** {get_clean_db_value(matched_row, '통관보류사유내용')}")
        st.write(f"• **상세 내용:** {get_clean_db_value(matched_row, '상세내용')}")
        st.write(f"• **법적 관련 근거:** {get_clean_db_value(matched_row, '관련근거')}")
    else:
        st.write("• 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.")

    # 현장 조치 가이드 상황별 동적 출력
    st.markdown("---")
    st.markdown("## 📋 현장 조치 가이드")
    
    if decision_situation == "금지":
        st.markdown(f"""
### ■ 판정이 [🔴 금지]인 경우 조치 지침:

**1. 통관 보류 및 유치**
- 사진 속 제품명, 바코드, 등록번호, 성분명 중 하나가 [불법의약품DB.xlsx]의 금지 정보와 명확히 일치하는 경우 통관을 허용하지 않는다.
- 해당 물품은 현장에서 통관 보류 대상으로 안내하고, 필요한 경우 세관 유치 절차로 전환한다.

**2. 유치 사유 기록 (연동 데이터)**
- 유치 또는 통관보류 사유에는 다음 항목을 함께 기록한다:
  - **DB 등록번호:** `{reg_num}`
  - **DB 제품명:** `{get_clean_db_value(matched_row, '제품명')}`
  - **이미지 인식 제품명:** `{product_name}`
  - **일치한 바코드 또는 성분명:** `{barcode if barcode != '바코드 확인 불가' else (matched_ingredient_str if matched_ingredient_str else get_clean_db_value(matched_row, '성분명'))}`
  - **통관보류사유내용:** `{get_clean_db_value(matched_row, '통관보류사유내용')}`
  - **상세내용:** `{get_clean_db_value(matched_row, '상세내용')}`
  - **관련근거:** `{get_clean_db_value(matched_row, '관련근거')}`

**3. 현품 및 증빙 확보**
- 제품 전면 사진, 성분표, 바코드 영역을 선명하게 촬영하여 증빙으로 보관한다.
- 바코드가 일치한 경우 바코드 숫자를 별도 기록한다.
- 성분명이 일치한 경우 원문 성분명과 한글 번역명을 함께 기록한다.

**4. 마약류·향정신성의약품 등 고위험 성분**
- DB의 통관보류사유내용 또는 관련근거에 마약류, 향정신성의약품, 대마, 코데인, 디히드로코데인 등 즉시 금지 대상 성분이 명시된 경우, 일반 건강기능식품 기준으로 처리하지 않는다.
- 현품을 보존하고 담당 부서 또는 조사 담당자 검토 대상으로 안내한다.

**5. 반송·폐기 안내**
- 통관이 불가능한 물품으로 판단되는 경우, 현장에서는 화주에게 통관보류 사유와 후속 처리 가능 절차를 안내한다.
- 폐기, 반송, 조사 인계 여부는 실제 세관 내부 절차와 담당자 판단에 따른다.
""")
        
    elif decision_situation == "제한A":
        if is_ingredient_only_match:
            st.warning("⚠️ **제품명/바코드는 DB와 일치하지 않으나, 성분표 내 성분명이 DB의 위해 성분명과 일치하므로 검토 및 정밀검사가 필요합니다.**")
            
        st.markdown(f"""
### ■ 판정이 [⚠️ 제한 - 성분 기반 검토 및 정밀검사 필요]인 경우 조치 지침:

**1. 즉시 승인 금지**
- 제품명 또는 바코드가 DB와 일치하지 않더라도, 성분표에서 추출한 원문 성분명 또는 한글 번역 성분명이 DB의 성분명과 일치하면 즉시 승인하지 않는다.
- 해당 물품은 “성분 기반 위해 가능성 확인 대상”으로 분류한다.

**2. 통관 보류 또는 유치 검토**
- 성분명 일치만으로 제품 자체가 DB 등록 제품이라고 단정하지 않는다.
- 다만 위해성분 포함 가능성이 있으므로 통관 보류, 유치, 추가 확인 또는 분석의뢰 대상인지 검토한다.

**3. 추가 정보 확보**
- 제품 전면 사진 / 전체 성분표 사진 / 바코드 영역 사진 / 제품명 원문 / 용량 및 복용법 / 함량 표시 / 구매 경위 또는 사용 목적

**4. 분석의뢰 검토**
- 성분명이 위해성분과 일치하거나 유사하나 실제 함유 여부가 불명확한 경우, 유치 후 분석의뢰 가능성을 안내한다.
- 분석의뢰가 필요한 경우 전자통관시스템의 품목분석 관련 메뉴를 통한 분석의뢰 절차를 검토한다.

**5. 최종 처리**
- 분석 또는 담당자 검토 결과 위해성분 함유가 확인되면 금지 또는 통관보류로 전환한다.
- DB 성분명과의 불일치가 확인되면 승인 가능 여부를 재검토한다.
""")
        
    elif decision_situation == "제한B":
        st.markdown(f"""
### ■ 판정이 [⚠️ 제한 - 현품 식별 불가 / 정보 보완 필요]인 경우 조치 지침:

**1. 통관 판단 보류**
- 이미지가 흐리거나 잘려 제품명, 성분표, 바코드를 확인할 수 없는 경우 승인 또는 금지를 단정하지 않는다.
- 정확한 판정을 위해 정보 보완을 요청한다.

**2. 재촬영 요청**
- 화주 또는 검사 담당자에게 다음 영역이 선명하게 보이도록 다시 촬영하도록 안내한다:
  - 제품 전면 전체 / 제품명 및 브랜드명 / Supplement Facts / Drug Facts / Ingredients / Active Ingredients / Other Ingredients / 바코드 숫자 / 용량 및 복용법

**3. 수기 입력 대체**
- 라벨 훼손 또는 촬영 불가 시, 제품명·성분명·바코드 숫자를 대화창에 직접 입력하도록 안내한다.

**4. 유치 상태 유지 검토**
- 세관장 확인대상 물품이거나 필요한 허가·승인·표시 등 조건이 갖춰지지 않은 물품은 통관 전 유치 검토 대상으로 안내한다.
""")
        
    elif decision_situation == "승인":
        st.markdown(f"""
### ■ 판정이 [🟢 승인]인 경우 조치 지침:

**1. DB 대조 결과 확인**
- 바코드, 제품명, 다국어 변환 제품명, 원문 성분명, 한글 번역 성분명이 [불법의약품DB.xlsx]와 일치하지 않는 경우에만 승인으로 표시한다.

**2. 수량 및 자가사용 기준 확인**
- 건강기능식품 및 의약품은 자가사용 목적 인정 범위인지 확인한다.
- 건강기능식품 및 일반 의약품은 원칙적으로 6병 이내 여부를 확인한다.
- 의약품이 6병을 초과하는 경우에는 용법상 3개월 복용량 이내인지 추가 확인이 필요하다.

**3. 금액 기준 확인**
- 면세 또는 과세 여부는 별도로 검토한다.
- DB상 위해성분이 없더라도 수량, 금액, 자가사용 인정기준을 초과하면 별도 과세 또는 정식수입신고 대상이 될 수 있음을 안내한다.

**4. 전문의약품·주사제 등 예외 확인**
- 전문의약품, 주사제, 보툴리눔 독소제제 등은 일반 건강기능식품 또는 일반 의약품 승인 기준으로 처리하지 않는다.
- 처방 필요 여부, 자가사용 가능 여부, 식약처 허가품목 여부 등 별도 검토가 필요하다.

**5. 최종 안내**
- AI 판정은 DB 대조 및 이미지 판독 결과에 따른 보조 판단이다.
- 실제 통관 허용 여부는 현장 세관공무원의 최종 확인, 수량 기준, 자가사용 여부, 관계 법령 요건 확인 결과에 따른다.
""")

    # 4. 이미지 세로 레이아웃 가로 병렬 배치 섹션 (DB 사진 공백 처리 포함)
    if matched_row is not None and decision_situation != "제한B":
        url_data = str(matched_row.get('원본이미지URL', ''))
        if url_data and url_data.lower() != 'nan' and url_data.strip():
            st.markdown("---")
            st.markdown("### 🔍 [현장 교차 검증] 사진 비교 대조")
            st.caption("상단의 촬영 현품 사진들과 하단의 DB 등록 원본 사진들의 패키지를 대조하십시오.")
            
            st.info("📸 내가 촬영한 현품 사진")
            user_cols = st.columns(len(user_images))
            for u_idx, u_img in enumerate(user_images):
                with user_cols[u_idx]:
                    st.image(u_img, caption=f"촬영 사진 {u_idx+1}", use_container_width=True)
            
            st.markdown("<hr style='margin: 25px 0; border-top: 2px solid #007bff;'>", unsafe_allow_html=True)
            st.warning("🔗 DB 등록 원본 이미지")
            
            urls = [u.strip() for u in url_data.split(',') if u.strip()]
            db_cols = st.columns(len(urls))
            
            with requests.Session() as session:
                session.verify = False
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                })
                
                for idx, url in enumerate(urls):
                    success = False
                    error_msg = ""
                    for attempt in range(3):
                        try:
                            img_response = session.get(url, timeout=15)
                            if img_response.status_code == 200:
                                db_img = Image.open(io.BytesIO(img_response.content))
                                with db_cols[idx]:
                                    st.image(db_img, caption=f"DB 사진 {idx+1}", use_container_width=True)
                                success = True
                                break
                            else:
                                error_msg = f"서버 거부 ({img_response.status_code})"
                        except Exception as e:
                            error_msg = f"네트워크 보안망 차단 ({type(e).__name__})"
                        if not success:
                            time.sleep(0.5)
                    
                    if not success:
                        with db_cols[idx]:
                            st.caption(f"❌ 사진 {idx+1}: {error_msg}")
        else:
            st.markdown("---")
            st.markdown("### 🔍 [현장 교차 검증] 사진 비교 대조")
            st.info("📸 내가 촬영한 현품 사진")
            user_cols = st.columns(len(user_images))
            for u_idx, u_img in enumerate(user_images):
                with user_cols[u_idx]:
                    st.image(u_img, caption=f"촬영 사진 {u_idx+1}", use_container_width=True)
            st.markdown("<hr style='margin: 25px 0; border-top: 2px solid #007bff;'>", unsafe_allow_html=True)
            st.info("❌ **DB에 등록된 원본 사진이 없습니다.** (상단의 텍스트 및 성분 정보로 현품과 교차 대조를 진행해 주십시오.)")

    # [다음 물품 판정 버튼 - 메모리 누수 방지 엔진 탑재]
    st.markdown("---")
    if st.button("🔄 다음 물품 판정하기 (화면 초기화)", use_container_width=True, type="primary"):
        for key in list(st.session_state.keys()):
            if key.startswith("cam_uploader_"):
                del st.session_state[key]
                
        st.session_state["uploader_id"] += 1
        st.session_state["start_analysis"] = False
        st.rerun()
