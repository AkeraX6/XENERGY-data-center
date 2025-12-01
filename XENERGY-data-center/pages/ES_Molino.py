import streamlit as st
import pandas as pd
import io
import re

# ===============================
# PAGE TITLE
# ===============================
st.markdown(
    "<h2 style='text-align:center;'>ES — Molino Data Processor</h2>"
    "<p style='text-align:center;color:gray;'>Classifies and cleans SAG mill data</p><hr>",
    unsafe_allow_html=True,
)

# Back button
if st.button("⬅️ Back to Menu", key="back_to_menu_molino"):
    st.session_state.page = "dashboard"
    st.rerun()

# ===============================
# FILE UPLOAD
# ===============================
uploaded = st.file_uploader("📤 Upload Molino CSV/Excel File", type=["csv", "xlsx"])

if uploaded is None:
    st.info("📂 Please upload a file to begin.")
    st.stop()

# Read file
try:
    if uploaded.name.endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"⚠️ Error loading file: {e}")
    st.stop()

# Standardize column names
df.columns = df.columns.str.strip()

if "Fuente de datos" not in df.columns or "Valor" not in df.columns or "Hora" not in df.columns:
    st.error("❌ Required columns missing: Fuente de datos / Hora / Valor")
    st.stop()

# =====================================================
# Add TYPE column
# =====================================================
conditions = {
    r"fino": 1,
    r"grueso": 2,
    r"interm": 3,
    r"tph|tp_sag": 4,
    r"pres": 5,
    r"pot": 6,
    r"cons_energ": 7,
    r"ch\d": 8,
    r"solido": 9,
}

def assign_type(text):
    for k, v in conditions.items():
        if re.search(k, text, re.IGNORECASE):
            return v
    return None

df["Type"] = df["Fuente de datos"].apply(assign_type)

# =====================================================
# Add CODE column based on exact mapping
# =====================================================

mapping = {
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
    "pres_sag2.Value": 2,
    "pres_sag3.Value": 3,
    "pres_sag4.Value": 4,
    "pres_sag5.Value": 5,
    "pot_sag1.Value": 1,
    "pot_sag2.Value": 2,
    "pot_sag3.Value": 3,
    "pot_sag4.Value": 4,
    "pot_sag5.Value": 5,
    "cons_energ_sag4.Value": 4,
    "cons_energ_sag5.Value": 5,
    "ch1_tph.Value": 1,
    "ch2_tph.Value": 2,
    "ch3_tph.Value": 3,
    "ch4_tph.Value": 4,
    "ch5_tph.Value": 5,
    "ls1_%solidoalimSAG4.Value": 1,
    "ls2_%solidoalimSG5.Value": 2
}

df["Code"] = df["Fuente de datos"].map(mapping)

# =====================================================
# Clean Value column
# Fix number commas "100,234,500" → 100.234500 etc.
# Remove negatives, zeros, empty
# =====================================================

df["Valor"] = (
    df["Valor"]
    .astype(str)
    .str.replace(r"[^\d,.-]", "", regex=True)
    .str.replace(",", ".", regex=False)
)

df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

df = df[df["Valor"].notna() & (df["Valor"] > 0)]
df = df.rename(columns={"Valor": "Value"})

# =====================================================
# Split time column
# =====================================================
df["Hora"] = pd.to_datetime(df["Hora"], dayfirst=True, errors="coerce")

df["Day"] = df["Hora"].dt.day
df["Month"] = df["Hora"].dt.month
df["Year"] = df["Hora"].dt.year
df["Hour"] = df["Hora"].dt.hour
df["Minute"] = df["Hora"].dt.minute

# Drop original Hora
df = df.drop(columns=["Hora"])

# =====================================================
# Final and download
# =====================================================
st.subheader("🧹 Final Clean Data Preview")
st.dataframe(df.head(25), use_container_width=True)

output = io.BytesIO()
df.to_excel(output, index=False, engine="openpyxl")
output.seek(0)

st.download_button(
    "📩 Download Clean Molino File",
    data=output,
    file_name="ES_Molino_Clean.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.success(f"✔ Processing complete — {len(df)} valid rows!")


