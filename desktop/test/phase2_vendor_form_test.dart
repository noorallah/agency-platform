// The vendor record in the phase 2 app (2026-09-26): a full-page tab with
// every section in one scroll, as the customer record the owner approved.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/geography.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/vendors/vendor_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions() => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>['VENDOR_VIEW', 'VENDOR_CREATE', 'VENDOR_UPDATE'],
  }));

Json _vendorJson({
  List<Json> addresses = const <Json>[],
  List<Json> contacts = const <Json>[],
  List<Json> bankAccounts = const <Json>[],
  List<Json> taxDetails = const <Json>[],
  List<Json> notes = const <Json>[],
}) =>
    <String, dynamic>{
      'id': 'v-1',
      'firm_id': 'firm-1',
      'code': 'V001',
      'name': 'Supplier One',
      'display_name': 'Supplier One',
      'status': 'ACTIVE',
      'payment_terms_days': 30,
      'udyam_number': 'UDYAM-TN-01-1234567',
      'msme_category': 'SMALL',
      'default_tds_section': '194C',
      'msme_written_agreement': true,
      'issues_e_invoices': true,
      'addresses': addresses,
      'contacts': contacts,
      'bank_accounts': bankAccounts,
      'tax_details': taxDetails,
      'notes': notes,
    };

class _VendorApi extends ApiClient {
  _VendorApi({this.rows = const <Json>[]})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  Json? saved;

  /// L5: the firm's buying switch for boxes and pieces.
  bool boxAndPieces = false;

  /// The filters the list was last read with.
  VendorQuery? lastFilters;

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async =>
      PurchaseWorkflowSettings.fromJson(<String, dynamic>{
        'purchase_order_stage': true,
        'goods_receipt_stage': true,
        'is_configured': true,
        'box_and_piece_entry': boxAndPieces,
      });

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async {
    lastFilters = filters;
    return PagedResult<Vendor>(
      items: <Vendor>[for (final Json row in rows) Vendor.fromJson(row)],
      total: rows.length,
    );
  }

  @override
  Future<List<GeoPlaceRecord>> geoPlaces(
    GeoLevel level, {
    String parentId = '',
  }) async =>
      switch (level) {
        GeoLevel.country => <GeoPlaceRecord>[
            GeoPlaceRecord.fromJson(level, <String, dynamic>{
              'id': 'c-in',
              'code': 'IN',
              'name': 'India',
            }),
          ],
        _ => const <GeoPlaceRecord>[],
      };

  /// When set, the next create is refused with it.
  ApiException? refuseCreate;

  @override
  Future<Vendor> createVendor(Json data) async {
    final ApiException? refusal = refuseCreate;
    if (refusal != null) {
      refuseCreate = null;
      throw refusal;
    }
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }

  @override
  Future<Vendor> updateVendor(
    String id,
    Json data, {
    int? expectedVersion,
  }) async {
    saved = data;
    return Vendor.fromJson(_vendorJson());
  }
}

