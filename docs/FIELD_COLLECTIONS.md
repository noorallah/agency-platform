# Field collections -- online, offline, and the daily sync

Design for a salesman or collector who visits shops, takes money against
outstanding bills, and records it where there may be no network. **Not built
yet.** It extends `docs/BACKLOG.md` §39 (field collections offline) and the
phone decision in §48 (orders and collections work offline). Offline sales
orders follow the same pattern later.

Written 2026-09-30 from a design discussion with the owner. The decisions at the
end are still open.

## The rule everything else follows

**The server is the only book.** A phone never holds a copy of the accounts,
never computes a real outstanding, and never posts anything. It holds
*intents* -- "I took ₹2,500 from shop X by cheque 004512" -- shaped exactly
like the `SettlementCreate` payload a receipt already takes
(`app/settlements/schemas/__init__.py`), and hands them to the server, which
records each one through `ReceiptService`. **No second write path for money**:
bulk and import endpoints are already documented in this repo as a second
implementation that drifts, and a field-sync path would be a third.

Every option below ends at the same server-side sync, so the rules for
numbering, duplicates, refusals and cash handover are the same however the data
arrives.

## Options, by how much network the firm allows

| # | Option | Network | Extra work | Reliability | When to choose |
|---|---|---|---|---|---|
| 1 | **Online app** -- phone screens in the existing Flutter app calling the APIs live | Server reachable from the field (fixed IP + certificate, or a hosted relay -- §48 open item 3) | Medium | High while in signal | Firm allows outside access and routes have signal |
| 2 | **Offline-first app, sync on office Wi-Fi** -- same app, saves on the phone, *Sync* calls the API at the server's LAN address | Office LAN only; nothing leaves the building | Medium | High | **Recommended default.** No domain, no internet |
| 3 | **Small standalone offline app + file exchange** -- no login, no server address; a *route pack* file in, a signed *collections* file out | None. File moves by USB, Bluetooth file share, Nearby Share or a shared folder | Medium | High | Firm allows no network access from phones at all |
| 4 | **QR code transfer** -- the phone shows the day's receipts as QR codes, the office PC scans them | None, no cable | Small-medium | High | Variant of 3 where cables and pairing are a problem |
| 5 | **Direct Bluetooth sync** -- a receiver on the office PC | Bluetooth | Large | Medium (pairing, drivers, drops) | Not recommended: brings nothing 2-4 don't |
| 6 | **Excel template import** -- collector fills a fixed sheet, office uploads it | None | Small | Medium (typing errors, no numbering control) | Stopgap before any app exists |
| -- | Full offline replica of the books on the phone, merged later | -- | Very large | Low | **Rejected.** Risks the accounts |

Options 2 and 3 are the same phone design with a different transport: 2 carries
the payloads over HTTP on the LAN (the client already accepts `http://` to a
local address -- §1), 3 carries them in a file. Building 3's file format first
makes 2 a thin wrapper over it.

**Separate app or a mode inside the existing app?** A separate small Flutter app
(e.g. `field_collect/`) is lighter, needs no login or server settings, and is
simpler for a collector; it makes the repo three applications where
`CLAUDE.md` describes two. A mode inside the existing app is one codebase but
carries every desktop screen and setting onto the phone. **Leaning: separate
small app for option 3; phone screens in the existing app for options 1-2.**

## The daily cycle

```
 MORNING                 DURING THE DAY             EVENING
 office → phone          phone only                 phone → office → phone
 ──────────────          ──────────────             ─────────────────────────
 Load route pack:        Collect at shops           1. Export / sync receipts
 · shops in visit order  Phone shows               2. Server records each one
 · outstanding + bills     morning outstanding     3. Server recalculates
 · receipt-number block    − collected today          outstanding
 · signing key             (provisional only)      4. Fresh pack + confirmation
                                                       back to the phone
                                                    5. Phone checks, then
                                                       REPLACES its data
```

- **Morning:** the route pack is built from the existing call lists
  (`GET /api/v1/call-lists`, `/beat-plans/{id}/call-list`) plus each
  customer's outstanding and open invoices. It is a snapshot and will be stale
  by afternoon; that is acceptable because the server re-decides at sync.
