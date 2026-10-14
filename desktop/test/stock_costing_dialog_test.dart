// L2 step 9, the desktop half: a firm switching its stock costing from
// Average to by lot.
//
//   * on Average the dialog asks for one preview on opening, fills the day the
//     server suggests, lists every refusal and keeps Switch disabled;
//   * a clean preview for the day shown enables Switch, which asks a plain
//     confirmation and posts exactly {on: <day>};
//   * on a by-lot firm there is no Switch, and the billing switch PUTs only
//     allow_billing_without_stock.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/inventory/stock_costing_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

class _Call {
  _Call(this.method, this.path, this.body, this.query);
  final String method;
  final String path;
  final Json? body;
  final Map<String, String>? query;
}

class _Api extends ApiClient {
  _Api({required this.byLot, this.refusals = const <String, List<String>>{}})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  bool byLot;
  bool allowBilling = false;

  /// Refusals by the day asked about.
  final Map<String, List<String>> refusals;
  final List<_Call> calls = [];

  Json _settings() => <String, dynamic>{
        'costing_method': byLot ? 'BY_LOT' : 'AVERAGE',
        'switched_on': byLot ? '2026-04-01' : null,
        'allow_billing_without_stock': allowBilling,
        'version': 1,
      };

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
    calls.add(_Call(method, path, body, query));
    if (path.endsWith('/switch-preview')) {
      final String on = query!['on']!;
      return {
        'success': true,
        'data': {
          'on': on,
          'suggested_on': '2026-04-01',
          'items': 12,
          'lots': 15,
          'quantity': '340.5000',
          'stock_value': '1234567.50',
          'refusals': refusals[on] ?? const <String>[],
        },
      };
    }
    if (path.endsWith('/lot-settings/switch')) {
      byLot = true;
      return {'success': true, 'data': _settings()};
    }
    if (path.endsWith('/lot-settings') && method == 'PUT') {
      allowBilling = body!['allow_billing_without_stock'] as bool;
      return {'success': true, 'data': _settings()};
    }
    return {'success': true, 'data': _settings()};
  }
}

void _viewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _pump(WidgetTester tester, _Api api) async {
  _viewport(tester);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: StockCostingDialog(
        api: api,
        permissions:
            _permissions(['INVENTORY_VIEW', 'INVENTORY_MANAGE_SETTINGS']),
        today: '2026-10-14',
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

FilledButton _switchButton(WidgetTester tester) => tester.widget<FilledButton>(
    find.byKey(const ValueKey('stock-costing-switch')));

void main() {
  testWidgets('Average: the preview lists every refusal and Switch stays off',
      (tester) async {
    final _Api api = _Api(byLot: false, refusals: {
      '2026-04-01': [
        'A stock movement is dated after 2026-04-01.',
        'Two items carry negative stock.',
      ],
    });
    await _pump(tester, api);

    // One read of the settings and one preview, for today, on opening.
    expect([for (final _Call c in api.calls) '${c.method} ${c.path}'], [
      'GET /api/v1/inventory/lot-settings',
      'GET /api/v1/inventory/lot-settings/switch-preview',
    ]);
    expect(api.calls.last.query, {'on': '2026-10-14'});
    expect(find.text('Average cost'), findsOneWidget);
    expect(find.widgetWithText(TextField, '2026-04-01'), findsOneWidget);

    // Typing asks nothing; Show asks once for the typed day.
    await tester.enterText(
        find.byKey(const ValueKey('stock-costing-date')), '2026-04-02');
    await tester.enterText(
        find.byKey(const ValueKey('stock-costing-date')), '2026-04-01');
    await tester.pump();
    expect(api.calls, hasLength(2));
    await tester.tap(find.byKey(const ValueKey('stock-costing-show')));
    await tester.pumpAndSettle();
    expect(api.calls, hasLength(3));
    expect(api.calls.last.query, {'on': '2026-04-01'});

    expect(find.byKey(const ValueKey('stock-costing-items')), findsOneWidget);
    expect(find.text('12'), findsOneWidget);
    expect(find.text('15'), findsOneWidget);
    expect(find.text('340.5'), findsOneWidget);
    expect(find.text('12,34,567.50'), findsOneWidget);
    expect(find.text('A stock movement is dated after 2026-04-01.'),
        findsOneWidget);
    expect(find.text('Two items carry negative stock.'), findsOneWidget);
    expect(_switchButton(tester).onPressed, isNull);
  });

  testWidgets('Average: a clean preview switches on the day shown',
      (tester) async {
    final _Api api = _Api(byLot: false);
    await _pump(tester, api);

    await tester.enterText(
        find.byKey(const ValueKey('stock-costing-date')), '2026-05-01');
    await tester.pump();
    // The preview on screen was for another day.
    expect(_switchButton(tester).onPressed, isNull);
    await tester.tap(find.byKey(const ValueKey('stock-costing-show')));
    await tester.pumpAndSettle();
    expect(_switchButton(tester).onPressed, isNotNull);

    await tester.tap(find.byKey(const ValueKey('stock-costing-switch')));
    await tester.pumpAndSettle();
    final String warning = tester
        .widget<Text>(find.byKey(const ValueKey('stock-costing-confirm-text')))
        .data!;
    expect(warning, contains('one way'));
    expect(warning, contains('Nothing is re-valued and no journal'));
    expect(warning, contains('keep the cost'));
    expect(warning, contains('dated before 2026-05-01 is refused'));
    expect(api.calls.where((c) => c.method == 'POST'), isEmpty);

    await tester.tap(find.byKey(const ValueKey('stock-costing-confirm')));
    await tester.pumpAndSettle();
    final _Call post = api.calls.firstWhere((c) => c.method == 'POST');
    expect(post.path, '/api/v1/inventory/lot-settings/switch');
    expect(post.body, {'on': '2026-05-01'});
    expect(find.text('By lot, since 2026-04-01'), findsOneWidget);
    expect(find.byKey(const ValueKey('stock-costing-switch')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('By lot: no Switch, and the billing switch PUTs its one field',
      (tester) async {
    final _Api api = _Api(byLot: true);
    await _pump(tester, api);

    expect(api.calls, hasLength(1));
    expect(find.text('By lot, since 2026-04-01'), findsOneWidget);
    expect(find.byKey(const ValueKey('stock-costing-switch')), findsNothing);
    expect(find.byKey(const ValueKey('stock-costing-date')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('stock-costing-allow-billing')));
    await tester.pumpAndSettle();
    final _Call put = api.calls.firstWhere((c) => c.method == 'PUT');
    expect(put.path, '/api/v1/inventory/lot-settings');
    expect(put.body, {'allow_billing_without_stock': true});
    expect(
      tester
          .widget<SwitchListTile>(
              find.byKey(const ValueKey('stock-costing-allow-billing')))
          .value,
      isTrue,
    );
  });
}
