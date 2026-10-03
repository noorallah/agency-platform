// GST-5, desktop half: the checks screen lists what a return would get wrong.
//
// Pins: rows with plain-language labels and severity badges, the summary line,
// the empty state, a period change re-querying with the right dates, and a
// refusal showing the server's message.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/gst_filing_checks_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _row(String check, String severity, String type, String number) => {
      'check': check,
      'severity': severity,
      'document_type': type,
      'document_id': type == 'FIRM' ? null : 'id-$number',
      'document_number': number,
      'document_date': '2026-09-10',
      'party_name': 'Acme Traders',
      'message': 'Something to fix on $number',
    };

class _Api extends ApiClient {
  _Api({this.empty = false, this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool empty;
  final String? refusal;
  final List<(DateTime, DateTime)> asked = [];

  @override
  Future<Json> getGstFilingChecks({
    required DateTime from,
    required DateTime to,
  }) async {
    asked.add((from, to));
    if (refusal != null) throw ApiException(refusal!, statusCode: 422);
    return {
      'from_date': '2026-09-01',
      'to_date': '2026-09-30',
      'required_hsn_digits': 4,
      'counts': {'GSTIN_INVALID': 1, 'HSN_SHORT': 1, 'IRN_MISSING': 1},
      'rows': empty
          ? <Json>[]
          : [
              _row('GSTIN_INVALID', 'ERROR', 'SALES_INVOICE', 'INV-1'),
              _row('HSN_SHORT', 'ERROR', 'SALES_INVOICE', 'INV-2'),
              _row('IRN_MISSING', 'WARNING', 'CREDIT_NOTE', 'CN-1'),
              _row('CREDIT_NOTE_LATE', 'WARNING', 'CREDIT_NOTE', 'CN-2'),
              _row('HSN_MISSING', 'ERROR', 'PURCHASE_INVOICE', 'PB-1'),
              _row('PLACE_OF_SUPPLY_MISSING', 'ERROR', 'CUSTOMER_DEBIT_NOTE',
                  'DN-1'),
              _row('CREDIT_NOTE_ON_CANCELLED_INVOICE', 'WARNING',
                  'CREDIT_NOTE', 'CN-3'),
              _row('GSTIN_INVALID', 'ERROR', 'FIRM', 'Firm'),
            ],
    };
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> codes = const ['SALES_VIEW'],
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: GstFilingChecksPage(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 3),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('asks for last month and lists the rows with labels',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    expect(api.asked.single, (DateTime(2026, 9, 1), DateTime(2026, 9, 30)));
    expect(find.text('2026-09-01 to 2026-09-30'), findsOneWidget);
    expect(find.text('GSTIN invalid'), findsNWidgets(2));
    expect(find.text('HSN too short'), findsOneWidget);
    expect(find.text('HSN missing'), findsOneWidget);
    expect(find.text('No place of supply'), findsOneWidget);
    expect(find.text('No IRN'), findsOneWidget);
    expect(find.text('Credit note too late'), findsOneWidget);
    expect(find.text('Credit note on cancelled bill'), findsOneWidget);
    expect(find.text('Error'), findsNWidgets(5));
    expect(find.text('Warning'), findsNWidgets(3));
    expect(find.text('INV-1'), findsOneWidget);
    expect(find.text('Purchase bill'), findsOneWidget);
    expect(
      find.text("5 errors, 3 warnings · HSN needs 4 digits at this firm's "
          'turnover'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('fits 800x600', (tester) async {
    await _pump(tester, _Api(), size: const Size(800, 600));
    expect(tester.takeException(), isNull);
  });

  testWidgets('says there is nothing to fix', (tester) async {
    await _pump(tester, _Api(empty: true));
    expect(find.text('Nothing to fix for this period'), findsOneWidget);
    expect(find.byKey(const ValueKey('gst-check-row-0')), findsNothing);
  });

  testWidgets('changing the month re-queries with its dates', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('gst-checks-prev')));
    await tester.pumpAndSettle();
    expect(api.asked.last, (DateTime(2026, 8, 1), DateTime(2026, 8, 31)));

    await tester.tap(find.byKey(const ValueKey('gst-checks-next')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gst-checks-next')));
    await tester.pumpAndSettle();
    expect(api.asked.last, (DateTime(2026, 10, 1), DateTime(2026, 10, 31)));
    expect(api.asked, hasLength(4));
  });

  testWidgets('shows the server refusal instead of findings', (tester) async {
    await _pump(
        tester, _Api(refusal: 'A return covers at most three months.'));
    expect(find.text('A return covers at most three months.'),
        findsOneWidget);
    expect(find.byKey(const ValueKey('gst-checks-summary')), findsNothing);
  });

  testWidgets('needs the view sales permission', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, codes: const ['ACCOUNT_VIEW']);
    expect(api.asked, isEmpty);
    expect(find.byKey(const ValueKey('gst-checks-period')), findsNothing);
  });
}