- **During the day:** the phone shows *morning outstanding minus what I
  collected today* as a working figure for the collector. It is never sent and
  never trusted.
- **Evening:** one office action -- *Import field collections* -- records the
  receipts **and** returns the next pack, so the evening sync also prepares the
  next morning. A separate morning sync is then needed only if something
  changed overnight.
- **Replace, never merge.** The phone throws its route data away and loads the
  server's. Errors cannot accumulate from day to day because nothing on the
  phone survives the refresh except receipts the server has not confirmed.

## What the phone stores

SQLite on the phone (`drift` or `sqflite`; the location from `AppStorage`),
not a JSON file -- a half-written file can lose a day.

- **Route pack** (read-only): customers, contact, outstanding, open invoices,
  the number block, the signing key, the pack's date and sequence number.
- **Collection queue**, one row per receipt:

| Field | Example | Note |
|---|---|---|
| `settlement_number` | `FC-07-0142`, or the paper receipt-book number | **The idempotency key** (below) |
| `party_id` / `party_code` | customer | Existing field |
| `settlement_date` | 2026-10-03 | The day collected, not the day synced |
| `amount`, `method`, `instrument_reference` | 2,500 · CHEQUE · 004512 | Existing fields |
| `narration` | "Collected by Ravi, route R3" | Existing field |
| `allocations` | empty (on account) or named bills | Open decision 1 |
| `status` | SAVED → SENT → ACCEPTED / REFUSED / VOID | Phone only |
| `server_reply` | receipt id, or the refusal reason | Phone only |
| `collected_at`, `prev_hash`, optional GPS | | Evidence and the hash chain |

A saved receipt is never edited on the phone. A mistake is marked **VOID** with
a reason and still sent; a correction after acceptance is a reversal in the
office, like any settlement (`docs/LEDGER_POSTING_RULES.md`).

## Numbering and duplicates

- **The phone assigns the number, from a block issued to it** (e.g.
  `FC-07-0101..0200`), or uses the physical receipt-book number handed to the
  customer. `UQ_settlements_firm_number` already makes `settlement_number`
  unique per firm, and the field is optional on create, so a device-assigned
  number **is** the idempotency key. `manual_allowed` on the numbering rule
  exists for this case.
- **A replay is not a clash.** A second arrival of the same number with the
  same party and amount answers *already recorded* with the original receipt;
  the same number with different content is refused as a conflict. Today a
  repeated number is simply refused, so the sync endpoint must make this
  distinction.
- **Numbers are consumed in order and never skipped.** A spoiled receipt is a
  VOID, which is what lets both sides detect a gap.

## Integrity checks -- nothing may go missing silently

