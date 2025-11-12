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
    """Read Excel or CSV (detect ; or ,)."""
    name = (uploaded.name or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(uploaded, sep=";", engine="python")
        except Exception:
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

# Detect operator file columns
name_col = find_col_by_hints(ops_df, "operator", "operador", "name", "nombre")
id_col   = find_col_by_hints(ops_df, "id", "codigo", "code")
if not name_col or not id_col:
    st.error("❌ Could not detect Operator mapping columns. The file must include both a name and ID column.")
    st.stop()

ops_df = ops_df[[name_col, id_col]].dropna(subset=[name_col, id_col])
ops_df[id_col] = pd.to_numeric(ops_df[id_col], errors="coerce").astype("Int64")
ops_df = ops_df.dropna(subset=[id_col])

# Build canonical index
ops_index = []
for _, row in ops_df.iterrows():
    full = str(row[name_col]).strip()
    code = int(row[id_col])
    ws = strip_accents_lower_spaces(full)
    ops_index.append({
        "code": code, "full_name": full, "ws": ws, "ns": nospace(ws),
        "tokens": ws.split(), "ntok": len(ws.split())
    })

max_existing_id = ops_df[id_col].max() if not ops_df.empty else 0
next_code = max_existing_id + 1
new_ops_norm_to_code = {}
updated_ops_records = ops_df[[name_col, id_col]].copy()
new_ops_dict = {}  # for displaying new operators

# ==========================================================
# OPERATOR MATCHING
# ==========================================================
def best_operator_code_assign(raw_value: str):
    global next_code
    if pd.isna(raw_value) or str(raw_value).strip() == "":
        return 25, "empty→25"

    s_ws = strip_accents_lower_spaces(raw_value)
    s_ns = nospace(s_ws)
    s_tokens = set(s_ws.split())

    # 1️⃣ Exact nospace match
    for rec in ops_index:
        if s_ns == rec["ns"]:
            return rec["code"], "exact-nospace"

    # 2️⃣ Token coverage + similarity
    best = None
    for rec in ops_index:
        have = sum(1 for t in rec["tokens"] if t in s_tokens)
        need = 2 if rec["ntok"] >= 3 else rec["ntok"]
        if have >= need:
            cov = have / max(rec["ntok"], 1)
            sim = SequenceMatcher(None, s_ns, rec["ns"]).ratio()
            score = 0.7 * cov + 0.3 * sim
            if best is None or score > best["score"]:
                best = {"code": rec["code"], "score": score}
    if best and best["score"] >= 0.80:
        return best["code"], "token-cover"

    # 3️⃣ Fuzzy fallback
    best = None
    for rec in ops_index:
        sim = SequenceMatcher(None, s_ns, rec["ns"]).ratio()
        if best is None or sim > best["sim"]:
            best = {"code": rec["code"], "sim": sim}
    if best and best["sim"] >= 0.90:
        return best["code"], f"fuzzy({best['sim']:.2f})"

    # 4️⃣ Unknown → assign new sequential code
    if s_ns in new_ops_norm_to_code:
        return new_ops_norm_to_code[s_ns], "new-reuse"

    new_code = next_code
    next_code += 1
    new_ops_norm_to_code[s_ns] = new_code
    new_ops_dict[str(raw_value).strip()] = new_code
    updated_ops_records.loc[len(updated_ops_records)] = {name_col: str(raw_value).strip(), id_col: new_code}

    ops_index.append({
        "code": new_code, "full_name": str(raw_value).strip(),
        "ws": s_ws, "ns": s_ns, "tokens": s_ws.split(), "ntok": len(s_ws.split())
    })
    return new_code, "new-assign"

# ==========================================================
# OTHER HELPERS
# ==========================================================
def convert_turno(v):
    if pd.isna(v): return v
    val = str(v).lower().strip()
    if "dia" in val or "día" in val: return 1
    if "noche" in val: return 2
    return v

def extract_expansion_level(text):
    if pd.isna(text): return None, None
    t = str(text).upper()
    xp = re.search(r"F0*(\d+)", t)
    expansion = int(xp.group(1)) if xp else None
    nivel = None
    nv = re.search(r"B0*(\d{3,4})", t)
    if nv:
        nivel = int(nv.group(1))
    else:
        nv = re.search(r"[_\-](2\d{3}|3\d{3}|4\d{3})[_\-]", t)
        if nv: nivel = int(nv.group(1))
    return expansion, nivel

def clean_perforadora(v):
    if pd.isna(v): return v
    val = strip_accents_lower_spaces(v)
    if val.isdigit(): return int(val)
    if "pe_01" in val or "pe01" in val: return 1
    if "pe_02" in val or "pe02" in val: return 2
    if "pd_02" in val or "pd02" in val: return 22
    if "trepsa" in val: return 4
    return v

def cross_fill_pair(df_in, col1, col2):
    def fix(a, b):
        a = pd.to_numeric(a, errors="coerce")
        b = pd.to_numeric(b, errors="coerce")
        if pd.isna(a) or a <= 0: a = b
        if pd.isna(b) or b <= 0: b = a
        return a, b
    df_local = df_in.copy()
    if not (col1 in df_local.columns and col2 in df_local.columns):
        return df_local, 0
    df_local[col1], df_local[col2] = zip(*df_local[[col1, col2]].apply(lambda r: fix(r[col1], r[col2]), axis=1))
    before = len(df_local)
    df_local = df_local.dropna(subset=[col1, col2], how="all")
    removed = before - len(df_local)
    return df_local, removed

# ==========================================================
# CLEANING PIPELINE
# ==========================================================
df = df.loc[:, ~df.columns.duplicated()]
df = df.loc[:, ~df.columns.str.contains(r"\.\d+$", regex=True)]
df.columns = df.columns.astype(str).str.replace(r"[\r\n]+", " ", regex=True).str.strip()

for c in df.columns:
    if "tiempo" in c.lower() and "perfor" in c.lower():
        df.rename(columns={c: "Tiempo Perforación [hrs]"}, inplace=True)
        break

steps_done, deletes_log = [], {}
total_deleted = 0

# 1️⃣ Delete rows with empty Tiempo Perforación [hrs]
if "Tiempo Perforación [hrs]" in df.columns:
    before = len(df)
    df = df.dropna(subset=["Tiempo Perforación [hrs]"])
    removed = before - len(df)
    deletes_log["Empty 'Tiempo Perforación [hrs]'"] = removed
    total_deleted += removed
    steps_done.append("• Deleted rows with empty 'Tiempo Perforación [hrs]'.")
else:
    steps_done.append("• Column 'Tiempo Perforación [hrs]' not found (no deletion).")

# 2️⃣ Turno conversion
if "Turno" in df.columns:
    df["Turno"] = df["Turno"].apply(convert_turno)
    steps_done.append("• Converted Turno (Día→1, Noche→2).")

# 3️⃣ Operator mapping
op_col = find_col_by_hints(df, "operador", "operator")
new_ops_added_count = 0
if op_col:
    codes = []
    added = 0
    for v in df[op_col]:
        code, reason = best_operator_code_assign(v)
        codes.append(code)
        if reason == "new-assign": added += 1
    df[op_col] = codes
    new_ops_added_count = added
    steps_done.append("• Mapped Operators using uploaded mapping file (new ones assigned sequential IDs).")
else:
    steps_done.append("• Operator column not found — skipping operator mapping.")

# 4️⃣ Banco → Expansion & Nivel
if "Banco" in df.columns:
    exps, nivs = zip(*df["Banco"].apply(extract_expansion_level))
    i = df.columns.get_loc("Banco") + 1
    df.insert(i, "Expansion", exps)
    df.insert(i + 1, "Nivel", nivs)
    steps_done.append("• Extracted Expansion and Nivel from Banco (added next to Banco).")

# 5️⃣ Perforadora mapping
if "Perforadora" in df.columns:
    df["Perforadora"] = df["Perforadora"].apply(clean_perforadora)
    steps_done.append("• Standardized Perforadora (PE_01→1, PE_02→2, PD_02→22, Trepsa→4; numeric kept as-is).")

# 6️⃣ Cross-fill Plan/Real pairs
pairs = [("Este Plan", "Este Real"), ("Norte Plan", "Norte Real"),
          ("Elev Plan", "Elev Real"), ("Profundidad Objetivo", "Profundidad Real")]
removed_total_pairs = 0
for a, b in pairs:
    df, removed_here = cross_fill_pair(df, a, b)
    removed_total_pairs += removed_here
if removed_total_pairs:
    deletes_log["Both empty Plan/Real after cross-fill"] = removed_total_pairs
    total_deleted += removed_total_pairs
steps_done.append("• Cross-filled Plan/Real pairs (Este, Norte, Elev, Profundidad).")

# ==========================================================
# PROCESSING SUMMARY
# ==========================================================
with st.expander("⚙️ Processing Summary", expanded=False):

    if new_ops_dict:
        st.markdown("### 👥 New Operators Added")
        for name, code in new_ops_dict.items():
            st.markdown(f"- **{name}** → Code **{code}**")
        st.info("🟢 You can now download the updated Operators file below.")

    st.markdown("### 🛠️ Transformations Applied")
    for s in steps_done:
        st.markdown(f"<div style='background:#eef6ff;padding:8px;border-radius:6px;margin-bottom:6px;color:#0b5394;'>{s}</div>", unsafe_allow_html=True)

    st.markdown("### 🗑️ Rows Deleted (by rule)")
    if deletes_log:
        for rule, cnt in deletes_log.items():
            st.markdown(f"<div style='background:#fdeaea;padding:8px;border-radius:6px;margin-bottom:6px;color:#a61b1b;'>• {rule}: <b>{cnt}</b></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='background:#f0fff0;padding:10px;border-radius:8px;margin-top:6px;color:#0b6b3a;'><b>Total deleted rows: {total_deleted}</b></div>", unsafe_allow_html=True)
    else:
        st.markdown("_No deletions performed._")

# ==========================================================
# SHOW FINAL DATA
# ==========================================================
st.markdown("---")
st.subheader("✅ Data After Cleaning & Transformation")
st.dataframe(df.head(15), use_container_width=True)
st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

# ==========================================================
# DOWNLOAD CLEANED FILES
# ==========================================================
st.markdown("---")
st.subheader("💾 Export Cleaned File")

option = st.radio("Choose download option:", ["⬇️ Download All Columns", "🧩 Download Selected Columns"])
if option == "⬇️ Download All Columns":
    export_df = df
else:
    selected = st.multiselect("Select columns:", options=list(df.columns), default=list(df.columns))
    export_df = df[selected] if selected else df

excel_buf = io.BytesIO()
export_df.to_excel(excel_buf, index=False, engine="openpyxl")
excel_buf.seek(0)

txt_buf = io.StringIO()
export_df.to_csv(txt_buf, index=False, sep="\t")

c1, c2 = st.columns(2)
with c1:
    st.download_button("📘 Download Excel File", excel_buf, file_name="DGM_Autonomia_Cleaned.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
with c2:
    st.download_button("📄 Download TXT File", txt_buf.getvalue(),
                       file_name="DGM_Autonomia_Cleaned.txt", mime="text/plain", use_container_width=True)

# ==========================================================
# UPDATED OPERATORS DOWNLOAD
# ==========================================================
if new_ops_added_count > 0:
    st.markdown("---")
    st.subheader("👥 Updated Operators Mapping")
    updated_ops = updated_ops_records.dropna(subset=[name_col, id_col])
    updated_ops[id_col] = updated_ops[id_col].astype(int)
    updated_ops["_norm"] = updated_ops[name_col].map(lambda x: nospace(strip_accents_lower_spaces(x)))
    updated_ops = updated_ops.sort_values([id_col]).drop_duplicates("_norm", keep="first").drop(columns="_norm")

    ops_buf = io.BytesIO()
    updated_ops.to_excel(ops_buf, index=False, engine="openpyxl")
    ops_buf.seek(0)
    today = datetime.now().strftime("%d%m%y")

    st.download_button(
        "📒 Download Updated Operators File",
        ops_buf,
        file_name=f"DGM_Operators_Updated_{today}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi -")






