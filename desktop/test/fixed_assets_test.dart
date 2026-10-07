// PG-13 desktop: the asset register, asset classes, depreciation runs, the
// Income-tax block schedule, and the capital-goods tick on a bill line. Each
// screen is also pumped at 1366x768 and 800x600 to prove nothing overflows.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/document_preview.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/goods_receipt.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/finance/fixed_assets_pages.dart';
import 'package:agency_desktop/ui/purchase_invoices/purchase_invoice_editor_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> perms) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': perms,
  }));

const List<String> _all = [
  'FIXED_ASSET_VIEW',
  'FIXED_ASSET_MANAGE',
  'JOURNAL_POST',
];

const List<Size> _sizes = [Size(1366, 768), Size(800, 600)];

Json _class(String id, {String code = 'PLANT'}) => <String, dynamic>{
      'id': id,
      'code': code,
      'name': 'Plant and machinery',
      'depreciation_method': 'WDV',
      'rate_percent': '15.0000',
      'useful_life_years': null,
      'residual_percent': '5.0000',
      'it_block_rate_percent': '15.0000',
      'asset_account_id': null,
      'accumulated_depreciation_account_id': null,
      'depreciation_expense_account_id': null,
      'is_active': true,
      'description': null,
      'version': 3,
    };

Json _asset(String id, {String status = 'ACTIVE'}) => <String, dynamic>{
      'id': id,
      'asset_number': 'FA-$id',
      'name': 'Packing machine',
      'asset_class_id': 'c-1',
      'asset_class_code': 'PLANT',
      'asset_class_name': 'Plant and machinery',
      'purchase_invoice_id': null,
      'purchase_invoice_line_id': null,
      'purchase_invoice_number': null,
      'vendor_id': null,
      'acquisition_date': '2026-04-10',
      'put_to_use_date': '2026-04-10',
      'quantity': '1.0000',
      'cost': '100000.00',
      'residual_value': '5000.00',
      'opening_accumulated_depreciation': '0.00',
      'opening_as_of': null,
      'opening_it_wdv': null,
      'accumulated_depreciation': '30000.00',
      'net_book_value': '70000.00',
      'depreciated_to': '2026-09-30',
      'branch_id': null,
      'location': 'Godown 2',
      'status': status,
      'disposed_on': status == 'DISPOSED' ? '2026-10-01' : null,
      'sale_amount': status == 'DISPOSED' ? '60000.00' : null,
      'disposal_method': status == 'DISPOSED' ? 'BANK' : null,
      'disposal_reason': status == 'DISPOSED' ? 'Replaced' : null,
      'disposal_gain_loss': status == 'DISPOSED' ? '-10000.00' : null,
      'remarks': null,
      'version': 4,
    };

