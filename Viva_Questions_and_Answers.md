# Viva Questions and Answers

**1. What does the project do?**
It reads student marks from a CSV, validates them, calculates total, average, grade and pass/fail for each student, and shows class, subject, department and attendance analysis in a Streamlit dashboard.

**2. Where is NumPy used?**
In `analyze_students()` the five subject columns become a NumPy matrix (`to_numpy`). `marks.sum(axis=1)` gives every student's total, `marks.min(axis=1)`-style row checks support the pass rule, and NumPy also gives medians (`np.median`), correlation (`np.corrcoef`), histograms (`np.histogram`) and tie checks (`np.isclose`).

**3. Where is Pandas used?**
For reading the CSV (`read_csv`), storing students in a DataFrame, filtering and sorting, `groupby` for departments, `value_counts` for grades, `pd.cut` for attendance bands and `to_csv` for downloads.

**4. How is the grade decided?**
`calculate_grade(average)` checks the average against 90, 80, 70, 60 and 50 in order and returns A+, A, B, C or D; anything lower is F.

**5. What are the pass rules?**
Average at least 40 **and** every subject at least 35. These are project-defined rules, not from the assignment.

**6. Why can a student have grade F but still pass?**
Grade F means an average below 50, but passing only needs 40. So an average of 45 gives F and Pass (S016 in the dataset). The app explains this.

**7. Why does S018 fail with an average of 60?**
Their NumPy mark is 30, below the subject minimum of 35.

**8. Which student is on the boundary of A+?**
S002 has an average of exactly 90.0 (A+); S003 has 89.8 (A).

**9. Where do you use loops, conditions and functions?**
Loop: `analyze_students()` over students and `subject_statistics()` over subjects. Conditions: `calculate_grade()` and `determine_result()`. Functions: every calculation is a reusable function in `functions.py`.

**10. Why keep calculations out of `app.py`?**
So every page, the downloads and the command line use the same code and cannot disagree, and so the logic can be tested without the GUI.

**11. How is invalid data handled?**
`load_students_csv()` checks the file, field counts, columns, missing values, non-numeric values, ranges and duplicate IDs. All problems are listed and the file is not analysed. Missing marks are never turned into zero.

**12. What happens with ties?**
Highest/lowest performers, best subject, best department and the top five return all tied items. Top five uses competition ranking so students tied at fifth place are all shown.

**13. How do you know the calculations are right?**
A hand-calculated four-student dataset, boundary tests (49.99, 50, 59.99, ...), an independent plain-Python recomputation of the bundled data (0 mismatches), and GUI tests comparing displayed metrics with engine output.

**14. Why round the total to six decimals?**
Decimal marks can produce totals like 399.99999999, which could drop a student to the wrong grade. Rounding removes the noise without changing real values.

**15. Does attendance affect the result?**
No. Below 75% is only flagged. The correlation chart does not prove causation.

**16. What happens to an uploaded file?**
It is validated and held in memory only after you confirm. It never overwrites `data/students.csv`, and "Return to the bundled dataset" restores the default.

**17. How do you run it?**
`python -m streamlit run app.py`, open the Local URL printed in the terminal. Tests: `python -m pytest -q`.

**18. What are the limitations?**
Exact-name matching for departments, uploads kept only for the session, UTF-8 CSV with exact column names, and Windows commands not run during development (verified on Linux).
