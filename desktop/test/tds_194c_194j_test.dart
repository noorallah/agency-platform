// PG-5 (backlog 86 #10): TDS under 194C and 194J on the desktop.
//
// The vendor form sends the three TDS fields, the bill's Approve dialog shows
// what the server proposes and sends an override only when one was typed, and
// the settings dialog saves a partial PUT for each section.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/document_framework/document_steps.dart';
import 'package:agency_desktop/ui/finance/tds_194q_settings_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/approve_bill_dialog.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_steps.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json? savedVendor;
  final List<({String section, Json body})> savedSections = [];

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(
        items: <Vendor>[
          Vendor.fromJson(<String, dynamic>{
            'id': 'v-1',
            'firm_id': 'firm-1',
            'code': 'V001',
            'name': 'Supplier One',
            'display_name': 'Supplier One',
            'status': 'ACTIVE',
            'default_tds_section': '194J',
          }),
        ],
        total: 1,
      );

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    savedVendor = data;
    return (await vendors()).items.first;
  }

  @override
  Future<Json> tds194qSettings() async => <String, dynamic>{
        'is_enabled': false,
        'threshold_amount': '5000000.00',
        'rate_percent': '0.1000',
        'rate_without_pan_percent': '5.0000',
      };

  @override
  Future<List<Json>> tdsSectionSettings() async => <Json>[
        <String, dynamic>{
          'section': '194C',
          'is_enabled': false,
          'single_threshold_amount': '30000.00',
          'annual_threshold_amount': '100000.00',
          'rate_percent': '2.0000',
          'lower_rate_percent': '1.0000',
          'rate_without_pan_percent': '20.0000',
        },
        <String, dynamic>{
          'section': '194J',
          'is_enabled': true,
          'single_threshold_amount': null,
          'annual_threshold_amount': '50000.00',
          'rate_percent': '10.0000',
          'lower_rate_percent': '2.0000',
          'rate_without_pan_percent': '20.0000',
        },
      ];

  @override
  Future<Json> saveTdsSectionSettings(String section, Json body) async {
    savedSections.add((section: section, body: body));
    return body;
  }
}

/// Answers the bill, and the bill's own TDS route, and records every GET.
class _BillApi extends ApiClient {
  _BillApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> gets = <String>[];

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
    if (method == 'GET') gets.add(path);
    if (path == '/api/v1/purchase-invoices/pi-1/tds-proposal') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'section': '194C',
          'rate_percent': '2.0000',
          'rate_basis': 'OTHER',
          'threshold_crossed': true,
          'due': '1234.00',
          'deducted': '0.00',
          'proposed': '1234.00',
          'applies': true,
        },
      };
    }
    if (path.startsWith('/api/v1/finance/tds-sections/suppliers/')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'section': '194C',
          'rate_percent': '2.0000',
          'due': '1.00',
          'deducted': '0.00',
          'proposed': '1.00',
          'applies': true,
        },
      };
    }
    if (path == '/api/v1/purchase-invoices/pi-1') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'id': 'pi-1',
          'vendor_id': 'v-1',
          'invoice_date': '2026-10-01',
          'subtotal': '1000.00',
          'grand_total': '1180.00',
          'currency_code': null,
        },
      };
    }
    return <String, dynamic>{'data': <String, dynamic>{}};
  }
}

const List<Size> _sizes = [Size(1366, 768), Size(800, 600)];

