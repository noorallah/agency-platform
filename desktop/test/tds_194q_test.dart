import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/report.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/finance/tds_194q_settings_dialog.dart';
import 'package:agency_desktop/ui/reports/reports_workspace.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show ListViewRequest, ListViewRequestScope, Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// TDS on purchases under section 194Q (ACC-8).
PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _Api extends ApiClient {
  _Api({this.applies = true, this.failSupplier = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool applies;
  final bool failSupplier;
  Json? saved;
  final List<String> suppliersAsked = [];
  final List<Map<String, String>?> queries = [];

  @override
  Future<Json> tds194qSettings() async => <String, dynamic>{
        'is_enabled': false,
        'threshold_amount': '5000000.00',
        'rate_percent': '0.1000',
        'rate_without_pan_percent': '5.0000',
      };

  @override
  Future<Json> saveTds194qSettings(Json body) async {
    saved = body;
    return body;
  }

  @override
  Future<Json> tds194qSupplier(String vendorId, {required String on}) async {
    suppliersAsked.add('$vendorId $on');
    if (failSupplier) throw ApiException('down', statusCode: 500);
    return <String, dynamic>{
      'applies': applies,
      'purchases': '6000000.00',
      'due': '1000.00',
      'deducted': '0.00',
      'to_deduct': applies ? '1000.00' : '0.00',
    };
  }

  @override
  Future<ReportPage> reportRows(
    String path, {
    Map<String, String>? query,
    String? rowsKey,
  }) async {
    queries.add(query);
    return const ReportPage(rows: [
      {
        'vendor_name': 'Principal Ltd',
        'pan': 'AAACP1234C',
        'purchases': '6000000.00',
        'excess': '1000000.00',
        'rate_percent': '0.1000',
        'due': '1000.00',
        'deducted': '0.00',
        'to_deduct': '1000.00',
      },
    ], total: 1);
  }
}

Future<void> _openPayment(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Phase2Scope(
        child: Scaffold(
          body: RecordSettlementDialog(
            api: api,
            direction: SettlementDirection.payment,
            parties: const [
              PartyOption(id: 'v-1', code: 'V1', name: 'Principal Ltd'),
            ],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.byType(TextFormField).first);
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('Principal Ltd').last);
  await tester.pumpAndSettle();
}

String _tdsText(WidgetTester tester) => tester
    .widget<TextField>(find.byKey(const ValueKey('settlement-tds-amount')))
    .controller!
    .text;

void main() {
  testWidgets('settings load, and Save sends the four fields',
      (tester) async {
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Tds194qSettingsDialog(
          api: api,
          permissions:
              _permissionsFor(const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('tds194q-enabled')));
    await tester.enterText(
        find.byKey(const ValueKey('tds194q-threshold')), '6000000');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('tds194q-save')));
    await tester.pumpAndSettle();
    expect(api.saved, {
      'is_enabled': true,
      'threshold_amount': '6000000',
      'rate_percent': '0.1000',
      'rate_without_pan_percent': '5.0000',
    });
  });

  testWidgets('without the manage code there is no Save', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Tds194qSettingsDialog(
          api: _Api(),
          permissions: _permissionsFor(const ['ACCOUNT_VIEW']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('tds194q-save')), findsNothing);
  });

  testWidgets('a payment to a supplier 194Q applies to prefills the TDS',
      (tester) async {
    final _Api api = _Api();
    await _openPayment(tester, api);
    expect(api.suppliersAsked.single, startsWith('v-1 '));
    expect(_tdsText(tester), '1000.00');
    expect(find.textContaining('194Q: ₹6000000.00 bought this year'),
        findsOneWidget);
    expect(find.text('194Q - Purchase of goods'), findsOneWidget);
  });

  testWidgets('a typed TDS amount is never overwritten', (tester) async {
    final _Api api = _Api();
    await _openPayment(tester, api);
    await tester.enterText(
        find.byKey(const ValueKey('settlement-tds-amount')), '7');
    await tester.enterText(find.widgetWithText(TextField, 'Amount'), '50000');
    await tester.pumpAndSettle();
    expect(_tdsText(tester), '7');
  });

  testWidgets('nothing is filled when 194Q does not apply', (tester) async {
    await _openPayment(tester, _Api(applies: false));
    expect(_tdsText(tester), isEmpty);
  });

  testWidgets('nothing is filled when the call fails', (tester) async {
    await _openPayment(tester, _Api(failSupplier: true));
    expect(_tdsText(tester), isEmpty);
  });

  testWidgets('the report asks as on a day and shows its rows',
      (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: ListViewRequestScope(
            request: const ListViewRequest(
              path: 'reports/financial',
              view: 'tds-194q',
              serial: 1,
            ),
            child: ReportsWorkspace(
              api: api,
              permissions: _permissionsFor(const ['ACCOUNT_VIEW']),
              hasActiveFirm: true,
              tabId: 'financial',
            ),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(api.queries.last!.keys, ['on']);
    expect(find.text('Principal Ltd'), findsOneWidget);
    expect(find.text('AAACP1234C'), findsOneWidget);
  });
}
