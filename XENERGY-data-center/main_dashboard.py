import streamlit as st
import importlib.util
from pathlib import Path

# ==========================================================
# PAGE CONFIGURATION
# ==========================================================
st.set_page_config(
    page_title="MAXAM Data Process Center",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================================
# HIDE DEFAULT STREAMLIT UI ELEMENTS
# ==========================================================
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================================
# SESSION STATE INITIALIZATION
# ==========================================================
if "page" not in st.session_state:
    st.session_state.page = "dashboard"

# ==========================================================
# HEADER BANNER IMAGE (FULL-WIDTH FACEBOOK-STYLE)
# ==========================================================
st.markdown(
    """
    <style>
        .banner-container {
            width: 100%;
            height: 250px; /* adjust for taller or shorter look */
            overflow: hidden;
            border-radius: 10px;
            margin-bottom: 25px;
        }
        .banner-container img {
            width: 100%;
            height: 100%;
            object-fit: cover;  /* fills horizontally without distortion */
            object-position: center; /* keeps the main part of the image centered */
        }
    </style>

    <div class="banner-container">
        <img src="https://raw.githubusercontent.com/AkeraX6/XENERGY-data-center/main/XENERGY-data-center/Cover.png" alt="MAXAM Data Process Center Banner">
    </div>
    """,
    unsafe_allow_html=True
)

# ==========================================================
# PAGE: DASHBOARD
# ==========================================================
def dashboard_page():
    st.markdown(
        """
        <hr style='margin-top: 10px; margin-bottom: 25px;'>
        """,
        unsafe_allow_html=True
    )

    st.subheader("🚩 Select Processing Module :")

    mine = st.selectbox("Select Mine", ["Select...", "DGM", "Escondida", "Mantos Blancos"])
    file_type = st.selectbox(
        "Select File Type",
        ["Select...", "Drilling", "QAQC", "Fragmentation", "Excavation", "Shovle Position"]
    )

    proceed_button = st.button("🚀 Proceed", use_container_width=True)

    if proceed_button:
        if mine == "Select..." or file_type == "Select...":
            st.warning("⚠️ Please select both Mine and File Type before proceeding.")
        else:
            mine_codes = {"DGM": "DGM", "Escondida": "ES", "Mantos Blancos": "MB"}
            file_codes = {
                "Drilling": "AUTO",
                "QAQC": "QAQC",
                "Fragmentation": "FRAG",
                "Excavation": "EXCA",
                "Shovle Position": "POSP"
            }

            mine_code = mine_codes[mine]
            file_code = file_codes[file_type]

            # Save selected module name in session
            st.session_state.selected_module = f"{mine_code}_{file_code}.py"
            st.session_state.page = "module"
            st.rerun()

# ==========================================================
# PAGE: MODULE EXECUTION
# ==========================================================
def module_page():
    pages_dir = Path(__file__).parent / "pages"
    module_name = st.session_state.selected_module
    module_path = pages_dir / module_name

    # Header with Back button
    col1, col2 = st.columns([0.15, 0.85])
    with col1:
        if st.button("⬅️ Back to Menu"):
            st.session_state.page = "dashboard"
            st.rerun()
    with col2:
        st.markdown(f"### ⚙️ Loaded Module: `{module_name}`")

    # Check file existence
    if not module_path.exists():
        st.error(f"❌ The file `{module_name}` was not found in `/pages` folder.")
        return

    # Load and execute selected module inline
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

# ==========================================================
# NAVIGATION LOGIC
# ==========================================================
if st.session_state.page == "dashboard":
    dashboard_page()
else:
    module_page()













