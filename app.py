import streamlit as st
import pandas as pd
import json
import google.generativeai as genai
from PIL import Image
import io

# [설정] 웹 페이지 제목 및 모바일 최적화 레이아웃
st.set_page_config(page_title="해외 특송 위해물품 판정 시스템", layout="centered")

st.title("📱 현장 검사용 위해물품 스마트 판정기 (무료최적화)")
st.caption("스마트폰 사진을 자동 압축하여 구글 무료 서버(Free Tier) 한도 내에서 안전하게 구동합니다.")

# API 키 설정
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
if gemini_key:
    genai.configure(api_key=gemini_key)
else:
    st.error("Gems 설정 창(Secrets)에 GEMINI_API_KEY를 등록해 주세요.")

@st.cache_data
def load_db():
    try:
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

# 1. 모바일 카메라 / 파일 업로드
uploaded_file = st.file_uploader("📸 제품 전면 또는 성분표 사진을 촬영하세요", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="촬영된 현품 이미지", use_container_width=True)
    
    with st.spinner("Gemini AI가 이미지 압축 및 라벨 판독을 진행 중입니다..."):
        try:
            # 🚨 [핵심] 무료 티어 용량 초과 방지를 위한 스마트폰 사진 압축 로직
            image = Image.open(uploaded_file)
            
            # 스마트폰 사진이 너무 크면 가로세로 최대 1024px로 리사이징
            image.thumbnail((1024, 1024))
            
            # 압축된 이미지를 바이너리 데이터로 변환 (JPEG 화질 75%로 최적화)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=75)
            compressed_bytes = buffer.getvalue()
            
            image_parts = [{"mime_type": "image/jpeg", "data": compressed_bytes}]
            
            # 모델 설정 (하루 50회 미만은 pro / 그 이상 원하면 flash로 변경)
            #model = genai.GenerativeModel(model_name="gemini-2.0-pro")
            model = genai.GenerativeModel(model_name="gemini-1.5-pro")
            prompt = (
                "Analyze the image and extract product information. "
                "Respond ONLY in JSON format with keys: 'brand', 'product_name', 'barcode', 'ingredients'. "
                "Do not hypothesize or use external knowledge."
            )
            
            response = model.generate_content(
                contents=[prompt, image_parts[0]],
                generation_config={"response_mime_type": "application/json"}
            )
            
            ocr_result = json.loads(response.text)
            brand = ocr_result.get('brand', '확인 불가')
            product_name = ocr_result.get('product_name', '확인 불가')
            barcode = ocr_result.get('barcode', '바코드 확인 불가')
            ingredients = ocr_result.get('ingredients', [])
            
        except Exception as e:
            st.error(f"무료 서버 호출 제한 또는 이미지 오류 발생: {e}")
            st.info("💡 1분당 호출 한도를 초과했을 수 있습니다. 잠시 후 다시 촬영해 주세요.")
            brand, product_name, barcode, ingredients = '확인 불가', '확인 불가', '바코드 확인 불가', []

    # 2. 파이썬 Pandas 기반 100% 정밀 매칭 매커니즘
    matched_row = None
    match_type = "🟢 매칭되지 않음"
    
    if df_db is not None and product_name != '확인 불가':
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

    # 3. 리포트 화면 렌더링
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
    else:
        st.write("• 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않습니다.")
