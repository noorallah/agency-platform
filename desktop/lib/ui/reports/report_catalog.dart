import '../../models/report.dart';

/// Every report the server can produce, as data.
///
/// Thirty-four report endpoints existed across seven modules and no screen
/// called any of them: registers, pending and overdue lists, reconciliations,
/// outstanding balances, and breakdowns by customer, salesman, territory,
/// route, warehouse, vendor and product. All of the work was already done on
/// the server; what was missing was somewhere to read it.
///
/// Six more were found the same way on 2026-09-04 -- the sales return's four
/// and the quotation's two, written after this list was and never added to
/// it. `tests/unit/test_reports_have_a_screen.py` now fails the build on a
/// `/reports/` route with no entry here, because the orphan-route guard
/// cannot see this class: it matches a served path against the *shapes* the
/// desktop builds, and `/sales-returns/reports/register` has the same shape
/// as `/sales-orders/reports/register`, which is listed.
///
/// Adding a report here is one entry. The grid derives its own columns from the
/// rows, so a report only names columns when the derived set reads badly.
const List<ReportDefinition> reportCatalog = [
  // ---- Sales ---------------------------------------------------------
  ReportDefinition(
    id: 'quotation-register',
    label: 'Quotation register',
    description: 'Every offer made, and what it was worth.',
    path: '/api/v1/quotations/reports/register',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'quotation-conversion',
    label: 'Quotation conversion',
    description: 'How many offers became orders, and how many lapsed.',
    path: '/api/v1/quotations/reports/conversion',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'enquiries-lost',
    label: 'Enquiries lost',
    description: 'Why enquiries were lost, and what they were worth.',
    path: '/api/v1/enquiries/reports/lost',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-register',
    label: 'Sales order register',
    description: 'Every order raised, with what it was worth.',
    path: '/api/v1/sales-orders/reports/register',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-pending',
    label: 'Orders not yet delivered',
    description: 'Orders with stock still owed to the customer.',
    path: '/api/v1/sales-orders/reports/pending',
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-back-orders',
    label: 'Back orders',
    description: 'Orders the warehouse could not fill in full.',
    path: '/api/v1/sales-orders/reports/back-orders',
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-customer',
    label: 'Orders by customer',
    description: 'Who is ordering, and how much of it.',
    path: '/api/v1/sales-orders/reports/by-customer',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-salesman',
    label: 'Orders by salesman',
    description: 'What each salesman has brought in.',
    path: '/api/v1/sales-orders/reports/by-salesman',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-territory',
    label: 'Orders by territory',
    description: 'Order value and count per territory, cancellations excluded.',
    path: '/api/v1/sales-orders/reports/by-territory',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  // What was given away (67 row 8), on billed sales: typed against what a
  // price list or a customer's standing rate applied, and what offers gave.
  ReportDefinition(
    id: 'discount-by-customer',
    label: 'Discount given by customer',
    description: 'Discount on bills in the dates, per customer: what was '
        'typed, what an arrangement or an offer applied, and the bill '
        'discount.',
    path: '/api/v1/sales-invoices/reports/discount-by-customer',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
    columns: _discountColumns,
  ),
  ReportDefinition(
    id: 'discount-by-salesman',
    label: 'Discount given by salesman',
    description: 'Discount on bills in the dates, per salesman: what was '
        'typed, what an arrangement or an offer applied, and the bill '
        'discount.',
    path: '/api/v1/sales-invoices/reports/discount-by-salesman',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
    columns: _discountColumns,
  ),
  ReportDefinition(
    id: 'discount-by-product',
    label: 'Discount given by product',
    description: 'Discount on bills in the dates, per product: what was '
        'typed, what an arrangement or an offer applied, and the bill '
        'discount.',
    path: '/api/v1/sales-invoices/reports/discount-by-product',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
    columns: _discountColumns,
  ),
  ReportDefinition(
    id: 'discount-by-promotion',
    label: 'Discount given by offer',
    description: 'What each offer was claimed for in the dates: claims, '
        'customers and the benefit given, costliest first.',
    path: '/api/v1/sales-invoices/reports/discount-by-promotion',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'code', label: 'Code'),
      ReportColumn(key: 'name', label: 'Offer'),
      ReportColumn(key: 'claims', label: 'Claims', numeric: true),
      ReportColumn(key: 'customers', label: 'Customers', numeric: true),
      ReportColumn(key: 'benefit_amount', label: 'Given', numeric: true),
    ],
  ),
  // The Targets screen's Achievement view, listed here too so it is found
  // beside the other by-salesman reports (BL-31.15). Its route checks only
  // SALES_TARGET_VIEW, not REPORT_VIEW.
  ReportDefinition(
    id: 'sales-target-achievement',
    label: 'Targets achieved',
    description: 'Each target overlapping the dates, against what it took -- '
        'measured over its own period and on its own basis.',
    path: '/api/v1/sales-targets/achievement',
    permission: 'SALES_TARGET_VIEW',
    area: ReportArea.operational,
    needsPeriod: true,
    openToReportView: false,
  ),

  // ---- Dispatch ------------------------------------------------------
  ReportDefinition(
    id: 'delivery-note-register',
    label: 'Delivery note register',
    description: 'Every dispatch, and the order it came from.',
    path: '/api/v1/delivery-notes/reports/register',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-pending',
    label: 'Dispatches not yet completed',
    description: 'Notes raised but not sent out.',
    path: '/api/v1/delivery-notes/reports/pending',
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
    // A flat register row since D-RPT-16; named so the order comes first.
    columns: [
      ReportColumn(key: 'delivery_note_number', label: 'Delivery note number'),
      ReportColumn(key: 'delivery_date', label: 'Delivery date'),
      ReportColumn(key: 'sales_order_number', label: 'Sales order'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'delivery-note-partial',
    // Named for what the endpoint answers: one row per live sales order with
    // ordered, delivered and pending quantities and COMPLETED, PARTIAL or
    // PENDING. It was called "Part-dispatched notes", which promised notes and
    // only the partial ones, and listed 65 orders -- most of them complete
    // (manual plan item 13.6, 2026-09-14).
    label: 'Delivery progress by order',
    description: 'Every live sales order: ordered, delivered, still to go.',
    path: '/api/v1/delivery-notes/reports/partial',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-route',
    label: 'Dispatches by route',
    description: 'What went out on each route.',
    path: '/api/v1/delivery-notes/reports/by-route',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-salesman',
    label: 'Dispatches by salesman',
    description: 'Delivered value and count per salesman.',
    path: '/api/v1/delivery-notes/reports/by-salesman',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-warehouse',
    label: 'Dispatches by warehouse',
    description: 'Delivered value and count per warehouse.',
    path: '/api/v1/delivery-notes/reports/by-warehouse',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),

  // ---- Promotions ----------------------------------------------------
  ReportDefinition(
    id: 'promotion-performance',
    label: 'Promotion performance',
    description: 'What each offer was claimed, and what it cost the firm.',
    path: '/api/v1/promotions/reports/performance',
    permission: 'PROMOTION_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'code', label: 'Code'),
      ReportColumn(key: 'name', label: 'Name'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(key: 'claimed_count', label: 'Claimed', numeric: true),
      ReportColumn(key: 'pending_count', label: 'Pending', numeric: true),
      ReportColumn(key: 'reversed_count', label: 'Reversed', numeric: true),
      ReportColumn(key: 'customer_count', label: 'Customers', numeric: true),
      ReportColumn(key: 'benefit_amount', label: 'Benefit', numeric: true),
      ReportColumn(key: 'free_quantity', label: 'Free units', numeric: true),
      ReportColumn(key: 'max_redemptions', label: 'Limit', numeric: true),
      ReportColumn(key: 'remaining_redemptions', label: 'Left', numeric: true),
      ReportColumn(
          key: 'max_benefit_amount', label: 'Budget (value)', numeric: true),
      ReportColumn(
          key: 'remaining_benefit_amount', label: 'Value left', numeric: true),
      ReportColumn(
          key: 'max_free_quantity', label: 'Budget (free)', numeric: true),
      ReportColumn(
          key: 'remaining_free_quantity', label: 'Free left', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'promotion-redemptions',
    label: 'Promotion claims',
    description: 'Every claim on an offer, and the document that took it.',
    path: '/api/v1/promotions/reports/redemptions',
    needsPeriod: true,
    permission: 'PROMOTION_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'promotion_code', label: 'Offer code'),
      ReportColumn(key: 'promotion_name', label: 'Offer'),
      ReportColumn(key: 'coupon_code', label: 'Coupon'),
      ReportColumn(key: 'customer_name', label: 'Customer'),
      ReportColumn(key: 'document_type', label: 'Document'),
      ReportColumn(key: 'document_number', label: 'Number'),
      ReportColumn(key: 'redeemed_on', label: 'On'),
      ReportColumn(key: 'benefit_amount', label: 'Benefit', numeric: true),
      ReportColumn(key: 'free_quantity', label: 'Free units', numeric: true),
      ReportColumn(key: 'status', label: 'Status'),
    ],
  ),
  ReportDefinition(
    id: 'promotion-coupons',
    label: 'Coupon performance',
    description: 'Which codes people actually presented, and what they cost.',
    path: '/api/v1/promotions/reports/coupons',
    permission: 'PROMOTION_VIEW',
    area: ReportArea.operational,
  ),

  // ---- Purchase ------------------------------------------------------
  ReportDefinition(
    id: 'purchase-order-register',
    label: 'Purchase order register',
    description: 'Every order raised on a supplier, and what it was worth.',
    path: '/api/v1/purchases/reports/register',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-order-pending',
    label: 'Orders not yet received',
    description: 'Orders with goods still owed by the supplier.',
    path: '/api/v1/purchases/reports/pending',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-order-overdue',
    label: 'Overdue purchase orders',
    description: 'Orders whose goods were expected and have not arrived.',
    path: '/api/v1/purchases/reports/overdue',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-order-by-vendor',
    label: 'Orders by supplier',
    description: 'Where the firm places its business, by value.',
    path: '/api/v1/purchases/reports/by-vendor',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  // BUY-12: how each supplier has kept its side, from the receipts.
  ReportDefinition(
    id: 'supplier-performance',
    label: 'Supplier performance',
    description: 'Per supplier in the dates: receipts on time, and the share '
        'rejected, returned and short against what was ordered.',
    path: '/api/v1/purchases/reports/supplier-performance',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'receipts', label: 'Receipts', numeric: true),
      ReportColumn(key: 'on_time_percent', label: 'On time %', numeric: true),
      ReportColumn(
          key: 'rejected_percent', label: 'Rejected %', numeric: true),
      ReportColumn(
          key: 'returned_percent', label: 'Returned %', numeric: true),
      ReportColumn(key: 'short_percent', label: 'Short %', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'supplier-price-trend',
    label: 'Supplier price trend',
    description: 'What one supplier has charged month by month, from the '
        'receipts: quantity and average rate.',
    path: '/api/v1/purchases/reports/supplier-price-trend',
    needsPeriod: true,
    needsSupplier: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'month', label: 'Month'),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'average_rate', label: 'Average rate', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'purchase-order-by-buyer',
    label: 'Orders by buyer',
    description: 'What each buyer has committed the firm to.',
    path: '/api/v1/purchases/reports/by-buyer',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-order-by-product',
    label: 'Purchases by product',
    description: 'What the firm is buying, by quantity and by value.',
    path: '/api/v1/purchases/reports/by-product',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'goods-receipt-pending',
    label: 'Receipts awaiting completion',
    description: 'Goods booked in but not yet put into stock.',
    path: '/api/v1/goods-receipts/reports/pending',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'grn_number', label: 'Grn number'),
      ReportColumn(key: 'receipt_date', label: 'Receipt date'),
      ReportColumn(
          key: 'purchase_order_number', label: 'Purchase order number'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(
          key: 'total_accepted_quantity',
          label: 'Total accepted quantity',
          numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'goods-receipt-partial',
    label: 'Orders part received',
    description: 'Purchase orders the supplier has only part filled.',
    path: '/api/v1/goods-receipts/reports/partial',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'goods-receipt-completed',
    label: 'Receipts completed',
    description: 'Goods received in full and taken into stock.',
    path: '/api/v1/goods-receipts/reports/completed',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'grn_number', label: 'Grn number'),
      ReportColumn(key: 'receipt_date', label: 'Receipt date'),
      ReportColumn(
          key: 'purchase_order_number', label: 'Purchase order number'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(
          key: 'total_accepted_quantity',
          label: 'Total accepted quantity',
          numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'goods-receipt-damaged',
    label: 'Damaged on receipt',
    description: 'Lines recorded as damaged when the goods arrived.',
    path: '/api/v1/goods-receipts/reports/damaged',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'line_number', label: 'Line number', numeric: true),
      // Beside the line, because the row carried only `product_id` and the
      // screen showed a UUID where the product belongs (D-RPT-17).
      ReportColumn(key: 'product_code', label: 'Product code'),
      ReportColumn(key: 'product_name', label: 'Product'),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(
          key: 'ordered_quantity', label: 'Ordered quantity', numeric: true),
      ReportColumn(
          key: 'current_receipt_quantity',
          label: 'Current receipt quantity',
          numeric: true),
      ReportColumn(
          key: 'damaged_quantity', label: 'Damaged quantity', numeric: true),
      ReportColumn(key: 'warehouse_name', label: 'Warehouse'),
      ReportColumn(key: 'batch_number', label: 'Batch number'),
    ],
  ),
  ReportDefinition(
    id: 'goods-receipt-rejected',
    label: 'Rejected on receipt',
    description: 'Lines refused at the door and not taken into stock.',
    path: '/api/v1/goods-receipts/reports/rejected',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'line_number', label: 'Line number', numeric: true),
      // Beside the line, because the row carried only `product_id` and the
      // screen showed a UUID where the product belongs (D-RPT-17).
      ReportColumn(key: 'product_code', label: 'Product code'),
      ReportColumn(key: 'product_name', label: 'Product'),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(
          key: 'ordered_quantity', label: 'Ordered quantity', numeric: true),
      ReportColumn(
          key: 'current_receipt_quantity',
          label: 'Current receipt quantity',
          numeric: true),
      ReportColumn(
          key: 'rejected_quantity', label: 'Rejected quantity', numeric: true),
      ReportColumn(key: 'warehouse_name', label: 'Warehouse'),
      ReportColumn(key: 'batch_number', label: 'Batch number'),
    ],
  ),
  ReportDefinition(
    id: 'purchase-return-register',
    label: 'Purchase return register',
    description: 'Everything sent back to a supplier.',
    path: '/api/v1/purchase-returns/reports/register',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-reconciliation',
    label: 'Purchase return reconciliation',
    description: 'Return lines against the receipts they came from.',
    path: '/api/v1/purchase-returns/reports/reconciliation',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-damaged',
    label: 'Damaged goods returned',
    description: 'Lines returned because the goods were damaged.',
    path: '/api/v1/purchase-returns/reports/damaged',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-expired',
    label: 'Expired stock returned',
    description: 'Lines returned because the stock was past its date.',
    path: '/api/v1/purchase-returns/reports/expired',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-by-product',
    label: 'Purchase returns by product',
    description: 'Quantity and value returned per product.',
    path: '/api/v1/purchase-returns/reports/by-product',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
  ),

  // ---- Financial -----------------------------------------------------
  ReportDefinition(
    id: 'sales-invoice-register',
    label: 'Sales invoice register',
    description: 'Every invoice raised, with its status.',
    path: '/api/v1/sales-invoices/reports/register',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
  ),
  // A period's outward supplies by tax head, outside the GSTR-1 screen, as
  // a CA asks for them (87 row 1). Every figure is GSTR-1's own.
  ReportDefinition(
    id: 'gst-sales-register',
    label: 'GST sales register',
    description: 'Approved invoices by tax head: GSTIN, place of supply, '
        'taxable value, IGST, CGST, SGST and cess. Credit notes, sales '
        'returns and late cancellations are rows of their own, in minus, '
        'and customer debit notes in plus, each on its own date.',
    path: '/api/v1/sales-invoices/reports/gst-register',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'document_date', label: 'Date'),
      ReportColumn(key: 'document_type_label', label: 'Type'),
      ReportColumn(key: 'document_number', label: 'Number'),
      ReportColumn(key: 'against_invoice_number', label: 'Against invoice'),
      ReportColumn(key: 'customer_name', label: 'Customer'),
      ReportColumn(key: 'customer_gstin', label: 'GSTIN'),
      ReportColumn(key: 'place_of_supply', label: 'Place of supply'),
      ReportColumn(key: 'taxable_value', label: 'Taxable', numeric: true),
      ReportColumn(key: 'igst', label: 'IGST', numeric: true),
      ReportColumn(key: 'cgst', label: 'CGST', numeric: true),
      ReportColumn(key: 'sgst', label: 'SGST', numeric: true),
      ReportColumn(key: 'cess', label: 'Cess', numeric: true),
      ReportColumn(key: 'total_tax', label: 'Total tax', numeric: true),
      ReportColumn(key: 'document_total', label: 'Total', numeric: true),
    ],
  ),
  // What each customer's turnover rebate has earned, what is booked and what
  // is still to set against their account (87 row 9). An agreement is on the
  // report when its period touches the dates asked for.
  ReportDefinition(
    id: 'customer-rebate-statement',
    label: 'Customer rebate statement',
    description: 'Turnover rebates promised to customers and customer '
        'groups: the turnover counted, the slab reached, what is accrued, '
        'what is settled against the account and the balance. Withdrawn '
        'agreements are left out.',
    path: '/api/v1/customer-rebates/reports/statement',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'code', label: 'Agreement'),
      ReportColumn(key: 'name', label: 'Name'),
      ReportColumn(key: 'party_name', label: 'Customer or group'),
      ReportColumn(key: 'period_from', label: 'From'),
      ReportColumn(key: 'period_to', label: 'To'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(key: 'agreed_label', label: 'Agreed'),
      ReportColumn(key: 'turnover', label: 'Turnover', numeric: true),
      ReportColumn(key: 'rate_percent', label: 'Rate %', numeric: true),
      ReportColumn(key: 'earned', label: 'Earned', numeric: true),
      ReportColumn(key: 'accrued', label: 'Accrued', numeric: true),
      ReportColumn(key: 'settled', label: 'Settled', numeric: true),
      ReportColumn(key: 'balance', label: 'Balance', numeric: true),
    ],
  ),
  // The same supplies folded by HSN code and rate, net of credits: GSTR-1's
  // Table 12 for any period. A product with no HSN shows under a blank code.
  ReportDefinition(
    id: 'hsn-sales-summary',
    label: 'HSN summary of sales',
    description: 'Outward supplies by HSN code and rate, net of credit '
        'notes and returns: quantity, taxable value and tax by head.',
    path: '/api/v1/sales-invoices/reports/hsn-summary',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'hsn_code', label: 'HSN'),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(key: 'rate', label: 'Rate %', numeric: true),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'taxable_value', label: 'Taxable', numeric: true),
      ReportColumn(key: 'igst', label: 'IGST', numeric: true),
      ReportColumn(key: 'cgst', label: 'CGST', numeric: true),
      ReportColumn(key: 'sgst', label: 'SGST', numeric: true),
      ReportColumn(key: 'cess', label: 'Cess', numeric: true),
      ReportColumn(key: 'total_tax', label: 'Total tax', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'customer-outstanding',
    label: 'Customer outstanding',
    description: 'What each customer still owes, and across how many invoices.',
    path: '/api/v1/sales-invoices/reports/customer-outstanding',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'sales-invoice-pending',
    label: 'Invoices not yet approved',
    description: 'Invoices still in draft, owed by nobody until approved.',
    path: '/api/v1/sales-invoices/reports/pending',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'sales-invoice-overdue',
    label: 'Overdue sales invoices',
    description: 'Invoices past their due date and still unpaid.',
    path: '/api/v1/sales-invoices/reports/overdue',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    // A flat row since D-RPT-3: the bill, whose it is, how late, and what it
    // still owes once receipts, points, returns and credits are taken off.
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(key: 'customer_name', label: 'Customer'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'days_overdue', label: 'Days overdue', numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
      ReportColumn(key: 'settled_amount', label: 'Settled', numeric: true),
      ReportColumn(
          key: 'outstanding_amount', label: 'Still owed', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'sales-invoice-due',
    label: 'Sales invoices falling due',
    description: 'Unpaid and falling due from today to the number of days '
        'ahead. Days 0 shows what falls due today and 7 the week ahead.',
    path: '/api/v1/sales-invoices/reports/due',
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
    days: 7,
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(key: 'customer_name', label: 'Customer'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'days_until_due', label: 'Days left', numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
      ReportColumn(key: 'settled_amount', label: 'Settled', numeric: true),
      ReportColumn(
          key: 'outstanding_amount', label: 'Still owed', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'sales-invoice-reconciliation',
    label: 'Sales invoice reconciliation',
    description: 'Invoices against the dispatches they were raised from.',
    path: '/api/v1/sales-invoices/reports/reconciliation',
    // Windowed on the invoice date since backlog 56 C step 4: over the whole
    // history it answered every line the firm ever billed.
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'sales-return-register',
    label: 'Sales return register',
    description: 'Every return taken back, with what it credited.',
    path: '/api/v1/sales-returns/reports/register',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-by-customer',
    label: 'Returns by customer',
    description: 'Who is sending goods back, and how much of it.',
    path: '/api/v1/sales-returns/reports/by-customer',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-by-product',
    label: 'Sales returns by product',
    description: 'What comes back most, by quantity and by value.',
    path: '/api/v1/sales-returns/reports/by-product',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-reconciliation',
    label: 'Sales return reconciliation',
    description: 'Each return line against the dispatch it came from, with '
        'what is still owed back.',
    path: '/api/v1/sales-returns/reports/reconciliation',
    needsPeriod: true,
    permission: 'SALES_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'credit-note-register',
    label: 'Credit note register',
    description: 'Every credit note raised, with the invoice it credits.',
    path: '/api/v1/credit-notes/reports/register',
    needsPeriod: true,
    permission: 'CREDIT_NOTE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'customer-debit-note-register',
    label: 'Customer debit note register',
    description:
        'Every debit note raised to a customer, with the invoice it adds to.',
    path: '/api/v1/customer-debit-notes/reports/register',
    needsPeriod: true,
    permission: 'CUSTOMER_DEBIT_NOTE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'debit-note-register',
    label: 'Debit note register',
    description: 'Every debit note raised, with the supplier bill it claims on.',
    path: '/api/v1/debit-notes/reports/register',
    needsPeriod: true,
    permission: 'DEBIT_NOTE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'party-adjustment-register',
    label: 'Party adjustment register',
    description:
        'Every write-off, write-back and set-off, with its reason and status.',
    path: '/api/v1/party-adjustments/reports/register',
    needsPeriod: true,
    permission: 'PARTY_ADJUSTMENT_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'contra-register',
    label: 'Contra register',
    description:
        'Every deposit, withdrawal and transfer between the firm\'s own '
        'cash and bank accounts.',
    path: '/api/v1/contra-vouchers/reports/register',
    needsPeriod: true,
    permission: 'JOURNAL_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'credit-note-by-customer',
    label: 'Credits by customer',
    description: 'What each customer has been credited, cancelled notes out.',
    path: '/api/v1/credit-notes/reports/by-customer',
    needsPeriod: true,
    permission: 'CREDIT_NOTE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'credit-note-by-reason',
    label: 'Credits by reason',
    description: 'Why credit is being given. A month of rate differences is '
        'a pricing problem; a month of short supply is a warehouse one.',
    path: '/api/v1/credit-notes/reports/by-reason',
    needsPeriod: true,
    permission: 'CREDIT_NOTE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'proforma-register',
    label: 'Proforma register',
    description: 'Every proforma raised, with the order it states.',
    path: '/api/v1/proforma-invoices/reports/register',
    needsPeriod: true,
    permission: 'PROFORMA_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'proforma-outstanding',
    label: 'Proformas awaiting payment',
    description: 'Issued figures a customer is still arranging payment '
        'against, with how long the prices stand.',
    path: '/api/v1/proforma-invoices/reports/outstanding',
    permission: 'PROFORMA_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'loyalty-balances',
    label: 'Loyalty balances',
    description: 'What each customer holds, and what it is worth today.',
    path: '/api/v1/loyalty/reports/balances',
    permission: 'LOYALTY_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'loyalty-movements',
    label: 'Loyalty movements',
    description: 'Every movement of credit: earned, spent, adjusted, lapsed.',
    path: '/api/v1/loyalty/reports/movements',
    needsPeriod: true,
    permission: 'LOYALTY_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'loyalty-expiring',
    label: 'Points about to lapse',
    description: 'What runs out and when, counted the way the sweep counts it.',
    path: '/api/v1/loyalty/reports/expiring',
    permission: 'LOYALTY_VIEW',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-invoice-register',
    label: 'Purchase invoice register',
    description: 'Every supplier invoice, with the number they gave it.',
    path: '/api/v1/purchase-invoices/reports/register',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'purchase-invoice-pending',
    label: 'Supplier invoices not yet approved',
    description: 'Supplier invoices still in draft.',
    path: '/api/v1/purchase-invoices/reports/pending',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(
          key: 'supplier_invoice_number', label: 'Supplier invoice number'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'purchase-invoice-reconciliation',
    label: 'Purchase invoice reconciliation',
    description: 'Supplier invoices against the goods actually received.',
    path: '/api/v1/purchase-invoices/reports/reconciliation',
    // Windowed on the bill date since backlog 56 C step 4, as the sales
    // invoice reconciliation is.
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'purchase-invoice-overdue',
    label: 'Overdue purchase invoices',
    description: 'What the firm owes and should already have paid.',
    path: '/api/v1/purchase-invoices/reports/overdue',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    // A flat row since D-RPT-2: the bill, whose it is, how late, and what it
    // still owes once payments, returns and credits are taken off.
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(
          key: 'supplier_invoice_number', label: 'Supplier invoice number'),
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'days_overdue', label: 'Days overdue', numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
      ReportColumn(key: 'allocated_amount', label: 'Paid', numeric: true),
      ReportColumn(
          key: 'outstanding_amount', label: 'Still owed', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'purchase-invoice-due',
    label: 'Purchase invoices falling due',
    description: 'Unpaid and falling due from today to the number of days '
        'ahead. Days 0 shows what falls due today and 7 the week ahead.',
    path: '/api/v1/purchase-invoices/reports/due',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    days: 7,
    columns: [
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(
          key: 'supplier_invoice_number', label: 'Supplier invoice number'),
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'due_date', label: 'Due date'),
      ReportColumn(key: 'days_until_due', label: 'Days left', numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
      ReportColumn(key: 'allocated_amount', label: 'Paid', numeric: true),
      ReportColumn(
          key: 'outstanding_amount', label: 'Still owed', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'purchase-invoice-msme-dues',
    label: 'MSME payments due',
    description: 'Unpaid bills to micro and small suppliers against the '
        'date the law sets: 45 days with a written agreement, 15 without. '
        'One unpaid past it is an expense disallowed this year (s.43B(h)).',
    path: '/api/v1/purchase-invoices/reports/msme-dues',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'msme_category', label: 'MSME'),
      ReportColumn(key: 'udyam_number', label: 'Udyam'),
      ReportColumn(key: 'invoice_number', label: 'Invoice number'),
      ReportColumn(
          key: 'supplier_invoice_number', label: 'Supplier invoice number'),
      ReportColumn(key: 'invoice_date', label: 'Invoice date'),
      ReportColumn(key: 'pay_by', label: 'Pay by'),
      ReportColumn(key: 'days_left', label: 'Days left', numeric: true),
      ReportColumn(key: 'state', label: 'State'),
      ReportColumn(
          key: 'outstanding_amount', label: 'Still owed', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'purchase-invoice-outstanding',
    label: 'Vendor outstanding',
    description: 'What is still owed to each supplier.',
    path: '/api/v1/purchase-invoices/reports/outstanding',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
  ),
  // The customer ageing's mirror (55 S7): what each supplier is owed, by
  // days past due, over what Record Payment says each bill still owes.
  ReportDefinition(
    id: 'vendor-ageing',
    label: 'Vendor ageing',
    description: 'What each supplier is owed today, by how many days past '
        'its due date. The bands are the firm\'s own, set under Financial '
        'years: 0-29, 30-59, 60-89 and 90+ unless changed.',
    path: '/api/v1/purchase-invoices/reports/vendor-ageing',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'vendor_code', label: 'Code'),
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'bills', label: 'Bills', numeric: true),
      ReportColumn(key: 'total_outstanding', label: 'Owed', numeric: true),
      ReportColumn(key: 'oldest_days', label: 'Oldest (days)', numeric: true),
    ],
    bandsKey: 'buckets',
  ),
  ReportDefinition(
    id: 'purchase-return-by-vendor',
    label: 'Returns by vendor',
    description: 'Returned value and count per supplier.',
    path: '/api/v1/purchase-returns/reports/by-vendor',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
  ),
  // The Commission screen's report, listed here too (BL-31.15): money each
  // salesman collected in the dates and the commission it earned. Its route
  // checks only COMMISSION_VIEW, not REPORT_VIEW.
  ReportDefinition(
    id: 'commission-collections',
    label: 'Commission on collections',
    description: 'What each salesman collected in the dates, and the '
        'commission it earned them.',
    path: '/api/v1/commission/report',
    permission: 'COMMISSION_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    rowsKey: 'rows',
    openToReportView: false,
  ),
  // Tally's Stock Summary (D-GOLIVE-3): what the stock is worth as on a day,
  // at moving average cost, with the Inventory account beside the total so a
  // gap between the stock and the books shows. Quarantined goods count: they
  // are still owned.
  ReportDefinition(
    id: 'stock-valuation',
    label: 'Stock valuation',
    description: "Every item's quantity, average cost and value as on the "
        'day, the grand total, and the Inventory account in the books.',
    path: '/api/v1/inventory/reports/stock-valuation',
    permission: 'INVENTORY_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    asOnDate: true,
    columns: [
      ReportColumn(key: 'product_code', label: 'Code'),
      ReportColumn(key: 'product_name', label: 'Item'),
      ReportColumn(key: 'category', label: 'Category'),
      ReportColumn(key: 'unit', label: 'Unit'),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'rate', label: 'Rate', numeric: true),
      ReportColumn(key: 'value', label: 'Value', numeric: true),
    ],
  ),
  // How old the stock on hand is (55 S7): FIFO's answer -- what is left is
  // what came in last -- in buckets of days, valued at the average cost.
  ReportDefinition(
    id: 'stock-ageing',
    label: 'Stock ageing',
    description: 'Stock on hand as on the day, split by how long ago it was '
        'received -- what came in last taken to be what is left -- with '
        'its value at average cost.',
    path: '/api/v1/inventory/reports/stock-ageing',
    permission: 'INVENTORY_VIEW',
    area: ReportArea.operational,
    needsPeriod: true,
    asOnDate: true,
    columns: [
      ReportColumn(key: 'product_code', label: 'Code'),
      ReportColumn(key: 'product_name', label: 'Item'),
      ReportColumn(key: 'category', label: 'Category'),
      ReportColumn(key: 'unit', label: 'Unit'),
      ReportColumn(key: 'quantity', label: 'On hand', numeric: true),
      ReportColumn(key: 'value', label: 'Value', numeric: true),
      ReportColumn(key: 'days_0_30', label: '0-30 days', numeric: true),
      ReportColumn(key: 'days_31_60', label: '31-60', numeric: true),
      ReportColumn(key: 'days_61_90', label: '61-90', numeric: true),
      ReportColumn(key: 'days_91_180', label: '91-180', numeric: true),
      ReportColumn(key: 'days_over_180', label: 'Over 180', numeric: true),
      ReportColumn(key: 'last_receipt_date', label: 'Last received'),
      ReportColumn(
          key: 'issued_last_year', label: 'Issued (last year)', numeric: true),
      ReportColumn(key: 'turnover', label: 'Turnover', numeric: true),
    ],
  ),
  // Stock that is not selling (55 S7): the Days box says over how long.
  ReportDefinition(
    id: 'slow-moving',
    label: 'Slow-moving stock',
    description: 'Stock on hand that the last so many days of sales would '
        'not clear in as many days again, or that did not sell at all -- '
        'slowest first.',
    path: '/api/v1/inventory/reports/slow-moving',
    permission: 'INVENTORY_VIEW',
    area: ReportArea.operational,
    needsPeriod: true,
    asOnDate: true,
    days: 90,
    columns: _slowStockColumns,
  ),
  ReportDefinition(
    id: 'dead-stock',
    label: 'Dead stock',
    description: 'Stock on hand that no customer took in the last so many '
        'days: what it is worth, and when it last sold.',
    path: '/api/v1/inventory/reports/dead-stock',
    permission: 'INVENTORY_VIEW',
    area: ReportArea.operational,
    needsPeriod: true,
    asOnDate: true,
    days: 180,
    columns: _slowStockColumns,
  ),
  // Free goods (BUY-1): what came in free, what went out free, what is left.
  ReportDefinition(
    id: 'free-goods',
    label: 'Free goods',
    description: 'Goods received free from suppliers, goods given free to '
        'customers, and promotional stock still on hand.',
    path: '/api/v1/inventory/reports/free-goods',
    needsPeriod: true,
    permission: 'INVENTORY_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'section', label: 'Section'),
      ReportColumn(key: 'party_name', label: 'Supplier / customer'),
      ReportColumn(key: 'detail', label: 'Scheme / reason'),
      ReportColumn(key: 'product_name', label: 'Product'),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'value', label: 'Value', numeric: true),
    ],
  ),
  // The drawing-power statement a bank asks a distributor for every month
  // (backlog 70 row 6): opening, in, out and closing, each with its value.
  ReportDefinition(
    id: 'stock-statement',
    label: 'Stock statement for the bank',
    description: 'Opening stock, receipts, issues and closing stock with '
        'their values over the period -- the monthly statement a bank asks '
        'for against a cash-credit limit.',
    path: '/api/v1/inventory/reports/stock-statement',
    permission: 'INVENTORY_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'product_code', label: 'Code'),
      ReportColumn(key: 'product_name', label: 'Item'),
      ReportColumn(key: 'category', label: 'Category'),
      ReportColumn(key: 'unit', label: 'Unit'),
      ReportColumn(key: 'opening_quantity', label: 'Opening', numeric: true),
      ReportColumn(key: 'opening_value', label: 'Opening value', numeric: true),
      ReportColumn(key: 'inward_quantity', label: 'In', numeric: true),
      ReportColumn(key: 'inward_value', label: 'In value', numeric: true),
      ReportColumn(key: 'outward_quantity', label: 'Out', numeric: true),
      ReportColumn(key: 'outward_value', label: 'Out value', numeric: true),
      ReportColumn(key: 'closing_quantity', label: 'Closing', numeric: true),
      ReportColumn(key: 'closing_value', label: 'Closing value', numeric: true),
    ],
  ),
  // Stock at or below its reorder level (42.9), with what is on order and a
  // suggested quantity. Purchase Orders > "..." > Below reorder level raises
  // the draft orders from the same rows.
  ReportDefinition(
    id: 'purchase-below-reorder',
    label: 'Below reorder level',
    description: 'Products at or below their reorder level in each warehouse: '
        'available, on order, the supplier last billed and what to order.',
    path: '/api/v1/purchases/reports/below-reorder',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    columns: [
      ReportColumn(key: 'warehouse_code', label: 'Warehouse'),
      ReportColumn(key: 'product_code', label: 'Code'),
      ReportColumn(key: 'product_name', label: 'Product'),
      ReportColumn(key: 'basis', label: 'Basis'),
      ReportColumn(key: 'average_daily_sales', label: 'Avg/day', numeric: true),
      ReportColumn(key: 'available_quantity', label: 'Available', numeric: true),
      ReportColumn(key: 'reorder_level', label: 'Reorder at', numeric: true),
      ReportColumn(key: 'maximum_level', label: 'Maximum', numeric: true),
      ReportColumn(key: 'on_order_quantity', label: 'On order', numeric: true),
      ReportColumn(
          key: 'suggested_quantity', label: 'Suggested', numeric: true),
      ReportColumn(key: 'supplier_name', label: 'Supplier'),
      ReportColumn(key: 'unit_price', label: 'Rate', numeric: true),
    ],
  ),
  // The Income-tax block schedule of a financial year (PG-13): it needs a
  // year chosen, which the generic grid cannot ask for, so Accounts > Fixed
  // assets is its screen and the Reports picker does not list it.
  ReportDefinition(
    id: 'it-block-schedule',
    label: 'Income-tax block schedule',
    description: 'Opening written down value, additions, disposals, '
        'depreciation and closing value for each Income-tax block.',
    path: '/api/v1/fixed-assets/reports/it-block-schedule',
    permission: 'FIXED_ASSET_VIEW',
    area: ReportArea.financial,
    ownScreen: true,
  ),
  // What one product was bought at, bill by bill: it needs a product chosen,
  // which the generic grid cannot ask for, so Buy > Rate Trend is its screen
  // (RPT-2) and the Reports picker does not list it.
  ReportDefinition(
    id: 'purchase-rate-trend',
    label: 'Purchase rate trend',
    description: 'The rate a product was bought at, bill by bill.',
    path: '/api/v1/purchase-invoices/reports/rate-trend',
    needsPeriod: true,
    permission: 'PURCHASE_VIEW',
    area: ReportArea.operational,
    ownScreen: true,
  ),
  // Where a supplier billed a rate other than the goods were received at
  // (65 row 5): the difference posts to Purchase Price Variance, and this
  // names it line by line so a buyer can take it up.
  ReportDefinition(
    id: 'purchase-price-variance',
    label: 'Purchase price variance',
    description: 'Bill lines charged at a rate other than the goods were '
        'received at: supplier, product, both rates and the difference.',
    path: '/api/v1/purchase-invoices/reports/price-variance',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'invoice_date', label: 'Date'),
      ReportColumn(key: 'invoice_number', label: 'Bill'),
      ReportColumn(key: 'supplier_invoice_number', label: 'Supplier bill'),
      ReportColumn(key: 'supplier_name', label: 'Supplier'),
      ReportColumn(key: 'receipt_number', label: 'Receipt'),
      ReportColumn(key: 'product_name', label: 'Product'),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'receipt_rate', label: 'Receipt rate', numeric: true),
      ReportColumn(key: 'bill_rate', label: 'Bill rate', numeric: true),
      ReportColumn(key: 'variance', label: 'Variance', numeric: true),
      ReportColumn(key: 'note', label: 'Note'),
    ],
  ),
  // The approved bills of a period by tax head, as a CA asks for them every
  // month (86 row 17). Heads are the components each line was charged, read
  // the way GSTR-3B reads them.
  ReportDefinition(
    id: 'gst-purchase-register',
    label: 'GST purchase register',
    description: 'Approved supplier bills by tax head: GSTIN, taxable value, '
        'IGST, CGST, SGST, cess, tax not claimable and reverse charge. '
        'Approved debit notes and completed purchase returns are rows of '
        'their own, in minus, on their own date.',
    path: '/api/v1/purchase-invoices/reports/gst-register',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'invoice_date', label: 'Date'),
      ReportColumn(key: 'document_type_label', label: 'Type'),
      ReportColumn(key: 'invoice_number', label: 'Number'),
      ReportColumn(key: 'against_invoice_number', label: 'Against bill'),
      ReportColumn(key: 'supplier_invoice_number', label: 'Supplier bill'),
      ReportColumn(key: 'supplier_invoice_date', label: 'Supplier bill date'),
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'vendor_gstin', label: 'GSTIN'),
      ReportColumn(key: 'taxable_value', label: 'Taxable', numeric: true),
      ReportColumn(key: 'igst', label: 'IGST', numeric: true),
      ReportColumn(key: 'cgst', label: 'CGST', numeric: true),
      ReportColumn(key: 'sgst', label: 'SGST', numeric: true),
      ReportColumn(key: 'cess', label: 'Cess', numeric: true),
      ReportColumn(key: 'total_tax', label: 'Total tax', numeric: true),
      ReportColumn(
          key: 'itc_not_claimable', label: 'Not claimable', numeric: true),
      ReportColumn(
          key: 'reverse_charge_tax', label: 'Reverse charge', numeric: true),
      ReportColumn(
          key: 'capital_goods_tax', label: 'Capital goods tax', numeric: true),
      ReportColumn(key: 'invoice_total', label: 'Bill total', numeric: true),
    ],
  ),
  // The same bills' inward supplies folded by HSN code and unit; a product
  // with no HSN shows under a blank code so the gap is visible.
  ReportDefinition(
    id: 'hsn-purchase-summary',
    label: 'HSN summary of purchases',
    description: 'Approved inward supplies by HSN code and unit: quantity, '
        'taxable value, tax by head and the number of bills.',
    path: '/api/v1/purchase-invoices/reports/hsn-summary',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'hsn_code', label: 'HSN'),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(key: 'unit', label: 'Unit'),
      ReportColumn(key: 'quantity', label: 'Quantity', numeric: true),
      ReportColumn(key: 'taxable_value', label: 'Taxable', numeric: true),
      ReportColumn(key: 'igst', label: 'IGST', numeric: true),
      ReportColumn(key: 'cgst', label: 'CGST', numeric: true),
      ReportColumn(key: 'sgst', label: 'SGST', numeric: true),
      ReportColumn(key: 'cess', label: 'Cess', numeric: true),
      ReportColumn(key: 'total_tax', label: 'Total tax', numeric: true),
      ReportColumn(key: 'bills', label: 'Bills', numeric: true),
    ],
  ),
  // TCS suppliers charged the firm under 206C(1H) (PG-6), claimed against
  // its own tax once 26AS shows it; each quarter closes with a total row.
  ReportDefinition(
    id: 'tcs-paid-to-suppliers',
    label: 'TCS paid to suppliers',
    description: 'Approved supplier bills that bore TCS: supplier, PAN, '
        'bill, base (the bill with GST), rate and TCS, with a total for each '
        'quarter to match against Form 26AS.',
    path: '/api/v1/purchase-invoices/reports/tcs-paid',
    permission: 'PURCHASE_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'quarter', label: 'Quarter'),
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'vendor_pan', label: 'PAN'),
      ReportColumn(key: 'invoice_number', label: 'Bill'),
      ReportColumn(key: 'supplier_invoice_number', label: 'Supplier bill'),
      ReportColumn(key: 'invoice_date', label: 'Date'),
      ReportColumn(key: 'base_amount', label: 'Base', numeric: true),
      ReportColumn(key: 'tcs_rate_percent', label: 'Rate %', numeric: true),
      ReportColumn(key: 'tcs_amount', label: 'TCS', numeric: true),
    ],
  ),
  // A collection is never rewritten, so a reversed or back-dated receipt
  // leaves a buyer over- or under-collected until they pay again; this is
  // where that shows (D-CMP-21). The year today falls in: a snapshot.
  ReportDefinition(
    id: 'tcs-charged-versus-due',
    label: 'TCS charged against due',
    description: 'Each buyer this financial year: the tax collected at '
        'source that was charged, against what their receipts made due.',
    path: '/api/v1/tcs/reports/charged-versus-due',
    permission: 'TCS_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'customer_name', label: 'Buyer'),
      ReportColumn(
          key: 'consideration_received', label: 'Received', numeric: true),
      ReportColumn(key: 'taxable_due', label: 'Taxable due', numeric: true),
      ReportColumn(key: 'tcs_due', label: 'TCS due', numeric: true),
      ReportColumn(key: 'tcs_charged', label: 'TCS charged', numeric: true),
      ReportColumn(key: 'difference', label: 'Difference', numeric: true),
      ReportColumn(key: 'position', label: 'Position'),
    ],
  ),
  // Section 194Q (ACC-8): what each supplier has been bought from this
  // Income-tax year against the threshold, and what is still to deduct.
  ReportDefinition(
    id: 'tds-194q',
    label: 'TDS on purchases (194Q)',
    description: 'Each supplier bought from this Income-tax year: the '
        'purchases, the part above the threshold, the TDS due on it, what '
        'has been deducted, and what is still to deduct.',
    path: '/api/v1/finance/reports/tds-194q',
    permission: 'ACCOUNT_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    asOnDate: true,
    onDateParam: 'on',
    columns: [
      ReportColumn(key: 'vendor_name', label: 'Supplier'),
      ReportColumn(key: 'pan', label: 'PAN'),
      ReportColumn(key: 'purchases', label: 'Bought', numeric: true),
      ReportColumn(key: 'excess', label: 'Above threshold', numeric: true),
      ReportColumn(key: 'rate_percent', label: 'Rate %', numeric: true),
      ReportColumn(key: 'due', label: 'TDS due', numeric: true),
      ReportColumn(key: 'deducted', label: 'Deducted', numeric: true),
      ReportColumn(key: 'to_deduct', label: 'To deduct', numeric: true),
    ],
  ),
  // Collections (67 row 9): money received from customers, a receipt on its
  // date and a reversal on the reversal's, netted.
  ReportDefinition(
    id: 'collections-by-day',
    label: 'Collections by day',
    description: 'Money received from customers each day in the dates, '
        'with reversals taken off on the day they were made.',
    path: '/api/v1/receipts/reports/collections-by-day',
    needsPeriod: true,
    permission: 'RECEIPT_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'label', label: 'Day'),
      ..._collectionFigures,
    ],
  ),
  ReportDefinition(
    id: 'collections-by-salesman',
    label: 'Collections by salesman',
    description: 'Money received in the dates, credited to the salesman of '
        'the bill it cleared; what cleared no bill is On account.',
    path: '/api/v1/receipts/reports/collections-by-salesman',
    needsPeriod: true,
    permission: 'RECEIPT_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'label', label: 'Salesman'),
      ..._collectionFigures,
    ],
  ),
  ReportDefinition(
    id: 'collections-by-mode',
    label: 'Collections by mode',
    description: 'Money received in the dates by cash and through the bank, '
        'reversals netted.',
    path: '/api/v1/receipts/reports/collections-by-mode',
    needsPeriod: true,
    permission: 'RECEIPT_VIEW',
    area: ReportArea.financial,
    columns: [
      ReportColumn(key: 'label', label: 'Mode'),
      ..._collectionFigures,
    ],
  ),
  // Tally's Day Book (55 M9): every journal in the books over the dates, in
  // date order. Double-click a row for the journal's lines.
  ReportDefinition(
    id: 'day-book',
    label: 'Day book',
    description: 'Every voucher in the books over the dates, in date order: '
        'what raised it, its narration and its totals. Double-click a row '
        'to see the journal.',
    path: '/api/v1/finance/reports/day-book',
    permission: 'JOURNAL_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    drill: ReportDrill.journal,
    columns: [
      ReportColumn(key: 'journal_date', label: 'Date'),
      ReportColumn(key: 'voucher', label: 'Voucher'),
      ReportColumn(key: 'voucher_type', label: 'Type'),
      ReportColumn(key: 'source', label: 'Raised by'),
      ReportColumn(key: 'narration', label: 'Narration'),
      ReportColumn(key: 'debit', label: 'Debit', numeric: true),
      ReportColumn(key: 'credit', label: 'Credit', numeric: true),
      ReportColumn(key: 'status', label: 'Status'),
    ],
  ),
  // The cash and bank books (55 M9): opening, each posting with the balance
  // after it -- in date order -- and closing.
  ReportDefinition(
    id: 'cash-book',
    label: 'Cash book',
    description: 'Every movement of cash over the dates with the balance '
        'after it, from the opening balance to the closing. Double-click a '
        'row to see the journal.',
    path: '/api/v1/finance/reports/cash-book',
    permission: 'LEDGER_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    drill: ReportDrill.journal,
    columns: _moneyBookColumns,
  ),
  ReportDefinition(
    id: 'bank-book',
    label: 'Bank book',
    description: 'Every movement through the bank over the dates with the '
        'balance after it, from the opening balance to the closing. '
        'Double-click a row to see the journal.',
    path: '/api/v1/finance/reports/bank-book',
    permission: 'LEDGER_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    drill: ReportDrill.journal,
    columns: _moneyBookColumns,
  ),
  // What the quarterly TDS return (26Q) is filed from (53.1): every
  // deduction the firm made on payments and expenses, by deductee and PAN.
  ReportDefinition(
    id: 'tds-deducted',
    label: 'TDS deducted',
    description: 'Every tax deducted at source on payments and expenses in '
        'the dates: deductee, PAN, section and return quarter.',
    path: '/api/v1/finance/reports/tds-deducted',
    permission: 'ACCOUNT_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'date', label: 'Date'),
      ReportColumn(key: 'quarter', label: 'Quarter'),
      ReportColumn(key: 'document_type', label: 'Document'),
      ReportColumn(key: 'document_number', label: 'Number'),
      ReportColumn(key: 'party_name', label: 'Deductee'),
      ReportColumn(key: 'pan', label: 'PAN'),
      ReportColumn(key: 'section', label: 'Section'),
      ReportColumn(key: 'gross_amount', label: 'Amount', numeric: true),
      ReportColumn(key: 'tds_amount', label: 'TDS', numeric: true),
      ReportColumn(key: 'net_amount', label: 'Paid', numeric: true),
      ReportColumn(key: 'status', label: 'Status'),
    ],
  ),
  // The quarterly TDS return (53.1): one quarter's deductions as Annexure I
  // of Form 26Q lists them, and the workbook to prepare the return from.
  ReportDefinition(
    id: 'tds-26q',
    label: 'TDS return (26Q)',
    description: 'One quarter of tax deducted at source on payments other '
        'than salary, laid out as Form 26Q lists deductees. Download gives '
        'the workbook to prepare the return from.',
    path: '/api/v1/finance/reports/tds-26q',
    permission: 'ACCOUNT_VIEW',
    area: ReportArea.financial,
    quarterly: true,
    file: ReportFile.tds26q,
    columns: [
      ReportColumn(key: 'serial', label: 'Sr', numeric: true),
      ReportColumn(key: 'section', label: 'Section'),
      ReportColumn(key: 'deductee_code', label: 'Code'),
      ReportColumn(key: 'pan', label: 'PAN'),
      ReportColumn(key: 'party_name', label: 'Deductee'),
      ReportColumn(key: 'payment_date', label: 'Paid on'),
      ReportColumn(key: 'amount_paid', label: 'Amount', numeric: true),
      ReportColumn(key: 'tds_amount', label: 'TDS', numeric: true),
      ReportColumn(key: 'rate_percent', label: 'Rate %', numeric: true),
      ReportColumn(key: 'higher_rate_reason', label: 'Reason'),
      ReportColumn(key: 'document_number', label: 'Document'),
    ],
  ),
  // What customers deducted from what they paid, by their TAN, to tick the
  // firm's TDS Receivable against Form 26AS (53.1).
  ReportDefinition(
    id: 'tds-deducted-by-customers',
    label: 'TDS deducted by customers',
    description: 'Tax customers deducted at source from their payments in '
        'the dates, with their TAN, to match against Form 26AS.',
    path: '/api/v1/finance/reports/tds-deducted-by-customers',
    permission: 'ACCOUNT_VIEW',
    area: ReportArea.financial,
    needsPeriod: true,
    columns: [
      ReportColumn(key: 'date', label: 'Date'),
      ReportColumn(key: 'quarter', label: 'Quarter'),
      ReportColumn(key: 'document_number', label: 'Receipt'),
      ReportColumn(key: 'party_name', label: 'Customer'),
      ReportColumn(key: 'tan', label: 'TAN'),
      ReportColumn(key: 'pan', label: 'PAN'),
      ReportColumn(key: 'section', label: 'Section'),
      ReportColumn(key: 'gross_amount', label: 'Amount', numeric: true),
      ReportColumn(key: 'tds_amount', label: 'TDS', numeric: true),
      ReportColumn(key: 'net_amount', label: 'Received', numeric: true),
      ReportColumn(key: 'status', label: 'Status'),
    ],
  ),
  // Parties whose PAN needs attention (PLT-11): a supplier with none costs
  // the higher TDS rate, and one outside the GSTIN is wrong on one side.
  ReportDefinition(
    id: 'customer-pan-check',
    label: 'Customer PAN check',
    description: 'Customers with no PAN, a PAN not in the PAN format, or one '
        'that is not characters 3 to 12 of their GSTIN. Saving a customer '
        'whose GSTIN carries the PAN fills a blank one.',
    path: '/api/v1/customers/reports/pan',
    permission: 'CUSTOMER_VIEW',
    area: ReportArea.financial,
    columns: _panCheckColumns,
  ),
  ReportDefinition(
    id: 'vendor-pan-check',
    label: 'Supplier PAN check',
    description: 'Suppliers with no PAN -- tax is deducted from them at the '
        'higher rate -- a PAN not in the PAN format, or one that is not '
        'characters 3 to 12 of their GSTIN.',
    path: '/api/v1/vendors/reports/pan',
    permission: 'VENDOR_VIEW',
    area: ReportArea.financial,
    columns: _panCheckColumns,
  ),
];

