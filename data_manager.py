import pandas as pd
import streamlit as st
from utils import normalize_product_name # 분리한 utils 파일에서 함수를 불러옴

@st.cache_data
def load_and_standardize_db():
    # 불법의약품DB.xlsx 불러오고 구조화하는 기존 코드 내용...
    return df
