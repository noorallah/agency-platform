// What a purchase return comes back as (backlog 69.7): Credit, Replacement or
// Refund. The editor sends it, the list shows it and can change it, and a
// credit whose return came back as a refund can have the supplier's money
// recorded against it and reversed.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/ui/finance/supplier_credit_refunds.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_editor_dialog.dart';
import 'package:agency_desktop/ui/purchase_returns/purchase_return_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'roles': <String>['user'], 'permissions': codes})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

/// Answers every route this file touches at the request level, so the real
/// client methods build the paths and bodies the assertions read.
class _OutcomeApi extends ApiClient {
  _OutcomeApi({this.returnStatus = 'DRAFT', this.outcome = 'CREDIT'})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String returnStatus;
  String outcome;
  final List<(String, String, Json?)> calls = <(String, String, Json?)>[];

  Json? get lastBody => calls.last.$3;

  Json get _returnRow => <String, dynamic>{
        'id': 'pr-1',
        'return_number': 'PR-2026-000001',
        'return_date': '2026-09-19',
        'status': returnStatus,
        'grand_total': '236.00',
        'vendor_name': 'Fixture Supplier',
        'outcome': outcome,
      };

  /// The refunds on pr-1, and whether the first has been taken back.
  bool refundReversed = false;
  String? refusal;

  /// Adds a debit note's credit (A4) to what the credits list answers.
  bool withDebitNote = false;

  Json _refund() => <String, dynamic>{
        'id': 'rf-1',
        'purchase_return_id': 'pr-1',
        'vendor_id': 'v-1',
        'refunded_on': '2026-09-20',
        'amount': '100.00',
        'method': 'BANK',
        'reference': 'NEFT-1',
        'status': refundReversed ? 'REVERSED' : 'POSTED',
        'journal_entry_id': 'je-1',
        'reversal_reason': refundReversed ? 'Keyed twice' : null,
      };

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
    int? expectedVersion,
  }) async {
    calls.add((method, path, body));
    if (path.endsWith('/outcome')) {
      outcome = body!['outcome'] as String;
      return <String, dynamic>{'data': _returnRow};
    }
    if (path == '/api/v1/purchase-returns' && method == 'GET') {
      return <String, dynamic>{
        'data': [_returnRow],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/purchase-returns' && method == 'POST') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'pr-1',
          'return_number': 'PR-1',
          'status': 'DRAFT',
        },
      };
    }
    if (path == '/api/v1/payments/supplier-credits') {
      return <String, dynamic>{
        'data': [
          <String, dynamic>{
            'source_id': 'pr-1',
            'source_type': 'PURCHASE_RETURN',
            'purchase_return_id': 'pr-1',
            'return_number': 'PR-2026-000001',
            'return_date': '2026-09-19',
            'credit_amount': '236.00',
            'applied_amount': '0.00',
            'refunded_amount': '100.00',
            'available_amount': '136.00',
            'outcome': 'REFUND',
            'applied_to': <String>[],
          },
          <String, dynamic>{
            'source_id': 'pr-2',
            'source_type': 'PURCHASE_RETURN',
            'purchase_return_id': 'pr-2',
            'return_number': 'PR-2026-000002',
            'return_date': '2026-09-21',
            'credit_amount': '50.00',
            'applied_amount': '0.00',
            'available_amount': '50.00',
            'applied_to': <String>[],
          },
          if (withDebitNote)
            <String, dynamic>{
              'source_id': 'dn-1',
              'source_type': 'DEBIT_NOTE',
              'purchase_return_id': null,
              'debit_note_id': 'dn-1',
              'return_number': 'DN-2026-000001',
              'return_date': '2026-09-22',
              'credit_amount': '40.00',
              'applied_amount': '0.00',
              'available_amount': '40.00',
              'outcome': 'CREDIT',
              'applied_to': <String>[],
            },
        ],
      };
    }
    if (path.endsWith('/refunds') && method == 'POST') {
      if (refusal != null) {
        throw ApiException(refusal!, statusCode: 422);
      }
      return <String, dynamic>{'data': _refund()};
    }
    if (path.endsWith('/refunds')) {
      return <String, dynamic>{
        'data': [_refund()],
      };
    }
    if (path.endsWith('/reverse')) {
      refundReversed = true;
      return <String, dynamic>{'data': _refund()};
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Amoxicillin 500mg',
          'accepted_quantity': '20',
          'unit_price': '25',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'batch_number': '',
        },
      ],
    });

