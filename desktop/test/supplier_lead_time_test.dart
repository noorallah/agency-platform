// BUY-6: the lead-time summary on the supplier catalogue.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/vendors/supplier_catalogue_section.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api(this.leadTime)
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json leadTime;
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
    calls.add('$method $path');
    if (path.endsWith('/lead-time')) {
      return <String, dynamic>{'data': leadTime};
    }
    return <String, dynamic>{'data': <Json>[]};
  }
}

Future<void> _open(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SingleChildScrollView(
        child: SupplierCatalogueSection(api: api, vendorId: 'v-1'),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the summary renders quote, average and punctuality',
      (tester) async {
    final _Api api = _Api(<String, dynamic>{
      'vendor_id': 'v-1',
      'quoted_days': 5,
      'receipts': 12,
      'average_days': '3.0',
      'late_receipts': 2,
      'receipts_with_expected_date': 12,
      'on_time_percent': '83.3',
    });
    await _open(tester, api);
    expect(
      find.text('Quoted: 5 days · Delivered: 3.0 days on average over 12 '
          'receipts · On time: 83.3% (2 late)'),
      findsOneWidget,
    );
    expect(api.calls, contains('GET /api/v1/vendors/v-1/lead-time'));
  });

  testWidgets('with no quote and no receipts it says so', (tester) async {
    await _open(
        tester,
        _Api(<String, dynamic>{
          'vendor_id': 'v-1',
          'quoted_days': null,
          'receipts': 0,
          'average_days': null,
          'late_receipts': 0,
          'receipts_with_expected_date': 0,
          'on_time_percent': null,
        }));
    expect(
      find.text('Quoted: none in the catalogue · Delivered: no receipts yet '
          '· On time: not measured'),
      findsOneWidget,
    );
  });
}
