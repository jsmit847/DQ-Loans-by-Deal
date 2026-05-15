import re
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st


APP_VERSION = "2026-05-15-v12-current-situs-termloan-carryforward"


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="DQ Table Generator",
    page_icon="📊",
    layout="wide",
)

st.title("DQ Table Generator")
st.caption(f"Version {APP_VERSION}")
st.caption(
    "Upload this month's RSRV/DLSR files, this month's dashboard for Term Loan/Situs enrichment, "
    "and last month's dashboard for DQ carry-forward metadata."
)


# ============================================================
# General helpers
# ============================================================


def clean_col_name(col):
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


def make_unique_columns(cols):
    seen = {}
    output = []

    for col in cols:
        base = clean_col_name(col)

        if base in ["", "nan", "none"]:
            base = "blank"

        if base not in seen:
            seen[base] = 0
            output.append(base)
        else:
            seen[base] += 1
            output.append(f"{base}_{seen[base]}")

    return output


def cell_to_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip().lower()


def is_blank_like(x):
    if pd.isna(x):
        return True

    s = str(x).strip()

    if s == "":
        return True

    if s.upper() in {"N/A", "NA", "NAN", "NONE", "NULL", "<NA>", "VARIOUS", "INCOMPLETE", "ZZ", "XX"}:
        return True

    return False


def clean_id_value(x):
    if pd.isna(x):
        return pd.NA

    x = str(x).strip()

    if re.match(r"^\d+\.0$", x):
        x = x.replace(".0", "")

    return x


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

    if re.match(r"^\d+\.0$", s):
        s = s.replace(".0", "")

    if re.match(r"^\d{8}$", s):
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")

    return pd.to_datetime(s, errors="coerce")


