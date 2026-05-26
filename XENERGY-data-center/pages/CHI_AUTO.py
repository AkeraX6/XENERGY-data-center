import streamlit as st
import pandas as pd
import io

# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Chinalco — Data Merger</h2>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:center; color:gray;'>Upload multiple Excel workbooks to merge and export consolidated datasets.</p>",
    unsafe_allow_html=True
)
st.markdown("---")

if st.button("← Back to Menu", key="back_chi"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# OUTPUT COLUMN DEFINITIONS
# ==========================================================
SHEET_NAMES = ["DrillingProfile", "Drilling", "Hauling", "Split", "Explosives"]

DRILLING_DATA_COLS = [
    "MACHINE", "DRILLPATTERN", "HOLE_NAME",
    "ACTUAL_X", "ACTUAL_Y", "ACTUAL_Z",
    "METERS", "ROP", "PULL_DOWN_KN", "TORQUE_NM", "BI",
    "DESIGN_SPACING", "DESIGN_BURDEN", "ACTUAL_SPACING", "ACTUAL_BURDEN", "BLOCKID",
]

HAULING_COLS = [
    "CYCLEID", "ENDCYCLE", "STARTLOAD", "ENDLOAD", "SHOVELLOADERNAME",
    "BLOCKID", "MATERIAL", "DESTINATION", "DIGRATE", "TONS",
    "CU", "AG", "FE", "MO", "AS", "ZN", "FLUOR", "MGO", "RTOX", "CUAS",
    "INP", "HARD", "HL_BI", "SG", "BXFI", "BXFS",
    "INTRU", "SKARN", "HORNFELS", "INTRUSIVOA", "INTRUSIVOB",
    "SKARNACTI", "SKARNSERPEN", "HORNDIOPS",
    "CHLOR", "PHLOG", "TALC", "MAGN", "PY", "ILLIT", "VALPT", "CAL",
    "BOND", "DWI", "MIC", "COSG", "RI", "RMC",
    "DIOPS", "TREM", "ACTIN", "RMRO", "SKMT", "RZNCU", "RQD", "UCS",
]

SPLIT_COLS = [
    "BLASTPATTERN", "BLOCKID", "SHOVEL", "DATE_SPLIT",
    "P10", "P20", "P30", "P40", "P50", "P60", "P70", "P80", "P90", "TS",
    "S0_250", "S0_375", "S0_500", "S0_750",
    "S1_000", "S1_500", "S2_000", "S3_000", "S4_000",
    "S5_000", "S6_000", "S7_000", "S8_000", "S9_000",
    "S10_000", "S12_000", "S14_000", "S16_000", "S18_000", "S20_000", "S25_000",
]

EXPLOSIVES_COLS = [
    "BLASTPROJECT", "PROJECTCREATED", "DATEFIRED", "HOLENAME", "HOLETYPE",
    "MATERIALTYPE", "ORIGINALNAME", "GRADEZ", "DESIGN_DIAMETER",
    "DESIGN_LENGTH", "ACTUAL_LENGTH",
    "DECKNUMBER", "EXPLOSIVEWEIGHTACTUAL", "EXPLOSIVEWEIGHTPLAN",
    "LOADLENGTHACTUAL", "LOADLENGTHPLAN", "PRODUCTNAME",
    "DENSITY", "RELATIVEBULKSTRENGTH", "RELATIVEWEIGHTSTRENGTH",
    "DECKNUMBER2", "STEMMINGACTUAL", "STEMMINGPLAN",
]

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def clean_outliers_by_quantile(df, columns_to_clean, group_col=None, lower_q=0.01, upper_q=0.99):
    """
    Remove rows where ANY value in columns_to_clean falls outside
    the [lower_q, upper_q] quantile range. If group_col is set,
    quantiles are computed per group (e.g. per SHOVEL).
    Returns: (df_cleaned, stats_df, rows_removed, pct_removed)
    """
    for col in columns_to_clean:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    rows_before = len(df)
    summary_rows = []
    mask_keep = pd.Series(True, index=df.index)

    if group_col and group_col in df.columns:
        groups = df[group_col].unique()
        for col in columns_to_clean:
            col_below = 0
            col_above = 0
            q_lows, q_highs = [], []
            for grp in groups:
                grp_mask = df[group_col] == grp
                grp_vals = df.loc[grp_mask, col]
                q_low = grp_vals.quantile(lower_q)
                q_high = grp_vals.quantile(upper_q)
                q_lows.append(q_low)
                q_highs.append(q_high)
                below = grp_mask & (df[col] < q_low)
                above = grp_mask & (df[col] > q_high)
                col_below += int(below.sum())
                col_above += int(above.sum())
                mask_keep &= ~below & ~above
            summary_rows.append({
                "Column": col,
                f"Q{lower_q} (Lower, avg)": round(sum(q_lows) / len(q_lows), 4),
                f"Q{upper_q} (Upper, avg)": round(sum(q_highs) / len(q_highs), 4),
                "Outliers Below": col_below,
                "Outliers Above": col_above,
            })
    else:
        for col in columns_to_clean:
            q_low = df[col].quantile(lower_q)
            q_high = df[col].quantile(upper_q)
            below = (df[col] < q_low).sum()
            above = (df[col] > q_high).sum()
            mask_keep &= (df[col] >= q_low) & (df[col] <= q_high)
            summary_rows.append({
                "Column": col,
                f"Q{lower_q} (Lower)": round(q_low, 4),
                f"Q{upper_q} (Upper)": round(q_high, 4),
                "Outliers Below": int(below),
                "Outliers Above": int(above),
            })

    df_cleaned = df[mask_keep].reset_index(drop=True)
    rows_removed = rows_before - len(df_cleaned)
    pct_removed = (rows_removed / rows_before * 100) if rows_before > 0 else 0
    stats_df = pd.DataFrame(summary_rows)
    return df_cleaned, stats_df, rows_removed, pct_removed


def clean_df(df):
    """Replace '-', empty strings, and NaN with 0. Fix mixed-type columns."""
    df = df.replace(["-", ""], 0)
    df = df.fillna(0)
    # Fix mixed-type columns: convert object columns to string to avoid Arrow errors
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str)
    return df


