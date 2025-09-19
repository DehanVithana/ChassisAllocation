import streamlit as st
import pandas as pd
import io

def find_column_by_keywords(df, keywords):
    """Finds a column in the dataframe that matches a list of keywords."""
    for col in df.columns:
        for keyword in keywords:
            if keyword in col.lower():
                return col
    return None

def process_files(user_df, subchassis_df):
    """
    Processes the user and subchassis dataframes to map the 'LatestSubChassis' column.
    """
    # Define keywords to find the necessary columns
    style_keywords = ['style', 'style #', 'style no', 'style number']
    customer_dept_keywords = ['customer department', 'ship to']

    # Find the style and customer department columns in the user's file
    style_col = find_column_by_keywords(user_df, style_keywords)
    customer_dept_col = find_column_by_keywords(user_df, customer_dept_keywords)

    if not style_col or not customer_dept_col:
        st.error("Could not find 'Style' or 'Customer Department'/'Ship To' columns in the uploaded user file.")
        st.stop()

    # For mapping, create a dictionary from the subchassis dataframe
    # Key: (Style, Department), Value: LatestSubChassis
    subchassis_map = {}
    if 'Style' in subchassis_df.columns and 'Department' in subchassis_df.columns and 'LatestSubChassis' in subchassis_df.columns:
        for _, row in subchassis_df.iterrows():
            key = (str(row['Style']).strip(), str(row['Department']).strip())
            subchassis_map[key] = row['LatestSubChassis']
    else:
        st.error("The Subchassis file must contain 'Style', 'Department', and 'LatestSubChassis' columns.")
        st.stop()
        
    # Create the new 'LatestSubChassis' column in the user's dataframe
    user_df['LatestSubChassis'] = user_df.apply(
        lambda row: subchassis_map.get(
            (str(row[style_col]).strip(), str(row[customer_dept_col]).strip()), 
            'Not Found'
        ),
        axis=1
    )
    
    return user_df

def to_excel(df):
    """Converts a dataframe to an Excel file in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    processed_data = output.getvalue()
    return processed_data

def main():
    st.set_page_config(page_title="Subchassis Mapping Tool", layout="wide")

    st.title("Subchassis and SP'26 Mapping Tool")

    # --- Session State Initialization ---
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""

    # --- Login Form ---
    if not st.session_state.logged_in:
        st.header("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            # Simple hardcoded credentials
            if username == "admin" and password == "admin123":
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.success("Logged in as Admin")
                st.rerun()
            elif username == "user" and password == "user123":
                st.session_state.logged_in = True
                st.session_state.username = "user"
                st.success("Logged in as User")
                st.rerun()
            else:
                st.error("Incorrect username or password")

    # --- Main Application ---
    if st.session_state.logged_in:
        st.sidebar.header(f"Welcome, {st.session_state.username}")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()

        # --- Admin View ---
        if st.session_state.username == 'admin':
            st.header("Admin Panel: Upload Subchassis Reference")
            uploaded_subchassis = st.file_uploader("Upload Subchassis.xlsx", type=["xlsx", "csv"])
            if uploaded_subchassis:
                try:
                    df = pd.read_excel(uploaded_subchassis) if uploaded_subchassis.name.endswith('xlsx') else pd.read_csv(uploaded_subchassis)
                    st.session_state['subchassis_df'] = df
                    st.success("Subchassis file uploaded successfully!")
                    st.dataframe(df)
                except Exception as e:
                    st.error(f"Error reading file: {e}")

        # --- User View ---
        if st.session_state.username == 'user':
            st.header("User Panel: Upload SP'26 File")
            
            if 'subchassis_df' not in st.session_state:
                st.warning("The Admin has not uploaded the Subchassis reference file yet. Please wait.")
                st.stop()

            uploaded_user_file = st.file_uploader("Upload your Excel/CSV file", type=["xlsx", "csv"])

            if uploaded_user_file:
                try:
                    user_df = pd.read_excel(uploaded_user_file) if uploaded_user_file.name.endswith('xlsx') else pd.read_csv(uploaded_user_file)
                    st.session_state['user_df_original'] = user_df.copy()
                    
                    st.subheader("Your Uploaded Data")
                    st.dataframe(user_df)

                    if st.button("Process and Map LatestSubChassis"):
                        with st.spinner('Processing...'):
                            processed_df = process_files(user_df, st.session_state['subchassis_df'])
                            st.session_state['processed_df'] = processed_df
                        
                        st.subheader("Processed Data with LatestSubChassis")
                        st.dataframe(processed_df)
                        
                        excel_data = to_excel(processed_df)
                        st.download_button(
                            label="📥 Download Compiled Excel File",
                            data=excel_data,
                            file_name="compiled_sp26.xlsx",
                            mime="application/vnd.ms-excel"
                        )

                except Exception as e:
                    st.error(f"Error reading or processing file: {e}")

if __name__ == "__main__":
    main()