Json _run(String id, String status, {String type = 'PERIODIC'}) =>
    <String, dynamic>{
      'id': id,
      'run_number': 'DEP-$id',
      'run_type': type,
      'book': 'COMPANIES_ACT',
      'period_from': '2026-09-01',
      'period_to': '2026-09-30',
      'status': status,
      'total_amount': '1250.00',
      'journal_entry_id': 'je-1',
      'reversal_journal_entry_id': null,
      'posted_at': '2026-10-01T00:00:00Z',
      'remarks': null,
      'cancel_reason': status == 'CANCELLED' ? 'Wrong period' : null,
      'version': 1,
      'lines': [
        {
          'id': 'l-1',
          'fixed_asset_id': '1',
          'asset_number': 'FA-1',
          'asset_name': 'Packing machine',
          'asset_class_id': 'c-1',
          'from_date': '2026-09-01',
          'to_date': '2026-09-30',
          'days': 30,
          'opening_book_value': '71250.00',
          'amount': '1250.00',
        },
      ],
    };

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Map<String, Json?> bodies = <String, Json?>{};
  final List<String> calls = <String>[];
  Json? bill;

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
    final String call = '$method $path';
    calls.add(call);
    bodies[call] = body;
    switch (call) {
      case 'GET /api/v1/fixed-assets/classes':
        return {
          'data': [_class('c-1'), _class('c-2', code: 'FURN')],
          'pagination': {'total_records': 2},
        };
      case 'GET /api/v1/fixed-assets/classes/c-1':
        return {'data': _class('c-1')};
      case 'POST /api/v1/fixed-assets/classes':
        return {'data': _class('c-9', code: 'VEH')};
      case 'PUT /api/v1/fixed-assets/classes/c-1':
        return {'data': _class('c-1')};
      case 'GET /api/v1/fixed-assets':
        return {
          'data': [_asset('1'), _asset('2', status: 'DISPOSED')],
          'pagination': {'total_records': 2},
        };
      case 'GET /api/v1/fixed-assets/1':
        return {'data': _asset('1')};
      case 'POST /api/v1/fixed-assets':
        return {'data': _asset('9')};
      case 'GET /api/v1/fixed-assets/1/schedule':
        return {
          'data': {
            'asset_number': 'FA-1',
            'depreciation_method': 'WDV',
            'cost': '100000.00',
            'residual_value': '5000.00',
            'charged': [
              {
                'from_date': '2026-04-10',
                'to_date': '2026-09-30',
                'days': 174,
                'opening_book_value': '100000.00',
                'amount': '30000.00',
                'accumulated_depreciation': '30000.00',
                'closing_book_value': '70000.00',
                'run_number': 'DEP-1',
                'projected': false,
              },
            ],
            'projected': [
              {
                'from_date': '2026-10-01',
                'to_date': '2027-03-31',
                'days': 182,
                'opening_book_value': '70000.00',
                'amount': '7500.00',
                'accumulated_depreciation': '37500.00',
                'closing_book_value': '62500.00',
                'run_number': null,
                'projected': true,
              },
            ],
          },
        };
      case 'POST /api/v1/fixed-assets/1/dispose':
        return {'data': _asset('1', status: 'DISPOSED')};
      case 'GET /api/v1/fixed-assets/depreciation-runs':
        return {
          'data': [_run('1', 'POSTED'), _run('2', 'CANCELLED')],
          'pagination': {'total_records': 2},
        };
      case 'GET /api/v1/fixed-assets/depreciation-runs/1':
        return {'data': _run('1', 'POSTED')};
      case 'GET /api/v1/fixed-assets/depreciation-runs/2':
        return {'data': _run('2', 'CANCELLED')};
      case 'POST /api/v1/fixed-assets/depreciation-runs':
        return {'data': _run('7', 'POSTED')};
      case 'POST /api/v1/fixed-assets/depreciation-runs/1/cancel':
        return {'data': _run('1', 'CANCELLED')};
      case 'GET /api/v1/finance/financial-years':
        return {
          'data': [
            {
              'id': 'fy-1',
              'code': 'FY2026-27',
              'name': 'FY 2026-27',
              'starts_on': '2026-04-01',
              'ends_on': '2027-03-31',
              'is_active': true,
              'is_locked': false,
            },
          ],
        };
      case 'GET /api/v1/fixed-assets/reports/it-block-schedule':
        return {
          'data': {
            'financial_year_id': 'fy-1',
            'starts_on': '2026-04-01',
            'ends_on': '2027-03-31',
            'blocks': [
              {
                'block_rate': '15.0000',
                'class_names': ['Plant and machinery'],
                'opening_wdv': '200000.00',
                'additions_full_rate': '80000.00',
                'additions_half_rate': '20000.00',
                'additions': '100000.00',
                'disposals': '0.00',
                'depreciation_full_rate': '42000.00',
                'depreciation_half_rate': '1500.00',
                'depreciation': '43500.00',
                'closing_wdv': '256500.00',
                'short_term_capital_gain': '0.00',
              },
            ],
          },
        };
    }
    return {'data': const <dynamic>[]};
  }

  @override
  Future<PurchaseInvoicePreviewRecord> previewPurchaseInvoice(Json data) async =>
      PurchaseInvoicePreviewRecord.fromJson({
        'invoice': {
          'invoice_number': 'PI-9',
          'subtotal': '1000.00',
          'tax_total': '0.00',
          'grand_total': '1000.00',
          'lines': <Json>[],
        },
        'interstate': false,
        'lines': <Json>[],
      });

  @override
  Future<Json> createPurchaseInvoice(Json body) async {
    bill = body;
    return {
      'data': {'id': 'pi-1', 'invoice_number': 'PI-1', 'status': 'DRAFT'}
    };
  }
}

