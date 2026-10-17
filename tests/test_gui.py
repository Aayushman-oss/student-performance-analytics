"""GUI and integration tests using Streamlit's AppTest (no browser, no network)."""

import re
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import functions as fn  # noqa: E402

APP_PATH = str(ROOT / "app.py")
HEADER = ",".join(fn.REQUIRED_COLUMNS)
PAGES = ["Dashboard", "Student Records", "Individual Student Analysis", "Subject Analysis",
         "Department Analysis", "Attendance Analysis", "Grade and Result Analysis",
         "Dataset Management", "Reports and Downloads"]


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_data.clear()
    yield


@pytest.fixture
def engine_df():
    return fn.load_students_csv(fn.DEFAULT_DATASET_PATH).data


@pytest.fixture
def app():
    return AppTest.from_file(APP_PATH, default_timeout=60).run()


def goto(app, page):
    app.sidebar.radio(key="page").set_value(page).run()
    return app


def metrics(app) -> dict:
    return {m.label: m.value for m in app.metric}


def showing(app):
    """(shown, total) from the 'Showing N of M students' line."""
    for md in app.markdown:
        match = re.search(r"Showing (\d+) of (\d+) students", md.value)
        if match:
            return int(match.group(1)), int(match.group(2))
    raise AssertionError("record count line not found")


def csv_bytes(*rows, header=HEADER) -> bytes:
    return ("\n".join([header, *[",".join(str(v) for v in r) for r in rows]]) + "\n").encode()


def upload(app, name, content):
    app.file_uploader(key=f"uploader_{app.session_state['uploader_n']}").set_value((name, content, "text/csv")).run()
    return app


def click(app, label_start):
    button = next(b for b in app.button if b.label.startswith(label_start))
    button.click().run()
    return app


GOOD_UPLOAD = csv_bytes(
    ["U1", "Uma", "Physics", 90, 90, 90, 90, 90, 95],
    ["U2", "Vik", "Physics", 30, 60, 60, 60, 60, 70],
    ["U3", "Wes", "Maths", 70, 70, 70, 70, 70, 50],
)


# ------------------------------------------------------------------ start-up

def test_application_loads_without_errors(app):
    assert not app.exception and not app.error
    assert app.title[0].value == "Student Performance Analytics System"
    assert any("Python, NumPy, and Pandas" in c.value for c in app.caption)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(app, page):
    goto(app, page)
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error


def test_navigation_lists_all_nine_pages(app):
    assert list(app.sidebar.radio(key="page").options) == PAGES


# ----------------------------------------------------------------- dashboard

def test_dashboard_metrics_come_from_the_engine(app, engine_df):
    m = metrics(app)
    s = fn.class_summary(engine_df)
    assert m["Total students"] == str(s["total_students"])
    assert m["Total subjects"] == "5"
    assert m["Overall class average"] == f"{s['class_average']:.2f}"
    assert m["Highest student average"] == f"{s['highest_average']:.2f}"
    assert m["Lowest student average"] == f"{s['lowest_average']:.2f}"
    assert m["Passing students"] == str(s["pass_count"])
    assert m["Failing students"] == str(s["fail_count"])
    assert m["Overall pass percentage"] == f"{s['pass_percentage']:.1f}%"
    assert m["Average attendance"] == f"{s['average_attendance']:.1f}%"
    assert len(app.metric) == 9


def test_dashboard_shows_dataset_and_charts(app):
    assert any("students.csv" in i.value and "25" in i.value for i in app.info)
    assert len(app.get("plotly_chart")) == 4
    assert len(app.dataframe) == 1 and len(app.dataframe[0].value) == 5      # top five


# ------------------------------------------------------------------- records

def test_records_default_shows_everyone(app):
    goto(app, "Student Records")
    assert showing(app) == (25, 25) and len(app.dataframe[0].value) == 25


def test_search_by_name_and_id(app):
    goto(app, "Student Records")
    app.text_input(key="rec_search").set_value("aarav").run()
    assert showing(app) == (1, 25) and app.dataframe[0].value["Student ID"].tolist() == ["S001"]
    app.text_input(key="rec_search").set_value("S02").run()
    assert showing(app)[0] == 6 and len(app.dataframe[0].value) == 6          # S020 ... S025


