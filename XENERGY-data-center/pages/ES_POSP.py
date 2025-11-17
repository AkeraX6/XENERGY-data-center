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
    """Normalize column names: lowercase, remove spaces, accents, underscores."""
    if s is None:
        return ""
    s = str(s).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace(" ", "").replace("_", "")
    return s

def find_col(df, candidates):
    """Return actual column name from a list of normalized candidate names."""
    norm_map = {norm(c): c for c in df.columns}
    for cand in candidates:
        if cand in norm_map:
            return norm_map[cand]
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

# BACK TO MENU
if st.button("⬅️ Back to Menu", key="back_esposp"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader("📤 Upload your Excel file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:

    # TRY LOAD
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file, encoding="latin1", engine="python")
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"❌ Error loading file: {e}")
        st.stop()

    st.subheader("📄 Original Data")
    st.dataframe(df.head(), use_container_width=True)
    st.info(f"Total rows before cleaning: {len(df)}")

    steps = []
    deleted_total = 0

    # ==========================================================
    # COLUMN DETECTION
    # ==========================================================
    col_fecha     = find_col(df, ["fecha"])
    col_turno     = find_col(df, ["turno"])
    col_cuadrilla = find_col(df, ["cuadrilla"])
    col_pala      = find_col(df, ["pala"])
    col_hcarga    = find_col(df, ["hcarga", "horacarga", "h_carga"])
    col_dumpx     = find_col(df, ["dumpx"])
    col_dumpy     = find_col(df, ["dumpy"])
    col_dumpz     = find_col(df, ["dumpz", "cenz"])   # <-- Z alternative

    required = [col_fecha, col_turno, col_cuadrilla, col_pala, col_hcarga, col_dumpx, col_dumpy, col_dumpz]
    if any(c is None for c in required):
        st.error("❌ Some required columns were NOT found. Check column names in the file.")
        st.write("Detected:")
        st.write({
            "Fecha": col_fecha,
            "Turno": col_turno,
            "Cuadrilla": col_cuadrilla,
            "Pala": col_pala,
            "H_Carga": col_hcarga,
            "DumpX": col_dumpx,
            "DumpY": col_dumpy,
            "DumpZ / CENZ": col_dumpz
        })
        st.stop()

    # ==========================================================
    # 1️⃣ FECHA → Dia, Mes, Año
    # ==========================================================
    try:
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
        df["Dia"] = df[col_fecha].dt.day
        df["Mes"] = df[col_fecha].dt.month
        df["Año"] = df[col_fecha].dt.year
        steps.append("✔️ Fecha separada en Día, Mes, Año.")
    except:
        st.error("❌ Error converting FECHA column.")
        st.stop()

    # ==========================================================
    # 2️⃣ TURNO → D=1, N=2
    # ==========================================================
    df[col_turno] = df[col_turno].astype(str).str.strip().str.upper()
    df["Turno"] = df[col_turno].replace({"D": 1, "N": 2})
    df["Turno"] = df["Turno"].fillna(1)
    steps.append("✔️ Turno convertido (D=1, N=2).")

    # ==========================================================
    # 3️⃣ CUADRILLA → A=1, B=2, C=3, D=4
    # ==========================================================
    df[col_cuadrilla] = df[col_cuadrilla].astype(str).str.strip().str.upper()
    df["Cuadrilla"] = df[col_cuadrilla].replace({"A": 1, "B": 2, "C": 3, "D": 4})
    steps.append("✔️ Cuadrilla convertida a números.")

    # ==========================================================
    # 4️⃣ PALA → Keep only SHE00XX and extract number
    # ==========================================================
    before = len(df)
    df = df[df[col_pala].astype(str).str.contains("SHE00", case=False, na=False)]
    deleted = before - len(df)
    deleted_total += deleted
    steps.append(f"✔️ Pala filtrada (solo SHE00XX). Filas eliminadas: {deleted}")

    df["Pala"] = df[col_pala].astype(str).str.extract(r"(\d+)$")
    steps.append("✔️ Pala convertida a números finales (SHE0097 → 97).")

    # ==========================================================
    # 5️⃣ H_CARGA → split Hour / Minute
    # ==========================================================
    def split_hm(val):
        if pd.isna(val):
            return (None, None)
        val = str(val)
        m = re.match(r"(\d+):(\d+)", val)
        if not m:
            return (None, None)
        return int(m.group(1)), int(m.group(2))

    df["Hora"], df["Minuto"] = zip(*df[col_hcarga].apply(split_hm))
    steps.append("✔️ H_CARGA separada en Hora y Minuto.")

    # ==========================================================
    # 6️⃣ DUMPX FILTER
    # ==========================================================
    before = len(df)
    df = df[(df[col_dumpx] >= 16000) & (df[col_dumpx] <= 40000)]
    deleted = before - len(df)
    deleted_total += deleted
    steps.append(f"✔️ DumpX filtrado (16000–40000). Filas eliminadas: {deleted}")

    # ==========================================================
    # 7️⃣ DUMPY FILTER
    # ==========================================================
    before = len(df)
    df = df[(df[col_dumpy] >= 110000)]
    deleted = before - len(df)
    deleted_total += deleted
    steps.append(f"✔️ DumpY filtrado (>110000). Filas eliminadas: {deleted}")

    # ==========================================================
    # 8️⃣ DUMPZ / CENZ FILTER (2000–5000)
    # ==========================================================
    before = len(df)
    df = df[(df[col_dumpz] >= 2000) & (df[col_dumpz] <= 5000)]
    deleted = before - len(df)
    deleted_total += deleted
    steps.append(f"✔️ Z filtrado (2000–5000). Filas eliminadas: {deleted}")

    # ==========================================================
    # FINAL OUTPUT DF
    # ==========================================================
    df_out = df[["Dia","Mes","Año","Turno","Cuadrilla","Pala","Hora","Minuto",
                 col_dumpx, col_dumpy, col_dumpz]]
    df_out = df_out.rename(columns={col_dumpx:"X", col_dumpy:"Y", col_dumpz:"Z"})

    # ==========================================================
    # SHOW RESULTS
    # ==========================================================
    st.subheader("🧼 Cleaned Data Preview")
    st.dataframe(df_out.head(), use_container_width=True)

    st.info(f"🧹 Total rows deleted: {deleted_total}")

    # PROCESS STEPS
    st.subheader("⚙️ Processing Steps")
    for s in steps:
        st.markdown(f"- {s}")

    # DOWNLOAD SECTION
    st.subheader("💾 Download Cleaned File")

    excel_buffer = io.BytesIO()
    df_out.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    text_buffer = io.StringIO()
    df_out.to_csv(text_buffer, sep="\t", index=False)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Excel",
            excel_buffer,
            file_name="ES_POSP_Cleaned.xlsx"
        )
    with col2:
        st.download_button(
            "📄 TXT",
            text_buffer.getvalue(),
            file_name="ES_POSP_Cleaned.txt"
        )

else:
    st.info("📂 Please upload a file to begin.")