/// The PAN reports' columns (PLT-11).
const List<ReportColumn> _panCheckColumns = [
  ReportColumn(key: 'code', label: 'Code'),
  ReportColumn(key: 'name', label: 'Name'),
  ReportColumn(key: 'status', label: 'Status'),
  ReportColumn(key: 'gstin', label: 'GSTIN'),
  ReportColumn(key: 'pan', label: 'PAN'),
  ReportColumn(key: 'pan_in_gstin', label: 'PAN in GSTIN'),
  ReportColumn(key: 'problem', label: 'Problem'),
];

/// The cash book's and the bank book's columns: Tally's layout, with the
/// account beside the particulars because a bank book can span accounts.
const List<ReportColumn> _moneyBookColumns = [
  ReportColumn(key: 'date', label: 'Date'),
  ReportColumn(key: 'voucher', label: 'Voucher'),
  ReportColumn(key: 'particulars', label: 'Particulars'),
  ReportColumn(key: 'source', label: 'Raised by'),
  ReportColumn(key: 'account', label: 'Account'),
  // How a receipt's or payment's money moved, and its cheque or UTR (ACC-3).
  ReportColumn(key: 'mode', label: 'Mode'),
  ReportColumn(key: 'instrument', label: 'Instrument'),
  ReportColumn(key: 'narration', label: 'Narration'),
  ReportColumn(key: 'receipt', label: 'Receipt', numeric: true),
  ReportColumn(key: 'payment', label: 'Payment', numeric: true),
  ReportColumn(key: 'balance', label: 'Balance', numeric: true),
];

