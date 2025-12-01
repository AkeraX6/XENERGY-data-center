import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

# ======================================================
# PAGE HEADER
# ======================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Molino Data Processor</h2>"
    "<p style='text-align:center;color:gray;'>Multi-file merging, automatic noise removal & SAG data codification</p>"
    "<hr>",
    unsafe_allow_html=True,
)

# Back button
if st.button("⬅️ Back to Menu", key="back_es_molino"):
    st.session_state.page = "dashboard"
    st.rerun()

# ======================================================
# FILE UPLOAD (MULTIPLE)
# ======================================================
uploaded_files = st.file_uploader(
    "📤 Upload Molino Files (CSV or Excel) — Multiple Allowed",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("📂 Please upload one or more files to begin.")
    st.stop()

# ======================================================
# READ & MERGE ALL FILES
# ======================================================
dataframes = []
for file in uploaded_files:
    try:
        if file.name.lower().endswith(".csv"):
            df = pd.read_csv(file, sep=";", header=1)
        else:
            df = pd.read_excel(file, header=1)
        dataframes.append(df)
    except Exception as e:
        st.error(f"⚠️ Error reading {file.name}: {e}")

if not dataframes:
    st.error("❌ No valid files loaded. Check file format.")
    st.stop()

df = pd.concat(dataframes, ignore_index=True)

st.success(f"📌 Loaded & merged {len(uploaded_files)} files → {len(df)} rows")

# Standardize column names
df.columns = df.columns.astype(str).str.strip()

# ======================================================
# COLUMN CHECK
# ======================================================
if "Fuente de datos" not in df.columns:
    st.error("❌ Missing 'Fuente de datos' column in input files!")
    st.stop()
if "Valor" not in df.columns:
    st.error("❌ Missing 'Valor' column in input files!")
    st.stop()
if "Hora" not in df.columns:
    st.error("❌ Missing 'Hora' column in input files!")
    st.stop()

# ======================================================
# CREATE TYPE COLUMN
# ======================================================
def detect_type(s):
    s = s.lower()
    if "fino" in s: return 1
    if "grueso" in s: return 2
    if "interm" in s: return 3
    if "tph" in s and "sag" in s: return 4
    if "pres" in s: return 5
    if "pot" in s: return 6
    if "cons" in s: return 7
    if re.search(r"ch\d", s): return 8
    if "solido" in s: return 9
    return None

df["Type"] = df["Fuente de datos"].apply(detect_type)

# ======================================================
# CODE MAPPING
# ======================================================
mapping = {
    "lc_finos_sag1_new.value": 1, "lc_finos_sag2_new.value": 2, "lc_finos_sag3_new.value": 3,
    "ls1_finos_new.value": 4, "ls2_finos_new.value": 5,
    "lc_grueso_sag1_new.value": 1, "lc_grueso_sag2_new.value": 2,
    "lc_grueso_sag3_new.value": 3, "ls1_grueso_new.value": 4, "ls2_grueso_new.value": 5,
    "lc_interm_sag1_new.value": 1, "lc_interm_sag2_new.value": 2,
    "lc_interm_sag3_new.value": 3, "ls1_interm_new.value": 4, "ls2_interm_new.value": 5,
    "tph_sag1.value": 1, "tph_sag2.value": 2, "tph_sag3.value": 3,
    "tph_sag4.value": 4, "tph_sag5.value": 5,
    "pres_sag1.value": 1, "pres_sag2.value": 2, "pres_sag3.value": 3,
    "pres_sag4.value": 4, "pres_sag5.value": 5,
    "pot_sag1.value": 1, "pot_sag2.value": 2, "pot_sag3.value": 3,
    "pot_sag4.value": 4, "pot_sag5.value": 5,
    "cons_energ_sag4.value": 4, "cons_energ_sag5.value": 5,
    "ch1_tph.value": 1, "ch2_tph.value": 2, "ch3_tph.value": 3,
    "ch4_tph.value": 4, "ch5_tph.value": 5,
    "ls1_%solidoalimsag4.value": 1, "ls2_%solidoalimsg5.value": 2
}

def detect_code(s):
    s_clean = s.lower().replace(" ", "")
    return mapping.get(s_clean, None)

df["Code"] = df["Fuente de datos"].apply(detect_code)

# ======================================================
# SPLIT DATE & TIME
# ======================================================
hora = pd.to_datetime(df["Hora"], errors="coerce", dayfirst=True)

df["Day"] = hora.dt.day
df["Month"] = hora.dt.month
df["Year"] = hora.dt.year
df["Hour"] = hora.dt.hour
df["Minute"] = hora.dt.minute

# ======================================================
# CLEAN VALUE COLUMN
# ======================================================
df["Valor"] = df["Valor"].astype(str)
df["Valor"] = df["Valor"].str.replace(",", ".", regex=False)

df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

df = df[df["Valor"] > 0]  # remove invalid

# ======================================================
# FINAL EXPORT STRUCTURE
# ======================================================
excel_cols = ["Fuente de datos", "Type", "Code", "Day", "Month", "Year", "Hour", "Minute", "Valor"]
txt_cols = ["Type", "Code", "Day", "Month", "Year", "Hour", "Minute", "Valor"]

final_excel = df[excel_cols].copy()
final_txt = df[txt_cols].copy()

# ======================================================
# DOWNLOAD
# ======================================================
excel_buf = io.BytesIO()
final_excel.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

txt_data = final_txt.to_csv(index=False, sep=";")

col1, col2 = st.columns(2)
with col1:
    st.download_button("📘 Download Excel", excel_buf, "ES_Molino_Merged.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
with col2:
    st.download_button("📄 Download TXT", txt_data, "ES_Molino_Merged.txt",
                       mime="text/plain",
                       use_container_width=True)

st.success("🎯 Processing Complete — Merged Dataset Ready!")
