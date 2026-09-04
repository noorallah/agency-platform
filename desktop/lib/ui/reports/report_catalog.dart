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
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'quotation-conversion',
    label: 'Quotation conversion',
    description: 'How many offers became orders, and how many lapsed.',
    path: '/api/v1/quotations/reports/conversion',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-register',
    label: 'Sales order register',
    description: 'Every order raised, with what it was worth.',
    path: '/api/v1/sales-orders/reports/register',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-pending',
    label: 'Orders not yet delivered',
    description: 'Orders with stock still owed to the customer.',
    path: '/api/v1/sales-orders/reports/pending',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-back-orders',
    label: 'Back orders',
    description: 'Orders the warehouse could not fill in full.',
    path: '/api/v1/sales-orders/reports/back-orders',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-customer',
    label: 'Orders by customer',
    description: 'Who is ordering, and how much of it.',
    path: '/api/v1/sales-orders/reports/by-customer',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-salesman',
    label: 'Orders by salesman',
    description: 'What each salesman has brought in.',
    path: '/api/v1/sales-orders/reports/by-salesman',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-order-by-territory',
    label: 'Orders by territory',
    description: 'Order value and count per territory, cancellations excluded.',
    path: '/api/v1/sales-orders/reports/by-territory',
    area: ReportArea.operational,
  ),

  // ---- Dispatch ------------------------------------------------------
  ReportDefinition(
    id: 'delivery-note-register',
    label: 'Delivery note register',
    description: 'Every dispatch, and the order it came from.',
    path: '/api/v1/delivery-notes/reports/register',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-pending',
    label: 'Dispatches not yet completed',
    description: 'Notes raised but not sent out.',
    path: '/api/v1/delivery-notes/reports/pending',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'delivery_note_number', label: 'Delivery note number'),
      ReportColumn(key: 'delivery_date', label: 'Delivery date'),
      ReportColumn(key: 'status', label: 'Status'),
      ReportColumn(
          key: 'total_current_delivery_quantity',
          label: 'Total current delivery quantity',
          numeric: true),
      ReportColumn(key: 'grand_total', label: 'Grand total', numeric: true),
    ],
  ),
  ReportDefinition(
    id: 'delivery-note-partial',
    label: 'Part-dispatched notes',
    description: 'Notes where some of the line was left behind.',
    path: '/api/v1/delivery-notes/reports/partial',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-route',
    label: 'Dispatches by route',
    description: 'What went out on each route.',
    path: '/api/v1/delivery-notes/reports/by-route',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-salesman',
    label: 'Dispatches by salesman',
    description: 'Delivered value and count per salesman.',
    path: '/api/v1/delivery-notes/reports/by-salesman',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'delivery-note-by-warehouse',
    label: 'Dispatches by warehouse',
    description: 'Delivered value and count per warehouse.',
    path: '/api/v1/delivery-notes/reports/by-warehouse',
    area: ReportArea.operational,
  ),

  // ---- Purchase ------------------------------------------------------
  ReportDefinition(
    id: 'goods-receipt-pending',
    label: 'Receipts awaiting completion',
    description: 'Goods booked in but not yet put into stock.',
    path: '/api/v1/goods-receipts/reports/pending',
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
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'goods-receipt-completed',
    label: 'Receipts completed',
    description: 'Goods received in full and taken into stock.',
    path: '/api/v1/goods-receipts/reports/completed',
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
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'line_number', label: 'Line number', numeric: true),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(
          key: 'ordered_quantity', label: 'Ordered quantity', numeric: true),
      ReportColumn(
          key: 'current_receipt_quantity',
          label: 'Current receipt quantity',
          numeric: true),
      ReportColumn(
          key: 'damaged_quantity', label: 'Damaged quantity', numeric: true),
      ReportColumn(key: 'batch_number', label: 'Batch number'),
    ],
  ),
  ReportDefinition(
    id: 'goods-receipt-rejected',
    label: 'Rejected on receipt',
    description: 'Lines refused at the door and not taken into stock.',
    path: '/api/v1/goods-receipts/reports/rejected',
    area: ReportArea.operational,
    // The endpoint answers with whole documents, so the columns are
    // named rather than derived from forty fields of one record.
    columns: [
      ReportColumn(key: 'line_number', label: 'Line number', numeric: true),
      ReportColumn(key: 'description', label: 'Description'),
      ReportColumn(
          key: 'ordered_quantity', label: 'Ordered quantity', numeric: true),
      ReportColumn(
          key: 'current_receipt_quantity',
          label: 'Current receipt quantity',
          numeric: true),
      ReportColumn(
          key: 'rejected_quantity', label: 'Rejected quantity', numeric: true),
      ReportColumn(key: 'batch_number', label: 'Batch number'),
    ],
  ),
  ReportDefinition(
    id: 'purchase-return-register',
    label: 'Purchase return register',
    description: 'Everything sent back to a supplier.',
    path: '/api/v1/purchase-returns/reports/register',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-reconciliation',
    label: 'Purchase return reconciliation',
    description: 'Return lines against the receipts they came from.',
    path: '/api/v1/purchase-returns/reports/reconciliation',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-damaged',
    label: 'Damaged goods returned',
    description: 'Lines returned because the goods were damaged.',
    path: '/api/v1/purchase-returns/reports/damaged',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-expired',
    label: 'Expired stock returned',
    description: 'Lines returned because the stock was past its date.',
    path: '/api/v1/purchase-returns/reports/expired',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-return-by-product',
    label: 'Returns by product',
    description: 'Quantity and value returned per product.',
    path: '/api/v1/purchase-returns/reports/by-product',
    area: ReportArea.operational,
  ),

  // ---- Financial -----------------------------------------------------
  ReportDefinition(
    id: 'sales-invoice-register',
    label: 'Sales invoice register',
    description: 'Every invoice raised, with its status.',
    path: '/api/v1/sales-invoices/reports/register',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'customer-outstanding',
    label: 'Customer outstanding',
    description: 'What each customer still owes, and across how many invoices.',
    path: '/api/v1/sales-invoices/reports/customer-outstanding',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'sales-invoice-pending',
    label: 'Invoices not yet approved',
    description: 'Invoices still in draft, owed by nobody until approved.',
    path: '/api/v1/sales-invoices/reports/pending',
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
    id: 'sales-invoice-reconciliation',
    label: 'Sales invoice reconciliation',
    description: 'Invoices against the dispatches they were raised from.',
    path: '/api/v1/sales-invoices/reports/reconciliation',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'sales-return-register',
    label: 'Sales return register',
    description: 'Every return taken back, with what it credited.',
    path: '/api/v1/sales-returns/reports/register',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-by-customer',
    label: 'Returns by customer',
    description: 'Who is sending goods back, and how much of it.',
    path: '/api/v1/sales-returns/reports/by-customer',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-by-product',
    label: 'Returns by product',
    description: 'What comes back most, by quantity and by value.',
    path: '/api/v1/sales-returns/reports/by-product',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'sales-return-reconciliation',
    label: 'Sales return reconciliation',
    description: 'Each return line against the dispatch it came from, with '
        'what is still owed back.',
    path: '/api/v1/sales-returns/reports/reconciliation',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'credit-note-register',
    label: 'Credit note register',
    description: 'Every credit note raised, with the invoice it credits.',
    path: '/api/v1/credit-notes/reports/register',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'credit-note-by-customer',
    label: 'Credits by customer',
    description: 'What each customer has been credited, cancelled notes out.',
    path: '/api/v1/credit-notes/reports/by-customer',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'credit-note-by-reason',
    label: 'Credits by reason',
    description: 'Why credit is being given. A month of rate differences is '
        'a pricing problem; a month of short supply is a warehouse one.',
    path: '/api/v1/credit-notes/reports/by-reason',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'proforma-register',
    label: 'Proforma register',
    description: 'Every proforma raised, with the order it states.',
    path: '/api/v1/proforma-invoices/reports/register',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'proforma-outstanding',
    label: 'Proformas awaiting payment',
    description: 'Issued figures a customer is still arranging payment '
        'against, with how long the prices stand.',
    path: '/api/v1/proforma-invoices/reports/outstanding',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'loyalty-balances',
    label: 'Loyalty balances',
    description: 'What each customer holds, and what it is worth today.',
    path: '/api/v1/loyalty/reports/balances',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'loyalty-movements',
    label: 'Loyalty movements',
    description: 'Every movement of credit: earned, spent, adjusted, lapsed.',
    path: '/api/v1/loyalty/reports/movements',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'loyalty-expiring',
    label: 'Points about to lapse',
    description: 'What runs out and when, counted the way the sweep counts it.',
    path: '/api/v1/loyalty/reports/expiring',
    area: ReportArea.operational,
  ),
  ReportDefinition(
    id: 'purchase-invoice-register',
    label: 'Purchase invoice register',
    description: 'Every supplier invoice, with the number they gave it.',
    path: '/api/v1/purchase-invoices/reports/register',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'purchase-invoice-pending',
    label: 'Supplier invoices not yet approved',
    description: 'Supplier invoices still in draft.',
    path: '/api/v1/purchase-invoices/reports/pending',
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
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'purchase-invoice-overdue',
    label: 'Overdue purchase invoices',
    description: 'What the firm owes and should already have paid.',
    path: '/api/v1/purchase-invoices/reports/overdue',
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
    id: 'purchase-invoice-outstanding',
    label: 'Vendor outstanding',
    description: 'What is still owed to each supplier.',
    path: '/api/v1/purchase-invoices/reports/outstanding',
    area: ReportArea.financial,
  ),
  ReportDefinition(
    id: 'purchase-return-by-vendor',
    label: 'Returns by vendor',
    description: 'Returned value and count per supplier.',
    path: '/api/v1/purchase-returns/reports/by-vendor',
    area: ReportArea.financial,
  ),
];

/// The reports belonging to one tab.
List<ReportDefinition> reportsFor(ReportArea area) => [
      for (final ReportDefinition report in reportCatalog)
        if (report.area == area) report
    ];