Future<void> _openEditor(WidgetTester tester, _OutcomeApi api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseReturnEditorDialog(
          api: api,
          receipts: [_receipt()],
          products: [
            Product.fromJson({
              'id': 'prod-1',
              'code': 'SKU-1',
              'name': 'Amoxicillin 500mg',
            }),
          ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(DropdownButtonFormField<String>).first);
  await tester.pumpAndSettle();
  await tester.tap(find.text('GRN-2026-000001 • 2026-08-10').last);
  await tester.pumpAndSettle();
}

Future<void> _openList(WidgetTester tester, _OutcomeApi api) async {
  tester.view.physicalSize = const Size(1600, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('pr-outcome');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseReturnManagementPage(
          api: api,
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _permissions(['PURCHASE_VIEW', 'PURCHASE_UPDATE']),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openCredits(WidgetTester tester, _OutcomeApi api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<void>(
            context: context,
            builder: (_) => SupplierCreditsDialog(
              api: api,
              vendorId: 'v-1',
              vendorName: 'Fixture Supplier',
              canManage: true,
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a new return sends Credit unless another outcome is chosen',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi();
    await _openEditor(tester, api);

    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();
    expect(api.calls.last.$3!['outcome'], 'CREDIT');
  });

  testWidgets('the outcome chosen in the editor is sent on create',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi();
    await _openEditor(tester, api);

    await tester.tap(find.byKey(const ValueKey('purchase-return-outcome')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Refund').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save Return'));
    await tester.pumpAndSettle();

    final (String, String, Json?) post =
        api.calls.lastWhere((call) => call.$1 == 'POST');
    expect(post.$2, '/api/v1/purchase-returns');
    expect(post.$3!['outcome'], 'REFUND');
  });

  testWidgets('the list shows the outcome and Change outcome calls the server',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi(outcome: 'CREDIT');
    await _openList(tester, api);

    expect(find.text('Outcome'), findsWidgets);
    expect(find.text('Credit'), findsWidgets);

    await tester.tap(find.text('PR-2026-000001'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-change-outcome')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('outcome-REFUND')));
    await tester.pumpAndSettle();

    final (String, String, Json?) post =
        api.calls.lastWhere((call) => call.$1 == 'POST');
    expect(post.$2, '/api/v1/purchase-returns/pr-1/outcome');
    expect(post.$3, <String, dynamic>{'outcome': 'REFUND'});
    expect(find.text('Refund'), findsWidgets);
  });

  testWidgets('a cancelled return cannot have its outcome changed',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi(returnStatus: 'CANCELLED');
    await _openList(tester, api);

    await tester.tap(find.text('PR-2026-000001'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    // The bar is up for the row, and offers no way to change a cancelled
    // return's outcome.
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('selection-change-outcome')),
      findsNothing,
    );
  });

  testWidgets('Record refund is offered only where the return is a refund',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi();
    await _openCredits(tester, api);

    expect(find.textContaining('Refunded 100.00'), findsOneWidget);
    expect(find.textContaining('Available 136.00'), findsOneWidget);
    // One credit came back as a refund, the other as the default credit.
    expect(find.text('Record refund'), findsOneWidget);
    expect(find.text('Refunds'), findsNWidgets(2));
  });

  testWidgets('a debit note credit is labelled and offers a refund',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi()..withDebitNote = true;
    await _openCredits(tester, api);

    expect(find.textContaining('Debit note DN-2026-000001'), findsOneWidget);
    expect(find.textContaining('Return PR-2026-000001'), findsOneWidget);
    // The refund-outcome return plus the debit note; the plain-credit
    // return still offers none.
    expect(find.text('Record refund'), findsNWidgets(2));

    await tester.ensureVisible(find.text('Record refund').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Record refund').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('supplier-refund-amount')),
      '40.00',
    );
    await tester.tap(find.byKey(const ValueKey('supplier-refund-save')));
    await tester.pumpAndSettle();

    final (String, String, Json?) post = api.calls.lastWhere(
      (call) => call.$1 == 'POST' && call.$2.endsWith('/refunds'),
    );
    expect(post.$2, '/api/v1/payments/supplier-credits/dn-1/refunds');
  });

  testWidgets('Record refund posts exactly the keys the server declares',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi();
    await _openCredits(tester, api);

    await tester.tap(find.text('Record refund'));
    await tester.pumpAndSettle();
    expect(find.text('up to 136.00'), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey('supplier-refund-amount')),
      '100.00',
    );
    await tester.enterText(
      find.byKey(const ValueKey('supplier-refund-reference')),
      'NEFT-1',
    );
    await tester.tap(find.byKey(const ValueKey('supplier-refund-save')));
    await tester.pumpAndSettle();

    final (String, String, Json?) post = api.calls.lastWhere(
      (call) => call.$1 == 'POST' && call.$2.endsWith('/refunds'),
    );
    expect(post.$2, '/api/v1/payments/supplier-credits/pr-1/refunds');
    final Json body = post.$3!;
    expect(body.keys.toSet(), {
      'amount',
      'refunded_on',
      'method',
      'reference',
    });
    expect(body['amount'], '100.00');
    expect(body['method'], 'BANK');
    expect(body['reference'], 'NEFT-1');
    expect(body['refunded_on'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
    // Closed on success.
    expect(find.byKey(const ValueKey('supplier-refund-save')), findsNothing);
  });

  testWidgets('a refused refund stays open with the server message',
      (tester) async {
    final _OutcomeApi api = _OutcomeApi()
      ..refusal = 'The refund is more than the credit available.';
    await _openCredits(tester, api);

    await tester.tap(find.text('Record refund'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('supplier-refund-amount')),
      '900',
    );
    await tester.tap(find.byKey(const ValueKey('supplier-refund-save')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('supplier-refund-save')), findsOneWidget);
    expect(
      find.text('The refund is more than the credit available.'),
      findsOneWidget,
    );
    expect(
      tester
          .widget<TextField>(
              find.byKey(const ValueKey('supplier-refund-amount')))
          .controller!
          .text,
      '900',
    );
  });

  testWidgets('Reverse asks a reason and posts it', (tester) async {
    final _OutcomeApi api = _OutcomeApi();
    await _openCredits(tester, api);

    await tester.tap(find.text('Refunds').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('NEFT-1'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Reverse'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Keyed twice');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Reverse'));
    await tester.pumpAndSettle();

    final (String, String, Json?) post =
        api.calls.lastWhere((call) => call.$2.endsWith('/reverse'));
    expect(post.$2, '/api/v1/payments/supplier-credits/refunds/rf-1/reverse');
    expect(post.$3, <String, dynamic>{'reason': 'Keyed twice'});
    // Reloaded: the row is now reversed and offers no second Reverse.
    expect(find.widgetWithText(TextButton, 'Reverse'), findsNothing);
    expect(find.textContaining('Reversed because Keyed twice'), findsOneWidget);
  });

  test('a credit that names no outcome is a plain credit', () {
    final SupplierCredit credit = SupplierCredit.fromJson({
      'purchase_return_id': 'pr-9',
      'return_number': 'PR-9',
      'return_date': '2026-09-19',
      'credit_amount': '10.00',
      'applied_amount': '0.00',
      'available_amount': '10.00',
    });
    expect(credit.outcome, 'CREDIT');
    expect(credit.isRefundOutcome, isFalse);
    expect(credit.refundedAmount, '0.00');
  });
}
