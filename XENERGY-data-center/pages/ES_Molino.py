import streamlit as st
import pandas as pd
import numpy as np
import io

# ======================================================
# PAGE TITLE & BACK BUTTON
# ======================================================
col1, col2 = st.columns([0.15, 0.85])
with col1:
    if st.button("⬅️ Back to Menu", key="back_molino"):
        st.session_state.page = "dashboard"
        st.rerun()

with col2:
    st.markdown("### ⚙️ ES — Molino Data Processor")

st.info("📌 You can upload multiple CSV / Excel files at once.")

# ======================================================
# FILE UPLOAD
# ======================================================
uploaded_files = st.file_uploader(
    "📤 Upload Molino Data Files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.stop()

# ======================================================
# READ & MERGE FILES
# ======================================================
merged_df = pd.DataFrame()
errors = []

for file in uploaded_files:
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file, sep=";", engine="python", dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower()

        # Validate required columns
        if "fuente de datos" not in df.columns or "hora" not in df.columns or "valor" not in df.columns:
            errors.append(file.name)
            continue

        merged_df = pd.concat([merged_df, df], ignore_index=True)

    except Exception as e:
        errors.append(f"{file.name} → {e}")

if merged_df.empty:
    st.error("❌ No valid files uploaded. Check column names and format.")
    st.stop()

if errors:
    st.warning(f"⚠️ Some files were skipped: {errors}")

# Rename columns properly after merge
merged_df.rename(columns={"fuente de datos": "Fuente de datos",
                          "hora": "Hora",
                          "valor": "Valor"}, inplace=True)

# ======================================================
# ADD TYPE COLUMN
# ======================================================
def detect_type(text):
    text = text.lower()
    if "fino" in text:
        return 1
    if "grueso" in text:
        return 2
    if "interm" in text:
        return 3
    if "tph" in text and "sag" in text:
        return 4
    if "pres" in text:
        return 5
    if "pot" in text:
        return 6
    if "cons" in text:
        return 7
    if "ch" in text:
        return 8
    if "solido" in text:
        return 9
    return np.nan

merged_df["Type"] = merged_df["Fuente de datos"].apply(detect_type)

# ======================================================
# ADD CODE COLUMN (specific SAG numbering)
# ======================================================
def detect_code(text):
    import re
    match = re.search(r"(\d)", text)
    if match:
        return int(match.group(1))
    return np.nan

merged_df["Code"] = merged_df["Fuente de datos"].apply(detect_code)

# ======================================================
# PROCESS DATE-TIME COLUMN
# ======================================================
dt = pd.to_datetime(merged_df["Hora"], errors="coerce")
merged_df["Day"] = dt.dt.day
merged_df["Month"] = dt.dt.month
merged_df["Year"] = dt.dt.year
merged_df["Hour"] = dt.dt.hour
merged_df["Minute"] = dt.dt.minute

# ======================================================
# CLEAN VALUE COLUMN
# ======================================================
merged_df["Value"] = (
    merged_df["Valor"]
    .astype(str)
    .str.replace(",", ".", regex=False)
)

merged_df["Value"] = pd.to_numeric(merged_df["Value"], errors="coerce")

# Remove invalid values
merged_df = merged_df[
    (merged_df["Value"].notna()) &
    (merged_df["Value"] > 0)
]

# ======================================================
# REMOVE COLUMNS NOT NEEDED
# ======================================================
merged_df.drop(columns=["Valor", "Hora"], inplace=True)

# ======================================================
# SORT FINAL COLUMNS ORDER
# ======================================================
excel_output = merged_df[
    ["Fuente de datos", "Type", "Code", "Day", "Month", "Year", "Hour", "Minute", "Value"]
]

txt_output = excel_output.drop(columns=["Fuente de datos"])

st.success("✅ Processing Completed Successfully!")

st.subheader("📝 Data Preview")
st.dataframe(excel_output.head(20), use_container_width=True)

# ======================================================
# DOWNLOADS
# ======================================================
excel_buf = io.BytesIO()
excel_output.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

txt_buf = io.StringIO()
txt_output.to_csv(txt_buf, index=False, sep="\t")

colA, colB = st.columns(2)

with colA:
    st.download_button(
        label="📘 Download Excel Result",
        data=excel_buf,
        file_name="ES_Molino_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

with colB:
    st.download_button(
        label="📗 Download TXT Result",
        data=txt_buf.getvalue(),
        file_name="ES_Molino_Output.txt",
        mime="text/plain",
        use_container_width=True
    )

