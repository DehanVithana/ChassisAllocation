import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Chassis Allocation Consolidation", layout="wide")

# ========= Helpers =========

STYLE_CANDIDATES = [
    "style", "style #", "style no", "style number", "style_num", "styleid", "style id"
]
CHASSIS_CANDIDATES = [
    "chassis allocation", "chassis_alloc", "chassisallocation", "allocation", "chassis"
]

def guess_column(columns, positive_terms, require_all=False):
    """
    Heuristic: find a column whose name contains all or any of the tokens in positive_terms.
    """
    cols_lc = [c.lower() for c in columns]
    # Exact-ish contains with all tokens
    if require_all:
        for c in columns:
            lc = c.lower()
            if all(t in lc for t in positive_terms):
                return c
    # Any token
    for c in columns:
        lc = c.lower()
        if any(t in lc for t in positive_terms):
            return c
    return None

def guess_style_column(columns):
    return guess_column(columns, [t for t in STYLE_CANDIDATES])

def guess_chassis_column(columns):
    # Prefer columns containing BOTH chassis & alloc
    both = guess_column(columns, ["chassis", "alloc"], require_all=True)
    if both:
        return both
    # Then fall back to broader candidates
    return guess_column(columns, [t for t in CHASSIS_CANDIDATES])

def normalize_style_series(s: pd.Series,
                           do_strip=True,
                           to_upper=True,
                           remove_spaces=True,
                           remove_leading_zeros=False):
    x = s.astype(str)
    if do_strip:
        x = x.str.strip()
    if remove_spaces:
        x = x.str.replace(r"\s+", "", regex=True)
    if to_upper:
        x = x.str.upper()
    if remove_leading_zeros:
        x = x.apply(lambda z: re.sub(r"^0+", "", z))
    return x

def read_uploaded_table(label: str, key_prefix: str):
    """
    Reads a CSV or Excel file. For Excel, allows interactive sheet selection.
    Returns (df, filetype_str).
    """
    file = st.file_uploader(label, type=["csv", "xlsx"], key=f"{key_prefix}_file")
    if not file:
        return None, None

    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file)
        return df, "csv"

    # Excel with sheet selection
    xl = pd.ExcelFile(file)
    sheet = st.selectbox(
        f"Select sheet for {label}",
        options=xl.sheet_names,
        index=0,
        key=f"{key_prefix}_sheet"
    )
    df = xl.parse(sheet)
    return df, "xlsx"

# ========= UI =========

st.title("Consolidate Chassis Allocation by Style")
st.caption(
    "Upload your **Unstructured** report (with a Style column, variable header/position) "
    "and your **Structured** report (with Style + Chassis Allocation). "
    "This tool will map **Chassis Allocation** into your Unstructured report."
)

col_u, col_s = st.columns(2)
with col_u:
    un_df, un_type = read_uploaded_table("Upload **Unstructured** Report", "un")
with col_s:
    st_df, st_type = read_uploaded_table("Upload **Structured** Report", "st")

