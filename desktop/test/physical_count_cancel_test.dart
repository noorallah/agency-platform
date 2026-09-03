// A physical count could be opened, recorded and posted, and not called off.
//
// `cancelPhysicalCount` had a route and a client method and no control, so a
// sheet opened by mistake -- or against the wrong warehouse -- stayed DRAFT
// for ever, holding expected quantities from whenever it was drawn up and
// cluttering the list.
//
// These pin the control, the confirmation in front of it, and that a posted
// sheet does not offer it.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/physical_count.dart';
import 'package:agency_desktop/ui/inventory/physical_count_sheet_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> calls = <String>[];

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
    if (method != 'GET') calls.add('$method $path');
    return <String, dynamic>{'data': _sheetJson()};
  }
}

Json _sheetJson({String status = 'DRAFT'}) => <String, dynamic>{
      'id': 'pc-1',
      'count_number': 'PC-0001',
      'count_date': '2026-09-03',
      'status': status,
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'notes': '',
      'lines': <Json>[
        <String, dynamic>{
          'id': 'l-1',
          'product_id': 'p-1',
          'product_name': 'Toothpaste 150g',
          'batch_id': '',
          'batch_number': '',
          'expected_quantity': '40.0000',
          'counted_quantity': '',
          'difference_quantity': '0.0000',
        },
      ],
    };

Future<void> _open(
  WidgetTester tester,
  _Api api, {
  String status = 'DRAFT',
  bool canCount = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: PhysicalCountSheetDialog(
        api: api,
        sheet: PhysicalCountSheet.fromJson(_sheetJson(status: status)),
        canCount: canCount,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a draft sheet can be abandoned', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    await tester.tap(find.widgetWithText(TextButton, 'Abandon sheet'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Abandon'));
    await tester.pumpAndSettle();

    expect(api.calls.single, contains('/counts/pc-1/cancel'));
  });

  testWidgets('it asks first, and nothing is sent if the answer is no',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);

    await tester.tap(find.widgetWithText(TextButton, 'Abandon sheet'));
    await tester.pumpAndSettle();

    // A sheet somebody spent an afternoon on must not go on one stray click.
    expect(find.textContaining('cannot be got back'), findsNothing);
    expect(find.textContaining('No stock moves'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(api.calls, isEmpty);
  });

  testWidgets('a posted sheet offers nothing to abandon', (tester) async {
    // Its differences are already adjustments in the ledger; the service
    // refuses anything but a draft, so the screen must not offer it.
    await _open(tester, _Api(), status: 'POSTED');

    expect(find.widgetWithText(TextButton, 'Abandon sheet'), findsNothing);
  });

  testWidgets('somebody who cannot adjust stock cannot abandon a sheet',
      (tester) async {
    // The route is gated on INVENTORY_ADJUST, the same permission that lets
    // the sheet be counted at all.
    await _open(tester, _Api(), canCount: false);

    expect(find.widgetWithText(TextButton, 'Abandon sheet'), findsNothing);
  });
}
