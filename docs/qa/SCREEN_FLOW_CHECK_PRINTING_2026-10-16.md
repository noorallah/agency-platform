# Screen cases, printing (P1, P2): click tests against the real server, 2026-10-16

Flow: `desktop/integration_test/sc_prt_test.dart`. Books: `08_SELLING.md`
TC-SELL-099, `09_PRICING_AND_INCENTIVES.md` TC-SELL-109, TC-SELL-112 and
TC-SELL-117 (the screen steps; the HTTP half is
`PRINTING_API_CHECK_ROUND_1_2026-10-15.md`).

Firm: the printing round's first `ready-firm` (**Ready t1015r7nh**, firm id
`53a34ccb-68f2-4aef-ac47-7f7c9bbad9c5`), built by `scripts/test_fixture.py
ready-firm` through `docs/qa/checks/printing/setup.py` on 2026-10-15. It was
**reused, not rebuilt**: this unattended run was refused permission to run the
fixture script (it writes a platform-admin row in-process), so the flow runs on
the fixture the API round made. Every run makes its own masters and bills, and
puts the firm's print template and sales stages back as it found them, so the
firm is left as the API round left it (A4, three copies, no terms). Users:
`t1015r7nh.readyadmin@fixtures.local` (Firm admin) and
`t1015r7nh.readyviewer@fixtures.local` (VIEWER), password `Fixture@2026pw`.
Window 1600x1000.

Every run makes over HTTP, named with the minute it started and the run's user
(`0853A` = 08:53, admin): a plain stocked item `0P<tag>` (300 on hand); four
customers `PA<tag>` (Firm's setting), `PB<tag>` (Firm's setting, set to Full
page on the screen), `PC<tag>` (Bill paper Half page); and, for the admin, two
batch- and manufacture-date-tracked items `0M<tag>` (batch `MF<tag>`, made
2026-01-15, expiry 2027-12-31, MRP 150) and `0N<tag>` (batch `NM<tag>`, no
manufacture date), a salesman `PRT Asha <tag>`, and a round `Market <tag>`
(region > territory > route) with `PR<tag>` on it and the salesman assigned.
With the order and note stages switched off for the moment (put back at once),
it types and approves: a one-line bill for PA (short), a sixty-line bill for PA
(long), one-line bills for PB and PC, and for the admin the round's bill for PR
naming the salesman and the round: 4 of 0M with 1 free and 6 of 0N.

**What was printed is what the app handed the printer.** The flow replaces the
operating system's print dialog (`PrintingPlatform.instance`) with one that
keeps the bytes and answers "printed", so every Print below ran the real
screen code up to the printer, nothing reached a printer, and the flow read
that very PDF: page sizes off each page's `/MediaBox` (A4 595 x 842, half page
595 x 421) and the text off its flate/ASCII85 streams. The paper box and the
settings dialog were read on screen.

## How to run it

From `desktop/` in Git Bash, one run at a time, each in a brand-new
`TEMP`/`TMP` folder:

```
IT_EMAIL=t1015r7nh.readyadmin@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1500 bash integration_test/run.sh sc_prt_test.dart
IT_EMAIL=t1015r7nh.readyviewer@fixtures.local IT_PASSWORD='Fixture@2026pw' LIMIT=1200 bash integration_test/run.sh sc_prt_test.dart
```

`IT_PART=settings`, `half` or `full` runs one part of the admin flow (`half`
puts the firm on Half page over HTTP if `settings` did not run). The admin run
takes about six minutes after the build, the Viewer three. Of eight runs, two
died before the flow began ("Unable to start the app on the device"; "did not
complete" 40 s in, which left the template on Half page with that run's terms,
put back by hand over HTTP); the same flow then ran in a new folder. A run that
dies mid-way does not reach its own `finally`, so check the template after one.

## Results

