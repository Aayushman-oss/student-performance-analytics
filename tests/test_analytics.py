"""Tests for the calculation engine (functions.py). No Streamlit involved."""

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import functions as fn  # noqa: E402

HEADER = ",".join(fn.REQUIRED_COLUMNS)


def make_row(student_id="S1", name="Test", dept="Dept", marks=(50, 50, 50, 50, 50), attendance=80):
    return [student_id, name, dept, *marks, attendance]


def make_csv(rows, header=HEADER) -> bytes:
    lines = [header] + [",".join(str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def load(rows, header=HEADER):
    return fn.load_students_csv(make_csv(rows, header), "test.csv")


def analysed(rows) -> pd.DataFrame:
    result = load(rows)
    assert result.ok, result.errors
    return result.data


@pytest.fixture
def small():
    """Hand-calculated 4-student dataset.

    A: all 100 -> total 500, avg 100, A+, Pass
    B: 80,70,60,50,40 -> total 300, avg 60, C, Pass
    C: 50,40,30,60,20 -> total 200, avg 40 but two subjects < 35 -> Fail (grade F)
    D: all 45 -> total 225, avg 45, grade F but Pass
    """
    return analysed([
        make_row("A", "Alice", "X", (100, 100, 100, 100, 100), 100),
        make_row("B", "Bob", "X", (80, 70, 60, 50, 40), 74),
        make_row("C", "Cara", "Y", (50, 40, 30, 60, 20), 90),
        make_row("D", "Dan", "Y", (45, 45, 45, 45, 45), 75),
    ])


# ---------------------------------------------------------------- calculations

def test_total_and_average_use_subjects_only(small):
    assert small[fn.TOTAL_COL].tolist() == [500, 300, 200, 225]
    assert small[fn.AVG_COL].tolist() == [100, 60, 40, 45]   # total / 5 subjects
    # Attendance (100, 74, 90, 75) must not leak into the totals.
    assert fn.SUBJECTS == ["Python", "Statistics", "NumPy", "Pandas", "Data_Analysis"]
    assert fn.ATT_COL not in fn.SUBJECTS and fn.ID_COL not in fn.SUBJECTS


def test_grades_and_results(small):
    assert small[fn.GRADE_COL].tolist() == ["A+", "C", "F", "F"]
    assert small[fn.RESULT_COL].tolist() == ["Pass", "Pass", "Fail", "Pass"]


def test_class_summary_matches_hand_calculation(small):
    s = fn.class_summary(small)
    assert s["total_students"] == 4 and s["total_subjects"] == 5
    assert s["class_average"] == pytest.approx(61.25)
    assert s["highest_average"] == 100 and s["lowest_average"] == 40
    assert s["highest_total"] == 500 and s["lowest_total"] == 200
    assert s["pass_count"] == 3 and s["fail_count"] == 1
    assert s["pass_percentage"] == pytest.approx(75.0) and s["fail_percentage"] == pytest.approx(25.0)
    assert s["average_attendance"] == pytest.approx(84.75)
    assert s["best_subjects"] == ["Python"] and s["lowest_subjects"] == ["Data_Analysis"]


def test_subject_statistics(small):
    stats = fn.subject_statistics(small).set_index("Subject")
    assert stats.loc["Python", "Average"] == pytest.approx(68.75)
    assert stats.loc["Statistics", "Average"] == pytest.approx(63.75)
    assert stats.loc["NumPy", "Average"] == pytest.approx(58.75)
    assert stats.loc["Data_Analysis", "Average"] == pytest.approx(51.25)
    assert stats.loc["Python", "Median"] == 65            # 45, 50, 80, 100
    assert stats.loc["Python", "Highest"] == 100 and stats.loc["Python", "Lowest"] == 45
    assert stats.loc["NumPy", "Passing"] == 3 and stats.loc["NumPy", "Failing"] == 1      # Cara has 30
    assert stats.loc["Data_Analysis", "Failing"] == 1                                       # Cara has 20
    assert stats.loc["Python", "Failing"] == 0
    assert (stats["Passing"] + stats["Failing"] == len(small)).all()


def test_best_and_lowest_subject_ties():
    df = analysed([make_row(marks=(80, 80, 60, 60, 70))])
    best, lowest = fn.best_and_lowest_subjects(fn.subject_statistics(df))
    assert best == ["Python", "Statistics"] and lowest == ["NumPy", "Pandas"]


def test_grade_distribution_includes_empty_grades_and_reconciles(small):
    dist = fn.grade_distribution(small)
    assert dist["Grade"].tolist() == fn.GRADE_ORDER
    assert dist.set_index("Grade")["Students"].to_dict() == {"A+": 1, "A": 0, "B": 0, "C": 1, "D": 0, "F": 2}
    assert dist["Students"].sum() == len(small)
    assert dist["Percentage"].sum() == pytest.approx(100.0)


def test_result_distribution_reconciles(small):
    dist = fn.result_distribution(small).set_index("Result")
    assert dist.loc["Pass", "Students"] == 3 and dist.loc["Fail", "Students"] == 1
    assert dist["Students"].sum() == len(small)
    assert dist.loc["Pass", "Percentage"] == pytest.approx(75.0)


def test_department_summary(small):
    dept = fn.department_summary(small).set_index(fn.DEPT_COL)
    assert dept.loc["X", "Students"] == 2 and dept.loc["Y", "Students"] == 2
    assert dept.loc["X", "Average_Marks"] == pytest.approx(80.0)
    assert dept.loc["Y", "Average_Marks"] == pytest.approx(42.5)
    assert dept.loc["X", "Passed"] == 2 and dept.loc["Y", "Passed"] == 1 and dept.loc["Y", "Failed"] == 1
    assert dept.loc["Y", "Pass_Percentage"] == pytest.approx(50.0)
    assert fn.best_departments(fn.department_summary(small)) == ["X"]


def test_departments_are_not_fixed_and_ties_are_reported():
    df = analysed([make_row("1", "A", "Alpha", (60,) * 5), make_row("2", "B", "Beta", (60,) * 5),
                   make_row("3", "C", "Gamma", (10 + 35,) * 5)])
    summary = fn.department_summary(df)
    assert len(summary) == 3
    assert fn.best_departments(summary) == ["Alpha", "Beta"]      # tie, alphabetical


def test_attendance_statistics(small):
    att = fn.attendance_summary(small)
    assert att["average"] == pytest.approx(84.75)
    assert att["highest"] == 100 and att["lowest"] == 74
    assert att["below_count"] == 1 and att["at_least_count"] == 3      # 75 is NOT below 75
    low = fn.low_attendance_students(small)
    assert low[fn.ID_COL].tolist() == ["B"]
    assert fn.attendance_distribution(small)["Students"].sum() == len(small)


def test_attendance_does_not_change_result():
    low = analysed([make_row(marks=(90,) * 5, attendance=0)])
    assert low[fn.RESULT_COL].iloc[0] == "Pass" and low[fn.GRADE_COL].iloc[0] == "A+"


def test_attendance_correlation_edge_cases(small):
    assert fn.attendance_marks_correlation(small) is not None
    assert fn.attendance_marks_correlation(small.head(2)) is None
    flat = analysed([make_row(str(i), marks=(50 + i,) * 5, attendance=80) for i in range(4)])
    assert fn.attendance_marks_correlation(flat) is None


# -------------------------------------------------------------------- rankings

def test_top_students_order_and_limit(small):
    top = fn.top_students(small, 3)
    assert top[fn.ID_COL].tolist() == ["A", "B", "D"]
    assert top["Rank"].tolist() == [1, 2, 3]


def test_top_five_with_fewer_than_five_students(small):
    assert len(fn.top_students(small, 5)) == 4


def test_top_five_includes_students_tied_at_the_cutoff():
    rows = [make_row(f"S{i}", f"N{i}", marks=(90 - i,) * 5) for i in range(4)]
    rows += [make_row("T1", "Tie1", marks=(80,) * 5), make_row("T2", "Tie2", marks=(80,) * 5),
             make_row("L", "Low", marks=(50,) * 5)]
    top = fn.top_students(analysed(rows), 5)          # ranks: 1,2,3,4,5,5,7
    assert len(top) == 6 and top["Rank"].tolist() == [1, 2, 3, 4, 5, 5]


def test_tied_highest_and_lowest_performers():
    df = analysed([make_row("1", "A", marks=(90,) * 5), make_row("2", "B", marks=(90,) * 5),
                   make_row("3", "C", marks=(40,) * 5), make_row("4", "D", marks=(40,) * 5)])
    assert fn.extreme_students(df, fn.AVG_COL, True)[fn.ID_COL].tolist() == ["1", "2"]
    assert fn.extreme_students(df, fn.AVG_COL, False)[fn.ID_COL].tolist() == ["3", "4"]
    assert fn.class_summary(df)["highest_students"] == ["A", "B"]


# ------------------------------------------------------------------ boundaries

@pytest.mark.parametrize("average, grade", [
    (0, "F"), (49.99, "F"), (50, "D"), (59.99, "D"), (60, "C"), (69.99, "C"),
    (70, "B"), (79.99, "B"), (80, "A"), (89.99, "A"), (90, "A+"), (100, "A+"),
])
def test_grade_boundaries(average, grade):
    assert fn.calculate_grade(average) == grade


@pytest.mark.parametrize("average, grade", [
    (49.99, "F"), (50, "D"), (59.99, "D"), (60, "C"), (69.99, "C"),
    (70, "B"), (79.99, "B"), (80, "A"), (89.99, "A"), (90, "A+"), (100, "A+"), (0, "F"),
])
def test_grade_boundaries_end_to_end(average, grade):
    df = analysed([make_row(marks=(average,) * 5)])
    assert df[fn.GRADE_COL].iloc[0] == grade


def test_floating_point_noise_cannot_change_the_grade():
    df = analysed([make_row(marks=(90.1, 89.9, 90.0, 90.0, 90.0))])   # total is exactly 450
    assert df[fn.GRADE_COL].iloc[0] == "A+"
    df = analysed([make_row(marks=(79.9, 80.1, 80.0, 80.0, 80.0))])
    assert df[fn.GRADE_COL].iloc[0] == "A"


@pytest.mark.parametrize("bad", [-0.01, 100.01, float("nan"), float("inf")])
def test_grade_rejects_impossible_averages(bad):
    with pytest.raises(ValueError):
        fn.calculate_grade(bad)


def test_pass_fail_rules():
    assert fn.determine_result(40, [40] * 5) == "Pass"                      # average exactly 40
    assert fn.determine_result(40, [35, 35, 45, 45, 40]) == "Pass"          # subject exactly 35
    assert fn.determine_result(66, [90, 90, 90, 31, 29]) == "Fail"      # avg ok, subjects below 35
    assert fn.determine_result(39.8, [40, 40, 40, 39, 40]) == "Fail"        # all >= 35 but average < 40
    assert fn.determine_result(60, [34.99, 70, 70, 70, 70]) == "Fail"       # average passes, one subject fails


def test_pass_fail_end_to_end():
    df = analysed([
        make_row("1", marks=(40, 40, 40, 40, 40)),        # avg 40 -> Pass
        make_row("2", marks=(35, 35, 45, 45, 40)),        # avg 40, min 35 -> Pass
        make_row("3", marks=(80, 80, 80, 80, 34)),        # avg 70.8, one subject 34 -> Fail
        make_row("4", marks=(38, 40, 40, 41, 40)),        # avg 39.8 -> Fail
    ])
    assert df[fn.RESULT_COL].tolist() == ["Pass", "Pass", "Fail", "Fail"]


def test_mark_distribution_bins():
    dist = fn.mark_distribution([0, 9.99, 10, 55, 89.99, 90, 100])
    counts = dict(zip(dist["Marks range"], dist["Students"]))
    assert counts["0 to <10"] == 2 and counts["10 to <20"] == 1 and counts["50 to <60"] == 1
    assert counts["80 to <90"] == 1 and counts["90 to 100"] == 2
    assert dist["Students"].sum() == 7


# ------------------------------------------------------------------ validation

def error_text(result) -> str:
    return " ".join(result.errors)


def test_valid_bundled_dataset():
    result = fn.load_students_csv(fn.DEFAULT_DATASET_PATH)
    assert result.ok and len(result.data) >= 20
    assert set(fn.REQUIRED_COLUMNS) <= set(result.data.columns)
    assert result.data[fn.ID_COL].is_unique
    assert result.data[fn.DEPT_COL].nunique() >= 3


def test_missing_file(tmp_path):
    result = fn.load_students_csv(tmp_path / "nope.csv")
    assert not result.ok and "not found" in error_text(result).lower()


@pytest.mark.parametrize("content", [b"", b"   \n  \n", b"\xef\xbb\xbf"])
def test_empty_csv(content):
    result = fn.load_students_csv(content, "empty.csv")
    assert not result.ok and result.data is None and "empty" in error_text(result).lower()


def test_header_only_csv():
    result = fn.load_students_csv((HEADER + "\n").encode(), "h.csv")
    assert not result.ok and "no student records" in error_text(result)


def test_missing_columns_are_all_listed():
    header = "Student_ID,Name,Python"
    result = load([["S1", "A", 50]], header)
    assert not result.ok
    for column in ("Department", "Statistics", "NumPy", "Pandas", "Data_Analysis", "Attendance"):
        assert column in error_text(result)
    assert fn.CAT_COLUMNS in result.failed_categories()


def test_duplicate_ids():
    result = load([make_row("S1", "A"), make_row("S2", "B"), make_row("S1", "C")])
    assert not result.ok and "'S1'" in error_text(result) and "rows 2, 4" in error_text(result)
    assert result.failed_categories() == {fn.CAT_DUPLICATE}


def test_duplicate_ids_ignore_surrounding_spaces():
    result = load([make_row("S1", "A"), make_row(" S1 ", "B")])
    assert fn.CAT_DUPLICATE in result.failed_categories()


@pytest.mark.parametrize("bad_marks", [(101, 50, 50, 50, 50), (-1, 50, 50, 50, 50), (50, 50, 50, 50, 100.5)])
def test_marks_out_of_range(bad_marks):
    result = load([make_row(marks=bad_marks)])
    assert not result.ok and fn.CAT_MARKS in result.failed_categories()


@pytest.mark.parametrize("bad_attendance", [101, -5, 100.1])
def test_attendance_out_of_range(bad_attendance):
    result = load([make_row(attendance=bad_attendance)])
    assert not result.ok and result.failed_categories() == {fn.CAT_ATTENDANCE}


def test_missing_values_are_reported_not_zeroed():
    rows = [make_row("S1", marks=("", 50, 50, 50, 50)), make_row("", "B"), make_row("S3", "", attendance="")]
    result = load(rows)
    assert not result.ok and result.data is None
    text = error_text(result)
    assert "Python is missing in row 2" in text and "Student ID is empty in row 3" in text
    assert "Name is empty" in text and "Attendance is missing" in text
    assert fn.CAT_MISSING in result.failed_categories()


@pytest.mark.parametrize("value", ["abc", "NaN", "inf", "5O", "--3"])
def test_non_numeric_marks(value):
    result = load([make_row(marks=(value, 50, 50, 50, 50))])
    assert not result.ok and fn.CAT_NUMERIC in result.failed_categories()


def test_all_problems_are_reported_together():
    rows = [make_row("S1", marks=(101, "x", 50, 50, 50), attendance=120), make_row("S1", "B")]
    assert len(load(rows).issues) >= 4


def test_malformed_csv_does_not_crash():
    malformed = (HEADER + "\nS1,A,Dept,50,50,50,50,50,80,EXTRA,FIELDS,HERE\n").encode()
    assert not fn.load_students_csv(malformed, "bad.csv").ok
    assert not fn.load_students_csv(b"\x00\x01\x02\xff\xfe binary", "bin.csv").ok
    assert not fn.load_students_csv(b'"unclosed,quote\nS1,\n', "q.csv").ok


def test_non_utf8_file():
    result = fn.load_students_csv(HEADER.encode() + b"\nS1,Ren\xe9,Dept,50,50,50,50,50,80\n", "latin.csv")
    assert not result.ok and "UTF-8" in error_text(result)


def test_rows_with_wrong_field_count_are_rejected_not_shifted():
    short = fn.load_students_csv((HEADER + "\nS1,A,Dept,50,50\n").encode(), "short.csv")
    assert not short.ok and "line 2 has 5 fields" in error_text(short)
    long = fn.load_students_csv((HEADER + "\nS1,A,Dept,50,50,50,50,50,80,99\n").encode(), "long.csv")
    assert not long.ok and "line 2 has 10 fields" in error_text(long)
    assert long.failed_categories() == {fn.CAT_FILE}
    # a quoted comma is a single field and must still load
    quoted = fn.load_students_csv((HEADER + '\nS1,"Doe, Jane",Dept,50,50,50,50,50,80\n').encode(), "q.csv")
    assert quoted.ok and quoted.data[fn.NAME_COL].iloc[0] == "Doe, Jane"


def test_one_record_dataset_works():
    df = analysed([make_row("ONLY", "Solo", marks=(70, 80, 90, 60, 50), attendance=60)])
    assert len(df) == 1
    s = fn.class_summary(df)
    assert s["class_average"] == pytest.approx(70) and s["pass_percentage"] == 100.0
    assert len(fn.top_students(df)) == 1 and len(fn.department_summary(df)) == 1
    assert fn.attendance_marks_correlation(df) is None
    assert fn.student_profile(df, "ONLY")["rank"] == 1


def test_extra_columns_are_kept_and_derived_columns_recalculated():
    csv = (HEADER + ",Notes,Total_Marks,Grade\nS1,A,D,50,50,50,50,50,80,hello,9999,Z\n").encode()
    result = fn.load_students_csv(csv, "extra.csv")
    assert result.ok and result.warnings
    row = result.data.iloc[0]
    assert row["Notes"] == "hello" and row[fn.TOTAL_COL] == 250 and row[fn.GRADE_COL] == "D"


def test_values_are_trimmed():
    df = analysed([[" S1 ", " Ann ", " Dept ", " 50", "50 ", 50, 50, 50, " 80 "]])
    assert df[fn.ID_COL].iloc[0] == "S1" and df[fn.NAME_COL].iloc[0] == "Ann"


def test_empty_dataset_functions_do_not_crash():
    empty = analysed([make_row()]).iloc[0:0]
    assert fn.class_summary(empty) == {"total_students": 0, "total_subjects": 5}
    assert fn.top_students(empty).empty and fn.department_summary(empty).empty
    assert fn.subject_statistics(empty).empty
    assert fn.best_and_lowest_subjects(fn.subject_statistics(empty)) == ([], [])
    assert fn.grade_distribution(empty)["Percentage"].sum() == 0
    assert fn.attendance_summary(empty)["students"] == 0
    assert fn.student_profile(empty, "x") is None


# ---------------------------------------------------------- filters and profile

def test_filtering_and_sorting_do_not_modify_the_source(small):
    before = small.copy(deep=True)
    out = fn.filter_students(small, search="a", sort_by=fn.NAME_COL, ascending=True)
    assert out[fn.NAME_COL].tolist() == ["Alice", "Cara", "Dan"]
    pd.testing.assert_frame_equal(small, before)


def test_filters(small):
    assert fn.filter_students(small, search="bob")[fn.ID_COL].tolist() == ["B"]
    assert fn.filter_students(small, search="  cara ")[fn.ID_COL].tolist() == ["C"]     # trimmed
    assert fn.filter_students(small, search="d")[fn.ID_COL].tolist() == ["D"]           # ID or name, any case
    assert sorted(fn.filter_students(small, departments=["Y"])[fn.ID_COL]) == ["C", "D"]
    assert fn.filter_students(small, grades=["A+"])[fn.ID_COL].tolist() == ["A"]
    assert fn.filter_students(small, results=["Fail"])[fn.ID_COL].tolist() == ["C"]
    assert sorted(fn.filter_students(small, attendance_range=(75, 100))[fn.ID_COL]) == ["A", "C", "D"]
    assert fn.filter_students(small, search="zzz").empty
    both = fn.filter_students(small, departments=["Y"], results=["Pass"])
    assert both[fn.ID_COL].tolist() == ["D"]


def test_search_is_literal_not_regex(small):
    assert fn.filter_students(small, search=".*").empty


def test_sorting(small):
    assert fn.filter_students(small, sort_by=fn.AVG_COL)[fn.ID_COL].tolist() == ["A", "B", "D", "C"]
    assert fn.filter_students(small, sort_by=fn.AVG_COL, ascending=True)[fn.ID_COL].tolist() == ["C", "D", "B", "A"]
    assert fn.filter_students(small, sort_by=fn.TOTAL_COL, ascending=True)[fn.ID_COL].tolist()[0] == "C"
    assert fn.filter_students(small, sort_by=fn.ATT_COL)[fn.ID_COL].tolist()[0] == "A"
    assert fn.filter_students(small, sort_by=fn.NAME_COL, ascending=True)[fn.NAME_COL].tolist() == ["Alice", "Bob", "Cara", "Dan"]
    with pytest.raises(ValueError):
        fn.filter_students(small, sort_by="Password")


def test_student_profile(small):
    p = fn.student_profile(small, "C")
    assert p["name"] == "Cara" and p["result"] == "Fail" and p["grade"] == "F"
    assert p["average"] == 40 and p["total"] == 200 and p["rank"] == 4
    assert p["difference"] == pytest.approx(40 - 61.25)
    assert "NumPy" in p["interpretation"] and "Data Analysis" in p["interpretation"]
    assert fn.student_profile(small, "nope") is None
    assert fn.student_profile(small, "B")["name"] == "Bob"      # never a different student


def test_interpretation_rules(small):
    assert "Met the pass criteria" in fn.student_profile(small, "A")["interpretation"]
    assert "well above the class average" in fn.student_profile(small, "A")["interpretation"]
    assert "slightly below" in fn.student_profile(small, "B")["interpretation"]
    assert "below the 75% threshold" in fn.student_profile(small, "B")["interpretation"]
    assert "same in every subject" in fn.student_profile(small, "D")["interpretation"]


# ------------------------------------------------------------- numeric & reports

def test_reconciliation_and_totals_equal_subject_sums():
    df = fn.load_students_csv(fn.DEFAULT_DATASET_PATH).data
    check = fn.reconciliation_check(df)
    assert check["grades_reconcile"] and check["results_reconcile"]
    assert check["totals_match"] and check["averages_match"]
    assert df[fn.TOTAL_COL].tolist() == df[fn.SUBJECTS].sum(axis=1).tolist()
    assert fn.grade_distribution(df)["Students"].sum() == len(df)
    assert fn.result_distribution(df)["Students"].sum() == len(df)
    assert fn.department_summary(df)["Students"].sum() == len(df)


def test_bundled_dataset_known_values():
    df = fn.load_students_csv(fn.DEFAULT_DATASET_PATH).data
    s = fn.class_summary(df)
    assert s["total_students"] == 25
    assert s["class_average"] == pytest.approx(65.816)
    assert (s["pass_count"], s["fail_count"]) == (21, 4)
    assert s["highest_students"] == ["Kavya Rao"] and s["lowest_students"] == ["Dev Malhotra"]
    assert fn.top_students(df)[fn.ID_COL].tolist() == ["S024", "S001", "S002", "S003", "S021"]
    assert fn.best_departments(fn.department_summary(df)) == ["Data Science"]
    assert fn.attendance_summary(df)["below_count"] == 9
    # Boundary students designed into the dataset
    by_id = df.set_index(fn.ID_COL)
    assert by_id.loc["S002", fn.GRADE_COL] == "A+" and by_id.loc["S003", fn.GRADE_COL] == "A"
    assert by_id.loc["S017", fn.RESULT_COL] == "Pass" and by_id.loc["S019", fn.RESULT_COL] == "Fail"
    assert by_id.loc["S018", fn.RESULT_COL] == "Fail" and by_id.loc["S018", fn.AVG_COL] == 60


def test_csv_export_round_trip(small):
    data = fn.to_csv_bytes(small)
    back = pd.read_csv(io.BytesIO(data))
    assert len(back) == len(small)
    for column in [*fn.REQUIRED_COLUMNS, *fn.DERIVED_COLUMNS]:
        assert column in back.columns
    assert back[fn.ID_COL].tolist() == small[fn.ID_COL].tolist()


def test_csv_export_rounds_only_calculated_columns():
    df = analysed([make_row(marks=(33.333, 50, 50, 50, 50), attendance=77.777)])
    back = pd.read_csv(io.BytesIO(fn.to_csv_bytes(df)))
    assert back["Python"].iloc[0] == 33.333 and back[fn.ATT_COL].iloc[0] == 77.777
    assert back[fn.AVG_COL].iloc[0] == round(df[fn.AVG_COL].iloc[0], 2)


def test_report_files_contain_current_data(small):
    filtered = fn.filter_students(small, results=["Fail"])
    files = fn.build_report_files(small, filtered, "demo.csv")
    assert set(files) == {"complete", "filtered", "subjects", "departments", "summary"}
    complete = pd.read_csv(io.BytesIO(files["complete"][1]))
    part = pd.read_csv(io.BytesIO(files["filtered"][1]))
    assert len(complete) == 4 and part[fn.ID_COL].tolist() == ["C"]
    assert len(pd.read_csv(io.BytesIO(files["subjects"][1]))) == 5
    assert set(pd.read_csv(io.BytesIO(files["departments"][1]))[fn.DEPT_COL]) == {"X", "Y"}
    report = files["summary"][1].decode()
    assert "demo.csv" in report and "61.25" in report and "Alice" in report


def test_summary_report_rejects_empty_data(small):
    with pytest.raises(ValueError):
        fn.build_summary_report(small.iloc[0:0])