void _size(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _openVendorEditor(WidgetTester tester, _Api api) async {
  _size(tester, const Size(1600, 1200));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: VendorManagementPage(
        api: api,
        permissions: _permissions(
          const ['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
        ),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester.tap(find.text('V001').first);
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Edit').first);
  await tester.pumpAndSettle();
}

Future<void> _openApprove(
  WidgetTester tester,
  List<Json> approvals,
  Size size, {
  Json? proposal,
}) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () => showDialog<Json>(
            context: context,
            builder: (_) => ApproveBillDialog(
              number: 'PI-1',
              loadProposal: () async => proposal,
              onApprove: (body) async {
                approvals.add(body ?? <String, dynamic>{'_none': true});
                return <String, dynamic>{};
              },
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

const Json _proposal = <String, dynamic>{
  'section': '194C',
  'rate_percent': '1.0000',
  'rate_basis': 'company',
  'threshold_crossed': true,
  'due': '1500.00',
  'deducted': '500.00',
  'proposed': '1000.00',
  'applies': true,
};

void main() {
  testWidgets('the vendor form sends the three TDS fields', (tester) async {
    final _Api api = _Api();
    await _openVendorEditor(tester, api);

    final Finder huf = find.byKey(const ValueKey('vendor-tds-individual-huf'));
    // The General tab is a lazy list: drag it until the TDS fields build.
    for (int i = 0; i < 6 && huf.evaluate().isEmpty; i++) {
      await tester.drag(find.byType(TabBarView), const Offset(0, -500));
      await tester.pumpAndSettle();
    }
    // Past the dialog's own bottom edge is "built" but not on screen.
    for (int i = 0; i < 6 && tester.getCenter(huf).dy > 500; i++) {
      await tester.drag(find.byType(TabBarView), const Offset(0, -150));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('Auto from PAN'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Yes').last);
    await tester.pumpAndSettle();
    final Finder technical = find.byKey(const ValueKey('vendor-tds-technical'));
    await tester.ensureVisible(technical);
    await tester.tap(technical);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.savedVendor!['default_tds_section'], '194J');
    expect(api.savedVendor!['tds_individual_huf'], true);
    expect(api.savedVendor!['tds_technical_services'], true);
  });

  testWidgets('the approve dialog shows the proposal and sends nothing '
      'when the override is blank', (tester) async {
    final List<Json> approvals = [];
    await _openApprove(tester, approvals, _sizes.first, proposal: _proposal);

    expect(find.byKey(const ValueKey('approve-tds-proposal')), findsOneWidget);
    expect(find.textContaining('TDS 194C at 1.0000%'), findsOneWidget);
    expect(find.textContaining('Proposed on this bill: ₹1000.00'),
        findsOneWidget);
    final TextField box = tester
        .widget<TextField>(find.byKey(const ValueKey('approve-tds-amount')));
    expect(box.controller!.text, isEmpty, reason: 'never prefilled');

    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(approvals.single, {'_none': true});
  });

  testWidgets('the bill\'s Approve dialog shows the figure the bill\'s own '
      'route answered, with no client-side base (D-BUY-37)', (tester) async {
    final _BillApi api = _BillApi();
    _size(tester, _sizes.first);
    final step = purchaseInvoiceSteps(
      api,
      _permissions(const ['PURCHASE_VIEW', 'PURCHASE_APPROVE']),
    ).firstWhere((s) => s.id == 'approve');
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => step.run(
              context,
              const DocumentRef(id: 'pi-1', number: 'PI-1', status: 'DRAFT'),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Proposed on this bill: ₹1234.00'),
        findsOneWidget);
    expect(
      api.gets.where((p) => p.startsWith('/api/v1/finance/tds-sections')),
      isEmpty,
      reason: 'no bill base is computed here, so the supplier route is unused',
    );
  });

  testWidgets('a typed override is sent, and 0 is sent as 0', (tester) async {
    final List<Json> approvals = [];
    await _openApprove(tester, approvals, _sizes.first, proposal: _proposal);
    await tester.enterText(
        find.byKey(const ValueKey('approve-tds-amount')), '0');
    await tester.tap(find.byKey(const ValueKey('approve-bill-confirm')));
    await tester.pumpAndSettle();
    expect(approvals.single, {'tds_amount': '0'});
  });

  testWidgets('no proposal means no TDS box', (tester) async {
    final List<Json> approvals = [];
    await _openApprove(tester, approvals, _sizes.first);
    expect(find.byKey(const ValueKey('approve-tds-amount')), findsNothing);
  });

  testWidgets('the settings rows save only what changed', (tester) async {
    final _Api api = _Api();
    _size(tester, const Size(1366, 768));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Tds194qSettingsDialog(
          api: api,
          permissions:
              _permissions(const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder rate = find.byKey(const ValueKey('tds194C-rate'));
    await tester.ensureVisible(rate);
    await tester.enterText(rate, '1');
    final Finder enabled = find.byKey(const ValueKey('tds194C-enabled'));
    await tester.ensureVisible(enabled);
    await tester.tap(enabled);
    await tester.pumpAndSettle();
    final Finder save = find.byKey(const ValueKey('tds194C-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();

    expect(api.savedSections.single.section, '194C');
    expect(api.savedSections.single.body, {
      'is_enabled': true,
      'rate_percent': '1',
    });
    // 194J has no single-payment box.
    expect(find.byKey(const ValueKey('tds194J-single')), findsNothing);
  });

  Future<_Api> openSettings(WidgetTester tester) async {
    final _Api api = _Api();
    _size(tester, const Size(1366, 768));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Tds194qSettingsDialog(
          api: api,
          permissions:
              _permissions(const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    return api;
  }

  testWidgets('the rate boxes say what the server does with each (D-BUY-38)',
      (tester) async {
    await openSettings(tester);
    expect(find.text('Rate % (companies, firms and others)'), findsOneWidget);
    expect(find.text('Rate % for an individual or HUF'), findsOneWidget);
    expect(find.text('Rate % for professional fees'), findsOneWidget);
    expect(find.text('Rate % for technical services, call centres and '
        'royalty on films'), findsOneWidget);
    expect(find.textContaining('certificate'), findsNothing);
    expect(find.text('Lower rate % (certificate)'), findsNothing);
  });

  for (final String bad in <String>['', '0', '31', 'abc']) {
    testWidgets('a rate of "$bad" is refused before the server (D-BUY-38)',
        (tester) async {
      final _Api api = await openSettings(tester);
      final Finder box = find.byKey(const ValueKey('tds194C-lower'));
      await tester.ensureVisible(box);
      await tester.enterText(box, bad);
      final Finder save = find.byKey(const ValueKey('tds194C-save'));
      await tester.ensureVisible(save);
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(api.savedSections, isEmpty);
      expect(find.textContaining('more than 0 and at most 30'), findsOneWidget);
    });
  }

  testWidgets('a negative threshold is refused before the server (D-BUY-38)',
      (tester) async {
    final _Api api = await openSettings(tester);
    final Finder box = find.byKey(const ValueKey('tds194C-annual'));
    await tester.ensureVisible(box);
    await tester.enterText(box, '-1');
    final Finder save = find.byKey(const ValueKey('tds194C-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(api.savedSections, isEmpty);
    expect(find.textContaining('cannot be below 0'), findsOneWidget);
  });

  testWidgets('a valid individual/HUF rate saves only that key (D-BUY-38)',
      (tester) async {
    final _Api api = await openSettings(tester);
    final Finder box = find.byKey(const ValueKey('tds194C-lower'));
    await tester.ensureVisible(box);
    await tester.enterText(box, '1.5');
    final Finder save = find.byKey(const ValueKey('tds194C-save'));
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(api.savedSections.single.body, {'lower_rate_percent': '1.5'});
  });

  for (final Size size in _sizes) {
    testWidgets('nothing overflows at ${size.width.toInt()}x'
        '${size.height.toInt()}', (tester) async {
      final List<Json> approvals = [];
      await _openApprove(tester, approvals, size, proposal: _proposal);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Tds194qSettingsDialog(
            api: _Api(),
            permissions:
                _permissions(const ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }
}
