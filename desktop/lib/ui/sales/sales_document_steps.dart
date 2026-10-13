import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/price_floor.dart';
import '../../phase2/document_page.dart' show documentQuantity;
import '../document_framework/document_status_gate.dart';
import '../document_framework/document_steps.dart';
import '../trade_licences/licence_check_dialog.dart';
import '../workspace/reason_prompt.dart';
import 'credit_notice.dart';
import 'price_floor_check_dialog.dart';

// The next steps of a sales order and a sales invoice, for the list
// toolbars and the documents' own windows alike (D-BUY-22). Both are read
// off the server's JSON, which is what the two lists hold.
//
// The server gates approve and close (and hold, release and reserving
// again) on `SALES_APPROVE` and cancel on `SALES_CANCEL`.

/// Approve a sale, asking first what approval decides.
///
/// Credit is asked about **before** the call: once approved the document is
/// in the exposure it is checked against, and asking afterwards would count
/// it twice. A question, never a block -- the server refuses when the firm's
/// policy says Block. Then the licences its lines need (backlog 54) and the
/// price floors (backlog 64 row 2), each of which may carry the reason of
/// whoever overrides it.
Future<DocumentStepDone?> _approveSale(
  BuildContext context,
  ApiClient api,
  PermissionService permissions, {
  required Json row,
  required String resource,
  required String document,
  required Future<PriceFloorCheck> Function() priceCheck,
  bool backOrders = false,
}) async {
  final bool goOn = await confirmCreditExposure(
    context,
    api,
    customerId: row['customer_id'] as String?,
    amount: '${row['grand_total'] ?? '0'}',
  );
  if (!goOn || !context.mounted) return null;
  final LicenceCheckOutcome licence = await confirmLicenceCheck(
    context,
    api,
    permissions,
    document: document,
    documentId: '${row['id']}',
  );
  if (!licence.proceed || !context.mounted) return null;
  final PriceFloorOutcome price =
      await confirmPriceFloor(context, permissions, check: priceCheck);
  if (!price.proceed) return null;
  final String? overrideReason = licence.overrideReason;
  final String? priceOverrideReason = price.overrideReason;
  await api.documentAction(
    resource,
    '${row['id']}',
    '/approve',
    query: overrideReason == null && priceOverrideReason == null
        ? null
        : {
            if (overrideReason != null)
              'licence_override_reason': overrideReason,
            if (priceOverrideReason != null)
              'price_override_reason': priceOverrideReason,
          },
  );
  // Said by the list once it reads itself again, and only by the status:
  // the status says it, and "approved" would add nothing to it --
  // except when an order was approved for more than the stock on hand,
  // which nothing else says (D-UI-24).
  final String? shortage =
      backOrders ? await _shortfallOf(api, '${row['id']}') : null;
  return shortage == null
      ? const DocumentStepDone('', step: 'approve')
      : DocumentStepDone(shortage, warning: true, step: 'approve');
}

/// What the back-order report says of the order just approved: one more
/// read, after the approval and only for a sales order.
///
/// The approval is done by now, so a report that cannot be read (no
/// connection, no leave to read it) costs the notice and nothing else.
Future<String?> _shortfallOf(ApiClient api, String orderId) async {
  try {
    return approvedShortfallNotice(
      await api.salesOrderBackOrders(orderIds: [orderId]),
      orderId,
    );
  } on Object {
    return null;
  }
}

/// What the back-order report says of the orders a bulk approve put
/// through: one read for all of them, asked about those orders alone
/// (D-UI-61). Null where every line was covered, where none was approved,
/// or where the report cannot be read -- the approvals are done by then.
Future<String?> bulkApprovedShortfall(
  ApiClient api,
  List<String> orderIds,
) async {
  if (orderIds.isEmpty) return null;
  try {
    return approvedOrdersShortfallNotice(
      await api.salesOrderBackOrders(orderIds: orderIds),
      orderIds,
    );
  } on Object {
    return null;
  }
}

/// How many orders a bulk approve's back-order sentence names before it
/// says "and N more": the sentence is a toast, not a report.
const int _ordersNamedOnBackOrder = 5;