def normalize_dq_status(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    u = re.sub(r"\s+", " ", s.upper())

    mapping = {
        "90": "90+",
        "90+": "90+",
        "90 +": "90+",
        "90+ DAYS DELINQUENT": "90+",
        "90 + DAYS DELINQUENT": "90+",
        "90 DAYS DELINQUENT": "90+",
        "90 PLUS DAYS DELINQUENT": "90+",

        "60": "60-89",
        "60-89": "60-89",
        "60 TO 89 DAYS DELINQUENT": "60-89",
        "60 - 89 DAYS DELINQUENT": "60-89",

        "30": "30-59",
        "30-59": "30-59",
        "30 TO 59 DAYS DELINQUENT": "30-59",
        "30 - 59 DAYS DELINQUENT": "30-59",

        "CURRENT AND AT SPECIAL SERVICER": "Current and at Special Servicer",
        "CURRENT & AT SPECIAL SERVICER": "Current and at Special Servicer",

        "MATURED PERFORMING LOANS": "Matured Performing",
        "MATURED PERFORMING": "Matured Performing",

        "MATURED NON-PERFORMING LOANS": "Matured Non-Performing",
        "MATURED NON-PERFORMING": "Matured Non-Performing",
        "MATURED NON PERFORMING": "Matured Non-Performing",
    }

    return mapping.get(u, s)


def normalize_securitization(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    u = re.sub(r"\s+", " ", s.upper())

    u = u.replace("COREVEST AMER", "CAF")
    u = u.replace("COREVEST", "CAF")
    u = u.replace("CVAF", "CAF")

    u = re.sub(r"\bCAF(\d{4})", r"CAF \1", u)
    u = re.sub(r"\bCAFL(\d{4})", r"CAFL \1", u)
    u = re.sub(r"\s+", " ", u).strip()

    mapping = {
        "CAF18-1": "CAF 2018-1",
        "CAF 18-1": "CAF 2018-1",
        "CAF19-2": "CAF 2019-2",
        "CAF 19-2": "CAF 2019-2",
        "CAF 2020 P1": "CAFL 2020-P1",
        "CAF 2022 P2": "CAF 2022-P2",
        "CAF 2023 P1": "CAF 2023-P1",
    }

    return mapping.get(u, u)




def normalize_state(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    if s == "":
        return pd.NA

    state_map = {
        "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
        "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
        "DISTRICT OF COLUMBIA": "DC", "WASHINGTON DC": "DC", "WASHINGTON D.C.": "DC",
        "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
        "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
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

    u = re.sub(r"\s+", " ", s.upper())
    if len(u) == 2:
        return u
    return state_map.get(u, s)


def normalize_property_type(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    u = re.sub(r"\s+", " ", s.upper())

    if u in {"SF", "SFR", "SFRS", "SINGLE FAMILY", "SINGLE-FAMILY", "SINGLE FAMILY RENTAL", "SINGLE FAMILY RENTALS"}:
        return "SF"
    if "SFR" in u or "SINGLE" in u:
        return "SF"
    if u in {"MF", "MULTIFAMILY", "MULTI FAMILY", "MULTI-FAMILY"}:
        return "MF"
    if "MULTI" in u:
        return "MF"

    return s

def dq_table_securitization_display(sec):
    sec = normalize_securitization(sec)

    # Match the existing dashboard quirk exactly.
    special = {
        "CAF 2018-2": "CAF2018-2",
    }

    return special.get(sec, sec)


def report_securitization_display(sec):
    return normalize_securitization(sec)


def col_or_na(df, col):
    if col in df.columns:
        return df[col]
    return pd.Series(pd.NA, index=df.index)


def first_existing_series(df, candidates):
    for col in candidates:
        if col in df.columns:
            return df[col]
    return pd.Series(pd.NA, index=df.index)


def safe_excel_value(value):
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime()

    return value


def coalesce_existing(left, right):
    """Keep left unless it is blank-like, otherwise use right."""
    if isinstance(left, pd.Series):
        out = left.copy()
        mask = out.apply(is_blank_like)
        out.loc[mask] = right.loc[mask]
        return out

    return right if is_blank_like(left) else left


# ============================================================
# Deal / DQ ordering
# ============================================================

DEAL_ORDER = [
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
    "90+": "90+ Days Delinquent",
    "60-89": "60-89 Days Delinquent",
    "30-59": "30-59 Days Delinquent",
    "Current and at Special Servicer": "Current and at Special Servicer",
    "Matured Performing": "Matured Performing Loans",
    "Matured Non-Performing": "Matured Non-Performing Loans",
}


def deal_sort_key(x):
    x = normalize_securitization(x)

    if x in DEAL_ORDER:
        return (0, DEAL_ORDER.index(x))

    return (1, str(x))


def deal_order_value(x):
    x = normalize_securitization(x)

    if x in DEAL_ORDER:
        return DEAL_ORDER.index(x)

    return 999


def dq_order_value(x, order):
    x = normalize_dq_status(x)

    if x in order:
        return order.index(x)

    return 999


# ============================================================
# Securitization helper
# ============================================================


def securitization_from_file(source_file):
    name = str(source_file).strip()

    name = re.sub(r"\.xlsx$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.xls$", "", name, flags=re.IGNORECASE)

    code = name
    code = re.sub(r"^CVAF_", "", code, flags=re.IGNORECASE)
    code = re.sub(r"_RSRV$", "", code, flags=re.IGNORECASE)
    code = code.upper()

    mapping = {
        "20172": "CAF 2017-2",
        "20181": "CAF 2018-1",
        "20182": "CAF 2018-2",
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


# ============================================================
# Generic workbook readers
# ============================================================


def get_sheet_names(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    xl = pd.ExcelFile(BytesIO(file_bytes))
    return xl.sheet_names


def read_sheet_raw(uploaded_file, sheet_name):
    file_bytes = uploaded_file.getvalue()
    return pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)


def find_header_row_by_required_terms(df_raw, required_terms, min_hits=None):
    required_terms = [term.lower() for term in required_terms]
    min_hits = min_hits or len(required_terms)

    for idx in df_raw.index:
        row = [cell_to_text(x) for x in df_raw.loc[idx].tolist()]
        row_text = " | ".join(row)
        hits = sum(1 for term in required_terms if term in row_text)

        if hits >= min_hits:
            return idx

    return None


def sheet_exists(uploaded_file, sheet_name):
    try:
        return sheet_name in get_sheet_names(uploaded_file)
    except Exception:
        return False


# ============================================================
# DLSR parser
# ============================================================


def find_dlsr_sheet(file_bytes):
    xl = pd.ExcelFile(BytesIO(file_bytes))
    sheet_names = xl.sheet_names

    preferred = [
        "Delinquent Loan Status",
        "Delinquency Loan Status",
        "DLSR",
    ]

    for sheet in preferred:
        if sheet in sheet_names:
            return sheet

    for sheet in sheet_names:
        s = sheet.lower()
        if "delinquent" in s or "delinquency" in s or "dlsr" in s:
            return sheet

    return None


def find_dlsr_header_row(df_raw):
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
            val = cell_to_text(df_raw.loc[r, c])

            if val == "as of":
                if r + 1 in df_raw.index:
                    return parse_report_date(df_raw.loc[r + 1, c])

    return pd.NaT


def classify_section_value(value):
    normalized = normalize_dq_status(value)

    if pd.isna(normalized):
        return None

    valid_sections = {
        "90+",
        "60-89",
        "30-59",
        "Current and at Special Servicer",
        "Matured Performing",
        "Matured Non-Performing",
    }

    if str(normalized) in valid_sections:
        return str(normalized)

    return None


def process_dlsr_uploaded_file(uploaded_file):
    source_file = uploaded_file.name
    file_bytes = uploaded_file.getvalue()

    sheet_name = find_dlsr_sheet(file_bytes)

    if sheet_name is None:
        return None, {
            "file": source_file,
            "status": "Skipped",
            "reason": "No DLSR-like sheet found",
        }

    df_raw = pd.read_excel(
        BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=None,
    )

    report_as_of = extract_as_of_date(df_raw)
    header_row = find_dlsr_header_row(df_raw)

    if header_row is None:
        return None, {
            "file": source_file,
            "status": "Skipped",
            "reason": f"Could not find header row on sheet '{sheet_name}'",
        }

    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = df_raw.iloc[header_row].astype(str).str.strip()

    df = df.replace(r"^\s*$", pd.NA, regex=True)

    loan_id_cols = [
        c for c in df.columns
        if clean_col_name(c) == "loan_id"
    ]

    if not loan_id_cols:
        return None, {
            "file": source_file,
            "status": "Skipped",
            "reason": "Loan ID column not found",
        }

    loan_id_col = loan_id_cols[0]

    # DQ status is encoded as section rows, then forward-filled.
    df["dq"] = pd.NA

    first_col = df.columns[0]
    section_candidates = df[first_col].apply(classify_section_value)
    section_mask = section_candidates.notna()

    df.loc[section_mask, "dq"] = section_candidates[section_mask]
    df["dq"] = df["dq"].ffill()

    # Keep actual loan rows only.
    df = df[df[loan_id_col].notna()].copy()
    df = df[
        df[loan_id_col].astype(str).str.contains(r"\d", na=False)
    ].copy()

    df.columns = make_unique_columns(df.columns)

    df["source_file"] = source_file
    df["source_sheet"] = sheet_name
    df["source_header_row"] = header_row
    df["report_as_of_date"] = report_as_of

    sec_from_file = securitization_from_file(source_file)

    if pd.isna(sec_from_file):
        df["securitization_key"] = col_or_na(df, "trans_id").apply(normalize_securitization)
    else:
        df["securitization_key"] = sec_from_file

    df["securitization_key"] = df["securitization_key"].apply(normalize_securitization)

    if "loan_id" not in df.columns:
        return None, {
            "file": source_file,
            "status": "Skipped",
            "reason": "Loan ID column missing after column cleanup",
        }

    df["loan_id"] = df["loan_id"].apply(clean_id_value)

    if "prospectus_loan_id" in df.columns:
        df["prospectus_loan_id"] = df["prospectus_loan_id"].apply(clean_id_value)

    return df, {
        "file": source_file,
        "status": "Parsed",
        "reason": f"Sheet '{sheet_name}', header row {header_row}, rows {len(df)}",
    }


def parse_uploaded_dlsr_files(uploaded_files):
    parsed = []
    logs = []

    for uploaded_file in uploaded_files:
        if not uploaded_file.name.lower().endswith((".xls", ".xlsx")):
            logs.append({
                "file": uploaded_file.name,
                "status": "Skipped",
                "reason": "Not an Excel file",
            })
            continue

        try:
            result, log = process_dlsr_uploaded_file(uploaded_file)
            logs.append(log)

            if result is not None and not result.empty:
                parsed.append(result)

        except Exception as e:
            logs.append({
                "file": uploaded_file.name,
                "status": "Error",
                "reason": str(e),
            })

    if not parsed:
        return pd.DataFrame(), pd.DataFrame(logs)

    dq_data_generated = pd.concat(parsed, ignore_index=True)

    dq_data_generated = dq_data_generated.drop_duplicates(
        subset=["securitization_key", "loan_id"],
        keep="first",
    ).copy()

    return dq_data_generated, pd.DataFrame(logs)


# ============================================================
# Current month dashboard enrichment readers
# ============================================================


def read_current_term_loan_metadata(uploaded_file):
    if uploaded_file is None or not sheet_exists(uploaded_file, "Term Loan"):
        return pd.DataFrame()

    raw = read_sheet_raw(uploaded_file, "Term Loan")

    header_row = find_header_row_by_required_terms(
        raw,
        ["deal number", "servicer id", "deal name", "borrower entity", "account name"],
        min_hits=4,
    )

    if header_row is None:
        return pd.DataFrame()

    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()

    # Term Loan: Servicer ID is the best match to DLSR Loan ID; Deal Number is dashboard Deal ID.
    if "servicer_id" not in df.columns:
        return pd.DataFrame()

    df["loan_id"] = df["servicer_id"].apply(clean_id_value)
    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()

    out = pd.DataFrame({
        "loan_id": df["loan_id"],
        "term_deal_id": col_or_na(df, "deal_number").apply(clean_id_value),
        "term_account": col_or_na(df, "account_name"),
        "term_borrower_entity": col_or_na(df, "borrower_entity"),
        "term_deal_name": col_or_na(df, "deal_name"),
        "term_portfolio": col_or_na(df, "portfolio"),
        "term_segment": col_or_na(df, "segment"),
    })

    out = out.drop_duplicates(subset=["loan_id"], keep="first")
    return out


def read_current_data_metadata(uploaded_file):
    if uploaded_file is None or not sheet_exists(uploaded_file, "Data"):
        return pd.DataFrame()

    raw = read_sheet_raw(uploaded_file, "Data")

    header_row = find_header_row_by_required_terms(
        raw,
        ["asset id", "asset name", "current upb", "city", "property type"],
        min_hits=4,
    )

    if header_row is None:
        return pd.DataFrame()

    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()

    if "asset_id" not in df.columns:
        return pd.DataFrame()

    df["loan_id"] = df["asset_id"].apply(clean_id_value)
    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()

    out = pd.DataFrame({
        "loan_id": df["loan_id"],
        "data_securitization": col_or_na(df, "deal_id").apply(normalize_securitization),
        "data_account": col_or_na(df, "status"),
        "data_deal_name": col_or_na(df, "asset_name"),
        "data_property_type": col_or_na(df, "property_type").apply(normalize_property_type),
        "data_city": col_or_na(df, "city"),
        "data_state": first_existing_series(df, ["st", "state"]).apply(normalize_state),
        "data_paid_through_date": col_or_na(df, "next_payment_due_date").apply(parse_report_date),
        "data_current_upb": pd.to_numeric(col_or_na(df, "current_upb"), errors="coerce"),
        "data_appraisal_date": first_existing_series(df, ["valuationdate", "valuation_date"]).apply(parse_report_date),
        "data_recent_appraisal": pd.to_numeric(first_existing_series(df, ["valuation_amount", "valuation_amount_1"]), errors="coerce"),
    })

    out = out.drop_duplicates(subset=["loan_id"], keep="first")
    return out


def read_current_situs_metadata(uploaded_file):
    """Read this month's Situs sheet.

    Situs is the preferred source for property/reporting fields such as
    property type, city, state, paid-through date, current balance, valuation,
    and comments. Term Loan remains the source for Deal ID, Account,
    Borrower Entity, and Deal Name.
    """
    if uploaded_file is None or not sheet_exists(uploaded_file, "Situs"):
        return pd.DataFrame()

    raw = read_sheet_raw(uploaded_file, "Situs")

    header_row = find_header_row_by_required_terms(
        raw,
        [
            "servicer loan number",
            "deal name",
            "securitization name",
            "current principal balance",
            "paid to date",
        ],
        min_hits=4,
    )

    if header_row is None:
        return pd.DataFrame()

    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()

    if "servicer_loan_number" not in df.columns:
        return pd.DataFrame()

    df["loan_id"] = df["servicer_loan_number"].apply(clean_id_value)
    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()

    out = pd.DataFrame({
        "loan_id": df["loan_id"],
        "situs_securitization": col_or_na(df, "securitization_name").apply(normalize_securitization),
        "situs_property_type": col_or_na(df, "property_type").apply(normalize_property_type),
        "situs_city": col_or_na(df, "city"),
        "situs_state": col_or_na(df, "state").apply(normalize_state),
        "situs_paid_through_date": col_or_na(df, "paid_to_date").apply(parse_report_date),
        "situs_current_upb": pd.to_numeric(col_or_na(df, "current_principal_balance"), errors="coerce"),
        "situs_recent_appraisal": pd.to_numeric(col_or_na(df, "valuation_amount"), errors="coerce"),
        "situs_appraisal_date": col_or_na(df, "valuation_date").apply(parse_report_date),
        "situs_commentary": col_or_na(df, "comments"),
    })

    return out.drop_duplicates(subset=["loan_id"], keep="first")


def build_current_month_enrichment(current_dashboard_file):
    term = read_current_term_loan_metadata(current_dashboard_file)
    situs = read_current_situs_metadata(current_dashboard_file)
    data = read_current_data_metadata(current_dashboard_file)

    frames = [df for df in [term, situs, data] if df is not None and not df.empty]

    if not frames:
        return pd.DataFrame()

    merged = frames[0].copy()
    for df in frames[1:]:
        merged = merged.merge(df, on="loan_id", how="outer")

    return merged.drop_duplicates(subset=["loan_id"], keep="first")


# ============================================================
# Last month dashboard carry-forward readers
# ============================================================


def find_dq_table_header_row(df_raw):
    for idx in df_raw.index:
        row = [cell_to_text(x) for x in df_raw.loc[idx].tolist()]
        row_text = " ".join(row)

        has_securitization = "securitization" in row_text
        has_loan = "loan id" in row_text or "loan_id" in row_text
        has_dq = any(x == "dq" for x in row)

        if has_securitization and has_loan and has_dq:
            return idx

    return None


def read_dq_table_from_dashboard(uploaded_file, preferred_sheets=None):
    if uploaded_file is None:
        return pd.DataFrame()

    preferred_sheets = preferred_sheets or ["DQ Table", "old DQ Table"]

    sheet_names = get_sheet_names(uploaded_file)

    selected_sheet = None
    for sheet in preferred_sheets:
        if sheet in sheet_names:
            selected_sheet = sheet
            break

    if selected_sheet is None:
        return pd.DataFrame()

    raw = read_sheet_raw(uploaded_file, selected_sheet)
    header_row = find_dq_table_header_row(raw)

    if header_row is None:
        return pd.DataFrame()

    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()

    if "loan_id" not in df.columns:
        return pd.DataFrame()

    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()
    df["loan_id"] = df["loan_id"].apply(clean_id_value)

    if "securitization" in df.columns:
        df["securitization"] = df["securitization"].apply(normalize_securitization)

    if "dq" in df.columns:
        df["dq"] = df["dq"].apply(normalize_dq_status)

    df["carry_source_sheet"] = selected_sheet
    return df.drop_duplicates(subset=["loan_id"], keep="first")


def read_dq_loans_by_deal_from_dashboard(uploaded_file, preferred_sheets=None):
    if uploaded_file is None:
        return pd.DataFrame()

    preferred_sheets = preferred_sheets or ["DQ Loans by Deal", "OLD DQ Loans by Deal"]
    sheet_names = get_sheet_names(uploaded_file)

    selected_sheet = None
    for sheet in preferred_sheets:
        if sheet in sheet_names:
            selected_sheet = sheet
            break

    if selected_sheet is None:
        return pd.DataFrame()

    raw = read_sheet_raw(uploaded_file, selected_sheet)

    header_row = find_header_row_by_required_terms(
        raw,
        ["loan id", "deal id", "current upb", "recent appraisal", "appraisal date"],
        min_hits=4,
    )

    if header_row is None:
        return pd.DataFrame()

    df = raw.iloc[header_row + 1:].copy()
    df.columns = make_unique_columns(raw.iloc[header_row])
    df = df.dropna(how="all").copy()

    if "loan_id" not in df.columns:
        return pd.DataFrame()

    df = df[df["loan_id"].notna()].copy()
    df = df[df["loan_id"].astype(str).str.contains(r"\d", na=False)].copy()
    df["loan_id"] = df["loan_id"].apply(clean_id_value)

    out = pd.DataFrame({
        "loan_id": df["loan_id"],
        "group_recent_appraisal": pd.to_numeric(col_or_na(df, "recent_appraisal"), errors="coerce"),
        "group_appraisal_date": col_or_na(df, "appraisal_date").apply(parse_report_date),
    })

    return out.drop_duplicates(subset=["loan_id"], keep="first")


def build_last_month_carryforward(last_dashboard_file):
    dq_table = read_dq_table_from_dashboard(last_dashboard_file, ["DQ Table", "old DQ Table"])
    grouped = read_dq_loans_by_deal_from_dashboard(last_dashboard_file, ["DQ Loans by Deal", "OLD DQ Loans by Deal"])

    if dq_table.empty and grouped.empty:
        return pd.DataFrame()

    if dq_table.empty:
        merged = grouped.copy()
    elif grouped.empty:
        merged = dq_table.copy()
    else:
        merged = dq_table.merge(grouped, on="loan_id", how="outer")

    return merged.drop_duplicates(subset=["loan_id"], keep="first")


# ============================================================
# DQ Table builder
# ============================================================


def build_dq_table_from_dq_data(
    dq_data,
    current_month_enrichment=None,
    last_month_carryforward=None,
    use_manual_dq_overrides=False,
):
    d = dq_data.copy()

    d["loan_id"] = d["loan_id"].apply(clean_id_value)

    if current_month_enrichment is not None and not current_month_enrichment.empty:
        d = d.merge(current_month_enrichment, on="loan_id", how="left")

    if last_month_carryforward is not None and not last_month_carryforward.empty:
        d = d.merge(
            last_month_carryforward,
            on="loan_id",
            how="left",
            suffixes=("", "_carry"),
        )

    dq_source = first_existing_series(d, ["dq", "dq_from_section", "delinquency_status"])
    d["dq_final"] = dq_source.apply(normalize_dq_status)

    if use_manual_dq_overrides and "dq_carry" in d.columns:
        carry_dq = d["dq_carry"].apply(normalize_dq_status)
        d["dq_final"] = carry_dq.combine_first(d["dq_final"])
    elif use_manual_dq_overrides and "dq" in d.columns and "dq_carry" not in d.columns:
        # No-op branch retained for clarity.
        d["dq_final"] = d["dq_final"]

    if "securitization_key" in d.columns:
        d["securitization_final"] = d["securitization_key"].apply(normalize_securitization)
    elif "securitization" in d.columns:
        d["securitization_final"] = d["securitization"].apply(normalize_securitization)
    elif "trans_id" in d.columns:
        d["securitization_final"] = d["trans_id"].apply(normalize_securitization)
    else:
        d["securitization_final"] = pd.NA

    # Current dashboard fallback for securitization if filename/trans ID were unavailable.
    if "situs_securitization" in d.columns:
        d["securitization_final"] = coalesce_existing(d["securitization_final"], d["situs_securitization"])
    if "data_securitization" in d.columns:
        d["securitization_final"] = coalesce_existing(d["securitization_final"], d["data_securitization"])

    # Situs is the preferred source for these current-month report fields.
    # DLSR remains the fallback because the DQ loan population/status comes from DLSR.
    current_upb = first_existing_series(
        d,
        [
            "situs_current_upb",
            "current_ending_scheduled_balance",
            "current_upb",
            "data_current_upb",
            "scheduled_balance",
            "ending_scheduled_balance",
        ],
    )

    recent_appraisal = first_existing_series(
        d,
        [
            "situs_recent_appraisal",
            "most_recent_value",
            "recent_appraisal",
            "group_recent_appraisal",
            "data_recent_appraisal",
            "most_recent_appraisal",
        ],
    )

    appraisal_date = first_existing_series(
        d,
        [
            "situs_appraisal_date",
            "most_recent_valuation_date",
            "appraisal_date",
            "group_appraisal_date",
            "data_appraisal_date",
            "most_recent_appraisal_date",
        ],
    )

    paid_through = first_existing_series(
        d,
        [
            "situs_paid_through_date",
            "paid_through_date",
            "paid_through_date_carry",
            "data_paid_through_date",
        ],
    )

    commentary = first_existing_series(
        d,
        [
            "situs_commentary",
            "comments_dlsr",
            "commentary",
            "comments",
        ],
    )

    out = pd.DataFrame({
        "Securitization": d["securitization_final"].apply(dq_table_securitization_display),
        "_Securitization Key": d["securitization_final"].apply(normalize_securitization),
        "DQ": d["dq_final"],
        "Loan id": d["loan_id"],
        "Deal ID": col_or_na(d, "prospectus_loan_id").apply(clean_id_value),
        "Account": col_or_na(d, "property_name"),
        "Borrower Entity": pd.NA,
        "Deal Name": col_or_na(d, "property_name"),
        "Property Type": col_or_na(d, "property_type"),
        "City": col_or_na(d, "property_city"),
        "State": col_or_na(d, "property_state"),
        "Paid Through Date": paid_through.apply(parse_report_date),
        "Current UPB": pd.to_numeric(current_upb, errors="coerce"),
        "Recent Appraisal": pd.to_numeric(recent_appraisal, errors="coerce"),
        "Appraisal Date": appraisal_date.apply(parse_report_date),
        "Commentary": commentary,
    })

    # 1. Carry-forward old/manual DQ Table metadata for existing loans.
    # Do not overwrite current fields like DQ, Paid Through, Current UPB, Commentary.
    if last_month_carryforward is not None and not last_month_carryforward.empty:
        e = last_month_carryforward.copy()
        e["loan_id"] = e["loan_id"].apply(clean_id_value)
        e = e.drop_duplicates(subset=["loan_id"], keep="first").set_index("loan_id")

        carry_map = {
            "securitization": ("Securitization", dq_table_securitization_display),
            "deal_id": ("Deal ID", clean_id_value),
            "account": ("Account", None),
            "borrower_entity": ("Borrower Entity", None),
            "deal_name": ("Deal Name", None),
            "property_type": ("Property Type", None),
            "city": ("City", None),
            "state": ("State", None),
        }

        for source_col, (target_col, transform) in carry_map.items():
            if source_col not in e.columns:
                continue
            mapped = out["Loan id"].map(e[source_col])
            if transform is not None:
                mapped = mapped.apply(transform)
            out[target_col] = mapped.combine_first(out[target_col])

        # DQ Loans by Deal often carries appraisal fields more completely than DLSR.
        if "group_recent_appraisal" in e.columns:
            mapped = pd.to_numeric(out["Loan id"].map(e["group_recent_appraisal"]), errors="coerce")
            out["_Carry Recent Appraisal"] = mapped
        else:
            out["_Carry Recent Appraisal"] = pd.NA

        if "group_appraisal_date" in e.columns:
            mapped = out["Loan id"].map(e["group_appraisal_date"]).apply(parse_report_date)
            out["_Carry Appraisal Date"] = mapped
        else:
            out["_Carry Appraisal Date"] = pd.NaT
    else:
        out["_Carry Recent Appraisal"] = pd.NA
        out["_Carry Appraisal Date"] = pd.NaT

    # 2. Current month enrichment.
    # Term Loan owns: Deal ID, Account, Borrower Entity, Deal Name.
    # Situs owns: property type, city, state, paid-through date, UPB, valuation, comments.
    # Data remains only a low-priority fallback if Situs is missing/blank.
    if current_month_enrichment is not None and not current_month_enrichment.empty:
        e = current_month_enrichment.copy()
        e["loan_id"] = e["loan_id"].apply(clean_id_value)
        e = e.drop_duplicates(subset=["loan_id"], keep="first").set_index("loan_id")

        term_map = {
            "term_deal_id": "Deal ID",
            "term_account": "Account",
            "term_borrower_entity": "Borrower Entity",
            "term_deal_name": "Deal Name",
        }

        for source_col, target_col in term_map.items():
            if source_col not in e.columns:
                continue
            mapped = out["Loan id"].map(e[source_col])
            if target_col == "Deal ID":
                mapped = mapped.apply(clean_id_value)
            # Term Loan is authoritative for these metadata fields when present.
            out[target_col] = mapped.combine_first(out[target_col])

        situs_map = {
            "situs_property_type": "Property Type",
            "situs_city": "City",
            "situs_state": "State",
            "situs_paid_through_date": "Paid Through Date",
            "situs_current_upb": "Current UPB",
            "situs_recent_appraisal": "Recent Appraisal",
            "situs_appraisal_date": "Appraisal Date",
            "situs_commentary": "Commentary",
        }

        for source_col, target_col in situs_map.items():
            if source_col not in e.columns:
                continue
            mapped = out["Loan id"].map(e[source_col])
            if target_col in ["Paid Through Date", "Appraisal Date"]:
                mapped = mapped.apply(parse_report_date)
            if target_col in ["Current UPB", "Recent Appraisal"]:
                mapped = pd.to_numeric(mapped, errors="coerce")
            if target_col == "Property Type":
                mapped = mapped.apply(normalize_property_type)
            if target_col == "State":
                mapped = mapped.apply(normalize_state)
            # Situs is authoritative for these current-month reporting fields when present.
            out[target_col] = mapped.combine_first(out[target_col])

        data_fallback_map = {
            "data_property_type": "Property Type",
            "data_city": "City",
            "data_state": "State",
            "data_paid_through_date": "Paid Through Date",
            "data_current_upb": "Current UPB",
            "data_recent_appraisal": "Recent Appraisal",
            "data_appraisal_date": "Appraisal Date",
        }

        for source_col, target_col in data_fallback_map.items():
            if source_col not in e.columns:
                continue
            mapped = out["Loan id"].map(e[source_col])
            if target_col in ["Paid Through Date", "Appraisal Date"]:
                mapped = mapped.apply(parse_report_date)
            if target_col in ["Current UPB", "Recent Appraisal"]:
                mapped = pd.to_numeric(mapped, errors="coerce")
            if target_col == "Property Type":
                mapped = mapped.apply(normalize_property_type)
            if target_col == "State":
                mapped = mapped.apply(normalize_state)
            out[target_col] = coalesce_existing(out[target_col], mapped)

    out["Securitization"] = out["Securitization"].apply(dq_table_securitization_display)
    out["_Securitization Key"] = out["_Securitization Key"].apply(normalize_securitization)
    out["Loan id"] = out["Loan id"].apply(clean_id_value)
    out["Deal ID"] = out["Deal ID"].apply(clean_id_value)
    out["DQ"] = out["DQ"].apply(normalize_dq_status)
    out["Property Type"] = out["Property Type"].apply(normalize_property_type)
    out["State"] = out["State"].apply(normalize_state)

    # For the grouped report, prefer carry-forward appraisal values where present,
    # then the generated/current DQ Table values.
    out["_Report Recent Appraisal"] = coalesce_existing(
        out["_Carry Recent Appraisal"],
        out["Recent Appraisal"],
    )
    out["_Report Appraisal Date"] = coalesce_existing(
        out["_Carry Appraisal Date"],
        out["Appraisal Date"],
    )

    out = out.drop_duplicates(
        subset=["_Securitization Key", "Loan id"],
        keep="first",
    ).copy()

    out["_deal_order"] = out["_Securitization Key"].map(deal_order_value)
    out["_dq_order"] = out["DQ"].map(lambda x: dq_order_value(x, DQ_TABLE_ORDER))
    out["_loan_sort"] = out["Loan id"].astype(str)

    out = out.sort_values(
        by=["_deal_order", "_dq_order", "_loan_sort"],
        ascending=True,
    ).drop(columns=["_deal_order", "_dq_order", "_loan_sort"])

    return out


def dq_table_display_frame(dq_table_internal):
    final_cols = [
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
    return dq_table_internal[final_cols].copy()


# ============================================================
# DQ Loans by Deal builder
# ============================================================


def build_dq_loans_by_deal(dq_table_internal):
    d = dq_table_internal.copy()

    d["_Securitization Key"] = d["_Securitization Key"].apply(normalize_securitization)
    d["DQ"] = d["DQ"].apply(normalize_dq_status)
    d["Current UPB"] = pd.to_numeric(d["Current UPB"], errors="coerce")

    detail_cols = [
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
        "_Report Recent Appraisal",
        "_Report Appraisal Date",
        "Commentary",
    ]

    rows = []

    for securitization in DEAL_ORDER:
        deal_df = d[d["_Securitization Key"].eq(securitization)].copy()

        rows.append({
            "row_type": "deal",
            "Item": report_securitization_display(securitization),
        })

        if deal_df.empty:
            rows.append({
                "row_type": "total",
                "Item": "TOTAL UPB",
                "Loan ID": None,
                "_sum_current_upb": 0,
            })
            continue

        for dq_status in DQ_REPORT_ORDER:
            status_df = deal_df[deal_df["DQ"].eq(dq_status)].copy()

            if status_df.empty:
                continue

            status_df["_loan_sort"] = status_df["Loan id"].astype(str)
            status_df = status_df.sort_values("_loan_sort").drop(columns=["_loan_sort"])

            rows.append({
                "row_type": "status",
                "Item": DQ_DISPLAY.get(dq_status, dq_status),
            })

            for _, loan in status_df.iterrows():
                row = {
                    "row_type": "loan",
                    "Item": pd.NA,
                }

                for col in detail_cols:
                    if col == "Loan id":
                        output_col = "Loan ID"
                    elif col == "_Report Recent Appraisal":
                        output_col = "Recent Appraisal"
                    elif col == "_Report Appraisal Date":
                        output_col = "Appraisal Date"
                    else:
                        output_col = col

                    row[output_col] = loan[col]

                rows.append(row)

            rows.append({
                "row_type": "total",
                "Item": "TOTAL UPB",
                "Loan ID": None,
                "_sum_current_upb": status_df["Current UPB"].sum(),
            })

    output_cols = [
        "row_type",
        "Item",
        "Loan ID",
        "Deal ID",
        "Account",
        "Borrower Entitity",
        "Deal Name",
        "Property Type",
        "City",
        "State",
        "Paid through Date",
        "Current UPB",
        "Recent Appraisal",
        "Appraisal Date",
        "Commentary",
        "_sum_current_upb",
    ]

    grouped = pd.DataFrame(rows)

    rename_map = {
        "Borrower Entity": "Borrower Entitity",
        "Paid Through Date": "Paid through Date",
    }
    grouped = grouped.rename(columns=rename_map)

    for col in output_cols:
        if col not in grouped.columns:
            grouped[col] = pd.NA

    return grouped[output_cols]


# ============================================================
# Excel workbook writer
# ============================================================


def excel_col_name(col_idx):
    """Convert zero-based column index to Excel letter."""
    name = ""
    col_idx += 1
    while col_idx:
        col_idx, remainder = divmod(col_idx - 1, 26)
        name = chr(65 + remainder) + name
    return name


def build_output_workbook(dq_table_internal, dq_loans_by_deal, report_title):
    output = BytesIO()
    dq_table = dq_table_display_frame(dq_table_internal)

    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="m/d/yyyy") as writer:
        workbook = writer.book

        # ----------------------------------------------------
        # Formats
        # ----------------------------------------------------
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAD3",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        })
        date_fmt = workbook.add_format({"num_format": "m/d/yyyy"})
        money_fmt = workbook.add_format({"num_format": "$#,##0.00"})
        wrap_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})

        # ----------------------------------------------------
        # DQ Table sheet: blank first row, headers on row 2.
        # ----------------------------------------------------
        sheet_name = "DQ Table"
        ws = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = ws

        start_row = 1
        for col_num, col_name in enumerate(dq_table.columns):
            ws.write(start_row, col_num, col_name, header_fmt)

        for r_idx, (_, row) in enumerate(dq_table.iterrows(), start=start_row + 1):
            for c_idx, col_name in enumerate(dq_table.columns):
                value = safe_excel_value(row[col_name])

                if col_name in ["Paid Through Date", "Appraisal Date"]:
                    fmt = date_fmt
                elif col_name in ["Current UPB", "Recent Appraisal"]:
                    fmt = money_fmt
                elif col_name == "Commentary":
                    fmt = wrap_fmt
                else:
                    fmt = None

                if value is None:
                    ws.write_blank(r_idx, c_idx, None, fmt)
                else:
                    ws.write(r_idx, c_idx, value, fmt)

        widths = {
            "A": 18,
            "B": 16,
            "C": 14,
            "D": 12,
            "E": 24,
            "F": 28,
            "G": 28,
            "H": 14,
            "I": 18,
            "J": 12,
            "K": 16,
            "L": 16,
            "M": 16,
            "N": 16,
            "O": 70,
        }
        for col_letter, width in widths.items():
            ws.set_column(f"{col_letter}:{col_letter}", width)

        ws.freeze_panes(2, 0)
        ws.autofilter(start_row, 0, start_row + len(dq_table), len(dq_table.columns) - 1)

        # ----------------------------------------------------
        # DQ Loans by Deal sheet
        # ----------------------------------------------------
        sheet_name = "DQ Loans by Deal"
        ws2 = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = ws2

        display_grouped = dq_loans_by_deal.drop(columns=["row_type", "_sum_current_upb"]).copy()
        grouped_cols = display_grouped.columns.tolist()

        title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 14,
            "align": "left",
        })
        header_fmt_2 = workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAD3",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        })
        deal_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#C6E0B4",
            "border": 1,
        })
        status_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#E2F0D9",
            "border": 1,
        })
        total_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#FFF2CC",
            "border": 1,
        })
        total_money_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#FFF2CC",
            "border": 1,
            "num_format": "$#,##0.00",
        })
        loan_fmt = workbook.add_format({
            "border": 1,
            "valign": "top",
        })
        loan_date_fmt = workbook.add_format({
            "border": 1,
            "num_format": "m/d/yyyy",
            "valign": "top",
        })
        loan_money_fmt = workbook.add_format({
            "border": 1,
            "num_format": "$#,##0.00",
            "valign": "top",
        })
        loan_wrap_fmt = workbook.add_format({
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        })

        ws2.write(0, 1, report_title, title_fmt)

        header_row = 3
        start_col = 1

        for col_num, col_name in enumerate(grouped_cols, start=start_col):
            ws2.write(header_row, col_num, col_name, header_fmt_2)

        col_positions = {col_name: idx + start_col for idx, col_name in enumerate(grouped_cols)}
        loan_id_col_idx = col_positions.get("Loan ID")

        current_loan_start_row = None
        current_loan_end_row = None
        current_upb_col_idx = col_positions.get("Current UPB")

        for row_idx, (_, row) in enumerate(dq_loans_by_deal.iterrows(), start=header_row + 1):
            row_type = row["row_type"]

            if row_type == "deal":
                current_loan_start_row = None
                current_loan_end_row = None
                label = row.get("Item", "")
                ws2.merge_range(
                    row_idx,
                    start_col,
                    row_idx,
                    start_col + len(grouped_cols) - 1,
                    label,
                    deal_fmt,
                )

            elif row_type == "status":
                current_loan_start_row = None
                current_loan_end_row = None
                label = row.get("Item", "")
                ws2.merge_range(
                    row_idx,
                    start_col,
                    row_idx,
                    start_col + len(grouped_cols) - 1,
                    label,
                    status_fmt,
                )

            elif row_type == "total":
                for col_name in grouped_cols:
                    col_idx = col_positions[col_name]

                    if col_name == "Item":
                        ws2.write(row_idx, col_idx, "TOTAL UPB", total_fmt)
                    elif col_name == "Loan ID":
                        if current_loan_start_row is not None and current_loan_end_row is not None and current_upb_col_idx is not None:
                            col_letter = excel_col_name(current_upb_col_idx)
                            # XlsxWriter row indexes are zero-based; Excel formulas are one-based.
                            start_excel_row = current_loan_start_row + 1
                            end_excel_row = current_loan_end_row + 1
                            formula = f"=SUM({col_letter}{start_excel_row}:{col_letter}{end_excel_row})"
                            ws2.write_formula(row_idx, col_idx, formula, total_money_fmt)
                        else:
                            ws2.write_blank(row_idx, col_idx, None, total_money_fmt)
                    else:
                        ws2.write_blank(row_idx, col_idx, None, total_fmt)

                current_loan_start_row = None
                current_loan_end_row = None

            else:
                if current_loan_start_row is None:
                    current_loan_start_row = row_idx
                current_loan_end_row = row_idx

                for col_name in grouped_cols:
                    col_idx = col_positions[col_name]
                    value = row.get(col_name)

                    if col_name in ["Paid through Date", "Appraisal Date"]:
                        fmt = loan_date_fmt
                    elif col_name in ["Current UPB", "Recent Appraisal"]:
                        fmt = loan_money_fmt
                    elif col_name == "Commentary":
                        fmt = loan_wrap_fmt
                    else:
                        fmt = loan_fmt

                    value = safe_excel_value(value)
                    if value is None:
                        ws2.write_blank(row_idx, col_idx, None, fmt)
                    else:
                        ws2.write(row_idx, col_idx, value, fmt)

        grouped_widths = {
            "B": 30,
            "C": 14,
            "D": 12,
            "E": 24,
            "F": 28,
            "G": 28,
            "H": 14,
            "I": 18,
            "J": 12,
            "K": 16,
            "L": 16,
            "M": 16,
            "N": 16,
            "O": 70,
        }

        for col_letter, width in grouped_widths.items():
            ws2.set_column(f"{col_letter}:{col_letter}", width)

        ws2.freeze_panes(header_row + 1, start_col)

    output.seek(0)
    return output


