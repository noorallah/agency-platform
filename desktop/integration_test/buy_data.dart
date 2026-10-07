import 'cases.dart';
import 'harness.dart';

// Data for the buying cases (PO, GR, PB, PY, PR), set up over HTTP.

String _today() => DateTime.now().toIso8601String().substring(0, 10);

/// A purchase order for [quantity] units of the product of the firm's newest
/// order, raised as [server]'s user. [stage] is 'draft', 'submitted' or
/// 'approved'.
Future<Json> apiPo(Server server,
    {num quantity = 10, String stage = 'approved'}) async {
  final Json? seed = await server.newest('purchases');
  if (seed == null) throw StateError('no purchase order to copy masters from');
  final Json f = await server.one('purchases', '${seed['id']}');
  final Json l = (f['lines'] as List<dynamic>).first as Json;
  final Json po = (await server.write('POST', '/api/v1/purchases', <String, dynamic>{
    'vendor_id': f['vendor_id'],
    'branch_id': f['branch_id'],
    'warehouse_id': f['warehouse_id'],
    'buyer_id': f['buyer_id'],
    'purchase_date': _today(),
    'lines': <Json>[
      <String, dynamic>{
        'product_id': l['product_id'],
        'ordered_quantity': quantity,
        'unit_price': '60',
        'purchase_uom_id': l['purchase_uom_id'],
        'inventory_uom_id': l['inventory_uom_id'],
      },
    ],
  })) as Json;
  if (stage != 'draft') await apiAct(server, 'purchases', '${po['id']}', 'submit');
  if (stage == 'approved') {
    await apiAct(server, 'purchases', '${po['id']}', 'approve');
  }
  return server.one('purchases', '${po['id']}');
}

/// A goods receipt of [quantity] against [po], completed unless [complete] is
/// false.
Future<Json> apiReceiptOf(Server server, Json po,
    {num quantity = 10, bool complete = true}) async {
  final Json line = (po['lines'] as List<dynamic>).first as Json;
  final Json gr = (await server
      .write('POST', '/api/v1/goods-receipts', <String, dynamic>{
    'purchase_order_id': po['id'],
    'receipt_date': _today(),
    'lines': <Json>[
      <String, dynamic>{
        'purchase_order_line_id': line['id'],
        'line_number': 1,
        'current_receipt_quantity': quantity,
      },
    ],
  })) as Json;
  if (complete) await apiAct(server, 'goods-receipts', '${gr['id']}', 'complete');
  return server.one('goods-receipts', '${gr['id']}');
}

/// A draft supplier bill for [quantity] (all, if null) of a completed [gr].
Future<Json> apiBill(Server server, Json gr, {num? quantity}) async {
  final Json l = (gr['lines'] as List<dynamic>).first as Json;
  return (await server
      .write('POST', '/api/v1/purchase-invoices', <String, dynamic>{
    'vendor_id': gr['vendor_id'],
    'branch_id': gr['branch_id'],
    'invoice_date': _today(),
    'supplier_invoice_number': 'SUP-${DateTime.now().microsecondsSinceEpoch}',
    'supplier_invoice_date': _today(),
    'source_documents': <Json>[
      <String, dynamic>{
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': gr['id'],
      },
    ],
    'lines': <Json>[
      <String, dynamic>{
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': gr['id'],
        'source_document_line_id': l['id'],
        'line_number': 1,
        'current_invoice_quantity': quantity ?? l['left_to_bill_quantity'],
      },
    ],
  })) as Json;
}

/// An approved bill from a fresh order, receipt and bill of [quantity];
/// `receipt` and `order` are added to it.
Future<Json> apiApprovedBill(Server server, {num quantity = 10}) async {
  final Json po = await apiPo(server, quantity: quantity);
  final Json gr = await apiReceiptOf(server, po, quantity: quantity);
  final Json draft = await apiBill(server, gr);
  await apiAct(server, 'purchase-invoices', '${draft['id']}', 'approve');
  final Json whole = await server.one('purchase-invoices', '${draft['id']}');
  whole['receipt'] = gr;
  whole['order'] = po;
  return whole;
}

/// A cash payment of [amount] to the supplier of [bill], against it.
Future<Json> apiPayment(Server server, Json bill, num amount) async {
  return (await server.write('POST', '/api/v1/payments', <String, dynamic>{
    'party_id': bill['vendor_id'],
    'settlement_date': _today(),
    'amount': '$amount',
    'method': 'CASH',
    'allocations': <Json>[
      <String, dynamic>{'invoice_id': bill['id'], 'amount': '$amount'},
    ],
  })) as Json;
}

/// A draft purchase return of [quantity] against completed receipt [gr].
Future<Json> apiPurchaseReturn(Server server, Json gr,
    {num quantity = 1}) async {
  final Json l = (gr['lines'] as List<dynamic>).first as Json;
  return (await server
      .write('POST', '/api/v1/purchase-returns', <String, dynamic>{
    'vendor_id': gr['vendor_id'],
    'branch_id': gr['branch_id'],
    'warehouse_id': gr['warehouse_id'],
    'return_date': _today(),
    'source_documents': <Json>[
      <String, dynamic>{
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': gr['id'],
      },
    ],
    'lines': <Json>[
      <String, dynamic>{
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': gr['id'],
        'source_document_line_id': l['id'],
        'line_number': 1,
        'current_return_quantity': quantity,
      },
    ],
  })) as Json;
}
