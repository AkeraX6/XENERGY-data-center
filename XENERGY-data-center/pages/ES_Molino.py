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
        # Read CSV (semicolon) or Excel
        if file.name.endswith(".csv"):
            df = pd.read_csv(file, sep=";", engine="python", dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)

        # Normalize headers only (not the data)
        df.columns = df.columns.str.strip().str.lower()

        # Check required columns
        if "fuente de datos" not in df.columns or "hora" not in df.columns or "valor" not in df.columns:
            errors.append(f"{file.name} → missing required columns")
            continue

        merged_df = pd.concat([merged_df, df], ignore_index=True)

    except Exception as e:
        errors.append(f"{file.name} → {e}")

if merged_df.empty:
    st.error("❌ No valid files uploaded. Make sure columns are: 'Fuente de datos;Hora;Valor'")
    st.stop()

if errors:
    st.warning(f"⚠️ Some files were skipped:\n- " + "\n- ".join(errors))

# Restore proper header names
merged_df.rename(columns={
    "fuente de datos": "Fuente de datos",
    "hora": "Hora",
    "valor": "Valor"
}, inplace=True)

# Strip spaces in Fuente de datos just in case
merged_df["Fuente de datos"] = merged_df["Fuente de datos"].astype(str).str.strip()

# ======================================================
# TYPE COLUMN
# ======================================================
def detect_type(text: str):
    t = text.lower()
    if "fino" in t:
        return 1
    if "grueso" in t:
        return 2
    if "interm" in t:
        return 3
    if "tph" in t and "sag" in t:
        return 4
    if "pres" in t:
        return 5
    if "pot" in t:
        return 6
    if "cons_energ" in t or "consenerg" in t:
        return 7
    if "ch" in t and "_tph" in t:
        return 8
    if "solido" in t:
        return 9
    return np.nan

merged_df["Type"] = merged_df["Fuente de datos"].apply(detect_type)

# ======================================================
# CODE COLUMN (EXACT LOOKUP TABLE)
# ======================================================
CODE_MAP = {
    "lc_finos_SAG1_new.Value": 1,
    "lc_finos_SAG2_new.Value": 2,
    "lc_finos_SAG3_new.Value": 3,
    "ls1_finos_new.Value": 4,
    "ls2_finos_new.Value": 5,

    "lc_grueso_SAG1_new.Value": 1,
    "lc_grueso_SAG2_new.Value": 2,
    "lc_grueso_SAG3_new.Value": 3,
    "ls1_grueso_new.Value": 4,
    "ls2_grueso_new.Value": 5,

    "lc_interm_SAG1_new.Value": 1,
    "lc_interm_SAG2_new.Value": 2,
    "lc_interm_SAG3_new.Value": 3,
    "ls1_interm_new.Value": 4,
    "ls2_interm_new.Value": 5,

    "tph_sag1.Value": 1,
    "tph_sag2.Value": 2,
    "tph_sag3.Value": 3,
    "tph_sag4.Value": 4,
    "tph_sag5.Value": 5,

    "pres_sag1.Value": 1,
    "lc_presdescansoSAG1.Value": 1,
    "pres_sag2.Value": 2,
    "lc_presdescansoSAG2.Value": 2,
    "pres_sag3.Value": 3,
    "lc_presdescansoSAG3.Value": 3,
    "pres_sag4.Value": 4,
    "ls1_presdescansoSAG4.Value": 4,
    "pres_sag5.Value": 5,
    "ls1_presdescansoSAG5.Value": 5,

    "pot_sag1.Value": 1,
    "lc_potSAG1.Value": 1,
    "pot_sag2.Value": 2,
    "lc_potSAG2.Value": 2,
    "pot_sag3.Value": 3,
    "lc_potSAG3.Value": 3,
    "pot_sag4.Value": 4,
    "ls1_potSAG4.Value": 4,
    "ls2_potSAG5.Value": 5,
    "pot_sag5.Value": 5,
    "ls1_consenergSAG4.Value": 4,
    "cons_energ_sag4.Value": 4,
    "cons_energ_sag5.Value": 5,
    "ls2_consenergSAG5.Value": 5,

    "ch1_tph.Value": 1,
    "ch2_tph.Value": 2,
    "ch3_tph.Value": 3,
    "ch4_tph.Value": 4,
    "ch5_tph.Value": 5,

    "ls1_%solidoalimSAG4.Value": 1,
    "ls2_%solidoalimSG5.Value": 2,
}

def detect_code(text: str):
    # Use exact mapping, try both original and lowercase variants for safety
    if text in CODE_MAP:
        return CODE_MAP[text]
    lower_text = text.lower()
    for key, val in CODE_MAP.items():
        if key.lower() == lower_text:
            return val
    return np.nan

merged_df["Code"] = merged_df["Fuente de datos"].apply(detect_code)

# ======================================================
# SPLIT DATE-TIME (Hora → Day/Month/Year/Hour/Minute)
# ======================================================
dt = pd.to_datetime(merged_df["Hora"], errors="coerce", dayfirst=True)
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
    .str.replace(",", ".", regex=False)  # in case some file uses comma
)

merged_df["Value"] = pd.to_numeric(merged_df["Value"], errors="coerce")

# Remove invalid rows (negative, zero, NaN, bad date)
merged_df = merged_df[
    (merged_df["Value"].notna()) &
    (merged_df["Value"] > 0) &
    (merged_df["Day"].notna())
]

# ======================================================
# DROP RAW COLUMNS
# ======================================================
merged_df.drop(columns=["Valor", "Hora"], inplace=True)

# ======================================================
# FINAL COLUMN ORDER
# ======================================================
excel_output = merged_df[
    ["Fuente de datos", "Type", "Code", "Day", "Month", "Year", "Hour", "Minute", "Value"]
]

txt_output = excel_output.drop(columns=["Fuente de datos"])

st.success("✅ Molino data processed successfully!")

st.subheader("📝 Data Preview")
st.dataframe(excel_output.head(20), use_container_width=True)

# ======================================================
# DOWNLOAD BUTTONS
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
        use_container_width=True,
    )

with colB:
    st.download_button(
        label="📗 Download TXT Result",
        data=txt_buf.getvalue(),
        file_name="ES_Molino_Output.txt",
        mime="text/plain",
        use_container_width=True,
    )
