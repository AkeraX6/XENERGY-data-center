import streamlit as st
import pandas as pd
import re
import io
import numpy as np

# ==================================================
# PAGE HEADER
# ==================================================
st.markdown(
    "<h2 style='text-align:center;'>Mantos Verde — Fragmentation Data Processor</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automated cleaning and transformation of MV fragmentation data.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# ==================================================
# HELPER FUNCTIONS
# ==================================================

def normalize_text(s):
    """Lowercase, strip spaces, remove accents for comparison."""
    if pd.isna(s):
        return ""
    s = str(s).strip().lower()
    s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    # collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    return s


# ----- PALA/CARGADOR mapping -----
def clean_pala(val):
    if pd.isna(val) or str(val).strip() == "":
        return 0
    val_raw = str(val).strip()
    val_upper = val_raw.upper()

    # "Sin equipo" → 0
    if "SIN EQUIPO" in val_upper or "SIN" in val_upper:
        return 0

    # Specific 2CF patterns: 2CF9405 → 9405, 2CF9412 → 9412
    m = re.match(r"2CF(\d+)", val_upper)
    if m:
        return int(m.group(1))

    # CF-type patterns: CFCA014 → 100014, CFCA05 → 10005, CFC… → 100 + number
    if "CF" in val_upper:
        nums = re.findall(r"\d+", val_upper)
        if nums:
            number_part = nums[-1]           # take last number group
            return int("100" + number_part)   # prepend 100
        return 0

    # PALA patterns: PALA001 → 1, PALA006 → 6
    m = re.match(r"PALA\D*(\d+)", val_upper)
    if m:
        return int(m.group(1))

    # Fallback: try to extract any number
    nums = re.findall(r"\d+", val_upper)
    if nums:
        return int(nums[-1])

    return 0


# ----- RAJOS / Pit mapping -----
RAJOS_MAP = {
    "celso": 1,
    "franco": 2,
    "kuroki": 3,
    "llano": 4,
    "mv07": 5,
    "mv1": 6,
    "mvn7": 7,
    "paredeste": 8,
    "punto63": 9,
    "reb": 10,
    "ruso": 11,
    "stock03b": 12,
    "stock1030": 13,
    "stockaltaameco": 14,
    "stockmixtos4": 15,
    "stocksulfuro": 16,
    "stocksulfuro04": 17,
}


def clean_rajos(val):
    if pd.isna(val) or str(val).strip() == "":
        return 0
    # normalize: lower, strip, remove spaces and special chars for lookup
    key = normalize_text(val).replace(" ", "").replace(".", "").replace("-", "").replace("_", "")
    return RAJOS_MAP.get(key, 0)


# ----- BANCO -----
def clean_banco(val):
    if pd.isna(val) or str(val).strip() == "":
        return 0
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return 0


# ----- MALLA -----
def clean_malla(val):
    if pd.isna(val) or str(val).strip() == "":
        return 0
    val_str = str(val).strip().upper()
    # pattern like 605B → 100605
    m = re.match(r"^(\d+)[Bb]$", val_str)
    if m:
        return int(m.group(1)) + 100000
    # plain number
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        # try extracting digits
        nums = re.findall(r"\d+", val_str)
        if nums:
            return int(nums[0])
        return 0


def read_any_file(uploaded_file):
    """Read CSV, TXT, or Excel file."""
    try:
        name = uploaded_file.name.lower()
        if name.endswith(".csv") or name.endswith(".txt"):
            content = uploaded_file.read()
            if b";" in content[:2000]:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, delimiter=";")
            elif b"\t" in content[:2000]:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, delimiter="\t")
            else:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file)
        else:
            return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file {uploaded_file.name}: {e}")
        return None


# ==================================================
# FILE UPLOAD
# ==================================================
uploaded_files = st.file_uploader(
    "📤 Upload your Fragmentation files (Excel, CSV or TXT)",
    type=["xlsx", "xls", "csv", "txt"],
    accept_multiple_files=True,
)