def test_department_grade_result_filters(app, engine_df):
    goto(app, "Student Records")
    app.multiselect(key="rec_dept").set_value(["Electronics"]).run()
    assert showing(app)[0] == int((engine_df[fn.DEPT_COL] == "Electronics").sum())
    app.multiselect(key="rec_result").set_value(["Fail"]).run()
    expected = engine_df[(engine_df[fn.DEPT_COL] == "Electronics") & (engine_df[fn.RESULT_COL] == "Fail")]
    assert showing(app)[0] == len(expected) == len(app.dataframe[0].value)
    app.multiselect(key="rec_dept").set_value([]).run()
    app.multiselect(key="rec_result").set_value([]).run()
    app.multiselect(key="rec_grade").set_value(["A+"]).run()
    assert showing(app)[0] == 3


def test_attendance_filter_and_sort(app, engine_df):
    goto(app, "Student Records")
    app.slider(key="rec_att").set_value((0.0, 74.0)).run()
    assert showing(app)[0] == int((engine_df[fn.ATT_COL] <= 74).sum()) == 9
    app.selectbox(key="rec_sort").set_value("Attendance").run()
    app.checkbox(key="rec_asc").set_value(True).run()
    attendance = app.dataframe[0].value["Attendance (%)"].tolist()
    assert attendance == sorted(attendance) and attendance[0] == 45


def test_sort_by_name_and_total(app):
    goto(app, "Student Records")
    app.selectbox(key="rec_sort").set_value("Name").run()
    app.checkbox(key="rec_asc").set_value(True).run()
    names = app.dataframe[0].value["Name"].tolist()
    assert names == sorted(names, key=str.casefold)
    app.selectbox(key="rec_sort").set_value("Total marks").run()
    app.checkbox(key="rec_asc").set_value(False).run()
    totals = app.dataframe[0].value["Total Marks"].tolist()
    assert totals == sorted(totals, reverse=True)


def test_no_match_message_and_reset(app):
    goto(app, "Student Records")
    app.text_input(key="rec_search").set_value("nobody-with-this-name").run()
    assert showing(app) == (0, 25)
    assert any("No students match" in i.value for i in app.info) and len(app.dataframe) == 0
    click(app, "Reset filters")
    assert showing(app) == (25, 25) and app.text_input(key="rec_search").value == ""


def test_records_table_has_required_columns(app):
    goto(app, "Student Records")
    columns = list(app.dataframe[0].value.columns)
    for expected in ["Student ID", "Name", "Department", "Python", "Statistics", "NumPy", "Pandas",
                     "Data Analysis", "Total Marks", "Average Marks", "Grade", "Result", "Attendance (%)"]:
        assert expected in columns


# ------------------------------------------------------------------- student

def test_student_selection_updates_the_profile(app):
    goto(app, "Individual Student Analysis")
    app.selectbox(key="ind_student").set_value("S018").run()
    m = metrics(app)
    assert (m["Total marks"], m["Average marks"], m["Grade"], m["Result"]) == ("300", "60.00", "C", "Fail")
    assert m["Attendance"] == "90%"
    assert any("NumPy" in w.value for w in app.warning)
    app.selectbox(key="ind_student").set_value("S001").run()
    m = metrics(app)
    assert (m["Total marks"], m["Average marks"], m["Grade"], m["Result"]) == ("470", "94.00", "A+", "Pass")
    assert any("Aarav Sharma" in s.value for s in app.subheader) and not app.warning
    assert len(app.get("plotly_chart")) == 1


def test_selected_student_survives_navigation(app):
    goto(app, "Individual Student Analysis")
    app.selectbox(key="ind_student").set_value("S005").run()
    goto(app, "Dashboard")
    goto(app, "Individual Student Analysis")
    assert app.selectbox(key="ind_student").value == "S005"


# ------------------------------------------------------------ analysis pages

