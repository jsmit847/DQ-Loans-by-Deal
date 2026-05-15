import re
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

APP_VERSION = "2026-05-15-v15c-dlsr-staging-no-dqdata-source"

# ============================================================
# Streamlit setup
# ============================================================

st.set_page_config(
    page_title="DQ Table Generator",
    page_icon="📊",
    layout="wide",
)

st.title("DQ Table Generator")
st.caption(f"Version {APP_VERSION}")
st.caption(
    "Creates DQ Table and DQ Loans by Deal from uploaded RSRV/DLSR files. "
    "The workbook DQ Data sheet is not used as a source; the app creates its own DLSR staging dataset."
)

# ============================================================
# Constants
# ============================================================

DQ_TABLE_COLUMNS = [
    "Securitization",
    "DQ",
    "Loan id",
    "Deal ID",
    "Account",
    "Borrower Entity",
    "Deal Name",
    "Property Type",
    "City",
    "State",
    "Paid Through Date",
    "Current UPB",
    "Recent Appraisal",
    "Appraisal Date",
    "Commentary",
]

DQ_REPORT_COLUMNS = [
    "Item",
    "Loan ID",
    "Deal ID",
    "Account",
    "Borrower Entitity",  # Intentional typo to match report sheet
    "Deal Name",
    "Property Type",
    "City",
    "State",
    "Paid through Date",
    "Current UPB",
    "Recent Appraisal",
    "Appraisal Date",
    "Commentary",
]

DQ_TABLE_ORDER = [
    "90+",
    "60-89",
    "30-59",
    "Current and at Special Servicer",
    "Matured Performing",
    "Matured Non-Performing",
]

DQ_REPORT_ORDER = [
    "30-59",
    "60-89",
    "90+",
    "Current and at Special Servicer",
    "Matured Performing",
    "Matured Non-Performing",
]

DQ_DISPLAY = {
    "30-59": "30-59 Days Delinquent",
    "60-89": "60-89 Days Delinquent",
    "90+": "90+ Days Delinquent",
    "Current and at Special Servicer": "Current and at Special Servicer",
    "Matured Performing": "Matured Performing Loans",
    "Matured Non-Performing": "Matured Non-Performing Loans",
}

# DQ Table has a historical no-space spelling for CAF2018-2 in the April workbook.
DQ_TABLE_DEAL_ORDER = [
    "CAF 2017-2",
    "CAF 2018-1",
    "CAF2018-2",
    "CAF 2019-1",
    "CAF 2019-2",
    "CAF 2019-3",
    "CAF 2020-1",
    "CAF 2020-2",
    "CAF 2020-3",
    "CAF 2020-4",
    "CAFL 2020-P1",
    "CAF 2021-1",
    "CAF 2021-2",
    "CAF 2021-3",
    "CAF 2022-1",
    "CAF 2022-P2",
    "CAF 2023-P1",
]

# The visible DQ Loans by Deal report uses spaced deal names.
DQ_REPORT_DEAL_ORDER = [
    "CAF 2017-2",
    "CAF 2018-1",
    "CAF 2018-2",
    "CAF 2019-1",
    "CAF 2019-2",
    "CAF 2019-3",
    "CAF 2020-1",
    "CAF 2020-2",
    "CAF 2020-3",
    "CAF 2020-4",
    "CAFL 2020-P1",
    "CAF 2021-1",
    "CAF 2021-2",
    "CAF 2021-3",
    "CAF 2022-1",
    "CAF 2022-P2",
    "CAF 2023-P1",
]

STATE_ABBREV = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
    "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
}

# ============================================================
# Generic helpers
# ============================================================

def clean_col_name(col) -> str:
    col = str(col).strip()
    col = re.sub(r"\s+", " ", col)
    col = col.replace("/", " or ")
    col = col.replace("-", " ")
    col = col.replace("(", "")
    col = col.replace(")", "")
    col = col.replace("%", "pct")
    col = re.sub(r"[^0-9a-zA-Z]+", "_", col)
    col = re.sub(r"_+", "_", col)
    return col.strip("_").lower()


def make_unique_columns(cols) -> List[str]:
    seen = {}
    out = []
    for col in cols:
        base = clean_col_name(col)
        if base in ["", "nan", "none"]:
            base = "blank"
        if base not in seen:
            seen[base] = 0
            out.append(base)
        else:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
    return out


def cell_to_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


