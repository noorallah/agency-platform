// Supplier gifts (BUY-2): recording posts the right body (an asset with its
// account, the owner's without one), taking back sends the reason, and the
// 194R summary renders and flags the suppliers past the limit.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/finance.dart';
import 'package:agency_desktop/models/vendor.dart';
import 'package:agency_desktop/ui/vendors/supplier_gifts_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({bool manage = true}) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': <String>[
      'VENDOR_VIEW',
      if (manage) 'SUPPLIER_GIFT_MANAGE',
    ],
  }));

Json _gift(String status) => <String, dynamic>{
      'id': 'g-1',
      'gift_number': 'SG-0001',
      'gift_date': '2026-10-01',
      'vendor_id': 'v-1',
      'vendor_name': 'Shah Foods',
      'item': 'Wall clock',
      'value': '1500.00',
      'kept_by': 'ASSET',
      'tds_194r_amount': '0',
      'status': status,
      'version': 2,
    };

LedgerAccount _account(String id, String code, String type) =>
    LedgerAccount.fromJson(<String, dynamic>{
      'id': id,
      'code': code,
      'name': 'Account $code',
      'account_type': type,
      'is_active': true,
    });

class _Api extends ApiClient {
  _Api({this.gifts = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> gifts;
  final List<String> requested = <String>[];
  Json? created;
  Json? cancelBody;

  @override
  Future<PagedResult<Vendor>> vendors({
    int page = 1,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    VendorQuery filters = const VendorQuery(),
  }) async =>
      PagedResult<Vendor>(items: [
        Vendor.fromJson(<String, dynamic>{
          'id': 'v-1',
          'code': 'V1',
          'name': 'Shah Foods',
          'display_name': 'Shah Foods',
        }),
      ], total: 1);

  @override
  Future<PagedResult<LedgerAccount>> ledgerAccounts({
    String? accountGroupId,
    bool? isActive,
    bool openToHandJournals = false,
  }) async =>
      PagedResult<LedgerAccount>(items: [
        _account('a-asset', '1500', 'ASSET'),
        _account('a-exp', '5900', 'EXPENSE'),
        _account('a-inc', '4100', 'INCOME'),
      ], total: 3);

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
    if (path.endsWith('/194r-summary')) {
      return <String, dynamic>{
        'data': [
          {
            'vendor_id': 'v-1',
            'vendor_name': 'Shah Foods',
            'gifts': 3,
            'total_value': '65000.00',
            'tds_deducted': '6500.00',
            'over_threshold': true,
            'year_from': '2026-04-01',
            'year_to': '2027-03-31',
          },
          {
            'vendor_id': 'v-2',
            'vendor_name': 'Patel Traders',
            'gifts': 1,
            'total_value': '900.00',
            'tds_deducted': '0',
            'over_threshold': false,
            'year_from': '2026-04-01',
            'year_to': '2027-03-31',
          },
        ],
      };
    }
    if (method == 'POST' && path == '/api/v1/vendors/gifts') {
      created = body;
      return <String, dynamic>{'data': _gift('POSTED')};
    }
    if (path.endsWith('/cancel')) {
      cancelBody = body;
      return <String, dynamic>{'data': _gift('CANCELLED')};
    }
    if (method == 'GET' && path == '/api/v1/vendors/gifts') {
      return <String, dynamic>{'data': gifts};
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('supplier-gifts'),
    );

Future<void> _pump(WidgetTester tester, _Api api, {bool manage = true}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: SupplierGiftsPage(
        api: api,
        preferences: _preferences(),
        permissions: _permissions(manage: manage),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _openDialog(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('toolbar-new')));
  await tester.pumpAndSettle();
}

Future<void> _chooseVendor(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('gift-vendor')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Shah Foods').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an asset gift posts its account', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _openDialog(tester);
    await _chooseVendor(tester);
    await tester.enterText(find.byKey(const ValueKey('gift-item')), 'Clock');
    await tester.enterText(find.byKey(const ValueKey('gift-value')), '1500');
    await tester.enterText(find.byKey(const ValueKey('gift-tds')), '150');

    // Only the asset accounts are offered for "Business asset".
    await tester.tap(find.byKey(const ValueKey('gift-account-ASSET')));
    await tester.pumpAndSettle();
    expect(find.text('1500 · Account 1500'), findsWidgets);
    expect(find.text('5900 · Account 5900'), findsNothing);
    await tester.tap(find.text('1500 · Account 1500').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('gift-save')));
    await tester.pumpAndSettle();

    expect(api.created, {
      'gift_date': api.created!['gift_date'],
      'vendor_id': 'v-1',
      'item': 'Clock',
      'value': '1500',
      'kept_by': 'ASSET',
      'debit_account_id': 'a-asset',
      'tds_194r_amount': '150',
    });
  });

  testWidgets('an owner gift has no account', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _openDialog(tester);
    await _chooseVendor(tester);
    await tester.enterText(find.byKey(const ValueKey('gift-item')), 'Watch');
    await tester.enterText(find.byKey(const ValueKey('gift-value')), '9000');

    await tester.tap(find.byKey(const ValueKey('gift-kept-by')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Owner').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('gift-account-ASSET')), findsNothing);
    expect(find.byKey(const ValueKey('gift-account-OWNER')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('gift-save')));
    await tester.pumpAndSettle();

    expect(api.created!['kept_by'], 'OWNER');
    expect(api.created!.containsKey('debit_account_id'), isFalse);
    expect(api.created!['tds_194r_amount'], '0');
  });

  testWidgets('an asset gift without an account is refused on the form',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _openDialog(tester);
    await _chooseVendor(tester);
    await tester.enterText(find.byKey(const ValueKey('gift-item')), 'Clock');
    await tester.enterText(find.byKey(const ValueKey('gift-value')), '1500');
    await tester.tap(find.byKey(const ValueKey('gift-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('gift-problem')), findsOneWidget);
    expect(api.created, isNull);
  });

  testWidgets('take back posts the reason', (tester) async {
    final _Api api = _Api(gifts: [_gift('POSTED')]);
    await _pump(tester, api);
    await tester.tap(find.text('SG-0001').first);
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('selection-take-back')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Returned to them');
    await tester.tap(find.text('Take back').last);
    await tester.pumpAndSettle();
    expect(api.requested, contains('POST /api/v1/vendors/gifts/g-1/cancel'));
    expect(api.cancelBody, {'reason': 'Returned to them'});
  });

  testWidgets('the 194R summary renders and flags the supplier over the limit',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    expect(api.requested, contains('GET /api/v1/vendors/gifts/194r-summary'));
    await tester.tap(find.text('194R summary'));
    await tester.pumpAndSettle();
    expect(find.text('Shah Foods'), findsOneWidget);
    expect(find.text('Patel Traders'), findsOneWidget);
    expect(find.textContaining('2026-04-01 to 2027-03-31'), findsOneWidget);

    final ColorScheme colors =
        Theme.of(tester.element(find.text('Shah Foods'))).colorScheme;
    Color? colourOf(String text) =>
        tester.widget<Text>(find.text(text).first).style?.color;
    // The row over the limit is drawn in the theme's error colour; the other
    // is not.
    expect(colourOf('65,000.00'), colors.error);
    expect(colourOf('900.00'), isNot(colors.error));
  });

  testWidgets('without the manage permission nothing can be recorded',
      (tester) async {
    await _pump(tester, _Api(gifts: [_gift('POSTED')]), manage: false);
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.text('SG-0001'), findsOneWidget);
  });
}
