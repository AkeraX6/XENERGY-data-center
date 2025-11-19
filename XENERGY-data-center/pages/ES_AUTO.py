import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from difflib import SequenceMatcher

# ==========================================================
# Helpers
# ==========================================================

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names:
    - strip spaces
    - make lowercase
    - remove spaces and underscores
    """
    df = df.copy()
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "", regex=False)
        .str.replace("_", "", regex=False)
    )
    return df


def transform_pozo(value):
    """
    Pozo rules:
    - Accept both upper/lowercase and with/without spaces:
      B002, b002, B 002, b 002 → 1000002
      Cxxx → 200000xxx
      Dxxx → xxx
    - Remove Aux* and pure letters
    - Only keep positive integers
    """
    if pd.isna(value):
        return None

    s = str(value).strip().lower()
    s = s.replace(" ", "")  # "b 125" → "b125"

    # Remove Aux or similar
    if s.startswith("aux"):
        return None

    # Only letters → invalid
    if re.fullmatch(r"[a-z]+", s):
        return None

    # Letter + digits
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

    # Only digits
    if s.isdigit():
        return int(s)

    # Mixed / weird → drop
    return None


# ---------- Operator Matching Helpers ----------

def build_operator_index(df_ops: pd.DataFrame):
    """
    Build an index for operator fuzzy matching from a mapping file
    with columns: nombre, codigo (already normalized to lowercase, no spaces in header).
    """
    df_ops = df_ops.copy()
    # normalized name for matching: lower, no accents, no spaces
    df_ops["norm"] = (
        df_ops["nombre"]
        .astype(str)
        .str.lower()
        .apply(lambda x: unicodedata.normalize("NFD", x))
        .str.replace(r"[\u0300-\u036f]", "", regex=True)
        .str.replace(" ", "", regex=False)
    )

    index = []
    for _, row in df_ops.iterrows():
        raw_name = str(row["nombre"])
        tokens = set(raw_name.lower().split())
        index.append(
            {
                "name": raw_name,
                "code": int(row["codigo"]),
                "norm": row["norm"],
                "tokens": tokens,
                "ntok": len(tokens),
            }
        )

    return index


def best_operator_match(name, index, new_ops, next_code_box):
    """
    Return numeric operator code using:
    1) exact no-space normalized match
    2) token coverage + similarity
    3) fuzzy similarity
    4) new operator → assign next code
    Empty → 75
    """
    # Empty → default code
    if pd.isna(name) or str(name).strip() == "":
        return 75

    raw = str(name).strip()
    # normalized: lowercase, remove accents, remove spaces
    norm = unicodedata.normalize("NFD", raw.lower())
    norm = re.sub(r"[\u0300-\u036f]", "", norm)
    norm = norm.replace(" ", "")

    # 1️⃣ Exact nospace match
    for rec in index:
        if norm == rec["norm"]:
            return rec["code"]

    # 2️⃣ Token coverage
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

    # 3️⃣ Fuzzy fallback
    best = None
    for rec in index:
        sim = SequenceMatcher(None, norm, rec["norm"]).ratio()
        if best is None or sim > best["sim"]:
            best = {"code": rec["code"], "sim": sim}

    if best and best["sim"] >= 0.90:
        return best["code"]

    # 4️⃣ New operator → create new code
    code = next_code_box[0]
    next_code_box[0] += 1
    new_ops[raw] = code

    # Also expand index so next matches can hit this name
    index.append(
        {
            "name": raw,
            "code": code,
            "norm": norm,
            "tokens": tokens,
            "ntok": len(tokens),
        }
    )
    return code


# ==========================================================
# STREAMLIT UI
# ==========================================================

st.markdown(
    "<h2 style='text-align:center;'>Escondida — Autonomía Data Cleaner</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;color:gray;'>Automatic transformation and validation of drilling autonomy data.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_esauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# Upload files
uploaded_auto = st.file_uploader("📤 Upload Autonomía Excel File", type=["xlsx"])
uploaded_ops = st.file_uploader(
    "📤 Upload Operators Mapping File (Excel)", type=["xlsx"]
)

if uploaded_auto is None or uploaded_ops is None:
    st.info("📂 Please upload BOTH files (Autonomía + Operators).")
else:
    try:
        # ---------- Read & normalize ----------
        df_raw = pd.read_excel(uploaded_auto)
        df_ops_raw = pd.read_excel(uploaded_ops)

        df = normalize_cols(df_raw)
        df_ops = normalize_cols(df_ops_raw)

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df_raw.head(), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {len(df)}")

        steps = []

        # ==========================================================
        # STEP 1 – Perforadora
        # ==========================================================
        if "perforadora" in df.columns:
            df["perforadora"] = df["perforadora"].astype(str).str[-2:]
            df["perforadora"] = pd.to_numeric(df["perforadora"], errors="coerce")
            steps.append("✅ Perforadora normalized (PE_01 → 1, PE_10 → 10).")

        # ==========================================================
        # STEP 2 – Turno & Coordinacion
        # ==========================================================
        if "turno(diaonoche)" in df.columns:
            df["turno(diaonoche)"] = df["turno(diaonoche)"].astype(str).str.lower()
            df["turno(diaonoche)"] = df["turno(diaonoche)"].replace(
                {"dia": 1, "noche": 2, "d": 1, "n": 2}
            )
            steps.append("✅ Turno converted to numeric (Dia=1, Noche=2).")

        if "coordinacion" in df.columns:
            df["coordinacion"] = df["coordinacion"].astype(str).str.lower()
            df["coordinacion"] = df["coordinacion"].replace(
                {"a": 1, "b": 2, "c": 3, "d": 4}
            )
            steps.append("✅ Coordinacion converted to numeric (A=1, B=2, C=3, D=4).")

        # ==========================================================
        # STEP 3 – Malla → Banco / Expansion / MallaID
        #   Malla format: 3040-N17B-5018
        #   Banco/Level = 3040, Expansion = 17, Grid = 5018
        # ==========================================================
        if "malla" in df.columns:
            m = df["malla"].astype(str).str.split("-", expand=True)

            # Banco/Level = 4 digits at the beginning of part 0
            df["banco"] = m[0].str.extract(r"(\d{4})", expand=False)

            # Expansion: from part 1 → patterns like N17B, S04, PL1S, etc.
            # extract digits after a letter sequence
            df["expansion"] = m[1].str.extract(r"[a-zA-Z]+(\d{1,2})", expand=False)

            # MallaID/Grid: last 4 digits of part 2
            df["mallaid"] = m[2].str.extract(r"(\d{4})", expand=False)

            steps.append(
                "✅ Malla split into Banco (Level), Expansion, and MallaID (Grid) using 3040-N17B-5018 format."
            )
        else:
            steps.append("⚠️ Column 'Malla' not found (after normalization).")

        # ==========================================================
        # STEP 4 – Pozo transformation
        # ==========================================================
        if "pozo" in df.columns:
            before_pozo = len(df)
            df["pozo"] = df["pozo"].apply(transform_pozo)
            df = df[df["pozo"].notna()]
            df = df[df["pozo"] > 0]
            removed_pozo = before_pozo - len(df)
            steps.append(
                f"✅ Pozo cleaned & transformed (removed {removed_pozo} invalid / Aux / non-positive rows)."
            )
        else:
            steps.append("⚠️ Column 'Pozo' not found (after normalization).")

        # ==========================================================
        # STEP 5 – Coordinates (X, Y, Z) cross-fill & filters
        #   - cross-fill design/real pairs
        #   - remove negative coords
        #   - X must be ≥ 100000
        #   - Z fallback: if both empty → Banco + 15
        # ==========================================================
        coordx = ["coordenadasdiseñox", "coordenadarealiniciox"]
        coordy = ["coordenadasdiseñoy", "coordenadarealinicioy"]
        coordz = ["coordenadasdiseñoz", "coordenairealinicioz"]

        # Cross-fill design/real for X, Y, Z
        for a, b in [(coordx[0], coordx[1]), (coordy[0], coordy[1]), (coordz[0], coordz[1])]:
            if a in df.columns and b in df.columns:
                df[a] = df[a].fillna(df[b])
                df[b] = df[b].fillna(df[a])

        # Z fallback with Banco+15 (only if Banco exists)
        if all(c in df.columns for c in coordz) and "banco" in df.columns:
            mask_z_empty = df[coordz[0]].isna() & df[coordz[1]].isna()
            if mask_z_empty.any():
                df.loc[mask_z_empty, coordz[0]] = (
                    pd.to_numeric(df.loc[mask_z_empty, "banco"], errors="coerce") + 15
                )
                df.loc[mask_z_empty, coordz[1]] = df.loc[mask_z_empty, coordz[0]]
            steps.append("✅ Z coordinates fallback applied where empty (Banco + 15).")

        # Remove rows with any negative coordinates (X/Y/Z, design or real)
        coord_cols_present = [c for c in coordx + coordy + coordz if c in df.columns]
        if coord_cols_present:
            before_coord = len(df)
            # Ensure numeric
            for c in coord_cols_present:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=coord_cols_present, how="any")
            df = df[(df[coord_cols_present] >= 0).all(axis=1)]
            removed_neg = before_coord - len(df)
            steps.append(
                f"✅ Removed {removed_neg} rows with negative or invalid coordinates (X/Y/Z)."
            )

        # X must be ≥ 100000
        if coordx[0] in df.columns and coordx[1] in df.columns:
            before_x = len(df)
            df = df[(df[coordx[0]] >= 100000) & (df[coordx[1]] >= 100000)]
            removed_x = before_x - len(df)
            steps.append(
                f"✅ Removed {removed_x} rows where X coordinates were < 100000."
            )

        # ==========================================================
        # STEP 6 – Dureza / Velocidad / RPM / Pulldown rules
        # ==========================================================
        # Dureza: empty → 0, otherwise keep
        if "dureza" in df.columns:
            df["dureza"] = pd.to_numeric(df["dureza"], errors="coerce").fillna(0)
            steps.append("✅ Dureza: empty values filled with 0.")

        # RPM de perforacion: empty → 0
        if "rpmdeperforacion" in df.columns:
            df["rpmdeperforacion"] = pd.to_numeric(
                df["rpmdeperforacion"], errors="coerce"
            ).fillna(0)
            steps.append("✅ RPM de perforacion: empty values filled with 0.")

        # Velocidad de penetracion (m/minutos): empty OR 0 → delete row
        vel_col = "velocidaddepenetracion(m/minutos)"
        if vel_col in df.columns:
            df[vel_col] = pd.to_numeric(df[vel_col], errors="coerce")
            before_vel = len(df)
            df = df[df[vel_col].notna() & (df[vel_col] != 0)]
            removed_vel = before_vel - len(df)
            steps.append(
                f"✅ Removed {removed_vel} rows with empty or zero 'Velocidad de penetracion (m/minutos)'."
            )

        # Pulldown KN: empty OR 0 → delete row
        if "pulldownkn" in df.columns:
            df["pulldownkn"] = pd.to_numeric(df["pulldownkn"], errors="coerce")
            before_pd = len(df)
            df = df[df["pulldownkn"].notna() & (df["pulldownkn"] != 0)]
            removed_pd = before_pd - len(df)
            steps.append(
                f"✅ Removed {removed_pd} rows with empty or zero 'Pulldown KN'."
            )

        # ==========================================================
        # STEP 7 – Largo de pozo real
        # ==========================================================
        if "largodepozoreal" in df.columns:
            df["largodepozoreal"] = pd.to_numeric(df["largodepozoreal"], errors="coerce")
            before_len = len(df)
            df = df[df["largodepozoreal"].notna() & (df["largodepozoreal"] != 0)]
            removed_len = before_len - len(df)
            steps.append(
                f"✅ Removed {removed_len} rows with empty or zero 'Largo de pozo real'."
            )

        # ==========================================================
        # STEP 8 – Categoria de pozo
        # ==========================================================
        if "categoriadepozo" in df.columns:
            df["categoriadepozo"] = df["categoriadepozo"].astype(str).str.lower()
            df["categoriadepozo"] = df["categoriadepozo"].replace(
                {"produccion": 1, "buffer": 2, "auxiliar": 3}
            )
            steps.append("✅ Categoria de pozo mapped to numeric (Produccion=1, Buffer=2, Auxiliar=3).")

        # ==========================================================
        # STEP 9 – Estatus de pozo → keep only Drilled
        # ==========================================================
        if "estatusdepozo" in df.columns:
            before_status = len(df)
            df["estatusdepozo"] = df["estatusdepozo"].astype(str).str.lower()
            df = df[df["estatusdepozo"] == "drilled"]
            removed_status = before_status - len(df)
            steps.append(
                f"✅ Estatus de pozo filtered: kept only 'Drilled' ({removed_status} rows removed)."
            )

        # ==========================================================
        # STEP 10 – Operator mapping with uploaded file
        # ==========================================================
        if "operador" in df.columns:
            # We expect operator mapping file to have columns "nombre" & "codigo"
            if "nombre" in df_ops.columns and "codigo" in df_ops.columns:
                ops_index = build_operator_index(df_ops)
                next_code_box = [int(pd.to_numeric(df_ops["codigo"], errors="coerce").max() or 0) + 1]
                new_ops = {}

                df["operadorcode"] = df["operador"].apply(
                    lambda x: best_operator_match(x, ops_index, new_ops, next_code_box)
                )
                steps.append("✅ Operator fuzzy matching applied using uploaded mapping file.")

                if new_ops:
                    st.warning(f"⚠️ New operators detected: {len(new_ops)}")
                    new_ops_df = pd.DataFrame(
                        [(k, v) for k, v in new_ops.items()], columns=["Nombre", "Codigo"]
                    )
                    st.dataframe(new_ops_df, use_container_width=True)

                    # Download updated operators file
                    updated_ops = pd.concat(
                        [
                            df_ops[["nombre", "codigo"]],
                            new_ops_df.rename(columns={"Nombre": "nombre", "Codigo": "codigo"}),
                        ],
                        ignore_index=True,
                    )

                    buf_ops = io.BytesIO()
                    updated_ops.to_excel(buf_ops, index=False, engine="openpyxl")
                    buf_ops.seek(0)

                    st.download_button(
                        "📥 Download Updated Operators Mapping",
                        buf_ops,
                        file_name=f"ES_Operators_{pd.Timestamp.now():%d_%m_%Y}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            else:
                steps.append("⚠️ Uploaded Operators file must contain 'nombre' and 'codigo' columns (after normalization).")

        # ==========================================================
        # STEP 11 – Modo de perforacion
        # ==========================================================
        if "mododeperforacion" in df.columns:
            df["mododeperforacion"] = df["mododeperforacion"].astype(str)
            df["mododeperforacion"] = df["mododeperforacion"].replace(
                {
                    "manual": 1,
                    "Manual": 1,
                    "autonomous": 2,
                    "Autonomous": 2,
                    "teleremote": 3,
                    "Teleremote": 3,
                }
            )
            steps.append("✅ Modo de perforacion mapped to numeric (Manual=1, Autonomous=2, Teleremote=3).")

        # ==========================================================
        # RESULTS
        # ==========================================================
        st.markdown("---")
        with st.expander("⚙️ Processing Steps", expanded=False):
            for s in steps:
                st.markdown(f"- {s}")

        st.subheader("✅ Cleaned Data Preview")
        st.dataframe(df.head(20), use_container_width=True)
        st.success(f"✅ Final dataset: {len(df)} rows × {len(df.columns)} columns.")

        # ==========================================================
        # DOWNLOAD SECTION
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Cleaned File")

        option = st.radio(
            "Choose download option:",
            ["⬇️ Download All Columns", "🧩 Download Selected Columns"],
        )

        if option == "⬇️ Download All Columns":
            export_df = df
        else:
            selected_columns = st.multiselect(
                "Select columns (drag to reorder):",
                options=list(df.columns),
                default=list(df.columns),
            )
            export_df = df[selected_columns] if selected_columns else df

        # Excel
        excel_buffer = io.BytesIO()
        export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        # TXT (pipe-separated)
        txt_buffer = io.StringIO()
        export_df.to_csv(txt_buffer, index=False, sep="|")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel File",
                excel_buffer,
                file_name="Escondida_Autonomia_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "📄 Download TXT File",
                txt_buffer.getvalue(),
                file_name="Escondida_Autonomia_Cleaned.txt",
                mime="text/plain",
                use_container_width=True,
            )

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi -")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")
