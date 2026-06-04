import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import requests
import io
import urllib3

# [보안] 정부 서버 SSL 인증서 미인증 경고 문구 출력 방지
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [설정] 웹 페이지 제목 및 모바일 레이아웃 최적화
st.set_page_config(page_title="해외 특송 위해물품 판정 시스템", layout="centered")

# [모바일 전용 화면 구성] 스마트폰 터치 및 가독성 향상을 위한 CSS 주입
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
st.caption("💡 사진들을 모두 촬영하여 등록한 후, 최하단의 [분석 시작] 버튼을 눌러주세요.")

# 세션 상태(State) 관리 엔진 정의
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0
if "start_analysis" not in st.session_state:
    st.session_state["start_analysis"] = False

# Streamlit Secrets에서 Gemini API 키 로드
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
if gemini_key:
    genai.configure(api_key=gemini_key)
else:
    st.error("오른쪽 하단 Manage app -> Settings -> Secrets에 GEMINI_API_KEY를 등록해 주세요.")

@st.cache_data
def load_db():
    try:
        try:
            df = pd.read_csv("불법의약품DB.xlsx - Sheet1.csv")
        except:
            df = pd.read_excel("불법의약품DB.xlsx")
            
        df['search_product'] = df['제품명'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        if '성분명' in df.columns:
            df['search_ingredient'] = df['성분명'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        else:
            df['search_ingredient'] = ""
        return df
    except Exception as e:
        st.error(f"데이터베이스 파일을 읽을 수 없습니다: {e}")
        return None

df_db = load_db()

# 모바일 카메라/갤러리 다중 파일 업로더
uploaded_files = st.file_uploader(
    "눌러서 카메라 촬영 또는 사진 선택", 
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"cam_uploader_{st.session_state['uploader_id']}",
    label_visibility="collapsed"
)

# 이미지를 올렸을 때는 대기 메시지와 분석 버튼만 표출 (화면 복잡도 최소화)
if uploaded_files:
    if not st.session_state["start_analysis"]:
        st.info(f"📁 현재 {len(uploaded_files)}장의 사진이 업로드 대기 중입니다. 준비가 완료되면 아래 버튼을 눌러주세요.")
        if st.button("🔍 위해물품 통합 분석 시작", type="primary", use_container_width=True):
            st.session_state["start_analysis"] = True
            st.rerun()

# 분석 버튼을 누른 이후에만 최종 판정문 및 이미지 대조 섹션 전체 작동
if uploaded_files and st.session_state["start_analysis"]:
    
    ai_contents = []
    prompt = (
        "Analyze ALL the provided images together as a single product. "
        "Extract product information by combining context from all images (e.g., one image shows the front label, another shows the ingredients list). "
        "Respond ONLY in JSON format with keys: 'brand', 'product_name', 'barcode', 'ingredients' (list of ingredients found across all images). "
        "If not found, use empty string or empty list. Do not hypothesize or use external knowledge."
    )
    ai_contents.append(prompt)
    
    for uploaded_file in uploaded_files:
        src_image = Image.open(uploaded_file)
        img_for_ai = src_image.copy()
        img_for_ai.thumbnail((1024, 1024))
        ai_contents.append(img_for_ai)

    brand, product_name, barcode, ingredients = '확인 불가', '확인 불가', '바코드 확인 불가', []
    
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
            barcode = ocr_result.get('barcode', '바코드 확인 불가')
            ingredients = ocr_result.get('ingredients', [])
        except Exception as e:
            st.error(f"비전 엔진 통합 판독 중 예외 발생: {e}")

    # 2. 파이썬 Pandas 기반 위해물품 정밀 매칭
    matched_row = None
    match_type = "🟢 매칭되지 않음"
    
    if df_db is not None and product_name not in ['확인 불가', '']:
        query_text = product_name.replace(" ", "").lower()
        exact_match = df_db[df_db['search_product'].str.contains(query_text, na=False)]
        if not exact_match.empty:
            matched_row = exact_match.iloc[0]
            match_type = "🔴 매칭됨 (제품명 일치)"
        else:
            for ing in ingredients:
                ing_query = ing.replace(" ", "").lower()
                if len(ing_query) > 2:
                    ing_match = df_db[df_db['search_ingredient'].str.contains(ing_query, na=False)]
                    if not ing_match.empty:
                        matched_row = ing_match.iloc[0]
                        match_type = "🟡 성분명 일치 매칭됨"
                        break

    # 3. 최종 세관 검사 판정 보고서 렌더링
    st.subheader("📋 세관 검사 판정 보고서")
    
    if matched_row is not None:
        final_decision = "🔴 반입 금지" if "🔴" in match_type else "🟡 제한 - 정밀검사 필요"
        st.error(f"결과: {final_decision}")
    else:
        final_decision = "🟢 통관 가능"
        st.success(f"결과: {final_decision}")
        
    # 🚨 [핵심 업데이트] 결과값을 강조하는 특제 하이라이트 Badge UI 적용
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **1. OCR 분석 정보 (사진 {len(uploaded_files)}장 취합 결과)**
        * 식별된 브랜드: <span style="background-color: #e7f5ff; color: #007bff; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;">{brand}</span>
        * 식별된 제품명: <span style="background-color: #fff0f6; color: #d6336c; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;">{product_name}</span>
        * 식별된 바코드: <span style="background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;">{barcode}</span>
        """, unsafe_allow_html=True)
    with col2:
        reg_num = matched_row['등록번호'] if matched_row is not None else "해당 없음"
        
        # 매칭 상태별 동적 강조 스타일 정의
        if "🔴" in match_type:
            match_badge = f'background-color: #fff5f5; color: #fa5252; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;'
        elif "🟡" in match_type:
            match_badge = f'background-color: #fff9db; color: #fab005; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;'
        else:
            match_badge = f'background-color: #ebfbee; color: #40c057; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;'
            
        st.markdown(f"""
        **2. DB 대조 결과**
        * 등록번호: <span style="background-color: #e8f7ff; color: #1c7ed6; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 15px;">{reg_num}</span>
        * DB 매칭 여부: <span style="{match_badge}">{match_type}</span>
        """, unsafe_allow_html=True)
                    
    st.markdown("---")
    st.markdown("**3. 불법의약품DB 상세 정보**")
    
    if matched_row is not
