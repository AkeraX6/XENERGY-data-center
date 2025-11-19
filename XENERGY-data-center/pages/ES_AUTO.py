import streamlit as st
import pandas as pd
import io
import re
from difflib import SequenceMatcher

# ---------------------------------------------------------
# Helper — Normalize Column Headers
# ---------------------------------------------------------
def normalize_cols(df):
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "", regex=False)
        .str.replace("_", "", regex=False)
    )
    return df


# ---------------------------------------------------------
# Helper — Pozo Transformation
# ---------------------------------------------------------
def transform_pozo(value):
    if pd.isna(value):
        return None

    s = str(value).strip().lower()
    s = s.replace(" ", "")  # remove spaces: "b 125" → "b125"

    # Remove Aux or similar
    if s.startswith("aux"):
        return None

    # If only letters → invalid
    if re.fullmatch(r"[a-z]+", s):
        return None

    m = re.match(r"([a-z])(\d+)", s)
    if m:
        letter = m.group(1)
        num = m.group(2)

        if letter == "b":
            return int("100000" + num)
        elif letter == "c":
            return int("200000" + num)
        elif letter == "d":
            return int(num)
        else:
            return int(num)

    # If only numbers
    if s.isdigit():
        return int(s)

    # If mixed letters in the middle → discard
    return None



# ---------------------------------------------------------
# Helper — Operator Matching System
# ---------------------------------------------------------
def build_operator_index(df_ops):
    df_ops = df_ops.copy()
    df_ops["norm"] = (
        df_ops["nombre"]
        .astype(str)
        .str.lower()
        .str.normalize("NFD")
        .str.replace(r"[\u0300-\u036f]", "", regex=True)
        .str.replace(" ", "", regex=False)
    )

    index = []

    for _, row in df_ops.iterrows():
        norm = row["norm"]
        tokens = set(str(row["nombre"]).lower().split())
        index.append({
            "name": row["nombre"],
            "code": int(row["codigo"]),
            "norm": norm,
            "tokens": tokens,
            "ntok": len(tokens)
        })

    return index


def best_operator_match(name, index, new_ops, next_code):
    if pd.isna(name) or str(name).strip() == "":
        return 75  # default empty

    raw = str(name).strip()
    norm = (
        raw.lower()
        .normalize("NFD")
        .encode("ascii", "ignore")
        .decode()
        .replace(" ", "")
    )

    # 1. Exact no-space match
    for rec in index:
        if norm == rec["norm"]:
            return rec["code"]

    # 2. Token coverage
    tokens = set(raw.lower().split())
    best = None
    for rec in index:
        have = sum(1 for t in rec["tokens"] if t in tokens)
        need = 2 if rec["ntok"] >= 3 else rec["ntok"]
        if have >= need:
            cov = have / max(rec["ntok"], 1)
            sim = SequenceMatcher(None, norm, rec["norm"]).ratio()
            score = 0.7 * cov + 0.3 * sim
            if best is None or score > best["score"]:
                best = {"code": rec["code"], "score": score}

    if best and best["score"] >= 0.80:
        return best["code"]

    # 3. Fuzzy fallback
    best = None
    for rec in index:
        sim = SequenceMatcher(None, norm, rec["norm"]).ratio()
        if best is None or sim > best["sim"]:
            best = {"code": rec["code"], "sim": sim}

    if best and best["sim"] >= 0.90:
        return best["code"]

    # 4. New operator
    code = next_code[0]
    next_code[0] += 1
    new_ops[raw] = code
    index.append({
        "name": raw,
        "code": code,
        "norm": norm,
        "tokens": tokens,
        "ntok": len(tokens)
    })
    return code


# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.markdown("<h2 style='text-align:center;'>Escondida — Autonomía Data Cleaner</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;color:gray;'>Automatic transformation and validation of drilling autonomy data.</p>", unsafe_allow_html=True)
st.markdown("---")

if st.button("⬅️ Back to Menu"):
    st.session_state.page = "dashboard"
    st.rerun()

uploaded_auto = st.file_uploader("📤 Upload Autonomía Excel File", type=["xlsx"])
uploaded_ops = st.file_uploader("📤 Upload Operators Mapping File (Excel)", type=["xlsx"])

if uploaded_auto is None or uploaded_ops is None:
    st.info("📂 Please upload both files.")
    st.stop()

