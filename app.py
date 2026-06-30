import streamlit as st
import os
import json
import shutil
import time
from typing import Optional
from transform import run_pipeline

# Page Configuration
st.set_page_config(
    page_title="Candidate Profile Transformer",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium CSS Styling
st.markdown("""
<style>
    /* Main layout and background */
    .stApp {
        background: linear-gradient(135deg, #0d120e 0%, #151e18 50%, #0d120e 100%);
        color: #e2e8f0;
    }
    
    /* Headers and titles */
    h1, h2, h3 {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 700;
        background: linear-gradient(90deg, #b8c7b4 0%, #839b8b 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: rgba(13, 18, 14, 0.95);
        border-right: 1px solid rgba(131, 155, 139, 0.2);
    }
    
    /* Card or Glassmorphism container */
    .glass-card {
        background: rgba(21, 30, 24, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(131, 155, 139, 0.15);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
    }
    
    /* Customized buttons */
    .stButton>button {
        background: linear-gradient(90deg, #44564c 0%, #5d7265 100%) !important;
        color: #f1f5f9 !important;
        border: 1px solid rgba(184, 199, 180, 0.3) !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(68, 86, 76, 0.4) !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(68, 86, 76, 0.6) !important;
        border-color: rgba(184, 199, 180, 0.6) !important;
    }
    
    /* Metric styling */
    [data-testid="stMetricValue"] {
        font-family: 'Outfit', sans-serif;
        color: #839b8b !important;
        font-size: 36px;
        font-weight: 700;
    }
    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# Title Header
st.title("🤖 Candidate Data Transformer")
st.markdown("Ingest messy recruitment files, merge candidate profiles, and project canonical JSONs in real time.")

# Setup temporary upload directory
TEMP_DIR = os.path.join(os.getcwd(), "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

if "session_id" not in st.session_state:
    import uuid
    st.session_state["session_id"] = str(uuid.uuid4())
session_id = st.session_state["session_id"]

def safe_cleanup_temp_dir(temp_dir: str):
    if not os.path.exists(temp_dir):
        return
    # Clean up folders older than 1 hour (3600 seconds)
    now = time.time()
    for item in os.listdir(temp_dir):
        item_path = os.path.join(temp_dir, item)
        if os.path.isdir(item_path):
            try:
                mtime = os.path.getmtime(item_path)
                if now - mtime > 3600:
                    shutil.rmtree(item_path)
            except Exception:
                pass

# Clean up older uploads once when rendering
safe_cleanup_temp_dir(TEMP_DIR)

def save_uploaded_file(uploaded_file, target_dir: str, index: Optional[int] = None) -> Optional[str]:
    if uploaded_file is None:
        return None
    prefix = f"{index}_" if index is not None else ""
    file_path = os.path.join(target_dir, f"{prefix}{uploaded_file.name}")
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

# Layout with two columns
col1, col2 = st.columns([1, 1.2], gap="large")

with col1:
    st.subheader("📥 Ingest Messy Sources")
    
    with st.container(border=True):
        # File Uploaders
        csv_file = st.file_uploader("Upload Recruiter CSV", type=["csv"], help="Fields: name, email, phone, current_company, title")
        ats_file = st.file_uploader("Upload ATS JSON", type=["json"], help="Structured applicant exports with custom field mappings")
        resume_files = st.file_uploader("Upload Resumes (PDF / DOCX)", type=["pdf", "docx"], accept_multiple_files=True, help="Raw text resumes to parse sections, skills, and dates")
        
        # Import parser
        from sources.pdf_parser import parse_resume
        
        # Parse uploaded resumes to get candidate names
        temp_candidate_info = []
        if resume_files:
            render_dir = os.path.join(TEMP_DIR, "render_" + session_id)
            os.makedirs(render_dir, exist_ok=True)
            for idx, r_file in enumerate(resume_files):
                p = save_uploaded_file(r_file, render_dir, index=idx)
                if p:
                    try:
                        cand = parse_resume(p)
                        name = cand.get("full_name") or r_file.name
                        email = cand.get("emails")[0] if cand.get("emails") else None
                        temp_candidate_info.append({"name": name, "email": email})
                    except Exception:
                        temp_candidate_info.append({"name": r_file.name, "email": None})

        # GitHub input
        github_source = ""
        if temp_candidate_info:
            st.markdown("**GitHub profiles for candidates:**")
            github_inputs = []
            for cand in temp_candidate_info:
                label = f"GitHub for {cand['name']}"
                val = st.text_input(label, key=f"gh_{cand['name']}_{cand['email']}", placeholder="username or profile URL")
                if val.strip():
                    if cand['email']:
                        github_inputs.append(f"{val.strip()}:{cand['email']}")
                    else:
                        github_inputs.append(val.strip())
            github_source = ", ".join(github_inputs)
        else:
            github_source = st.text_input("GitHub Username or URL", placeholder="e.g., https://github.com/vishhneww", help="Fetches public profile, top starred repos, and programming languages")
        
    st.subheader("⚙️ Output Configuration")
    with st.container(border=True):
        config_option = st.selectbox(
            "Select Output Config",
            ["config/default.json", "config/minimal.json"],
            format_func=lambda x: "Default Schema (Full Profile + Metadata)" if "default" in x else "Minimal Schema (Name, Email, Skills Only)"
        )
        
        run_btn = st.button("🚀 Run Pipeline", use_container_width=True)

# Process Pipeline
if run_btn:
    import uuid
    run_id = str(uuid.uuid4())
    run_dir = os.path.join(TEMP_DIR, "run_" + run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    # Save files to temp directory
    csv_path = save_uploaded_file(csv_file, run_dir)
    ats_path = save_uploaded_file(ats_file, run_dir)
    
    resume_paths = []
    if resume_files:
        for idx, r_file in enumerate(resume_files):
            p = save_uploaded_file(r_file, run_dir, index=idx)
            if p:
                resume_paths.append(p)
                
    # Check if at least one source is provided
    if not any([csv_path, ats_path, github_source, resume_paths]):
        st.error("Please provide at least one candidate data source (file or GitHub).")
    else:
        with st.container():
            try:
                # Show visual progress bar for execution stages
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                
                stages = [
                    ("Uploading...", 0.1),
                    ("Parsing...", 0.3),
                    ("Normalizing...", 0.5),
                    ("Merging...", 0.7),
                    ("Scoring...", 0.9),
                    ("Generating JSON...", 1.0)
                ]
                
                for stage_name, progress_val in stages:
                    status_text.text(f"Current stage: {stage_name}")
                    progress_bar.progress(progress_val)
                    time.sleep(0.15)
                    
                status_text.empty()
                progress_bar.empty()

                # Run the pipeline
                summary, profiles = run_pipeline(
                    csv_path=csv_path,
                    ats_path=ats_path,
                    github_source=github_source if github_source.strip() else None,
                    resume_path=resume_paths,
                    config_path=config_option,
                    output_dir="output/"
                )
                
                # Success display in col2
                with col2:
                    st.success("Pipeline executed successfully!")
                    
                    # Output JSON Files
                    st.subheader("📄 Candidate Profiles")
                    
                    for p in profiles:
                        cid = p.get("candidate_id")
                        cname = p.get("full_name", "Unknown Candidate")
                        
                        # Load canonical profile to extract sources and metrics
                        canonical_path = os.path.join("output", f"canonical_{cid}.json")
                        sources_contrib = []
                        overall_conf = 0.0
                        
                        if os.path.exists(canonical_path):
                            with open(canonical_path, "r", encoding="utf-8") as cf:
                                canonical_data = json.load(cf)
                                sources_contrib = list(set(entry["source"] for entry in canonical_data.get("provenance", []) if entry["source"] != "none"))
                                overall_conf = canonical_data.get("overall_confidence", 0.0)
                        else:
                            overall_conf = p.get("overall_confidence", 0.0)
                            
                        # Render Card
                        with st.container():
                            st.markdown(f"""
                            <div class="glass-card">
                                <h4 style="margin: 0 0 10px 0; color: #b8c7b4;">👤 {cname}</h4>
                                <p style="margin: 0; font-size: 14px; color: #a3b899;">
                                    <b>Overall Confidence:</b> <span style="color: #839b8b; font-weight: 600;">{overall_conf:.3f}</span> | 
                                    <b>Sources Used:</b> {", ".join([f"`{s}`" for s in sources_contrib]) if sources_contrib else "`N/A`"}
                                </p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            with st.expander("👁️ View JSON", expanded=False):
                                st.json(p)
                                
            except Exception as e:
                st.error(f"Pipeline Execution Failed: {str(e)}")
            finally:
                # Cleanup only this run's temp directory to avoid race conditions
                try:
                    shutil.rmtree(run_dir)
                except Exception:
                    pass
else:
    with col2:
        st.subheader("📊 Execution Results")
        st.info("Upload candidate sources in the left panel and click 'Run Pipeline' to view transformed profiles.")
        
        # Display existing sample output if available
        sample_path = "output/sample_default.json"
        if os.path.exists(sample_path):
            with st.expander("👀 View Current Sample Profile", expanded=False):
                with open(sample_path, "r", encoding="utf-8") as sf:
                    st.json(json.load(sf))