def test_subject_page(app, engine_df):
    goto(app, "Subject Analysis")
    stats = fn.subject_statistics(engine_df)
    best, lowest = fn.best_and_lowest_subjects(stats)
    m = metrics(app)
    assert m["Best-performing subject"] == "Data Analysis" and m["Lowest-performing subject"] == "Statistics"
    table = app.dataframe[0].value
    assert table["Subject"].tolist() == ["Python", "Statistics", "NumPy", "Pandas", "Data Analysis"]
    app.selectbox(key="sub_select").set_value("NumPy").run()
    assert metrics(app)["Failing"] == "2" and metrics(app)["Passing"] == "23"


def test_department_page(app):
    goto(app, "Department Analysis")
    m = metrics(app)
    assert m["Departments"] == "5" and m["Best-performing department"] == "Data Science"
    assert len(app.get("plotly_chart")) == 4


def test_attendance_page(app):
    goto(app, "Attendance Analysis")
    m = metrics(app)
    assert m["Below 75%"] == "9" and m["At least 75%"] == "16" and m["Average attendance"] == "78.8%"
    assert len(app.dataframe[0].value) == 9
    assert any("does not establish causation" in c.value for c in app.caption)


def test_grade_page_reconciles(app):
    goto(app, "Grade and Result Analysis")
    assert any("Reconciliation" in s.value and "25" in s.value for s in app.success)
    assert any("grade F but still pass" in i.value for i in app.info)
    assert len(app.expander) == 6


# ------------------------------------------------------------------- reports

def test_report_page_offers_five_downloads(app):
    goto(app, "Reports and Downloads")
    buttons = app.get("download_button")
    assert len(buttons) == 5
    text = " ".join(md.value for md in app.markdown)
    for name in ["student_analysis_complete.csv", "student_analysis_filtered.csv", "subject_analysis.csv",
                 "department_analysis.csv", "student_performance_summary.md"]:
        assert name in text


def test_filters_carry_over_to_reports(app):
    goto(app, "Student Records")
    app.multiselect(key="rec_result").set_value(["Fail"]).run()
    goto(app, "Dashboard")
    goto(app, "Reports and Downloads")
    assert any("4 of 25" in md.value and "result: Fail" in md.value for md in app.markdown)


def test_reports_do_not_modify_the_source_file(app):
    before = fn.DEFAULT_DATASET_PATH.read_bytes()
    goto(app, "Reports and Downloads")
    goto(app, "Student Records")
    assert fn.DEFAULT_DATASET_PATH.read_bytes() == before


# ------------------------------------------------------------ dataset upload

def test_dataset_page_shows_checks_for_bundled_data(app):
    goto(app, "Dataset Management")
    assert metrics(app)["Source"] == "Bundled dataset" and metrics(app)["Records"] == "25"
    assert metrics(app)["Columns in file"] == "9"
    assert all(row == "Passed" for row in app.dataframe[0].value["Status"])


def test_valid_upload_requires_confirmation_then_updates_everything(app):
    goto(app, "Dataset Management")
    upload(app, "mine.csv", GOOD_UPLOAD)
    assert any("Validation passed: 3 records" in s.value for s in app.success)
    goto_total = metrics(app)["Records"]
    assert goto_total == "25"                      # not adopted yet
    click(app, "Use this dataset")
    assert metrics(app)["Source"] == "Uploaded file" and metrics(app)["Records"] == "3"
    goto(app, "Dashboard")
    m = metrics(app)
    assert m["Total students"] == "3" and m["Passing students"] == "2" and m["Failing students"] == "1"
    assert any("mine.csv" in i.value and "3" in i.value for i in app.info)
    assert fn.DEFAULT_DATASET_PATH.read_text().count("\n") == 26      # bundled file untouched


def test_every_page_works_with_the_uploaded_dataset(app):
    goto(app, "Dataset Management")
    upload(app, "mine.csv", GOOD_UPLOAD)
    click(app, "Use this dataset")
    for page in PAGES:
        goto(app, page)
        assert not app.exception, (page, [e.value for e in app.exception])


def test_dataset_reset_restores_the_bundled_file(app):
    goto(app, "Dataset Management")
    upload(app, "mine.csv", GOOD_UPLOAD)
    click(app, "Use this dataset")
    click(app, "Return to the bundled dataset")
    assert metrics(app)["Source"] == "Bundled dataset" and metrics(app)["Records"] == "25"
    goto(app, "Dashboard")
    assert metrics(app)["Total students"] == "25"