try:
    df = pd.read_excel(uploaded_auto)
    df_ops = pd.read_excel(uploaded_ops)

    df = normalize_cols(df)
    df_ops = normalize_cols(df_ops)

    st.subheader("📄 Original Data (Before Cleaning)")
    st.dataframe(df.head())
    st.info(f"Rows before cleaning: {len(df)}")

    steps = []


    # ---------------------------------------------------------
    # STEP 1 — Perforadora → Last 2 digits
    # ---------------------------------------------------------
    if "perforadora" in df.columns:
        df["perforadora"] = df["perforadora"].astype(str).str[-2:]
        df["perforadora"] = pd.to_numeric(df["perforadora"], errors="coerce")
        steps.append("Perforadora normalized (PE_01 → 1).")

    # ---------------------------------------------------------
    # STEP 2 — Turno & Coordinacion
    # ---------------------------------------------------------
    df["turno(diaonoche)"] = df["turno(diaonoche)"].replace({"dia": 1, "noche": 2, "d": 1, "n": 2})
    df["coordinacion"] = df["coordinacion"].replace({"a": 1, "b": 2, "c": 3, "d": 4})
    steps.append("Turno & Coordinacion converted to numeric codes.")


    # ---------------------------------------------------------
    # STEP 3 — Malla → Banco, Expansion, MallaID
    # ---------------------------------------------------------
    if "malla" in df.columns:
        m = df["malla"].astype(str).str.split("-", expand=True)
        df["banco"] = m[0].str[:4]
        df["expansion"] = m[1].str.extract(r"(\d+)")
        df["mallaid"] = m[2].str[-4:]
        steps.append("Malla split into Banco, Expansion, MallaID.")

    # ---------------------------------------------------------
    # STEP 4 — Pozo transformation (corrected)
    # ---------------------------------------------------------
    if "pozo" in df.columns:
        before = len(df)
        df["pozo"] = df["pozo"].apply(transform_pozo)
        df = df[df["pozo"].notna()]
        df = df[df["pozo"] > 0]
        removed = before - len(df)
        steps.append(f"Pozo cleaned and transformed ({removed} rows removed).")


    # ---------------------------------------------------------
    # STEP 5 — Coordinates cleanup
    # ---------------------------------------------------------
    coordx = ["coordenadasdiseñox", "coordenadarealiniciox"]
    coordy = ["coordenadasdiseñoy", "coordenadarealinicioy"]
    coordz = ["coordenadasdiseñoz", "coordenairealinicioz"]

    for a, b in [(coordx[0], coordx[1]), (coordy[0], coordy[1]), (coordz[0], coordz[1])]:
        if a in df.columns and b in df.columns:
            df[a] = df[a].fillna(df[b])
            df[b] = df[b].fillna(df[a])

    # X must be ≥ 100000
    if coordx[0] in df.columns and coordx[1] in df.columns:
        before = len(df)
        df = df[(df[coordx[0]] >= 100000) & (df[coordx[1]] >= 100000)]
        steps.append(f"Coordinate X filter applied ({before - len(df)} removed).")

    # Z fallback using Banco+15
    if coordz[0] in df.columns and coordz[1] in df.columns:
        mask = df[coordz[0]].isna() & df[coordz[1]].isna()
        df.loc[mask, coordz[0]] = pd.to_numeric(df["banco"], errors="coerce") + 15
        df.loc[mask, coordz[1]] = df.loc[mask, coordz[0]]
        steps.append("Z fallback applied using Banco+15.")

    # ---------------------------------------------------------
    # STEP 6 — Largo de pozo real
    # ---------------------------------------------------------
    if "largodepozoreal" in df.columns:
        before = len(df)
        df = df[df["largodepozoreal"].notna() & (df["largodepozoreal"] != 0)]
        steps.append(f"Largo de pozo real cleaned ({before - len(df)} removed).")

    # ---------------------------------------------------------
    # STEP 7 — Categoria de pozo
    # ---------------------------------------------------------
    df["categoriadepozo"] = df["categoriadepozo"].replace(
        {"produccion": 1, "buffer": 2, "auxiliar": 3}
    )
    steps.append("Categoria de pozo mapped.")

    # ---------------------------------------------------------
    # STEP 8 — Operator mapping with uploaded file
    # ---------------------------------------------------------
    if "operador" in df.columns:

        df_ops = df_ops.rename(columns={"nombre": "nombre", "codigo": "codigo"})
        index = build_operator_index(df_ops)

        next_code = [max(df_ops["codigo"]) + 1]
        new_ops = {}

        df["operadorcode"] = df["operador"].apply(lambda x: best_operator_match(x, index, new_ops, next_code))

        steps.append("Operator fuzzy matching completed.")

        if new_ops:
            st.warning(f"⚠️ New operators detected: {len(new_ops)}")
            st.dataframe(pd.DataFrame(new_ops.items(), columns=["Nombre", "Codigo"]))

            # Download updated operators file
            updated_ops = pd.concat([
                df_ops,
                pd.DataFrame(new_ops.items(), columns=["nombre", "codigo"])
            ], ignore_index=True)

            buf = io.BytesIO()
            updated_ops.to_excel(buf, index=False, engine="openpyxl")
            buf.seek(0)

            st.download_button(
                "📥 Download Updated Operators File",
                buf,
                file_name=f"ES_Operators_{pd.Timestamp.now():%d_%m_%Y}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


    # ---------------------------------------------------------
    # STEP 9 — Modo de perforacion
    # ---------------------------------------------------------
    df["mododeperforacion"] = df["mododeperforacion"].replace(
        {"manual": 1, "autonomous": 2, "teleremote": 3,
         "Manual": 1, "Autonomous": 2, "Teleremote": 3}
    )
    steps.append("Modo de perforación mapped.")

    # ---------------------------------------------------------
    # Display results
    # ---------------------------------------------------------
    st.markdown("---")
    with st.expander("⚙️ Processing Steps", expanded=False):
        for s in steps:
            st.markdown(f"- {s}")

    st.subheader("Cleaned Data Preview")
    st.dataframe(df.head())

    st.success(f"✔️ Final dataset: {len(df)} rows.")

    # ---------------------------------------------------------
    # DOWNLOAD
    # ---------------------------------------------------------
    col1, col2 = st.columns(2)

    excel_buf = io.BytesIO()
    df.to_excel(excel_buf, index=False, engine="openpyxl")
    excel_buf.seek(0)

    with col1:
        st.download_button(
            "📘 Download Excel",
            excel_buf,
            file_name="ES_AUTO_Cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    txt_buf = io.StringIO()
    df.to_csv(txt_buf, index=False, sep="|")

    with col2:
        st.download_button(
            "📄 Download TXT",
            txt_buf.getvalue(),
            file_name="ES_AUTO_Cleaned.txt",
            mime="text/plain"
        )

except Exception as e:
    st.error(f"⚠️ Error: {e}")
