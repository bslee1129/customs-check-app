import streamlit st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import requests
import io
import urllib3
import time
import re

# [보안] 정부 서버 SSL 인증서 미인증 경고 문구 출력 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [설정] 웹 페이지 제목 및 모바일 레이아웃 최적화
st.set_page_config(page_title="해외 특송 위해물품 판정 시스템", layout="centered")

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

st.title("📱 현장 검사용 위해물품 스마트 판정기")
st.caption("💡 대량의 성분도 모바일 화면에 맞춰 한눈에 요약하는 콤팩트 그리드 엔진입니다.")

# 세션 상태(State) 관리 엔진 정의
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0
if "start_analysis" not in st.session_state:
    st.session_state["start_analysis"] = False

# [대조원칙 조항] 제품명 정규화 처리 함수 (노이즈 제외 및 기호 제거)
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

# [대조원칙 조항] 성분명 분리 기준 기호 기반 토큰화 및 정규화 함수
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
    
    is_low_res_detected = False
    for uploaded_file in uploaded_files:
        src_image = Image.open(uploaded_file)
        w, h = src_image.size
        if w < 500 or h < 500:
            is_low_res_detected = True
            
        img_for_ai = src_image.copy()
        img_for_ai.thumbnail((1024, 1024))
        ai_contents.append(img_for_ai)

    brand, product_name, translated_product_name, barcode, translated_ingredients, package_features, multilingual_candidates = '확인 불가', '확인 불가', '', '바코드 확인 불가', [], '', []
    
    with st.spinner("구글 Gemini 최신 비전 엔진이 촬영본을 통합 분석 중입니다..."):
        try:
            gemini_key = st.secrets.get("GEMINI_API_KEY", "")
            if gemini_key:
                genai.configure(api_key=gemini_key)
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

    # 5단계 우선순위 매칭 알고리즘 가동
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
            
        # --- [1순위] 바코드 일치 판정 ---
        if norm_user_barcode and 'norm_barcode' in df_db.columns:
            b_match = df_db[df_db['norm_barcode'] == norm_user_barcode]
            if not b_match.empty:
                matched_row = b_match.iloc[0]
                match_type = "1순위 바코드 일치"

        # --- [2순위/3순위] 제품명 다국어 정규화 일치 판정 ---
        if matched_row is None and user_norm_candidates and 'norm_product' in df_db.columns:
            for idx_row, row in df_db.iterrows():
                db_norm = str(row['norm_product'])
                if db_norm in user_norm_candidates or any(uc == db_norm for uc in user_norm_candidates if uc):
                    matched_row = row
                    match_type = "2/3순위 제품명 다국어 정규화 일치"
                    break

        # --- [우선순위 확장] 유사도 기반 다국어 애매한 매칭 감지 ---
        if matched_row is None and '제품명' in df_db.columns:
            for idx_row, row in df_db.iterrows():
                db_raw = str(row['제품명']).lower()
                if any(uc in db_raw and len(uc) >= 3 for uc in user_norm_candidates if uc):
                    matched_row = row
                    is_ambiguous_multilingual = True
                    match_type = "다국어 유사 판단"
                    break

        # --- [4순위] 성분명 토큰화 대조 ---
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

        # --- [5순위] 상세내용/근거 매칭 ---
        if matched_row is None:
            for idx_row, row in df_db.iterrows():
                detail_str = str(row.get('상세내용', '')).lower() + str(row.get('관련근거', '')).lower() + str(row.get('통관보류사유내용', '')).lower()
                if user_main_norm and user_main_norm in detail_str:
                    matched_row = row
                    match_type = "5순위 상세 기재내역 매칭"
                    break

    # 현장 조치 가이드 상황별 분기 정의
    decision_situation = "승인"
    is_high_risk_ingredient = False
    
    if matched_row is not None:
        reason_pool = str(matched_row.get('통관보류사유내용', '')).lower() + str(matched_row.get('관련근거', '')).lower()
        if any(kw in reason_pool for kw in ['마약', '향정', '향정신성', '대마', '코데인', '디히드로코데인', '반입금지', '반입 금지']):
            is_high_risk_ingredient = True

    if is_low_res_detected or (product_name in ['확인 불가', ''] and brand in ['확인 불가', ''] and not translated_ingredients):
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

    # 최종 세관 검사 판정 보고서 렌더링
    st.subheader("📋 세관 검사 판정 보고서")
    display_func(f"결과: {final_decision}")
        
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **1. OCR 분석 정보 (사진 {len(uploaded_files)}장 취합 결과)**
        * 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{brand}</span>
        * 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{product_name}</span>
        * 식별된 번역명: <span style="background-color: #faf0f6; color: #ae3ec9; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 14px;">{translated_product_name if translated_product_name else '해당없음'}</span>
        * 식별된 바코드: <span style="background-color