/// The back-order sentence for several orders approved at once: each order
/// with something short is named by its number, with its lines as the single
/// approve states them. One order short among the several still names it --
/// the person approved a batch and has to know which.
String? approvedOrdersShortfallNotice(
  Object? backOrders,
  List<String> orderIds,
) {
  if (backOrders is! List) return null;
  final Set<String> approved = orderIds.toSet();
  final Map<String, List<String>> short = <String, List<String>>{};
  final Map<String, String> numbers = <String, String>{};
  for (final Object? line in backOrders) {
    if (line is! Map || !approved.contains('${line['order_id']}')) continue;
    final String? stated = _shortLine(line);
    if (stated == null) continue;
    final String id = '${line['order_id']}';
    short.putIfAbsent(id, () => <String>[]).add(stated);
    numbers[id] = '${line['order_number'] ?? ''}'.trim();
  }
  if (short.isEmpty) return null;
  final List<String> named = [
    for (final MapEntry<String, List<String>> order
        in short.entries.take(_ordersNamedOnBackOrder))
      '${numbers[order.key]!.isEmpty ? 'An order' : numbers[order.key]}: '
          '${order.value.join(', ')}',
  ];
  final int more = short.length - named.length;
  return 'Not in stock, and staying on back order. ${named.join('; ')}'
      '${more > 0 ? '; and $more more ${more == 1 ? 'order' : 'orders'}' : ''}.';
}

/// One back-order row as the sentence states it, "418 of 500 of Shampoo",
/// or null where the row has nothing short.
String? _shortLine(Map<Object?, Object?> line) {
  final double? need = double.tryParse('${line['requested_quantity']}');
  final double? missing = double.tryParse('${line['back_order_quantity']}');
  if (need == null || missing == null || missing <= 0) return null;
  String figure(double value) => documentQuantity(value.toStringAsFixed(4));
  final String name = '${line['product_name'] ?? ''}'.trim();
  return '${figure(missing)} of ${figure(need)}'
      '${name.isEmpty ? '' : ' of $name'}';
}

/// What the back-order rows say about the stock an approved order could not
/// be given, or null where every line was covered (D-UI-24, D-UI-48).
///
/// The server approves the order whatever the stock and leaves the shortfall
/// on back order, so approval itself is no sign of it -- and neither is the
/// approve response: a line's `reserved_quantity` is set to its whole
/// `reservable_quantity`, back order included, so the two never differ
/// (D-UI-48: 500 approved against 82 on hand said nothing, where a test fed
/// an invented `reserved_quantity` of 82 had passed). The shortfall as it
/// stands is the back-order report's: each row is one line of an open order,
/// with what it still owes (`requested_quantity`) and what of that the
/// warehouse cannot meet (`back_order_quantity`).
String? approvedShortfallNotice(Object? backOrders, String orderId) {
  if (backOrders is! List) return null;
  final List<String> short = <String>[];
  for (final Object? line in backOrders) {
    if (line is! Map || '${line['order_id']}' != orderId) continue;
    final String? stated = _shortLine(line);
    if (stated != null) short.add(stated);
  }
  if (short.isEmpty) return null;
  final String what = short.length == 1
      ? '${short.single} are not in stock and stay'
      : '${short.join('; ')} are not in stock and stay';
  return 'Approved. $what on back order.';
}

/// The steps of one sale whose lifecycle actions are plain
/// `POST /<resource>/{id}/<step>` calls.
DocumentStep<Json> _plainStep(
  ApiClient api, {
  required String resource,
  required String numberKey,
  required DocumentStatusGate gate,
  required String id,
  required String label,
  required IconData icon,
  required DocumentLifecycleAction action,
  required bool permitted,
  required String said,
}) =>
    DocumentStep<Json>(
      id: id,
      label: label,
      icon: icon,
      permitted: permitted,
      allows: (row) => gate.allows(action, '${row['status'] ?? ''}'),
      run: (context, row) async {
        await api.documentAction(resource, '${row['id']}', '/$id');
        return DocumentStepDone('${row[numberKey] ?? ''} $said', step: id);
      },
    );

bool _held(Json row) => row['is_on_hold'] == true;

/// Backlog 119: a document raised where approval is not a step of its own
/// is approved by whoever raised it, without the approve code. The server
/// makes the same test on `approval_step` and `created_by`.
bool Function(Json row) _ownUnstepped(PermissionService permissions) =>
    (Json row) {
      final String? me = permissions.userId;
      return row['approval_step'] == false &&
          me != null &&
          '${row['created_by'] ?? ''}' == me;
    };

