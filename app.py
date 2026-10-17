"""Student Performance Analytics System - Streamlit interface.

This file only handles presentation and user interaction. Every number,
table and report comes from functions.py (the shared calculation engine).

Run with:  python -m streamlit run app.py
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

import functions as fn

APP_TITLE = "Student Performance Analytics System"
APP_SUBTITLE = ("An interactive academic performance analysis dashboard "
                "built with Python, NumPy, and Pandas.")

PAGES = [
    "Dashboard",
    "Student Records",
    "Individual Student Analysis",
    "Subject Analysis",
    "Department Analysis",
    "Attendance Analysis",
    "Grade and Result Analysis",
    "Dataset Management",
    "Reports and Downloads",
]

NAVY, BLUE, SKY, PALE, RED, GREY = "#1F3A5F", "#2F6DB5", "#5E8FCB", "#9DB9DE", "#B4524F", "#8A94A3"
GRADE_COLORS = {"A+": NAVY, "A": BLUE, "B": SKY, "C": PALE, "D": "#C9D6E8", "F": RED}
RESULT_COLORS = {fn.PASS: BLUE, fn.FAIL: RED}

FILTER_DEFAULTS = {
    "rec_search": "",
    "rec_dept": [],
    "rec_grade": [],
    "rec_result": [],
    "rec_att": (0.0, 100.0),
    "rec_sort": "Average marks",
    "rec_asc": False,
}
# Widget values kept alive while the user visits other pages.
PERSISTED_KEYS = [*FILTER_DEFAULTS, "ind_student", "sub_select"]

st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #D5DEEA; border-left: 4px solid #1F3A5F;
        border-radius: 6px; padding: 10px 16px; min-height: 122px;
    }
    [data-testid="stMetricLabel"] { color: #44546A; }
    h1, h2, h3 { color: #1F3A5F; }
    .block-container { padding-top: 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state and dataset selection
# ---------------------------------------------------------------------------

def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("active_source", "default")   # "default" or "uploaded"
    ss.setdefault("uploaded_result", None)      # validated upload, never written to disk
    ss.setdefault("uploader_n", 0)              # changing it clears the file uploader
    for key, value in FILTER_DEFAULTS.items():
        ss.setdefault(key, list(value) if isinstance(value, list) else value)
    for key in PERSISTED_KEYS:                  # stop Streamlit dropping unseen widget values
        if key in ss:
            ss[key] = ss[key]


@st.cache_data(show_spinner=False)
def _load_default(modified_time: float) -> fn.ValidationResult:
    return fn.load_students_csv(fn.DEFAULT_DATASET_PATH)


def default_result() -> fn.ValidationResult:
    try:
        modified = fn.DEFAULT_DATASET_PATH.stat().st_mtime
    except OSError:
        modified = 0.0
    return _load_default(modified)


def using_upload() -> bool:
    ss = st.session_state
    return (ss.active_source == "uploaded" and ss.uploaded_result is not None
            and ss.uploaded_result.ok)


def active_result() -> fn.ValidationResult:
    return st.session_state.uploaded_result if using_upload() else default_result()


def adopt_upload(result: fn.ValidationResult) -> None:
    st.session_state.active_source = "uploaded"
    st.session_state.uploaded_result = result
    reset_filters()
    st.session_state.pop("ind_student", None)


def use_bundled_dataset() -> None:
    st.session_state.active_source = "default"
    st.session_state.uploaded_result = None
    st.session_state.uploader_n += 1
    reset_filters()
    st.session_state.pop("ind_student", None)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

TABLE_FORMATS = {
    fn.AVG_COL: "%.2f", "Average": "%.2f", "Median": "%.2f", fn.TOTAL_COL: "%g",
    fn.ATT_COL: "%g", "Highest": "%g", "Lowest": "%g",
    "Pass_Percentage": "%.1f", "Percentage": "%.1f", "Difference": "%.2f",
    **{subject: "%g" for subject in fn.SUBJECTS},
}
EXTRA_LABELS = {"Pass_Percentage": "Pass Percentage (%)", "Percentage": "Percentage (%)"}


def show_table(df, height=None) -> None:
    """Show a DataFrame with friendly headers and consistent number formats."""
    shown = df.rename(columns=lambda c: EXTRA_LABELS.get(c, fn.label(c)))
    config = {
        EXTRA_LABELS.get(col, fn.label(col)): st.column_config.NumberColumn(format=fmt)
        for col, fmt in TABLE_FORMATS.items() if col in df.columns
    }
    options = {"height": height} if height is not None else {}
    st.dataframe(shown, hide_index=True, width="stretch", column_config=config, **options)


def show_chart(fig, height: int = 340) -> None:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=50, b=10),
        title_font_size=16, font=dict(family="Segoe UI, Helvetica, Arial, sans-serif", color="#1B2430"),
        legend_title_text="",
    )
    st.plotly_chart(fig, width="stretch")


def names_text(names: list) -> str:
    return ", ".join(names)


def subject_names(subjects: list) -> str:
    return ", ".join(fn.label(s) for s in subjects)


def subject_table(stats):
    return stats.assign(Subject=stats["Subject"].map(fn.label))


# ---------------------------------------------------------------------------
# Page 1: Dashboard
# ---------------------------------------------------------------------------

def page_dashboard(df, result) -> None:
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    source = "Uploaded file" if using_upload() else "Bundled dataset"
    st.info(f"Dataset loaded: **{result.source_name}** ({source}) with **{len(df)}** student records.")

    s = fn.class_summary(df)
    row1 = st.columns(3)
    row1[0].metric("Total students", s["total_students"])
    row1[1].metric("Total subjects", s["total_subjects"], help=subject_names(fn.SUBJECTS))
    row1[2].metric("Overall class average", f"{s['class_average']:.2f}")
    row2 = st.columns(3)
    row2[0].metric("Highest student average", f"{s['highest_average']:.2f}",
                   delta=names_text(s["highest_students"]), delta_color="off", delta_arrow="off")
    row2[1].metric("Lowest student average", f"{s['lowest_average']:.2f}",
                   delta=names_text(s["lowest_students"]), delta_color="off", delta_arrow="off")
    row2[2].metric("Average attendance", f"{s['average_attendance']:.1f}%")
    row3 = st.columns(3)
    row3[0].metric("Passing students", s["pass_count"])
    row3[1].metric("Failing students", s["fail_count"])
    row3[2].metric("Overall pass percentage", f"{s['pass_percentage']:.1f}%")

    st.divider()
    stats = fn.subject_statistics(df)
    left, right = st.columns(2)
    with left:
        chart = subject_table(stats)
        fig = px.bar(chart, x="Subject", y="Average", title="Average marks by subject",
                     color_discrete_sequence=[NAVY])
        fig.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False)
        fig.update_yaxes(range=[0, 100], title="Average marks")
        show_chart(fig)
        st.caption(f"Best subject: {subject_names(s['best_subjects'])}. "
                   f"Lowest subject: {subject_names(s['lowest_subjects'])}.")
    with right:
        grades = fn.grade_distribution(df)
        fig = px.bar(grades, x="Grade", y="Students", color="Grade", title="Grade distribution",
                     color_discrete_map=GRADE_COLORS, category_orders={"Grade": fn.GRADE_ORDER})
        fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
        fig.update_layout(showlegend=False)
        show_chart(fig)

    left, right = st.columns(2)
    with left:
        results = fn.result_distribution(df)
        fig = px.pie(results, names="Result", values="Students", hole=0.5, title="Pass / fail distribution",
                     color="Result", color_discrete_map=RESULT_COLORS)
        fig.update_traces(textinfo="label+value+percent")
        show_chart(fig)
    with right:
        departments = fn.department_summary(df)
        fig = px.bar(departments, x=fn.DEPT_COL, y="Average_Marks", title="Average marks by department",
                     color_discrete_sequence=[BLUE])
        fig.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False)
        fig.update_yaxes(range=[0, 100], title="Average marks")
        fig.update_xaxes(title="")
        show_chart(fig)

    st.subheader("Top-performing students")
    st.caption("Ranked by average marks. Students tied at the cut-off share a rank and are all shown.")
    show_table(fn.top_students(df))


# ---------------------------------------------------------------------------
# Page 2: Student Records
# ---------------------------------------------------------------------------

def apply_record_filters(df):
    """Apply the filters stored in session state (shared with the Reports page)."""
    ss = st.session_state
    return fn.filter_students(
        df,
        search=ss.get("rec_search", ""),
        departments=ss.get("rec_dept", []),
        grades=ss.get("rec_grade", []),
        results=ss.get("rec_result", []),
        attendance_range=tuple(ss.get("rec_att", (0.0, 100.0))),
        sort_by=fn.SORT_OPTIONS[ss.get("rec_sort", "Average marks")],
        ascending=bool(ss.get("rec_asc", False)),
    )


def describe_filters() -> str:
    ss = st.session_state
    parts = []
    if ss.get("rec_search", "").strip():
        parts.append(f"search '{ss['rec_search'].strip()}'")
    if ss.get("rec_dept"):
        parts.append("department: " + ", ".join(ss["rec_dept"]))
    if ss.get("rec_grade"):
        parts.append("grade: " + ", ".join(ss["rec_grade"]))
    if ss.get("rec_result"):
        parts.append("result: " + ", ".join(ss["rec_result"]))
    low, high = ss.get("rec_att", (0.0, 100.0))
    if (low, high) != (0.0, 100.0):
        parts.append(f"attendance {low:g}-{high:g}%")
    return "; ".join(parts) if parts else "no filters (all students)"


def page_records(df) -> None:
    st.title("Student Records")
    st.caption("Search, filter and sort the analysed student table.")
    ss = st.session_state
    for key, options in (("rec_dept", sorted(df[fn.DEPT_COL].unique())), ("rec_grade", fn.GRADE_ORDER),
                         ("rec_result", [fn.PASS, fn.FAIL])):
        ss[key] = [v for v in ss.get(key, []) if v in options]   # drop values not in this dataset

    top = st.columns([2, 2, 1.5, 1.5])
    top[0].text_input("Search by Student ID or name", key="rec_search", placeholder="e.g. S004 or Aarav")
    top[1].multiselect("Department", sorted(df[fn.DEPT_COL].unique()), key="rec_dept",
                       placeholder="All departments")
    top[2].multiselect("Grade", fn.GRADE_ORDER, key="rec_grade", placeholder="All grades")
    top[3].multiselect("Result", [fn.PASS, fn.FAIL], key="rec_result", placeholder="Pass and fail")
    bottom = st.columns([2, 2, 1.5, 1.5])
    bottom[0].slider("Attendance range (%)", 0.0, 100.0, step=1.0, key="rec_att")
    bottom[1].selectbox("Sort by", list(fn.SORT_OPTIONS), key="rec_sort")
    bottom[2].checkbox("Ascending order", key="rec_asc")
    bottom[3].button("Reset filters", on_click=reset_filters, width="stretch")

    filtered = apply_record_filters(df)
    st.markdown(f"**Showing {len(filtered)} of {len(df)} students**")
    if filtered.empty:
        st.info("No students match the current filters. Adjust or reset the filters to see records.")
        return
    show_table(filtered)


# ---------------------------------------------------------------------------
# Page 3: Individual Student Analysis
# ---------------------------------------------------------------------------

def page_student(df) -> None:
    st.title("Individual Student Analysis")
    st.caption("Select a student to see their marks, result and how they compare with the class.")
    options = df[fn.ID_COL].tolist()
    names = dict(zip(df[fn.ID_COL], df[fn.NAME_COL]))
    if st.session_state.get("ind_student") not in options:
        st.session_state.pop("ind_student", None)
    student_id = st.selectbox("Select a student (type to search)", options,
                              format_func=lambda i: f"{i} - {names[i]}", key="ind_student")
    profile = fn.student_profile(df, student_id)
    if profile is None:
        st.warning("That student was not found in the current dataset. Please choose another student.")
        return

    st.subheader(f"{profile['name']} ({profile['id']})")
    st.caption(f"Department: {profile['department']}")
    cols = st.columns(5)
    cols[0].metric("Total marks", f"{profile['total']:g}")
    cols[1].metric("Average marks", f"{profile['average']:.2f}")
    cols[2].metric("Grade", profile["grade"])
    cols[3].metric("Result", profile["result"])
    cols[4].metric("Attendance", f"{profile['attendance']:g}%")

    cmp_cols = st.columns(3)
    cmp_cols[0].metric("Class average", f"{profile['class_average']:.2f}")
    cmp_cols[1].metric("Student vs class average", f"{profile['average']:.2f}",
                       delta=f"{profile['difference']:+.2f}")
    cmp_cols[2].metric("Class rank", f"{profile['rank']} of {profile['students']}")

    if profile["result"] == fn.PASS:
        st.success(profile["interpretation"])
    else:
        st.warning(profile["interpretation"])

    stats = fn.subject_statistics(df)
    table = stats[["Subject", "Average"]].rename(columns={"Average": "Class average"})
    table["Subject"] = table["Subject"].map(fn.label)
    table["Student"] = [profile["marks"][s] for s in fn.SUBJECTS]
    left, right = st.columns([3, 2])
    with left:
        long = table.melt(id_vars="Subject", value_vars=["Student", "Class average"],
                          var_name="Series", value_name="Marks")
        fig = px.bar(long, x="Subject", y="Marks", color="Series", barmode="group",
                     title="Subject marks compared with the class average",
                     color_discrete_map={"Student": NAVY, "Class average": PALE})
        fig.update_yaxes(range=[0, 100])
        show_chart(fig, 360)
    with right:
        st.markdown("**Subject marks**")
        table["Difference"] = table["Student"] - table["Class average"]
        st.dataframe(table[["Subject", "Student", "Class average", "Difference"]], hide_index=True,
                     width="stretch", column_config={
                         "Student": st.column_config.NumberColumn(format="%g"),
                         "Class average": st.column_config.NumberColumn(format="%.2f"),
                         "Difference": st.column_config.NumberColumn(format="%+.2f")})


# ---------------------------------------------------------------------------
# Page 4: Subject Analysis
# ---------------------------------------------------------------------------

def page_subjects(df) -> None:
    st.title("Subject Analysis")
    st.caption(f"Marks per subject. A student passes a subject with at least {fn.PASS_SUBJECT_MARK:g} marks.")
    stats = fn.subject_statistics(df)
    best, lowest = fn.best_and_lowest_subjects(stats)
    top = st.columns(2)
    top[0].metric("Best-performing subject", subject_names(best),
                  delta=f"average {stats['Average'].max():.2f}", delta_color="off", delta_arrow="off")
    top[1].metric("Lowest-performing subject", subject_names(lowest),
                  delta=f"average {stats['Average'].min():.2f}", delta_color="off", delta_arrow="off")

    left, right = st.columns([3, 2])
    with left:
        fig = px.bar(subject_table(stats), x="Subject", y="Average", title="Subject averages",
                     color_discrete_sequence=[NAVY])
        fig.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False)
        fig.update_yaxes(range=[0, 100], title="Average marks")
        show_chart(fig)
    with right:
        st.markdown("**Subject statistics**")
        show_table(subject_table(stats))

    st.subheader("Mark distribution")
    if st.session_state.get("sub_select") not in fn.SUBJECTS:
        st.session_state.pop("sub_select", None)
    subject = st.selectbox("Choose a subject", fn.SUBJECTS, format_func=fn.label, key="sub_select")
    row = stats[stats["Subject"] == subject].iloc[0]
    cols = st.columns(6)
    cols[0].metric("Average", f"{row['Average']:.2f}")
    cols[1].metric("Highest", f"{row['Highest']:g}")
    cols[2].metric("Lowest", f"{row['Lowest']:g}")
    cols[3].metric("Median", f"{row['Median']:g}")
    cols[4].metric("Passing", int(row["Passing"]))
    cols[5].metric("Failing", int(row["Failing"]))
    distribution = fn.mark_distribution(df[subject])
    fig = px.bar(distribution, x="Marks range", y="Students", title=f"{fn.label(subject)}: number of students per marks range",
                 color_discrete_sequence=[BLUE])
    fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
    show_chart(fig)
    failing = df[df[subject] < fn.PASS_SUBJECT_MARK][[fn.ID_COL, fn.NAME_COL, fn.DEPT_COL, subject]]
    if not failing.empty:
        st.markdown(f"**Students below {fn.PASS_SUBJECT_MARK:g} in {fn.label(subject)}**")
        show_table(failing)


# ---------------------------------------------------------------------------
# Page 5: Department Analysis
# ---------------------------------------------------------------------------

def page_departments(df) -> None:
    st.title("Department Analysis")
    st.caption("Department-wise size, average marks and pass/fail results. Departments are read from the data.")
    summary = fn.department_summary(df)
    best = fn.best_departments(summary)
    top = st.columns(2)
    top[0].metric("Departments", len(summary))
    top[1].metric("Best-performing department" if len(best) == 1 else "Best-performing departments (tied)",
                  names_text(best), delta=f"average {summary['Average_Marks'].max():.2f}",
                  delta_color="off", delta_arrow="off")
    left, right = st.columns(2)
    with left:
        fig = px.bar(summary, x=fn.DEPT_COL, y="Students", title="Students per department",
                     color_discrete_sequence=[NAVY])
        fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
        fig.update_xaxes(title="")
        show_chart(fig)
    with right:
        fig = px.bar(summary, x=fn.DEPT_COL, y="Average_Marks", title="Average marks per department",
                     color_discrete_sequence=[BLUE])
        fig.update_traces(texttemplate="%{y:.1f}", textposition="outside", cliponaxis=False)
        fig.update_yaxes(range=[0, 100], title="Average marks")
        fig.update_xaxes(title="")
        show_chart(fig)
    left, right = st.columns(2)
    with left:
        long = summary.melt(id_vars=fn.DEPT_COL, value_vars=["Passed", "Failed"],
                            var_name="Result", value_name="Count")
        long["Result"] = long["Result"].map({"Passed": fn.PASS, "Failed": fn.FAIL})
        fig = px.bar(long, x=fn.DEPT_COL, y="Count", color="Result", barmode="stack",
                     title="Pass and fail counts per department", color_discrete_map=RESULT_COLORS)
        fig.update_xaxes(title="")
        show_chart(fig)
    with right:
        fig = px.bar(summary, x=fn.DEPT_COL, y="Pass_Percentage", title="Pass percentage per department",
                     color_discrete_sequence=[SKY])
        fig.update_traces(texttemplate="%{y:.1f}%", textposition="outside", cliponaxis=False)
        fig.update_yaxes(range=[0, 110], title="Pass percentage")
        fig.update_xaxes(title="")
        show_chart(fig)
    show_table(summary)


# ---------------------------------------------------------------------------
# Page 6: Attendance Analysis
# ---------------------------------------------------------------------------

def page_attendance(df) -> None:
    st.title("Attendance Analysis")
    att = fn.attendance_summary(df)
    st.caption(f"Attendance below {att['threshold']:g}% is treated as low. "
               "Attendance does not change a student's academic pass/fail result.")
    cols = st.columns(5)
    cols[0].metric("Average attendance", f"{att['average']:.1f}%")
    cols[1].metric("Highest attendance", f"{att['highest']:g}%", delta=names_text(att["highest_students"]),
                   delta_color="off", delta_arrow="off")
    cols[2].metric("Lowest attendance", f"{att['lowest']:g}%", delta=names_text(att["lowest_students"]),
                   delta_color="off", delta_arrow="off")
    cols[3].metric(f"Below {att['threshold']:g}%", att["below_count"])
    cols[4].metric(f"At least {att['threshold']:g}%", att["at_least_count"])

    left, right = st.columns(2)
    with left:
        fig = px.bar(fn.attendance_distribution(df), x="Attendance band", y="Students",
                     title="Attendance distribution", color_discrete_sequence=[NAVY])
        fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
        show_chart(fig)
    with right:
        fig = px.scatter(df, x=fn.ATT_COL, y=fn.AVG_COL, color=fn.RESULT_COL, hover_name=fn.NAME_COL,
                         title="Attendance and average marks", color_discrete_map=RESULT_COLORS,
                         labels={fn.ATT_COL: "Attendance (%)", fn.AVG_COL: "Average marks"})
        fig.add_vline(x=att["threshold"], line_dash="dash", line_color=GREY)
        show_chart(fig)
        correlation = fn.attendance_marks_correlation(df)
        if correlation is None:
            st.caption("A correlation needs at least three students with varying attendance and marks.")
        else:
            st.caption(f"Correlation between attendance and average marks: r = {correlation:.2f}. "
                       "Correlation does not establish causation.")

    st.subheader(f"Students with attendance below {att['threshold']:g}%")
    low = fn.low_attendance_students(df)
    if low.empty:
        st.success("No students are below the attendance threshold.")
    else:
        show_table(low[[fn.ID_COL, fn.NAME_COL, fn.DEPT_COL, fn.ATT_COL, fn.AVG_COL, fn.GRADE_COL, fn.RESULT_COL]])


# ---------------------------------------------------------------------------
# Page 7: Grade and Result Analysis
# ---------------------------------------------------------------------------

def page_grades(df) -> None:
    st.title("Grade and Result Analysis")
    st.caption(f"Grades use the average marks. A student passes with an average of at least {fn.PASS_AVERAGE:g} "
               f"and at least {fn.PASS_SUBJECT_MARK:g} in every subject.")
    grades = fn.grade_distribution(df)
    results = fn.result_distribution(df)
    left, right = st.columns(2)
    with left:
        fig = px.bar(grades, x="Grade", y="Students", color="Grade", title="Grade distribution",
                     color_discrete_map=GRADE_COLORS, category_orders={"Grade": fn.GRADE_ORDER})
        fig.update_traces(texttemplate="%{y}", textposition="outside", cliponaxis=False)
        fig.update_layout(showlegend=False)
        show_chart(fig)
        show_table(grades)
    with right:
        fig = px.pie(results, names="Result", values="Students", hole=0.5, title="Pass and fail",
                     color="Result", color_discrete_map=RESULT_COLORS)
        fig.update_traces(textinfo="label+value+percent")
        show_chart(fig)
        show_table(results)

    check = fn.reconciliation_check(df)
    if check["grades_reconcile"] and check["results_reconcile"] and check["totals_match"] and check["averages_match"]:
        st.success(f"Reconciliation: grade counts add up to {check['grade_total']} and pass + fail adds up to "
                   f"{check['result_total']}, matching the {check['students']} students analysed.")
    else:
        st.error("Reconciliation failed: grade or result counts do not match the number of students.")
    grade_f_pass = int(((df[fn.GRADE_COL] == "F") & (df[fn.RESULT_COL] == fn.PASS)).sum())
    if grade_f_pass:
        st.info(f"{grade_f_pass} student(s) have grade F but still pass. Grade F covers averages below 50, "
                f"while passing needs an average of at least {fn.PASS_AVERAGE:g} and every subject at least "
                f"{fn.PASS_SUBJECT_MARK:g}. This follows the project's documented rules.")

    left, right = st.columns(2)
    columns = [fn.ID_COL, fn.NAME_COL, fn.DEPT_COL, fn.AVG_COL, fn.GRADE_COL, fn.RESULT_COL]
    with left:
        st.markdown("**Highest performer(s)**")
        show_table(fn.extreme_students(df, fn.AVG_COL, True)[columns])
    with right:
        st.markdown("**Lowest performer(s)**")
        show_table(fn.extreme_students(df, fn.AVG_COL, False)[columns])

    st.subheader("Students in each grade")
    for grade in fn.GRADE_ORDER:
        members = df[df[fn.GRADE_COL] == grade].sort_values([fn.AVG_COL, fn.ID_COL], ascending=[False, True])
        with st.expander(f"Grade {grade}: {len(members)} student(s)"):
            if members.empty:
                st.caption("No students have this grade.")
            else:
                show_table(members[columns])


# ---------------------------------------------------------------------------
# Page 8: Dataset Management
# ---------------------------------------------------------------------------

def show_checklist(result: fn.ValidationResult) -> None:
    rows = [{"Check": name, "Status": "Passed" if passed else "Failed"} for name, passed in result.checklist()]
    st.dataframe(rows, hide_index=True, width="stretch")


def page_dataset() -> None:
    st.title("Dataset Management")
    st.caption("Inspect the loaded dataset, or upload a CSV file. Uploads are validated before use and the "
               "bundled file is never changed.")
    ss = st.session_state
    current = active_result()
    if not current.ok:
        st.error("The current dataset is not valid, so no analysis is shown. Upload a corrected CSV below.")
        for message in current.errors:
            st.markdown(f"- {message}")
    else:
        st.subheader("Current dataset")
        cols = st.columns([1.8, 1.6, 1, 1])
        cols[0].metric("Source", "Uploaded file" if using_upload() else "Bundled dataset")
        cols[1].metric("File name", current.source_name)
        cols[2].metric("Records", len(current.data))
        cols[3].metric("Columns in file", current.raw_columns)
        show_checklist(current)
        st.markdown("**Data preview** (first 10 rows, with calculated columns)")
        show_table(current.data.head(10))

    st.button("Return to the bundled dataset", on_click=use_bundled_dataset, disabled=not using_upload())

    st.subheader("Upload a CSV file")
    with st.expander("Required file format"):
        st.markdown(
            "The first row must contain these column names exactly:\n\n"
            f"`{', '.join(fn.REQUIRED_COLUMNS)}`\n\n"
            f"Marks and attendance must be numbers from 0 to 100. Student IDs must be unique. "
            "Missing values are never replaced with zero; the file is rejected instead."
        )
    uploaded = st.file_uploader("Choose a CSV file", type=["csv"], key=f"uploader_{ss.uploader_n}")
    if uploaded is None:
        return
    result = fn.load_students_csv(uploaded, uploaded.name)
    show_checklist(result)
    if not result.ok:
        st.error(f"Validation failed for {uploaded.name}. The file was not loaded and the current dataset is "
                 "unchanged. Fix the problems below and upload the file again.")
        for message in result.errors:
            st.markdown(f"- {message}")
        if result.raw_preview is not None:
            st.caption("The file as read (not used for any analysis):")
            st.dataframe(result.raw_preview, hide_index=True, width="stretch")
        return
    st.success(f"Validation passed: {len(result.data)} records and {result.raw_columns} columns.")
    for warning in result.warnings:
        st.warning(warning)
    st.dataframe(result.data.head(10), hide_index=True, width="stretch")
    already = (using_upload() and ss.uploaded_result.source_name == result.source_name
               and ss.uploaded_result.data.equals(result.data))
    if already:
        st.info("This file is the dataset currently in use.")
    else:
        st.button("Use this dataset for analysis", on_click=adopt_upload, args=(result,), type="primary")


# ---------------------------------------------------------------------------
# Page 9: Reports and Downloads
# ---------------------------------------------------------------------------

def page_reports(df, result) -> None:
    st.title("Reports and Downloads")
    st.caption("Download the current analysis. The source CSV is never modified. "
               "Calculated averages and percentages in CSV files are rounded to 2 decimals.")
    filtered = apply_record_filters(df)
    st.markdown(f"Dataset: **{result.source_name}**  |  Filtered records: **{len(filtered)} of {len(df)}** "
                f"({describe_filters()})")
    try:
        files = fn.build_report_files(df, filtered, result.source_name)
    except Exception as exc:
        st.error(f"The reports could not be generated: {exc}")
        return
    for key, (title, description) in REPORT_TEXT.items():
        file_name, data, mime = files[key]
        with st.container(border=True):
            cols = st.columns([4, 1.2])
            cols[0].markdown(f"**{title}**  \n{description}  \nFile: `{file_name}`")
            cols[1].download_button("Download", data=data, file_name=file_name, mime=mime,
                                    key=f"download_{key}", width="stretch")
    st.caption("Set the filters on the Student Records page to change the filtered download.")


REPORT_TEXT = {
    "complete": ("Complete analysed student data (CSV)",
                 "All students with original fields, total marks, average marks, grade and result."),
    "filtered": ("Filtered student data (CSV)",
                 "The students currently shown on the Student Records page."),
    "subjects": ("Subject-wise analysis (CSV)", "Average, highest, lowest, median, passing and failing per subject."),
    "departments": ("Department-wise analysis (CSV)",
                    "Students, average marks, pass/fail counts and pass percentage per department."),
    "summary": ("Complete summary report (Markdown)",
                "Key metrics, rules, grade, subject, department, top-student and attendance sections."),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    init_state()
    result = active_result()

    with st.sidebar:
        st.markdown(f"### {APP_TITLE}")
        st.caption("Python, NumPy and Pandas analytics")
        page = st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
        st.divider()
        if result.ok:
            st.markdown(f"**Dataset:** {result.source_name}  \n**Records:** {len(result.data)}  \n"
                        f"**Source:** {'Uploaded file' if using_upload() else 'Bundled dataset'}")
        else:
            st.error("No valid dataset is loaded.")

    if page == "Dataset Management":
        page_dataset()
        return
    if not result.ok:
        st.title(page)
        st.error("The dataset could not be loaded, so no results are shown. Open Dataset Management to fix this.")
        for message in result.errors:
            st.markdown(f"- {message}")
        return
    df = result.data.copy()
    if df.empty:
        st.title(page)
        st.warning("The dataset has no student records.")
        return

    pages = {
        "Dashboard": lambda: page_dashboard(df, result),
        "Student Records": lambda: page_records(df),
        "Individual Student Analysis": lambda: page_student(df),
        "Subject Analysis": lambda: page_subjects(df),
        "Department Analysis": lambda: page_departments(df),
        "Attendance Analysis": lambda: page_attendance(df),
        "Grade and Result Analysis": lambda: page_grades(df),
        "Reports and Downloads": lambda: page_reports(df, result),
    }
    pages[page]()


main()
