// Bulk approve and bulk cancel on the Sales Orders and Purchase Orders lists
// (backlog 56 A): tick several rows, act on them together, and read what the
// server did with each -- some rows can be refused while the others go through.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/bulk_action.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/purchase_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _salesRow(int n, {String status = 'DRAFT'}) => <String, dynamic>{
      'id': 'so-$n',
      'order_number': 'SO-000$n',
      'order_date': '2026-08-23',
      'status': status,
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
      'version': n + 6,
    };

Json _purchaseRow(int n) => <String, dynamic>{
      'id': 'po-$n',
      'po_number': 'PO-000$n',
      'purchase_date': '2026-08-23',
      'status': 'SUBMITTED',
      'grand_total': '500.00',
    };

/// Serves a list of rows and records each bulk call. The second row of every
/// approve is refused, so the result dialog has something to name.
class _BulkApi extends ApiClient {
  _BulkApi({required this.listPath, required this.rows})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String listPath;
  final List<Json> rows;

  /// Every bulk call: its path and body.
  final List<(String, Json)> bulkCalls = <(String, Json)>[];

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
    if (method == 'POST' && path.contains('/bulk-')) {
      bulkCalls.add((path, body!));
      final List<Json> items = (body['items'] as List).cast<Json>();
      final bool cancel = path.endsWith('bulk-cancel');
      return <String, dynamic>{
        'data': <String, dynamic>{
          'done': cancel ? items.length : 1,
          'refused': cancel ? 0 : items.length - 1,
          'results': [
            for (int i = 0; i < items.length; i++)
              <String, dynamic>{
                'id': items[i]['id'],
                'number': 'NUM-${items[i]['id']}',
                'outcome': cancel || i == 0 ? 'DONE' : 'REFUSED',
                'message': cancel || i == 0 ? null : 'Already approved.',
              },
          ],
        },
      };
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': rows.length, 'draft': rows.length},
      };
    }
    if (path == listPath) {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': <dynamic>[]};
  }
}

Future<void> _pump(WidgetTester tester, Widget page) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: Phase2Scope(child: page)),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpSales(
  WidgetTester tester,
  _BulkApi api,
  List<String> codes,
) async {
  final Directory temp = Directory.systemTemp.createTempSync('bulk-so-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await _pump(
    tester,
    SalesOrderManagementPage(
      api: api,
      preferences: DesktopPreferencesService(directory: temp),
      permissions: _permissions(codes),
      hasActiveFirm: true,
    ),
  );
}

Future<void> _pumpPurchases(
  WidgetTester tester,
  _BulkApi api,
  List<String> codes,
) async {
  final Directory temp = Directory.systemTemp.createTempSync('bulk-po-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await _pump(
    tester,
    PurchaseManagementPage(
      api: api,
      preferences: DesktopPreferencesService(directory: temp),
      permissions: _permissions(codes),
      hasActiveFirm: true,
      section: PurchaseSection.purchaseOrders,
    ),
  );
}

/// The selection bar's own text -- the status bar also counts what is ticked.
Finder _barSays(String text) => find.descendant(
      of: find.byKey(const ValueKey('selection-bar')),
      matching: find.textContaining(text, findRichText: true),
    );

/// Tick the first [count] data rows (the header's own box is index 0).
Future<void> _tick(WidgetTester tester, int count) async {
  for (int i = 1; i <= count; i++) {
    await tester.tap(find.byType(Checkbox).at(i));
    await tester.pumpAndSettle();
  }
}