if un_df is not None and st_df is not None:
    st.markdown("### 1) Column Mapping")

    # Auto-guess columns
    un_guess_style = guess_style_column(un_df.columns) or (len(un_df.columns) and un_df.columns[0])
    st_guess_style = guess_style_column(st_df.columns) or (len(st_df.columns) and st_df.columns[0])
    st_guess_alloc = guess_chassis_column(st_df.columns)

    cm1, cm2, cm3 = st.columns([1, 1, 1])
    with cm1:
        un_style_col = st.selectbox(
            "Unstructured: **Style Number** column",
            options=list(un_df.columns),
            index=list(un_df.columns).index(un_guess_style) if un_guess_style in un_df.columns else 0,
            help="Choose the column in the Unstructured report that represents the Style Number."
        )
    with cm2:
        st_style_col = st.selectbox(
            "Structured: **Style Number** column",
            options=list(st_df.columns),
            index=list(st_df.columns).index(st_guess_style) if st_guess_style in st_df.columns else 0,
            help="Choose the column in the Structured report that represents the Style Number."
        )
    with cm3:
        st_alloc_col = st.selectbox(
            "Structured: **Chassis Allocation** column",
            options=list(st_df.columns),
            index=list(st_df.columns).index(st_guess_alloc) if (st_guess_alloc and st_guess_alloc in st_df.columns) else 0,
            help="Choose the column with Chassis Allocation."
        )

    st.markdown("### 2) Style Number Normalization (applied to both reports)")
    n1, n2, n3, n4 = st.columns(4)
    with n1:
        opt_strip = st.checkbox("Trim whitespace", value=True)
    with n2:
        opt_upper = st.checkbox("Uppercase", value=True)
    with n3:
        opt_rm_spaces = st.checkbox("Remove inner spaces", value=True)
    with n4:
        opt_rm_lead0 = st.checkbox("Remove leading zeros", value=False)

    st.markdown("### 3) Duplicate Styles in Structured Report")
    d1, d2 = st.columns([1, 3])
    with d1:
        handle_dupes = st.selectbox(
            "If duplicates exist:",
            options=["Keep first", "Sum allocations"],
            index=1
        )
    with d2:
        st.caption(
            "• **Keep first**: Uses the first occurrence per Style.\n\n"
            "• **Sum allocations**: Groups by Style and sums **Chassis Allocation** (non-numeric values will fallback to first)."
        )

    run = st.button("▶️ Consolidate", type="primary")

    if run:
        # Work on copies
        u = un_df.copy()
        s = st_df.copy()

        # Build normalized keys
        u["_STYLE_KEY_"] = normalize_style_series(u[un_style_col],
                                                  do_strip=opt_strip,
                                                  to_upper=opt_upper,
                                                  remove_spaces=opt_rm_spaces,
                                                  remove_leading_zeros=opt_rm_lead0)
        s["_STYLE_KEY_"] = normalize_style_series(s[st_style_col],
                                                  do_strip=opt_strip,
                                                  to_upper=opt_upper,
                                                  remove_spaces=opt_rm_spaces,
                                                  remove_leading_zeros=opt_rm_lead0)

        # Prepare structured (dedupe/aggregate if needed)
        left_cols = ["_STYLE_KEY_", st_alloc_col]
        s_reduced = s[left_cols].copy()

        if handle_dupes == "Sum allocations":
            # Try numeric sum; if not numeric, coerce and sum; fallback to first if all NaN
            s_reduced["_alloc_num_"] = pd.to_numeric(s_reduced[st_alloc_col], errors="coerce")
            grouped = s_reduced.groupby("_STYLE_KEY_", as_index=False)["_alloc_num_"].sum(min_count=1)
            # If all NaN sums for a key, fallback to first non-null original value
            fallback_first = (
                s_reduced.dropna(subset=[st_alloc_col])
                .sort_index()
                .drop_duplicates("_STYLE_KEY_")
                [["_STYLE_KEY_", st_alloc_col]]
            )
            merged_group = grouped.merge(fallback_first, on="_STYLE_KEY_", how="left")
            # Prefer numeric sum if available; else fallback to first
            merged_group[st_alloc_col] = merged_group["_alloc_num_"].where(
                merged_group["_alloc_num_"].notna(), merged_group[st_alloc_col]
            )
            structured_final = merged_group[["_STYLE_KEY_", st_alloc_col]].copy()
        else:
            # Keep first
            structured_final = (
                s_reduced.drop_duplicates("_STYLE_KEY_", keep="first")[["_STYLE_KEY_", st_alloc_col]].copy()
            )

        # Left merge to preserve Unstructured rows
        consolidated = u.merge(structured_final, on="_STYLE_KEY_", how="left", suffixes=("", "_y"))

        # Drop helper key
        consolidated.drop(columns=["_STYLE_KEY_"], inplace=True, errors="ignore")

        # Metrics
        total_rows = len(consolidated)
        matched_rows = consolidated[st_alloc_col].notna().sum()
        unmatched_rows = total_rows - matched_rows

        m1, m2, m3 = st.columns(3)
        m1.metric("Total rows (Unstructured)", f"{total_rows:,}")
        m2.metric("Matched styles", f"{matched_rows:,}")
        m3.metric("Unmatched styles", f"{unmatched_rows:,}")

        st.success("Consolidation complete. Preview below:")
        st.dataframe(consolidated, use_container_width=True, height=380)

        # Prepare downloads
        # 1) CSV
        csv_data = consolidated.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Consolidated (CSV)",
            data=csv_data,
            file_name="consolidated_report.csv",
            mime="text/csv",
        )

        # 2) Excel (with optional Unmatched sheet)
        unmatched_df = consolidated.loc[consolidated[st_alloc_col].isna()].copy()

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            consolidated.to_excel(writer, index=False, sheet_name="Consolidated")
            if unmatched_rows > 0:
                unmatched_df.to_excel(writer, index=False, sheet_name="Unmatched")
        output.seek(0)

        st.download_button(
            "⬇️ Download Consolidated (Excel)",
            data=output,
            file_name="consolidated_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with st.expander("Preview uploaded data (optional)"):
        st.subheader("Unstructured report (head)")
        st.dataframe(un_df.head(20), use_container_width=True)
        st.subheader("Structured report (head)")
        st.dataframe(st_df.head(20), use_container_width=True)
else:
    st.info("Please upload both the **Unstructured** and **Structured** reports to continue.")
