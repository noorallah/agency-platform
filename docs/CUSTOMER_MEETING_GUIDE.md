# Customer meeting guide

Which document to use at each point of a customer meeting, and what each one
holds. Written 2026-10-10. This page is for the person giving the meeting,
not for the customer.

The PDFs and the deck are in `dist\customer` (not in git). Their sources are
in `docs\`. Each PDF is built from its source by `packaging/md_to_pdf.py`
(source, then target); build it again after changing the source. The tool
needs the `pymupdf` package, which the backend's environment does not have,
so run it with the system Python.

---

## 1. Which document, when

| When | Document | Use |
| --- | --- | --- |
| Before the meeting | `CUSTOMER_REQUIREMENTS_QUESTIONS.pdf`, section 1 | Ask by phone or at the start |
| In the meeting | `Jugnix_Trade_Features_and_Demo.pptx` | Present it: 14 slides on the product (slides 2 to 5 are the installation, creating a firm, people and roles, and what a firm does every day), then the demonstration, then "not included" and next steps |
| In the meeting | The live demonstration on DEMO01 | The 30-minute story |
| After the demonstration | `CUSTOMER_REQUIREMENTS_QUESTIONS.pdf`, sections 2 to 11 | Fill in with the customer |
| To record the answers | `CUSTOMER_REQUIREMENTS_QUESTIONS.xlsx` | The same questions with a cell for each answer. Save a copy under the customer's name, type the answers in the yellow cells, and review it afterwards line by line with the Outcome and Reviewed columns |
| Before you leave | The collect list in section 4 of this page | What to bring back about their present software, so their data can be loaded |
| Leave with them | `CUSTOMER_FEATURE_BROCHURE.pdf` | Their copy: features, the counts, what is not included |
| Only if they ask about schemes and pricing | `PROMOTIONS_AND_DISCOUNTS_GUIDE.pdf`, sections 16 to 19 | The types, every field, and one worked order |

## 2. For you only, not the customer

| Document | What it is |
| --- | --- |
| `docs/CUSTOMER_DEMO_SCRIPT.md` | The step-by-step script, the preparation table, and the questions to expect with their answers |
| `docs/DEMO_FIRMS_USERS_AND_FEATURES.md` | The sign-ins and what DEMO01 holds |
| This page | Which document to use when |

---

## 3. The question list

`docs/CUSTOMER_REQUIREMENTS_QUESTIONS.md` -- 117 questions in ten
sections: the business, the goods, buying, selling, prices and offers, credit
and collections, stock, accounts and GST, people, and installation and data.
Each question says what it decides in the set-up, so an answer turns straight
into a setting.

- **Section 1 (seven questions) is asked before the demonstration.** The
  answers decide what to show: which lines of goods, one firm or several, and
  the three things that trouble them most.
- **The rest is asked after the demonstration**, when the customer has seen
  the screens.
- **Questions marked "check"** are where the answer may be something the
  application does not do: van sales, export, job work, a phone app for
  salesmen, portal upload, a machine link, remote access, interest on late
  payment, consignment stock, and bringing old transactions across. Do not
  say yes to these in the meeting.
- **Every question has a priority.** Critical (35): the answer can change
  how the application is designed, or decides whether it fits and how the
  firm is created; do not leave without these. High (57): may be something
  to build or support, or a setting needed before the first bill. Low (25):
  a setting that can wait. Every "check" question is at least High. When
  time is short, filter the Excel sheet on Critical.
- **Section 11 is a blank table** for "what do you do today that you did not
  see?", to bring back.
- **The Excel answer sheet** holds the same questions and is built from the
  question list by `backend/scripts/make_customer_questions_xlsx.py`. Run it
  again after changing a question; it writes a blank sheet over the one in
  `dist\customer`, so keep filled-in copies under another name.

The "check" marks on interest on late payment, consignment stock and remote
access are a caution: nobody confirmed on 2026-10-10 whether the application
covers them. Confirm before the meeting if the customer is likely to ask.

---

## 4. What to collect about their present software

Bring this back from the visit. It decides how their data is loaded: each of
their tables is matched to one of the file loads the application already has,
and what does not fit is listed as a gap before anything is promised. The
same items are questions 10.8 to 10.13 of the question list, so the Excel
answer sheet has a cell for each.

| Collect | Why |
| --- | --- |
| The software's name and version, and the kind of database behind it (SQL Server, MySQL, Access, Tally and so on) | Decides how the data can be taken out |
| The list of tables with their column names and types. A schema export or screenshots are enough | Each column is matched to a field here, or listed as having no home |
| 20 to 50 sample rows from each main table: products, customers, suppliers, stock, unpaid bills | Sample rows show what the column names do not: blanks, mixed codes, how dates and amounts are written |
| How they code units, tax rates and HSN, price lists, batches and expiry | These codes have to be translated, not copied |
| The number of rows in each table | Sizes the work and the time a load takes |
| The date they want to start on, and whether they want old transactions or only opening balances | Decides how much has to be brought across |

Two limits to keep in mind while asking:

- **Data is loaded from files (Excel or CSV), not read from their database.**
  Their tables have to be exported to files, by them or by whoever supports
  their present software.
- **What is loaded is masters and opening figures:** products, customers,
  suppliers, unpaid bills on both sides, opening stock and the opening trial
  balance. Old invoices, orders and payments are not loaded. Do not promise
  history in the meeting; the usual answer is opening balances, with the old
  software kept for looking things up.

Take sample rows only with the customer's agreement, and do not carry away a
full copy of their database.

---

## 5. The numbers to quote

Counted from the application on 2026-10-10. Do not round them up.

| What | Count |
| --- | ---: |
| Screens | more than 150 |
| Reports (54 on day-to-day trade, 48 on money and tax) | 102 |
| Ready-made roles (12 for a firm's staff) | 16 |
| Separate rights a role can be given or refused | 235 |
| Kinds of offer | 10 |
| Things an offer can depend on | 18 |
| Kinds of file loaded from Excel or another program | 8 |
| Ways to track a product | 4 |

Screens by area: Selling 33, Buying 20, Stock 18, Accounts 30, Masters 25,
Set-up 27, Reports and control 5.

The screen count is approximate (about 158 from the screen catalogue,
including screens only a platform administrator sees), which is why the
headline says "more than 150".

---

## 6. What was changed on 2026-10-10

| Document | Change |
| --- | --- |
| `docs/PROMOTIONS_AND_DISCOUNTS_GUIDE.md` | New sections 16 to 19: every kind of thing that changes a price, the price a line starts at, every field on every create screen, and one order worked start to finish. Sections 3, 4 and 15 corrected (ten benefits, not five; best-offer mode exists). |
| `docs/CUSTOMER_FEATURE_BROCHURE.md` | New "Prices and offers" block under Selling; new section 7 "Everything in it, counted"; "more than fifty reports" corrected to "more than a hundred". |
| The deck | 27 slides, was 23. Four new slides after the title: 2 "From installation to the first bill", 3 "A firm is created once and set up on one panel", 4 "A job decides what each person sees", 5 "What the firm does every day". Every later slide moved down four: "Prices and offers" is now slide 10 and "What you get, counted" slide 14. |
| `docs/CUSTOMER_REQUIREMENTS_QUESTIONS.md` | New. |
| `docs/CUSTOMER_DEMO_SCRIPT.md` | A pointer to the question list at the close. |
| This page | New section 4: what to collect about the customer's present software. |

## 7. Open points before a meeting

- **Section 19 of the promotions guide is worked by hand**, not run on a
  server. Drive that order on a fresh `selling-firm` fixture before quoting
  its figures to anybody.
- **The demo script lists two things missing from DEMO01:** the
  buy-10-get-1 offer with a Dealer price level (step 7) and the lapsed
  licence (step 6). DEMO01 was not checked on 2026-10-10; if they are still
  missing, those two steps cannot be shown as written.
- **The deck was checked as a PDF made by LibreOffice**, not opened in
  PowerPoint.
- **The previous deck, brochure PDF and demo script PDF were replaced** in
  `dist\customer`, and the old copies were deleted the same day. The deck's
  generator is `build.js` in `D:\ws\agencyApp\unattended\scratch\deck`.
- **Nothing of this is committed.**
