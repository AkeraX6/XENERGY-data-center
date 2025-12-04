import streamlit as st
import pandas as pd
import io
import unicodedata
import re
from difflib import SequenceMatcher
from datetime import datetime

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>DGM — Autonomía Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Upload your main DGM data and an Operators mapping file. "
    "The app maps operators (fuzzy), auto-assigns IDs to new names, cleans fields, and exports.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# ==========================================================
# FILE UPLOADS
# ==========================================================
st.subheader("📤 Upload Files")
c1, c2 = st.columns(2)
with c1:
    data_file = st.file_uploader("Main DGM Data (Excel/CSV)", type=["xlsx", "xls", "csv"], key="data_file")
with c2:
    ops_file = st.file_uploader("Operators Mapping (Excel/CSV)", type=["xlsx", "xls", "csv"], key="ops_file")

if not data_file or not ops_file:
    st.info("Please upload **both** files to begin.")
    st.stop()

# ==========================================================
# HELPERS
# ==========================================================
def read_any_table(uploaded):
    name = (uploaded.name or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded, sep=";", engine="python")
        except:
            uploaded.seek(0)
            return pd.read_csv(uploaded, engine="python")
    return pd.read_excel(uploaded)

def strip_accents_lower_spaces(s: str) -> str:
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def nospace(s: str) -> str:
    return s.replace(" ", "")

def find_col_by_hints(df, *hints):
    for c in df.columns:
        n = strip_accents_lower_spaces(c)
        for h in hints:
            if strip_accents_lower_spaces(h) in n:
                return c
    return None

# ==========================================================
# LOAD FILES
# ==========================================================
df = read_any_table(data_file)
ops_df = read_any_table(ops_file)

st.subheader("📄 Original Data (Before Cleaning)")
st.dataframe(df.head(10), use_container_width=True)
st.info(f"📏 Total rows before cleaning: {len(df)}")

# Operator file structure
name_col = find_col_by_hints(ops_df, "operator", "operador", "name", "nombre")
id_col   = find_col_by_hints(ops_df, "id", "codigo", "code")

ops_df[id_col] = pd.to_numeric(ops_df[id_col], errors="coerce").astype("Int64")
ops_df = ops_df.dropna(subset=[id_col])

# Index operators
ops_index = []
for _, r in ops_df.iterrows():
    nm = str(r[name_col]).strip()
    cd = int(r[id_col])
    ws = strip_accents_lower_spaces(nm)
    ops_index.append({"code": cd, "nm": nm, "ws": ws, "ns": nospace(ws), "tok": ws.split(), "nt": len(ws.split())})

next_code = ops_df[id_col].max() + 1
new_ops_dict = {}
updated_ops_records = ops_df[[name_col, id_col]].copy()

# ==========================================================
# OPERATOR MATCHING
# ==========================================================
def assign_op(v):
    global next_code
    if pd.isna(v) or str(v).strip() == "":
        return 25

    ws = strip_accents_lower_spaces(v)
    ns = nospace(ws)
    tok = set(ws.split())

    # Exact nospace match
    for rec in ops_index:
        if rec["ns"] == ns:
            return rec["code"]

    # Token match / fuzzy
    best = None
    for rec in ops_index:
        have = sum(1 for t in rec["tok"] if t in tok)
        need = 2 if rec["nt"] >= 3 else rec["nt"]
        if have >= need:
            score = SequenceMatcher(None, ns, rec["ns"]).ratio()
            if not best or score > best["score"]:
                best = {"code": rec["code"], "score": score}

    if best and best["score"] >= 0.80:
        return best["code"]

    # New operator
    code = next_code
    next_code += 1
    updated_ops_records.loc[len(updated_ops_records)] = {name_col: str(v).strip(), id_col: code}
    new_ops_dict[str(v).strip()] = code
    return code

# ==========================================================
# CLEANING PIPELINE
# ==========================================================
df = df.loc[:, ~df.columns.duplicated()]
df.columns = df.columns.astype(str).str.replace(r"[\r\n]+", " ", regex=True).str.strip()

steps_done = []
deleted_counts = {}
total_deleted = 0

# Clean Tiempo Perforación
tp_col = find_col_by_hints(df, "tiempo", "hrs", "perfor")
if tp_col:
    before = len(df)
    df.dropna(subset=[tp_col], inplace=True)
    removed = before - len(df)
    total_deleted += removed
    deleted_counts["Empty Tiempo Perforación"] = removed
    df.rename(columns={tp_col: "Tiempo Perforación [hrs]"}, inplace=True)
