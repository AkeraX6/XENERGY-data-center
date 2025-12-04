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
col_resi = find_col(df, "resi", "residual")

if not all([col_fecha, col_id, col_pala, col_p50, col_p80, col_pasante]):
    st.error("❌ Some required columns are missing. Please check your file headers.")
    st.write("Detected columns:", df.columns.tolist())
    st.stop()

# ======================================================
# FUNCTIONS
# ======================================================
def extract_expansion(text):
    if pd.isna(text): return pd.NA
    text = str(text).upper()
    match = re.search(r"F[_\-]?0*(\d{1,2})", text)
    return int(match.group(1)) if match else pd.NA

def extract_level(text):
    if pd.isna(text): return pd.NA
    text = str(text).upper()
    match = re.search(r"(\d{4})", text)
    return int(match.group(1)) if match else pd.NA

def clean_pala(val):
    if pd.isna(val): return pd.NA
    val = str(val).upper().strip()
    if val == "PA_01": return 1
    if val == "PA_02": return 2
    return pd.NA

# ======================================================
# MAIN PROCESS
# ======================================================
steps = []

# FECHA MEDICION → Day, Month, Year
fechas = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
result = pd.DataFrame({
    "Day": fechas.dt.day,
    "Month": fechas.dt.month,
    "Year": fechas.dt.year,
    "Expansion": df[col_id].apply(extract_expansion),
    "Level": df[col_id].apply(extract_level),
    "PALA": df[col_pala].apply(clean_pala),
    "P50 [\"]": df[col_p50],
    "P80 [\"]": df[col_p80],
    "% PASANTE 2\"": df[col_pasante]
})
steps.append("✅ Extracted Day/Month/Year, Expansion, Level, and cleaned PALA")

# Keep only PA_01 & PA_02
before = len(result)
result = result[result["PALA"].isin([1, 2])]
steps.append(f"✅ Removed rows without valid PALA (removed {before - len(result)})")

# Convert `% PASANTE 2"` to percent (×100)
result["% PASANTE 2\""] = pd.to_numeric(result["% PASANTE 2\""], errors="coerce") * 100

# Convert Residual if exists
if col_resi:
    result["Residual [%]"] = pd.to_numeric(df[col_resi], errors="coerce") * 100
    steps.append("🔁 Converted Residual values to percentage")
else:
    steps.append("ℹ️ Residual column not found — skipped")

# ======================================================
# DISPLAY RESULTS
# ======================================================
with st.expander("⚙️ Processing Summary", expanded=True):
    for s in steps:
        st.success(s)

st.subheader("✅ Final Clean Result (first 20 rows)")
st.dataframe(result.head(20), use_container_width=True)
st.success(f"Final dataset: {len(result)} rows × {len(result.columns)} columns")

# ======================================================
# DOWNLOAD
# ======================================================
excel_buf = io.BytesIO()
result.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

txt_buf = io.StringIO()
result.to_csv(txt_buf, index=False, sep="\t")  # TXT tab-separated

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
        "📄 Download TXT",
        data=txt_buf.getvalue(),
        file_name="DGM_Fragmentation_Output.txt",
        mime="text/plain",
        use_container_width=True,
    )

st.caption("Built by Maxam — Omar El Kendi")

