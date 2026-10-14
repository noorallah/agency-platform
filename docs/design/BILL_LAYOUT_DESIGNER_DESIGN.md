# A bill a firm arranges itself: design note

**Status: design note for the open half of backlog 143 (PRT-5), written
2026-10-14. Nothing in it is built.** The owner asked on 2026-10-14 whether a
firm could "change the layout by moving fields", after the choice of two fixed
layouts (Standard and Trade, #1516) was built. This note says how, so he can
read it before anything is built. What it decided in his absence is listed in
section 9 for him to confirm.

## 1. What it does for the user

*Print settings* gains **Arrange the bill**. It opens the bill as a page: the
blocks down the page (the firm, the buyer, the bill's particulars, the lines,
the summary by HSN, the totals, the amount in words, the terms, the
signature) and, in the lines, the columns across. A person:

- drags a block up or down, or puts two side by side (the firm on the left,
  the buyer on the right, as the trade's bill does);
- switches a block or a column off, where the law lets it be off (section 4);
- drags a column left or right, and drags its edge to make it wider;
- renames a heading (*P.T.R.* for *Rate*, *Net Value* for *Amount*);
- says how many lines a page holds, and how a long name is printed;
- sees the sample bill change as each choice is made (the Preview built in
  #1516), and saves it under a name.

A firm starts from **Standard** or **Trade**, which stay as they are and are
never changed by anyone. What it arranges is a copy, its own, with a name it
gives (*Our bill*, *Bill for medical shops*). It may keep several and choose
which one its bills print in, as it chooses Standard or Trade today; a
customer's own *Bill paper* can name one too.

## 2. What is there today

Read on 2026-10-14 at main `5810b896`.

- **Four renderers, each a fixed arrangement in code**: the standard full
  page (`InvoicePdfRenderer`, `app/sales_invoice/services/invoice_pdf.py`), the
  trade's boxed bill (`TradeInvoiceRenderer`, `trade_invoice_pdf.py`, built on
  the first), the half page (`half_page_pdf.py`) and the 80 mm roll
  (`thermal_pdf.py`). Each draws the same `InvoiceDocument`, which holds every
  figure already resolved from the record.
- **What a firm may change** is `document_print_templates` (one row per firm
  per document type): words around the bill, the bank block, copies, paper,
  margin, three column switches, and since #1516 `bill_layout`, STANDARD or
  TRADE.
- **Preview** (`POST /api/v1/document-framework/print-templates/{type}/preview`)
  draws a sample bill from settings that need not be saved.
- **Nothing says how many lines a page holds**; a long name wraps in its
  cell.

## 3. The model: a layout is rows, not a picture

A layout is stored as rows in three tables, firm-owned, in each firm's store:

- **`bill_layouts`**: `id`, `firm_id`, `name`, `document_type` (SALES_INVOICE
  first), `paper` (A4, A5), `lines_per_page` (null: as many as fit),
  `long_names` (WRAP or SHRINK), `based_on` (STANDARD or TRADE), and the usual
  `BaseEntity` columns. A unique name per firm among live rows.
- **`bill_layout_blocks`**: `layout_id`, `block` (a code from the catalogue,
  section 5), `row`, `column` (0 or 1: alone on its row, or one of two side by
  side), `visible`, `heading` (the firm's own words, null for the
  catalogue's).
- **`bill_layout_columns`**: `layout_id`, `column` (a code from the catalogue),
  `position`, `width` (a share of the line, the description taking what is
  left), `visible`, `heading`.

Rows rather than one JSON document, because the repository stores
configuration in typed columns (`docs/CUSTOM_FIELDS_FRAMEWORK.md`): a layout
can then be validated column by column, listed, audited field by field like
every other setting (`record_change`), and a catalogue code that is renamed is
found by a query rather than by reading every document.

`document_print_templates.bill_layout` widens from STANDARD or TRADE to also
name a firm's own layout (`bill_layout_id`, null for the two presets).

## 4. What can never be moved out

The rule `document_print_templates` already follows (its docstring): the
statutory spine of a tax invoice is not configurable. A layout may move it,
rename around it and set its width, but never switch it off:

- the title (*Tax Invoice* or *Bill of Supply*), the firm's name, GSTIN and
  address, the buyer's name and GSTIN, the bill's number and date, the place
  of supply;
- in the lines, the description, the HSN, the quantity, the taxable value and
  the GST rate;
- each GST head's amount (in the lines or in the totals), the summary by HSN,
  the total and the amount in words;
- the e-invoice block where the bill is registered.

The catalogue marks these `required`; the save refuses a layout that hides
one, by name, and the designer draws their switch locked with a line saying
why.

## 5. The catalogue: what can be placed

One list in code (`app/sales_invoice/services/layout_catalogue.py`), of
**blocks** and of **columns**, each with its code, the heading it prints, what
it reads from `InvoiceDocument`, its alignment, its narrowest width, whether
it is required, and which papers can hold it.

- **Blocks**: seller, buyer, ship to, particulars (number, date, due date,
  references, Order By, Market), e-invoice, lines, total quantity, HSN summary,
  GST by rate, totals, amount in words, bank, UPI, terms, declaration,
  signature, footer note.
- **Columns**: serial, description, HSN, quantity, free, unit, MRP, rate with
  GST (D.Price), rate (P.T.R.), discount, GST rate, each GST head's rate and
  amount, taxable value, amount (Net Value), batch, made, expiry.

A new figure that a bill should be able to show joins the catalogue once and
is then available to every layout, which is the reason for having one.

## 6. One engine draws them all

A new renderer, `ArrangedInvoiceRenderer`, draws any layout: the blocks in
their rows, each by the block's own drawing function, the lines with the
columns in order at their widths. Standard and Trade become two layouts
**defined in code** (not rows), drawn by the same engine.

The order of the build protects what prints today: the engine is first made
to draw the Standard and Trade presets, and the tests that pin today's two
renderers (`test_invoice_print.py`, `test_trade_bill_layout.py`) must pass on
the engine's output **unchanged** before the old renderers are removed (the
clean-up rule). The half page and the roll keep their own renderers until a
later step; they are narrow forms with fewer choices.

**Lines per page.** Where a layout sets it, the lines table breaks after that
many lines; each page repeats the headings and the blocks marked *every page*
(the firm and the buyer), and the totals print once, on the last page, with
*Continued* at the foot of the others.

**Long names.** WRAP (today) lets a name take two lines in its cell; SHRINK
sets it smaller to keep one line, never below a size that still reads
(6.5 pt), and wraps after that.

## 7. The screen

*Print settings* (sales invoice) gets **Arrange the bill**, opening a window
in three parts:

- **left**: the blocks, a list to drag, each with its switch and its heading;
- **middle**: the columns of the lines, a list to drag, each with its switch,
  heading and a width slider;
- **right**: the sample bill, drawn again a moment after each change (one
  call to the existing Preview, which takes the layout in its body), so the
  screen never guesses what the server will print.

**Save as** names it. The layouts a firm has are listed in *Print settings*
beside Standard and Trade, with **Copy**, **Rename** and **Delete** (a layout a
bill or a customer is set to cannot be deleted; the refusal says which).

Calls (the rule of fewer server calls): one read of the firm's layouts when
*Print settings* opens; one preview per change, debounced; one write on save.

## 8. The steps of the build

Each a run of its own, merged on its own:

1. **Tables, catalogue and API.** The three tables (migration), the catalogue,
   `GET/POST/PUT/DELETE /api/v1/bill-layouts`, the save's checks (section 4),
   the audit. The preview accepts a layout.
2. **The engine.** `ArrangedInvoiceRenderer` draws a layout; Standard and
   Trade are redefined as two presets it draws; the tests of today's two
   renderers pass on it unchanged; the two old renderers are then removed.
3. **The screen.** *Arrange the bill*, with the live sample.
4. **Lines per page and long names.** The page break with *Continued*, and
   SHRINK.
5. **Where a layout is chosen.** A firm's own layout chosen in *Print
   settings* and on a customer's *Bill paper*; print, print together and the
   email attachment all read it.
6. **Later, by need:** the delivery note, the order and the credit note
   (`document_type`), and the half page.

Size: steps 1 and 2 are the large ones (the engine must reproduce two
layouts exactly); 3 is one window; 4 and 5 are small. About five runs.

## 9. Decided here, for the owner to confirm

1. **Presets are never edited.** A firm arranges a copy; Standard and Trade
   stay as they are, so a firm can always go back to a bill that is known to
   be right.
2. **A layout is stored as rows, not as one JSON document** (section 3), as
   every other setting is.
3. **The statutory parts can be moved but never hidden** (section 4).
4. **Two blocks side by side at most.** The trade's bill needs two; three
   across an A4 page cannot hold an address.
5. **Sales invoice first**, A4 and A5; other documents and the half page
   later (step 6).
6. **Long names: WRAP or SHRINK**, never cut off: a name printed short is a
   different product.
7. **No fonts or colours per block.** The accent colour stays one setting for
   the whole bill; a firm that wants its own look chooses it there.
8. **No logo position yet.** The bill prints no logo today; placing one is a
   block for the catalogue when the owner wants it.
