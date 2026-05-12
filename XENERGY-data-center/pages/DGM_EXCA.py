import streamlit as st
import pandas as pd
import io
import re

# ======================================================
# PAGE HEADER
# ======================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — Excavator Performance Processor</h2>"
    "<p style='text-align:center;color:gray;'>Processes excavator rendimiento data and converts it to daily structured format.</p>"
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

# 2️⃣ Extract rendimiento values, rename, divide by 1000, and fill NaN with 0
clean_cols = {}
for c in rend_cols:
    new_name = c.replace("RENDIMIENTO", "").strip()
    new_name = new_name.replace("_", "").replace("  ", " ").strip()
    new_name = new_name.replace(" ", "_")
    clean_cols[c] = new_name

result = df[["Day", "Month", "Year"] + rend_cols].rename(columns=clean_cols)

# Divide rendimiento values by 1000 and fill NaN with 0
for col in clean_cols.values():
    result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)  # fill empty cells with 0
    result[col] = (result[col] / 1000).round(4)

steps.append("✅ Extracted rendimiento columns, renamed them, filled empty values with 0, and divided by 1000")

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

txt_buf = io.StringIO()
result.to_csv(txt_buf, index=False, header=False, sep="\t")

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
        "📄 Download TXT",
        data=txt_buf.getvalue(),
        file_name="DGM_Excavator_Output.txt",
        mime="text/plain",
        use_container_width=True,
    )

# ======================================================
# DATA QUALITY CHECK
# ======================================================
st.markdown("---")
st.subheader("🔍 Data Quality Check")

if st.button("▶️ Run Quality Check", use_container_width=True, key="dgm_exca_qc"):
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