# ============================================================
# Validation helpers
# ============================================================


def validate_against_current_dashboard(dq_table_internal, current_dashboard_file):
    if current_dashboard_file is None or not sheet_exists(current_dashboard_file, "DQ Table"):
        return None, None

    target = read_dq_table_from_dashboard(current_dashboard_file, ["DQ Table"])
    if target.empty:
        return None, None

    generated = dq_table_display_frame(dq_table_internal).copy()
    generated.columns = [clean_col_name(c) for c in generated.columns]
    generated["loan_id"] = generated["loan_id"].apply(clean_id_value)

    target["loan_id"] = target["loan_id"].apply(clean_id_value)

    compare_rows = generated.merge(
        target,
        on="loan_id",
        how="outer",
        suffixes=("_generated", "_target"),
        indicator=True,
    )

    cols_to_compare = [
        "securitization",
        "dq",
        "deal_id",
        "account",
        "borrower_entity",
        "deal_name",
        "property_type",
        "city",
        "state",
        "paid_through_date",
        "current_upb",
        "recent_appraisal",
        "appraisal_date",
        "commentary",
    ]

    def norm_compare_value(x):
        if pd.isna(x):
            return ""
        if isinstance(x, pd.Timestamp):
            return x.strftime("%Y-%m-%d")
        if hasattr(x, "strftime") and not isinstance(x, str):
            try:
                return pd.Timestamp(x).strftime("%Y-%m-%d")
            except Exception:
                pass
        s = str(x).strip()
        if re.match(r"^\d+\.0$", s):
            s = s.replace(".0", "")
        s = re.sub(r"\s+", " ", s)
        return s

    mismatch_frames = []
    matched = compare_rows[compare_rows["_merge"].eq("both")].copy()

    for col in cols_to_compare:
        gen_col = f"{col}_generated"
        tgt_col = f"{col}_target"
        if gen_col not in matched.columns or tgt_col not in matched.columns:
            continue
        left = matched[gen_col].apply(norm_compare_value)
        right = matched[tgt_col].apply(norm_compare_value)
        mask = left.ne(right)
        temp = matched.loc[mask, ["loan_id"]].copy()
        temp["field"] = col
        temp["generated_value"] = matched.loc[mask, gen_col].values
        temp["target_value"] = matched.loc[mask, tgt_col].values
        mismatch_frames.append(temp)

    if mismatch_frames:
        mismatches = pd.concat(mismatch_frames, ignore_index=True)
    else:
        mismatches = pd.DataFrame(columns=["loan_id", "field", "generated_value", "target_value"])

    return compare_rows, mismatches


