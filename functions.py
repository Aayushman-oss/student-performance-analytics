"""Shared validation and analytics engine for the Student Performance Analytics System.

Every number shown anywhere in the application (Streamlit pages, command-line
report, CSV downloads) is produced by the functions in this module, so the
different views can never disagree with each other.

This module has no dependency on Streamlit.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration (single source of truth for schema and rules)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET_PATH = BASE_DIR / "data" / "students.csv"
OUTPUT_DIR = BASE_DIR / "outputs"

ID_COL = "Student_ID"
NAME_COL = "Name"
DEPT_COL = "Department"
ATT_COL = "Attendance"

# The subject columns are listed explicitly so that Student_ID or Attendance
# can never be mistaken for a subject.
SUBJECTS = ["Python", "Statistics", "NumPy", "Pandas", "Data_Analysis"]

REQUIRED_COLUMNS = [ID_COL, NAME_COL, DEPT_COL, *SUBJECTS, ATT_COL]
TOTAL_COL = "Total_Marks"
AVG_COL = "Average_Marks"
GRADE_COL = "Grade"
RESULT_COL = "Result"
DERIVED_COLUMNS = [TOTAL_COL, AVG_COL, GRADE_COL, RESULT_COL]

# Column order of the analysed dataset.
ANALYSED_COLUMNS = [
    ID_COL, NAME_COL, DEPT_COL, *SUBJECTS,
    TOTAL_COL, AVG_COL, GRADE_COL, RESULT_COL, ATT_COL,
]

MIN_VALUE = 0.0
MAX_VALUE = 100.0

# Project-defined rules (NOT prescribed by the assignment).
PASS_AVERAGE = 40.0          # average must be at least this ...
PASS_SUBJECT_MARK = 35.0     # ... and every subject must be at least this
ATTENDANCE_THRESHOLD = 75.0  # "low attendance" means strictly below this

GRADE_BOUNDS = [(90.0, "A+"), (80.0, "A"), (70.0, "B"), (60.0, "C"), (50.0, "D")]
GRADE_ORDER = ["A+", "A", "B", "C", "D", "F"]
PASS = "Pass"
FAIL = "Fail"

SORT_OPTIONS = {
    "Average marks": AVG_COL,
    "Total marks": TOTAL_COL,
    "Name": NAME_COL,
    "Attendance": ATT_COL,
}

COLUMN_LABELS = {
    ID_COL: "Student ID",
    NAME_COL: "Name",
    DEPT_COL: "Department",
    "Data_Analysis": "Data Analysis",
    TOTAL_COL: "Total Marks",
    AVG_COL: "Average Marks",
    GRADE_COL: "Grade",
    RESULT_COL: "Result",
    ATT_COL: "Attendance (%)",
}

# Validation categories (used by the Dataset Management page checklist).
CAT_FILE = "File can be read"
CAT_COLUMNS = "Required columns present"
CAT_ROWS = "Contains student records"
CAT_MISSING = "No missing values"
CAT_NUMERIC = "Marks and attendance are numeric"
CAT_DUPLICATE = "Student IDs are unique"
CAT_MARKS = "Marks within 0-100"
CAT_ATTENDANCE = "Attendance within 0-100"
CHECK_ORDER = [
    CAT_FILE, CAT_COLUMNS, CAT_ROWS, CAT_MISSING,
    CAT_NUMERIC, CAT_DUPLICATE, CAT_MARKS, CAT_ATTENDANCE,
]


def label(column: str) -> str:
    """Human-friendly label for a column or subject name (table headers)."""
    return COLUMN_LABELS.get(column, column.replace("_", " "))


def plain_label(column: str) -> str:
    """Label without unit suffixes, for use inside sentences and error messages."""
    return "Attendance" if column == ATT_COL else label(column)


# ---------------------------------------------------------------------------
# Core rules: grade and pass/fail (one reusable function each)
# ---------------------------------------------------------------------------

def calculate_grade(average: float) -> str:
    """Return the grade for an average mark using the documented bands.

    90-100 A+, 80-<90 A, 70-<80 B, 60-<70 C, 50-<60 D, below 50 F.
    """
    if average is None or not np.isfinite(average):
        raise ValueError("Average must be a finite number.")
    if average < MIN_VALUE or average > MAX_VALUE:
        raise ValueError(f"Average must be between 0 and 100, got {average}.")
    for lower_bound, grade in GRADE_BOUNDS:
        if average >= lower_bound:
            return grade
    return "F"


def determine_result(average: float, subject_marks) -> str:
    """Return 'Pass' or 'Fail'.

    A student passes only if the average is at least 40 AND every subject
    mark is at least 35.
    """
    if average >= PASS_AVERAGE and all(mark >= PASS_SUBJECT_MARK for mark in subject_marks):
        return PASS
    return FAIL


# ---------------------------------------------------------------------------
# Validation and loading
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    category: str
    message: str


@dataclass
class ValidationResult:
    """Outcome of loading and validating a dataset."""

    source_name: str = ""
    data: pd.DataFrame | None = None            # analysed data, only when valid
    issues: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    raw_preview: pd.DataFrame | None = None     # first rows exactly as read
    raw_rows: int = 0
    raw_columns: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues and self.data is not None

    @property
    def errors(self) -> list:
        return [issue.message for issue in self.issues]

    def failed_categories(self) -> set:
        return {issue.category for issue in self.issues}

    def checklist(self) -> list:
        """List of (check name, passed) in a fixed order for display."""
        failed = self.failed_categories()
        return [(name, name not in failed) for name in CHECK_ORDER]


def _as_text(series: pd.Series) -> pd.Series:
    """Convert a column to stripped strings; missing values become ''."""
    return series.astype("object").where(series.notna(), "").astype(str).str.strip()


def _rows(positions, limit: int = 8) -> str:
    """Format row numbers (CSV line numbers; the header is line 1)."""
    numbers = [int(p) + 2 for p in positions]
    shown = ", ".join(str(n) for n in numbers[:limit])
    extra = len(numbers) - limit
    return f"row {shown}" if len(numbers) == 1 else (
        f"rows {shown}" + (f" and {extra} more" if extra > 0 else "")
    )


def validate_dataframe(raw: pd.DataFrame, source_name: str = "") -> ValidationResult:
    """Validate a raw table and, when valid, return it analysed.

    All problems are collected so that the user can fix them in one pass.
    Invalid values are never converted silently (for example to zero).
    """
    result = ValidationResult(source_name=source_name)
    if raw is None or raw.shape[1] == 0:
        result.issues.append(ValidationIssue(CAT_FILE, "The file contains no columns."))
        return result

    df = raw.copy().reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    result.raw_rows, result.raw_columns = df.shape
    result.raw_preview = df.head(50)

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_columns:
        result.issues.append(ValidationIssue(
            CAT_COLUMNS,
            "Missing required column(s): " + ", ".join(missing_columns)
            + ". Column names must match exactly: " + ", ".join(REQUIRED_COLUMNS) + ".",
        ))
        return result
    if len(df) == 0:
        result.issues.append(ValidationIssue(
            CAT_ROWS, "The file has column headers but no student records."))
        return result

    text = {col: _as_text(df[col]) for col in REQUIRED_COLUMNS}

    # Text fields: ID, name, department.
    for col in (ID_COL, NAME_COL, DEPT_COL):
        blank = np.flatnonzero((text[col] == "").to_numpy())
        if len(blank):
            result.issues.append(ValidationIssue(
                CAT_MISSING, f"{plain_label(col)} is empty in {_rows(blank)}."))

    # Numeric fields: subject marks and attendance.
    numeric = {}
    for col in [*SUBJECTS, ATT_COL]:
        blank_mask = (text[col] == "").to_numpy()
        values = pd.to_numeric(text[col], errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(values)
        bad_mask = ~blank_mask & ~finite
        if blank_mask.any():
            result.issues.append(ValidationIssue(
                CAT_MISSING, f"{plain_label(col)} is missing in {_rows(np.flatnonzero(blank_mask))}. "
                             "Missing values are not replaced with zero; please fill them in."))
        if bad_mask.any():
            examples = ", ".join(f"'{v}'" for v in text[col][bad_mask].unique()[:3])
            result.issues.append(ValidationIssue(
                CAT_NUMERIC, f"{plain_label(col)} has non-numeric value(s) {examples} "
                             f"in {_rows(np.flatnonzero(bad_mask))}."))
        out_of_range = finite & ((values < MIN_VALUE) | (values > MAX_VALUE))
        if out_of_range.any():
            category = CAT_ATTENDANCE if col == ATT_COL else CAT_MARKS
            examples = ", ".join(f"{v:g}" for v in values[out_of_range][:3])
            result.issues.append(ValidationIssue(
                category, f"{plain_label(col)} must be between 0 and 100, but found {examples} "
                          f"in {_rows(np.flatnonzero(out_of_range))}."))
        numeric[col] = values

    # Duplicate IDs (blank IDs are already reported above).
    ids = text[ID_COL]
    duplicated = ids[(ids != "") & ids.duplicated(keep=False)]
    for student_id in duplicated.unique():
        positions = np.flatnonzero((ids == student_id).to_numpy())
        result.issues.append(ValidationIssue(
            CAT_DUPLICATE, f"Student ID '{student_id}' appears more than once ({_rows(positions)})."))

    if [c for c in DERIVED_COLUMNS if c in df.columns]:
        result.warnings.append(
            "Columns " + ", ".join(c for c in DERIVED_COLUMNS if c in df.columns)
            + " were found in the file and ignored; they are recalculated by the application.")

    if result.issues:
        return result

    clean = pd.DataFrame({ID_COL: ids, NAME_COL: text[NAME_COL], DEPT_COL: text[DEPT_COL]})
    for col in [*SUBJECTS, ATT_COL]:
        clean[col] = numeric[col]
    for col in df.columns:  # keep any extra user columns untouched
        if col not in REQUIRED_COLUMNS and col not in DERIVED_COLUMNS:
            clean[col] = df[col]
    result.data = analyze_students(clean)
    return result


def load_students_csv(source, source_name: str | None = None) -> ValidationResult:
    """Read and validate a CSV from a path, bytes, or an uploaded-file object.

    Never raises for bad input; problems are returned as validation issues.
    """
    name = source_name or ""

    def fail(message: str, category: str = CAT_FILE) -> ValidationResult:
        return ValidationResult(source_name=name, issues=[ValidationIssue(category, message)])

    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            name = name or path.name
            if not path.is_file():
                return fail(f"File not found: {path}")
            content = path.read_bytes()
        elif isinstance(source, (bytes, bytearray)):
            content = bytes(source)
        elif hasattr(source, "getvalue"):
            content = source.getvalue()
            name = name or getattr(source, "name", "")
        elif hasattr(source, "read"):
            content = source.read()
        else:
            return fail("Unsupported file source.")

        if isinstance(content, str):
            content = content.encode("utf-8")
        if not content.strip():
            return fail("The file is empty.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return fail("The file is not valid UTF-8 text. Save it as a CSV (UTF-8) and try again.")

        # Every row must have exactly as many fields as the header. Without this
        # check pandas could silently shift columns for rows with extra fields.
        reader = csv.reader(StringIO(text))
        header = next(reader, [])
        wrong = [(reader.line_num, len(row)) for row in reader if row and len(row) != len(header)]
        if wrong:
            examples = "; ".join(f"line {line} has {count} fields" for line, count in wrong[:3])
            more = f" (and {len(wrong) - 3} more)" if len(wrong) > 3 else ""
            return fail(f"The file is not a well-formed CSV: the header has {len(header)} columns but "
                        f"{examples}{more}.")

        raw = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False, index_col=False)
        raw = raw.fillna("")
    except pd.errors.EmptyDataError:
        return fail("The file is empty or has no readable header row.")
    except pd.errors.ParserError as exc:
        return fail(f"The file is not a well-formed CSV: {exc}")
    except Exception as exc:  # defensive: an upload must never crash the app
        return fail(f"The file could not be read: {exc}")

    return validate_dataframe(raw, name)


# ---------------------------------------------------------------------------
# Per-student calculations
# ---------------------------------------------------------------------------

def analyze_students(df: pd.DataFrame) -> pd.DataFrame:
    """Add Total_Marks, Average_Marks, Grade and Result to a clean dataset.

    Full precision is kept; rounding happens only when data is displayed or
    exported. Totals are rounded to 6 decimals so floating-point noise (for
    example 399.99999999) can never push a student into the wrong grade band.
    """
    out = df.drop(columns=[c for c in DERIVED_COLUMNS if c in df.columns]).copy()
    marks = out[SUBJECTS].to_numpy(dtype=float)           # NumPy matrix: students x subjects
    total = np.round(marks.sum(axis=1), 6)
    average = total / len(SUBJECTS)

    grades, results = [], []
    for i in range(len(out)):                              # loop over students
        grades.append(calculate_grade(float(average[i])))
        results.append(determine_result(float(average[i]), marks[i]))

    out[TOTAL_COL] = total
    out[AVG_COL] = average
    out[GRADE_COL] = grades
    out[RESULT_COL] = results
    extras = [c for c in out.columns if c not in ANALYSED_COLUMNS]
    return out[ANALYSED_COLUMNS + extras].reset_index(drop=True)


def _pct(count: int, total: int) -> float:
    return float(count) / total * 100.0 if total else 0.0


def reconciliation_check(df: pd.DataFrame) -> dict:
    """Independent re-computation used to prove that the figures reconcile."""
    n = len(df)
    marks = df[SUBJECTS].to_numpy(dtype=float)
    return {
        "students": n,
        "grade_total": int(df[GRADE_COL].isin(GRADE_ORDER).sum()),
        "result_total": int(df[RESULT_COL].isin([PASS, FAIL]).sum()),
        "grades_reconcile": int(df[GRADE_COL].isin(GRADE_ORDER).sum()) == n,
        "results_reconcile": int(df[RESULT_COL].isin([PASS, FAIL]).sum()) == n,
        "totals_match": bool(np.allclose(df[TOTAL_COL], marks.sum(axis=1))) if n else True,
        "averages_match": bool(np.allclose(df[AVG_COL], marks.sum(axis=1) / len(SUBJECTS))) if n else True,
    }


# ---------------------------------------------------------------------------
# Class-level metrics
# ---------------------------------------------------------------------------

def extreme_students(df: pd.DataFrame, column: str, highest: bool = True) -> pd.DataFrame:
    """All students tied for the highest (or lowest) value of a column."""
    if df.empty:
        return df.copy()
    target = df[column].max() if highest else df[column].min()
    return df[np.isclose(df[column].to_numpy(dtype=float), target)].sort_values(ID_COL)


def top_students(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Top-n students by average marks.

    Uses competition ranking ("1, 2, 2, 4"): every student whose rank is <= n
    is included, so students tied at the cut-off are not dropped. With fewer
    than n students, all students are returned.
    """
    columns = ["Rank", ID_COL, NAME_COL, DEPT_COL, TOTAL_COL, AVG_COL, GRADE_COL, RESULT_COL]
    if df.empty:
        return pd.DataFrame(columns=columns)
    ranked = df.copy()
    ranked["Rank"] = ranked[AVG_COL].rank(method="min", ascending=False).astype(int)
    ranked = ranked[ranked["Rank"] <= n].sort_values(["Rank", ID_COL])
    return ranked[columns].reset_index(drop=True)


