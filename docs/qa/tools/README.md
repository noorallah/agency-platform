# Regenerating the QA suite

**Decision 2026-10-16: the files in `docs/qa/` are edited by hand from now
on; do not regenerate them over the top.** Hand edits outside the case blocks
(role counts, preconditions, lot notes, system-role rows) live only there, and
a regeneration drops them: a trial run on 2026-10-16 differed in eight files
(01, 03, 04, 05, 06, 07, 09, 13). The hand-added "Clicked/Driven" notes were
carried back into `docs/INDEPENDENT_TEST_CASES.md` (#1635). A new case goes
into the source *and* into its `docs/qa` file by hand. Regenerate into a
scratch folder and diff only to find a case missing from `docs/qa`.

The files in `docs/qa/` (except `00_README.md`, which is written by hand)
are generated. Regenerate them when `docs/INDEPENDENT_TEST_CASES.md`, the
role seed or the desktop's screen catalogue changes. Put the three JSON
files in one scratch folder, `OUT` below.

1. From `backend/`: `.venv\Scripts\python.exe ..\docs\qa\tools\export_roles.py OUT`
2. Copy `qa_matrix_test.dart.txt` to `desktop/test/zz_qa_matrix_tmp_test.dart`,
   set its `OUT`, run `flutter test test/zz_qa_matrix_tmp_test.dart` from
   `desktop/`, and delete the copy.
3. From the repository root: `python docs\qa\tools\generate_qa_suite.py . OUT`

The generator maps each developer fixture to a plain-language precondition
(`PREP`), and each source section to a module file (`FILES`). A new fixture
or section stops the run until it has an entry. For the PDFs, render each
file with `packaging/render_guide.py` and print it with Edge, as
`docs/RELEASE_BUILD.md` describes for the installation guide.
