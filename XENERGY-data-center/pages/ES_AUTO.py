import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime

# ==========================================================
# HELPERS
# ==========================================================

def normalize_text(s: str) -> str:
    s = str(s).replace("\xa0", " ")
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_header(col: str) -> str:
    return normalize_text(col)

# Canonical column list (51 columns from input)
EXPECTED_COLUMNS = [
    "Id", "Perforadora", "ShiftIndex", "tiempo incio de turno", "Tiempo final de turno",
    "turno (dia o noche)", "Coordinacion", "Malla", "Pozo", "tiempo de inicio de ciclo",
    "Tiempo final de ciclo", "Tiempo total de ciclo (en segundos)", "tiempo de inicio de pozo",
    "Tiempo final de pozo", "Tiempo total de pozo (segundos)", "Coordenadas diseño X",
    "Coordenadas diseño Y", "Coordenadas diseño Z", "Coordenada real inicioX",
    "Coordenada real inicio Y", "Coordena real inicio Z", "Coordenada real final X",
    "Coordenada real final Y", "Coordenada real final Z", "GPS calidad", "Dureza",
    "Velocidad de penetracion (m/minutos)", "RPM de perforacion", "Pulldown KN",
    "Largo de pozo planeado", "Largo de pozo real", "Desviacion XY", "Desviacion Z",
    "Desviacion en largo", "Estatus de pozo", "Categoria de pozo", "Operador", "Broca",
    "Tiempo en modo autonomo (segundos)", "Tiempo en modo manual (segundos)",
    "Tiempo en modo teleremoto (segundos)", "Tiempo en modo Switched (segundos)",
    "Tiempo en parada de emergencia (segundos)", "Modo de perforacion",
    "Tiempo en modo configuracion (segundos)", "Tiempo en modo parqueo (segundos)",
    "Tiempo en propulcion (segundos)", "Tiempo en perforacion (segundos)",
    "Tiempo en demora (segundos)", "Velocidad efectiva ciclo (mt/hrs)",
    "Velocidad de penetracion (mts/hrs)"
]

expected_norm_map = {normalize_header(c): c for c in EXPECTED_COLUMNS}

# Output column order (25 columns)
OUTPUT_COLUMNS = [
    "Perforadora", "ShiftIndex", "turno (dia o noche)", "Coordinacion",
    "Banco", "Expansion", "Pattern",
    "Pozo", "Coordenadas diseño X", "Coordenadas diseño Y", "Coordenadas diseño Z",
    "Coordenada real inicioX", "Coordenada real inicio Y", "Coordena real inicio Z",
    "Dureza", "Velocidad de penetracion (m/minutos)", "RPM de perforacion", "Pulldown KN",
    "Largo de pozo real", "Categoria de pozo", "Operador", "Broca",
    "Modo de perforacion", "Velocidad efectiva ciclo (mt/hrs)", "Velocidad de penetracion (mts/hrs)"
]

# Expansion special mapping
EXPANSION_MAP = {
    "n17b": 170,
    "pl1s": 101,
}

# ==========================================================
# TRANSFORMATION FUNCTIONS
# ==========================================================

def transform_pozo_value(val):
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    s = s.replace(" ", "")

    # Anything containing "aux" -> delete
    if "aux" in s:
        return None

    # AX prefix -> delete
    if s.startswith("ax"):
        return None

    # Only letters -> invalid
    if re.fullmatch(r"[a-z]+", s):
        return None

    # letter + digits (possibly followed by junk like d146-2 -> 146)
    m = re.match(r"([a-z])\s*(\d+)", s)
    if m:
        letter = m.group(1)
        num_str = m.group(2).lstrip("0") or "0"
        num = int(num_str)
        if letter == "b":
            return 100000 + num
        elif letter == "c":
            return 200000 + num
        elif letter == "d":
            return num if num > 0 else None
        else:
            return None

    # Only digits
    digits_only = re.match(r"(\d+)", s)
    if digits_only:
        num = int(digits_only.group(1).lstrip("0") or "0")
        return num if num > 0 else None

    return None


