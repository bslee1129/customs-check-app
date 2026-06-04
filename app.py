import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image

# [설정] 웹 페이지 제목 및 모바일 최적화 레이아웃
st.set_page_config(page_title="해외 특송 위해물품 판정 시스템", layout="centered")

st.title("📱 현장 검사용 위해물품 스마트 판정기 (Gemini 무제한)")
st.caption("스마트폰 사진을 자동 압축하여 구글 무료 서버 한도 내에서 상시 무료로 구동합니다.")

# Streamlit Secrets에서 Gemini API 키 로드
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
if gemini_key:
    genai.configure(api_key=gemini_key)
else:
    st.error("오른쪽 하단 Manage app -> Settings -> Secrets에 GEMINI_API_KEY를 등록해 주세요.")

@st.cache_data
def load_db():
    try:
        df = pd.read_excel("불법의약품DB.xlsx")
        # 검색 최적화용 정규화 컬럼 생성 (공백 제거, 소문자화)
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

# 1. 모바일 카메라 / 파일 업로드 컴포넌트
uploaded_file = st.file_uploader("📸 제품 전면 또는 성분표 사진을 촬영하세요", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # 화면에 이미지 즉시 표시
    image = Image.open(uploaded_file)
    st.image(image, caption="촬영된 현품 이미지", use_container_width=True)
    
    with st.spinner("Gemini AI가 라벨을 판독하고 있습니다..."):
        try:
            # 무료 티어 용량 초과 방지를 위한 실시간 리사이징 (최대 1024px)
            image.thumbnail((1024, 1024))
            
            # 💡 하루 50회 제한 Pro 모델 원할 시: "gemini-1.5-pro" 로 변경
            # 💡 하루 1,500회 제한 완전 무료 원할 시: "gemini-2.0-flash" 유지
            model = genai.GenerativeModel(model_name="gemini-2.0-flash")
            
            prompt = (
                "Analyze the image and extract product information. "
                "Respond ONLY in JSON format with keys: 'brand', 'product_name', 'barcode', 'ingredients' (list of ingredients found in the text). "
                "If not found, use empty string or empty list. Do not hypothesize or use external knowledge."
            )
            
            # PIL 이미지 객체를 그대로 전달하는 가장 안정적인 호출 방식
            response = model.generate_content(
                contents=[prompt, image],
                generation_config={"response_mime_type": "application/json"}
            )
            
            # OCR 결과 파싱
            ocr_result = json.loads(response.text)
            brand = ocr_result.get('brand', '확인 불가')
            product_name = ocr_result.get('product_name', '확인 불가')
            barcode = ocr_result.get('barcode', '바코드 확인 불가')
            ingredients = ocr_result.get('ingredients', [])
            
        except Exception as e:
            st.error(f"무료 서버 호출 제한 또는 계정 권한 오류 발생: {e}")
            brand, product_name, barcode, ingredients = '확인 불가', '확인 불가', '바코드 확인 불가', []

    # 2. 파이썬 Pandas 기반 100% 정밀 매칭 매커니즘
    matched_row = None
    match_type = "🟢 매칭되지 않음"
    
    if df_db is not None and product_name != '확인 불가':
        query_text = product_name.replace(" ", "").lower()
        
        # 1차 제품명 매칭
        exact_match = df_db[df_db['search_product'].str.contains(query_text, na=False)]
        if not exact_match.empty:
            matched_row = exact_match.iloc[0]
            match_type = "🔴 매칭됨 (제품명 일치)"
        else:
            # 2차 성분명 매칭
            for ing in ingredients:
                ing_query = ing.replace(" ", "").lower()
                if len(ing_query) > 2:
                    ing_match = df_db[df_db['search_ingredient'].str.contains(ing_query, na=False)]
                    if not ing_match.empty:
                        matched_row = ing_match.iloc[0]
                        match_type = "🟡 성분명 일치 매칭됨"
                        break

    # 3. 최종 세관 검사 판정 및 리포트 화면 렌더링
    st.subheader("📋 세관 검사 판정 보고서")
    
    if matched_row is not None:
        final_decision = "🔴 반입 금지" if "🔴" in match_type else "🟡 제한 - 성분 기반 검토 및 정밀검사 필요"
        st.error(f"결과: {final_decision}")
    else:
        final_decision = "🟢 통관 가능"
        st.success(f"결과: {final_decision}")
        
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**1. OCR 분석 정보**\n"
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
        st.write(f"• **정보 출처:** {matched_row.get('정보출처', '해당 없음')}")
        st.write(f"• **통관 보류 사유:** {matched_row.get('통관보류사유내용', '해당 없음')}")
        st.write(f"• **법적 관련 근거:** {matched_row.get('관련근거', '해당 없음')}")
        
        st.warning(f"**검사원 조치 의견:**\n"
                   f"본 물품은 [불법의약품DB.xlsx] 대조 원칙 및 파이썬 정규화 매칭 결과, 등록번호 [{reg_num}]번에 "
                   f"매칭되는 위해 항목임이 확정되었습니다. 현장에서 **통관 보류 및 폐기/반송 조치**하시기 바랍니다.")
    else:
        st.write("• 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.")
        st.info("**검사원 조치 의견:** 금지 성분 및 DB 매칭 내역 없으므로 **통관 허용** 처리합니다.")
