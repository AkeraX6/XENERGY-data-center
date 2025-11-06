import streamlit as st
import pandas as pd
import re
import io
import unicodedata

# ======================================================
# PAGE HEADER
# ======================================================
st.markdown(
    """
    <h2 style='text-align:center;'>DGM — Fragmentation Processor</h2>
    <p style='text-align:center;color:gray;'>
    Automatically extracts Day, Month, Year, Expansion, Level, PALA, P50, P80, and %PASANTE2 from fragmentation files.
    </p>
    <hr>
    """,
    unsafe_allow_html=True,
)

# ======================================================
# FILE UPLOAD
# ======================================================
uploaded = st.file_uploader("📤 Upload your Fragmentation Excel File", type=["xlsx", "xls"])
if uploaded is None:
    st.info("📂 Please upload a file to begin.")
    st.stop()

# ======================================================
# LOAD FILE
# ======================================================
try:
    df = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"❌ Could not read the file: {e}")
    st.stop()

# Clean column names
df.columns = (
    df.columns.astype(str)
    .str.strip()
    .str.replace("\n", " ", regex=False)
    .str.replace("’", "'", regex=False)
)

st.subheader("📄 Original Data Preview")
st.dataframe(df.head(10), use_container_width=True)
st.info(f"Loaded {len(df)} rows and {len(df.columns)} columns.")

# ======================================================
# FLEXIBLE COLUMN DETECTION
# ======================================================
def normalize(s):
    s = str(s).lower()
    s = unicodedata.normalize("NFD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    return s

def find_col(df, *patterns):
    for c in df.columns:
        name = normalize(c)
        for p in patterns:
            if normalize(p) in name:
                return c
    return None

col_fecha = find_col(df, "fecha medicion", "fecha", "medicion")
col_id = find_col(df, "id tronadura", "tronadura", "blast id", "id")
col_pala = find_col(df, "pala")
col_p50 = find_col(df, "p50")
col_p80 = find_col(df, "p80")
col_pasante = find_col(df, "% pasante", "pasante", "pasante 2", "<2", "2 pulgadas")

if not all([col_fecha, col_id, col_pala, col_p50, col_p80, col_pasante]):
    st.error("❌ Some required columns are missing. Please check your file headers.")
    st.write("Detected columns:", df.columns.tolist())
    st.stop()

# ======================================================
# FUNCTIONS
# ======================================================
def extract_expansion(text):
    if pd.isna(text):
        return pd.NA
    text = str(text).upper()
    match = re.search(r"F[_\-]?0*(\d{1,2})", text)
    return int(match.group(1)) if match else pd.NA

def extract_level(text):
    if pd.isna(text):
        return pd.NA
    text = str(text).upper()
    match = re.search(r"(\d{4})", text)
    return int(match.group(1)) if match else pd.NA

# --- Clean only PA_01 and PA_02
def clean_pala(val):
    if pd.isna(val):
        return pd.NA
    val = str(val).upper().strip()
    if val == "PA_01":
        return 1
    elif val == "PA_02":
        return 2
    else:
        return pd.NA  # delete others later

# ======================================================
# MAIN PROCESS
# ======================================================
steps = []

# 1️⃣ Split FECHA MEDICION
fechas = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
day = fechas.dt.day
month = fechas.dt.month
year = fechas.dt.year
steps.append("✅ FECHA MEDICION split into Day / Month / Year")

# 2️⃣ Extract Expansion + Level from ID TRONADURA
expansion = df[col_id].apply(extract_expansion)
level = df[col_id].apply(extract_level)
steps.append("✅ Extracted Expansion and Level from ID TRONADURA")

# 3️⃣ Build clean result
result = pd.DataFrame({
    "Day": day,
    "Month": month,
    "Year": year,
    "Expansion": expansion,
    "Level": level,
    "PALA": df[col_pala],
    "P50 [\"]": df[col_p50],
    "P80 [\"]": df[col_p80],
    "% PASANTE 2\"": df[col_pasante],
})

# 4️⃣ Clean PALA (keep only PA_01 & PA_02)
before = len(result)
result["PALA"] = result["PALA"].apply(clean_pala)
result = result[result["PALA"].isin([1, 2])]
after = len(result)
steps.append(f"✅ Kept only PALA PA_01 and PA_02 (converted to 1 & 2) — removed {before - after} rows.")

# ======================================================
# DISPLAY RESULTS
# ======================================================
with st.expander("⚙️ Processing Summary", expanded=True):
    for s in steps:
        st.markdown(
            f"<div style='background:#e8f8f0;border-radius:8px;padding:10px;margin-bottom:6px;color:#137333;'>{s}</div>",
            unsafe_allow_html=True,
        )

st.subheader("✅ Final Clean Result (first 20 rows)")
st.dataframe(result.head(20), use_container_width=True)
st.success(f"✅ Final dataset: {len(result)} rows × {len(result.columns)} columns")

# ======================================================
# DOWNLOAD
# ======================================================
excel_buf = io.BytesIO()
result.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

csv_buf = io.StringIO()
result.to_csv(csv_buf, index=False, sep=";")

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel",
        data=excel_buf,
        file_name="DGM_Fragmentation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col2:
    st.download_button(
        "📗 Download CSV",
        data=csv_buf.getvalue(),
        file_name="DGM_Fragmentation_Output.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.caption("Built by Maxam — Omar El Kendi")