void main() {
  testWidgets('phase 2 shows the whole vendor on one page and saves it',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi(rows: <Json>[
      _vendorJson(
        bankAccounts: <Json>[
          <String, dynamic>{
            'id': 'bk-1',
            'bank_name': 'State Bank',
            'account_name': 'Supplier One',
            'account_number': '000123456789',
            'ifsc': 'SBIN0001234',
            'is_primary': true,
          },
        ],
      ),
    ]);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('V001').first);
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    // Option C (owner, 2026-09-27): the bar names the supplier picked.
    expect(find.byKey(const ValueKey('selection-bar')), findsOneWidget);
    expect(find.textContaining('V001 ·'), findsOneWidget);
    await tester.tap(find.byTooltip('Edit').first);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // No tabs: the bank account sits on the same page as the name.
    expect(find.text('Vendor Name'), findsOneWidget);
    expect(find.text('Account number'), findsOneWidget);
    // The side panel says where they are paid.
    expect(find.text('State Bank · SBIN0001234'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved?['code'], 'V001');
    expect(api.saved?['banking'], hasLength(1));
    // Terms and MSME standing go back as they came (backlog 68 rows 1-2).
    expect(api.saved?['payment_terms_days'], 30);
    expect(api.saved?['udyam_number'], 'UDYAM-TN-01-1234567');
    expect(api.saved?['msme_category'], 'SMALL');
    expect(api.saved?['default_tds_section'], '194C');
    expect(api.saved?['msme_written_agreement'], isTrue);
    // The e-invoicing flag goes back as it came (backlog 78 row 5).
    expect(api.saved?['issues_e_invoices'], isTrue);
  });

  testWidgets('a blocked supplier shows and keeps why (backlog 69 row 4)',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi(rows: <Json>[
      <String, dynamic>{
        ..._vendorJson(),
        'status': 'BLOCKED',
        'blocked_reason': 'Quality complaints',
      },
    ]);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions: _permissions(),
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

    expect(find.text('Quality complaints'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved?['status'], 'BLOCKED');
    expect(api.saved?['blocked_reason'], 'Quality complaints');
  });

  testWidgets('a new vendor with a blank code is saved without one (MST-5)',
      (tester) async {
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New vendor'));
    await tester.pumpAndSettle();
    expect(find.text('Blank: issued on save'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextField, 'Vendor Name'),
      'Supplier Two',
    );
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(api.saved, isNotNull);
    expect(api.saved!.containsKey('code'), isFalse);
  });

  testWidgets('a refused save names the field, not only "validation failed"',
      (tester) async {
    // MST-VN-010: an empty Save said only "The request validation failed.";
    // and a refusal the server names a field for kept the name to itself.
    tester.view.physicalSize = const Size(1600, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _VendorApi api = _VendorApi();
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => Phase2Scope(child: child!),
      home: Scaffold(
        body: VendorManagementPage(
          api: api,
          permissions: _permissions(),
          hasActiveFirm: true,
        ),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('New vendor'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(find.text('Vendor name is required.'), findsOneWidget);
    expect(api.saved, isNull);

    api.refuseCreate = const ApiException(
      'The request validation failed.',
      statusCode: 422,
      details: <Object>[
        <String, dynamic>{
          'field': 'body.gstin',
          'message': 'Value error, A GSTIN is 15 characters.',
        },
      ],
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Vendor Name'),
      'Supplier Two',
    );
    await tester.tap(find.byKey(const ValueKey('vendor-save')));
    await tester.pumpAndSettle();
    expect(
      find.text('The request validation failed.\n'
          'gstin: Value error, A GSTIN is 15 characters.'),
      findsOneWidget,
    );
    expect(api.saved, isNull);
  });

  group('the TDS switch (backlog 113)', () {
    Future<_VendorApi> pump(WidgetTester tester, {List<Json>? rows}) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _VendorApi api = _VendorApi(rows: rows ?? const <Json>[]);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: VendorManagementPage(
            api: api,
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    final Finder control = find.byKey(const ValueKey('vendor-tds-applicable'));

    testWidgets('a new supplier sends true, and off sends false',
        (tester) async {
      final _VendorApi api = await pump(tester);
      await tester.tap(find.text('New vendor'));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Vendor Name'), 'Supplier Two');
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.saved!['tds_applicable'], true);

      api.saved = null;
      await tester.tap(find.text('New vendor'));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Vendor Name'), 'Supplier Three');
      await tester.ensureVisible(control);
      await tester.tap(control);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.saved!['tds_applicable'], false);
    });

    testWidgets('a supplier whose record says off shows it off',
        (tester) async {
      await pump(tester, rows: <Json>[
        _vendorJson()..['tds_applicable'] = false,
      ]);
      await tester.tap(find.text('V001').first);
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Edit').first);
      await tester.pumpAndSettle();
      await tester.ensureVisible(control);
      expect(tester.widget<CheckboxListTile>(control).value, false);
    });
  });

  group('L5: buys in boxes and pieces', () {
    Future<_VendorApi> pump(
      WidgetTester tester, {
      required bool on,
      List<Json> rows = const <Json>[],
    }) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _VendorApi api = _VendorApi(rows: rows)..boxAndPieces = on;
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: VendorManagementPage(
            api: api,
            permissions: _permissions(),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    const ValueKey<String> tick = ValueKey('vendor-box-and-piece-entry');

    testWidgets('with the buying switch on the tick is shown and sent',
        (tester) async {
      final _VendorApi api = await pump(tester, on: true);
      await tester.tap(find.text('New vendor'));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Vendor Name'), 'Supplier Two');
      await tester.ensureVisible(find.byKey(tick));
      expect(find.text('Buys in boxes and pieces'), findsOneWidget);
      await tester.tap(find.byKey(tick));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.saved!['box_and_piece_entry'], isTrue);
    });

    testWidgets('the supplier list filters by the mark', (tester) async {
      final _VendorApi api =
          await pump(tester, on: true, rows: <Json>[_vendorJson()]);
      await tester.tap(find.text('+ filter'));
      await tester.pumpAndSettle();
      await tester
          .tap(find.byKey(const ValueKey('vendor-filter-box-and-pieces')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Yes').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Apply'));
      await tester.pumpAndSettle();
      expect(api.lastFilters!.toQuery()['box_and_piece_entry'], 'true');
    });

    testWidgets('with the switch off there is no tick and nothing is sent',
        (tester) async {
      final _VendorApi api = await pump(tester, on: false);
      await tester.tap(find.text('New vendor'));
      await tester.pumpAndSettle();
      await tester.enterText(
          find.widgetWithText(TextField, 'Vendor Name'), 'Supplier Two');
      expect(find.byKey(tick), findsNothing);
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.saved!.containsKey('box_and_piece_entry'), isFalse);
    });
  });

  group('D-UI-113: a supplier opens read-only without VENDOR_UPDATE', () {
    Future<_VendorApi> pump(WidgetTester tester, List<String> codes) async {
      tester.view.physicalSize = const Size(1600, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final _VendorApi api = _VendorApi(rows: <Json>[_vendorJson()]);
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => Phase2Scope(child: child!),
        home: Scaffold(
          body: VendorManagementPage(
            api: api,
            permissions: PermissionService()
              ..applyAccessToken(_accessToken({
                'roles': <String>['user'],
                'permissions': codes,
              })),
            hasActiveFirm: true,
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    Future<void> openRow(WidgetTester tester) async {
      await tester.tap(find.text('V001').first);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('V001').first);
      await tester.pumpAndSettle();
    }

    final Finder name = find.widgetWithText(TextField, 'Vendor Name');
    final Finder tds = find.byKey(const ValueKey('vendor-tds-applicable'));

    testWidgets('a viewer opens the record with every field disabled',
        (tester) async {
      final _VendorApi api = await pump(tester, <String>['VENDOR_VIEW']);
      await openRow(tester);
      expect(tester.takeException(), isNull);

      expect(name, findsOneWidget);
      expect(tester.widget<TextField>(name).readOnly, isTrue);
      expect(find.byKey(const ValueKey('vendor-save')), findsNothing);
      expect(find.text('Close'), findsOneWidget);
      expect(find.text('View only'), findsOneWidget);
      expect(find.text('Add contact(s)'), findsNothing);
      expect(find.text('Add address'), findsNothing);
      await tester.ensureVisible(tds);
      expect(tester.widget<CheckboxListTile>(tds).onChanged, isNull);

      // Ctrl+S saves nothing either.
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(LogicalKeyboardKey.keyS);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pumpAndSettle();
      expect(api.saved, isNull);
    });

    testWidgets('an editor still opens it to edit and save', (tester) async {
      final _VendorApi api =
          await pump(tester, <String>['VENDOR_VIEW', 'VENDOR_UPDATE']);
      await openRow(tester);

      expect(tester.widget<TextField>(name).readOnly, isFalse);
      expect(find.text('View only'), findsNothing);
      await tester.ensureVisible(tds);
      expect(tester.widget<CheckboxListTile>(tds).onChanged, isNotNull);
      await tester.tap(find.byKey(const ValueKey('vendor-save')));
      await tester.pumpAndSettle();
      expect(api.saved?['code'], 'V001');
    });
  });
}
