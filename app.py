import re
from io import BytesIO

import pandas as pd
import streamlit as st


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="DQ Table Generator",
    page_icon="📊",
    layout="wide",
)

st.title("DQ Table Generator")
st.caption(
    "Upload RSRV / DLSR Excel files to generate the DQ Table and DQ Loans by Deal sheets."
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

        "60": "60-89",
        "60-89": "60-89",
        "60 TO 89 DAYS DELINQUENT": "60-89",
        "60 TO 89 DAYS DELINQUENT": "60-89",

        "30": "30-59",
        "30-59": "30-59",
        "30 TO 59 DAYS DELINQUENT": "30-59",

        "CURRENT AND AT SPECIAL SERVICER": "Current and at Special Servicer",

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

    u = re.sub(r"\bCAF(\d{4})", r"CAF \1", u)
    u = re.sub(r"\bCAFL(\d{4})", r"CAFL \1", u)
    u = re.sub(r"\s+", " ", u).strip()

    mapping = {
        "CAF18-1": "CAF 2018-1",
        "CAF 18-1": "CAF 2018-1",
        "CAF19-2": "CAF 2019-2",
        "CAF 19-2": "CAF 2019-2",
        "CAF 2019-3": "CAF 2019-3",
    }

    return mapping.get(u, u)


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


# ============================================================
# Securitization helpers
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


def deal_sort_key(x):
    x = str(x)

    if x in DEAL_ORDER:
        return (0, DEAL_ORDER.index(x))

    return (1, x)


DQ_ORDER = [
    "90+",
    "60-89",
    "30-59",
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


def dq_sort_key(x):
    x = normalize_dq_status(x)

    if x in DQ_ORDER:
        return DQ_ORDER.index(x)

    return 999


# ============================================================
# DLSR sheet detection
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
            val = cell_to_text(df_raw.loc[r, c])

            if val == "as of":
                if r + 1 in df_raw.index:
                    return parse_report_date(df_raw.loc[r + 1, c])

    return pd.NaT


def classify_section_value(value):
    normalized = normalize_dq_status(value)

    valid_sections = [
        "90+",
        "60-89",
        "30-59",
        "Current and at Special Servicer",
        "Matured Performing",
        "Matured Non-Performing",
    ]

    if normalized in valid_sections:
        return normalized

    return None


# ============================================================
# DLSR parser
# ============================================================

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

    header_row = find_header_row(df_raw)

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

    # DQ status is stored as a section row, not as a column.
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
        df["securitization"] = col_or_na(df, "trans_id").apply(normalize_securitization)
    else:
        df["securitization"] = sec_from_file

    df["securitization"] = df["securitization"].apply(normalize_securitization)

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
        subset=["securitization", "loan_id"],
        keep="first",
    ).copy()

    return dq_data_generated, pd.DataFrame(logs)


# ============================================================
# Prior DQ Table metadata reader
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

    return 1


def read_dq_table_metadata(uploaded_file, sheet_name="DQ Table"):
    file_bytes = uploaded_file.getvalue()

    xl = pd.ExcelFile(BytesIO(file_bytes))

    if sheet_name not in xl.sheet_names:
        return pd.DataFrame()

    dq_table_raw = pd.read_excel(
        BytesIO(file_bytes),
        sheet_name=sheet_name,
        header=None,
    )

    header_row = find_dq_table_header_row(dq_table_raw)

    dq_table = dq_table_raw.iloc[header_row + 1:].copy()
    dq_table.columns = make_unique_columns(dq_table_raw.iloc[header_row])

    dq_table = dq_table.dropna(how="all").copy()

    if "loan_id" not in dq_table.columns:
        return pd.DataFrame()

    dq_table = dq_table[dq_table["loan_id"].notna()].copy()
    dq_table = dq_table[
        dq_table["loan_id"].astype(str).str.contains(r"\d", na=False)
    ].copy()

    dq_table["loan_id"] = dq_table["loan_id"].apply(clean_id_value)

    if "securitization" in dq_table.columns:
        dq_table["securitization"] = dq_table["securitization"].apply(normalize_securitization)

    if "dq" in dq_table.columns:
        dq_table["dq"] = dq_table["dq"].apply(normalize_dq_status)

    return dq_table


# ============================================================
# DQ Table builder
# ============================================================

def build_dq_table_from_dq_data(dq_data, metadata_cache=None):
    d = dq_data.copy()

    dq_source = first_existing_series(
        d,
        ["dq", "dq_from_section", "delinquency_status"],
    )

    d["dq_final"] = dq_source.apply(normalize_dq_status)

    if "securitization" in d.columns:
        d["securitization_final"] = d["securitization"].apply(normalize_securitization)
    elif "trans_id" in d.columns:
        d["securitization_final"] = d["trans_id"].apply(normalize_securitization)
    else:
        d["securitization_final"] = pd.NA

    d["loan_id"] = d["loan_id"].apply(clean_id_value)

    current_upb = first_existing_series(
        d,
        [
            "current_ending_scheduled_balance",
            "current_upb",
            "scheduled_balance",
            "ending_scheduled_balance",
        ],
    )

    recent_appraisal = first_existing_series(
        d,
        [
            "most_recent_value",
            "recent_appraisal",
            "most_recent_appraisal",
        ],
    )

    appraisal_date = first_existing_series(
        d,
        [
            "most_recent_valuation_date",
            "appraisal_date",
            "most_recent_appraisal_date",
        ],
    )

    commentary = first_existing_series(
        d,
        [
            "comments_dlsr",
            "commentary",
            "comments",
        ],
    )

    out = pd.DataFrame({
        "Securitization": d["securitization_final"],
        "DQ": d["dq_final"],
        "Loan id": d["loan_id"],
        "Deal ID": col_or_na(d, "prospectus_loan_id").apply(clean_id_value),
        "Account": col_or_na(d, "property_name"),
        "Borrower Entity": pd.NA,
        "Deal Name": col_or_na(d, "property_name"),
        "Property Type": col_or_na(d, "property_type"),
        "City": col_or_na(d, "property_city"),
        "State": col_or_na(d, "property_state"),
        "Paid Through Date": col_or_na(d, "paid_through_date").apply(parse_report_date),
        "Current UPB": pd.to_numeric(current_upb, errors="coerce"),
        "Recent Appraisal": pd.to_numeric(recent_appraisal, errors="coerce"),
        "Appraisal Date": appraisal_date.apply(parse_report_date),
        "Commentary": commentary,
    })

    # Optional enrichment using a prior/manual DQ Table.
    # These fields are descriptive metadata and are not reliably present in DLSR files.
    if metadata_cache is not None and not metadata_cache.empty:
        e = metadata_cache.copy()
        e["loan_id"] = e["loan_id"].apply(clean_id_value)
        e = e.drop_duplicates(subset=["loan_id"], keep="first")
        e = e.set_index("loan_id")

        enrich_map = {
            "securitization": "Securitization",
            "deal_id": "Deal ID",
            "account": "Account",
            "borrower_entity": "Borrower Entity",
            "deal_name": "Deal Name",
            "property_type": "Property Type",
            "city": "City",
            "state": "State",
        }

        for source_col, target_col in enrich_map.items():
            if source_col not in e.columns:
                continue

            mapped = out["Loan id"].map(e[source_col])

            if target_col == "Securitization":
                out[target_col] = out[target_col].combine_first(mapped)
            else:
                out[target_col] = mapped.combine_first(out[target_col])

    out["Securitization"] = out["Securitization"].apply(normalize_securitization)
    out["Loan id"] = out["Loan id"].apply(clean_id_value)
    out["Deal ID"] = out["Deal ID"].apply(clean_id_value)
    out["DQ"] = out["DQ"].apply(normalize_dq_status)

    out = out.drop_duplicates(
        subset=["Securitization", "Loan id"],
        keep="first",
    ).copy()

    out["_deal_order"] = out["Securitization"].map(lambda x: deal_sort_key(x))
    out["_dq_order"] = out["DQ"].map(lambda x: dq_sort_key(x))
    out["_loan_sort"] = out["Loan id"].astype(str)

    out = out.sort_values(
        by=["_deal_order", "_dq_order", "_loan_sort"],
        ascending=True,
    ).drop(columns=["_deal_order", "_dq_order", "_loan_sort"])

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

    return out[final_cols]


# ============================================================
# DQ Loans by Deal builder
# ============================================================

def build_dq_loans_by_deal(dq_table):
    d = dq_table.copy()

    d["Securitization"] = d["Securitization"].apply(normalize_securitization)
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
        "Recent Appraisal",
        "Appraisal Date",
        "Commentary",
    ]

    rows = []

    deals = sorted(
        d["Securitization"].dropna().unique(),
        key=deal_sort_key,
    )

    for securitization in deals:
        deal_df = d[d["Securitization"].eq(securitization)].copy()

        rows.append({
            "row_type": "deal",
            "Item": securitization,
        })

        for dq_status in DQ_ORDER:
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
                    output_col = "Loan ID" if col == "Loan id" else col
                    row[output_col] = loan[col]

                rows.append(row)

            rows.append({
                "row_type": "total",
                "Item": "TOTAL UPB",
                "Current UPB": status_df["Current UPB"].sum(),
            })

    output_cols = [
        "row_type",
        "Item",
        "Loan ID",
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

    return pd.DataFrame(rows, columns=output_cols)


# ============================================================
# Excel workbook writer
# ============================================================

def build_output_workbook(dq_table, dq_loans_by_deal, report_title):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="m/d/yyyy") as writer:
        workbook = writer.book

        # ----------------------------------------------------
        # DQ Table sheet
        # ----------------------------------------------------
        dq_table.to_excel(writer, sheet_name="DQ Table", index=False)

        ws = writer.sheets["DQ Table"]

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

        for col_num, col_name in enumerate(dq_table.columns):
            ws.write(0, col_num, col_name, header_fmt)

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

        ws.set_column("K:K", 16, date_fmt)
        ws.set_column("L:M", 16, money_fmt)
        ws.set_column("N:N", 16, date_fmt)
        ws.set_column("O:O", 70, wrap_fmt)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(dq_table), len(dq_table.columns) - 1)

        # ----------------------------------------------------
        # DQ Loans by Deal sheet
        # ----------------------------------------------------
        sheet_name = "DQ Loans by Deal"
        ws2 = workbook.add_worksheet(sheet_name)
        writer.sheets[sheet_name] = ws2

        display_grouped = dq_loans_by_deal.drop(columns=["row_type"]).copy()
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

        col_positions = {
            col_name: idx + start_col
            for idx, col_name in enumerate(grouped_cols)
        }

        for row_idx, (_, row) in enumerate(dq_loans_by_deal.iterrows(), start=header_row + 1):
            row_type = row["row_type"]

            if row_type == "deal":
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
                    elif col_name == "Current UPB":
                        ws2.write(
                            row_idx,
                            col_idx,
                            safe_excel_value(row.get("Current UPB")),
                            total_money_fmt,
                        )
                    else:
                        ws2.write_blank(row_idx, col_idx, None, total_fmt)

            else:
                for col_name in grouped_cols:
                    col_idx = col_positions[col_name]
                    value = row.get(col_name)

                    if col_name in ["Paid Through Date", "Appraisal Date"]:
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
# Streamlit UI
# ============================================================