/// A sales order's next steps: Approve, Hold or Release, Reserve again,
/// Cancel, Close.
List<DocumentStep<Json>> salesOrderSteps(
  ApiClient api,
  PermissionService permissions,
) {
  final bool approver = permissions.hasPermission('SALES_APPROVE');
  String number(Json row) => '${row['order_number'] ?? ''}';
  bool finished(Json row) => const {'CANCELLED', 'CLOSED'}
      .contains('${row['status'] ?? ''}'.toUpperCase());
  return [
    DocumentStep<Json>(
      id: 'approve',
      label: 'Approve',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & approve',
      permitted: approver,
      rowPermitted: _ownUnstepped(permissions),
      allows: (row) => DocumentStatusGate.salesOrder
          .allows(DocumentLifecycleAction.approve, '${row['status'] ?? ''}'),
      run: (context, row) => _approveSale(
        context,
        api,
        permissions,
        row: row,
        resource: 'sales-orders',
        document: 'SALES_ORDER',
        priceCheck: () => api.salesOrderPriceCheck('${row['id']}'),
        backOrders: true,
      ),
    ),
    // A hold is a flag, not a status: the order keeps where it had got to
    // and its stock stays reserved. The reason is required -- whoever hits
    // the refusal downstream has to know why.
    DocumentStep<Json>(
      id: 'hold',
      label: 'Hold',
      icon: Icons.pause_outlined,
      permitted: approver,
      allows: (row) => !_held(row) && !finished(row),
      run: (context, row) async {
        final String? reason = await askForReason(
          context,
          title: 'Hold ${number(row)}',
          explanation: 'Nothing is unwound. The order keeps its status and '
              'its stock stays reserved — a hold says "not yet", not '
              '"never". It cannot be dispatched until it is released.',
          confirmLabel: 'Hold',
        );
        if (reason == null) return null;
        await api.holdSalesOrder('${row['id']}', reason: reason);
        return DocumentStepDone('${number(row)} is on hold.', step: 'hold');
      },
    ),
    DocumentStep<Json>(
      id: 'release',
      label: 'Release',
      icon: Icons.play_arrow_outlined,
      forward: true,
      permitted: approver,
      allows: _held,
      run: (context, row) async {
        await api.releaseSalesOrder('${row['id']}');
        return DocumentStepDone('${number(row)} released.', step: 'release');
      },
    ),
    // STK-12: the order's stock hold lapsed unshipped.
    DocumentStep<Json>(
      id: 'reserve-again',
      label: 'Reserve again',
      icon: Icons.inventory_2_outlined,
      permitted: approver,
      allows: (row) => '${row['reservation_lapsed_at'] ?? ''}'.isNotEmpty,
      run: (context, row) async {
        await api.reserveSalesOrderAgain('${row['id']}');
        return DocumentStepDone(
          'Stock is held again for ${number(row)}.',
          step: 'reserve-again',
        );
      },
    ),
    _plainStep(
      api,
      resource: 'sales-orders',
      numberKey: 'order_number',
      gate: DocumentStatusGate.salesOrder,
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      action: DocumentLifecycleAction.cancel,
      permitted: permissions.hasPermission('SALES_CANCEL'),
      said: 'cancelled. Its stock is released.',
    ),
    _plainStep(
      api,
      resource: 'sales-orders',
      numberKey: 'order_number',
      gate: DocumentStatusGate.salesOrder,
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      action: DocumentLifecycleAction.close,
      permitted: approver,
      said: 'closed.',
    ),
  ];
}

/// A sales invoice's next steps: Approve, Cancel, Close.
List<DocumentStep<Json>> salesInvoiceSteps(
  ApiClient api,
  PermissionService permissions,
) {
  final bool approver = permissions.hasPermission('SALES_APPROVE');
  return [
    DocumentStep<Json>(
      id: 'approve',
      label: 'Approve',
      icon: Icons.check_circle_outline,
      forward: true,
      afterSave: 'Save & approve',
      permitted: approver,
      rowPermitted: _ownUnstepped(permissions),
      allows: (row) => DocumentStatusGate.salesInvoice
          .allows(DocumentLifecycleAction.approve, '${row['status'] ?? ''}'),
      run: (context, row) => _approveSale(
        context,
        api,
        permissions,
        row: row,
        resource: 'sales-invoices',
        document: 'SALES_INVOICE',
        priceCheck: () => api.salesInvoicePriceCheck('${row['id']}'),
      ),
    ),
    _plainStep(
      api,
      resource: 'sales-invoices',
      numberKey: 'invoice_number',
      gate: DocumentStatusGate.salesInvoice,
      id: 'cancel',
      label: 'Cancel',
      icon: Icons.cancel_outlined,
      action: DocumentLifecycleAction.cancel,
      permitted: permissions.hasPermission('SALES_CANCEL'),
      said: 'cancelled.',
    ),
    _plainStep(
      api,
      resource: 'sales-invoices',
      numberKey: 'invoice_number',
      gate: DocumentStatusGate.salesInvoice,
      id: 'close',
      label: 'Close',
      icon: Icons.lock_outline,
      action: DocumentLifecycleAction.close,
      permitted: approver,
      said: 'closed.',
    ),
  ];
}
