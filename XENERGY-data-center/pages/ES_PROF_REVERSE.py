import streamlit as st
import pandas as pd
import io
import re
import csv

# ==========================================================
# COLUMN DEFINITIONS FOR X-ENERGY FILE (after removing leading seq number)
# ==========================================================
XENERGY_COLUMNS = [
    "Blast", "Hole_ID", "Coord_X", "Coord_Y", "Coord_Z",
    "Hole_Length", "Subdrill", "Burden", "Spacing", "Diameter",
    "Stemming", "Density_1", "Density_2"
]

# Density rules by hole letter prefix
DENSITY_RULES = {
    "B": (0.8, 0.8),
    "C": (0.9, 0.9),
}


# ==========================================================
# HELPERS
# ==========================================================
def detect_delimiter(text: str) -> str:
    for delim in ["\t", ";", ","]:
        if delim in text:
            try:
                csv.Sniffer().sniff(text, delimiters=delim)
                return delim
            except csv.Error:
                pass
            return delim
    return r"\s+"


def load_xenergy_file(uploaded_file) -> pd.DataFrame:
    """Load X-Energy TXT file (no headers), auto-detect delimiter, drop leading seq column if present."""
    raw = uploaded_file.read().decode("utf-8", errors="replace")
    uploaded_file.seek(0)
    delim = detect_delimiter(raw[:4096])

    if delim == r"\s+":
        df = pd.read_csv(io.StringIO(raw), sep=r"\s+", header=None, engine="python")
    else:
        df = pd.read_csv(io.StringIO(raw), sep=delim, header=None, engine="python")

    # If 14 columns → leading sequence number, drop it
    if len(df.columns) == 14:
        df = df.iloc[:, 1:]
        df.columns = range(len(df.columns))

    # Ensure we have exactly 13 columns
    if len(df.columns) < len(XENERGY_COLUMNS):
        for i in range(len(df.columns), len(XENERGY_COLUMNS)):
            df[i] = pd.NA
    elif len(df.columns) > len(XENERGY_COLUMNS):
        df = df.iloc[:, :len(XENERGY_COLUMNS)]

    df.columns = XENERGY_COLUMNS

    # Convert numeric columns
    for col in ["Coord_X", "Coord_Y", "Coord_Z", "Hole_Length", "Subdrill",
                "Burden", "Spacing", "Diameter", "Stemming", "Density_1", "Density_2"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Hole_ID"] = df["Hole_ID"].astype(str).str.strip()

    return df


def load_prof_file(uploaded_file) -> pd.DataFrame:
    """Load ES_PROF input file (with headers, Excel/CSV/TXT). Needs at least Hole Name, X, Y columns."""
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        sample = uploaded_file.read(8192).decode(errors="replace")
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        except Exception:
            uploaded_file.seek(0)
            if sample.count("\t") > sample.count(","):
                df = pd.read_csv(uploaded_file, sep="\t")
            else:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file)

    return df


def reverse_hole_id(numeric_id: str) -> str:
    """
    Reverse the ES_PROF transform_pozo encoding:
    10000000 + n → B/P + n (we'll resolve B vs P later via coordinates)
    20000000 + n → C + n
    Plain number → D + n (or keep as-is if small)
    """
    s = str(numeric_id).strip()
    if not s or not s.isdigit():
        return s

    num = int(s)
    if num >= 20000000:
        return f"C{num - 20000000}"
    elif num >= 10000000:
        # Could be B or P — mark as B for now, resolve later
        return f"B{num - 10000000}"
    else:
        # Could be D or original number
        return f"D{num}"


def get_letter_prefix(name: str) -> str:
    """Extract the letter prefix from a hole name like B15, C3, D18, P120."""
    m = re.match(r"^([A-Za-z]+)", str(name).strip())
    return m.group(1).upper() if m else ""


def get_hole_number(name: str) -> str:
    """Extract the numeric part from a hole name."""
    m = re.match(r"^[A-Za-z]*(\d+)$", str(name).strip())
    return m.group(1) if m else str(name).strip()


