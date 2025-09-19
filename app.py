import streamlit as st
import pandas as pd
import numpy as np
import io
from fuzzywuzzy import process

# --- Helper Functions ---

def find_column(df, possible_names):
    """Find the best matching column name in df for any of the possible_names."""
    cols = df.columns.tolist()
    match, score = process.extractOne(possible_names[0], cols)
    if score > 90:
        return match
    for name in possible_names:
        match, score = process.extractOne(name, cols)
        if score > 80:
            return match
    # Try partial matches
    for name in possible_names:
        for col in cols:
            if name.lower() in col.lower():
                return col
    return None

def get_style_column(df):
    style_names = ["Style", "Style #", "Style No", "Style number", "Style code", "Style ID"]
    return find_column(df, style_names)

def get_customer_dept_column(df):
    cust_names = ["Customer department", "Customer Dept", "Customer", "Department", "Cust Dept"]
    return find_column(df, cust_names)

def join_on_style_and_customer(user_df, ref_df, style_col, cust_col, ref_style_col, ref_cust_col):
    merged = pd.merge(
        user_df,
        ref_df[[ref_style_col, ref_cust_col, "LatestSubChassis"]],
        left_on=[style_col, cust_col],
        right_on=[ref_style_col, ref_cust_col],
        how="left"
    )
    # Move LatestSubChassis to last column
    cols = [c for c in merged.columns if c != "LatestSubChassis"] + ["LatestSubChassis"]
    return merged[cols]

# --- Streamlit App ---

st.set_page_config(page_title="Subchassis Mapping Tool", layout="wide")

st.title("Subchassis Mapping Tool")

# --- Admin Upload Section ---
st.sidebar.header("Admin: Upload Reference Table")
admin_user = st.sidebar.text_input("Admin Username")
admin_pass = st.sidebar.text_input("Admin Password", type="password")
admin_uploaded = st.sidebar.file_uploader("Upload Subchassis Reference Table (.xlsx)", type=["xlsx"], key="admin")

if admin_user and admin_pass and admin_uploaded:
    # In production, validate username/password securely!
    ref_df = pd.read_excel(admin_uploaded)
    st.sidebar.success("Reference table uploaded and stored for this session.")
    st.session_state['ref_df'] = ref_df
else:
    ref_df = st.session_state.get('ref_df', None)

# --- User Upload Section ---
st.header("User: Upload Your Dynamic Excel File")
user_uploaded = st.file_uploader("Upload your Excel file (.xlsx)", type=["xlsx"], key="user")

if user_uploaded and ref_df is not None:
    user_df = pd.read_excel(user_uploaded)
    # Flexible column extraction
    style_col = get_style_column(user_df)
    cust_col = get_customer_dept_column(user_df)
    ref_style_col = get_style_column(ref_df)
    ref_cust_col = get_customer_dept_column(ref_df)

    if not style_col or not cust_col or not ref_style_col or not ref_cust_col:
        st.error("Could not find Style or Customer Department columns in one of the files. Please check your files and try again.")
    else:
        st.info(f"Using columns: User file [{style_col}, {cust_col}], Reference file [{ref_style_col}, {ref_cust_col}]")
        result_df = join_on_style_and_customer(user_df, ref_df, style_col, cust_col, ref_style_col, ref_cust_col)
        st.success("Mapping complete! Preview below:")
        st.dataframe(result_df.head(50))

        # Download button
        towrite = io.BytesIO()
        result_df.to_excel(towrite, index=False)
        towrite.seek(0)
        st.download_button(
            label="Download Compiled Excel",
            data=towrite,
            file_name="compiled_subchassis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    if user_uploaded and ref_df is None:
        st.warning("Admin must upload the reference table first.")

st.markdown("---")
st.markdown("**Instructions:**\n"
            "1. Admin uploads the standard Subchassis reference table (one-time per session).\n"
            "2. User uploads their dynamic Excel file.\n"
            "3. The tool will map and append the `LatestSubChassis` column based on Style and Customer Department.\n"
            "4. Download the compiled Excel file.")

