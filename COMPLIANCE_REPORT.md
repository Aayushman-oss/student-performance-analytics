# Compliance Report

Status key: **PASS** implemented and verified; **PENDING STUDENT ACTION** needs an external action by the student; **NOT VERIFIED** could not be tested here.

Verification environment: Linux, Python 3.12. Methods: **T** = pytest (89 engine + 45 GUI tests, 134 total, all passing); **B** = real headless Chromium run against the live Streamlit server; **X** = independent plain-Python recomputation of every student's total, average, grade and result from the CSV (0 mismatches); **I** = inspection.

## Core assignment

| Requirement | File | Method | Status |
|---|---|---|---|
| Python used | all `.py` | I | PASS |
| NumPy used meaningfully | `functions.py` (`analyze_students`, `subject_statistics`, correlation, histogram) | I, T | PASS |
| Pandas DataFrame used | `functions.py`, `app.py` | I, T | PASS |
| Variables and data types | `main.py` (int, float, str, bool), `functions.py` constants | I | PASS |
| Loops | `analyze_students`, `subject_statistics`, `main.py` | I | PASS |
| Reusable functions | `functions.py` | I, T | PASS |
| Conditional statements | `calculate_grade`, `determine_result`, validation | I, T | PASS |
| At least 20 fictional records | `data/students.csv` (25) | T | PASS |
| ID, Name, Department, 5 subjects, Attendance | `data/students.csv` | T | PASS |
| Total, average, grade, pass/fail | `functions.analyze_students` | T, X | PASS |
| Highest/lowest performance, overall average | `class_summary`, `extreme_students` | T, B | PASS |
| Subject-wise analysis, best/lowest subject | `subject_statistics`, `best_and_lowest_subjects` | T, B | PASS |
| Top-performing students | `top_students` | T, B | PASS |

## GUI

| Requirement | Method | Status |
|---|---|---|
| Dashboard (9 metrics, 4 charts, top table, file name and count) | T, B (screenshot) | PASS |
| Student Records, search, 4 filters, sort, count, reset | T, B | PASS |
| Individual Student Analysis incl. class comparison and interpretation | T, B | PASS |
| Subject, Department, Attendance, Grade and Result pages | T, B | PASS |
| Dataset upload, validation, preview, reset | T, B | PASS |
| Five downloads contain current data | T (content, engine level), B (all five files downloaded; complete and filtered CSV contents inspected) | PASS |
| Empty/invalid/one-record states handled | T | PASS |
| No hardcoded values; all pages use one engine | I, T (dashboard values equal engine values) | PASS |

## Quality

| Requirement | Method | Status |
|---|---|---|
| Calculation logic centralised in `functions.py` | I | PASS |
| Validation (missing file/columns/values, duplicates, ranges, malformed, empty, one record) | T, B | PASS |
| Grade and pass/fail boundaries (0, 49.99, 50 ... 90, 100; avg 40; subject 35) | T | PASS |
| Ties, fewer than five students, empty data | T | PASS |
| Dependencies install from `requirements.txt` in a fresh venv; suite passes on newest and oldest allowed versions | T | PASS |
| Run commands on Windows PowerShell | not executed on Windows; equivalent Linux commands verified | NOT VERIFIED |

## Submission

| Item | Status |
|---|---|
| Dataset, app, requirements, README, formal documentation, tests, screenshots included | PASS |
| `.gitignore` excludes venvs, caches, generated outputs | PASS |
| GitHub repository created and pushed | PENDING STUDENT ACTION |
| Repository accessibility checked, URL verified | PENDING STUDENT ACTION |
| EWB Google Form submitted | PENDING STUDENT ACTION |
| Student details and repository URL placeholders in `Project_Documentation.md` filled | PENDING STUDENT ACTION |

## Defects found and fixed during the audit

1. `st.dataframe(height=None)` rejected by Streamlit (crashed 6 pages).
2. Pandas `melt` column-name clash on the Department page.
3. Rows with extra fields silently shifted columns; now rejected by a field-count check.
4. Error messages said "Attendance (%)"; now "Attendance".
5. `delta_arrow` needs a newer Streamlit than first declared; minimum raised to the verified 1.66.
6. Metric cards uneven height and a truncated "Bundled dataset" card (layout).

## Notes

- Grade F (average below 50) still passes when average is at least 40 and all subjects at least 35. This follows the stated rules; three students in the dataset (S015, S016, S017) show it.
- Screenshot 11 was taken with a small uploaded test file (3 students), not the bundled dataset.
