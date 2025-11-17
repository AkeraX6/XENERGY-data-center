import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import unicodedata

# ==========================================================
# NORMALIZATION HELPERS
# ==========================================================
def norm(s: str):
    if s is None:
        return ""
    s = str(s).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace(" ", "").replace("_", "")

def find_col(df, candidates):
    m = {norm(c): c for c in df.columns}
    for c in candidates:
        if c in m:
            return m[c]
    return None


# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Posición de Palas (ES_POSP)</h2>",
    unsafe_allow_html=True
)
st.markdown("<p style='text-align:center;color:gray;'>Procesamiento automático de datos de ubicación de palas.</p>", unsafe_allow_html=True)
st.markdown("---")

# BACK BUTTON
if st.button("⬅️ Back to Menu", key="back_esposp"):
    st.session_state.page = "dashboard"
    st.rerun()


# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel file", type=["xlsx","xls","csv"])

if uploaded_file is not None:

    # LOAD FILE
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file, engine="python")
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"❌ Error loading file: {e}")
        st.stop()

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head(10), use_container_width=True)
    st.info(f"📏 Total rows before cleaning: {len(df)}")

    steps = []
    deleted_total = 0

    # ==========================================================
    # PROCESSING STEPS (COLLAPSED LIKE OTHER CODES)
    # ==========================================================
    with st.expander("⚙️ Processing Steps (Click to Expand)", expanded=False):

        # =========== COLUMN DETECTION ===========
        col_fecha     = find_col(df, ["fecha"])
        col_turno     = find_col(df, ["turno"])
        col_cuadrilla = find_col(df, ["cuadrilla"])
        col_pala      = find_col(df, ["pala"])
        col_hcarga    = find_col(df, ["hcarga","h_carga","horacarga"])
        col_dumpx     = find_col(df, ["dumpx"])
        col_dumpy     = find_col(df, ["dumpy"])
        col_dumpz     = find_col(df, ["dumpz","cenz"])

        required = [col_fecha,col_turno,col_cuadrilla,col_pala,col_hcarga,col_dumpx,col_dumpy,col_dumpz]
        if any(c is None for c in required):
            st.error("❌ Some required columns were not found.")
            st.stop()

        # ========= FECHA SPLIT =========
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
        df["Dia"] = df[col_fecha].dt.day
        df["Mes"] = df[col_fecha].dt.month
        df["Año"] = df[col_fecha].dt.year
        steps.append("✔️ FECHA column split into Día, Mes, Año.")

        # ========= TURN0 =========
        df[col_turno] = df[col_turno].astype(str).str.upper().str.strip()
        df["Turno"] = df[col_turno].replace({"D":1,"N":2}).fillna(1)
        steps.append("✔️ Turno converted (D=1, N=2).")

        # ========= CUADRILLA =========
        df[col_cuadrilla] = df[col_cuadrilla].astype(str).str.upper().str.strip()
        df["Cuadrilla"] = df[col_cuadrilla].replace({"A":1,"B":2,"C":3,"D":4})
        steps.append("✔️ Cuadrilla converted (A=1, B=2, C=3, D=4).")

        # ========= PALA FILTER =========
        before = len(df)
        df = df[df[col_pala].astype(str).str.contains("SHE00", case=False, na=False)]
        deleted = before - len(df)
        deleted_total += deleted
        steps.append(f"✔️ Pala filtered (SHE00XX only). Deleted: {deleted}")

        # Extract trailing digits → convert to integer → remove leading zeros
        df["Pala"] = (
            df[col_pala]
            .astype(str)
            .str.extract(r"(\d+)$")[0]        # extract numbers
            .astype(float)                    # convert to numeric
            .fillna(0)
            .astype(int)                      # final clean integer
)
        steps.append("✔️ Pala transformed (SHE0067 → 67).")

        # ========= H_CARGA SPLIT =========
        def split_hm(val):
            if pd.isna(val):
                return (None,None)
            m = re.match(r"(\d+):(\d+)", str(val))
            return (int(m.group(1)), int(m.group(2))) if m else (None,None)

        df["Hora"], df["Minuto"] = zip(*df[col_hcarga].apply(split_hm))
        steps.append("✔️ H_CARGA split into Hora and Minuto.")

        # ========= DUMPX FILTER =========
        before = len(df)
        df = df[(df[col_dumpx] >= 16000) & (df[col_dumpx] <= 40000)]
        deleted = before - len(df)
        deleted_total += deleted
        steps.append(f"✔️ DumpX filtered (16000–40000). Deleted: {deleted}")

        # ========= DUMPY FILTER =========
        before = len(df)
        df = df[df[col_dumpy] >= 110000]
        deleted = before - len(df)
        deleted_total += deleted
        steps.append(f"✔️ DumpY filtered (>110000). Deleted: {deleted}")

        # ========= DUMPZ FILTER =========
        before = len(df)
        df = df[(df[col_dumpz] >= 2000) & (df[col_dumpz] <= 5000)]
        deleted = before - len(df)
        deleted_total += deleted
        steps.append(f"✔️ DumpZ/CENZ filtered (2000–5000). Deleted: {deleted}")

        # Show steps in green cards (same style as other tools)
        for step in steps:
            st.markdown(
                f"<div style='background:#e8f8f0;padding:8px;border-radius:6px;margin-bottom:6px;'><span style='color:#137333'>{step}</span></div>",
                unsafe_allow_html=True
            )


    # ==========================================================
    # CLEANED DATA PREVIEW
    # ==========================================================
    st.markdown("---")
    st.subheader("📌 Cleaned Data Preview")

    df_out = df[["Dia","Mes","Año","Turno","Cuadrilla","Pala","Hora","Minuto",
                 col_dumpx,col_dumpy,col_dumpz]]
    df_out = df_out.rename(columns={col_dumpx:"X", col_dumpy:"Y", col_dumpz:"Z"})

    st.dataframe(df_out.head(20), use_container_width=True)
    st.success(f"✅ Final dataset: {len(df_out)} rows. Total deleted: {deleted_total}")

    # ==========================================================
    # DOWNLOAD SECTION
    # ==========================================================
    st.markdown("---")
    st.subheader("💾 Export Cleaned File")

    excel_buffer = io.BytesIO()
    df_out.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    txt_buffer = io.StringIO()
    df_out.to_csv(txt_buffer, sep="\t", index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📘 Download Excel", excel_buffer, "ES_POSP_Cleaned.xlsx")
    with col2:
        st.download_button("📄 Download TXT", txt_buffer.getvalue(), "ES_POSP_Cleaned.txt")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam - Omar El Kendi -")

else:
    st.info("📂 Please upload a file to begin.")