| Check | Detects | Where |
|---|---|---|
| **No gaps in receipt numbers** within the block | A receipt lost on the phone or in transit | Server on import; daily report |
| **Export files numbered per device** (#17, #18, #19) | A whole file never delivered; the same file imported twice | Server, before accepting anything |
| **Header totals** -- count, first/last number, total per method | A truncated or damaged file | Server recounts; refuses the file whole |
| **Signature** (HMAC-SHA256, key issued in the route pack, copy kept by the server) | An amount edited between phone and office | Server |
| **Hash chain** -- each receipt carries a hash of the previous one | A row deleted or inserted in the middle | Server |
| **Pack confirmation** -- accepted numbers, refused numbers with reasons, last export received, accepted total | A receipt the server never got | **Phone, before it replaces anything** |
| **Pack identity** -- for this device, newer than the current pack, signed | Loading another phone's pack or yesterday's | Phone |

**The phone clears a receipt only when the server has confirmed it.** If any
receipt on the phone is neither accepted nor refused, or the accepted total
disagrees with the phone's, the refresh is blocked and the collector is told
what to re-send. Nothing is lost by a failed sync; the old data simply stays.

## The export file (option 3; the same payload is the sync body in option 2)

```json
{
  "format": "agency-field-collections/1",
  "firm_code": "WHOLE01",
  "collector": "ravi",
  "device_id": "PH-07",
  "export_seq": 19,
  "pack_seq": 42,
  "block": "FC-07-0101..0200",
  "exported_at": "2026-10-03T18:40:00+05:30",
  "header": {"count": 24, "first": "FC-07-0141", "last": "FC-07-0164",
             "totals": {"CASH": "15950.00", "CHEQUE": "2500.00", "UPI": "0.00"}},
  "receipts": [
    {"settlement_number": "FC-07-0142", "party_code": "CUST-0231",
     "settlement_date": "2026-10-03", "amount": "2500.00",
     "method": "CHEQUE", "instrument_reference": "004512",
     "status": "SAVED", "collected_at": "2026-10-03T11:20:00+05:30",
     "prev_hash": "..."}
  ],
  "signature": "HMAC-SHA256 over everything above"
}
```

## Server side -- new pieces

| Piece | Purpose |
|---|---|
| `GET /api/v1/field/route-pack` | Build the pack for one collector: call list, outstanding, open bills, block, key, confirmation of the last import |
| `POST /api/v1/field/number-blocks` | Issue a block to a device and record who holds it; close a block (lost phone) |
| `POST /api/v1/field/receipts/sync` | Verify signature, sequence and totals; then each receipt **in its own transaction** through `ReceiptService`; answer **per receipt** (accepted / already recorded / refused + reason) plus the next pack |
| Cash handover (`GET` summary, `POST` confirm) | Total collected per collector and day by method; the cashier confirms or records a shortage |
| Daily reconciliation report | Per collector: block issued, used, void, received, missing, cash handed over, difference |
| Desktop: *Export route pack*, *Import field collections* | The office end of option 3, calling the same endpoints |

- One refused receipt never rolls back the others (§39).
- Allocations are resolved against the outstanding **at sync**, not the
  morning snapshot -- the office may have banked a cheque against the same bill.
- Permission codes -- e.g. `FIELD_COLLECTION_SYNC`, `CASH_HANDOVER_CONFIRM`
  -- must be added to `PERMISSION_GROUPS` in `app/identity/system_seed.py` with
  a migration, or the endpoints silently become platform-admin-only
  (`CLAUDE.md`, Authorization). **The collector must not confirm his own
  handover** -- the same separation as `COMMISSION_PAY` and
  `COMMISSION_MANAGE`.

## Security

- Options 1-2: the refresh token lasts 7 days in the OS credential vault, so
  signing in at the office covers the day; add an app PIN.
- Option 3: no credentials on the phone at all -- only the per-device signing
  key, which the office can revoke with the block.
- Lost phone: close its block and revoke its key/token from the office; any
  later file from it is refused.
- Plain HTTP on the office LAN is the firm's choice (§1): anything on that
  network can read the traffic. The signature still stops tampering.

## Things that will bite (from §39)

- **Closed period:** collected on the 31st, synced on the 2nd after the period
  closed.
- **Cash in hand is invisible** between collection and sync -- the handover
  step is what makes it auditable, and is arguably larger than the sync.
- **A real phone layout** is the cost: today's APK is the desktop layout
  (`desktop/build_android.ps1`).
- **Photos and signatures** need file storage, which does not exist yet
  (`backend/storage/` holds nothing). Later phase.

## Order of work

1. Server: number blocks, the sync endpoint with every integrity check, tested
   with a script -- no app yet.
2. Server: route pack with confirmation; cash handover; reconciliation report.
3. Desktop: *Export route pack* / *Import field collections* (option 3's office
   end).
4. Phone: Collect, My collections, Export / Sync; then Start my day and Today's
   shops.
5. Pilot one collector for a week on option 2 or 3.
6. Offline sales orders on the same pattern (§48), with its own conflict rules
   (stock gone, price changed).

## Open decisions

1. **Collect on account, or allocate to bills on the phone?** Leaning: on
   account -- the office applies it -- which removes the staleness problem.
2. **Paper receipt-book numbers, or blocks issued to the phone?** The book is
   better evidence; blocks suit printing from the phone later.
3. **Which option first:** 2 (office Wi-Fi) or 3 (file, no network)?
4. **Separate small app or a mode in the existing app?**
5. **Late sync across a closed period:** hold the period open, or post into the
   open period keeping the true collection date?
6. **A refused receipt with cash already taken:** who is told, and does it stay
   in the collector's cash in hand until resolved?
7. **Android only, or iPhone too** (§48).