void main() {
  const List<String> salesCodes = <String>[
    'SALES_VIEW',
    'SALES_APPROVE',
    'SALES_CANCEL',
  ];
  const List<String> purchaseCodes = <String>[
    'PURCHASE_VIEW',
    'PURCHASE_APPROVE',
    'PURCHASE_CANCEL',
  ];

  test('a bulk result reads the server\'s rows', () {
    final BulkActionResult result = BulkActionResult.fromJson(<String, dynamic>{
      'done': 1,
      'refused': 1,
      'results': [
        {'id': 'a', 'number': 'A-1', 'outcome': 'DONE', 'message': null},
        {'id': 'b', 'number': null, 'outcome': 'REFUSED', 'message': 'No.'},
      ],
    });
    expect(result.refusedRows.single.id, 'b');
    expect(result.refusedRows.single.message, 'No.');
  });

  testWidgets('sales: approve selected sends both ids and lists the refusal',
      (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/sales-orders',
      rows: [_salesRow(1), _salesRow(2), _salesRow(3)],
    );
    await _pumpSales(tester, api, salesCodes);

    // One row ticked is still a single-row selection: no bulk actions yet.
    await _tick(tester, 1);
    expect(find.text('Approve selected'), findsNothing);

    await tester.tap(find.byType(Checkbox).at(2));
    await tester.pumpAndSettle();
    expect(_barSays('2 selected'), findsOneWidget);
    expect(find.text('Cancel selected'), findsOneWidget);

    await tester.tap(find.text('Approve selected'));
    await tester.pumpAndSettle();

    expect(api.bulkCalls, hasLength(1));
    expect(api.bulkCalls.single.$1, '/api/v1/sales-orders/bulk-approve');
    final List<Json> items =
        (api.bulkCalls.single.$2['items'] as List).cast<Json>();
    expect(items.map((item) => item['id']).toSet(), {'so-1', 'so-2'});
    // The list row's version rides along.
    expect(items.every((item) => item['version'] != null), isTrue);
    expect(api.bulkCalls.single.$2.containsKey('reason'), isFalse);

    expect(find.text('Approved 1 of 2'), findsOneWidget);
    expect(find.textContaining('Already approved.'), findsOneWidget);

    // Retry sends only the refused id, with no version.
    await tester.tap(find.byKey(const ValueKey('bulk-retry')));
    await tester.pumpAndSettle();
    expect(api.bulkCalls, hasLength(2));
    final List<Json> retried =
        (api.bulkCalls.last.$2['items'] as List).cast<Json>();
    expect(retried, hasLength(1));
    expect(retried.single.containsKey('version'), isFalse);

    await tester.tap(find.byKey(const ValueKey('bulk-close')));
    await tester.pumpAndSettle();
    expect(_barSays('2 selected'), findsNothing);
  });

  testWidgets('sales: cancel selected sends the typed reason', (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/sales-orders',
      rows: [_salesRow(1), _salesRow(2)],
    );
    await _pumpSales(tester, api, salesCodes);
    await _tick(tester, 2);

    await tester.tap(find.text('Cancel selected'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Customer withdrew.');
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel orders'));
    await tester.pumpAndSettle();

    expect(api.bulkCalls.single.$1, '/api/v1/sales-orders/bulk-cancel');
    expect(api.bulkCalls.single.$2['reason'], 'Customer withdrew.');
    expect(find.text('Cancelled 2 of 2'), findsOneWidget);
  });

  testWidgets('sales: a cancel with no reason is not sent', (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/sales-orders',
      rows: [_salesRow(1), _salesRow(2)],
    );
    await _pumpSales(tester, api, salesCodes);
    await _tick(tester, 2);

    await tester.tap(find.text('Cancel selected'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel orders'));
    await tester.pumpAndSettle();

    expect(api.bulkCalls, isEmpty);
  });

  testWidgets('sales: each bulk action needs its own permission',
      (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/sales-orders',
      rows: [_salesRow(1), _salesRow(2)],
    );
    await _pumpSales(tester, api, const ['SALES_VIEW', 'SALES_APPROVE']);
    await _tick(tester, 2);

    expect(find.text('Approve selected'), findsOneWidget);
    expect(find.text('Cancel selected'), findsNothing);
  });

  testWidgets('purchases: approve selected sends both ids', (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/purchases',
      rows: [_purchaseRow(1), _purchaseRow(2), _purchaseRow(3)],
    );
    await _pumpPurchases(tester, api, purchaseCodes);
    await _tick(tester, 2);

    expect(_barSays('2 selected'), findsOneWidget);
    await tester.tap(find.text('Approve selected'));
    await tester.pumpAndSettle();

    expect(api.bulkCalls.single.$1, '/api/v1/purchases/bulk-approve');
    final List<Json> items =
        (api.bulkCalls.single.$2['items'] as List).cast<Json>();
    expect(items.map((item) => item['id']).toSet(), {'po-1', 'po-2'});
    expect(find.text('Approved 1 of 2'), findsOneWidget);
    expect(find.textContaining('Already approved.'), findsOneWidget);
  });

  testWidgets('purchases: cancel selected sends the typed reason',
      (tester) async {
    final _BulkApi api = _BulkApi(
      listPath: '/api/v1/purchases',
      rows: [_purchaseRow(1), _purchaseRow(2)],
    );
    await _pumpPurchases(tester, api, purchaseCodes);
    await _tick(tester, 2);

    await tester.tap(find.text('Cancel selected'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Wrong supplier.');
    await tester.tap(find.widgetWithText(FilledButton, 'Cancel orders'));
    await tester.pumpAndSettle();

    expect(api.bulkCalls.single.$1, '/api/v1/purchases/bulk-cancel');
    expect(api.bulkCalls.single.$2['reason'], 'Wrong supplier.');
  });
}