/// The slow-moving and dead stock reports' columns (55 S7).
const List<ReportColumn> _slowStockColumns = [
  ReportColumn(key: 'product_code', label: 'Code'),
  ReportColumn(key: 'product_name', label: 'Item'),
  ReportColumn(key: 'category', label: 'Category'),
  ReportColumn(key: 'unit', label: 'Unit'),
  ReportColumn(key: 'quantity', label: 'On hand', numeric: true),
  ReportColumn(key: 'value', label: 'Value', numeric: true),
  ReportColumn(key: 'issued_quantity', label: 'Sold in the days', numeric: true),
  ReportColumn(key: 'days_of_cover', label: 'Days of cover', numeric: true),
  ReportColumn(key: 'last_issue_date', label: 'Last sold'),
  ReportColumn(key: 'days_since_issue', label: 'Days since', numeric: true),
  ReportColumn(key: 'last_receipt_date', label: 'Last received'),
];

/// The discount reports' columns (67 row 8): typed beside arranged.
const List<ReportColumn> _discountColumns = [
  ReportColumn(key: 'code', label: 'Code'),
  ReportColumn(key: 'name', label: 'Name'),
  ReportColumn(key: 'lines', label: 'Lines', numeric: true),
  ReportColumn(key: 'gross_amount', label: 'Gross', numeric: true),
  ReportColumn(key: 'typed_discount', label: 'Typed', numeric: true),
  ReportColumn(key: 'arranged_discount', label: 'Arranged', numeric: true),
  ReportColumn(key: 'promotion_discount', label: 'Offers', numeric: true),
  ReportColumn(key: 'bill_discount', label: 'Bill discount', numeric: true),
  ReportColumn(key: 'total_discount', label: 'Total', numeric: true),
  ReportColumn(key: 'discount_percent', label: '% of gross', numeric: true),
];

/// The collection reports' figures (67 row 9), after what each row is for.
const List<ReportColumn> _collectionFigures = [
  ReportColumn(key: 'receipts', label: 'Receipts', numeric: true),
  ReportColumn(key: 'collected', label: 'Received', numeric: true),
  ReportColumn(key: 'reversals', label: 'Reversals', numeric: true),
  ReportColumn(key: 'reversed', label: 'Reversed', numeric: true),
  ReportColumn(key: 'net_collected', label: 'Net', numeric: true),
];

/// The reports belonging to one tab, narrowed to what `canRead` allows.
///
/// A report opens to whoever holds `REPORT_VIEW` or the module's own view
/// code, so the picker asks that of each entry rather than listing reports
/// the server will refuse (D-RPT-4). With no predicate every entry is
/// listed, which is what the catalogue tests ask.
List<ReportDefinition> reportsFor(
  ReportArea area, {
  bool Function(ReportDefinition report)? canRead,
}) =>
    [
      for (final ReportDefinition report in reportCatalog)
        if (report.area == area && (canRead == null || canRead(report))) report
    ];