def parse_expansion(mid_segment):
    mid_lower = mid_segment.strip().lower()
    if mid_lower in EXPANSION_MAP:
        return EXPANSION_MAP[mid_lower]
    digits = re.findall(r"\d+", mid_segment)
    if digits:
        return int(digits[0])
    return None


def parse_malla(text):
    if pd.isna(text):
        return (None, None, None)
    txt = str(text).strip()
    # Split by - or _ (supports "3040-N17B-5018" and "2870_N11_5004")
    parts = re.split(r"[-_]", txt)

    # Banco = first 4-digit number
    m_level = re.search(r"(\d{4})", txt)
    banco = int(m_level.group(1)) if m_level else None

    # Expansion from middle segment
    expansion = None
    if len(parts) >= 2:
        expansion = parse_expansion(parts[1])

    # Pattern = last 4-digit number (third segment)
    pattern = None
    if len(parts) >= 3:
        m_pat = re.search(r"(\d{4})", parts[-1])
        if m_pat:
            pattern = int(m_pat.group(1))
    else:
        m_all = re.findall(r"(\d{4})", txt)
        if len(m_all) >= 2:
            pattern = int(m_all[-1])

    return banco, expansion, pattern


def extract_drillbit(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    drillbit_patterns = [
        ("541", re.compile(r"CN54S?$", re.IGNORECASE)),
        ("44",  re.compile(r"(?:S|SJ|CN)44S?$", re.IGNORECASE)),
        ("54",  re.compile(r"(?:S|SJ)54S?$", re.IGNORECASE)),
        ("64",  re.compile(r"(?:CN|S)64S?$", re.IGNORECASE)),
    ]
    for code, pat in drillbit_patterns:
        if pat.search(s):
            return code
    return ""


# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Autonomia Data Cleaner</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Automatic transformation and validation of drilling autonomy data.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_esauto"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# TRANSFORMATION LEGEND
# ==========================================================
with st.expander("📖 Transformation Mapping Legend", expanded=False):
    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        st.markdown("""
**Coordinacion**
| Input | Output |
|-------|--------|
| A | 1 |
| B | 2 |
| C | 3 |
| D | 4 |
""")
        st.markdown("""
**Turno**
| Input | Output |
|-------|--------|
| Dia | 1 |
| Noche | 2 |
| Empty/other | 1 |
""")
    with lc2:
        st.markdown("""
**Expansion (Malla)** *(case-insensitive)*
| Input | Output |
|-------|--------|
| N17B / n17b | 170 |
| PL1S / pl1s | 101 |
| N17 / n17 | 17 |
| PL1 / pl1 | 1 |
| S04 / s04 | 4 |
| E07 / e07 | 7 |
| N12 / n12 | 12 |
| N11 / n11 | 11 |
| N13 / n13 | 13 |
| N14, S14, n14... | 14 |
""")
        st.markdown("""
**Categoria de Pozo**
| Input | Output |
|-------|--------|
| Produccion | 1 |
| Buffer | 2 |
| Auxiliar | Deleted |
| Empty/other | 1 |
""")
    with lc3:
        st.markdown("""
**Pozo**
| Prefix | Output |
|--------|--------|
| B + num | 100000 + num |
| C + num | 200000 + num |
| D + num | num |
| Aux / AX / other letters | Deleted |
""")
        st.markdown("""
**Modo de Perforacion**
| Input | Output |
|-------|--------|
| Autonomous | 1 |
| Manual | 2 |
| Teleremote | 3 |
| Empty/other | 1 |
""")

# ==========================================================
# FILE UPLOADS
# ==========================================================
uploaded_file = st.file_uploader(
    "📤 Upload Autonomia Excel file",
    type=["xlsx", "xls"],
    key="auto_file"
)

uploaded_ops = st.file_uploader(
    "📤 Upload Operators mapping file (ES_Operators.xlsx)",
    type=["xlsx", "xls"],
    key="ops_file"
)

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        initial_rows = len(df)

        # ---------- Normalize headers ----------
        original_cols = list(df.columns)
        rename_map = {}
        for col in original_cols:
            norm = normalize_header(col)
            if norm in expected_norm_map:
                rename_map[col] = expected_norm_map[norm]
        df = df.rename(columns=rename_map)

        steps_done = []

        # Check missing columns
        normalized_present = {normalize_header(c) for c in df.columns}
        missing = [c for c in EXPECTED_COLUMNS if normalize_header(c) not in normalized_present]
        if missing:
            steps_done.append("⚠️ Missing columns: " + ", ".join(missing))
        else:
            steps_done.append("✅ All 51 input columns found.")

        st.subheader("📄 Original Data (Before Cleaning)")
        st.dataframe(df.head(10), use_container_width=True)
        st.info(f"📏 Total rows before cleaning: {initial_rows}")

        # ==========================================================
        # CLEANING & TRANSFORMATION
        # ==========================================================
        with st.expander("⚙️ See Processing Steps", expanded=False):

            # ==============================================================
            # PRE-FILTER 1 — Estatus de pozo: keep only "Drilled"
            # ==============================================================
            if "Estatus de pozo" in df.columns:
                before = len(df)
                df = df[df["Estatus de pozo"].astype(str).str.strip().str.lower() == "drilled"]
                deleted = before - len(df)
                steps_done.append(f"✅ Filtered 'Estatus de pozo' -> kept only Drilled ({deleted} rows removed).")
            else:
                steps_done.append("⚠️ Column 'Estatus de pozo' not found.")

            # ==============================================================
            # PRE-FILTER 2 — Categoria de pozo: delete Auxiliar rows
            # ==============================================================
            if "Categoria de pozo" in df.columns:
                before = len(df)
                df = df[~df["Categoria de pozo"].astype(str).str.strip().str.lower().str.startswith("aux")]
                deleted = before - len(df)
                steps_done.append(f"✅ Removed 'Auxiliar' rows from 'Categoria de pozo' ({deleted} rows removed).")
            else:
                steps_done.append("⚠️ Column 'Categoria de pozo' not found.")

            # ==============================================================
            # STEP 1 — Perforadora: EDD0034 -> 34
            # ==============================================================
            if "Perforadora" in df.columns:
                def parse_perforadora(val):
                    s = str(val)
                    digits = re.findall(r"\d+", s)
                    if digits:
                        return int(digits[-1])
                    return 0
                df["Perforadora"] = df["Perforadora"].apply(parse_perforadora)
                steps_done.append("✅ Transformed 'Perforadora' -> numeric (EDD0034 -> 34).")
            else:
                steps_done.append("⚠️ Column 'Perforadora' not found.")

            # ==============================================================
            # STEP 2 — ShiftIndex: keep as-is, empty/random -> 0
            # ==============================================================
            if "ShiftIndex" in df.columns:
                df["ShiftIndex"] = pd.to_numeric(df["ShiftIndex"], errors="coerce").fillna(0)
                steps_done.append("✅ 'ShiftIndex': ensured numeric, empty/invalid -> 0.")
            else:
                steps_done.append("⚠️ Column 'ShiftIndex' not found.")

            # ==============================================================
            # STEP 3 — Turno: Dia->1, Noche->2, empty/random->1
            # ==============================================================
            if "turno (dia o noche)" in df.columns:
                def map_turno(val):
                    s = normalize_text(str(val))
                    if s.startswith("n"):
                        return 2
                    return 1
                df["turno (dia o noche)"] = df["turno (dia o noche)"].apply(map_turno)
                steps_done.append("✅ Transformed 'turno' -> Dia=1, Noche=2 (default 1).")
            else:
                steps_done.append("⚠️ Column 'turno (dia o noche)' not found.")

            # ==============================================================
            # STEP 4 — Coordinacion: A->1, B->2, C->3, D->4
            # ==============================================================
            if "Coordinacion" in df.columns:
                coord_map = {"a": 1, "b": 2, "c": 3, "d": 4}
                def map_coord(val):
                    s = str(val).strip().lower()
                    return coord_map.get(s, 0)
                df["Coordinacion"] = df["Coordinacion"].apply(map_coord)
                steps_done.append("✅ Transformed 'Coordinacion' -> A=1, B=2, C=3, D=4.")
            else:
                steps_done.append("⚠️ Column 'Coordinacion' not found.")

            # ==============================================================
            # STEP 5 — Malla -> Banco, Expansion, Pattern (replaces Malla)
            # ==============================================================
            if "Malla" in df.columns:
                bancos, expansions, patterns = [], [], []
                for val in df["Malla"]:
                    b, e, p = parse_malla(val)
                    bancos.append(b)
                    expansions.append(e)
                    patterns.append(p)

                idx_malla = df.columns.get_loc("Malla")
                df.insert(idx_malla, "Banco", bancos)
                df.insert(idx_malla + 1, "Expansion", expansions)
                df.insert(idx_malla + 2, "Pattern", patterns)
                df = df.drop(columns=["Malla"])
                steps_done.append("✅ Parsed 'Malla' -> Banco, Expansion, Pattern (N17B=170, PL1S=101).")
            else:
                steps_done.append("⚠️ Column 'Malla' not found.")

            # ==============================================================
            # STEP 6 — Pozo: B/C/D logic, remove aux/invalid/negative
            # ==============================================================
            if "Pozo" in df.columns:
                before = len(df)
                df["Pozo"] = df["Pozo"].apply(transform_pozo_value)
                df = df[df["Pozo"].notna()]
                df = df[df["Pozo"] > 0]
                deleted = before - len(df)
                steps_done.append(f"✅ Cleaned 'Pozo' with B/C/D logic ({deleted} invalid rows removed).")
            else:
                steps_done.append("⚠️ Column 'Pozo' not found.")

            # ==============================================================
            # STEP 7 — Coordinates: cross-fill, remove negatives, X>=100000
            # ==============================================================
            before = len(df)
            coord_cols = [
                "Coordenadas diseño X", "Coordenadas diseño Y", "Coordenadas diseño Z",
                "Coordenada real inicioX", "Coordenada real inicio Y", "Coordena real inicio Z"
            ]
            existing_coord = [c for c in coord_cols if c in df.columns]
            for c in existing_coord:
                df[c] = pd.to_numeric(df[c], errors="coerce")

            # X cross-fill
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df["Coordenadas diseño X"] = df["Coordenadas diseño X"].fillna(df["Coordenada real inicioX"])
                df["Coordenada real inicioX"] = df["Coordenada real inicioX"].fillna(df["Coordenadas diseño X"])
                both_x_empty = df["Coordenadas diseño X"].isna() & df["Coordenada real inicioX"].isna()
                df = df[~both_x_empty]

            # Y cross-fill
            if "Coordenadas diseño Y" in df.columns and "Coordenada real inicio Y" in df.columns:
                df["Coordenadas diseño Y"] = df["Coordenadas diseño Y"].fillna(df["Coordenada real inicio Y"])
                df["Coordenada real inicio Y"] = df["Coordenada real inicio Y"].fillna(df["Coordenadas diseño Y"])
                both_y_empty = df["Coordenadas diseño Y"].isna() & df["Coordenada real inicio Y"].isna()
                df = df[~both_y_empty]

            # Z cross-fill + Banco fallback
            if "Coordenadas diseño Z" in df.columns and "Coordena real inicio Z" in df.columns:
                df["Coordenadas diseño Z"] = df["Coordenadas diseño Z"].fillna(df["Coordena real inicio Z"])
                df["Coordena real inicio Z"] = df["Coordena real inicio Z"].fillna(df["Coordenadas diseño Z"])
                both_z_empty = df["Coordenadas diseño Z"].isna() & df["Coordena real inicio Z"].isna()
                if both_z_empty.any() and "Banco" in df.columns:
                    banco_val = pd.to_numeric(df.loc[both_z_empty, "Banco"], errors="coerce")
                    df.loc[both_z_empty, "Coordenadas diseño Z"] = banco_val
                    df.loc[both_z_empty, "Coordena real inicio Z"] = banco_val

            # Remove negative coordinates
            neg_mask = pd.Series(False, index=df.index)
            for c in existing_coord:
                if c in df.columns:
                    neg_mask = neg_mask | (df[c] < 0)
            df = df[~neg_mask]

            # Remove X < 100000
            if "Coordenadas diseño X" in df.columns and "Coordenada real inicioX" in df.columns:
                df = df[
                    (df["Coordenadas diseño X"] >= 100000) &
                    (df["Coordenada real inicioX"] >= 100000)
                ]

            deleted = before - len(df)
            steps_done.append(f"✅ Coordinates: cross-filled, negatives/X<100000 removed ({deleted} rows).")

            # ==============================================================
            # STEP 8 — Dureza & RPM: empty -> 0
            # ==============================================================
            if "Dureza" in df.columns:
                df["Dureza"] = pd.to_numeric(df["Dureza"], errors="coerce").fillna(0)
                steps_done.append("✅ 'Dureza': empty -> 0.")

            if "RPM de perforacion" in df.columns:
                df["RPM de perforacion"] = pd.to_numeric(df["RPM de perforacion"], errors="coerce").fillna(0)
                steps_done.append("✅ 'RPM de perforacion': empty -> 0.")

            # ==============================================================
            # STEP 9 — Velocidad de penetracion: remove 0 or empty
            # ==============================================================
            if "Velocidad de penetracion (m/minutos)" in df.columns:
                before = len(df)
                df["Velocidad de penetracion (m/minutos)"] = pd.to_numeric(
                    df["Velocidad de penetracion (m/minutos)"], errors="coerce"
                )
                df = df[df["Velocidad de penetracion (m/minutos)"] > 0]
                steps_done.append(f"✅ 'Velocidad penetracion': removed {before - len(df)} rows (empty/0).")

            # ==============================================================
            # STEP 10 — Pulldown KN: remove 0 or empty
            # ==============================================================
            if "Pulldown KN" in df.columns:
                before = len(df)
                df["Pulldown KN"] = pd.to_numeric(df["Pulldown KN"], errors="coerce")
                df = df[df["Pulldown KN"] > 0]
                steps_done.append(f"✅ 'Pulldown KN': removed {before - len(df)} rows (empty/0).")

            # ==============================================================
            # STEP 11 — Largo de pozo real: numeric, <=40, fallback to planeado
            # ==============================================================
            if "Largo de pozo real" in df.columns:
                df["Largo de pozo real"] = pd.to_numeric(df["Largo de pozo real"], errors="coerce")
                if "Largo de pozo planeado" in df.columns:
                    df["Largo de pozo planeado"] = pd.to_numeric(df["Largo de pozo planeado"], errors="coerce")
                    df["Largo de pozo real"] = df["Largo de pozo real"].fillna(df["Largo de pozo planeado"])
                # Values > 40 -> replace with planeado if available, else NaN
                too_big = df["Largo de pozo real"] > 40
                if too_big.any() and "Largo de pozo planeado" in df.columns:
                    fallback = df.loc[too_big, "Largo de pozo planeado"]
                    fallback = fallback.where(fallback <= 40)
                    df.loc[too_big, "Largo de pozo real"] = fallback
                elif too_big.any():
                    df.loc[too_big, "Largo de pozo real"] = pd.NA
                steps_done.append("✅ 'Largo de pozo real': numeric, <=40, fallback to planeado.")

            # ==============================================================
            # STEP 12 — Categoria de pozo: Produccion->1, Buffer->2, empty->1
            # ==============================================================
            if "Categoria de pozo" in df.columns:
                def map_cat(val):
                    s = str(val).strip().lower()
                    if s.startswith("buff"):
                        return 2
                    return 1
                df["Categoria de pozo"] = df["Categoria de pozo"].apply(map_cat)
                steps_done.append("✅ 'Categoria de pozo': Produccion/empty->1, Buffer->2.")

            # ==============================================================
            # STEP 13 — Operador: map from uploaded file
            # ==============================================================
            new_ops_df = None
            if "Operador" in df.columns:
                if uploaded_ops is None:
                    steps_done.append("⚠️ No operators mapping file uploaded — skipping operator mapping.")
                else:
                    try:
                        ops_df = pd.read_excel(uploaded_ops)
                        ops_rename = {}
                        for c in ops_df.columns:
                            n = normalize_header(c)
                            if n == "nombre":
                                ops_rename[c] = "Nombre"
                            elif n == "codigo":
                                ops_rename[c] = "Codigo"
                        ops_df = ops_df.rename(columns=ops_rename)

                        if "Nombre" not in ops_df.columns or "Codigo" not in ops_df.columns:
                            steps_done.append("⚠️ Operators file must have 'Nombre' and 'Codigo'.")
                        else:
                            ops_df["Nombre"] = ops_df["Nombre"].astype(str).str.strip()
                            ops_df["Codigo"] = pd.to_numeric(ops_df["Codigo"], errors="coerce").astype("Int64")
                            ops_df = ops_df.dropna(subset=["Codigo"])

                            ops_df["Norm"] = ops_df["Nombre"].apply(
                                lambda x: re.sub(r"\s+", "", normalize_text(x))
                            )
                            norm_to_code = dict(zip(ops_df["Norm"], ops_df["Codigo"]))

                            max_code = int(ops_df["Codigo"].max() or 0)
                            next_code_box = [max_code + 1]
                            new_norm_to_code = {}
                            new_ops = []

                            def map_operator(raw):
                                if pd.isna(raw) or str(raw).strip() == "":
                                    return 75
                                s_norm = re.sub(r"\s+", "", normalize_text(raw))

                                if s_norm in norm_to_code:
                                    return int(norm_to_code[s_norm])

                                # Fuzzy match against existing
                                best, best_sim = None, 0.0
                                for key in norm_to_code:
                                    sim = SequenceMatcher(None, s_norm, key).ratio()
                                    if sim > best_sim:
                                        best_sim = sim
                                        best = key
                                if best is not None and best_sim >= 0.85:
                                    return int(norm_to_code[best])

                                # Check among new operators
                                for known_norm, code in new_norm_to_code.items():
                                    sim = SequenceMatcher(None, s_norm, known_norm).ratio()
                                    if sim >= 0.90:
                                        return int(code)

                                # New operator
                                code = next_code_box[0]
                                next_code_box[0] += 1
                                new_norm_to_code[s_norm] = code
                                new_ops.append((str(raw).strip(), code))
                                return int(code)

                            df["Operador"] = df["Operador"].apply(map_operator)

                            if new_ops:
                                new_ops_df = pd.DataFrame(new_ops, columns=["Nombre", "Codigo"])
                                steps_done.append(f"🆕 New operators detected: {len(new_ops)}")
                            else:
                                steps_done.append("✅ All operators matched — no new ones.")

                    except Exception as e:
                        steps_done.append(f"⚠️ Operator mapping error: {e}")

            # ==============================================================
            # STEP 14 — Broca: extract drill bit code (44/54/541/64)
            # ==============================================================
            if "Broca" in df.columns:
                df["Broca"] = df["Broca"].apply(extract_drillbit)

                # Primary fallback by Perforadora
                if "Perforadora" in df.columns:
                    empty_mask = df["Broca"] == ""
                    if empty_mask.any():
                        valid = df.loc[~empty_mask]
                        if not valid.empty:
                            mode_by_rig = valid.groupby("Perforadora")["Broca"].agg(
                                lambda x: x.mode().iloc[0] if len(x) >= 2 and not x.mode().empty else ""
                            )
                            for idx in df.loc[empty_mask].index:
                                rig = df.at[idx, "Perforadora"]
                                if rig in mode_by_rig.index and mode_by_rig[rig] != "":
                                    df.at[idx, "Broca"] = mode_by_rig[rig]

                # Secondary fallback by Coordinacion
                if "Coordinacion" in df.columns:
                    empty_mask = df["Broca"] == ""
                    if empty_mask.any():
                        valid = df.loc[~empty_mask]
                        if not valid.empty:
                            mode_by_crew = valid.groupby("Coordinacion")["Broca"].agg(
                                lambda x: x.mode().iloc[0] if len(x) >= 2 and not x.mode().empty else ""
                            )
                            for idx in df.loc[empty_mask].index:
                                crew = df.at[idx, "Coordinacion"]
                                if crew in mode_by_crew.index and mode_by_crew[crew] != "":
                                    df.at[idx, "Broca"] = mode_by_crew[crew]

                # Convert to numeric
                df["Broca"] = pd.to_numeric(df["Broca"], errors="coerce").fillna(0)
                remaining = (df["Broca"] == 0).sum()
                steps_done.append(f"✅ 'Broca' -> drill bit code (44/54/541/64). {remaining} unresolved.")

            # ==============================================================
            # STEP 15 — Modo de perforacion: Autonomous=1, Manual=2, Teleremote=3
            # ==============================================================
            if "Modo de perforacion" in df.columns:
                def map_modo(val):
                    s = normalize_text(str(val))
                    if s.startswith("auton"):
                        return 1
                    if s.startswith("manu"):
                        return 2
                    if s.startswith("tele"):
                        return 3
                    if s in ["1", "2", "3"]:
                        return int(s)
                    return 1
                df["Modo de perforacion"] = df["Modo de perforacion"].apply(map_modo)
                steps_done.append("✅ 'Modo de perforacion': Autonomous=1, Manual=2, Teleremote=3.")

            # ==============================================================
            # STEP 16 — Velocidad efectiva & Velocidad penetracion (mts/hrs)
            # ==============================================================
            for vel_col in ["Velocidad efectiva ciclo (mt/hrs)", "Velocidad de penetracion (mts/hrs)"]:
                if vel_col in df.columns:
                    before = len(df)
                    df[vel_col] = pd.to_numeric(df[vel_col], errors="coerce")
                    df = df[df[vel_col] > 0]
                    steps_done.append(f"✅ '{vel_col}': removed {before - len(df)} rows (empty/negative).")

            # ==============================================================
            # FINAL — Round all numeric columns to 2 decimals
            # ==============================================================
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].round(2)

            steps_done.append(f"✅ All numeric values rounded to 2 decimal places.")
            steps_done.append(f"📊 Final: {len(df)} rows (from {initial_rows} original).")

            # --- Display Steps ---
            for step in steps_done:
                if step.startswith("✅"):
                    color, bg = "#137333", "#e8f8f0"
                elif step.startswith("⚠️"):
                    color, bg = "#b45309", "#fef3c7"
                else:
                    color, bg = "#1a56db", "#e0edff"
                st.markdown(
                    f"<div style='background-color:{bg};padding:10px;border-radius:8px;margin-bottom:8px;'>"
                    f"<span style='color:{color};font-weight:500;'>{step}</span></div>",
                    unsafe_allow_html=True
                )

            # Show new operators
            if uploaded_ops is not None and new_ops_df is not None and not new_ops_df.empty:
                st.markdown("### 🆕 New operators detected")
                st.dataframe(new_ops_df, use_container_width=True)

        # ==========================================================
        # QUALITY CHECKER
        # ==========================================================
        st.markdown("---")
        st.subheader("🔍 Quality Checker")

        # Build output dataframe
        available_out = [c for c in OUTPUT_COLUMNS if c in df.columns]
        missing_out = [c for c in OUTPUT_COLUMNS if c not in df.columns]

        if missing_out:
            st.warning(f"⚠️ Missing output columns (will be skipped): {', '.join(missing_out)}")

        df_out = df[available_out].copy()

        # Quality check per column
        quality_issues = []
        for pos, col in enumerate(df_out.columns, start=1):
            issues_in_col = []
            na_count = df_out[col].isna().sum()
            if na_count > 0:
                issues_in_col.append(f"{na_count} empty/NaN")

            numeric_col = pd.to_numeric(df_out[col], errors="coerce")
            non_numeric = df_out[col].notna() & numeric_col.isna()
            non_num_count = non_numeric.sum()
            if non_num_count > 0:
                bad_vals = df_out.loc[non_numeric, col].unique()[:5]
                issues_in_col.append(f"{non_num_count} non-numeric (e.g. {list(bad_vals)})")

            neg_count = (numeric_col < 0).sum()
            if neg_count > 0:
                issues_in_col.append(f"{neg_count} negative")

            if issues_in_col:
                quality_issues.append({
                    "Position": pos,
                    "Column": col,
                    "Issues": " | ".join(issues_in_col)
                })

        if quality_issues:
            qi_df = pd.DataFrame(quality_issues)
            st.markdown("#### ❌ Issues Found")
            st.dataframe(qi_df, use_container_width=True, hide_index=True)

            with st.expander("🔎 See rows with issues", expanded=False):
                for qi in quality_issues:
                    col = qi["Column"]
                    numeric_col = pd.to_numeric(df_out[col], errors="coerce")
                    bad_mask = df_out[col].isna() | numeric_col.isna() | (numeric_col < 0)
                    bad_rows = df_out[bad_mask]
                    if not bad_rows.empty:
                        st.markdown(f"**Column {qi['Position']}: {col}** — {len(bad_rows)} problematic rows:")
                        st.dataframe(bad_rows.head(20), use_container_width=True)
        else:
            st.success("✅ All output columns are fully numeric — no empty, negative, or text values.")

        # ==========================================================
        # PREVIEW
        # ==========================================================
        st.markdown("---")
        st.subheader("✅ Cleaned Data Preview (Output Order)")
        st.dataframe(df_out.head(15), use_container_width=True)
        st.success(f"✅ Final dataset: {len(df_out)} rows x {len(df_out.columns)} columns.")

        # ==========================================================
        # DOWNLOADS
        # ==========================================================
        st.markdown("---")
        st.subheader("💾 Export Cleaned File")

        # Excel with headers
        excel_buffer = io.BytesIO()
        df_out.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.seek(0)

        # TXT without headers
        txt_buffer = io.StringIO()
        df_out.to_csv(txt_buffer, index=False, header=False, sep="\t")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📘 Download Excel File",
                excel_buffer,
                file_name="Escondida_Autonomia_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col2:
            st.download_button(
                "📄 Download TXT File (no headers)",
                txt_buffer.getvalue(),
                file_name="Escondida_Autonomia_Cleaned.txt",
                mime="text/plain",
                use_container_width=True
            )

        # ==========================================================
        # UPDATED OPERATORS FILE (only if new operators found)
        # ==========================================================
        if uploaded_ops is not None and new_ops_df is not None and not new_ops_df.empty:
            try:
                ops_base = pd.read_excel(uploaded_ops)
                ops_rename2 = {}
                for c in ops_base.columns:
                    n = normalize_header(c)
                    if n == "nombre":
                        ops_rename2[c] = "Nombre"
                    elif n == "codigo":
                        ops_rename2[c] = "Codigo"
                ops_base = ops_base.rename(columns=ops_rename2)

                updated_ops = pd.concat(
                    [ops_base[["Nombre", "Codigo"]], new_ops_df],
                    ignore_index=True
                )

                ops_buffer = io.BytesIO()
                updated_ops.to_excel(ops_buffer, index=False, engine="openpyxl")
                ops_buffer.seek(0)

                today_str = datetime.now().strftime("%d_%m_%Y")

                st.markdown("---")
                st.subheader("💾 Export Updated Operators Mapping")
                st.download_button(
                    "📘 Download Updated Operators File",
                    ops_buffer,
                    file_name=f"Operators_MEL_{today_str}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.warning(f"⚠️ Could not build updated operators file: {e}")

        st.markdown("<hr>", unsafe_allow_html=True)
        st.caption("Built by Maxam - Omar El Kendi -")

    except Exception as e:
        st.error(f"⚠️ Error processing file: {e}")

else:
    st.info("📂 Please upload the Autonomia Excel file (and optionally the Operators mapping file) to begin.")