def clean_id_value(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if s.lower() in ["", "nan", "none", "na", "n/a"]:
        return pd.NA
    return s


def is_blankish(x) -> bool:
    if pd.isna(x):
        return True
    s = str(x).strip()
    # Keep literal "NA" as a valid reporting value for Borrower Entity.
    return s == "" or s.lower() in ["nan", "none", "n/a", "<na>"]


def clean_text_value(x, zero_as_blank=True):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if zero_as_blank and s in ["0", "0.0"]:
        return pd.NA
    if s.lower() in ["nan", "none", "<na>"]:
        return pd.NA
    return s


def clean_text_preserve_na(x, zero_as_blank=True):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if zero_as_blank and s in ["0", "0.0"]:
        return pd.NA
    if s.lower() in ["nan", "none", "<na>"]:
        return pd.NA
    # Keep literal NA when the workbook uses NA as a reporting value.
    return s


def parse_report_date(x):
    if pd.isna(x):
        return pd.NaT
    if isinstance(x, pd.Timestamp):
        return x.normalize()
    if hasattr(x, "strftime") and not isinstance(x, str):
        try:
            return pd.Timestamp(x).normalize()
        except Exception:
            pass
    s = str(x).strip()
    if s in ["", "0", "0.0"]:
        return pd.NaT
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if re.fullmatch(r"\d{8}", s):
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def safe_numeric(x):
    if pd.isna(x):
        return pd.NA
    if isinstance(x, str):
        x = x.replace(",", "").replace("$", "").strip()
        if x in ["", "0", "0.0"]:
            # For numeric columns, zero can be meaningful. Keep zero if explicit.
            pass
    return pd.to_numeric(x, errors="coerce")


def first_present(*values):
    for value in values:
        if not is_blankish(value):
            return value
    return pd.NA


def normalize_dq_status(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    u = re.sub(r"\s+", " ", s.upper())
    u = u.replace("–", "-").replace("—", "-")

    mapping = {
        "90": "90+",
        "90+": "90+",
        "90 +": "90+",
        "90+ DAYS DELINQUENT": "90+",
        "90 + DAYS DELINQUENT": "90+",
        "90 DAYS DELINQUENT": "90+",
        "60": "60-89",
        "60-89": "60-89",
        "60 TO 89 DAYS DELINQUENT": "60-89",
        "60 - 89 DAYS DELINQUENT": "60-89",
        "30": "30-59",
        "30-59": "30-59",
        "30 TO 59 DAYS DELINQUENT": "30-59",
        "30 - 59 DAYS DELINQUENT": "30-59",
        "CURRENT AND AT SPECIAL SERVICER": "Current and at Special Servicer",
        "CURRENT AND AT SPECIAL SERVICER LOANS": "Current and at Special Servicer",
        "MATURED PERFORMING": "Matured Performing",
        "MATURED PERFORMING LOANS": "Matured Performing",
        "MATURED NON-PERFORMING": "Matured Non-Performing",
        "MATURED NON PERFORMING": "Matured Non-Performing",
        "MATURED NON-PERFORMING LOANS": "Matured Non-Performing",
    }
    return mapping.get(u, s)


def normalize_property_type(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s == "" or s.lower() in ["nan", "none", "<na>"]:
        return pd.NA
    u = s.upper()
    if u in ["XX", "ZZ", "INCOMPLETE"]:
        return "Various"
    if u in ["MULTIFAMILY", "MULTI FAMILY"]:
        return "MF"
    if u in ["SFRS", "SFR", "SINGLE FAMILY", "SINGLE FAMILY RENTAL", "SINGLE FAMILY RENTALS"]:
        # Preserve SFR when it comes from carry-forward; DLSR generally uses SF.
        return "SF"
    return s


def clean_city(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s == "" or s.lower() in ["nan", "none", "<na>"]:
        return pd.NA
    if s.upper() in ["INCOMPLETE", "ZZ", "XX"]:
        return pd.NA
    return s


def clean_state(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s == "" or s.lower() in ["nan", "none", "<na>"]:
        return pd.NA
    u = s.upper()
    if u in ["ZZ", "XX", "INCOMPLETE"]:
        return pd.NA
    return STATE_ABBREV.get(u, s)


def safe_excel_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime() if not pd.isna(value) else None
    return value


def extract_city_state_from_commentary(commentary) -> Tuple[object, object]:
    """Best-effort helper for new loans only. Do not use for existing carry-forward loans."""
    if pd.isna(commentary):
        return pd.NA, pd.NA
    text = str(commentary)
    if not text.strip():
        return pd.NA, pd.NA

    # Avoid cases with multiple states or counts such as "3 located in CO and 1 located in FL".
    state_mentions = re.findall(r"\b[A-Z]{2}\b", text)
    if len(set(state_mentions)) > 1 and not re.search(r"located in [A-Za-z ./'-]+,\s*[A-Z]{2}\b", text):
        return "Various", "Various"

    # Common phrasing: "located in Glassboro, NJ" or "properties located in Glassboro, NJ".
    m = re.search(r"located in\s+([A-Za-z ./'-]+?),\s*([A-Z]{2})\b", text)
    if m:
        city = m.group(1).strip()
        state = m.group(2).strip()
        # Filter out broad phrases that are not a city.
        if len(city) <= 40 and city.lower() not in ["multiple cities", "various"]:
            return city, state

    # If text says properties in two states but no single city, use Various/Various.
    if re.search(r"\blocated in\s+[A-Z]{2}\s+and\s+\d+\s+located in\s+[A-Z]{2}\b", text):
        return "Various", "Various"

    return pd.NA, pd.NA

# ============================================================
# Securitization display helpers
# ============================================================

def securitization_from_file(source_file):
    name = str(source_file).strip()
    name = re.sub(r"\.xlsx$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.xls$", "", name, flags=re.IGNORECASE)
    code = re.sub(r"^CVAF_", "", name, flags=re.IGNORECASE)
    code = re.sub(r"_RSRV$", "", code, flags=re.IGNORECASE)
    code = code.upper()
    mapping = {
        "20172": "CAF 2017-2",
        "20181": "CAF 2018-1",
        "20182": "CAF2018-2",
        "20191": "CAF 2019-1",
        "20192": "CAF 2019-2",
        "20193": "CAF 2019-3",
        "20201": "CAF 2020-1",
        "20202": "CAF 2020-2",
        "20203": "CAF 2020-3",
        "20204": "CAF 2020-4",
        "2020P1": "CAFL 2020-P1",
        "20211": "CAF 2021-1",
        "20212": "CAF 2021-2",
        "20213": "CAF 2021-3",
        "20221": "CAF 2022-1",
        "2022P2": "CAF 2022-P2",
        "2023P1": "CAF 2023-P1",
    }
    return mapping.get(code, pd.NA)


def normalize_sec_for_table(x, source_file=None):
    if pd.isna(x) or str(x).strip() == "":
        return securitization_from_file(source_file) if source_file is not None else pd.NA
    s = str(x).strip()
    u = re.sub(r"\s+", " ", s.upper())

    explicit = {
        "COREVEST18-1": "CAF 2018-1",
        "COREVEST 18-1": "CAF 2018-1",
        "COREVEST19-2": "CAF 2019-2",
        "COREVEST 19-2": "CAF 2019-2",
        "COREVEST AMER 2019-3": "CAF 2019-3",
        "COREVEST AMERICAN FINANCE 2019-3": "CAF 2019-3",
        "CAF 2020-P1": "CAFL 2020-P1",
        "CAF2020-P1": "CAFL 2020-P1",
        "CAF2020P1": "CAFL 2020-P1",
        "CAFL2020P1": "CAFL 2020-P1",
        "CAFL 2020P1": "CAFL 2020-P1",
        "CAFL 2020-P1": "CAFL 2020-P1",
        "CAF 2022P2": "CAF 2022-P2",
        "CAF2022P2": "CAF 2022-P2",
        "CAFL 2022-P2": "CAF 2022-P2",
        "CAF 2023P1": "CAF 2023-P1",
        "CAF2023P1": "CAF 2023-P1",
    }
    if u in explicit:
        return explicit[u]

    # Preserve historical no-space display for CAF2018-2 in DQ Table.
    if u in ["CAF2018-2", "CAF 2018-2"]:
        return "CAF2018-2" if "CAF2018-2" in s.upper().replace(" ", "") else "CAF 2018-2"

    m = re.match(r"CAF(\d{4})-(\d+)$", u)
    if m:
        return f"CAF {m.group(1)}-{m.group(2)}"

    return s


def sec_table_to_report(x):
    if pd.isna(x):
        return pd.NA
    s = str(x).strip()
    if s.upper() == "CAF2018-2":
        return "CAF 2018-2"
    return s


def deal_order_value_table(x):
    s = str(x)
    return DQ_TABLE_DEAL_ORDER.index(s) if s in DQ_TABLE_DEAL_ORDER else 999


def deal_order_value_report(x):
    s = str(x)
    return DQ_REPORT_DEAL_ORDER.index(s) if s in DQ_REPORT_DEAL_ORDER else 999


def dq_order_value(x, report=False):
    status = normalize_dq_status(x)
    order = DQ_REPORT_ORDER if report else DQ_TABLE_ORDER
    return order.index(status) if status in order else 999

# ============================================================
# DLSR parsing - this creates the app's DQ staging data
# ============================================================

def find_dlsr_sheet(file_bytes):
    xl = pd.ExcelFile(BytesIO(file_bytes))
    sheet_names = xl.sheet_names
    preferred = ["Delinquent Loan Status", "Delinquency Loan Status", "DLSR"]
    for sheet in preferred:
        if sheet in sheet_names:
            return sheet
    for sheet in sheet_names:
        s = sheet.lower()
        if "delinquent" in s or "delinquency" in s or "dlsr" in s:
            return sheet
    return None


def find_header_row(df_raw):
    for idx in df_raw.index:
        row = [cell_to_text(x) for x in df_raw.loc[idx].tolist()]
        has_loan_id = any(x == "loan id" for x in row)
        has_prospectus = any(("prospectus" in x and "loan" in x) for x in row)
        has_paid_through = any("paid through" in x for x in row)
        if has_loan_id and (has_prospectus or has_paid_through):
            return idx
    return None


def extract_as_of_date(df_raw):
    for r in df_raw.index:
        for c in df_raw.columns:
            if cell_to_text(df_raw.loc[r, c]) == "as of" and r + 1 in df_raw.index:
                return parse_report_date(df_raw.loc[r + 1, c])
    return pd.NaT


def section_value(value):
    normalized = normalize_dq_status(value)
    valid = set(DQ_TABLE_ORDER)
    if isinstance(normalized, str) and normalized in valid:
        return normalized
    return None


def process_dlsr_uploaded_file(uploaded_file):
    source_file = uploaded_file.name
    file_bytes = uploaded_file.getvalue()

    sheet_name = find_dlsr_sheet(file_bytes)
    if sheet_name is None:
        return None, {"file": source_file, "status": "Skipped", "reason": "No DLSR-like sheet found"}

    df_raw = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)
    report_as_of = extract_as_of_date(df_raw)
    header_row = find_header_row(df_raw)
    if header_row is None:
        return None, {"file": source_file, "status": "Skipped", "reason": f"Could not find header row on sheet '{sheet_name}'"}

    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = df_raw.iloc[header_row].astype(str).str.strip()
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    loan_id_raw_cols = [c for c in df.columns if clean_col_name(c) == "loan_id"]
    if not loan_id_raw_cols:
        return None, {"file": source_file, "status": "Skipped", "reason": "Loan ID column not found"}
    loan_id_raw_col = loan_id_raw_cols[0]

    first_col = df.columns[0]
    section_candidates = df[first_col].apply(section_value)
    df["dq"] = pd.NA
    mask = section_candidates.notna()
    df.loc[mask, "dq"] = section_candidates[mask]
    df["dq"] = df["dq"].ffill()

    # Keep loan rows only.
    df = df[df[loan_id_raw_col].notna()].copy()
    df = df[df[loan_id_raw_col].astype(str).str.contains(r"\d", na=False)].copy()
    if df.empty:
        return None, {"file": source_file, "status": "Parsed empty", "reason": f"No loan rows found on '{sheet_name}'"}

    df.columns = make_unique_columns(df.columns)
    if "loan_id" not in df.columns:
        return None, {"file": source_file, "status": "Skipped", "reason": "Loan ID missing after cleanup"}

    df["source_file"] = source_file
    df["source_sheet"] = sheet_name
    df["source_header_row"] = header_row
    df["report_as_of_date"] = report_as_of

    df["loan_id"] = df["loan_id"].apply(clean_id_value)
    if "prospectus_loan_id" in df.columns:
        df["prospectus_loan_id"] = df["prospectus_loan_id"].apply(clean_id_value)

    # If DQ section is missing for older rows, fall back to Group ID.
    if "group_id" in df.columns:
        fallback_dq = df["group_id"].apply(normalize_dq_status)
        df["dq"] = df["dq"].combine_first(fallback_dq.where(fallback_dq.isin(DQ_TABLE_ORDER)))

    trans = df["trans_id"] if "trans_id" in df.columns else pd.Series(pd.NA, index=df.index)
    file_sec = securitization_from_file(source_file)
    df["securitization"] = [
        normalize_sec_for_table(t if not is_blankish(t) else file_sec, source_file)
        for t in trans
    ]

    return df, {"file": source_file, "status": "Parsed", "reason": f"Sheet '{sheet_name}', header row {header_row}, rows {len(df)}"}


def parse_uploaded_dlsr_files(uploaded_files):
    parsed = []
    logs = []
    for uploaded_file in uploaded_files:
        if not uploaded_file.name.lower().endswith((".xls", ".xlsx")):
            logs.append({"file": uploaded_file.name, "status": "Skipped", "reason": "Not an Excel file"})
            continue
        try:
            result, log = process_dlsr_uploaded_file(uploaded_file)
            logs.append(log)
            if result is not None and not result.empty:
                parsed.append(result)
        except Exception as exc:
            logs.append({"file": uploaded_file.name, "status": "Error", "reason": str(exc)})

    if not parsed:
        return pd.DataFrame(), pd.DataFrame(logs)

    staging = pd.concat(parsed, ignore_index=True)
    staging = staging.drop_duplicates(subset=["securitization", "loan_id"], keep="first").copy()
    return staging, pd.DataFrame(logs)

# ============================================================
# Metadata readers
# ============================================================

def find_header_row_by_required(df_raw, required_terms):
    required_terms = [t.lower() for t in required_terms]
    for idx in df_raw.index:
        row = [cell_to_text(x) for x in df_raw.loc[idx].tolist()]
        row_text = " | ".join(row)
        if all(term in row_text for term in required_terms):
            return idx
    return None


def read_sheet_as_table(file_bytes, sheet_name, required_terms=None):
    xl = pd.ExcelFile(BytesIO(file_bytes))
    if sheet_name not in xl.sheet_names:
        return pd.DataFrame()
    raw = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)
    if required_terms:
        header_row = find_header_row_by_required(raw, required_terms)
    else:
        header_row = 0
    if header_row is None:
        return pd.DataFrame()
    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()
    return df


def read_prior_dq_table(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame()
    file_bytes = uploaded_file.getvalue()
    # A prior dashboard should have DQ Table. If someone provides a workbook with old DQ Table, accept that too.
    xl = pd.ExcelFile(BytesIO(file_bytes))
    sheet_name = "DQ Table" if "DQ Table" in xl.sheet_names else ("old DQ Table" if "old DQ Table" in xl.sheet_names else None)
    if sheet_name is None:
        return pd.DataFrame()
    df = read_sheet_as_table(file_bytes, sheet_name, required_terms=["securitization", "loan"])
    if df.empty or "loan_id" not in df.columns:
        return pd.DataFrame()
    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()
    df["loan_id"] = df["loan_id"].apply(clean_id_value)
    if "securitization" in df.columns:
        df["securitization"] = df["securitization"].apply(lambda x: normalize_sec_for_table(x))
    if "dq" in df.columns:
        df["dq"] = df["dq"].apply(normalize_dq_status)
    return df


def read_current_term_loan(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame()
    file_bytes = uploaded_file.getvalue()
    df = read_sheet_as_table(file_bytes, "Term Loan", required_terms=["deal number", "servicer id"])
    if df.empty:
        return pd.DataFrame()

    rename_map = {}
    # Already clean names, but account for slight variants.
    for col in df.columns:
        c = clean_col_name(col)
        if c == "deal_number":
            rename_map[col] = "deal_id"
        elif c == "servicer_id":
            rename_map[col] = "loan_id"
        elif c == "account_name":
            rename_map[col] = "account"
        elif c == "borrower_entity":
            rename_map[col] = "borrower_entity"
        elif c == "deal_name":
            rename_map[col] = "deal_name"
    df = df.rename(columns=rename_map)

    if "loan_id" not in df.columns:
        return pd.DataFrame()
    df = df[df["loan_id"].notna()].copy()
    df["loan_id"] = df["loan_id"].apply(clean_id_value)

    keep = [c for c in ["loan_id", "deal_id", "account", "borrower_entity", "deal_name"] if c in df.columns]
    df = df[keep].copy()
    if "deal_id" in df.columns:
        df["deal_id"] = df["deal_id"].apply(clean_id_value)
    for col in ["account", "borrower_entity", "deal_name"]:
        if col in df.columns:
            if col == "borrower_entity":
                df[col] = df[col].apply(lambda x: "NA" if str(x).strip() in ["0", "0.0"] else clean_text_value(x, zero_as_blank=False))
            else:
                df[col] = df[col].apply(clean_text_value)
    df = df.drop_duplicates(subset=["loan_id"], keep="first")
    return df

# ============================================================
# DQ Table builder
# ============================================================

def as_lookup(df, key="loan_id") -> Dict[str, dict]:
    if df is None or df.empty or key not in df.columns:
        return {}
    work = df.copy()
    work[key] = work[key].apply(clean_id_value)
    work = work[work[key].notna()].copy()
    work = work.drop_duplicates(subset=[key], keep="first")
    return work.set_index(key).to_dict(orient="index")


def get_from_lookup(lookup, loan_id, col):
    rec = lookup.get(loan_id, {})
    if col in rec and not is_blankish(rec[col]):
        return rec[col]
    return pd.NA


def build_dq_table_from_staging(dlsr_staging, prior_dq_table=None, current_term_loan=None, use_prior_dq_override=False):
    d = dlsr_staging.copy()
    d["loan_id"] = d["loan_id"].apply(clean_id_value)
    prior_lookup = as_lookup(prior_dq_table)
    term_lookup = as_lookup(current_term_loan)

    rows = []
    for _, row in d.iterrows():
        loan_id = clean_id_value(row.get("loan_id"))
        if is_blankish(loan_id):
            continue

        prior = prior_lookup.get(loan_id, {})
        term = term_lookup.get(loan_id, {})
        is_existing = bool(prior)

        securitization = row.get("securitization")
        securitization = normalize_sec_for_table(securitization, row.get("source_file"))

        dq = normalize_dq_status(row.get("dq"))
        if use_prior_dq_override and is_existing and not is_blankish(prior.get("dq")):
            dq = normalize_dq_status(prior.get("dq"))

        dlsr_property_type = normalize_property_type(row.get("property_type"))
        dlsr_city = clean_city(row.get("property_city"))
        dlsr_state = clean_state(row.get("property_state"))
        dlsr_commentary = clean_text_value(row.get("comments_dlsr"), zero_as_blank=True)

        # DLSR property type/city/state can be placeholders. Existing loans keep prior/manual metadata.
        if is_existing:
            deal_id = first_present(prior.get("deal_id"), term.get("deal_id"), row.get("prospectus_loan_id"))
            account = first_present(prior.get("account"), term.get("account"), row.get("property_name"))
            borrower_entity = first_present(prior.get("borrower_entity"), term.get("borrower_entity"))
            deal_name = first_present(prior.get("deal_name"), term.get("deal_name"), row.get("property_name"))
            property_type = first_present(prior.get("property_type"), dlsr_property_type)
            city = first_present(prior.get("city"), dlsr_city, "Various")
            state = first_present(prior.get("state"), dlsr_state, "Various")
        else:
            inferred_city, inferred_state = extract_city_state_from_commentary(dlsr_commentary)
            deal_id = first_present(term.get("deal_id"), row.get("prospectus_loan_id"))
            account = first_present(term.get("account"), row.get("property_name"))
            borrower_entity = first_present(term.get("borrower_entity"), pd.NA)
            deal_name = first_present(term.get("deal_name"), row.get("property_name"))
            property_type = first_present(dlsr_property_type, "Various")
            city = first_present(dlsr_city, inferred_city, "Various")
            state = first_present(dlsr_state, inferred_state, "Various")

        # Current values come from the generated DLSR staging dataset.
        paid_through = parse_report_date(row.get("paid_through_date"))
        current_upb = safe_numeric(row.get("current_ending_scheduled_balance"))
        recent_appraisal = safe_numeric(row.get("most_recent_value"))
        appraisal_date = parse_report_date(row.get("most_recent_valuation_date"))
        commentary = dlsr_commentary

        out = {
            "Securitization": securitization,
            "DQ": dq,
            "Loan id": loan_id,
            "Deal ID": clean_id_value(deal_id),
            "Account": clean_text_value(account, zero_as_blank=False),
            "Borrower Entity": clean_text_preserve_na(borrower_entity, zero_as_blank=False),
            "Deal Name": clean_text_value(deal_name, zero_as_blank=False),
            "Property Type": normalize_property_type(property_type),
            "City": clean_city(city) if not is_blankish(clean_city(city)) else "Various",
            "State": clean_state(state) if not is_blankish(clean_state(state)) else "Various",
            "Paid Through Date": paid_through,
            "Current UPB": current_upb,
            "Recent Appraisal": recent_appraisal,
            "Appraisal Date": appraisal_date,
            "Commentary": commentary,
        }
        rows.append(out)

    out = pd.DataFrame(rows, columns=DQ_TABLE_COLUMNS)
    if out.empty:
        return out

    out["_deal_order"] = out["Securitization"].map(deal_order_value_table)
    out["_dq_order"] = out["DQ"].map(lambda x: dq_order_value(x, report=False))
    out["_loan_sort"] = out["Loan id"].astype(str)
    out = out.sort_values(["_deal_order", "_dq_order", "_loan_sort"]).drop(columns=["_deal_order", "_dq_order", "_loan_sort"])
    out = out.drop_duplicates(subset=["Securitization", "Loan id"], keep="first")
    return out[DQ_TABLE_COLUMNS]

# ============================================================
# DQ Loans by Deal builder
# ============================================================

def build_dq_loans_by_deal(dq_table, include_empty_2017_2=True):
    d = dq_table.copy()
    if d.empty:
        return pd.DataFrame(columns=["row_type"] + DQ_REPORT_COLUMNS)
    d["Report Securitization"] = d["Securitization"].apply(sec_table_to_report)
    d["DQ"] = d["DQ"].apply(normalize_dq_status)
    d["Current UPB"] = pd.to_numeric(d["Current UPB"], errors="coerce")

    rows = []
    deals_with_rows = set(d["Report Securitization"].dropna().astype(str).unique())

    for deal in DQ_REPORT_DEAL_ORDER:
        deal_df = d[d["Report Securitization"].astype(str).eq(deal)].copy()
        if deal_df.empty and not (include_empty_2017_2 and deal == "CAF 2017-2"):
            continue

        rows.append({"row_type": "deal", "Item": deal})

        any_bucket = False
        for dq_status in DQ_REPORT_ORDER:
            status_df = deal_df[deal_df["DQ"].eq(dq_status)].copy()
            if status_df.empty:
                continue
            any_bucket = True
            status_df["_loan_sort"] = status_df["Loan id"].astype(str)
            status_df = status_df.sort_values("_loan_sort")

            rows.append({"row_type": "status", "Item": DQ_DISPLAY.get(dq_status, dq_status)})
            start_loan_excel_row = len(rows) + 4  # after headers/title in Excel writer
            for _, loan in status_df.iterrows():
                rows.append({
                    "row_type": "loan",
                    "Item": pd.NA,
                    "Loan ID": loan.get("Loan id"),
                    "Deal ID": loan.get("Deal ID"),
                    "Account": loan.get("Account"),
                    "Borrower Entitity": loan.get("Borrower Entity"),
                    "Deal Name": loan.get("Deal Name"),
                    "Property Type": loan.get("Property Type"),
                    "City": loan.get("City"),
                    "State": loan.get("State"),
                    "Paid through Date": loan.get("Paid Through Date"),
                    "Current UPB": loan.get("Current UPB"),
                    "Recent Appraisal": loan.get("Recent Appraisal"),
                    "Appraisal Date": loan.get("Appraisal Date"),
                    "Commentary": loan.get("Commentary"),
                })
            end_loan_excel_row = len(rows) + 3
            total_upb = status_df["Current UPB"].sum()
            rows.append({
                "row_type": "total",
                "Item": "TOTAL UPB",
                "Loan ID": total_upb,
                "_sum_start": start_loan_excel_row,
                "_sum_end": end_loan_excel_row,
            })

        if deal_df.empty and include_empty_2017_2 and deal == "CAF 2017-2":
            rows.append({"row_type": "total", "Item": "TOTAL UPB", "Loan ID": 0, "_sum_start": None, "_sum_end": None})

    report = pd.DataFrame(rows)
    for col in DQ_REPORT_COLUMNS:
        if col not in report.columns:
            report[col] = pd.NA
    return report[["row_type", "_sum_start", "_sum_end"] + DQ_REPORT_COLUMNS]

# ============================================================
# Excel writer
# ============================================================

def write_output_workbook(dq_table, dq_report, report_title):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="m/d/yyyy") as writer:
        workbook = writer.book

        # DQ Table with blank first row and headers on row 2.
        dq_table.to_excel(writer, sheet_name="DQ Table", index=False, startrow=1)
        ws = writer.sheets["DQ Table"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAD3", "border": 1, "text_wrap": True, "valign": "top"})
        date_fmt = workbook.add_format({"num_format": "m/d/yyyy"})
        money_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})
        for c, name in enumerate(DQ_TABLE_COLUMNS):
            ws.write(1, c, name, header_fmt)
        widths = [18, 16, 14, 12, 26, 30, 30, 14, 20, 12, 16, 16, 16, 16, 75]
        for c, width in enumerate(widths):
            ws.set_column(c, c, width)
        ws.set_column(10, 10, 16, date_fmt)
        ws.set_column(11, 12, 16, money_fmt)
        ws.set_column(13, 13, 16, date_fmt)
        ws.set_column(14, 14, 75, wrap_fmt)
        ws.freeze_panes(2, 0)
        ws.autofilter(1, 0, len(dq_table) + 1, len(DQ_TABLE_COLUMNS) - 1)

        # DQ Loans by Deal
        sheet = "DQ Loans by Deal"
        ws2 = workbook.add_worksheet(sheet)
        writer.sheets[sheet] = ws2

        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        header_fmt2 = workbook.add_format({"bold": True, "bg_color": "#D9EAD3", "border": 1, "text_wrap": True, "valign": "top"})
        deal_fmt = workbook.add_format({"bold": True, "bg_color": "#C6E0B4", "border": 1})
        status_fmt = workbook.add_format({"bold": True, "bg_color": "#E2F0D9", "border": 1})
        total_fmt = workbook.add_format({"bold": True, "bg_color": "#FFF2CC", "border": 1})
        total_money_fmt = workbook.add_format({"bold": True, "bg_color": "#FFF2CC", "border": 1, "num_format": "$#,##0.00"})
        body_fmt = workbook.add_format({"border": 1, "valign": "top"})
        body_date_fmt = workbook.add_format({"border": 1, "num_format": "m/d/yyyy", "valign": "top"})
        body_money_fmt = workbook.add_format({"border": 1, "num_format": "$#,##0.00", "valign": "top"})
        body_wrap_fmt = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})

        start_col = 1
        header_row = 3
        ws2.write(0, start_col, report_title, title_fmt)
        for i, name in enumerate(DQ_REPORT_COLUMNS):
            ws2.write(header_row, start_col + i, name, header_fmt2)

        for ridx, row in dq_report.iterrows():
            excel_row = header_row + 1 + ridx
            row_type = row.get("row_type")
            if row_type == "deal":
                ws2.merge_range(excel_row, start_col, excel_row, start_col + len(DQ_REPORT_COLUMNS) - 1, safe_excel_value(row.get("Item")), deal_fmt)
            elif row_type == "status":
                ws2.merge_range(excel_row, start_col, excel_row, start_col + len(DQ_REPORT_COLUMNS) - 1, safe_excel_value(row.get("Item")), status_fmt)
            elif row_type == "total":
                for i, name in enumerate(DQ_REPORT_COLUMNS):
                    col = start_col + i
                    if name == "Item":
                        ws2.write(excel_row, col, "TOTAL UPB", total_fmt)
                    elif name == "Loan ID":
                        sum_start = row.get("_sum_start")
                        sum_end = row.get("_sum_end")
                        value = safe_excel_value(row.get("Loan ID")) or 0
                        if pd.notna(sum_start) and pd.notna(sum_end) and sum_end >= sum_start:
                            # Current UPB is column L in this layout.
                            formula = f"=SUM(L{int(sum_start)}:L{int(sum_end)})"
                            ws2.write_formula(excel_row, col, formula, total_money_fmt, value)
                        else:
                            ws2.write(excel_row, col, value, total_money_fmt)
                    else:
                        ws2.write_blank(excel_row, col, None, total_fmt)
            else:
                for i, name in enumerate(DQ_REPORT_COLUMNS):
                    col = start_col + i
                    value = safe_excel_value(row.get(name))
                    if name in ["Paid through Date", "Appraisal Date"]:
                        fmt = body_date_fmt
                    elif name in ["Current UPB", "Recent Appraisal"]:
                        fmt = body_money_fmt
                    elif name == "Commentary":
                        fmt = body_wrap_fmt
                    else:
                        fmt = body_fmt
                    if value is None:
                        ws2.write_blank(excel_row, col, None, fmt)
                    else:
                        ws2.write(excel_row, col, value, fmt)

        widths2 = [30, 14, 12, 26, 30, 30, 14, 20, 12, 16, 16, 16, 16, 75]
        for i, width in enumerate(widths2):
            ws2.set_column(start_col + i, start_col + i, width)
        ws2.freeze_panes(header_row + 1, start_col)

    output.seek(0)
    return output

# ============================================================
# UI
# ============================================================

st.subheader("1. Upload this month's RSRV / DLSR files")
dlsr_files = st.file_uploader(
    "Upload all current-month RSRV Excel files that contain a Delinquent Loan Status / DLSR sheet.",
    type=["xls", "xlsx"],
    accept_multiple_files=True,
)

st.subheader("2. Upload this month's dashboard workbook")
current_dashboard_file = st.file_uploader(
    "Used only for the current Term Loan sheet. The app does not use this workbook's DQ Data sheet as a source.",
    type=["xlsx", "xls"],
    accept_multiple_files=False,
    key="current_dashboard",
)

st.subheader("3. Upload last month's dashboard workbook")
prior_dashboard_file = st.file_uploader(
    "Used for carry-forward DQ Table metadata for existing loans.",
    type=["xlsx", "xls"],
    accept_multiple_files=False,
    key="prior_dashboard",
)

use_prior_dq_override = st.checkbox(
    "Use last month's DQ status as an override for existing loans",
    value=False,
    help="Leave unchecked if DQ should always come from current DLSR section headers. Check only for manual carry-forward exceptions.",
)

show_debug = st.checkbox("Show debug staging data", value=False)

generate = st.button("Generate DQ Workbook", type="primary")

if generate:
    if not dlsr_files:
        st.error("Please upload the current month's RSRV / DLSR files.")
        st.stop()
    if current_dashboard_file is None:
        st.error("Please upload this month's dashboard workbook so the app can read Term Loan for new-loan identity fields.")
        st.stop()
    if prior_dashboard_file is None:
        st.error("Please upload last month's dashboard workbook so the app can carry forward existing DQ Table metadata.")
        st.stop()

    with st.spinner("Parsing DLSR files and creating generated DLSR staging data..."):
        dlsr_staging, parse_log = parse_uploaded_dlsr_files(dlsr_files)

    st.subheader("File parsing results")
    st.dataframe(parse_log, width="stretch")

    if dlsr_staging.empty:
        st.error("No DQ loan rows were generated from the uploaded DLSR files.")
        st.stop()

    with st.spinner("Reading current Term Loan and prior DQ Table metadata..."):
        current_term_loan = read_current_term_loan(current_dashboard_file)
        prior_dq_table = read_prior_dq_table(prior_dashboard_file)

    if current_term_loan.empty:
        st.warning("No usable Term Loan rows were found in this month's dashboard. New-loan identity fields may be incomplete.")
    else:
        st.success(f"Loaded current Term Loan metadata: {len(current_term_loan):,} rows")

    if prior_dq_table.empty:
        st.warning("No usable prior DQ Table rows were found. Existing-loan metadata may be incomplete.")
    else:
        st.success(f"Loaded prior DQ Table metadata: {len(prior_dq_table):,} rows")

    dq_table = build_dq_table_from_staging(
        dlsr_staging=dlsr_staging,
        prior_dq_table=prior_dq_table,
        current_term_loan=current_term_loan,
        use_prior_dq_override=use_prior_dq_override,
    )

    if dq_table.empty:
        st.error("DQ Table generation produced no rows.")
        st.stop()

    dq_report = build_dq_loans_by_deal(dq_table)

    report_as_of = pd.NaT
    if "report_as_of_date" in dlsr_staging.columns and dlsr_staging["report_as_of_date"].notna().any():
        report_as_of = pd.to_datetime(dlsr_staging["report_as_of_date"].dropna().iloc[0], errors="coerce")

    if pd.notna(report_as_of):
        report_title = f"Summary of CAFL Deal Loans for {report_as_of.strftime('%B %Y')}, by DQ Status"
        output_name = f"dq_output_{report_as_of.strftime('%Y_%m')}.xlsx"
    else:
        report_title = "Summary of CAFL Deal Loans by DQ Status"
        output_name = "dq_output.xlsx"

    st.subheader("Generated DQ Table")
    st.dataframe(dq_table, width="stretch")

    st.subheader("Generated DQ Loans by Deal")
    st.dataframe(dq_report.drop(columns=["row_type", "_sum_start", "_sum_end"], errors="ignore"), width="stretch")

    st.subheader("Summary by Securitization and DQ")
    summary = (
        dq_table.assign(
            _deal_order=dq_table["Securitization"].map(deal_order_value_table),
            _dq_order=dq_table["DQ"].map(lambda x: dq_order_value(x, report=False)),
        )
        .groupby(["Securitization", "DQ", "_deal_order", "_dq_order"], dropna=False)
        .agg(loan_count=("Loan id", "count"), current_upb=("Current UPB", "sum"))
        .reset_index()
        .sort_values(["_deal_order", "_dq_order"])
        .drop(columns=["_deal_order", "_dq_order"])
    )
    st.dataframe(summary, width="stretch")

    if show_debug:
        st.subheader("Debug: generated DLSR staging dataset")
        st.dataframe(dlsr_staging, width="stretch")
        st.subheader("Debug: current Term Loan metadata")
        st.dataframe(current_term_loan, width="stretch")
        st.subheader("Debug: prior DQ Table metadata")
        st.dataframe(prior_dq_table, width="stretch")

    workbook_bytes = write_output_workbook(dq_table, dq_report, report_title)
    st.download_button(
        label="Download DQ Workbook",
        data=workbook_bytes,
        file_name=output_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
