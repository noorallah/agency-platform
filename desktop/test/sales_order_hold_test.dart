// Holding an order from the orders screen.
//
// A hold is a flag beside the status, not a status of its own, and the screen
// has to reflect that: the button reads Hold or Release depending on where the
// order is, and a held order must not look identical to a live one in the list.

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

Json _order({
  String status = 'APPROVED',
  bool onHold = false,
  String? holdReason,
}) =>
    <String, dynamic>{
      'id': 'so-1',
      'order_number': 'SO-0001',
      'order_date': '2026-08-23',
      'reference_number': '',
      'status': status,
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
      'is_on_hold': onHold,
      'hold_reason': holdReason,
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
  final List<String> posted = <String>[];
  Json? sentBody;

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
    if (method == 'POST') {
      posted.add(path);
      sentBody = body;
      return <String, dynamic>{'data': rows.isEmpty ? null : rows.first};
    }
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
  final Directory temp = Directory.systemTemp.createTempSync('so-hold-test');
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

bool _enabled(WidgetTester tester, String label) {
  final Finder button = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate((widget) => widget is ButtonStyleButton),
  );
  return (tester.widget(button.first) as ButtonStyleButton).onPressed != null;
}

void main() {
  const List<String> full = <String>[
    'SALES_VIEW',
    'SALES_APPROVE',
    'SALES_CANCEL',
  ];

  testWidgets('a live order offers Hold', (tester) async {
    await _pump(tester, _OrdersApi(rows: <Json>[_order()]), full);

    expect(find.text('Hold'), findsOneWidget);
    expect(find.text('Release'), findsNothing);
    expect(_enabled(tester, 'Hold'), isTrue);
  });

  testWidgets('a held order offers Release instead', (tester) async {
    await _pump(
      tester,
      _OrdersApi(rows: <Json>[_order(onHold: true, holdReason: 'Payment.')]),
      full,
    );

    // One button, not two with one always dead: an order is either held or it
    // is not, and the label says which.
    expect(find.text('Release'), findsOneWidget);
    expect(find.text('Hold'), findsNothing);
  });

  testWidgets('a held order does not look like a live one in the list',
      (tester) async {
    await _pump(
      tester,
      _OrdersApi(rows: <Json>[_order(onHold: true, holdReason: 'Payment.')]),
      full,
    );

    // The whole failure this feature exists to avoid is a held order sitting
    // in the list indistinguishable from one that is about to ship.
    expect(find.text('APPROVED (on hold)'), findsOneWidget);
  });

  testWidgets('holding sends the reason somebody typed', (tester) async {
    final _OrdersApi api = _OrdersApi(rows: <Json>[_order()]);
    await _pump(tester, api, full);

    await tester.tap(find.text('Hold'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Awaiting the LC.');
    await tester.tap(find.widgetWithText(FilledButton, 'Hold'));
    await tester.pumpAndSettle();

    expect(api.posted.any((path) => path.endsWith('/hold')), isTrue);
    expect(api.sentBody?['reason'], 'Awaiting the LC.');
  });

  testWidgets('a hold with no reason is not sent', (tester) async {
    final _OrdersApi api = _OrdersApi(rows: <Json>[_order()]);
    await _pump(tester, api, full);

    await tester.tap(find.text('Hold'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Hold'));
    await tester.pumpAndSettle();

    // Whoever hits the refusal downstream has to know why; a blank reason
    // tells them nothing, so the request is not made at all.
    expect(api.posted.any((path) => path.endsWith('/hold')), isFalse);
  });

  testWidgets('a cancelled order cannot be held', (tester) async {
    await _pump(
      tester,
      _OrdersApi(rows: <Json>[_order(status: 'CANCELLED')]),
      full,
    );

    expect(_enabled(tester, 'Hold'), isFalse);
  });

  testWidgets('someone who cannot approve cannot hold', (tester) async {
    await _pump(
      tester,
      _OrdersApi(rows: <Json>[_order()]),
      const <String>['SALES_VIEW'],
    );

    // The same authority the server asks for: holding decides whether the
    // order goes out.
    expect(_enabled(tester, 'Hold'), isFalse);
  });
}
