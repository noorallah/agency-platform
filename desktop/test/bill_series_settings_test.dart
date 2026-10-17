// The bill series setting (backlog 157): one series for every sales bill, or
// a series per company. The fake answers at `request`, so the paths and the
// body the real client methods build are what is checked.

import 'dart:async';
import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/menu_layout.dart';
import 'package:agency_desktop/ui/settings/bill_series_settings_page.dart';
import 'package:agency_desktop/ui/workspace/module_catalog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissionsFor(List<String> perms) {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({'permissions': perms})),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Json _settings({
  String driver = 'ONE_SERIES',
  bool configured = true,
  int longest = 5,
  bool withSeries = true,
}) =>
    <String, dynamic>{
      'series_driver': driver,
      'drivers': <String>['ONE_SERIES', 'BY_COMPANY'],
      'longest_prefix': longest,
      'is_configured': configured,
      if (withSeries)
        'series': <Json>[
          <String, dynamic>{
            'series_prefix': 'GENERAL',
            'company_name': null,
            'last_issued': 12,
            'capacity': 9999,
            'near_limit': false,
            'at_limit': false,
            'warning': null,
            'fit': 'Fits the 16-character GST limit.',
          },
          <String, dynamic>{
            'series_prefix': 'ASIAN',
            'company_name': 'Asian Paints',
            'last_issued': 9500,
            'capacity': 9999,
            'near_limit': true,
            'at_limit': false,
            'warning': 'ASIAN has 499 numbers left this year.',
            'fit': 'Fits with 2 characters to spare.',
          },
        ],
    };

class _Api extends ApiClient {
  _Api({Json? settings, this.refuseSave, this.hold})
      : _current = settings ?? _settings(),
        super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  Json _current;

  /// The server's refusal of a save, when it should refuse one.
  final String? refuseSave;

  /// Holds the first read open, so the loading state can be seen.
  final Completer<void>? hold;

  final List<String> calls = <String>[];
  final List<Json?> bodies = <Json?>[];

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
    bodies.add(body);
    if (method == 'GET' && hold != null) await hold!.future;
    if (method == 'PUT') {
      if (refuseSave != null) {
        throw ApiException(refuseSave!, statusCode: 403);
      }
      _current = <String, dynamic>{
        ..._current,
        'series_driver': body!['series_driver'],
        'is_configured': true,
      };
    }
    if (path.startsWith('/api/v1/sales-invoices/series-preview')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'series_driver': 'BY_COMPANY',
          'series_prefix': 'ASIAN',
          'reason': 'ONE_COMPANY',
          'number': 'ASIAN-26-27-0001',
        },
      };
    }
    return <String, dynamic>{'data': _current};
  }
}

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> perms = const ['SETTINGS_VIEW', 'SETTINGS_UPDATE'],
  bool settle = true,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: BillSeriesSettingsPage(
        api: api,
        permissions: _permissionsFor(perms),
        hasActiveFirm: true,
      ),
    ),
  ));
  if (settle) await tester.pumpAndSettle();
}

Finder _key(String key) => find.byKey(ValueKey(key));

FilledButton _saveButton(WidgetTester tester) =>
    tester.widget<FilledButton>(_key('bill-series-save'));