# ==========================================================
# PAGE HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — PROF Reverse</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;color:gray;'>Restore original hole names in X-Energy export files using the original PROF input.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

if st.button("⬅️ Back to Menu", key="back_prof_reverse"):
    st.session_state.page = "dashboard"
    st.rerun()

# ==========================================================
# FILE UPLOADS
# ==========================================================
col_up1, col_up2 = st.columns(2)

with col_up1:
    st.markdown("**📤 Original PROF Input File**")
    st.caption("The file with original hole names (B15, C3, D18, P120...)")
    prof_file = st.file_uploader(
        "Upload PROF file",
        type=["xlsx", "xls", "csv", "txt"],
        key="prof_reverse_prof",
    )

with col_up2:
    st.markdown("**📤 X-Energy Export File**")
    st.caption("TXT exported from X-Energy app (no headers)")
    xenergy_file = st.file_uploader(
        "Upload X-Energy file",
        type=["txt", "csv", "tsv"],
        key="prof_reverse_xenergy",
    )

if not prof_file or not xenergy_file:
    st.info("📂 Please upload both files to begin.")
    st.stop()

# ==========================================================
# LOAD FILES
# ==========================================================
df_prof = load_prof_file(prof_file)
df_xe = load_xenergy_file(xenergy_file)

st.success(f"✅ PROF file: {len(df_prof)} rows | X-Energy file: {len(df_xe)} rows")

# ==========================================================
# BUILD COORDINATE LOOKUP FROM PROF FILE
# ==========================================================
# The PROF input has columns by position: A=Hole Name, B=X, C=Y
prof_cols = df_prof.columns.tolist()
if len(prof_cols) < 3:
    st.error("❌ PROF file needs at least 3 columns (Hole Name, X, Y).")
    st.stop()

col_name_prof = prof_cols[0]  # Original hole name (B15, C3, etc.)
col_x_prof = prof_cols[1]     # Coord Este/X
col_y_prof = prof_cols[2]     # Coord Norte/Y

df_prof["_orig_name"] = df_prof[col_name_prof].astype(str).str.strip().str.upper()
df_prof["_x"] = pd.to_numeric(df_prof[col_x_prof], errors="coerce")
df_prof["_y"] = pd.to_numeric(df_prof[col_y_prof], errors="coerce")
df_prof = df_prof.dropna(subset=["_x", "_y"])

# Build lookup: (rounded X, rounded Y) → original name
# Round to 1 decimal for matching tolerance
coord_lookup = {}
for _, row in df_prof.iterrows():
    key = (round(row["_x"], 1), round(row["_y"], 1))
    coord_lookup[key] = row["_orig_name"]

st.info(f"🔑 Built coordinate lookup with {len(coord_lookup)} unique positions from PROF file.")

# ==========================================================
# RESTORE ORIGINAL HOLE NAMES
# ==========================================================
restored_names = []
match_method = []

for _, row in df_xe.iterrows():
    x_val = row["Coord_X"]
    y_val = row["Coord_Y"]
    numeric_id = str(row["Hole_ID"]).strip()

    # Try coordinate match first (most reliable)
    key = (round(x_val, 1), round(y_val, 1))
    if key in coord_lookup:
        restored_names.append(coord_lookup[key])
        match_method.append("coord")
    else:
        # Try nearby coordinates (tolerance ±0.5)
        found = False
        for dx in [-0.1, 0.0, 0.1, -0.2, 0.2, -0.5, 0.5]:
            for dy in [-0.1, 0.0, 0.1, -0.2, 0.2, -0.5, 0.5]:
                alt_key = (round(x_val + dx, 1), round(y_val + dy, 1))
                if alt_key in coord_lookup:
                    restored_names.append(coord_lookup[alt_key])
                    match_method.append("coord_fuzzy")
                    found = True
                    break
            if found:
                break

        if not found:
            # Fallback: reverse the numeric encoding
            fallback = reverse_hole_id(numeric_id)
            restored_names.append(fallback)
            match_method.append("numeric_reverse")

