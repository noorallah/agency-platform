// The one mistake this screen exists to prevent: a proforma read as a bill.
//
// No input credit can be claimed against it and no tax is payable on it.
// Somebody eventually prints one and hands it to an accounts clerk, so the
// words have to travel with the document.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/proforma_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

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
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
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
}
