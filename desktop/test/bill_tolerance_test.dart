// Bill matching tolerances (BUY-10): the buying-stages dialog sends the two
// limits (a value, or null once cleared), and an approval the server refuses
// for pricing a bill past its order says so, singly and in a bulk result.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_management_page.dart';
import 'package:agency_desktop/ui/purchases/purchase_workflow_settings_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _refusal = 'Line 1 is priced 12.00% over its order, past the '
    '5.00% allowed. Approving needs the over-tolerance permission.';

PermissionService _holder(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{'permissions': codes})))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.signature');
}

class _SettingsApi extends ApiClient {
  _SettingsApi({this.percent, this.amount})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? percent;
  final String? amount;
  final List<Json> saved = [];

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(<String, dynamic>{
        'purchase_order_stage': true,
        'goods_receipt_stage': true,
        'bill_price_tolerance_percent': percent,
        'bill_tolerance_amount': amount,
        'is_configured': true,
      });

  @override
  Future<PurchaseWorkflowSettings> updatePurchaseWorkflowSettings(
    PurchaseWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

Future<void> _openDialog(WidgetTester tester, _SettingsApi api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseWorkflowSettingsDialog(
          api: api,
          permissions: _holder(const ['PURCHASE_MANAGE_SETTINGS']),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

class _BillsApi extends ApiClient {
  _BillsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json _row(int n) => <String, dynamic>{
        'id': 'doc-$n',
        'invoice_number': 'PB-000$n',
        'invoice_date': '2026-10-01',
        'status': 'DRAFT',
        'grand_total': '1000.00',
        'vendor_name': 'Vendor $n',
        'version': n,
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
    if (method == 'POST' && path.endsWith('/approve')) {
      throw const ApiException(_refusal);
    }
    if (method == 'POST' && path.endsWith('/bulk-approve')) {
      final List<Json> items = (body!['items'] as List).cast<Json>();
      return <String, dynamic>{
        'data': <String, dynamic>{
          'done': 0,
          'refused': items.length,
          'results': [
            for (final Json item in items)
              <String, dynamic>{
                'id': item['id'],
                'number': 'NUM-${item['id']}',
                'outcome': 'REFUSED',
                'message': _refusal,
              },
          ],
        },
      };
    }
    if (method == 'GET' && path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': 2, 'draft': 2},
      };
    }
    if (method == 'GET' && path == '/api/v1/purchase-invoices') {
      return <String, dynamic>{
        'data': [_row(1), _row(2)],
        'pagination': <String, dynamic>{'total_records': 2},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

Future<void> _openBills(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('bill-tol-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceManagementPage(
          api: _BillsApi(),
          preferences: DesktopPreferencesService(directory: temp),
          permissions: _holder(const ['PURCHASE_VIEW', 'PURCHASE_APPROVE']),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('both tolerances are sent as typed', (tester) async {
    final _SettingsApi api = _SettingsApi();
    await _openDialog(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey('bill-tolerance-percent')), '5');
    await tester.enterText(
        find.byKey(const ValueKey('bill-tolerance-amount')), '250.5');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved.single['bill_price_tolerance_percent'], 5.0);
    expect(api.saved.single['bill_tolerance_amount'], 250.5);
  });

  testWidgets('clearing a loaded tolerance sends null', (tester) async {
    final _SettingsApi api = _SettingsApi(percent: '5.00', amount: '100.00');
    await _openDialog(tester, api);

    expect(find.text('5'), findsOneWidget);
    expect(find.text('100'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('bill-tolerance-percent')), '');
    await tester.enterText(
        find.byKey(const ValueKey('bill-tolerance-amount')), '');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved.single.containsKey('bill_price_tolerance_percent'),
        isTrue);
    expect(api.saved.single['bill_price_tolerance_percent'], isNull);
    expect(api.saved.single['bill_tolerance_amount'], isNull);
  });

  testWidgets('a percentage past 100 is refused before it is sent',
      (tester) async {
    final _SettingsApi api = _SettingsApi();
    await _openDialog(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey('bill-tolerance-percent')), '150');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.textContaining('from 0 to 100'), findsOneWidget);
    expect(api.saved, isEmpty);
  });

  testWidgets('a bulk approval reports the tolerance refusal per row',
      (tester) async {
    await _openBills(tester);

    await tester.tap(find.byType(Checkbox).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Checkbox).at(2));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Approve selected'));
    await tester.pumpAndSettle();

    expect(find.text('Approved 0 of 2'), findsOneWidget);
    expect(find.textContaining('past the 5.00% allowed'), findsNWidgets(2));
  });
}