void _size(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _pump(
  WidgetTester tester,
  _Api api,
  Size size,
  Widget Function(DesktopPreferencesService prefs, PermissionService perms)
      page, {
  List<String> perms = _all,
}) async {
  _size(tester, size);
  final DesktopPreferencesService preferences = DesktopPreferencesService(
    directory: Directory.systemTemp.createTempSync('fixed-assets'),
  );
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(body: page(preferences, _permissions(perms))),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pumpRegister(WidgetTester tester, _Api api, Size size,
        {List<String> perms = _all}) =>
    _pump(
      tester,
      api,
      size,
      (p, perms) => AssetRegisterPage(
        api: api,
        preferences: p,
        permissions: perms,
        hasActiveFirm: true,
      ),
      perms: perms,
    );

Future<void> _pumpClasses(WidgetTester tester, _Api api, Size size) => _pump(
      tester,
      api,
      size,
      (p, perms) => AssetClassesPage(
        api: api,
        preferences: p,
        permissions: perms,
        hasActiveFirm: true,
      ),
    );

Future<void> _pumpRuns(WidgetTester tester, _Api api, Size size,
        {List<String> perms = _all}) =>
    _pump(
      tester,
      api,
      size,
      (p, perms) => DepreciationRunsPage(
        api: api,
        preferences: p,
        permissions: perms,
        hasActiveFirm: true,
      ),
      perms: perms,
    );

Future<void> _pumpReport(WidgetTester tester, _Api api, Size size) => _pump(
      tester,
      api,
      size,
      (p, perms) => ItBlockSchedulePage(
        api: api,
        permissions: perms,
        hasActiveFirm: true,
      ),
    );

/// A command of the selection bar, which is where a picked row's actions are.
Future<void> _command(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey('selection-$id')));
  await tester.pumpAndSettle();
}

