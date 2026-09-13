import os
import json
import logging
from datetime import datetime

import pandas as pd
import streamlit as st


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

SCHEMA_FILE = os.path.join(
    CONFIG_DIR,
    "schema.json"
)

LOG_FILE = os.path.join(
    LOG_DIR,
    "schema_drift.log"
)

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ============================================================
# STREAMLIT PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="SchemaGuard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("SchemaGuard")


# ============================================================
# SESSION STATE
# ============================================================

if "result" not in st.session_state:
    st.session_state.result = None

if "filename" not in st.session_state:
    st.session_state.filename = None

if "dataframe" not in st.session_state:
    st.session_state.dataframe = None


# ============================================================
# LOAD BASELINE SCHEMA
# ============================================================

@st.cache_data
def load_schema():

    if not os.path.exists(SCHEMA_FILE):

        return None

    with open(
        SCHEMA_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# ============================================================
# TYPE DETECTION
# ============================================================

def detect_column_type(series):
    """
    Detect a logical data type from a pandas Series.

    Returns:
        integer
        float
        boolean
        string
        datetime
    """

    dtype = series.dtype

    # Boolean
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"

    # Integer
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"

    # Float
    if pd.api.types.is_float_dtype(dtype):
        return "float"

    # Datetime
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"

    # Object columns:
    # Try to determine whether values are boolean,
    # integer, float, datetime, or string.
    if pd.api.types.is_object_dtype(dtype):

        non_null = series.dropna()

        if len(non_null) == 0:
            return "string"

        values = (
            non_null
            .astype(str)
            .str.strip()
        )

        # Boolean-like values
        boolean_values = {
            "true",
            "false",
            "yes",
            "no"
        }

        if values.str.lower().isin(
            boolean_values
        ).all():

            return "boolean"

        # Integer-like
        numeric = pd.to_numeric(
            values,
            errors="coerce"
        )

        if numeric.notna().all():

            if (
                numeric % 1 == 0
            ).all():

                return "integer"

            return "float"

        # Date-like
        dates = pd.to_datetime(
            values,
            errors="coerce"
        )

        if dates.notna().all():

            return "datetime"

        return "string"

    return "string"


# ============================================================
# NULLABILITY
# ============================================================

def detect_nullable(series):

    return bool(
        series.isna().any()
    )


# ============================================================
# SCHEMA DRIFT ENGINE
# ============================================================

def compare_schema(
    dataframe,
    baseline_schema
):

    expected_columns = (
        baseline_schema["columns"]
    )

    actual_columns = {}

    # --------------------------------------------------------
    # Build actual schema
    # --------------------------------------------------------

    for column in dataframe.columns:

        actual_columns[column] = {

            "type":
                detect_column_type(
                    dataframe[column]
                ),

            "nullable":
                detect_nullable(
                    dataframe[column]
                )

        }


    expected_names = set(
        expected_columns.keys()
    )

    actual_names = set(
        actual_columns.keys()
    )


    # --------------------------------------------------------
    # Added columns
    # --------------------------------------------------------

    added_columns = sorted(
        actual_names - expected_names
    )


    # --------------------------------------------------------
    # Removed columns
    # --------------------------------------------------------

    removed_columns = sorted(
        expected_names - actual_names
    )


    # --------------------------------------------------------
    # Type changes
    # --------------------------------------------------------

    type_changes = []

    common_columns = sorted(
        expected_names & actual_names
    )

    for column in common_columns:

        expected_type = (
            expected_columns[
                column
            ]["type"]
        )

        actual_type = (
            actual_columns[
                column
            ]["type"]
        )

        if expected_type != actual_type:

            type_changes.append({

                "column": column,

                "expected": expected_type,

                "actual": actual_type

            })


    # --------------------------------------------------------
    # Nullability changes
    # --------------------------------------------------------

    nullability_changes = []

    for column in common_columns:

        expected_nullable = (
            expected_columns[
                column
            ]["nullable"]
        )

        actual_nullable = (
            actual_columns[
                column
            ]["nullable"]
        )

        if expected_nullable != actual_nullable:

            nullability_changes.append({

                "column": column,

                "expected":
                    expected_nullable,

                "actual":
                    actual_nullable

            })


    # --------------------------------------------------------
    # Required column violations
    # --------------------------------------------------------

    required_missing = []

    for column, definition in (
        expected_columns.items()
    ):

        required = definition.get(
            "required",
            False
        )

        if required and column not in actual_names:

            required_missing.append(
                column
            )


    # --------------------------------------------------------
    # Severity
    # --------------------------------------------------------

    critical_count = (
        len(removed_columns)
        + len(type_changes)
        + len(required_missing)
    )

    warning_count = (
        len(added_columns)
        + len(nullability_changes)
    )


    if critical_count > 0:

        severity = "CRITICAL"

    elif warning_count > 0:

        severity = "WARNING"

    else:

        severity = "PASS"


    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {

        "severity": severity,

        "drift_detected":
            severity != "PASS",

        "summary": {

            "added":
                len(added_columns),

            "removed":
                len(removed_columns),

            "type_changes":
                len(type_changes),

            "nullability_changes":
                len(nullability_changes),

            "required_missing":
                len(required_missing)

        },

        "added_columns":
            added_columns,

        "removed_columns":
            removed_columns,

        "type_changes":
            type_changes,

        "nullability_changes":
            nullability_changes,

        "required_missing":
            required_missing,

        "actual_schema":
            actual_columns

    }


# ============================================================
# AUDIT LOG
# ============================================================

def write_audit_log(
    filename,
    dataframe,
    result
):

    summary = result["summary"]

    message = (
        f"FILE={filename} | "
        f"ROWS={len(dataframe)} | "
        f"COLUMNS={len(dataframe.columns)} | "
        f"SEVERITY={result['severity']} | "
        f"ADDED={summary['added']} | "
        f"REMOVED={summary['removed']} | "
        f"TYPE_CHANGES={summary['type_changes']} | "
        f"NULLABILITY_CHANGES="
        f"{summary['nullability_changes']} | "
        f"REQUIRED_MISSING="
        f"{summary['required_missing']}"
    )

    if result["severity"] == "CRITICAL":

        logger.error(message)

    elif result["severity"] == "WARNING":

        logger.warning(message)

    else:

        logger.info(message)


# ============================================================
# LOAD AUDIT LOGS
# ============================================================

def read_logs():

    if not os.path.exists(LOG_FILE):

        return []

    with open(
        LOG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        lines = file.readlines()

    return list(
        reversed(
            lines[-200:]
        )
    )


# ============================================================
# GENERATE REPORT
# ============================================================

def generate_report(
    filename,
    dataframe,
    result
):

    return {

        "timestamp":
            datetime.now().isoformat(),

        "filename":
            filename,

        "rows":
            len(dataframe),

        "columns":
            len(dataframe.columns),

        "validation":
            result

    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🛡️ SchemaGuard")

    st.caption(
        "Schema Drift Monitor"
    )

    st.divider()

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Schema Explorer",
            "Audit Logs"
        ]
    )

    st.divider()

    schema = load_schema()

    if schema:

        st.subheader(
            "Baseline"
        )

        st.write(
            f"**{schema['schema_name']}**"
        )

        st.write(
            f"Version: `{schema['version']}`"
        )

        st.write(
            f"Columns: `{len(schema['columns'])}`"
        )

    else:

        st.error(
            "schema.json not found."
        )


# ============================================================
# DASHBOARD
# ============================================================

if page == "Dashboard":

    st.title(
        "📊 Schema Drift Dashboard"
    )

    st.caption(
        "Upload a CSV and compare it against your expected schema."
    )

    st.divider()


    # --------------------------------------------------------
    # Input method
    # --------------------------------------------------------

    input_method = st.radio(
        "Choose data source",
        [
            "Upload CSV",
            "Use Sample Dataset"
        ],
        horizontal=True
    )


    dataframe = None
    filename = None


    # --------------------------------------------------------
    # Upload CSV
    # --------------------------------------------------------

    if input_method == "Upload CSV":

        uploaded_file = st.file_uploader(
            "Choose a CSV file",
            type=["csv"]
        )

        if uploaded_file:

            filename = uploaded_file.name

            try:

                dataframe = pd.read_csv(
                    uploaded_file
                )

            except Exception as error:

                st.error(
                    f"Could not read CSV: {error}"
                )


    # --------------------------------------------------------
    # Sample data
    # --------------------------------------------------------

    else:

        if not os.path.exists(DATA_DIR):

            st.warning(
                "The data folder does not exist."
            )

        else:

            sample_files = sorted(
                [
                    file
                    for file in os.listdir(
                        DATA_DIR
                    )
                    if file.lower().endswith(
                        ".csv"
                    )
                ]
            )

            if not sample_files:

                st.warning(
                    "No sample CSV files found in data/."
                )

            else:

                selected_file = st.selectbox(
                    "Select sample dataset",
                    sample_files
                )

                sample_path = os.path.join(
                    DATA_DIR,
                    selected_file
                )

                try:

                    dataframe = pd.read_csv(
                        sample_path
                    )

                    filename = selected_file

                except Exception as error:

                    st.error(
                        f"Could not read sample file: {error}"
                    )


    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if dataframe is not None:

        if schema is None:

            st.error(
                "Baseline schema is missing."
            )

            st.stop()


        # ----------------------------------------------------
        # Basic dataset information
        # ----------------------------------------------------

        st.subheader(
            "Dataset Information"
        )

        info1, info2, info3, info4 = st.columns(4)

        with info1:

            st.metric(
                "File",
                filename
            )

        with info2:

            st.metric(
                "Rows",
                f"{len(dataframe):,}"
            )

        with info3:

            st.metric(
                "Columns",
                len(dataframe.columns)
            )

        with info4:

            st.metric(
                "Baseline Columns",
                len(schema["columns"])
            )


        # ----------------------------------------------------
        # Compare
        # ----------------------------------------------------

        result = compare_schema(
            dataframe,
            schema
        )


        st.session_state.result = result
        st.session_state.filename = filename
        st.session_state.dataframe = dataframe


        write_audit_log(
            filename,
            dataframe,
            result
        )


        # ----------------------------------------------------
        # Main status
        # ----------------------------------------------------

        st.divider()

        if result["severity"] == "PASS":

            st.success(
                "✅ PASS — No schema drift detected."
            )

        elif result["severity"] == "WARNING":

            st.warning(
                "⚠️ WARNING — Non-critical schema drift detected."
            )

        else:

            st.error(
                "🚨 CRITICAL — Breaking schema drift detected."
            )


        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        st.subheader(
            "Drift Summary"
        )

        m1, m2, m3, m4, m5 = st.columns(5)

        with m1:

            st.metric(
                "Added",
                result["summary"]["added"]
            )

        with m2:

            st.metric(
                "Removed",
                result["summary"]["removed"]
            )

        with m3:

            st.metric(
                "Type Changes",
                result["summary"]["type_changes"]
            )

        with m4:

            st.metric(
                "Nullability",
                result["summary"]["nullability_changes"]
            )

        with m5:

            st.metric(
                "Required Missing",
                result["summary"]["required_missing"]
            )


        # ----------------------------------------------------
        # Drift details
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "🔎 Drift Details"
        )


        # Added columns

        if result["added_columns"]:

            with st.expander(
                f"🟡 Added Columns ({len(result['added_columns'])})",
                expanded=True
            ):

                for column in result[
                    "added_columns"
                ]:

                    st.warning(
                        f"Added column: `{column}`"
                    )


        # Removed columns

        if result["removed_columns"]:

            with st.expander(
                f"🔴 Removed Columns ({len(result['removed_columns'])})",
                expanded=True
            ):

                for column in result[
                    "removed_columns"
                ]:

                    st.error(
                        f"Missing expected column: `{column}`"
                    )


        # Type changes

        if result["type_changes"]:

            with st.expander(
                f"🔴 Data Type Changes ({len(result['type_changes'])})",
                expanded=True
            ):

                type_rows = []

                for change in result[
                    "type_changes"
                ]:

                    type_rows.append({

                        "Column":
                            change["column"],

                        "Expected":
                            change["expected"],

                        "Actual":
                            change["actual"],

                        "Severity":
                            "CRITICAL"

                    })

                st.dataframe(
                    pd.DataFrame(type_rows),
                    use_container_width=True,
                    hide_index=True
                )


        # Nullability

        if result[
            "nullability_changes"
        ]:

            with st.expander(
                "🟠 Nullability Changes",
                expanded=True
            ):

                null_rows = []

                for change in result[
                    "nullability_changes"
                ]:

                    null_rows.append({

                        "Column":
                            change["column"],

                        "Expected Nullable":
                            change["expected"],

                        "Actual Nullable":
                            change["actual"],

                        "Severity":
                            "WARNING"

                    })

                st.dataframe(
                    pd.DataFrame(null_rows),
                    use_container_width=True,
                    hide_index=True
                )


        # Required missing

        if result[
            "required_missing"
        ]:

            with st.expander(
                "🚨 Required Columns Missing",
                expanded=True
            ):

                for column in result[
                    "required_missing"
                ]:

                    st.error(
                        f"Required column missing: `{column}`"
                    )


        # No drift

        if not result["drift_detected"]:

            st.success(
                "🎉 Dataset schema exactly matches the baseline."
            )


        # ----------------------------------------------------
        # Schema comparison
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "📋 Schema Comparison"
        )


        comparison_rows = []

        expected_columns = (
            schema["columns"]
        )

        actual_columns = (
            result["actual_schema"]
        )


        all_columns = list(
            dict.fromkeys(
                list(expected_columns.keys())
                + list(actual_columns.keys())
            )
        )


        for column in all_columns:

            expected = (
                expected_columns.get(
                    column
                )
            )

            actual = (
                actual_columns.get(
                    column
                )
            )


            expected_type = (
                expected["type"]
                if expected
                else "-"
            )

            actual_type = (
                actual["type"]
                if actual
                else "-"
            )

            expected_nullable = (
                expected["nullable"]
                if expected
                else "-"
            )

            actual_nullable = (
                actual["nullable"]
                if actual
                else "-"
            )


            if (
                expected is None
            ):

                status = "ADDED"

            elif (
                actual is None
            ):

                status = "REMOVED"

            elif (
                expected_type
                != actual_type
            ):

                status = "TYPE DRIFT"

            elif (
                expected_nullable
                != actual_nullable
            ):

                status = "NULLABILITY DRIFT"

            else:

                status = "MATCH"


            comparison_rows.append({

                "Column":
                    column,

                "Expected Type":
                    expected_type,

                "Actual Type":
                    actual_type,

                "Expected Nullable":
                    expected_nullable,

                "Actual Nullable":
                    actual_nullable,

                "Status":
                    status

            })


        comparison_df = pd.DataFrame(
            comparison_rows
        )


        st.dataframe(
            comparison_df,
            use_container_width=True,
            hide_index=True
        )


        # ----------------------------------------------------
        # Dataset preview
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "👁️ Dataset Preview"
        )

        st.dataframe(
            dataframe.head(50),
            use_container_width=True,
            hide_index=True
        )


        # ----------------------------------------------------
        # Report
        # ----------------------------------------------------

        report = generate_report(
            filename,
            dataframe,
            result
        )


        report_json = json.dumps(
            report,
            indent=4,
            default=str
        )


        st.download_button(
            label="📥 Download JSON Report",
            data=report_json,
            file_name="schema_drift_report.json",
            mime="application/json"
        )


