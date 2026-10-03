// TDS challans and a supplier's usual TDS section (ACC-7).
//
// The screen lists challans and the deductions each paid; the record dialog
// posts the ticked deductions with the declared keys; a cancel sends its
// reason; the vendor editor sends default_tds_section; a payment prefills the
// supplier's usual section without overwriting a chosen one.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/settlement.dart';
import 'package:agency_desktop/models/settlement_direction.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/finance/record_settlement_dialog.dart';
import 'package:agency_desktop/ui/finance/tds_challan_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'ACCOUNT_VIEW',
    'JOURNAL_POST',
    'JOURNAL_REVERSE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

Json _challan() => <String, dynamic>{
      'id': 'ch-1',
      'challan_number': 'TDSC-2026-0001',
      'deposited_on': '2026-09-07',
      'bsr_code': '0510308',
      'challan_serial': '12345',
      'cin': '051030800709202612345',
      'section': '194C',
      'section_name': 'Contractors and transporters',
      'tax_amount': '1500.00',
      'interest_amount': '20.00',
      'fee_amount': '10.00',
      'total_amount': '1530.00',
      'paid_from_account_id': 'acc-bank',
      'paid_from_account_code': '1010',
      'paid_from_account_name': 'HDFC Current',
      'status': 'POSTED',
      'is_late': true,
      'items': <Json>[
        <String, dynamic>{
          'kind': 'PAYMENT',
          'document_id': 'p-1',
          'document_number': 'PAY-0001',
          'document_date': '2026-08-20',
          'party_name': 'Sharma Transport',
          'pan': 'AAAPS1234C',
          'tds_amount': 1500,
        },
      ],
      'version': 3,
    };

Json _open(String kind, String id, String number, String tds) =>
    <String, dynamic>{
      'kind': kind,
      'id': id,
      'document_number': number,
      'document_date': '2026-08-20',
      'party_name': 'Sharma Transport',
      'pan': 'AAAPS1234C',
      'section': '194C',
      'gross_amount': '50000.00',
      'tds_amount': tds,
      'due_date': '2026-09-07',
    };

