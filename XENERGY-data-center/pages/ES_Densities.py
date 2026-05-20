import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import io
import csv
from datetime import datetime

# ==========================================================
# COLUMN DEFINITIONS
# ==========================================================
COLUMN_NAMES = [
    "Blast_Name", "Hole_ID", "Coord_Este", "Coord_Norte", "Collar_Z",
    "Length", "Subdrill_Length", "Burden", "Spacing", "Drill_Rig",
    "Diameter_or_Dip", "Original_Density", "Extra"
]

# Default color palette for density values
DENSITY_OPTIONS = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.33, 1.35, 1.40]

DENSITY_COLORS = {
    0.80: "#00C853",  # bright green
    0.85: "#76FF03",  # lime green
    0.90: "#C6FF00",  # yellow-green
    0.95: "#FFD600",  # gold / yellow
    1.00: "#FF9100",  # orange
    1.05: "#FF3D00",  # red-orange
    1.10: "#D50000",  # red
    1.15: "#AA00FF",  # purple
    1.20: "#2962FF",  # blue
    1.25: "#00B0FF",  # light blue
    1.30: "#795548",  # brown
    1.33: "#00695C",  # teal
    1.35: "#78909C",  # blue-gray
    1.40: "#37474F",  # dark gray
}

# ==========================================================
# HEADER
# ==========================================================
st.markdown(
    "<h2 style='text-align:center;'>Escondida — Density Editor</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;color:gray;'>Visualize, edit, and export drill hole density data interactively.</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# Back to Menu
if st.button("⬅️ Back to Menu", key="back_densities"):
    st.session_state.page = "dashboard"
    st.rerun()


# ==========================================================
# HELPERS
# ==========================================================
def detect_delimiter(text: str) -> str:
    """Detect the most likely delimiter from a text sample."""
    for delim in ["\t", ";", ","]:
        if delim in text:
            try:
                dialect = csv.Sniffer().sniff(text, delimiters=delim)
                return dialect.delimiter
            except csv.Error:
                pass
            return delim
    return r"\s+"


def load_file(uploaded_file) -> tuple[pd.DataFrame, str]:
    """Read an uploaded file with auto-detected delimiter. Returns (df, delimiter)."""
    raw = uploaded_file.read().decode("utf-8", errors="replace")
    uploaded_file.seek(0)
    delim = detect_delimiter(raw[:4096])

    if delim == r"\s+":
        df = pd.read_csv(io.StringIO(raw), sep=r"\s+", header=None, engine="python")
    else:
        df = pd.read_csv(io.StringIO(raw), sep=delim, header=None, engine="python")

    # 14-column files have a leading sequence/row number — drop it
    if len(df.columns) == 14:
        df = df.iloc[:, 1:]  # drop first column (sequence number)
        df.columns = range(len(df.columns))

    if len(df.columns) < len(COLUMN_NAMES):
        # Pad with NaN if fewer columns
        for i in range(len(df.columns), len(COLUMN_NAMES)):
            df[i] = pd.NA
    elif len(df.columns) > len(COLUMN_NAMES):
        df = df.iloc[:, :len(COLUMN_NAMES)]

    df.columns = COLUMN_NAMES

    # Convert types
    for col in ["Coord_Este", "Coord_Norte", "Collar_Z", "Length",
                 "Subdrill_Length", "Burden", "Spacing", "Diameter_or_Dip", "Original_Density"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Extra"] = pd.to_numeric(df["Extra"], errors="coerce")

    # New_Density starts as a copy of Original_Density (editable column)
    df["New_Density"] = df["Original_Density"].copy()

    return df, delim


def get_color_map(densities: list, custom_colors: dict) -> dict:
    """Return a density → color mapping, using fixed DENSITY_COLORS."""
    color_map = {}
    for d in sorted(densities):
        key = str(d)
        if key in custom_colors:
            color_map[d] = custom_colors[key]
        elif d in DENSITY_COLORS:
            color_map[d] = DENSITY_COLORS[d]
        else:
            # For unexpected density values, pick a fallback
            color_map[d] = "#888888"
    return color_map


def build_figure(df: pd.DataFrame, color_map: dict) -> go.Figure:
    """Build a Plotly scatter figure colored by New_Density. Stars for Mineral, dots for Lastre."""
    fig = go.Figure()

    for density_val in sorted(df["New_Density"].dropna().unique()):
        sub = df[df["New_Density"] == density_val]
        color = color_map.get(density_val, "#888888")

        # Split by material type: Mineral (Extra==1) = star, Lastre (Extra==2) = circle
        mineral = sub[sub["Extra"] == 1]
        lastre = sub[sub["Extra"] != 1]

        if len(lastre) > 0:
            fig.add_trace(go.Scatter(
                x=lastre["Coord_Este"],
                y=lastre["Coord_Norte"],
                mode="markers",
                name=f"Density {density_val}",
                legendgroup=f"d_{density_val}",
                marker=dict(size=7, symbol="circle", color=color, line=dict(width=0.5, color="#333")),
                customdata=lastre[["Hole_ID", "Blast_Name", "Original_Density", "New_Density"]].values,
                hovertemplate=(
                    "<b>Hole:</b> %{customdata[0]}<br>"
                    "<b>Blast:</b> %{customdata[1]}<br>"
                    "<b>Este:</b> %{x:.1f}<br>"
                    "<b>Norte:</b> %{y:.1f}<br>"
                    "<b>Original:</b> %{customdata[2]}<br>"
                    "<b>Current:</b> %{customdata[3]}<br>"
                    "<b>Type:</b> Lastre<extra></extra>"
                ),
            ))

        if len(mineral) > 0:
            fig.add_trace(go.Scatter(
                x=mineral["Coord_Este"],
                y=mineral["Coord_Norte"],
                mode="markers",
                name=f"Density {density_val} ★",
                legendgroup=f"d_{density_val}",
                marker=dict(size=9, symbol="star", color=color, line=dict(width=0.5, color="#333")),
                customdata=mineral[["Hole_ID", "Blast_Name", "Original_Density", "New_Density"]].values,
                hovertemplate=(
                    "<b>Hole:</b> %{customdata[0]}<br>"
                    "<b>Blast:</b> %{customdata[1]}<br>"
                    "<b>Este:</b> %{x:.1f}<br>"
                    "<b>Norte:</b> %{y:.1f}<br>"
                    "<b>Original:</b> %{customdata[2]}<br>"
                    "<b>Current:</b> %{customdata[3]}<br>"
                    "<b>Type:</b> Mineral<extra></extra>"
                ),
            ))

    fig.update_layout(
        xaxis_title="Coord Este",
        yaxis_title="Coord Norte",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        legend_title="Density",
        margin=dict(l=40, r=20, t=30, b=40),
        height=700,
        dragmode="lasso",
    )
    return fig


def build_material_figure(df: pd.DataFrame) -> go.Figure:
    """Build a read-only scatter colored by material type (Extra column): 1=Lastre, 2=Mineral."""
    MATERIAL_MAP = {1: ("Mineral", "#D50000"), 2: ("Lastre", "#2962FF")}
    fig = go.Figure()

    for val in sorted(df["Extra"].dropna().unique()):
        sub = df[df["Extra"] == val]
        label, color = MATERIAL_MAP.get(int(val), (f"Type {val}", "#888888"))
        fig.add_trace(go.Scatter(
            x=sub["Coord_Este"],
            y=sub["Coord_Norte"],
            mode="markers",
            name=label,
            marker=dict(size=7, color=color, line=dict(width=0.5, color="#333")),
            customdata=sub[["Hole_ID", "Blast_Name"]].values,
            hovertemplate=(
                "<b>Hole:</b> %{customdata[0]}<br>"
                "<b>Blast:</b> %{customdata[1]}<br>"
                "<b>Este:</b> %{x:.1f}<br>"
                "<b>Norte:</b> %{y:.1f}<br>"
                f"<b>Type:</b> {label}<extra></extra>"
            ),
        ))

    fig.update_layout(
        xaxis_title="Coord Este",
        yaxis_title="Coord Norte",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        legend_title="Material",
        margin=dict(l=40, r=20, t=30, b=40),
        height=700,
        dragmode=False,
    )
    return fig


# ==========================================================
# FILE UPLOAD
# ==========================================================
uploaded_file = st.file_uploader(
    "📤 Upload density data file",
    type=["txt", "csv", "tsv"],
)

if uploaded_file is not None:
    # Load only once per file
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("_density_file_key") != file_key:
        df, delim = load_file(uploaded_file)
        st.session_state["_density_file_key"] = file_key
        st.session_state["density_df"] = df.copy()
        st.session_state["density_df_original"] = df.copy()
        st.session_state["density_delim"] = delim
        st.session_state["density_changes"] = []
        st.session_state["density_custom_colors"] = {}

if "density_df" not in st.session_state:
    st.info("📂 Please upload a TXT/CSV file to begin.")
    st.stop()

df = st.session_state["density_df"]
original_df = st.session_state["density_df_original"]
changes_log = st.session_state["density_changes"]
custom_colors = st.session_state["density_custom_colors"]

st.success(f"✅ Loaded {len(df)} holes  |  {df['New_Density'].nunique()} unique density values")

# ==========================================================
# EDITING CONTROLS (in main area — sidebar is hidden)
# ==========================================================

# Initialize target density in session state
if "target_density" not in st.session_state:
    st.session_state["target_density"] = 1.20

# --- Target density selector with colored buttons ---
st.subheader("🎨 Select Target Density")

# Build colored button grid — 7 columns per row
btn_cols = st.columns(7)
for idx, d in enumerate(DENSITY_OPTIONS):
    color = DENSITY_COLORS.get(d, "#888888")
    is_selected = (st.session_state["target_density"] == d)
    border = "3px solid #fff" if is_selected else "1px solid #555"
    bg = color if is_selected else "transparent"
    text_color = "#fff" if is_selected else color
    with btn_cols[idx % 7]:
        st.markdown(
            f"<div style='text-align:center;margin-bottom:2px;'>"
            f"<div style='width:18px;height:18px;border-radius:50%;background:{color};border:{border};"
            f"margin:0 auto;'></div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            f"{'✔ ' if is_selected else ''}{d}",
            key=f"density_btn_{d}",
            use_container_width=True,
        ):
            st.session_state["target_density"] = d
            st.rerun()

target_density = st.session_state["target_density"]
active_color = DENSITY_COLORS.get(target_density, "#888888")
st.markdown(
    f"**Active density:** <span style='color:{active_color};font-size:18px;font-weight:700;'>"
    f"● {target_density}</span>",
    unsafe_allow_html=True,
)

# --- Edit mode + Undo / Reset in one row ---
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
with ctrl_col1:
    edit_mode = st.radio(
        "Edit Mode",
        ["Lasso / Box Select", "Range (X/Y bounds)"],
        index=0,
        horizontal=True,
    )
with ctrl_col2:
    if st.button("↩ Undo Last", use_container_width=True, disabled=len(changes_log) == 0):
        last = changes_log.pop()
        match_mask = df["Hole_ID"].astype(str) == str(last["Hole_ID"])
        df.loc[match_mask, "New_Density"] = last["Old_Density"]
        st.session_state["density_df"] = df
        st.rerun()
with ctrl_col3:
    if st.button("🔄 Reset All", use_container_width=True):
        st.session_state["density_df"] = original_df.copy()
        st.session_state["density_changes"] = []
        st.rerun()

# --- Range inputs (shown only when Range mode is selected) ---
if edit_mode == "Range (X/Y bounds)":
    r1, r2, r3, r4, r5 = st.columns([1, 1, 1, 1, 1])
    with r1:
        x_min = st.number_input("X min", value=float(df["Coord_Este"].min()), format="%.1f")
    with r2:
        x_max = st.number_input("X max", value=float(df["Coord_Este"].max()), format="%.1f")
    with r3:
        y_min = st.number_input("Y min", value=float(df["Coord_Norte"].min()), format="%.1f")
    with r4:
        y_max = st.number_input("Y max", value=float(df["Coord_Norte"].max()), format="%.1f")
    with r5:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Apply Range Edit", use_container_width=True):
            mask = (
                (df["Coord_Este"] >= x_min) & (df["Coord_Este"] <= x_max) &
                (df["Coord_Norte"] >= y_min) & (df["Coord_Norte"] <= y_max) &
                (df["New_Density"] != target_density)
            )
            affected = df.loc[mask]
            if len(affected) > 0:
                for idx_row in affected.index:
                    changes_log.append({
                        "Hole_ID": df.at[idx_row, "Hole_ID"],
                        "Old_Density": df.at[idx_row, "New_Density"],
                        "New_Density": target_density,
                        "Timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                df.loc[mask, "New_Density"] = target_density
                st.session_state["density_df"] = df
                st.success(f"✅ Updated {len(affected)} holes.")
                st.rerun()
            else:
                st.warning("No holes in that range need updating.")

# --- Color map ---
unique_densities = sorted(df["New_Density"].dropna().unique().tolist())
color_map = get_color_map(unique_densities, custom_colors)
with st.expander("🎨 Customize Colors", expanded=False):
    cc_cols = st.columns(min(len(unique_densities), 7) or 1)
    for i, d in enumerate(unique_densities):
        key = str(d)
        current_color = color_map.get(d, "#888888")
        with cc_cols[i % len(cc_cols)]:
            new_color = st.color_picker(f"{d}", value=current_color, key=f"cp_{d}")
            if new_color != current_color:
                custom_colors[key] = new_color
                color_map[d] = new_color

st.markdown("---")

# ==========================================================
# SCATTER PLOTS (Density Editor + Material Reference)
# ==========================================================
graph_left, graph_right = st.columns(2)

fig = build_figure(df, color_map)
fig_material = build_material_figure(df)

with graph_left:
    st.subheader("📊 Density Map (editable)")
    if edit_mode == "Lasso / Box Select":
        event = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode=["points", "box", "lasso"],
            key="density_plot",
        )

        # Process selection
        if event and event.selection and event.selection.points:
            selected_points = event.selection.points
            updated_count = 0

            for pt in selected_points:
                pt_x = pt.get("x")
                pt_y = pt.get("y")
                if pt_x is None or pt_y is None:
                    continue

                mask = (
                    (df["Coord_Este"] == pt_x) &
                    (df["Coord_Norte"] == pt_y) &
                    (df["New_Density"] != target_density)
                )
                affected = df.loc[mask]
                for idx_row in affected.index:
                    changes_log.append({
                        "Hole_ID": df.at[idx_row, "Hole_ID"],
                        "Old_Density": df.at[idx_row, "New_Density"],
                        "New_Density": target_density,
                        "Timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    df.at[idx_row, "New_Density"] = target_density
                    updated_count += 1

            if updated_count > 0:
                st.session_state["density_df"] = df
                st.toast(f"Updated {updated_count} hole(s) to density {target_density}")
                st.rerun()
    else:
        st.plotly_chart(fig, use_container_width=True, key="density_plot_range")

with graph_right:
    st.subheader("🪨 Lastre / Mineral")
    st.plotly_chart(fig_material, use_container_width=True, key="material_plot")

# ==========================================================
# DATA PREVIEW
# ==========================================================
st.subheader("📋 Data Preview")
st.dataframe(df.head(30), use_container_width=True, hide_index=True)

# ==========================================================
# CHANGE LOG
# ==========================================================
with st.expander("📜 Change History", expanded=False):
    if changes_log:
        log_df = pd.DataFrame(changes_log)
        st.dataframe(log_df, use_container_width=True, hide_index=True)
        st.info(f"Total edits: {len(changes_log)}")
    else:
        st.write("No changes yet.")

# ==========================================================
# EXPORT
# ==========================================================
st.markdown("---")
st.subheader("💾 Export Modified Data")

delim = st.session_state.get("density_delim", "\t")
delim_char = delim if delim != r"\s+" else "\t"

# Build export dataframe
export_cols_base = [
    "Blast_Name", "Hole_ID", "Coord_Este", "Coord_Norte", "Collar_Z",
    "Length", "Subdrill_Length", "Burden", "Spacing", "Drill_Rig",
    "Diameter_or_Dip",
]
export_df = df[export_cols_base].copy()

# Convert Hole_ID to numeric for prefix detection
hole_numeric = pd.to_numeric(export_df["Hole_ID"], errors="coerce").fillna(0).astype(int)

# --- Density LB: all 1.3, except 10000000+ → 0.8, 20000000+ → 0.9 ---
export_df["Density LB"] = 1.3
export_df.loc[hole_numeric >= 20000000, "Density LB"] = 0.9
export_df.loc[(hole_numeric >= 10000000) & (hole_numeric < 20000000), "Density LB"] = 0.8

# --- Density XE: keep New_Density (editable), but force 0.8/0.9 for prefix holes ---
export_df["Density XE"] = df["New_Density"].values
export_df.loc[hole_numeric >= 20000000, "Density XE"] = 0.9
export_df.loc[(hole_numeric >= 10000000) & (hole_numeric < 20000000), "Density XE"] = 0.8

# TXT (original format, no header)
txt_buffer = io.StringIO()
export_df.to_csv(txt_buffer, sep=delim_char, index=False, header=False)

# Excel (with headers)
excel_buffer = io.BytesIO()
export_df.to_excel(excel_buffer, index=False, engine="openpyxl")
excel_buffer.seek(0)

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "📄 Download TXT (no header)",
        txt_buffer.getvalue(),
        file_name="ES_Densities_Modified.txt",
        mime="text/plain",
        use_container_width=True,
    )
with col2:
    st.download_button(
        "📘 Download Excel",
        excel_buffer,
        file_name="ES_Densities_Modified.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ==========================================================
# STATISTICS
# ==========================================================
with st.expander("📈 Density Statistics", expanded=False):
    stats = df.groupby("New_Density").agg(
        Count=("Hole_ID", "count"),
        Avg_Este=("Coord_Este", "mean"),
        Avg_Norte=("Coord_Norte", "mean"),
    ).reset_index()
    stats["Avg_Este"] = stats["Avg_Este"].round(1)
    stats["Avg_Norte"] = stats["Avg_Norte"].round(1)
    st.dataframe(stats, use_container_width=True, hide_index=True)

    # Count changes
    if changes_log:
        changed_holes = len(set(c["Hole_ID"] for c in changes_log))
        st.markdown(f"**Holes modified:** {changed_holes} / {len(df)}")

# ==========================================================
# REVERSE SECTION — Restore Original Hole Names
# ==========================================================
st.markdown("---")
st.subheader("🔄 Download with Original Hole Names")
st.caption("Upload the same PROF input file (with original names like B15, C3, D18, P120) to restore hole IDs by coordinate matching.")

prof_reverse_file = st.file_uploader(
    "📤 Upload original PROF input file",
    type=["xlsx", "xls", "csv", "txt"],
    key="density_prof_reverse",
)

if prof_reverse_file is not None:
    # Load PROF file
    prof_name = prof_reverse_file.name.lower()
    if prof_name.endswith((".xlsx", ".xls")):
        df_prof = pd.read_excel(prof_reverse_file)
    else:
        sample = prof_reverse_file.read(8192).decode(errors="replace")
        prof_reverse_file.seek(0)
        try:
            df_prof = pd.read_csv(prof_reverse_file, sep=None, engine="python")
        except Exception:
            prof_reverse_file.seek(0)
            if sample.count("\t") > sample.count(","):
                df_prof = pd.read_csv(prof_reverse_file, sep="\t")
            else:
                prof_reverse_file.seek(0)
                df_prof = pd.read_csv(prof_reverse_file)

    prof_cols = df_prof.columns.tolist()
    if len(prof_cols) < 3:
        st.error("❌ PROF file needs at least 3 columns (Hole Name, X, Y).")
    else:
        # Columns by position: A=Hole Name, B=X (Este), C=Y (Norte)
        col_name_prof = prof_cols[0]
        col_x_prof = prof_cols[1]
        col_y_prof = prof_cols[2]

        df_prof["_orig_name"] = df_prof[col_name_prof].astype(str).str.strip().str.upper()
        df_prof["_x"] = pd.to_numeric(df_prof[col_x_prof], errors="coerce")
        df_prof["_y"] = pd.to_numeric(df_prof[col_y_prof], errors="coerce")
        df_prof = df_prof.dropna(subset=["_x", "_y"])

        # Build coordinate lookup: (rounded X, rounded Y) → original name
        coord_lookup = {}
        for _, row in df_prof.iterrows():
            key = (round(row["_x"], 1), round(row["_y"], 1))
            coord_lookup[key] = row["_orig_name"]

        st.info(f"🔑 Loaded {len(coord_lookup)} holes from PROF file for coordinate matching.")

        # Match each hole in the density data by coordinates
        reversed_ids = []
        match_stats = {"exact": 0, "fuzzy": 0, "unmatched": 0}

        for _, row in df.iterrows():
            x_val = row["Coord_Este"]
            y_val = row["Coord_Norte"]

            # Exact match
            key = (round(x_val, 1), round(y_val, 1))
            if key in coord_lookup:
                reversed_ids.append(coord_lookup[key])
                match_stats["exact"] += 1
            else:
                # Fuzzy match (±0.5)
                found = False
                for dx in [0.0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.5, 0.5]:
                    for dy in [0.0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.5, 0.5]:
                        alt_key = (round(x_val + dx, 1), round(y_val + dy, 1))
                        if alt_key in coord_lookup:
                            reversed_ids.append(coord_lookup[alt_key])
                            match_stats["fuzzy"] += 1
                            found = True
                            break
                    if found:
                        break
                if not found:
                    # Keep numeric ID as fallback
                    reversed_ids.append(str(row["Hole_ID"]))
                    match_stats["unmatched"] += 1

        # Build reversed export (same columns as density export but with original names)
        rev_export = export_df.copy()
        rev_export["Hole_ID"] = reversed_ids

        st.success(
            f"✅ Matched: **{match_stats['exact']}** exact | "
            f"**{match_stats['fuzzy']}** fuzzy | "
            f"**{match_stats['unmatched']}** unmatched (kept numeric ID)"
        )

        st.dataframe(rev_export.head(20), use_container_width=True, hide_index=True)

        # Export reversed file
        rev_txt_buffer = io.StringIO()
        rev_export.to_csv(rev_txt_buffer, sep=delim_char, index=False, header=False)

        rev_excel_buffer = io.BytesIO()
        rev_export.to_excel(rev_excel_buffer, index=False, engine="openpyxl")
        rev_excel_buffer.seek(0)

        rev_col1, rev_col2 = st.columns(2)
        with rev_col1:
            st.download_button(
                "📄 Download Reversed TXT (no header)",
                rev_txt_buffer.getvalue(),
                file_name="ES_Densities_Reversed.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with rev_col2:
            st.download_button(
                "📘 Download Reversed Excel",
                rev_excel_buffer,
                file_name="ES_Densities_Reversed.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi")