def class_summary(df: pd.DataFrame) -> dict:
    """Headline metrics for the dashboard and the reports."""
    n = len(df)
    summary = {"total_students": n, "total_subjects": len(SUBJECTS)}
    if n == 0:
        return summary
    passed = int((df[RESULT_COL] == PASS).sum())
    failed = n - passed
    stats = subject_statistics(df)
    best, worst = best_and_lowest_subjects(stats)
    summary.update({
        "class_average": float(df[AVG_COL].mean()),
        "highest_average": float(df[AVG_COL].max()),
        "lowest_average": float(df[AVG_COL].min()),
        "highest_total": float(df[TOTAL_COL].max()),
        "lowest_total": float(df[TOTAL_COL].min()),
        "highest_students": extreme_students(df, AVG_COL, True)[NAME_COL].tolist(),
        "lowest_students": extreme_students(df, AVG_COL, False)[NAME_COL].tolist(),
        "pass_count": passed,
        "fail_count": failed,
        "pass_percentage": _pct(passed, n),
        "fail_percentage": _pct(failed, n),
        "average_attendance": float(df[ATT_COL].mean()),
        "best_subjects": best,
        "lowest_subjects": worst,
    })
    return summary


def subject_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Average, highest, lowest, median and pass/fail counts for each subject.

    Only the explicit SUBJECTS columns are used (never Attendance or IDs).
    A student passes a subject with at least PASS_SUBJECT_MARK.
    """
    columns = ["Subject", "Average", "Highest", "Lowest", "Median", "Passing", "Failing"]
    rows = []
    for subject in SUBJECTS:                               # loop over subjects
        values = df[subject].to_numpy(dtype=float)
        if values.size == 0:
            continue
        rows.append({
            "Subject": subject,
            "Average": float(np.mean(values)),
            "Highest": float(np.max(values)),
            "Lowest": float(np.min(values)),
            "Median": float(np.median(values)),
            "Passing": int(np.sum(values >= PASS_SUBJECT_MARK)),
            "Failing": int(np.sum(values < PASS_SUBJECT_MARK)),
        })
    return pd.DataFrame(rows, columns=columns)


def best_and_lowest_subjects(stats: pd.DataFrame) -> tuple:
    """Subject(s) with the highest and lowest average (all ties returned)."""
    if stats.empty:
        return [], []
    averages = stats["Average"].to_numpy(dtype=float)
    best = stats.loc[np.isclose(averages, averages.max()), "Subject"].tolist()
    lowest = stats.loc[np.isclose(averages, averages.min()), "Subject"].tolist()
    return best, lowest


def grade_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Count and percentage for every grade (grades with zero students included)."""
    counts = df[GRADE_COL].value_counts().reindex(GRADE_ORDER, fill_value=0)
    n = len(df)
    return pd.DataFrame({
        "Grade": GRADE_ORDER,
        "Students": counts.to_numpy(dtype=int),
        "Percentage": [_pct(int(c), n) for c in counts],
    })