if uploaded_files:
    all_dfs = []
    for uf in uploaded_files:
        temp = read_any_file(uf)
        if temp is not None:
            all_dfs.append(temp)

    if not all_dfs:
        st.error("⚠️ Could not read any of the uploaded files.")
        st.stop()

    df = pd.concat(all_dfs, ignore_index=True)
    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]

    st.subheader("📄 Original Data Preview")
    st.dataframe(df.head(15), use_container_width=True)
    st.info(f"📏 Loaded {len(df)} rows × {len(df.columns)} columns from {len(uploaded_files)} file(s).")

    # ==================================================
    # DETECT COLUMNS (flexible matching)
    # ==================================================
    def find_col(df, *keywords):
        for c in df.columns:
            cn = normalize_text(c)
            for kw in keywords:
                if normalize_text(kw) in cn:
                    return c
        return None

    col_fecha = find_col(df, "fecha")
    col_pala = find_col(df, "pala", "cargador")
    col_rajos = find_col(df, "rajos", "rajo", "pit")
    col_banco = find_col(df, "banco")
    col_malla = find_col(df, "malla")
    col_p50 = find_col(df, "p50")
    col_p80 = find_col(df, "p80")
    col_p90 = find_col(df, "p90")

    missing = []
    for name, col in [("Fecha", col_fecha), ("PALA/CARGADOR", col_pala),
                       ("RAJOS", col_rajos), ("P50", col_p50),
                       ("P80", col_p80), ("P90", col_p90)]:
        if col is None:
            missing.append(name)
    if missing:
        st.error(f"❌ Required columns not found: {', '.join(missing)}")
        st.write("Available columns:", df.columns.tolist())
        st.stop()

    # ==================================================
    # PROCESSING
    # ==================================================
    with st.expander("⚙️ Processing Steps", expanded=True):
        steps = []

        # 1. Parse date → Day, Month, Year
        fechas = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
        result = pd.DataFrame()
        result["Day"] = fechas.dt.day.astype("Int64")
        result["Month"] = fechas.dt.month.astype("Int64")
        result["Year"] = fechas.dt.year.astype("Int64")
        steps.append("✅ Split Fecha into Day, Month, Year")

        # 2. Clean PALA/CARGADOR → Pala
        result["Pala"] = df[col_pala].apply(clean_pala)
        steps.append("✅ Transformed PALA/CARGADOR → Pala (numeric codes)")

        # 3. Clean RAJOS → Pit
        result["Pit"] = df[col_rajos].apply(clean_rajos)
        steps.append("✅ Mapped RAJOS → Pit (1–17 codes)")

        # 4. Clean BANCO
        if col_banco is not None:
            result["Banco"] = df[col_banco].apply(clean_banco)
        else:
            result["Banco"] = 0
        steps.append("✅ Cleaned Banco (empty → 0)")

        # 5. Clean MALLA
        if col_malla is not None:
            result["Malla"] = df[col_malla].apply(clean_malla)
        else:
            result["Malla"] = 0
        steps.append("✅ Cleaned Malla (empty → 0, B suffix → +100000)")

        # 6. P50, P80, P90
        result["P50"] = pd.to_numeric(df[col_p50], errors="coerce")
        result["P80"] = pd.to_numeric(df[col_p80], errors="coerce")
        result["P90"] = pd.to_numeric(df[col_p90], errors="coerce")
        steps.append("✅ Extracted P50, P80, P90 values")

        # Drop rows where date could not be parsed
        before = len(result)
        result = result.dropna(subset=["Day", "Month", "Year"])
        if before - len(result) > 0:
            steps.append(f"⚠️ Removed {before - len(result)} rows with invalid dates")

        # Final column order
        result = result[["Day", "Month", "Year", "Pala", "Pit", "Banco", "Malla", "P50", "P80", "P90"]]

        steps.append(f"✅ Final dataset: {len(result)} rows × {len(result.columns)} columns")

        for s in steps:
            st.markdown(
                f"<div style='background-color:#e8f8f0;padding:10px;border-radius:8px;margin-bottom:8px;'>"
                f"<span style='color:#137333;font-weight:500;'>{s}</span></div>",
                unsafe_allow_html=True,
            )

    # ==================================================
    # SHOW RESULTS
    # ==================================================
    st.markdown("---")
    st.subheader("✅ Transformed Data")
    st.dataframe(result.head(20), use_container_width=True)
    st.success(f"Final dataset: {len(result)} rows × {len(result.columns)} columns.")

    # ==================================================
    # DOWNLOAD — Excel (with headers) + TXT (no headers, just numbers)
    # ==================================================
    st.markdown("---")
    st.subheader("💾 Export Processed Data")

    # Excel with headers
    excel_buf = io.BytesIO()
    result.to_excel(excel_buf, index=False, engine="openpyxl")
    excel_buf.seek(0)

    # TXT without headers, tab-separated, numbers only
    txt_buf = io.StringIO()
    result.to_csv(txt_buf, index=False, header=False, sep="\t")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📘 Download Excel File",
            data=excel_buf,
            file_name="MV_FRAG_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "📗 Download TXT File (no headers)",
            data=txt_buf.getvalue(),
            file_name="MV_FRAG_Cleaned.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam — Omar El Kendi")

else:
    st.info("📄 Please upload one or more files to begin.")