# ============================================================
# SCHEMA EXPLORER
# ============================================================

elif page == "Schema Explorer":

    st.title(
        "🔬 Schema Explorer"
    )

    st.caption(
        "Expected baseline schema."
    )

    schema = load_schema()


    if schema is None:

        st.error(
            "schema.json was not found."
        )

        st.stop()


    st.info(
        f"Schema: **{schema['schema_name']}** | "
        f"Version: **{schema['version']}**"
    )


    rows = []


    for column, definition in (
        schema["columns"].items()
    ):

        rows.append({

            "Column":
                column,

            "Type":
                definition["type"],

            "Nullable":
                "Yes"
                if definition["nullable"]
                else "No",

            "Required":
                "Yes"
                if definition["required"]
                else "No"

        })


    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True
    )


    st.subheader(
        "Raw Schema"
    )

    st.json(schema)


# ============================================================
# AUDIT LOGS
# ============================================================

elif page == "Audit Logs":

    st.title(
        "📜 Audit Logs"
    )

    st.caption(
        "Historical schema validation events."
    )


    logs = read_logs()


    if not logs:

        st.info(
            "No validation logs available yet."
        )

    else:

        st.metric(
            "Validation Events",
            len(logs)
        )


        st.divider()


        # Display logs

        for log_line in logs:

            if "CRITICAL" in log_line:

                st.error(
                    log_line.strip()
                )

            elif "WARNING" in log_line:

                st.warning(
                    log_line.strip()
                )

            else:

                st.success(
                    log_line.strip()
                )


        # Download

        with open(
            LOG_FILE,
            "rb"
        ) as file:

            log_data = file.read()


        st.download_button(
            label="📥 Download Audit Log",
            data=log_data,
            file_name="schema_drift.log",
            mime="text/plain"
        )
