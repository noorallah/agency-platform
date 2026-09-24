# Regenerating the QA suite

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