# ============================================================
# Streamlit UI
# ============================================================

st.subheader("1. Upload this month's RSRV / DLSR Excel files")

dlsr_files = st.file_uploader(
    "Upload all RSRV Excel files that contain a 'Delinquent Loan Status', 'Delinquency Loan Status', or 'DLSR' sheet.",
    type=["xls", "xlsx"],
    accept_multiple_files=True,
)

st.subheader("2. Upload this month's dashboard workbook")

current_dashboard_file = st.file_uploader(
    "Required: upload this month's dashboard workbook. The app uses Term Loan for deal metadata and Situs for property/reporting fields.",
    type=["xls", "xlsx"],
    accept_multiple_files=False,
    key="current_dashboard",
)

st.subheader("3. Upload last month's dashboard workbook")

last_dashboard_file = st.file_uploader(
    "Required: upload last month's dashboard workbook. The app uses its DQ Table / DQ Loans by Deal sheets as carry-forward metadata.",
    type=["xls", "xlsx"],
    accept_multiple_files=False,
    key="last_dashboard",
)

use_manual_dq_overrides = st.checkbox(
    "Use last month's DQ values as overrides when available",
    value=False,
    help=(
        "Leave this unchecked if DLSR section rows are the source of truth. "
        "Check only if you want prior/manual DQ values to override the current DLSR status."
    ),
)