| Case | Step | Firm admin | Viewer | Values seen |
| --- | --- | --- | --- | --- |
| TC-SELL-099 1 | Print settings reads what the server holds | PASS | PASS | Admin: Paper A4, 3 copies, Terms blank; server A4, 3 labels, terms null. Viewer (firm on Half page): Paper Half page, as the server |
| TC-SELL-099 1 / TC-SELL-112 1 | Half page and two lines of terms saved | PASS | — | The line "A bill too long for half a page prints on a full page by itself." shows; no Bill layout box on Half page; "Print settings saved."; server HALF, terms the two typed lines; copies 3 -> 3 and declaration unchanged |
| PRT-S2 | Reopened: paper and terms read back | PASS | — | Paper Half page; both lines of terms |
| TC-SELL-109 2 | Short bill on a half-page firm | PASS | PASS | Box "Print SI-26-27-000097", "This bill prints on a Half page.", "Check the paper in the printer's tray before printing."; Half page chosen, Full page offered; server `paper` HALF, `may_choose` true; printed 3 half pages (one per copy); "SI-26-27-000097 sent to the printer." |
| TC-SELL-109 3 | One print switched to Full page | PASS | PASS | Sentence follows the choice: "This bill prints on a Full page."; printed 3 A4 pages |
| TC-SELL-109 4, 8 | Box opens on Half again; Cancel | PASS | — | Opens on Half page; Cancel: nothing printed, no message |
| TC-SELL-099 4 | Customer B's Bill paper set on the customer screen | PASS | — | Masters > Customers > PB > Edit, Money section: the box starts on "Firm's setting", helper "Read where the firm prints its bills on half pages."; Full page (A4) chosen, Save customer: "Customer updated."; server `bill_page_size` A4 |
| TC-SELL-109 5 | B's bill | PASS | — | "This bill prints on a Full page: this customer's bills are set to a full page."; Full page chosen, Half offered; server A4 / customer A4; printed 3 A4 pages |
| TC-SELL-109 6 | B's bill switched to Half | PASS | — | 3 half pages |
| TC-SELL-099 3 / TC-SELL-109 7 | Sixty-line bill | PASS | PASS | "This bill prints on a Full page: it is too long for half a page."; no choice offered; server A4, `fits_half_page` false; 6 A4 pages (2 per copy) |
| TC-SELL-112 4 | Round's bill on half pages | PASS | — | 3 half pages; Market "Market 0853A"; Total quantity 10, 1 under Free; the terms under the amount in words; no Mfg column |
| TC-SELL-099 6 | Paper back to A4 on the screen | PASS | — | The half-page line goes, Bill layout returns; "Print settings saved."; server A4, terms kept |
| TC-SELL-109 1 / TC-SELL-099 7 | Full-page firm, customer on Half page | PASS | — | No box opened (no Half choice anywhere); printed 3 A4 pages; server `customer_paper` null, `may_choose` false |
| TC-SELL-112 3 / TC-SELL-117 | Round's bill on A4 | PASS | — | No box; 3 A4 pages. First copy: columns Batch, **Mfg**, Expiry; line 1 `MF0853A` **01/26** 2027-12-31; line 2 `NM0853A` then straight to 2027-11-30 (Mfg blank); "Total quantity, and 1 free" **10** = server lines 4 + 6, free 1 not in it; the two terms lines under TERMS at the foot; **Market** "Market 0853A"; **Order By** "PRT Asha 0853A" |
| TC-SELL-117 / TC-SELL-112 5 | Bill with no salesman, round or batch | PASS | — | 3 A4 pages; no Order By, no Market, no Mfg; Total quantity present |
| PRT-V1 | Viewer: Print settings | — | PASS (after fix) | Paper Half page as the server; Paper and Terms boxes disabled, Save disabled, Preview enabled; on screen "You can read these settings but not change them: your role does not allow changing settings."; HTTP PUT as the Viewer 403 "You do not have permission to perform this action."; server unchanged. **Failed before the fix**: nothing said why |
| PRT-V3 | Viewer: long bill | — | PASS | Too-long box, no choice; 6 A4 pages |

Last full runs: Firm admin passed 15, failed 0, not run 2; Viewer passed 3,
failed 0, not run 0. No app error and no overflow in any run.

Not clicked:

- **TC-SELL-099 5 / TC-SELL-109 9** (*Print selected*): the bulk run's order
  and paper per bill is the server's check; the button is
  `print_selected_test.dart`.
- **TC-SELL-099 2** column list and layout details of the half page beyond
  Market, Total quantity, terms and no Mfg; the GST summary was not compared.
- **TC-SELL-117** trade layout, a deleted salesman, the roll; **TC-SELL-113**
  (Trade layout and Preview) was not driven. Preview's button state was read
  for the Viewer only.
- **TC-SELL-099 8** (customer back to Firm's setting).
- The bills were made over HTTP (counter bills with the stages off), not typed
  on the screen; the round's bill's salesman and round were not read on the
  bill's own view.
- No real printer and no operating-system print dialog: the PDF is read where
  the app hands it over.

## Defects found

1. **Screen, fixed (Medium): Print settings that failed to load could be saved
   over the firm's settings.** In the second admin run the dialog's save wrote
   `copy_labels: []` and `declaration: null` (audit trail, 08:32:00, firm
   t1015r7nh) though the firm held three copies and the declaration and the
   flow had changed only the paper and the terms; every later print of that
   run came out as one copy. The server logged the dialog's GET as 200, so the
   read was lost on the way back (the dropped connection `harness.dart` already
   retries for); the dialog then showed its blank defaults with every box and
   **Save** live, and saving wrote the blanks over the firm's copies,
   declaration and letterhead. Fix
   (`desktop/lib/ui/workspace/print_settings_dialog.dart`): the boxes, Save and
   Preview work only once the settings have been read; a failed read says
   "... The settings could not be read, so nothing here can be saved: close
   this and open it again." and no longer claims these are the platform
   defaults. Guard: `desktop/test/print_settings_test.dart` "settings that
   could not be read cannot be saved over" (red without the fix). The flow now
   also checks the copies and the declaration survive the save.
2. **Screen, fixed (Low): a Viewer was not told why Print settings cannot be
   saved.** Every box greyed and Save dead, with nothing on screen saying why.
   The dialog now says "You can read these settings but not change them: your
   role does not allow changing settings." Guard:
   `desktop/test/print_settings_test.dart` "somebody who may only view is told
   why nothing can be saved" (red without the fix) and "somebody who may change
   it is not told otherwise".

No server defect found. D-PRT-1 (an unsaved firm's template listing no copies)
is fixed on main: the second printing firm, never saved, reads three labels.