def test_uploading_new_dataset_resets_filters_and_selection(app):
    goto(app, "Student Records")
    app.multiselect(key="rec_dept").set_value(["Electronics"]).run()
    goto(app, "Dataset Management")
    upload(app, "mine.csv", GOOD_UPLOAD)
    click(app, "Use this dataset")
    goto(app, "Student Records")
    assert showing(app) == (3, 3) and app.multiselect(key="rec_dept").value == []


@pytest.mark.parametrize("name, content, expected", [
    ("cols.csv", b"Student_ID,Name,Python\nS1,A,50\n", "Missing required column"),
    ("dup.csv", csv_bytes(["S1", "A", "D", 50, 50, 50, 50, 50, 80], ["S1", "B", "D", 50, 50, 50, 50, 50, 80]), "more than once"),
    ("marks.csv", csv_bytes(["S1", "A", "D", 101, 50, 50, 50, 50, 80]), "between 0 and 100"),
    ("att.csv", csv_bytes(["S1", "A", "D", 50, 50, 50, 50, 50, 140]), "between 0 and 100"),
    ("blank.csv", csv_bytes(["S1", "A", "D", "", 50, 50, 50, 50, 80]), "not replaced with zero"),
    ("text.csv", csv_bytes(["S1", "A", "D", "abc", 50, 50, 50, 50, 80]), "non-numeric"),
    ("empty.csv", b"", "empty"),
    ("bad.csv", HEADER.encode() + b"\nS1,A,D,50,50,50,50,50,80,1,2,3,4\n", "not a well-formed CSV"),
])
def test_invalid_upload_is_rejected_and_never_used(app, name, content, expected):
    goto(app, "Dataset Management")
    upload(app, name, content)
    assert not app.exception
    assert any("Validation failed" in e.value for e in app.error)
    assert any(expected in md.value for md in app.markdown)
    assert not [b for b in app.button if b.label.startswith("Use this dataset")]   # cannot be adopted
    checklists = [d.value for d in app.dataframe if "Status" in d.value.columns]
    assert "Failed" in checklists[-1]["Status"].tolist()              # the upload's checklist shows the failure
    assert set(checklists[0]["Status"]) == {"Passed"}                 # the dataset in use is still valid
    goto(app, "Dashboard")
    assert metrics(app)["Total students"] == "25"                                     # analysis unchanged


def test_one_student_dataset_does_not_break_any_page(app):
    goto(app, "Dataset Management")
    upload(app, "one.csv", csv_bytes(["ONE", "Solo", "Only", 70, 80, 90, 60, 50, 60]))
    click(app, "Use this dataset")
    for page in PAGES:
        goto(app, page)
        assert not app.exception, (page, [e.value for e in app.exception])
    goto(app, "Attendance Analysis")
    assert any("at least three students" in c.value for c in app.caption)


# --------------------------------------------------------------- invalid data

def test_invalid_bundled_dataset_shows_clear_messages(monkeypatch, tmp_path):
    bad = tmp_path / "students.csv"
    bad.write_text("Student_ID,Name\nS1,A\n")
    monkeypatch.setattr(fn, "DEFAULT_DATASET_PATH", bad)
    app = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not app.exception
    assert len(app.metric) == 0 and len(app.get("plotly_chart")) == 0          # nothing misleading
    assert any("could not be loaded" in e.value for e in app.error)
    goto(app, "Student Records")
    assert not app.exception and len(app.dataframe) == 0
    goto(app, "Dataset Management")
    assert not app.exception and any("not valid" in e.value for e in app.error)
    upload(app, "fix.csv", GOOD_UPLOAD)
    click(app, "Use this dataset")
    goto(app, "Dashboard")
    assert metrics(app)["Total students"] == "3"


def test_missing_bundled_file(monkeypatch, tmp_path):
    monkeypatch.setattr(fn, "DEFAULT_DATASET_PATH", tmp_path / "gone.csv")
    app = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not app.exception and any("not found" in md.value for md in app.markdown)
