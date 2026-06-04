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

# 🚨 [수정 사항 1] 이미지를 올렸을 때는 대기 메시지와 분석 버튼만 표출 (목록 및 분석 보류)
if uploaded_files:
    if not st.session_state["start_analysis"]:
        st.info(f"📁 현재 {len(uploaded_files)}장의 사진이 업로드 대기 중입니다. 준비가 완료되면 아래 버튼을 눌러주세요.")
        if st.button("🔍 위해물품 통합 분석 시작", type="primary", use_container_width=True):
            st.session_state["start_analysis"] = True
            st.rerun()

# 🚨 [수정 사항 1] 분석 버튼을 누른 이후에만 목록 출력 및 AI 연산 전체 작동
if uploaded_files and st.session_state["start_analysis"]:
    
    # 1. 촬영된 현품 이미지 목록 출력
    st.markdown("### 📸 촬영된 현품 이미지 목록")
    img_display_cols = st.columns(len(uploaded_files))
    
    ai_contents = []
    prompt = (
        "Analyze ALL the provided images together as a single product. "
        "Extract product information by combining context from all images (e.g., one image shows the front label, another shows the ingredients list). "
        "Respond ONLY in JSON format with keys: 'brand', 'product_name', 'barcode', 'ingredients' (list of ingredients found across all images). "
        "If not found, use empty string or empty list. Do not hypothesize or use external knowledge."
    )
    ai_contents.append(prompt)
    
    for idx, uploaded_file in enumerate(uploaded_files):
        src_image = Image.open(uploaded_file)
        
        with img_display_cols[idx]:
            st.image(src_image, caption=f"촬영 사진 {idx+1}", use_container_width=True)
            
        # 이미지 압축 가공
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
    st.markdown("---")
    st.subheader("📋 세관 검사 판정 보고서 (통합 판정)")
    
    if matched_row is not None:
        final_decision = "🔴 반입 금지" if "🔴" in match_type else "🟡 제한 - 정밀검사 필요"
        st.error(f"결과: {final_decision}")
    else:
        final_decision = "🟢 통관 가능"
        st.success(f"결과: {final_decision}")
        
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**1. OCR 분석 정보 (사진 {len(uploaded_files)}장 취합 결과)**\n"
                    f"* 식별된 브랜드: `{brand}`\n"
                    f"* 식별된 제품명: `{product_name}`\n"
                    f"* 식별된 바코드: `{barcode}`")
    with col2:
        reg_num = matched_row['등록번호'] if matched_row is not None else "해당 없음"
        st.markdown(f"**2. DB 대조 결과**\n"
                    f"* 등록번호: `{reg_num}`\n"
                    f"* DB 매칭 여부: **{match_type}**")
                    
    st.markdown("---")
    st.markdown("**3. 불법의약품DB 상세 정보**")
    
    if matched_row is not None:
        def get_clean_db_value(row, column_name):
            val = row.get(column_name)
            if pd.isna(val) or str(val).strip().lower() == 'nan' or not str(val).strip():
                if column_name == '통관보류사유내용':
                    return f"위해 성분({row.get('성분명', '확인불가')}) 검출 및 함유로 인한 현장 통관 보류 대상 물품"
                elif column_name == '정보출처':
                    return "식품의약품안전처(식약처) 위해식품 반입차단 목록"
                elif column_name == '관련근거':
                    return "수입식품안전관리 특별법 제25조의3 (위해식품등의 반입 차단)"
                return "확인 불가"
            return str(val)

        st.write(f"• **정보 출처:** {get_clean_db_value(matched_row, '정보출처')}")
        st.write(f"• **통관 보류 사유:** {get_clean_db_value(matched_row, '통관보류사유내용')}")
        st.write(f"• **법적 관련 근거:** {get_clean_db_value(matched_row, '관련근거')}")
        
        # 4. 복수 이미지 전수 출력 레이아웃
        url_data = str(matched_row.get('원본이미지URL', ''))
        if url_data and url_data.lower() != 'nan':
            st.markdown("---")
            st.markdown("### 🔍 [현장 교차 검증] 사진 비교 대조")
            st.caption("우측에 표시되는 DB 등록 원본 사진들과 실물을 대조하십시오.")
            
            urls = [u.strip() for u in url_data.split(',') if u.strip()]
            
            # 메인 분할 화면 (좌측: 내가 촬영한 첫 번째 대표 이미지 / 우측: DB 원본 이미지 공간)
            main_col1, main_col2 = st.columns(2)
            
            with main_col1:
                st.info("📸 내가 촬영한 현품 사진")
                st.image(Image.open(uploaded_files[0]), use_container_width=True, caption="촬영본 (대표)")
                
            with main_col2:
                st.warning("🔗 DB 등록 원본 이미지")
                
                # 🚨 [수정 사항 2] DB 사진 개수만큼 우측 공간 내부를 쪼개서 병렬(가로) 배치 및 자동 축소 효과
                db_cols = st.columns(len(urls))
                
                for idx, url in enumerate(urls):
                    success = False
                    error_msg = ""
                    
                    for attempt in range(2):
                        try:
                            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                            img_response = requests.get(url, headers=headers, timeout=15, verify=False)
                            if img_response.status_code == 200:
                                db_img = Image.open(io.BytesIO(img_response.content))
                                # 🚨 병렬로 생성된 칸 안에 축소하여 표출
                                with db_cols[idx]:
                                    st.image(db_img, caption=f"DB 사진 {idx+1}", use_container_width=True)
                                success = True
                                break
                            else:
                                error_msg = f"서버 거부 ({img_response.status_code})"
                        except Exception as e:
                            error_msg = f"보안망 연결 실패"
                    
                    if not success:
                        with db_cols[idx]:
                            st.caption(f"❌ 사진 {idx+1}: {error_msg}")

        st.warning(f"**검사원 조치 의견:**\n"
                   f"본 물품은 [불법의약품DB.xlsx] 대조 원칙 및 파이썬 정규화 매칭 결과, 등록번호 [{reg_num}]번에 "
                   f"매칭되는 위해 항목임이 확정되었습니다. 내부 규정에 근거하여 현장에서 **통관 보류 및 폐기/반송 조치**하시기 바랍니다.")
    else:
        st.write("• 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.")
        st.info("**검사원 조치 의견:** 금지 성분 및 DB 매칭 내역 없으므로 **통관 허용** 처리합니다.")

    # [다음 물품 판정 버튼] 세션 분석 플래그까지 함께 리셋
    st.markdown("---")
    if st.button("🔄 다음 물품 판정하기 (화면 초기화)", use_container_width=True, type="primary"):
        st.session_state["uploader_id"] += 1
        st.session_state["start_analysis"] = False
        st.rerun()