st.subheader("1. Upload DLSR / RSRV Excel files")

dlsr_files = st.file_uploader(
    "Upload all RSRV Excel files that contain a 'Delinquent Loan Status', 'Delinquency Loan Status', or 'DLSR' sheet.",
    type=["xls", "xlsx"],
    accept_multiple_files=True,
)

st.subheader("2. Upload metadata source")

metadata_file = st.file_uploader(
    "Optional but recommended: upload the prior dashboard workbook with a 'DQ Table' sheet. This fills Account, Borrower Entity, Deal Name, City, and State.",
    type=["xls", "xlsx"],
    accept_multiple_files=False,
)

generate = st.button("Generate DQ Workbook", type="primary")

if generate:
    if not dlsr_files:
        st.error("Please upload at least one DLSR / RSRV Excel file.")
        st.stop()

    with st.spinner("Parsing DLSR files..."):
        dq_data_generated, parse_log = parse_uploaded_dlsr_files(dlsr_files)

    st.subheader("File parsing results")
    st.dataframe(parse_log, use_container_width=True)

    if dq_data_generated.empty:
        st.error("No DQ loan rows were generated. Please check that the uploaded files contain DLSR sheets.")
        st.stop()

    st.success(f"Generated DQ Data: {len(dq_data_generated):,} loan rows")

    metadata_cache = None

    if metadata_file is not None:
        with st.spinner("Reading metadata cache from DQ Table..."):
            try:
                metadata_cache = read_dq_table_metadata(metadata_file, sheet_name="DQ Table")

                if metadata_cache.empty:
                    st.warning("Metadata workbook was uploaded, but no usable DQ Table rows were found.")
                else:
                    st.success(f"Loaded metadata cache: {len(metadata_cache):,} rows")

            except Exception as e:
                st.warning(f"Could not read metadata workbook. Continuing without enrichment. Error: {e}")
                metadata_cache = None
    else:
        st.warning(
            "No metadata workbook uploaded. The app will still generate outputs, but descriptive fields "
            "like Account, Borrower Entity, cleaned Deal Name, City, and State may not match the existing manual DQ Table."
        )

    dq_table_generated = build_dq_table_from_dq_data(
        dq_data=dq_data_generated,
        metadata_cache=metadata_cache,
    )

    dq_loans_by_deal = build_dq_loans_by_deal(dq_table_generated)

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
    st.dataframe(dq_table_generated, use_container_width=True)

    st.subheader("Generated DQ Loans by Deal")
    st.dataframe(
        dq_loans_by_deal.drop(columns=["row_type"]),
        use_container_width=True,
    )

    st.subheader("Summary by Securitization and DQ")

    summary = (
        dq_table_generated
        .assign(
            _deal_order=dq_table_generated["Securitization"].map(deal_sort_key),
            _dq_order=dq_table_generated["DQ"].map(dq_sort_key),
        )
        .groupby(["Securitization", "DQ", "_deal_order", "_dq_order"], dropna=False)
        .agg(
            loan_count=("Loan id", "count"),
            current_upb=("Current UPB", "sum"),
        )
        .reset_index()
        .sort_values(["_deal_order", "_dq_order"])
        .drop(columns=["_deal_order", "_dq_order"])
    )

    st.dataframe(summary, use_container_width=True)

    output_workbook = build_output_workbook(
        dq_table=dq_table_generated,
        dq_loans_by_deal=dq_loans_by_deal,
        report_title=report_title,
    )

    st.download_button(
        label="Download DQ Workbook",
        data=output_workbook,
        file_name=output_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
