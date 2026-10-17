"""Command-line entry point: runs the required analysis and prints a report.

Usage:
    python main.py                      # analyse the bundled dataset
    python main.py --file my.csv        # analyse another CSV
    python main.py --export             # also write CSV/Markdown reports to outputs/

All calculations come from functions.py, the same engine the GUI uses.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import functions as fn


def print_section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Student Performance Analytics (command line)")
    parser.add_argument("--file", default=str(fn.DEFAULT_DATASET_PATH), help="CSV file to analyse")
    parser.add_argument("--export", action="store_true", help="write reports to the outputs/ folder")
    args = parser.parse_args(argv)

    result = fn.load_students_csv(args.file)
    if not result.ok:
        print("The dataset is not valid:")
        for message in result.errors:
            print(f"  - {message}")
        return 1
    df = result.data

    # Variables and data types: simple values taken from the engine's summary.
    summary = fn.class_summary(df)
    student_count = summary["total_students"]          # int
    class_average = summary["class_average"]           # float
    dataset_name = result.source_name                  # str
    all_passed = summary["fail_count"] == 0            # bool

    print("STUDENT PERFORMANCE ANALYTICS SYSTEM")
    print(f"Dataset: {dataset_name} | Students: {student_count} | Subjects: {', '.join(fn.SUBJECTS)}")
    print(f"Class average: {class_average:.2f} | Everyone passed: {all_passed}")

    print_section("Per-student results")
    # Loop with a condition: print each student and flag low attendance.
    for _, row in df.iterrows():
        flag = "  (low attendance)" if row[fn.ATT_COL] < fn.ATTENDANCE_THRESHOLD else ""
        print(f"{row[fn.ID_COL]}  {row[fn.NAME_COL]:<16} total={row[fn.TOTAL_COL]:>5g} "
              f"avg={row[fn.AVG_COL]:>6.2f} grade={row[fn.GRADE_COL]:<2} {row[fn.RESULT_COL]}{flag}")

    print_section("Key metrics")
    print(f"Highest average : {summary['highest_average']:.2f} ({', '.join(summary['highest_students'])})")
    print(f"Lowest average  : {summary['lowest_average']:.2f} ({', '.join(summary['lowest_students'])})")
    print(f"Highest/lowest total marks: {summary['highest_total']:g} / {summary['lowest_total']:g}")
    print(f"Passed: {summary['pass_count']} ({summary['pass_percentage']:.1f}%) | "
          f"Failed: {summary['fail_count']} ({summary['fail_percentage']:.1f}%)")
    print(f"Best subject  : {', '.join(summary['best_subjects'])}")
    print(f"Lowest subject: {', '.join(summary['lowest_subjects'])}")

    print_section("Subject statistics")
    print(fn.subject_statistics(df).round(2).to_string(index=False))

    print_section("Grade distribution")
    print(fn.grade_distribution(df).round(1).to_string(index=False))

    print_section("Department performance")
    departments = fn.department_summary(df)
    print(departments.round(2).to_string(index=False))
    print(f"Best department: {', '.join(fn.best_departments(departments))}")

    print_section("Top five students")
    print(fn.top_students(df).round(2).to_string(index=False))

    print_section("Attendance")
    attendance = fn.attendance_summary(df)
    print(f"Average {attendance['average']:.1f}% | below {attendance['threshold']:g}%: "
          f"{attendance['below_count']} | at least {attendance['threshold']:g}%: {attendance['at_least_count']}")

    if args.export:
        fn.OUTPUT_DIR.mkdir(exist_ok=True)
        for key, (file_name, data, _mime) in fn.build_report_files(df, df, dataset_name).items():
            if key == "filtered":
                continue  # identical to the complete file when no filter is applied
            (fn.OUTPUT_DIR / file_name).write_bytes(data)
        print(f"\nReports written to {Path(fn.OUTPUT_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