df_xe["Original_Name"] = restored_names
df_xe["_match_method"] = match_method

# ==========================================================
# APPLY DENSITY RULES
# ==========================================================
for idx, row in df_xe.iterrows():
    prefix = get_letter_prefix(row["Original_Name"])
    if prefix in DENSITY_RULES:
        d1, d2 = DENSITY_RULES[prefix]
        df_xe.at[idx, "Density_1"] = d1
        df_xe.at[idx, "Density_2"] = d2

# Replace Hole_ID with restored original name
df_xe["Hole_ID"] = df_xe["Original_Name"]

# ==========================================================
# BUILD EXPORT
# ==========================================================
export_df = df_xe[XENERGY_COLUMNS].copy()

st.markdown("---")
st.subheader("📋 Result Preview")
st.dataframe(export_df.head(30), use_container_width=True, hide_index=True)

# Match statistics
n_coord = sum(1 for m in match_method if m == "coord")
n_fuzzy = sum(1 for m in match_method if m == "coord_fuzzy")
n_fallback = sum(1 for m in match_method if m == "numeric_reverse")
st.info(
    f"🎯 Matching: **{n_coord}** exact coord | **{n_fuzzy}** fuzzy coord | "
    f"**{n_fallback}** numeric reverse (no coord match)"
)

# ==========================================================
# QUALITY CHECK
# ==========================================================
st.markdown("---")
st.subheader("🔍 Quality Check")

if st.button("▶️ Run Quality Check", use_container_width=True, key="prof_rev_qc"):
    issues = []

    # Check 1: Hole names have correct letter prefix
    for idx, row in export_df.iterrows():
        name = str(row["Hole_ID"]).strip().upper()
        prefix = get_letter_prefix(name)
        d1 = row["Density_1"]
        d2 = row["Density_2"]

        if prefix == "B":
            if d1 != 0.8 or d2 != 0.8:
                issues.append(f"Row {idx}: Hole **{name}** (B) should have density 0.8/0.8 but has {d1}/{d2}")
        elif prefix == "C":
            if d1 != 0.9 or d2 != 0.9:
                issues.append(f"Row {idx}: Hole **{name}** (C) should have density 0.9/0.9 but has {d1}/{d2}")

    # Check 2: Holes that couldn't be matched by coordinates
    if n_fallback > 0:
        fallback_names = df_xe[df_xe["_match_method"] == "numeric_reverse"]["Original_Name"].tolist()
        issues.append(
            f"⚠️ **{n_fallback}** hole(s) could not be matched by coordinates "
            f"(used numeric reverse instead): {fallback_names[:10]}{'...' if len(fallback_names) > 10 else ''}"
        )

    # Check 3: Holes without letter prefix
    no_letter = export_df[export_df["Hole_ID"].apply(lambda x: get_letter_prefix(str(x)) == "")]
    if len(no_letter) > 0:
        issues.append(f"⚠️ **{len(no_letter)}** hole(s) have no letter prefix in their name.")

    if not issues:
        st.success("✅ All hole names correctly restored and densities match their prefix rules.")
    else:
        st.warning(f"⚠️ Found {len(issues)} issue(s):")
        for issue in issues[:30]:
            st.markdown(f"- {issue}")

# ==========================================================
# EXPORT
# ==========================================================
st.markdown("---")
st.subheader("💾 Export")

excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

txt_buffer = io.StringIO()
export_df.to_csv(txt_buffer, sep="\t", index=False, header=False)

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📘 Download Excel (with headers)",
        excel_buffer,
        file_name="ES_PROF_Reverse.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with col2:
    st.download_button(
        "📄 Download TXT (no headers)",
        txt_buffer.getvalue(),
        file_name="ES_PROF_Reverse.txt",
        mime="text/plain",
        use_container_width=True,
    )

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi")