generate = st.button("Generate DQ Workbook", type="primary")

if generate:
    if not dlsr_files:
        st.error("Please upload at least one DLSR / RSRV Excel file.")
        st.stop()

    if current_dashboard_file is None:
        st.error("Please upload this month's dashboard workbook so the app can read the Term Loan and Situs sheets.")
        st.stop()

    if last_dashboard_file is None:
        st.error("Please upload last month's dashboard workbook so the app can carry forward prior DQ metadata.")
        st.stop()

    with st.spinner("Parsing DLSR files..."):
        dq_data_generated, parse_log = parse_uploaded_dlsr_files(dlsr_files)

    st.subheader("File parsing results")
    st.dataframe(parse_log, width="stretch")

    if dq_data_generated.empty:
        st.error("No DQ loan rows were generated. Please check that the uploaded files contain DLSR sheets.")
        st.stop()

    st.success(f"Generated DQ Data: {len(dq_data_generated):,} loan rows")

    with st.spinner("Reading current month Term Loan and Situs enrichment..."):
        current_enrichment = build_current_month_enrichment(current_dashboard_file)

    if current_enrichment.empty:
        st.warning("No current-month enrichment rows were found from Term Loan/Situs.")
    else:
        st.success(f"Loaded current-month enrichment rows: {len(current_enrichment):,}")

    with st.spinner("Reading last month carry-forward metadata..."):
        last_carryforward = build_last_month_carryforward(last_dashboard_file)

    if last_carryforward.empty:
        st.warning("No last-month carry-forward rows were found from DQ Table / DQ Loans by Deal.")
    else:
        st.success(f"Loaded last-month carry-forward rows: {len(last_carryforward):,}")

    dq_table_internal = build_dq_table_from_dq_data(
        dq_data=dq_data_generated,
        current_month_enrichment=current_enrichment,
        last_month_carryforward=last_carryforward,
        use_manual_dq_overrides=use_manual_dq_overrides,
    )

    dq_table_generated = dq_table_display_frame(dq_table_internal)
    dq_loans_by_deal = build_dq_loans_by_deal(dq_table_internal)

    report_as_of = pd.NaT
    if (
        "report_as_of_date" in dq_data_generated.columns
        and dq_data_generated["report_as_of_date"].notna().any()
    ):
        report_as_of = pd.to_datetime(
            dq_data_generated["report_as_of_date"].dropna().iloc[0],
            errors="coerce",
        )

    if pd.notna(report_as_of):
        report_title = f"Summary of CAFL Deal Loans for {report_as_of.strftime('%B %Y')}, by DQ Status"
        output_name = f"dq_output_{report_as_of.strftime('%Y_%m')}.xlsx"
    else:
        report_title = "Summary of CAFL Deal Loans by DQ Status"
        output_name = "dq_output.xlsx"

    st.subheader("Generated DQ Table")
    st.dataframe(dq_table_generated, width="stretch")

    st.subheader("Generated DQ Loans by Deal")
    st.dataframe(
        dq_loans_by_deal.drop(columns=["row_type", "_sum_current_upb"]),
        width="stretch",
    )

    st.subheader("Summary by Securitization and DQ")
    summary = (
        dq_table_internal
        .assign(
            _deal_order=dq_table_internal["_Securitization Key"].map(deal_order_value),
            _dq_order=dq_table_internal["DQ"].map(lambda x: dq_order_value(x, DQ_REPORT_ORDER)),
        )
        .groupby(["_Securitization Key", "DQ", "_deal_order", "_dq_order"], dropna=False)
        .agg(
            loan_count=("Loan id", "count"),
            current_upb=("Current UPB", "sum"),
        )
        .reset_index()
        .rename(columns={"_Securitization Key": "Securitization"})
        .sort_values(["_deal_order", "_dq_order"])
        .drop(columns=["_deal_order", "_dq_order"])
    )
    st.dataframe(summary, width="stretch")

    with st.expander("Optional validation against this month's dashboard DQ Table"):
        compare_rows, field_mismatches = validate_against_current_dashboard(
            dq_table_internal,
            current_dashboard_file,
        )

        if compare_rows is None:
            st.info("This month's dashboard does not have a readable DQ Table for validation.")
        else:
            st.write("Row match counts:")
            st.dataframe(compare_rows["_merge"].value_counts().reset_index(), width="stretch")

            st.write("Field mismatch summary:")
            if field_mismatches.empty:
                st.success("No field mismatches found against the current dashboard DQ Table.")
            else:
                mismatch_summary = (
                    field_mismatches
                    .groupby("field")
                    .size()
                    .reset_index(name="mismatch_count")
                    .sort_values("mismatch_count", ascending=False)
                )
                st.dataframe(mismatch_summary, width="stretch")
                st.dataframe(field_mismatches, width="stretch")

    output_workbook = build_output_workbook(
        dq_table_internal=dq_table_internal,
        dq_loans_by_deal=dq_loans_by_deal,
        report_title=report_title,
    )

    st.download_button(
        label="Download DQ Workbook",
        data=output_workbook,
        file_name=output_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
