// The one mistake this screen exists to prevent: a proforma read as a bill.
//
// No input credit can be claimed against it and no tax is payable on it.
// Somebody eventually prints one and hands it to an accounts clerk, so the
// words have to travel with the document.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/proforma_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show ColumnsButton, Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/server_pricing.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const ['PROFORMA_VIEW', 'PROFORMA_MANAGE'],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

class _ProformaApi extends ApiClient {
  _ProformaApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = <String>[];
  Json? raised;

  /// A sales order as the server answers it, offered in place of the
  /// hand-written one when a test checks the screen against it
  /// (`support/server_pricing.dart`).
  Json? serverOrder;

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
    requested.add('$method $path');
    if (path == '/api/v1/sales-orders') {
      return <String, dynamic>{
        'data': [serverOrder ?? _approvedOrder()],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/products') {
      return <String, dynamic>{
        'data': [
          {'id': 'p-1', 'code': 'TP', 'name': 'Toothpaste 150g'},
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (method == 'POST' && path == '/api/v1/proforma-invoices') {
      raised = body;
      return <String, dynamic>{'data': _proforma()};
    }
    if (path.contains('/issue') || path.contains('/cancel')) {
      return <String, dynamic>{'data': rows.first};
    }
    return <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };
  }
}

Json _proforma({String status = 'DRAFT'}) => <String, dynamic>{
      'id': 'pf-1',
      'proforma_number': 'PI-2026-2027-000001',
      'proforma_date': '2026-06-10',
      'valid_until': '2026-07-10',
      'status': status,
      'customer_id': 'cust-1',
      'customer_name': 'Kumar Stores',
      'branch_id': 'br-1',
      'sales_order_id': 'so-1',
      'sales_order_number': 'SO-2026-2027-000004',
      'payment_terms': '30 days net',
      'delivery_terms': 'Ex works',
      'line_discount_total': '100.00',
      'bill_discount_amount': '50.00',
      'subtotal': '850.00',
      'tax_total': '153.00',
      'grand_total': '1003.00',
      'is_tax_invoice': false,
      'supersedes_id': null,
      'version': 1,
      'lines': <Json>[
        <String, dynamic>{
          'id': 'l-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_name': 'Toothpaste 150g',
          'quantity': '10.0000',
          'free_quantity': '1.0000',
          'unit_price': '100.0000',
          'discount_percent': '10.0000',
          'discount_amount': '100.0000',
          'bill_discount_amount': '50.0000',
          'gross_amount': '1000.0000',
          'tax_amount': '153.0000',
          'net_amount': '1003.0000',
        },
      ],
    };

/// An approved order of ten toothpaste at 100, 10% off, 18% tax.
Json _approvedOrder() => <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-2026-2027-000004',
      'order_date': '2026-06-01',
      'customer_name': 'Kumar Stores',
      'status': 'APPROVED',
      'subtotal': '900.00',
      'tax_total': '162.00',
      'grand_total': '1062.00',
      'lines': <Json>[
        <String, dynamic>{
          'line_number': 1,
          'product_id': 'p-1',
          'quantity': '10.0000',
          'free_quantity': '0',
          'unit_price': '100.0000',
          'gross_amount': '1000.0000',
          'discount_amount': '100.0000',
          'bill_discount_amount': '0',
          'tax_amount': '162.0000',
        },
      ],
    };

Future<void> _pump(
  WidgetTester tester,
  _ProformaApi api, {
  PermissionService? permissions,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ProformaPage(
        api: api,
        preferences: DesktopPreferencesService(
          directory: Directory.systemTemp.createTempSync('proforma'),
        ),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  test('an order in the Raise dialog says whose it is', () {
    expect(
      proformaOrderLabel(<String, dynamic>{
        'order_number': 'SO-2026-2027-000020',
        'customer_name': 'Vijaya Super Stores',
        'grand_total': '1159.7040',
      }),
      'SO-2026-2027-000020 — Vijaya Super Stores — 1159.7040',
    );
    expect(
      proformaOrderLabel(<String, dynamic>{
        'order_number': 'SO-1',
        'grand_total': '10',
      }),
      'SO-1 — 10',
    );
  });

  testWidgets('the workspace says it is not a tax invoice', (tester) async {
    await _pump(tester, _ProformaApi(rows: <Json>[_proforma()]));

    expect(find.textContaining('not a tax invoice'), findsOneWidget);
  });

  testWidgets('so does the document itself, once one is open', (tester) async {
    await _pump(tester, _ProformaApi(rows: <Json>[_proforma()]));
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    // On the detail pane as well, because that is what gets printed.
    expect(find.textContaining('no input tax credit'), findsOneWidget);
  });

  testWidgets('free goods are stated on the line', (tester) async {
    await _pump(tester, _ProformaApi(rows: <Json>[_proforma()]));
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    // A document that dropped them would understate what is being shipped.
    expect(find.textContaining('+1.00 free'), findsOneWidget);
  });

  testWidgets('the order\'s other charges are stated above the total',
      (tester) async {
    // D-SELL-16: the total now carries the order's header charges and
    // round-off, so the document says what they came to.
    final Json row = _proforma()
      ..['other_charges'] = '24.80'
      ..['grand_total'] = '1027.80';
    await _pump(tester, _ProformaApi(rows: <Json>[row]));
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    expect(find.text('Other charges'), findsOneWidget);
    expect(find.text('24.80'), findsOneWidget);
  });

  testWidgets('no charges, no line for them', (tester) async {
    await _pump(tester, _ProformaApi(rows: <Json>[_proforma()]));
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    expect(find.text('Other charges'), findsNothing);
  });

  testWidgets('an issued proforma cannot be issued again', (tester) async {
    await _pump(tester, _ProformaApi(rows: <Json>[_proforma(status: 'ISSUED')]));
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    final Finder issue = find.widgetWithText(FilledButton, 'Issue');
    expect(tester.widget<FilledButton>(issue).onPressed, isNull);
  });

  testWidgets('a cancelled one cannot be withdrawn twice', (tester) async {
    await _pump(
      tester,
      _ProformaApi(rows: <Json>[_proforma(status: 'CANCELLED')]),
    );
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    final Finder withdraw = find.widgetWithText(OutlinedButton, 'Withdraw');
    expect(tester.widget<OutlinedButton>(withdraw).onPressed, isNull);
  });

  testWidgets('someone who cannot manage cannot issue', (tester) async {
    await _pump(
      tester,
      _ProformaApi(rows: <Json>[_proforma()]),
      permissions: _permissions(perms: const <String>['PROFORMA_VIEW']),
    );
    await tester.tap(find.textContaining('PI-2026-2027-000001'));
    await tester.pumpAndSettle();

    final Finder issue = find.widgetWithText(FilledButton, 'Issue');
    expect(tester.widget<FilledButton>(issue).onPressed, isNull);
  });

  testWidgets('someone without the view permission sees nothing',
      (tester) async {
    await _pump(
      tester,
      _ProformaApi(rows: <Json>[_proforma()]),
      permissions: _permissions(perms: const <String>['CUSTOMER_VIEW']),
    );

    expect(find.textContaining('view proforma permission'), findsOneWidget);
    expect(find.textContaining('PI-2026'), findsNothing);
  });

  // D-UI-97: the lines a proforma states, against the server's own pricing
  // of an order with a line discount, a bill discount and a delivery charge.
  testWidgets('phase 2 shows each order line as the server priced it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final Json order = withIds(
      serverPricing('sales_order_preview')['order'] as Json,
      {'product_id': 'p-1', 'status': 'APPROVED'},
    );
    final _ProformaApi api = _ProformaApi()..serverOrder = order;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ProformaPage(
            api: api,
            preferences: DesktopPreferencesService(
              directory: Directory.systemTemp.createTempSync('proforma'),
            ),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('New').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('proforma-order')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('${order['order_number']}').last);
    await tester.pumpAndSettle();

    expectLinesReconcile(tester, document: order, rowKey: 'proforma-line-');
    // 500.00 less 10%, less 5% of the rest, plus 40.00 delivery: 467.50
    // taxable, 84.15 tax at 18%, 551.65 in all.
    expect(find.text('467.50'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phase 2 raises on one screen showing the order it states',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _ProformaApi api = _ProformaApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ProformaPage(
            api: api,
            preferences: DesktopPreferencesService(
              directory: Directory.systemTemp.createTempSync('proforma'),
            ),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('New').last);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No order until one is chosen: Raise with nothing touched raises
    // nothing and says what is missing (D-UI-66).
    expect(find.text('Toothpaste 150g'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('proforma-raise')));
    await tester.pumpAndSettle();
    expect(api.raised, isNull);
    expect(
      find.text('Choose the sales order this proforma states.'),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('proforma-order')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('SO-2026-2027-000004').last);
    await tester.pumpAndSettle();

    // The order's line, named from the products, at what the order agreed.
    expect(find.text('Toothpaste 150g'), findsWidgets);
    expect(find.text('900.00'), findsWidgets);
    expect(
      find.textContaining('1,062.00', findRichText: true),
      findsWidgets,
    );

    await tester.tap(find.byKey(const ValueKey('proforma-raise')));
    await tester.pumpAndSettle();
    expect(api.raised?['sales_order_id'], 'so-1');
    expect(api.raised?.containsKey('valid_until'), isFalse);
  });

  // Phase 2 (owner, 2026-09-27): a full-width grid with Columns, the
  // proforma read on a double-click rather than in a side pane.
  group('phase 2 grid', () {
    Future<void> open(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: ProformaPage(
            api: _ProformaApi(rows: <Json>[_proforma()]),
            preferences: DesktopPreferencesService(
              directory: Directory.systemTemp.createTempSync('proforma'),
            ),
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
    }

    testWidgets('a grid, no side pane, and the bar names the pick',
        (tester) async {
      await open(tester);
      expect(find.byType(ColumnsButton), findsOneWidget);
      expect(find.text('SO-2026-2027-000004'), findsOneWidget);

      await tester.tap(find.text('PI-2026-2027-000001').first);
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
      expect(find.textContaining('Kumar Stores ·'), findsOneWidget);
      // A document made to be handed over can be printed (D-UI-71).
      expect(find.text('Print'), findsOneWidget);
      // The side pane is gone: its warning is not on the page.
      expect(find.textContaining('Not a tax invoice'), findsNothing);

      tester.view.physicalSize = const Size(1366, 768);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('double-clicking a proforma reads it', (tester) async {
      await open(tester);
      final Finder row = find.text('PI-2026-2027-000001').first;
      await tester.tap(row);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(row);
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsOneWidget);
      expect(find.textContaining('Not a tax invoice'), findsOneWidget);
    });
  });
}
