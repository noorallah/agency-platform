# Customer meeting guide

Which document to use at each point of a customer meeting, and what each one
holds. Written 2026-10-10. This page is for the person giving the meeting,
not for the customer.

The PDFs and the deck are in `dist\customer` (not in git). Their sources are
in `docs\`.

---

## 1. Which document, when

| When | Document | Use |
| --- | --- | --- |
| Before the meeting | `CUSTOMER_REQUIREMENTS_QUESTIONS.pdf`, section 1 | Ask by phone or at the start |
| In the meeting | `Jugnix_Trade_Features_and_Demo.pptx` | Present it: 10 slides on the product, then the demonstration, then "not included" and next steps |
| In the meeting | The live demonstration on DEMO01 | The 30-minute story |
| After the demonstration | `CUSTOMER_REQUIREMENTS_QUESTIONS.pdf`, sections 2 to 11 | Fill in with the customer |
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

`docs/CUSTOMER_REQUIREMENTS_QUESTIONS.md` -- about 70 questions in ten
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
  payment, and consignment stock. Do not say yes to these in the meeting.
- **Section 11 is a blank table** for "what do you do today that you did not
  see?", to bring back.

The "check" marks on interest on late payment, consignment stock and remote
access are a caution: nobody confirmed on 2026-10-10 whether the application
covers them. Confirm before the meeting if the customer is likely to ask.

---

## 4. The numbers to quote

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

## 5. What was changed on 2026-10-10

| Document | Change |
| --- | --- |
| `docs/PROMOTIONS_AND_DISCOUNTS_GUIDE.md` | New sections 16 to 19: every kind of thing that changes a price, the price a line starts at, every field on every create screen, and one order worked start to finish. Sections 3, 4 and 15 corrected (ten benefits, not five; best-offer mode exists). |
| `docs/CUSTOMER_FEATURE_BROCHURE.md` | New "Prices and offers" block under Selling; new section 7 "Everything in it, counted"; "more than fifty reports" corrected to "more than a hundred". |
| The deck | 23 slides, was 21. New slide 6 "Prices and offers follow rules you set once"; new slide 10 "What you get, counted from the application"; slide 9 reports figure corrected to 102. |
| `docs/CUSTOMER_REQUIREMENTS_QUESTIONS.md` | New. |
| `docs/CUSTOMER_DEMO_SCRIPT.md` | A pointer to the question list at the close. |

## 6. Open points before a meeting

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
