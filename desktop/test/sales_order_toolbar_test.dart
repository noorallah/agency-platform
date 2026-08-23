// Raising an order, and correcting one — from the orders screen itself.
//
// An order could only appear by converting a quotation, so a phone order had
// to be typed as a quotation and immediately accepted: two documents, and an
// acceptance the customer never gave. `POST /api/v1/sales-orders` had existed
// the whole time with nothing on the desktop calling it — and the orphan-route
// guard could not see it, because the generic `documentPage` /
// `documentAction` helpers shadow every two-segment sales route.
//
// What is worth pinning here is not that the buttons exist but that they are
// gated the way the server is: `SALES_CREATE` to raise one, `SALES_UPDATE` and
// a DRAFT to correct one. A button the server refuses is worse than no button.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _order({String status = 'DRAFT', String id = 'so-1'}) =>
    <String, dynamic>{
      'id': id,
      'order_number': 'SO-0001',
      'order_date': '2026-08-23',
      'reference_number': '',
      'status': status,
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
    };

class _OrdersApi extends ApiClient {
  _OrdersApi({this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;

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
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': rows.length, 'draft': rows.length},
      };
    }
    return <String, dynamic>{
      'data': rows,
      'pagination': <String, dynamic>{'total_records': rows.length},
    };
  }
}

Future<void> _pump(
  WidgetTester tester,
  _OrdersApi api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('so-toolbar-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesOrderManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

/// The enabled state of the button carrying [label].
bool _enabled(WidgetTester tester, String label) {
  final Finder button = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate((widget) => widget is ButtonStyleButton),
  );
  return (tester.widget(button.first) as ButtonStyleButton).onPressed != null;
}

void main() {
  testWidgets('an order can be raised without a quotation behind it',
      (tester) async {
    await _pump(tester, _OrdersApi(), const ['SALES_VIEW', 'SALES_CREATE']);

    expect(find.text('New Order'), findsOneWidget);
    expect(_enabled(tester, 'New Order'), isTrue);
  });

  testWidgets('somebody who may only read is offered neither', (tester) async {
    // A button the server refuses is worse than no button: it reads as a
    // permission the account has and produces a refusal on the press.
    await _pump(tester, _OrdersApi(rows: [_order()]), const ['SALES_VIEW']);

    expect(find.text('New Order'), findsNothing);
    expect(find.text('Edit'), findsNothing);
  });

  testWidgets('only a draft can be corrected', (tester) async {
    // The service refuses an update to anything past DRAFT, and it is right
    // to: an approved order is what the warehouse picks against and what
    // credit was committed on.
    await _pump(
      tester,
      _OrdersApi(rows: [_order(status: 'APPROVED')]),
      const ['SALES_VIEW', 'SALES_UPDATE'],
    );

    expect(find.text('Edit'), findsOneWidget);
    expect(_enabled(tester, 'Edit'), isFalse);
  });

  testWidgets('a draft is selected and Edit comes alive', (tester) async {
    await _pump(
      tester,
      _OrdersApi(rows: [_order()]),
      const ['SALES_VIEW', 'SALES_UPDATE'],
    );

    expect(_enabled(tester, 'Edit'), isTrue);
  });
}
