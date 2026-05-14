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
    0.80: "#1f77b4",  # blue
    0.85: "#17becf",  # cyan
    0.90: "#2ca02c",  # green
    0.95: "#98df8a",  # light green
    1.00: "#bcbd22",  # olive
    1.05: "#ff7f0e",  # orange
    1.10: "#ffbb78",  # light orange
    1.15: "#d62728",  # red
    1.20: "#9467bd",  # purple
    1.25: "#e377c2",  # pink
    1.30: "#8c564b",  # brown
    1.33: "#636EFA",  # indigo
    1.35: "#EF553B",  # coral
    1.40: "#7f7f7f",  # gray
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
    """Build a Plotly scatter figure colored by New_Density."""
    fig = go.Figure()

    for density_val in sorted(df["New_Density"].dropna().unique()):
        sub = df[df["New_Density"] == density_val]
        color = color_map.get(density_val, "#888888")
        fig.add_trace(go.Scatter(
            x=sub["Coord_Este"],
            y=sub["Coord_Norte"],
            mode="markers",
            name=f"Density {density_val}",
            marker=dict(size=7, color=color, line=dict(width=0.5, color="#333")),
            customdata=sub[["Hole_ID", "Blast_Name", "Original_Density", "New_Density"]].values,
            hovertemplate=(
                "<b>Hole:</b> %{customdata[0]}<br>"
                "<b>Blast:</b> %{customdata[1]}<br>"
                "<b>Este:</b> %{x:.1f}<br>"
                "<b>Norte:</b> %{y:.1f}<br>"
                "<b>Original:</b> %{customdata[2]}<br>"
                "<b>Current:</b> %{customdata[3]}<extra></extra>"
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
# SCATTER PLOT
# ==========================================================
st.subheader("📊 Drill Hole Map")

fig = build_figure(df, color_map)

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
            # Match by coordinates
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

# Build export dataframe: 13 columns matching input layout
# Cols 1-11 unchanged, col 12 = Original_Density, col 13 = New_Density
export_cols = [
    "Blast_Name", "Hole_ID", "Coord_Este", "Coord_Norte", "Collar_Z",
    "Length", "Subdrill_Length", "Burden", "Spacing", "Drill_Rig",
    "Diameter_or_Dip", "Original_Density", "New_Density"
]
export_df = df[export_cols].copy()

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

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built by Maxam - Omar El Kendi")