def result_distribution(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    passed = int((df[RESULT_COL] == PASS).sum())
    failed = int((df[RESULT_COL] == FAIL).sum())
    return pd.DataFrame({
        "Result": [PASS, FAIL],
        "Students": [passed, failed],
        "Percentage": [_pct(passed, n), _pct(failed, n)],
    })


def department_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-department size, average marks and pass/fail statistics.

    Departments are discovered from the data (no fixed list). Sorted by
    average marks (highest first), then name.
    """
    columns = [DEPT_COL, "Students", "Average_Marks", "Passed", "Failed", "Pass_Percentage"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    work = df.assign(_passed=(df[RESULT_COL] == PASS).astype(int))
    grouped = work.groupby(DEPT_COL, as_index=False).agg(
        Students=(ID_COL, "count"),
        Average_Marks=(AVG_COL, "mean"),
        Passed=("_passed", "sum"),
    )
    grouped["Failed"] = grouped["Students"] - grouped["Passed"]
    grouped["Pass_Percentage"] = grouped["Passed"] / grouped["Students"] * 100.0
    grouped = grouped.sort_values(["Average_Marks", DEPT_COL], ascending=[False, True])
    return grouped[columns].reset_index(drop=True)


def best_departments(summary: pd.DataFrame) -> list:
    """Department(s) with the highest average marks (ties included)."""
    if summary.empty:
        return []
    values = summary["Average_Marks"].to_numpy(dtype=float)
    return summary.loc[np.isclose(values, values.max()), DEPT_COL].tolist()


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def attendance_summary(df: pd.DataFrame, threshold: float = ATTENDANCE_THRESHOLD) -> dict:
    n = len(df)
    summary = {"threshold": threshold, "students": n}
    if n == 0:
        return summary
    below = int((df[ATT_COL] < threshold).sum())
    summary.update({
        "average": float(df[ATT_COL].mean()),
        "highest": float(df[ATT_COL].max()),
        "lowest": float(df[ATT_COL].min()),
        "highest_students": extreme_students(df, ATT_COL, True)[NAME_COL].tolist(),
        "lowest_students": extreme_students(df, ATT_COL, False)[NAME_COL].tolist(),
        "below_count": below,
        "at_least_count": n - below,
    })
    return summary


def low_attendance_students(df: pd.DataFrame, threshold: float = ATTENDANCE_THRESHOLD) -> pd.DataFrame:
    """Students strictly below the threshold, lowest attendance first."""
    return df[df[ATT_COL] < threshold].sort_values([ATT_COL, ID_COL]).reset_index(drop=True)


ATTENDANCE_BINS = [0, 50, 60, 70, 75, 85, 95, np.inf]
ATTENDANCE_BIN_LABELS = ["0 to <50", "50 to <60", "60 to <70", "70 to <75",
                         "75 to <85", "85 to <95", "95 to 100"]


def attendance_distribution(df: pd.DataFrame) -> pd.DataFrame:
    bands = pd.cut(df[ATT_COL], bins=ATTENDANCE_BINS, labels=ATTENDANCE_BIN_LABELS, right=False)
    counts = bands.value_counts().reindex(ATTENDANCE_BIN_LABELS, fill_value=0)
    return pd.DataFrame({"Attendance band": ATTENDANCE_BIN_LABELS, "Students": counts.to_numpy(dtype=int)})


def attendance_marks_correlation(df: pd.DataFrame):
    """Pearson correlation between attendance and average marks, or None.

    Returns None when it cannot be computed meaningfully (fewer than three
    students, or no variation in one of the variables).
    """
    if len(df) < 3:
        return None
    x = df[ATT_COL].to_numpy(dtype=float)
    y = df[AVG_COL].to_numpy(dtype=float)
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def mark_distribution(values, bin_width: int = 10) -> pd.DataFrame:
    """Histogram of marks in left-closed bins; the last bin includes 100."""
    edges = list(range(0, 100 + bin_width, bin_width))
    counts, _ = np.histogram(np.asarray(values, dtype=float), bins=edges)
    labels = [f"{edges[i]} to <{edges[i + 1]}" for i in range(len(edges) - 2)]
    labels.append(f"{edges[-2]} to {edges[-1]}")
    return pd.DataFrame({"Marks range": labels, "Students": counts.astype(int)})


# ---------------------------------------------------------------------------
# Filtering and individual analysis
# ---------------------------------------------------------------------------

def filter_students(
    df: pd.DataFrame,
    search: str = "",
    departments=None,
    grades=None,
    results=None,
    attendance_range=(MIN_VALUE, MAX_VALUE),
    sort_by: str = AVG_COL,
    ascending: bool = False,
) -> pd.DataFrame:
    """Return a filtered, sorted copy; the source dataset is never modified.

    Empty or None lists mean "no restriction". Search matches Student ID or
    name (case-insensitive, partial).
    """
    if sort_by not in SORT_OPTIONS.values():
        raise ValueError(f"Cannot sort by '{sort_by}'.")
    mask = pd.Series(True, index=df.index)
    term = (search or "").strip()
    if term:
        in_id = df[ID_COL].str.contains(term, case=False, regex=False)
        in_name = df[NAME_COL].str.contains(term, case=False, regex=False)
        mask &= in_id | in_name
    if departments:
        mask &= df[DEPT_COL].isin(list(departments))
    if grades:
        mask &= df[GRADE_COL].isin(list(grades))
    if results:
        mask &= df[RESULT_COL].isin(list(results))
    low, high = attendance_range
    mask &= (df[ATT_COL] >= low) & (df[ATT_COL] <= high)

    def sort_key(column: pd.Series):
        return column.str.casefold() if column.name == NAME_COL else column

    filtered = df[mask].sort_values(
        [sort_by, ID_COL], ascending=[ascending, True], key=sort_key, kind="mergesort")
    return filtered.reset_index(drop=True)


def _join(names: list) -> str:
    return " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1]


def student_profile(df: pd.DataFrame, student_id: str):
    """Everything shown on the individual page, or None if the ID is unknown."""
    if df.empty or student_id is None:
        return None
    rows = df[df[ID_COL] == str(student_id).strip()]
    if rows.empty:
        return None
    row = rows.iloc[0]
    marks = {s: float(row[s]) for s in SUBJECTS}
    values = np.array(list(marks.values()))
    rank = int((df[AVG_COL] > row[AVG_COL]).sum() + 1)
    reasons = []
    if row[AVG_COL] < PASS_AVERAGE:
        reasons.append(f"average marks ({row[AVG_COL]:.2f}) are below {PASS_AVERAGE:g}")
    weak = [label(s) for s, m in marks.items() if m < PASS_SUBJECT_MARK]
    if weak:
        reasons.append(f"marks are below {PASS_SUBJECT_MARK:g} in {_join(weak)}")
    class_average = float(df[AVG_COL].mean())
    profile = {
        "id": row[ID_COL], "name": row[NAME_COL], "department": row[DEPT_COL],
        "marks": marks, "total": float(row[TOTAL_COL]), "average": float(row[AVG_COL]),
        "grade": row[GRADE_COL], "result": row[RESULT_COL], "attendance": float(row[ATT_COL]),
        "rank": rank, "students": len(df),
        "class_average": class_average, "difference": float(row[AVG_COL]) - class_average,
        "strongest": [label(s) for s, m in marks.items() if np.isclose(m, values.max())],
        "weakest": [label(s) for s, m in marks.items() if np.isclose(m, values.min())],
        "fail_reasons": reasons if row[RESULT_COL] == FAIL else [],
    }
    profile["interpretation"] = interpret_performance(profile)
    return profile


def interpret_performance(profile: dict) -> str:
    """Plain-language interpretation using documented rules.

    1. Result: a Fail is explained by the rule(s) that were not met.
    2. Position against the class average (difference d in marks):
       d >= 10 well above; 0 <= d < 10 at or above; -10 < d < 0 slightly below;
       d <= -10 well below.
    3. Strongest and weakest subject (ties listed).
    4. Attendance below 75% is flagged (informational only).
    """
    d = profile["difference"]
    if d >= 10:
        position = "well above the class average"
    elif d >= 0:
        position = "at or above the class average"
    elif d > -10:
        position = "slightly below the class average"
    else:
        position = "well below the class average"
    parts = []
    if profile["result"] == FAIL:
        parts.append("Did not meet the pass criteria because " + _join(profile["fail_reasons"]) + ".")
    else:
        parts.append("Met the pass criteria.")
    parts.append(f"Average marks are {abs(d):.2f} {'above' if d >= 0 else 'below'} the class average, "
                 f"so performance is {position}.")
    if set(profile["strongest"]) == set(profile["weakest"]):
        parts.append("Marks are the same in every subject.")
    else:
        parts.append(f"Strongest: {_join(profile['strongest'])}. Weakest: {_join(profile['weakest'])}.")
    if profile["attendance"] < ATTENDANCE_THRESHOLD:
        parts.append(f"Attendance ({profile['attendance']:g}%) is below the "
                     f"{ATTENDANCE_THRESHOLD:g}% threshold.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Exports and reports
# ---------------------------------------------------------------------------

def to_csv_bytes(df: pd.DataFrame, decimals: int = 2) -> bytes:
    """CSV bytes for download. Calculated float columns (averages, percentages)
    are rounded to `decimals`; original marks and attendance are never rounded."""
    out = df.copy()
    keep_exact = set(SUBJECTS) | {ATT_COL}
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]) and column not in keep_exact:
            out[column] = out[column].round(decimals)
    return out.to_csv(index=False).encode("utf-8")


def _markdown_table(df: pd.DataFrame, formats: dict | None = None) -> str:
    formats = formats or {}
    header = "| " + " | ".join(df.columns) + " |"
    divider = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, divider]
    for _, row in df.iterrows():
        cells = []
        for column in df.columns:
            value = row[column]
            cells.append(formats[column].format(value) if column in formats else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_summary_report(df: pd.DataFrame, source_name: str = "dataset", generated_at=None) -> str:
    """Complete summary report (Markdown) built from the same engine as the GUI."""
    if df.empty:
        raise ValueError("Cannot build a report from an empty dataset.")
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    s = class_summary(df)
    att = attendance_summary(df)
    subjects = subject_statistics(df)
    departments = department_summary(df)
    top = top_students(df)
    lines = [
        "# Student Performance Summary Report", "",
        f"- Dataset: {source_name}", f"- Generated: {stamp}",
        f"- Students: {s['total_students']}  |  Subjects: {s['total_subjects']} ({', '.join(label(x) for x in SUBJECTS)})", "",
        "## Rules used", "",
        "- Average = total marks / number of subjects.",
        "- Grades: A+ (90-100), A (80 to <90), B (70 to <80), C (60 to <70), D (50 to <60), F (<50).",
        f"- Pass: average >= {PASS_AVERAGE:g} and every subject >= {PASS_SUBJECT_MARK:g}; otherwise Fail.", "",
        "## Key metrics", "",
        f"- Class average: {s['class_average']:.2f}",
        f"- Highest average: {s['highest_average']:.2f} ({', '.join(s['highest_students'])})",
        f"- Lowest average: {s['lowest_average']:.2f} ({', '.join(s['lowest_students'])})",
        f"- Highest / lowest total marks: {s['highest_total']:g} / {s['lowest_total']:g}",
        f"- Passed: {s['pass_count']} ({s['pass_percentage']:.1f}%)  |  Failed: {s['fail_count']} ({s['fail_percentage']:.1f}%)",
        f"- Best subject: {', '.join(label(x) for x in s['best_subjects'])}  |  "
        f"Lowest subject: {', '.join(label(x) for x in s['lowest_subjects'])}",
        f"- Average attendance: {s['average_attendance']:.1f}%", "",
        "## Grade distribution", "",
        _markdown_table(grade_distribution(df), {"Percentage": "{:.1f}%"}), "",
        "## Subject analysis", "",
        _markdown_table(subjects.assign(Subject=subjects["Subject"].map(label)),
                        {"Average": "{:.2f}", "Highest": "{:g}", "Lowest": "{:g}", "Median": "{:g}"}), "",
        "## Department analysis", "",
        _markdown_table(departments, {"Average_Marks": "{:.2f}", "Pass_Percentage": "{:.1f}%"}),
        "", f"Best department: {', '.join(best_departments(departments))}", "",
        "## Top students", "",
        _markdown_table(top, {TOTAL_COL: "{:g}", AVG_COL: "{:.2f}"}), "",
        "## Attendance", "",
        f"- Average: {att['average']:.1f}%  |  Highest: {att['highest']:g}%  |  Lowest: {att['lowest']:g}%",
        f"- Below {att['threshold']:g}%: {att['below_count']} students  |  At least {att['threshold']:g}%: {att['at_least_count']} students",
    ]
    low = low_attendance_students(df)
    if not low.empty:
        lines += ["", "Students below the attendance threshold: "
                  + ", ".join(f"{r[NAME_COL]} ({r[ID_COL]}, {r[ATT_COL]:g}%)" for _, r in low.iterrows())]
    return "\n".join(lines) + "\n"


def build_report_files(df: pd.DataFrame, filtered: pd.DataFrame, source_name: str = "dataset") -> dict:
    """All downloadable reports as {key: (file name, bytes, MIME type)}.

    Used by both the Streamlit Reports page and the command line (--export),
    so the two always produce identical content.
    """
    subjects = subject_statistics(df)
    subjects = subjects.assign(Subject=subjects["Subject"].map(label))
    return {
        "complete": ("student_analysis_complete.csv", to_csv_bytes(df), "text/csv"),
        "filtered": ("student_analysis_filtered.csv", to_csv_bytes(filtered), "text/csv"),
        "subjects": ("subject_analysis.csv", to_csv_bytes(subjects), "text/csv"),
        "departments": ("department_analysis.csv", to_csv_bytes(department_summary(df)), "text/csv"),
        "summary": ("student_performance_summary.md",
                    build_summary_report(df, source_name).encode("utf-8"), "text/markdown"),
    }
