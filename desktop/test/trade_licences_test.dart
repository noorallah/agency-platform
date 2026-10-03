// Backlog 54: the trade licence register, its types, and the Home alert.
//
// These pin the register's own screen (columns, standing shown with a
// status badge), the dialog's cross-field rule that a licence whose type
// runs out cannot be saved with no valid-to date, and the Home tile that
// counts what `GET /trade-licences/expiring` returns.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/trade_licence.dart';
import 'package:agency_desktop/phase2/home_page.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _LicenceApi extends ApiClient {
  _LicenceApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<(String, Json)> writes = <(String, Json)>[];
  final List<String> requested = <String>[];

  static const Json _drugLicence = {
    'id': 'lic-1',
    'version': 1,
    'licence_type_id': 'type-drug',
    'licence_type_code': 'DRUG',
    'licence_type_name': 'Drug Licence',
    'holder_type': 'FIRM',
    'branch_id': null,
    'customer_id': null,
    'vendor_id': null,
    'holder_name': 'Firm',
    'licence_number': 'DL-001',
    'issued_by': 'FDA',
    'valid_from': '2026-01-01',
    'valid_to': '2026-10-05',
    'premises': null,
    'remarks': null,
    'standing': 'EXPIRING',
    'days_to_expiry': 5,
  };

  static const Json _shopLicence = {
    'id': 'lic-2',
    'version': 1,
    'licence_type_id': 'type-shop',
    'licence_type_code': 'SHOP',
    'licence_type_name': 'Shop Act',
    'holder_type': 'CUSTOMER',
    'branch_id': null,
    'customer_id': 'cust-1',
    'vendor_id': null,
    'holder_name': 'Sri Traders',
    'licence_number': 'SA-100',
    'issued_by': null,
    'valid_from': null,
    'valid_to': null,
    'premises': null,
    'remarks': null,
    'standing': 'NO_EXPIRY_RECORDED',
    'days_to_expiry': null,
  };

  static const List<Json> _types = [
    {
      'id': 'type-drug',
      'version': 1,
      'code': 'DRUG',
      'name': 'Drug Licence',
      'form_numbers': null,
      'expires': true,
      'is_active': true,
      'description': null,
    },
    {
      'id': 'type-shop',
      'version': 1,
      'code': 'SHOP',
      'name': 'Shop Act',
      'form_numbers': null,
      'expires': false,
      'is_active': true,
      'description': null,
    },
  ];

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
    if (method != 'GET') {
      writes.add((path, Map<String, dynamic>.from(body ?? const {})));
      return {
        'data': {'id': 'lic-new', ...?body},
      };
    }
    if (path == '/api/v1/trade-licences/types') {
      return {'data': _types};
    }
    if (path == '/api/v1/trade-licences/expiring') {
      return {
        'data': [_drugLicence],
      };
    }
    if (path == '/api/v1/trade-licences') {
      return {
        'data': [_drugLicence, _shopLicence],
      };
    }
    return {'data': const <dynamic>[]};
  }
}

PermissionService _permissions() {
  final String claims = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': <String>['TRADE_LICENCE_VIEW', 'TRADE_LICENCE_MANAGE'],
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$claims.sig');
}

