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
result.to_csv(txt_buf, index=False, header=False, sep="\t")  # TXT tab-separated, no headers

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

# ======================================================
# DATA QUALITY CHECK
# ======================================================
st.markdown("---")
st.subheader("🔍 Data Quality Check")

if st.button("▶️ Run Quality Check", use_container_width=True, key="dgm_frag_qc"):
    total_rows = len(result)

    if total_rows == 0:
        st.error("❌ No data to check — the dataset is empty after cleaning.")
    else:
        issues_found = False
        report_lines = []

        for col in result.columns:
            col_issues = []

            empty_count = int(result[col].isna().sum() + (result[col].astype(str).str.strip() == "").sum())
            if empty_count > 0:
                col_issues.append(f"**{empty_count}** empty value(s)")

            non_empty = result[col].dropna().astype(str).str.strip()
            non_empty = non_empty[non_empty != ""]

            if len(non_empty) > 0:
                text_mask = non_empty.apply(lambda x: bool(re.search(r"[A-Za-z]", str(x))))
                text_count = int(text_mask.sum())
            else:
                text_count = 0
            if text_count > 0:
                col_issues.append(f"**{text_count}** cell(s) contain text/letters")

            if len(non_empty) > 0:
                special_mask = non_empty.apply(lambda x: bool(re.search(r"[^0-9eE.\-+\s]", str(x))))
                special_count = int(special_mask.sum())
            else:
                special_count = 0
            if special_count > 0:
                examples = non_empty[special_mask].head(3).tolist()
                col_issues.append(f"**{special_count}** cell(s) with special characters (e.g. {examples})")

            if col_issues:
                issues_found = True
                report_lines.append(f"⚠️ **{col}**: " + " | ".join(col_issues))
            else:
                report_lines.append(f"✅ **{col}**: OK ({total_rows} values, all numeric)")

        if not issues_found:
            st.success("✅ All columns are clean — no empty values, no text, no special characters. Ready to download!")
        else:
            st.warning("⚠️ Some columns have issues. Review the report below:")

        for line in report_lines:
            st.markdown(line)

st.caption("Built by Maxam — Omar El Kendi")

