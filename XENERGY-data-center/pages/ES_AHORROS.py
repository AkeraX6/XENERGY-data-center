import streamlit as st
import pandas as pd
import re
import io
import csv
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Ahorros Report Generator</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:gray;'>"
    "Upload QAQC files, clean, and generate the structured Excel report with formulas.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

if st.button("Back to Menu", key="back_ahorros"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# CLEANING FUNCTIONS  (shared logic with ES_QAQC)
# ==========================================================

def read_csv_smart(file_obj):
    sample_bytes = file_obj.read(8192)
    file_obj.seek(0)
    encodings_to_try = ("utf-8", "cp1252", "latin1", "iso-8859-1")
    delimiters = [",", ";", "\t", "|"]
    for enc in encodings_to_try:
        try:
            text = sample_bytes.decode(enc, errors="replace")
        except Exception:
            continue
        sep = None
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(text, delimiters="".join(delimiters))
            sep = dialect.delimiter
        except Exception:
            if text.count(";") > text.count(","):
                sep = ";"
            elif "\t" in text:
                sep = "\t"
            elif "|" in text:
                sep = "|"
            else:
                sep = ","
        try:
            file_obj.seek(0)
            return pd.read_csv(file_obj, sep=sep, engine="python", encoding=enc)
        except Exception:
            file_obj.seek(0)
            continue
    file_obj.seek(0)
    return pd.read_csv(file_obj, sep=None, engine="python", encoding="latin1")


def _replace_dash_with_na(series):
    if series is None:
        return series
    return series.replace(["-", " -", "- ", "\u2014", "\u2013", "", "\xa0"], pd.NA)


def _to_numeric(series):
    return pd.to_numeric(_replace_dash_with_na(series), errors="coerce")


def find_water_level_column(df):
    for c in df.columns:
        key = re.sub(r"\s+", "", str(c).strip().lower())
        if ("water" in key) and ("lev" in key):
            return c
    return None


def extract_level_from_blast(text):
    if pd.isna(text):
        return None
    m = re.search(r"(\d{4})", str(text))
    return int(m.group(1)) if m else None


def extract_expansion_from_blast(text):
    if pd.isna(text):
        return None
    txt = str(text).upper()
    if "N17B" in txt:
        return 170
    if "PL1S" in txt:
        return 111
    m = re.search(r"N(\d{1,2})(?![A-Z])", txt)
    if m:
        return int(m.group(1))
    m = re.search(r"PL(\d{1,2})(?![A-Z])", txt)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:S|L|E)(\d{1,2})", txt)
    if m:
        return int(m.group(1))
    return None


def parse_borehole_and_grid(raw_val):
    if pd.isna(raw_val):
        return None, ""
    s = str(raw_val).strip()
    if s == "":
        return None, ""
    s = re.sub(r"\s+", "", s)
    if "_" in s:
        left, right = s.split("_", 1)
        grid = int(left) if left.isdigit() else None
        suffix = right
    else:
        grid = None
        suffix = s
    suffix_low = suffix.lower()
    if suffix_low.startswith("aux"):
        return grid, None
    m = re.match(r"^([a-z])(\d+)$", suffix_low)
    if m:
        letter, num = m.groups()
        if letter == "b":
            return grid, int("100000" + num)
        elif letter == "c":
            return grid, int("200000" + num)
        elif letter == "d":
            return grid, int(num)
        else:
            return grid, None
    if suffix_low.isdigit():
        return grid, int(suffix_low)
    return grid, None


def fill_boreholes_by_blast(df):
    def _fill_group(group):
        counter = 10000
        new_vals = []
        for v in group["Borehole"]:
            if v == "" or pd.isna(v):
                new_vals.append(counter)
                counter += 1
            else:
                new_vals.append(v)
        group["Borehole"] = new_vals
        return group
    return df.groupby("Blast", group_keys=False).apply(_fill_group)


def cross_fill_pair(df, col_a, col_b, steps_done, label):
    if col_a not in df.columns or col_b not in df.columns:
        steps_done.append(f"  {label}: columns not found ({col_a}, {col_b}).")
        return df
    df[col_a] = _replace_dash_with_na(df[col_a])
    df[col_b] = _replace_dash_with_na(df[col_b])
    df[col_a] = df[col_a].fillna(df[col_b])
    df[col_b] = df[col_b].fillna(df[col_a])
    steps_done.append(f"  Cross-filled {label}.")
    return df