void main() {
  testWidgets('shows a spinner until the setting arrives, then the choice',
      (tester) async {
    final Completer<void> hold = Completer<void>();
    final _Api api = _Api(hold: hold);
    await _pump(tester, api, settle: false);
    await tester.pump();

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(_key('bill-series-save'), findsNothing);

    hold.complete();
    await tester.pumpAndSettle();

    expect(api.calls, ['GET /api/v1/document-framework/bill-series-settings']);
    expect(find.text('One series for every bill'), findsOneWidget);
    expect(find.text('A series per company'), findsOneWidget);
    // Design: switching is safe mid-year and the screen says so.
    expect(find.textContaining('Switching affects new bills only'),
        findsOneWidget);
    // The figure is the server's, not written into the sentence.
    expect(find.textContaining('up to 5 characters'), findsOneWidget);
    // Nothing moved, so there is nothing to save.
    expect(_saveButton(tester).onPressed, isNull);
  });

  testWidgets('saving sends the chosen series and shows what was saved',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(_key('bill-series-driver-BY_COMPANY'));
    await tester.pumpAndSettle();
    expect(_saveButton(tester).onPressed, isNotNull);

    await tester.tap(_key('bill-series-save'));
    await tester.pumpAndSettle();

    expect(api.calls.last, 'PUT /api/v1/document-framework/bill-series-settings');
    expect(api.bodies.last, {'series_driver': 'BY_COMPANY'});
    expect(find.text('Bill series setting saved.'), findsOneWidget);
    // Saved, so the button rests again.
    expect(_saveButton(tester).onPressed, isNull);
  });

  testWidgets('each series shows its usage, its fit and any warning',
      (tester) async {
    await _pump(tester, _Api());

    expect(_key('bill-series-row-GENERAL'), findsOneWidget);
    expect(_key('bill-series-row-ASIAN'), findsOneWidget);
    expect(find.text('ASIAN (Asian Paints)'), findsOneWidget);
    expect(find.text('Last issued 12 of 9999'), findsOneWidget);
    expect(find.text('Last issued 9500 of 9999'), findsOneWidget);
    expect(find.text('Fits the 16-character GST limit.'), findsOneWidget);
    expect(find.text('Fits with 2 characters to spare.'), findsOneWidget);
    // Only the series the server warned about carries a warning.
    expect(_key('bill-series-warning-ASIAN'), findsOneWidget);
    expect(_key('bill-series-warning-GENERAL'), findsNothing);
    expect(find.text('ASIAN has 499 numbers left this year.'), findsOneWidget);
  });

  testWidgets('a reply with no series lists none', (tester) async {
    await _pump(tester, _Api(settings: _settings(withSeries: false)));

    expect(find.text('One series for every bill'), findsOneWidget);
    expect(find.text('Series in use'), findsNothing);
    expect(find.textContaining('Last issued'), findsNothing);
  });

  testWidgets('a firm that never chose may save the default as its own',
      (tester) async {
    final _Api api = _Api(settings: _settings(configured: false));
    await _pump(tester, api);

    expect(find.textContaining('This firm has not chosen'), findsOneWidget);
    expect(_saveButton(tester).onPressed, isNotNull);
  });

  testWidgets('a refusal is shown and the choice stays on screen',
      (tester) async {
    final _Api api = _Api(
      refuseSave: 'You do not have permission to change settings.',
    );
    await _pump(tester, api);

    await tester.tap(_key('bill-series-driver-BY_COMPANY'));
    await tester.pumpAndSettle();
    await tester.tap(_key('bill-series-save'));
    await tester.pumpAndSettle();

    expect(find.text('You do not have permission to change settings.'),
        findsOneWidget);
    final RadioGroup<String> group =
        tester.widget<RadioGroup<String>>(find.byType(RadioGroup<String>));
    expect(group.groupValue, 'BY_COMPANY');
    expect(_saveButton(tester).onPressed, isNotNull);
  });

  testWidgets('a reader sees the setting and is offered no Save',
      (tester) async {
    await _pump(tester, _Api(), perms: const ['SETTINGS_VIEW']);

    expect(find.text('One series for every bill'), findsOneWidget);
    expect(_key('bill-series-save'), findsNothing);
    expect(find.textContaining('needs the update settings permission'),
        findsOneWidget);
  });

  testWidgets('without SETTINGS_VIEW nothing is read', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, perms: const ['SALES_VIEW']);

    expect(find.textContaining('do not have permission'), findsOneWidget);
    expect(api.calls, isEmpty);
  });

  test('the series preview asks once per line and reads the answer', () async {
    final _Api api = _Api();
    final preview = await api.salesInvoiceSeriesPreview(
      productIds: const ['p-1', 'p-2'],
      invoiceDate: '2026-10-17',
    );

    expect(
      api.calls.single,
      'GET /api/v1/sales-invoices/series-preview'
      '?product_id=p-1&product_id=p-2&invoice_date=2026-10-17',
    );
    expect(preview.seriesPrefix, 'ASIAN');
    expect(preview.number, 'ASIAN-26-27-0001');
  });

  test('the screen is reachable: a tab, a sidebar leaf and a Settings item',
      () {
    final ModuleDefinition admin = ModuleCatalog.byId(AppModule.administration);
    final ModuleTabDefinition tab =
        admin.tabs.singleWhere((tab) => tab.id == 'bill-series');
    expect(tab.requiredPermissions, ['SETTINGS_VIEW']);
    expect(
      MenuLayout.settings.item('administration/bill-series'),
      isNotNull,
    );
  });
}