Future<void> _pumpRegister(WidgetTester tester, _LicenceApi api) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1600, 900);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: ResourceManagementPage<TradeLicenceRecord>(
        api: api,
        definition: tradeLicenceDefinition(api, _permissions()),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

class _HomeSource implements HomeSource {
  _HomeSource({this.expiring = 0});
  final int expiring;

  @override
  Future<List<Map<String, dynamic>>> invoiceRegister(
          DateTime from, DateTime to) async =>
      const [];

  @override
  Future<List<Map<String, dynamic>>> customerOutstanding() async => const [];

  @override
  Future<int> itemsBelowReorder() async => 0;

  @override
  Future<double> receiptsOn(DateTime day) async => 0;

  @override
  Future<int> batchesExpiringIn30Days() async => 0;

  @override
  Future<int> expiringLicences() async => expiring;

  @override
  Future<Map<String, dynamic>> stockAlerts() async => const {};

  @override
  Future<List<Map<String, dynamic>>> taxCalendar() async => const [];

  @override
  Future<void> markGstReturnFiled(Map<String, dynamic> body) async {}

  @override
  Future<void> withdrawGstReturnFiling(String id) async {}

  @override
  Future<Map<String, dynamic>> summary(String path) async => const {};
}

void main() {
  test('Masters declares both screens', () {
    final Set<String> ids =
        ModuleCatalog.byId(AppModule.masters).tabs.map((tab) => tab.id).toSet();
    expect(ids, containsAll(['trade-licences', 'licence-types']));
  });

  test('the phase 2 menu places both screens', () {
    final Set<String> placed = {
      for (final MenuAreaSpec area in MenuLayout.all)
        for (final MenuItemSpec item in area.items) item.path,
    };
    expect(placed, containsAll(['masters/trade-licences', 'masters/licence-types']));
  });

  testWidgets(
      'the register lists type, holder, standing and days to expiry, '
      'expiring shown as a warning', (tester) async {
    final _LicenceApi api = _LicenceApi();
    await _pumpRegister(tester, api);

    expect(find.text('Drug Licence'), findsOneWidget);
    expect(find.text('DL-001'), findsOneWidget);
    expect(find.text('Firm'), findsOneWidget);
    expect(find.text('Sri Traders'), findsOneWidget);
    expect(find.text('EXPIRING'), findsOneWidget);
    expect(find.text('5'), findsOneWidget);
    expect(find.text('NO_EXPIRY_RECORDED'), findsOneWidget);

    // The Status column is shown with StatusBadge -- expired reads as an
    // error and expiring as a warning, not the same undifferentiated chip.
    final StatusBadge expiring = tester.widget<StatusBadge>(
      find.widgetWithText(StatusBadge, 'EXPIRING'),
    );
    expect(expiring.tone, StatusBadgeTone.warning);
    final StatusBadge noExpiry = tester.widget<StatusBadge>(
      find.widgetWithText(StatusBadge, 'NO_EXPIRY_RECORDED'),
    );
    expect(noExpiry.tone, isNot(StatusBadgeTone.warning));
  });

  testWidgets(
      'a licence whose type runs out cannot be saved with no valid-to date',
      (tester) async {
    final _LicenceApi api = _LicenceApi();
    await _pumpRegister(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();

    // The type chip: `optionsResource` submits the id, and a single-selection
    // chip shows the code and the name together.
    await tester.tap(find.text('DRUG · Drug Licence'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Licence number'),
      'DL-777',
    );
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(find.textContaining('runs out'), findsWidgets);
    expect(api.writes, isEmpty,
        reason: 'the missing valid-to date must be refused before anything '
            'is sent');
  });

  testWidgets('a licence type that never expires needs no valid-to date',
      (tester) async {
    final _LicenceApi api = _LicenceApi();
    await _pumpRegister(tester, api);

    await tester.tap(find.widgetWithText(FilledButton, 'New').hitTestable());
    await tester.pumpAndSettle();
    await tester.tap(find.text('SHOP · Shop Act'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Licence number'),
      'SA-777',
    );
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    final (String path, Json body) = api.writes.single;
    expect(path, '/api/v1/trade-licences');
    expect(body['licence_type_id'], 'type-shop');
    expect(body['holder_type'], 'FIRM');
    expect(body['licence_number'], 'SA-777');
    expect(body['customer_id'], isNull);
    expect(body['vendor_id'], isNull);
  });

  group('Home', () {
    Future<List<String>> pumpHome(
      WidgetTester tester, {
      required bool allowed,
      int expiring = 3,
    }) async {
      final List<String> opened = [];
      tester.view.physicalSize = const Size(1366, 768);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Phase2HomePage(
            firmName: 'Test Firm',
            userName: 'Owner',
            today: DateTime(2026, 9, 30),
            allowed: (path) => allowed && path == 'masters/trade-licences',
            source: _HomeSource(expiring: expiring),
            onOpen: (item) => opened.add(item.path),
          ),
        ),
      ));
      await tester.pump();
      await tester.pump();
      return opened;
    }

    testWidgets('a tile counting what is expiring, for somebody who may see '
        'licences', (tester) async {
      final List<String> opened =
          await pumpHome(tester, allowed: true, expiring: 3);
      expect(find.text('Licences expiring'), findsOneWidget);
      final Finder count = find.descendant(
        of: find.byKey(const ValueKey('home-todo-licences-expiring')),
        matching: find.text('3'),
      );
      expect(count, findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('home-todo-licences-expiring')));
      expect(opened, ['masters/trade-licences']);
    });

    testWidgets('no tile at all for somebody without TRADE_LICENCE_VIEW',
        (tester) async {
      await pumpHome(tester, allowed: false);
      expect(find.text('Licences expiring'), findsNothing);
    });

    testWidgets('nothing due is not an alert', (tester) async {
      await pumpHome(tester, allowed: true, expiring: 0);
      final Finder count = find.descendant(
        of: find.byKey(const ValueKey('home-todo-licences-expiring')),
        matching: find.text('0'),
      );
      final BuildContext context = tester.element(count);
      expect(tester.widget<Text>(count).style?.color,
          isNot(Theme.of(context).colorScheme.error));
    });
  });
}
