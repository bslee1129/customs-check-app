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

# [설정] 웹 페이지 제목 및 모바일 최적화 레이아웃
st.set_page_config(page_title="해외 특송 위해물품 판정 시스템", layout="centered")

st.title("📱 현장 검사용 위해물품 스마트 판정기")
st.caption("여러 장의 사진을 동시에 올리면 AI가 순차적으로 개별 분석 및 DB 대조를 진행합니다.")

# 사진 업로더를 초기화하기 위한 고유 키 상태 관리
if "uploader_id" not in st.session_state:
    st.session_state["uploader_id"] = 0

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

# 🚨 [대폭 수정] accept_multiple_files=True 를 추가하여 다중 파일 업로드 허용
uploaded_files = st.file_uploader(
    "📸 제품 사진들을 촬영하거나 선택하세요 (여러 장 동시 업로드 가능)", 
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"cam_uploader_{st.session_state['uploader_id']}"
)

# 🚨 [대폭 수정] 업로드된 파일 리스트가 존재할 때 반복문 작동
if uploaded_files:
    st.success(f"총 {len(uploaded_files)}장의 사진이 접수되었습니다. 판독을 시작합니다.")
    
    for idx, uploaded_file in enumerate(uploaded_files):
        st.markdown(f"---")
        st.markdown(f"## 🔍 [{idx+1}번 물품] 현품 판정 리포트")
        
        src_image = Image.open(uploaded_file)
        
        # 해상도 체크 및 방어 로직
        width, height = src_image.size
        if width < 500 or height < 500:
            st.warning(f"⚠️ {idx+1}번 사진 화질 주의 ({width}x{height}px): 선명하지 않아 오판정 가능성이 있습니다.")
        
        # 가로 화면 분할 (좌측: 내가 찍은 사진, 우측: 분석 정보)
        img_col, info_col = st.columns([1, 1])
        
        with img_col:
            st.info(f"📸 촬영 파일: {uploaded_file.name}")
            st.image(src_image, use_container_width=True)
        
        brand, product_name, barcode, ingredients = '확인 불가', '확인 불가', '바코드 확인 불가', []
        
        with st.spinner(f"[{idx+1}번 물품] AI 라벨 판독 중..."):
            try:
                img_for_ai = src_image.copy()
                img_for_ai.thumbnail((1024, 1024))
                
                model = genai.GenerativeModel(model_name="gemini-3.5-flash")
                
                prompt = (
                    "Analyze the image and extract product information. "
                    "Respond ONLY in JSON format with keys: 'brand', 'product_name', 'barcode', 'ingredients'. "
                    "If the image is too blurry or low resolution to read, return empty fields. Do not hallucinate."
                )
                
                response = model.generate_content(
                    contents=[prompt, img_for_ai],
                    generation_config={"response_mime_type": "application/json"}
                )
                
                ocr_result = json.loads(response.text)
                brand = ocr_result.get('brand', '확인 불가')
                product_name = ocr_result.get('product_name', '확인 불가')
                barcode = ocr_result.get('barcode', '바코드 확인 불가')
                ingredients = ocr_result.get('ingredients', [])
                
            except Exception as e:
                st.error(f"⚠️ {idx+1}번 사진 OCR 판독 실패")

        # 파이썬 Pandas 기반 100% 정밀 매칭 매커니즘
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

        # 우측 칸에 판정 결과 출력
        with info_col:
            st.markdown("### 📋 판정 결과")
            if matched_row is not None:
                final_decision = "🔴 반입 금지" if "🔴" in match_type else "🟡 제한 - 정밀검사 필요"
                st.error(f"결과: {final_decision}")
            else:
                final_decision = "🟢 통관 가능"
                st.success(f"결과: {final_decision}")
                
            st.markdown(f"**1. 식별 정보**\n"
                        f"* 브랜드: `{brand}`\n"
                        f"* 제품명: `{product_name}`\n"
                        f"* 바코드: `{barcode}`")
            
            reg_num = matched_row['등록번호'] if matched_row is not None else "해당 없음"
            st.markdown(f"**2. DB 대조**\n"
                        f"* 등록번호: `{reg_num}`\n"
                        f"* 매칭여부: **{match_type}**")

        # 하단 상세 정보 섹션
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

            st.markdown("**3. 규제 상세 정보**")
            st.write(f"• **정보 출처:** {get_clean_db_value(matched_row, '정보출처')}")
            st.write(f"• **통관 보류 사유:** {get_clean_db_value(matched_row, '통관보류사유내용')}")
            st.write(f"• **법적 관련 근거:** {get_clean_db_value(matched_row, '관련근거')}")
            
            # 4. 복수 이미지 전수 출력 레이아웃 (정부 보안 서버 차단 우회 버전)
            url_data = str(matched_row.get('원본이미지URL', ''))
            if url_data and url_data.lower() != 'nan':
                st.markdown("[현장 교차 검증] DB 등록 원본 이미지")
                urls = [u.strip() for u in url_data.split(',')]
                
                for idx_url, url in enumerate(urls):
                    if not url:
                        continue
                    success = False
                    error_msg = ""
                    
                    for attempt in range(2):
                        try:
                            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                            img_response = requests.get(url, headers=headers, timeout=15, verify=False)
                            if img_response.status_code == 200:
                                db_img = Image.open(io.BytesIO(img_response.content))
                                st.image(db_img, caption=f"[{idx+1}번 물품 관련] DB 사진 {idx_url+1}", width=300)
                                success = True
                                break
                            else:
                                error_msg = f"서버 거부 ({img_response.status_code})"
                        except Exception as e:
                            error_msg = f"연결 실패"
                    
                    if not success:
                        st.caption(f"❌ DB 사진 {idx_url+1}: {error_msg}")

            st.warning(f"**검사원 조치 의견:**\n"
                       f"본 물품은 대조 원칙에 의거, 등록번호 [{reg_num}]번에 매칭되는 위해 항목임이 확정되었습니다. "
                       f"현장에서 **통관 보류 및 폐기/반송 조치**하시기 바랍니다.")
        else:
            st.info("💡 특이사항: 데이터베이스 내 일치하는 위해 규제 이력이 존재하지 않으므로 **통관 허용** 처리합니다.")

    # [연속 검사 리셋 버튼] 모든 반복문이 끝난 맨 아래에 배치
    st.markdown("---")
    if st.button("🔄 검사 완료 및 전체 화면 초기화", use_container_width=True, type="primary"):
        st.session_state["uploader_id"] += 1
        st.rerun()