steps_done.append("• Cleaned Tiempo Perforación column")

# Turno mapping
turno_col = find_col_by_hints(df, "turno")
if turno_col:
    df[turno_col] = df[turno_col].apply(lambda x: 1 if pd.isna(x) else (2 if ("noc" in str(x).lower()) else 1))
steps_done.append("• Filled empty Turno with 1")

# Operator mapping
op_col = find_col_by_hints(df, "operador", "operator")
if op_col:
    df[op_col] = df[op_col].apply(assign_op)
steps_done.append("• Operator mapping complete")

# Banco Expansion/Nivel
if "Banco" in df.columns:
    df["Expansion"] = df["Banco"].astype(str).str.extract(r"F0*(\d+)")
    df["Nivel"] = df["Banco"].astype(str).str.extract(r"(\d{3,4})")
steps_done.append("• Extracted Expansion & Nivel")

# Perforadora
pcol = find_col_by_hints(df, "perforadora")
if pcol:
    df[pcol] = df[pcol].astype(str).str.replace(r"[^0-9]", "", regex=True).replace("", None)
steps_done.append("• Cleaned Perforadora")

# Fixed Special Cross-fill Rules
pairs = [
    ("Este Plan", "Este Real"),
    ("Norte Plan", "Norte Real"),
    ("Elev Plan", "Elev Real"),
    ("Profundidad Objetivo", "Profundidad Real")
]

for a, b in pairs:
    if a in df.columns and b in df.columns:
        df[a] = pd.to_numeric(df[a], errors="coerce")
        df[b] = pd.to_numeric(df[b], errors="coerce")

        df[a] = df[a].fillna(df[b])
        df[b] = df[b].fillna(df[a])

# Elev: fill from Nivel if still empty
if "Elev Plan" in df.columns and "Nivel" in df.columns:
    df["Elev Plan"] = df["Elev Plan"].fillna(df["Nivel"])
if "Elev Real" in df.columns and "Nivel" in df.columns:
    df["Elev Real"] = df["Elev Real"].fillna(df["Nivel"])

# Profundidad: delete when both empty
if "Profundidad Objetivo" in df.columns and "Profundidad Real" in df.columns:
    before = len(df)
    df = df.dropna(subset=["Profundidad Objetivo", "Profundidad Real"], how="all")
    removed = before - len(df)
    total_deleted += removed
    deleted_counts["Rows deleted missing Profundidad"] = removed

steps_done.append("• Improved cross-fill Elev & Profundidad rules")

# ==========================================================
# SUMMARY DISPLAY
# ==========================================================
with st.expander("⚙️ Processing Summary", expanded=False):
    if new_ops_dict:
        st.markdown("### 👥 New Operators Added")
        for n, c in new_ops_dict.items():
            st.markdown(f"- **{n}** → Code **{c}**")

    st.markdown("### 🔧 Transformations")
    for s in steps_done:
        st.markdown(f"- {s}")

    if deleted_counts:
        st.markdown("### 🗑️ Rows Deleted")
        for rule, cnt in deleted_counts.items():
            st.markdown(f"- {rule}: **{cnt}**")
        st.markdown(f"**Total deleted: {total_deleted}**")

# ==========================================================
# SHOW DATA + DOWNLOAD
# ==========================================================
st.subheader("📊 Cleaned Data Preview")
st.dataframe(df.head(20), use_container_width=True)

export_df = df.copy()

excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

txt_buffer = io.StringIO()
export_df.to_csv(txt_buffer, index=False, sep="\t")

col1, col2 = st.columns(2)
with col1:
    st.download_button("📘 Download Excel File", excel_buffer,
        file_name="DGM_Autonomia_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with col2:
    st.download_button("📄 Download TXT File", txt_buffer.getvalue(),
        file_name="DGM_Autonomia_Cleaned.txt",
        mime="text/plain")

if new_ops_dict:
    st.subheader("📒 Updated Operators File")
    ops_buf = io.BytesIO()
    updated_ops_records.to_excel(ops_buf, index=False, engine="openpyxl")
    ops_buf.seek(0)
    st.download_button("Download Updated Operators",
        ops_buf,
        file_name=f"DGM_Operators_Updated_{datetime.now().strftime('%d%m%y')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("Built by Maxam - Omar El Kendi -")