/// Taps a row and waits out the double-tap window, so the selection bar shows.
Future<void> _pick(WidgetTester tester, String text) async {
  await tester.tap(find.text(text));
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

Future<void> _enter(WidgetTester tester, String key, String text) async {
  final Finder box = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(box);
  await tester.enterText(box, text);
  await tester.pump();
}

Future<void> _tapKey(WidgetTester tester, String key) async {
  final Finder f = find.byKey(ValueKey<String>(key));
  await tester.ensureVisible(f);
  await tester.tap(f);
  await tester.pumpAndSettle();
}

GoodsReceiptRecord _receipt() => GoodsReceiptRecord.fromJson({
      'id': 'grn-1',
      'grn_number': 'GRN-2026-000001',
      'receipt_date': '2026-08-10',
      'status': 'COMPLETED',
      'vendor_id': 'vendor-1',
      'vendor_name': 'Acme Machines',
      'branch_id': 'branch-1',
      'lines': [
        {
          'id': 'grn-line-1',
          'line_number': 1,
          'product_id': 'prod-1',
          'description': 'Packing machine',
          'accepted_quantity': '1',
          'unit_price': '100000',
          'purchase_uom_id': 'uom-box',
          'warehouse_id': 'wh-1',
          'tax_profile_id': 'tax-1',
        },
      ],
    });

Future<void> _pumpBill(WidgetTester tester, _Api api, Size size) async {
  _size(tester, size);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: PurchaseInvoiceEditorDialog(
          api: api,
          receipts: [_receipt()],
          vendors: [
            Vendor.fromJson({
              'id': 'vendor-1',
              'firm_id': 'firm-1',
              'code': 'V001',
              'name': 'Acme Machines',
              'display_name': 'Acme Machines',
              'status': 'ACTIVE',
              'addresses': <Json>[],
              'contacts': <Json>[],
              'bank_accounts': <Json>[],
              'tax_details': <Json>[],
              'notes': <Json>[],
            }),
          ],
          products: [
            Product.fromJson({
              'id': 'prod-1',
              'code': 'SKU-1',
              'name': 'Packing machine',
            }),
          ],
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  await tester
      .tap(find.byKey(const ValueKey('purchase-invoice-receipt-supplier')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Acme Machines').last);
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pumpAndSettle();
}

void main() {
  group('Asset register', () {
    testWidgets('renders the net book value', (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768));
      expect(find.text('FA-1'), findsOneWidget);
      expect(find.text('FA-2'), findsOneWidget);
      expect(find.text('70,000.00'), findsNWidgets(2));
      expect(find.text('Net book value'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('add sends the declared fields and no vendor or branch',
        (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768));
      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();

      await _enter(tester, 'asset-name', 'Forklift');
      await _tapKey(tester, 'asset-class');
      await tester.tap(find.text('PLANT · Plant and machinery').last);
      await tester.pumpAndSettle();
      await _enter(tester, 'asset-cost', '250000');
      await _enter(tester, 'asset-opening-dep', '50000');
      await _tapKey(tester, 'asset-save');
      // Depreciation so far is given without the date it is up to.
      expect(api.bodies['POST /api/v1/fixed-assets'], isNull);
      expect(find.byKey(const ValueKey('asset-problem')), findsOneWidget);

      await _enter(tester, 'asset-opening-dep', '');
      await _enter(tester, 'asset-location', 'Yard');
      await _tapKey(tester, 'asset-save');

      final Json sent = api.bodies['POST /api/v1/fixed-assets']!;
      expect(sent['name'], 'Forklift');
      expect(sent['asset_class_id'], 'c-1');
      expect(sent['cost'], '250000');
      expect(sent['quantity'], '1');
      expect(sent['location'], 'Yard');
      expect(sent.containsKey('residual_value'), isFalse);
      expect(sent.containsKey('opening_accumulated_depreciation'), isFalse);
      expect(sent.containsKey('vendor_id'), isFalse);
      expect(sent.containsKey('branch_id'), isFalse);
    });

    testWidgets('a change sends only what changed', (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768));
      await _pick(tester, 'FA-1');
      await _command(tester, 'view');
      await _enter(tester, 'asset-location', 'Godown 3');
      await _tapKey(tester, 'asset-save');
      expect(api.bodies['PUT /api/v1/fixed-assets/1'], {'location': 'Godown 3'});
    });

    testWidgets('dispose sends the date, amount, method and a reason',
        (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768));
      await _pick(tester, 'FA-1');
      await _command(tester, 'dispose');

      // A reason is required.
      await _tapKey(tester, 'dispose-confirm');
      expect(api.bodies['POST /api/v1/fixed-assets/1/dispose'], isNull);
      expect(find.byKey(const ValueKey('dispose-problem')), findsOneWidget);

      await _enter(tester, 'dispose-sale', '60000');
      await _enter(tester, 'dispose-reason', 'Replaced by a new line');
      await _tapKey(tester, 'dispose-method');
      await tester.tap(find.text('Cash').last);
      await tester.pumpAndSettle();
      await _tapKey(tester, 'dispose-confirm');

      final Json sent = api.bodies['POST /api/v1/fixed-assets/1/dispose']!;
      expect(sent['sale_amount'], '60000');
      expect(sent['method'], 'CASH');
      expect(sent['reason'], 'Replaced by a new line');
      expect(sent['disposal_date'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
      expect(sent.keys.toSet(),
          {'disposal_date', 'sale_amount', 'method', 'reason'});
    });

    testWidgets('the schedule lists charged and projected years',
        (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768));
      await _pick(tester, 'FA-1');
      await _command(tester, 'schedule');
      expect(find.byKey(const ValueKey('schedule-table')), findsOneWidget);
      expect(find.text('DEP-1'), findsOneWidget);
      expect(find.text('Projected'), findsOneWidget);
    });

    testWidgets('without FIXED_ASSET_MANAGE there is no add or dispose',
        (tester) async {
      final _Api api = _Api();
      await _pumpRegister(tester, api, const Size(1366, 768),
          perms: const ['FIXED_ASSET_VIEW']);
      expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
      await _pick(tester, 'FA-1');
      expect(find.byKey(const ValueKey('selection-dispose')), findsNothing);
      expect(find.byKey(const ValueKey('selection-delete')), findsNothing);
    });

    for (final Size size in _sizes) {
      testWidgets('does not overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}, nor do its dialogs', (tester) async {
        final _Api api = _Api();
        await _pumpRegister(tester, api, size);
        expect(tester.takeException(), isNull);
        await tester.tap(find.byKey(const ValueKey('toolbar-new')));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await _tapKey(tester, 'asset-close');
        await _pick(tester, 'FA-1');
        await _command(tester, 'dispose');
        expect(tester.takeException(), isNull);
        await tester.tap(find.text('Cancel').last);
        await tester.pumpAndSettle();
        await _command(tester, 'schedule');
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Asset classes', () {
    testWidgets('the list renders', (tester) async {
      await _pumpClasses(tester, _Api(), const Size(1366, 768));
      expect(find.text('PLANT'), findsOneWidget);
      expect(find.text('FURN'), findsOneWidget);
    });

    testWidgets('create sends the declared fields', (tester) async {
      final _Api api = _Api();
      await _pumpClasses(tester, api, const Size(1366, 768));
      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();
      await _enter(tester, 'class-code', 'VEH');
      await _enter(tester, 'class-name', 'Vehicles');
      // Neither a rate nor a life: refused.
      await _tapKey(tester, 'class-save');
      expect(api.bodies['POST /api/v1/fixed-assets/classes'], isNull);
      expect(find.byKey(const ValueKey('class-problem')), findsOneWidget);

      await _enter(tester, 'class-life', '8');
      await _tapKey(tester, 'class-save');
      final Json sent = api.bodies['POST /api/v1/fixed-assets/classes']!;
      expect(sent['code'], 'VEH');
      expect(sent['depreciation_method'], 'SLM');
      expect(sent['useful_life_years'], '8');
      expect(sent['residual_percent'], '5');
      expect(sent['is_active'], true);
      expect(sent.containsKey('rate_percent'), isFalse);
    });

    testWidgets('a change sends only what changed', (tester) async {
      final _Api api = _Api();
      await _pumpClasses(tester, api, const Size(1366, 768));
      await _pick(tester, 'PLANT');
      await _command(tester, 'view');
      await _enter(tester, 'class-name', 'Machinery');
      await _tapKey(tester, 'class-save');
      expect(api.bodies['PUT /api/v1/fixed-assets/classes/c-1'],
          {'name': 'Machinery'});
    });

    for (final Size size in _sizes) {
      testWidgets('editor does not overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}', (tester) async {
        await _pumpClasses(tester, _Api(), size);
        await tester.tap(find.byKey(const ValueKey('toolbar-new')));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Depreciation runs', () {
    testWidgets('lists the runs', (tester) async {
      await _pumpRuns(tester, _Api(), const Size(1366, 768));
      expect(find.text('DEP-1'), findsOneWidget);
      expect(find.text('DEP-2'), findsOneWidget);
      expect(find.text('1250.00'), findsNWidgets(2));
    });

    testWidgets('the run dialog posts the period', (tester) async {
      final _Api api = _Api();
      await _pumpRuns(tester, api, const Size(1366, 768));
      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();
      await _enter(tester, 'run-remarks', 'September');
      await _tapKey(tester, 'run-confirm');
      final Json sent = api.bodies['POST /api/v1/fixed-assets/depreciation-runs']!;
      expect(sent['period_from'], matches(RegExp(r'^\d{4}-\d{2}-01$')));
      expect(sent['period_to'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
      expect(sent['book'], 'COMPANIES_ACT');
      expect(sent['remarks'], 'September');
      expect(sent.keys.toSet(),
          {'period_from', 'period_to', 'book', 'remarks'});
    });

    testWidgets('a run opens with its lines', (tester) async {
      await _pumpRuns(tester, _Api(), const Size(1366, 768));
      await _pick(tester, 'DEP-1');
      await _command(tester, 'view');
      expect(find.byKey(const ValueKey('run-lines')), findsOneWidget);
      expect(find.text('Packing machine'), findsOneWidget);
    });

    testWidgets('cancel asks for a reason and sends it', (tester) async {
      final _Api api = _Api();
      await _pumpRuns(tester, api, const Size(1366, 768));
      await _pick(tester, 'DEP-1');
      await _command(tester, 'cancel');
      await tester.enterText(find.byType(TextField).last, 'Wrong period');
      await tester.pump();
      await tester.tap(find.text('Cancel the run'));
      await tester.pumpAndSettle();
      expect(api.bodies['POST /api/v1/fixed-assets/depreciation-runs/1/cancel'],
          {'reason': 'Wrong period'});
    });

    testWidgets('without JOURNAL_POST there is no run or cancel',
        (tester) async {
      await _pumpRuns(tester, _Api(), const Size(1366, 768),
          perms: const ['FIXED_ASSET_VIEW', 'FIXED_ASSET_MANAGE']);
      expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
      await _pick(tester, 'DEP-1');
      expect(find.byKey(const ValueKey('selection-cancel')), findsNothing);
    });

    for (final Size size in _sizes) {
      testWidgets('does not overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}', (tester) async {
        await _pumpRuns(tester, _Api(), size);
        expect(tester.takeException(), isNull);
        await tester.tap(find.byKey(const ValueKey('toolbar-new')));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await tester.tap(find.text('Cancel').last);
        await tester.pumpAndSettle();
        await _pick(tester, 'DEP-1');
        await _command(tester, 'view');
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('Income-tax block schedule', () {
    testWidgets('renders the blocks of the chosen year', (tester) async {
      final _Api api = _Api();
      await _pumpReport(tester, api, const Size(1366, 768));
      expect(api.calls, contains('GET /api/v1/fixed-assets/reports/it-block-schedule'));
      expect(find.byKey(const ValueKey('it-block-table')), findsOneWidget);
      expect(find.text('256500.00'), findsOneWidget);
      expect(find.text('Plant and machinery'), findsOneWidget);
    });

    for (final Size size in _sizes) {
      testWidgets('does not overflow at ${size.width.toInt()}x'
          '${size.height.toInt()}', (tester) async {
        await _pumpReport(tester, _Api(), size);
        expect(tester.takeException(), isNull);
      });
    }
  });

  group('capital goods on a bill line', () {
    testWidgets('the tick sends is_capital_goods and the class',
        (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, const Size(1600, 900));
      // Nothing is read or sent until the tick.
      expect(api.calls, isNot(contains('GET /api/v1/fixed-assets/classes')));
      await _tapKey(tester, 'purchase-invoice-capital-grn-1-0');
      expect(api.calls, contains('GET /api/v1/fixed-assets/classes'));

      await tester.enterText(
          find.byKey(const ValueKey('purchase-invoice-supplier-number-0')),
          'AM-1');
      await tester.pumpAndSettle();

      // Required once ticked.
      await _tapKey(tester, 'purchase-invoice-save');
      expect(api.bill, isNull);
      expect(find.textContaining('choose the asset class'), findsWidgets);

      await _tapKey(tester, 'purchase-invoice-asset-class-grn-1-0');
      await tester.tap(find.text('PLANT · Plant and machinery').last);
      await tester.pumpAndSettle();
      await _tapKey(tester, 'purchase-invoice-save');

      final Json line = (api.bill!['lines'] as List).first as Json;
      expect(line['is_capital_goods'], true);
      expect(line['asset_class_id'], 'c-1');
    });

    testWidgets('an unticked line sends neither key', (tester) async {
      final _Api api = _Api();
      await _pumpBill(tester, api, const Size(1600, 900));
      await tester.enterText(
          find.byKey(const ValueKey('purchase-invoice-supplier-number-0')),
          'AM-2');
      await tester.pumpAndSettle();
      await _tapKey(tester, 'purchase-invoice-save');
      final Json line = (api.bill!['lines'] as List).first as Json;
      expect(line.containsKey('is_capital_goods'), isFalse);
      expect(line.containsKey('asset_class_id'), isFalse);
    });
  });
}