class _Api extends ApiClient {
  _Api({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = <String>[];
  final List<Map<String, String>?> queries = [];
  Json? created;
  Json? cancelBody;

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
    if (path == '/api/v1/contra-vouchers/money-accounts') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'acc-bank',
            'code': '1010',
            'name': 'HDFC Current',
            'kind': 'BANK',
          },
        ],
      };
    }
    if (path == '/api/v1/finance/tds-challans/open-deductions') {
      queries.add(query);
      return <String, dynamic>{
        'data': <Json>[
          _open('PAYMENT', 'p-1', 'PAY-0001', '1000.00'),
          _open('EXPENSE', 'e-1', 'EXP-0002', '500.00'),
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/finance/tds-challans') {
      created = body;
      return <String, dynamic>{'data': _challan()};
    }
    if (path.endsWith('/cancel')) {
      cancelBody = body;
      return <String, dynamic>{'data': _challan()};
    }
    if (path == '/api/v1/finance/tds-challans') {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('tds-challans'),
    );

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: TdsChallanPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pickFrom(WidgetTester tester, Key menu, String label) async {
  await tester.tap(find.byKey(menu));
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining(label).last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows the challan, its CIN and a late flag, and '
      'selecting it shows its deductions', (tester) async {
    final _Api api = _Api(rows: <Json>[_challan()]);
    await _pump(tester, api);

    expect(find.text('TDSC-2026-0001'), findsOneWidget);
    expect(find.text('051030800709202612345'), findsOneWidget);
    expect(find.text('194C'), findsOneWidget);
    expect(find.text('Late'), findsWidgets);
    expect(find.textContaining('1,530'), findsWidgets);

    await tester.tap(find.text('TDSC-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('tds-challan-items')), findsOneWidget);
    expect(find.textContaining('PAY-0001'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('recording posts the ticked deductions with the declared keys',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_challan()]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const ValueKey('tds-challan-bsr')),
        '0510308');
    await tester.enterText(find.byKey(const ValueKey('tds-challan-serial')),
        '12345');
    await _pickFrom(
        tester, const ValueKey('tds-challan-section'), '194C - Contractors');
    await _pickFrom(
        tester, const ValueKey('tds-challan-account'), 'HDFC Current');

    expect(api.queries.last!['section'], '194C');
    expect(api.queries.last!.containsKey('to_date'), isTrue);
    expect(find.text('Tax: ₹1500.00'), findsOneWidget);

    // Untick the expense: only the payment is paid.
    await tester.tap(find.byKey(const ValueKey('tds-open-EXPENSE:e-1')));
    await tester.pumpAndSettle();
    expect(find.text('Tax: ₹1000.00'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('tds-challan-counterfoil')), '1000');
    await tester.tap(find.byKey(const ValueKey('tds-challan-save')));
    await tester.pumpAndSettle();

    expect(api.requested, contains('POST /api/v1/finance/tds-challans'));
    expect(api.created, <String, dynamic>{
      'deposited_on': api.created!['deposited_on'],
      'bsr_code': '0510308',
      'challan_serial': '12345',
      'section': '194C',
      'paid_from_account_id': 'acc-bank',
      'tax_amount': '1000',
      'interest_amount': '0',
      'fee_amount': '0',
      'deductions': <Map<String, dynamic>>[
        {'kind': 'PAYMENT', 'id': 'p-1'},
      ],
    });
    expect(tester.takeException(), isNull);
  });

  testWidgets('a challan with nothing ticked is refused before the server',
      (tester) async {
    final _Api api = _Api(rows: <Json>[_challan()]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('tds-challan-save')));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.byKey(const ValueKey('tds-challan-problem')), findsOneWidget);
  });

  testWidgets('cancelling asks why and sends the reason', (tester) async {
    final _Api api = _Api(rows: <Json>[_challan()]);
    await _pump(tester, api);
    await tester.tap(find.text('TDSC-2026-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();

    expect(
      api.requested,
      isNot(contains('POST /api/v1/finance/tds-challans/ch-1/cancel')),
    );
    await tester.enterText(find.byType(TextField).last, 'Wrong serial');
    await tester.tap(find.text('Cancel challan'));
    await tester.pumpAndSettle();

    expect(api.requested,
        contains('POST /api/v1/finance/tds-challans/ch-1/cancel'));
    expect(api.cancelBody, <String, dynamic>{'reason': 'Wrong serial'});
  });

  testWidgets('a user with no view permission sees nothing', (tester) async {
    final _Api api = _Api(rows: <Json>[_challan()]);
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: TdsChallanPage(
          api: api,
          preferences: _preferences(),
          permissions: _permissions(perms: const []),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('You cannot see TDS challans'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  test('a vendor reads default_tds_section, and none is empty', () {
    final Vendor with194 = Vendor.fromJson(<String, dynamic>{
      'id': 'v-1',
      'default_tds_section': '194C',
    });
    final Vendor without = Vendor.fromJson(<String, dynamic>{
      'id': 'v-2',
      'default_tds_section': null,
    });
    expect(with194.defaultTdsSection, '194C');
    expect(without.defaultTdsSection, isEmpty);
  });

  group('a payment', () {
    Future<void> openPayment(
      WidgetTester tester,
      _PayApi api, {
      String usual = '',
    }) async {
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
                parties: [
                  PartyOption(
                    id: 'v-1',
                    code: 'V1',
                    name: 'Sharma Transport',
                    defaultTdsSection: usual,
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(TextFormField).first);
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('Sharma Transport').last);
      await tester.pumpAndSettle();
    }

    testWidgets('prefills the supplier\'s usual section when none is chosen',
        (tester) async {
      await openPayment(tester, _PayApi(usual: '194C'));
      expect(find.text('194C - Contractors and transporters'), findsOneWidget);
    });

    testWidgets('leaves the section empty when the supplier has none',
        (tester) async {
      await openPayment(tester, _PayApi());
      expect(find.text('194C - Contractors and transporters'), findsNothing);
    });

    testWidgets('lets the 194Q prefill win where it applies', (tester) async {
      await openPayment(tester, _PayApi(usual: '194C', applies194q: true));
      expect(find.text('194Q - Purchase of goods'), findsOneWidget);
      expect(find.text('194C - Contractors and transporters'), findsNothing);
    });
  });
}

/// A payment dialog's api: the supplier's usual section comes from the vendor
/// list, as it does for a role that may read vendors.
class _PayApi extends ApiClient {
  _PayApi({this.usual = '', this.applies194q = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String usual;
  final bool applies194q;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: [
          Vendor.fromJson(<String, dynamic>{
            'id': 'v-1',
            'default_tds_section': usual.isEmpty ? null : usual,
          }),
        ],
        total: 1,
      );

  @override
  Future<Json> tds194qSupplier(String vendorId, {required String on}) async =>
      <String, dynamic>{
        'applies': applies194q,
        'purchases': '6000000.00',
        'due': '1000.00',
        'deducted': '0.00',
        'to_deduct': applies194q ? '1000.00' : '0.00',
      };
}