def process_file(df):
    steps_done = []

    # Clean invalid Density
    if "Density" in df.columns:
        before = len(df)
        df["Density_clean"] = pd.to_numeric(df["Density"], errors="coerce")
        df = df[df["Density_clean"].notna() & (df["Density_clean"] > 0)]
        deleted = before - len(df)
        df.drop(columns=["Density_clean"], inplace=True)
        steps_done.append(f"  Density: removed {deleted} invalid rows.")

    # Remove negative coordinates
    if "Local X (Design)" in df.columns and "Local Y (Design)" in df.columns:
        before = len(df)
        df["Local X (Design)"] = _to_numeric(df["Local X (Design)"])
        df["Local Y (Design)"] = _to_numeric(df["Local Y (Design)"])
        df = df[(df["Local X (Design)"] >= 0) & (df["Local Y (Design)"] >= 0)]
        deleted = before - len(df)
        steps_done.append(f"  Coordinates: removed {deleted} rows with negatives.")

    # Level, Expansion, Grid, Borehole
    if "Blast" in df.columns:
        df["Level"] = df["Blast"].apply(extract_level_from_blast)
        df["Expansion"] = df["Blast"].apply(extract_expansion_from_blast)
        if "Borehole" in df.columns:
            grids, bores = [], []
            for v in df["Borehole"]:
                g, b = parse_borehole_and_grid(v)
                grids.append(g)
                bores.append(b if b is not None else None if v is not None else "")
            df["Grid"] = grids
            df["Borehole"] = bores
            before_invalid = len(df)
            df = df[df["Borehole"].notna()]
            deleted_invalid = before_invalid - len(df)
            df["Borehole"] = df["Borehole"].apply(lambda x: "" if x is None else x)
            df = fill_boreholes_by_blast(df)
            steps_done.append(f"  Parsed Level/Expansion/Grid/Borehole ({deleted_invalid} invalid removed).")
            cols = list(df.columns)
            for c in ["Level", "Expansion", "Grid", "Borehole"]:
                if c in cols:
                    cols.remove(c)
            if "Blast" in cols:
                idx = cols.index("Blast")
                cols[idx + 1: idx + 1] = ["Level", "Expansion", "Grid", "Borehole"]
                df = df[cols]

    # Hole Length cross-fill
    if "Hole Length (Design)" in df.columns and "Hole Length (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Hole Length (Design)", "Hole Length (Actual)", steps_done, "Hole Length")
        df.dropna(subset=["Hole Length (Design)", "Hole Length (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"  Hole Length: removed {deleted} fully-empty rows.")

    # Explosive cross-fill
    if "Explosive (kg) (Design)" in df.columns and "Explosive (kg) (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Explosive (kg) (Design)", "Explosive (kg) (Actual)", steps_done, "Explosive")
        df.dropna(subset=["Explosive (kg) (Design)", "Explosive (kg) (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"  Explosive: removed {deleted} fully-empty rows.")

    # Stemming cross-fill
    if "Stemming (Design)" in df.columns and "Stemming (Actual)" in df.columns:
        before = len(df)
        df = cross_fill_pair(df, "Stemming (Design)", "Stemming (Actual)", steps_done, "Stemming")
        df.dropna(subset=["Stemming (Design)", "Stemming (Actual)"], how="all", inplace=True)
        deleted = before - len(df)
        steps_done.append(f"  Stemming: removed {deleted} fully-empty rows.")

    # Water Level: dash → 0
    water_col = find_water_level_column(df)
    if water_col:
        df[water_col] = df[water_col].astype(str).str.strip()
        df[water_col] = df[water_col].replace(["-", "\u2014", "\u2013", ""], "0")
        df[water_col] = pd.to_numeric(df[water_col], errors="coerce").fillna(0)
        steps_done.append(f"  '{water_col}': dashes → 0.")

    # Asset clean
    asset_col = next((c for c in df.columns if "Asset" in c), None)
    if asset_col:
        df[asset_col] = df[asset_col].astype(str).str.extract(r"(\d+)", expand=False)
        df[asset_col] = _replace_dash_with_na(df[asset_col])
        empty_before = int(df[asset_col].isna().sum())
        if empty_before > 0 and "Grid" in df.columns:
            grid_mode = (
                df.dropna(subset=[asset_col])
                .groupby("Grid")[asset_col]
                .agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else pd.NA)
            )
            filled_mask = df[asset_col].isna()
            df.loc[filled_mask, asset_col] = df.loc[filled_mask, "Grid"].map(grid_mode)
        still_empty = int(df[asset_col].isna().sum())
        if still_empty > 0:
            overall_mode = df[asset_col].mode()
            if len(overall_mode) > 0:
                df[asset_col] = df[asset_col].fillna(overall_mode.iloc[0])
        steps_done.append(f"  Asset cleaned.")

    return df, steps_done


# ==========================================================
# DENSITY FIX
# ==========================================================
def fix_density(v):
    try:
        v = float(v)
    except (ValueError, TypeError):
        return v
    if 100 <= v <= 200:
        return v / 100
    if 10 <= v <= 99:
        return v / 10
    if 2 < v <= 9:
        return v / 10
    return v


# ==========================================================
# SHEET NAME CLEANER
# ==========================================================
_MONTHS_PAT = (
    r"(?:_?)(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|"
    r"Septiembre|Octubre|Noviembre|Diciembre|"
    r"Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)"
)


def clean_sheet_name(filename):
    """
    QAQC_2485_PL1_5002_04_Mayo_21.xlsx  →  2485_PL1_5002_04
    """
    name = re.sub(r"\.(xlsx|xls|csv)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"^QAQC_", "", name, flags=re.IGNORECASE)
    name = re.sub(rf"{_MONTHS_PAT}.*$", "", name, flags=re.IGNORECASE)
    name = name.strip("_ ")
    # Sanitise for Excel sheet names
    name = re.sub(r'[\\/:*?\"\[\]<>|]', "_", name)
    return name[:31] if len(name) > 31 else (name or "Sheet")


# ==========================================================
# EXCEL REPORT CONSTANTS
# ==========================================================
HEADERS = [
    "ID malla",                                       # A  (1)
    "I Pozo",                                         # B  (2)
    "Long real BC",                                   # C  (3)
    "Pasadura real BC",                               # D  (4)
    "Taco real BC",                                   # E  (5)
    "Diámetro Protocolo BC",                          # F  (6)
    "Densidad Real calculada",                        # G  (7)  formula
    "Densidad protocolo BC",                          # H  (8)
    "Kg real BC",                                     # I  (9)
    "Burden",                                         # J  (10)
    "Spacing",                                        # K  (11)
    "Area protocolo BC",                              # L  (12) formula
    "IP protocolo BC (t/m)",                          # M  (13) formula
    "Long equivalente LB según pasaduras",            # N  (14) formula
    "Pasadura LB",                                    # O  (15)
    "Taco LB",                                        # P  (16) formula
    "Diámetro Protocolo",                             # Q  (17)
    "Densidad LB",                                    # R  (18) constant
    "Kg LB",                                          # S  (19) formula
    "B LB",                                           # T  (20)
    "S LB",                                           # U  (21)
    "Tonelaje tronado LB",                            # V  (22) formula
    "Area LB",                                        # W  (23) formula
    "IP LB (ton/m)",                                  # X  (24) formula
    "kg LB eq varicion de densidad solo produccion",  # Y  (25) formula
    "Tonelaje real tronado",                          # Z  (26) formula
]

# col_number (1-based) → source column in cleaned dataframe
DATA_MAP = {
    1:  "Grid",                     # A  ID malla
    2:  "Borehole",                 # B  I Pozo
    3:  "Hole Length (Actual)",     # C  Long real BC
    4:  "Subdrill (Design)",       # D  Pasadura real BC
    5:  "Stemming (Actual)",       # E  Taco real BC
    6:  "Diameter (Design)",       # F  Diámetro Protocolo BC
    8:  "Density",                 # H  Densidad protocolo BC
    9:  "Explosive (kg) (Actual)", # I  Kg real BC
    10: "Burden (Design)",         # J  Burden
    11: "Spacing (Design)",        # K  Spacing
    15: "Subdrill (Design)",       # O  Pasadura LB  (= Subdrill)
    17: "Diameter (Design)",       # Q  Diámetro Protocolo (= F)
    20: "Burden (Design)",         # T  B LB  (= Burden)
    21: "Spacing (Design)",        # U  S LB  (= Spacing)
}


# ==========================================================
# EXCEL GENERATOR
# ==========================================================
def _safe_number(val):
    """Convert a value to a proper number for openpyxl."""
    if pd.isna(val) or val == "" or val is None:
        return None
    try:
        f = float(val)
        if f == int(f):
            return int(f)
        return f
    except (ValueError, TypeError):
        return val


def write_sheet(ws, df):
    """Write one blast sheet: headers + data + Excel formulas."""

    # ── Styles ───────────────────────────────────────────────
    hdr_font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    fill_bc = PatternFill("solid", fgColor="404040")
    fill_lb = PatternFill("solid", fgColor="1D5FA0")
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    data_align = Alignment(horizontal="center", vertical="center")
    thin = Border(
        left=Side("thin"), right=Side("thin"),
        top=Side("thin"), bottom=Side("thin"),
    )

    # ── Headers (row 1) ─────────────────────────────────────
    for ci, hdr in enumerate(HEADERS, 1):
        c = ws.cell(row=1, column=ci, value=hdr)
        c.font = hdr_font
        c.fill = fill_lb if ci >= 14 else fill_bc
        c.alignment = hdr_align
        c.border = thin

    # ── Data rows (starting row 2) ──────────────────────────
    for ri, (_, row) in enumerate(df.iterrows()):
        r = ri + 2  # Excel row

        # Data columns
        for col_1, src in DATA_MAP.items():
            val = _safe_number(row.get(src))
            c = ws.cell(row=r, column=col_1, value=val)
            c.alignment = data_align
            c.border = thin

        # Densidad LB = 1.3  (column R = 18)
        c = ws.cell(row=r, column=18, value=1.3)
        c.alignment = data_align
        c.border = thin

        # Formula columns  (English function names — Excel shows
        # them in the user locale automatically)
        formulas = {
            7:  f"=(I{r}/(C{r}-E{r}))/(POWER(F{r}/25.4,2)*0.507)",         # G  Densidad Real calculada
            12: f"=J{r}*K{r}",                                              # L  Area protocolo BC
            13: f"=IF(B{r}>5000,0,(L{r}*(C{r}-D{r})*2.5)/C{r})",           # M  IP protocolo BC
            14: f"=C{r}+(O{r}-D{r})",                                       # N  Long equivalente LB
            16: f'=IF(F{r}=270,5,IF(F{r}=311,5.5,""))',                     # P  Taco LB
            19: f"=(Q{r}/2000)^2*PI()*(N{r}-P{r})*R{r}*1000",              # S  Kg LB
            22: f"=T{r}*U{r}*(N{r}-O{r})",                                  # V  Tonelaje tronado LB
            23: f"=T{r}*U{r}",                                              # W  Area LB
            24: f"=IF(B{r}>5000,0,(W{r}*(N{r}-O{r})*2.5)/N{r})",           # X  IP LB
            25: f"=IF(B{r}>5000,0,(Q{r}/2000)^2*PI()*(N{r}-P{r})*R{r}*1000)",  # Y  kg LB eq
            26: f"=J{r}*K{r}*(C{r}-D{r})*2.5",                             # Z  Tonelaje real tronado
        }
        for col_1, formula in formulas.items():
            c = ws.cell(row=r, column=col_1, value=formula)
            c.alignment = data_align
            c.border = thin

    # ── Column widths ────────────────────────────────────────
    widths = {
        1: 11, 2: 12, 3: 12, 4: 13, 5: 12, 6: 16,
        7: 18, 8: 16, 9: 12, 10: 10, 11: 10,
        12: 14, 13: 16, 14: 22, 15: 13, 16: 10,
        17: 16, 18: 12, 19: 10, 20: 8, 21: 8,
        22: 17, 23: 10, 24: 14, 25: 28, 26: 17,
    }
    for ci, w in widths.items():
        ws.column_dimensions[get_column_letter(ci)].width = w

    # Header row height
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "A2"


def generate_excel(cleaned_files):
    """Build workbook with one sheet per blast file."""
    wb = Workbook()
    wb.remove(wb.active)  # remove default empty sheet

    for sheet_name, df in cleaned_files:
        ws = wb.create_sheet(title=sheet_name)
        write_sheet(ws, df)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ==========================================================
# MAIN UI
# ==========================================================
uploaded_files = st.file_uploader(
    "Upload QAQC files",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    # ── 1) Clean every file ──────────────────────────────────
    cleaned_files = []
    all_steps = {}

    progress = st.progress(0, text="Cleaning files…")
    for i, uf in enumerate(uploaded_files):
        fname = uf.name.lower()
        df = read_csv_smart(uf) if fname.endswith(".csv") else pd.read_excel(uf)

        df_clean, steps = process_file(df)

        # Fix density scale
        if "Density" in df_clean.columns:
            df_clean["Density"] = df_clean["Density"].apply(fix_density)

        sheet_name = clean_sheet_name(uf.name)
        cleaned_files.append((sheet_name, df_clean))
        all_steps[uf.name] = steps
        progress.progress((i + 1) / len(uploaded_files), text=f"Cleaned {i + 1}/{len(uploaded_files)}")

    progress.empty()

    # ── Detect files where cleaning removed ALL rows ─────────
    empty_files = [(name, uf_name) for (name, df), uf_name
                   in zip(cleaned_files, [u.name for u in uploaded_files])
                   if len(df) == 0]
    cleaned_files = [(name, df) for name, df in cleaned_files if len(df) > 0]

    if empty_files:
        st.warning(
            f"**{len(empty_files)} file(s) had all rows removed by the filters** "
            f"(excluded from the report):"
        )
        for sheet_name, original_name in empty_files:
            st.markdown(f"  - `{original_name}` → sheet `{sheet_name}`")

    # ── Deduplicate sheet names ──────────────────────────────
    seen = {}
    for i, (name, df) in enumerate(cleaned_files):
        if name in seen:
            seen[name] += 1
            cleaned_files[i] = (f"{name}_{seen[name]}", df)
        else:
            seen[name] = 0

    st.success(
        f"Cleaned **{len(uploaded_files)}** file(s): "
        f"**{len(cleaned_files)}** with data, **{len(empty_files)}** empty (excluded)."
    )

    # ── 2) Processing steps ──────────────────────────────────
    with st.expander("Processing Steps", expanded=False):
        for fname, steps in all_steps.items():
            st.markdown(f"**{fname}**")
            for s in steps:
                st.markdown(s)
            st.markdown("---")

    # ── 3) Preview cleaned data ──────────────────────────────
    st.subheader("Cleaned Data Preview")
    preview_cols = [
        "Grid", "Borehole", "Hole Length (Actual)", "Subdrill (Design)",
        "Stemming (Actual)", "Diameter (Design)", "Density",
        "Explosive (kg) (Actual)", "Burden (Design)", "Spacing (Design)",
    ]
    for name, df in cleaned_files:
        with st.expander(f"{name}  ({len(df)} rows)"):
            cols_present = [c for c in preview_cols if c in df.columns]
            st.dataframe(df[cols_present].head(25), use_container_width=True)

    # ── 4) Quality check ─────────────────────────────────────
    st.markdown("---")
    st.subheader("Data Quality Check")

    if st.button("Run Quality Check", use_container_width=True):
        qc_cols = [
            "Grid", "Borehole", "Hole Length (Actual)", "Subdrill (Design)",
            "Stemming (Actual)", "Diameter (Design)", "Density",
            "Explosive (kg) (Actual)", "Burden (Design)", "Spacing (Design)",
        ]
        all_ok = True

        for name, df in cleaned_files:
            file_issues = []
            for col in qc_cols:
                if col not in df.columns:
                    file_issues.append(f"Missing column: **{col}**")
                    all_ok = False
                    continue

                col_issues = []
                # Empty / NaN
                empty_count = int(
                    df[col].isna().sum()
                    + (df[col].astype(str).str.strip() == "").sum()
                )
                if empty_count > 0:
                    col_issues.append(f"{empty_count} empty")
                    all_ok = False

                # Text in numeric columns
                non_empty = df[col].dropna().astype(str).str.strip()
                non_empty = non_empty[non_empty != ""]
                text_count = 0
                special_count = 0
                if len(non_empty) > 0:
                    text_mask = non_empty.apply(lambda x: bool(re.search(r"[A-Za-z]", str(x))))
                    text_count = int(text_mask.sum())

                    # Special characters
                    special_mask = non_empty.apply(
                        lambda x: bool(re.search(r"[^0-9eE.\-+\s]", str(x)))
                    )
                    special_count = int(special_mask.sum())

                if text_count > 0:
                    col_issues.append(f"{text_count} text cells")
                    all_ok = False
                if special_count > 0:
                    col_issues.append(f"{special_count} special chars")
                    all_ok = False

                if col_issues:
                    file_issues.append(f"**{col}**: " + " | ".join(col_issues))

            if file_issues:
                st.warning(f"**{name}**")
                for issue in file_issues:
                    st.markdown(f"  - {issue}")
            else:
                st.markdown(f"**{name}**: All columns OK")

        if all_ok:
            st.success("All files passed quality check — ready to generate the report.")

    # ── 5) Generate & download ───────────────────────────────
    st.markdown("---")
    st.subheader("Generate Ahorros Report")

    st.markdown(
        f"The report will contain **{len(cleaned_files)}** sheet(s): "
        + ", ".join(f"`{n}`" for n, _ in cleaned_files)
    )

    today = date.today().strftime("%Y-%m-%d")
    excel_buf = generate_excel(cleaned_files)

    st.download_button(
        "Download Ahorros Report (.xlsx)",
        excel_buf,
        file_name=f"Ahorros_Report_{today}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.caption("Built by Maxam — Omar El Kendi")

else:
    st.info("Upload QAQC Excel or CSV files to begin.")

