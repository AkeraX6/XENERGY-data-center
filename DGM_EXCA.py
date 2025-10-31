import streamlit as st
import pandas as pd
import io

# ======================================================
# PAGE HEADER
# ======================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — Excavator Performance Processor</h2>"
    "<p style='text-align:center;color:gray;'>Extracts daily rendimiento per excavator and structures data by day, month, and year.</p>"
    "<hr>",
    unsafe_allow_html=True,
)

# Back button
if st.button("⬅️ Back to Menu", key="back_dgm_exca"):
    st.session_state.page = "dashboard"
    st.rerun()

# ======================================================
# FILE UPLOAD
# ======================================================
uploaded = st.file_uploader("📤 Upload Excavator Performance Excel File", type=["xlsx", "xls"])

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

df.columns = df.columns.astype(str).str.strip().str.replace("\n", " ", regex=False)

st.subheader("📄 Original Data Preview")
st.dataframe(df.head(10), use_container_width=True)
st.info(f"Loaded {len(df)} rows and {len(df.columns)} columns.")

# ======================================================
# DETECT REQUIRED COLUMNS
# ======================================================
expected = [
    "RENDIMIENTO PA_01",
    "RENDIMIENTO PA_02",
    "RENDIMIENTO PC_8000",
    "RENDIMIENTO PC_5500",
    "RENDIMIENTO CF_01",
    "RENDIMIENTO CF_02",
    "RENDIMIENTO CF_03",
]

def find_col(df, name):
    for c in df.columns:
        if name.lower() in c.lower():
            return c
    return None

col_fecha = find_col(df, "FECHA")
rend_cols = [find_col(df, col) for col in expected]

missing = [col for col, found in zip(expected, rend_cols) if not found]
if not col_fecha:
    st.error("❌ Column 'FECHA' not found.")
    st.stop()
if missing:
    st.warning(f"⚠️ Missing rendimiento columns: {missing}")

# Keep only existing rendimiento columns
rend_cols = [c for c in rend_cols if c is not None]

# ======================================================
# PROCESSING
# ======================================================
steps = []

# 1️⃣ Split FECHA column
fechas = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
df["Day"] = fechas.dt.day
df["Month"] = fechas.dt.month
df["Year"] = fechas.dt.year
steps.append("✅ Split FECHA into Day / Month / Year")

# 2️⃣ Extract rendimiento values and rename
clean_cols = {}
for c in rend_cols:
    new_name = c.replace("RENDIMIENTO", "").strip()
    new_name = new_name.replace("_", "").replace("  ", " ").strip()
    new_name = new_name.replace(" ", "_")
    clean_cols[c] = new_name

result = df[["Day", "Month", "Year"] + rend_cols].rename(columns=clean_cols)
steps.append("✅ Extracted rendimiento columns and renamed them to clean excavator references")

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
result.to_csv(csv_buf, index=False)

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel",
        data=excel_buf,
        file_name="DGM_Excavator_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col2:
    st.download_button(
        "📗 Download CSV",
        data=csv_buf.getvalue(),
        file_name="DGM_Excavator_Output.csv",
        mime="text/csv",
        use_container_width=True,
    )