def pick_columns(df, columns):
    """Select only existing columns in the specified order."""
    available = [c for c in columns if c in df.columns]
    return df[available]


def to_excel(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


def to_txt(df):
    """Tab-separated, no headers, floats rounded to 2 decimals."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype in ("float64", "float32"):
            out[col] = out[col].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "0")
    buf = io.StringIO()
    out.to_csv(buf, index=False, header=False, sep="\t")
    return buf.getvalue()


def download_buttons(df, label, key):
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            f"Download {label} — Excel",
            to_excel(df),
            file_name=f"{label}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key}_xl",
        )
    with c2:
        st.download_button(
            f"Download {label} — TXT",
            to_txt(df),
            file_name=f"{label}.txt",
            mime="text/plain",
            key=f"{key}_tx",
        )

# ==========================================================
# FILE UPLOAD
# ==========================================================
st.subheader("Upload Files")
uploaded_files = st.file_uploader(
    "Select one or more Excel workbooks or CSV files (CSV filenames must contain the sheet name, e.g. DrillingProfile.csv)",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key="chi_files",
)

if not uploaded_files:
    st.info("Upload files to begin processing.")
    st.stop()

# ==========================================================
# READ ALL SHEETS
# ==========================================================
all_sheets = {name: [] for name in SHEET_NAMES}
file_report = []

for f in uploaded_files:
    try:
        fname = f.name.lower()
        found = []

        if fname.endswith(".csv"):
            # CSV: match filename to a sheet name
            matched_sheet = None
            for sheet in SHEET_NAMES:
                if sheet.lower() in fname:
                    matched_sheet = sheet
                    break
            if matched_sheet:
                data = pd.read_csv(f)
                if not data.empty:
                    data.columns = data.columns.str.strip()
                    all_sheets[matched_sheet].append(data)
                    found.append(f"{matched_sheet} ({len(data)})")
            else:
                found.append("no sheet name match in filename")
        else:
            # Excel: read all matching sheets
            xls = pd.ExcelFile(f)
            for sheet in SHEET_NAMES:
                if sheet in xls.sheet_names:
                    data = pd.read_excel(xls, sheet_name=sheet)
                    if not data.empty:
                        data.columns = data.columns.str.strip()
                        all_sheets[sheet].append(data)
                        found.append(f"{sheet} ({len(data)})")

        file_report.append(f"**{f.name}** — {', '.join(found) if found else 'no matching sheets'}")
    except Exception as e:
        st.error(f"Error reading {f.name}: {e}")

# ==========================================================
# IMPORT SUMMARY
# ==========================================================
with st.expander("Import Summary", expanded=True):
    for line in file_report:
        st.markdown(line)
    st.markdown("---")
    summary_cols = st.columns(len(SHEET_NAMES))
    for i, sheet in enumerate(SHEET_NAMES):
        total_rows = sum(len(d) for d in all_sheets[sheet])
        file_count = len(all_sheets[sheet])
        with summary_cols[i]:
            st.metric(sheet, f"{total_rows} rows", f"{file_count} file(s)")

# ==========================================================
# PROCESS & OUTPUT
# ==========================================================
st.markdown("---")
st.subheader("Outputs")

tabs = st.tabs(["Drilling Data", "Hauling", "Split", "Explosives"])

# ----------------------------------------------------------
# TAB 1 — DRILLING DATA (DrillingProfile + Drilling join)
# ----------------------------------------------------------
with tabs[0]:
    if all_sheets["DrillingProfile"] and all_sheets["Drilling"]:
        dp = pd.concat(all_sheets["DrillingProfile"], ignore_index=True)
        dr = pd.concat(all_sheets["Drilling"], ignore_index=True)

        # Normalize join keys to string
        dp["DRILLPATTERN"] = dp["DRILLPATTERN"].astype(str).str.strip()
        dp["HOLE_NAME"] = dp["HOLE_NAME"].astype(str).str.strip()
        dr["DRILLPATTERN"] = dr["DRILLPATTERN"].astype(str).str.strip()
        dr["HOLE_NAME"] = dr["HOLE_NAME"].astype(str).str.strip()

        # Take only needed columns from Drilling, deduplicate
        drill_extra_cols = [
            "DRILLPATTERN", "HOLE_NAME",
            "ACTUAL_X", "ACTUAL_Y", "ACTUAL_Z",
            "DESIGN_SPACING", "DESIGN_BURDEN", "ACTUAL_SPACING", "ACTUAL_BURDEN", "BLOCKID",
        ]
        dr_subset = pick_columns(dr, drill_extra_cols)
        dr_subset = dr_subset.drop_duplicates(subset=["DRILLPATTERN", "HOLE_NAME"])

        # Inner join — rows without a match in Drilling are removed
        drilling_data = dp.merge(dr_subset, on=["DRILLPATTERN", "HOLE_NAME"], how="inner")

        # Reorder, clean
        drilling_data = pick_columns(drilling_data, DRILLING_DATA_COLS)
        drilling_data = clean_df(drilling_data)

        rows_removed = len(dp) - len(drilling_data)

        st.dataframe(drilling_data.head(30))
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.info(f"{len(drilling_data)} rows  |  {len(drilling_data.columns)} columns")
        with col_info2:
            if rows_removed > 0:
                st.warning(f"{rows_removed} rows removed (holes not found in Drilling)")

        download_buttons(drilling_data, "DrillingData", "dd")
    else:
        missing = []
        if not all_sheets["DrillingProfile"]:
            missing.append("DrillingProfile")
        if not all_sheets["Drilling"]:
            missing.append("Drilling")
        st.warning(f"Missing required sheets: {', '.join(missing)}")

# ----------------------------------------------------------
# TAB 2 — HAULING
# ----------------------------------------------------------
with tabs[1]:
    if all_sheets["Hauling"]:
        hauling = pd.concat(all_sheets["Hauling"], ignore_index=True)
        hauling = pick_columns(hauling, HAULING_COLS)
        hauling = clean_df(hauling)

        st.dataframe(hauling.head(30))
        st.info(f"{len(hauling)} rows  |  {len(hauling.columns)} columns")
        download_buttons(hauling, "Hauling", "haul")
    else:
        st.warning("No Hauling sheets found in the uploaded files.")

# ----------------------------------------------------------
# TAB 3 — SPLIT
# ----------------------------------------------------------
with tabs[2]:
    if all_sheets["Split"]:
        split = pd.concat(all_sheets["Split"], ignore_index=True)
        split = pick_columns(split, SPLIT_COLS)
        split = clean_df(split)

        # --- Outlier filtering controls ---
        st.markdown("**Outlier Filtering Configuration**")

        default_filter_cols = ["P10", "P20", "P30", "P40", "P50", "P60", "P70", "P80", "P90", "TS"]
        numeric_candidates = [c for c in default_filter_cols if c in split.columns]

        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            selected_filter_cols = st.multiselect(
                "Columns to filter",
                options=numeric_candidates,
                default=numeric_candidates,
                key="split_filter_cols",
            )
        with col_cfg2:
            group_by_shovel = st.checkbox("Filter per SHOVEL", value=True, key="split_group_shovel")

        col_sl1, col_sl2 = st.columns(2)
        with col_sl1:
            lower_q = st.slider("Lower quantile", 0.00, 0.10, 0.01, 0.01, key="split_lq")
        with col_sl2:
            upper_q = st.slider("Upper quantile", 0.90, 1.00, 0.99, 0.01, key="split_uq")

        # --- Apply filtering ---
        if selected_filter_cols:
            group_col = "SHOVEL" if group_by_shovel and "SHOVEL" in split.columns else None
            split, stats_df, rows_removed, pct_removed = clean_outliers_by_quantile(
                split, selected_filter_cols, group_col=group_col,
                lower_q=lower_q, upper_q=upper_q
            )
            rows_after = len(split)

            st.markdown("---")
            st.markdown("**Outlier Filtering Summary**")
            st.dataframe(stats_df, hide_index=True)

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Rows Before", rows_after + rows_removed)
            with col_m2:
                st.metric("Rows After", rows_after)
            with col_m3:
                st.metric("Removed", f"{rows_removed} ({pct_removed:.1f}%)")
        else:
            st.info("No columns selected for filtering — showing raw merged data.")

        st.markdown("---")
        st.dataframe(split.head(30))
        st.info(f"{len(split)} rows  |  {len(split.columns)} columns")
        download_buttons(split, "Split", "spl")
    else:
        st.warning("No Split sheets found in the uploaded files.")

# ----------------------------------------------------------
# TAB 4 — EXPLOSIVES
# ----------------------------------------------------------
with tabs[3]:
    if all_sheets["Explosives"]:
        explosives = pd.concat(all_sheets["Explosives"], ignore_index=True)
        explosives = pick_columns(explosives, EXPLOSIVES_COLS)
        explosives = clean_df(explosives)

        st.dataframe(explosives.head(30))
        st.info(f"{len(explosives)} rows  |  {len(explosives.columns)} columns")
        download_buttons(explosives, "Explosives", "expl")
    else:
        st.warning("No Explosives sheets found in the uploaded files.")

# ==========================================================
st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam — Omar El Kendi")

