// Backlog 78 row 4, desktop half: rule 37 (bills unpaid 180 days).
//
// Pins: the grid shows the rows; the note when the mode is OFF; the post
// action only for POST mode and JOURNAL_POST, sending all or the selected
// rows, and a refusal showing the server's message; the GST documents
// settings send rule37_mode; GSTR-3B shows the two new rows.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/einvoice.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/gst_return_page.dart';
import 'package:agency_desktop/ui/sales/rule37_page.dart';
import 'package:agency_desktop/ui/tax/gst_documents_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode({'permissions': codes})));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _tax(String cgst) => {
      'igst': '0.00',
      'cgst': cgst,
      'sgst': cgst,
      'cess': '0.00',
    };

Json _row(String id, String action) => {
      'purchase_invoice_id': id,
      'invoice_number': 'PB-$id',
      'supplier_invoice_number': 'S-$id',
      'vendor_name': 'Acme Traders',
      'bill_date': '2026-01-01',
      'days': 270,
      'bill_total': '1180.00',
      'outstanding': '590.00',
      'credit': _tax('90.00'),
      'reversed': _tax('0.00'),
      'action': action,
      'amount': _tax('45.00'),
    };

class _Api extends ApiClient {
  _Api({this.mode = 'POST', this.refusal})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String mode;
  final String? refusal;
  String? askedAsOf;
  final List<Json> posts = [];
  Json? savedSettings;
  Json summary3b = {};

  // The dialog asks for the filing provider too; a refusal hides that choice.
  @override
  Future<EInvoiceSettings> einvoiceSettings() async =>
      throw const ApiException('not here');

  @override
  Future<Json> rule37(String asOf) async {
    askedAsOf = asOf;
    return {
      'as_of': asOf,
      'mode': mode,
      'rows': mode == 'OFF'
          ? <Json>[]
          : [_row('a', 'REVERSE'), _row('b', 'RECLAIM')],
    };
  }

  @override
  Future<Json> postRule37(String asOf, {List<String>? purchaseInvoiceIds}) async {
    if (refusal != null) {
      throw ApiException(refusal!, statusCode: 422);
    }
    posts.add({'as_of': asOf, 'ids': purchaseInvoiceIds});
    return {};
  }

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
    if (path.endsWith('/gst-compliance-settings')) {
      if (method == 'PUT') {
        savedSettings = Map<String, dynamic>.from(body ?? const {});
        return {
          'data': {...?body, 'is_configured': true},
        };
      }
      return {
        'data': {
          'dispatch_without_invoice': 'OFF',
          'route_sale_needs_invoice': false,
          'is_configured': true,
          'rule37_mode': 'REPORT',
        },
      };
    }
    // The GSTR-3B page asks how the firm files (GST-7): monthly here.
    if (path.endsWith('/filing-plan')) {
      return <String, dynamic>{
        'data': {'filing_frequency': 'MONTHLY'},
      };
    }
    throw StateError('unexpected $method $path');
  }

  @override
  Future<Json> gstr1({required String fromDate, required String toDate}) async =>
      {'gstin': '29AAAAA0000A1Z5'};

  @override
  Future<Json> gstr3b({required String fromDate, required String toDate}) async =>
      summary3b;
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> codes = const ['ACCOUNT_VIEW', 'JOURNAL_POST'],
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Rule37Page(
        api: api,
        permissions: _permissions(codes),
        hasActiveFirm: true,
        today: DateTime(2026, 10, 2),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('lists the rows as of today', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    expect(api.askedAsOf, '2026-10-02');
    expect(find.text('PB-a'), findsOneWidget);
    expect(find.text('Reverse'), findsOneWidget);
    expect(find.text('Reclaim'), findsOneWidget);
    expect(find.text('270'), findsNWidgets(2));
    expect(find.text('180.00'), findsNWidgets(2));
    expect(find.text('90.00'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('fits 800x600', (tester) async {
    await _pump(tester, _Api(), size: const Size(800, 600));
    expect(tester.takeException(), isNull);
  });

  testWidgets('says where to turn it on when the mode is OFF', (tester) async {
    await _pump(tester, _Api(mode: 'OFF'));
    expect(find.byKey(const ValueKey('rule37-off')), findsOneWidget);
    expect(find.textContaining('Settings > Tax > GST Documents'),
        findsOneWidget);
    expect(find.byKey(const ValueKey('rule37-post')), findsNothing);
  });

  testWidgets('report mode and missing permission offer no post action',
      (tester) async {
    await _pump(tester, _Api(mode: 'REPORT'));
    expect(find.byKey(const ValueKey('rule37-post')), findsNothing);

    await _pump(tester, _Api(), codes: ['ACCOUNT_VIEW']);
    expect(find.byKey(const ValueKey('rule37-post')), findsNothing);
  });

  testWidgets('post sends every row, then the selected ones', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('rule37-post')));
    await tester.pumpAndSettle();
    expect(api.posts.single, {'as_of': '2026-10-02', 'ids': null});

    await tester.tap(find.byType(Checkbox).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rule37-post')));
    await tester.pumpAndSettle();
    expect(api.posts.last, {
      'as_of': '2026-10-02',
      'ids': ['a'],
    });
  });

  testWidgets('a refusal shows the server message', (tester) async {
    await _pump(tester, _Api(refusal: 'Posting is switched off.'));
    await tester.tap(find.byKey(const ValueKey('rule37-post')));
    await tester.pumpAndSettle();
    expect(find.text('Posting is switched off.'), findsOneWidget);
  });

  testWidgets('settings send rule37_mode', (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstDocumentsSettingsDialog(
          api: api,
          permissions: _permissions(['TAX_VIEW', 'TAX_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const ValueKey('gst-rule37-mode')));
    await tester.tap(find.byKey(const ValueKey('gst-rule37-mode')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Report and post').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
    await tester.pumpAndSettle();

    expect(api.savedSettings?['rule37_mode'], 'POST');
    // Not touched, it goes back as the default: warn (backlog 78 row 5).
    expect(api.savedSettings?['supplier_irn_check'], 'WARN');
  });

  testWidgets('settings send supplier_irn_check', (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstDocumentsSettingsDialog(
          api: api,
          permissions: _permissions(['TAX_VIEW', 'TAX_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester
        .ensureVisible(find.byKey(const ValueKey('gst-supplier-irn-check')));
    await tester.tap(find.byKey(const ValueKey('gst-supplier-irn-check')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Off').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('gst-settings-save')));
    await tester.pumpAndSettle();

    expect(api.savedSettings?['supplier_irn_check'], 'OFF');
  });

  testWidgets('GSTR-3B shows the reclaim and the rule 37 part of 4(B)(2)',
      (tester) async {
    final _Api api = _Api()
      ..summary3b = {
        'itc_reversed': _tax('10.00'),
        'itc_reversed_rule37': _tax('4.00'),
        'itc_reclaimed': _tax('2.00'),
      };
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GstReturnPage(
          api: api,
          permissions: _permissions(['SALES_VIEW']),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GSTR-3B'));
    await tester.pumpAndSettle();
    expect(find.text('4(D)(1) Reclaimed (rule 37)'), findsOneWidget);
    expect(find.text('of which rule 37'), findsOneWidget);
  });
}
