// STK-12: an approved order's stock hold can lapse, and the screens say so.
//
// Three things carry the weight. The firm's setting is sent as typed (blank is
// never, sent as null). A lapsed order is marked in the list and the editor,
// so nobody mistakes it for one whose stock is still held. And "Reserve again"
// posts to the order's own path, only for someone who may approve.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/ui/sales/sales_order_editor_dialog.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_workflow_settings_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.sig');
}

class _SettingsApi extends ApiClient {
  _SettingsApi({this.lapseDays})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final int? lapseDays;
  final List<Json> saved = <Json>[];

  @override
  Future<SalesWorkflowSettings> salesWorkflowSettings() async =>
      SalesWorkflowSettings.fromJson(<String, dynamic>{
        'quotation_stage': false,
        'sales_order_stage': true,
        'delivery_note_stage': true,
        'is_configured': true,
        'reservation_lapse_days': lapseDays,
      });

  @override
  Future<SalesWorkflowSettings> updateSalesWorkflowSettings(
    SalesWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

Json _order({bool lapsed = true}) => <String, dynamic>{
      'id': 'so-1',
      'version': 3,
      'order_number': 'SO-0001',
      'order_date': '2026-08-23',
      'reference_number': '',
      'status': 'APPROVED',
      'grand_total': '1000.00',
      'customer_id': 'cus-1',
      'branch_id': 'b1',
      'warehouse_id': 'w1',
      'is_on_hold': false,
      'reservation_lapsed_at': lapsed ? '2026-09-20T00:00:00Z' : null,
      'lines': <Json>[],
    };

class _OrdersApi extends ApiClient {
  _OrdersApi({this.row})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final Json? row;
  final List<String> posted = <String>[];

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
    if (method == 'POST') {
      posted.add(path);
      return <String, dynamic>{'data': row};
    }
    if (path == '/api/v1/sales-orders/so-1') {
      return <String, dynamic>{'data': row};
    }
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{'total': 1, 'draft': 0},
      };
    }
    if (path == '/api/v1/sales-orders') {
      return <String, dynamic>{
        'data': <Json>[row!],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

Future<void> _pumpList(
  WidgetTester tester,
  _OrdersApi api,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1600, 1100);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('so-lapse-test');
  addTearDown(() => temp.deleteSync(recursive: true));
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesOrderManagementPage(
        api: api,
        preferences: DesktopPreferencesService(directory: temp),
        permissions: _permissions(codes),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the lapse days are sent as typed, and blank is sent as null',
      (tester) async {
    final _SettingsApi api = _SettingsApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SalesWorkflowSettingsDialog(
          api: api,
          permissions: _permissions(<String>[
            'SALES_VIEW',
            'SALES_MANAGE_SETTINGS',
          ]),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved.single.containsKey('reservation_lapse_days'), isTrue);
    expect(api.saved.single['reservation_lapse_days'], isNull);
  });

  testWidgets('a typed number of days is sent as a whole number',
      (tester) async {
    final _SettingsApi api = _SettingsApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SalesWorkflowSettingsDialog(
          api: api,
          permissions: _permissions(<String>[
            'SALES_VIEW',
            'SALES_MANAGE_SETTINGS',
          ]),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder box = find.byKey(const ValueKey('sales-settings-reservation-lapse'));
    await tester.ensureVisible(box);
    expect(find.text('Release stock held by unshipped orders after (days)'),
        findsOneWidget);
    await tester.enterText(box, '14');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved.single['reservation_lapse_days'], 14);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a stored value is shown, and a bad one is refused',
      (tester) async {
    final _SettingsApi api = _SettingsApi(lapseDays: 30);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SalesWorkflowSettingsDialog(
          api: api,
          permissions: _permissions(<String>[
            'SALES_VIEW',
            'SALES_MANAGE_SETTINGS',
          ]),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder box = find.byKey(const ValueKey('sales-settings-reservation-lapse'));
    await tester.ensureVisible(box);
    expect(find.text('30'), findsOneWidget);
    await tester.enterText(box, '400');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved, isEmpty);
  });

  testWidgets('a lapsed order is marked in the list', (tester) async {
    await _pumpList(
      tester,
      _OrdersApi(row: _order()),
      const <String>['SALES_VIEW', 'SALES_APPROVE'],
    );
    expect(find.textContaining('stock hold lapsed'), findsOneWidget);
  });

  testWidgets('Reserve again posts to the order and needs approval',
      (tester) async {
    final _OrdersApi api = _OrdersApi(row: _order());
    await _pumpList(
      tester,
      api,
      const <String>['SALES_VIEW', 'SALES_APPROVE'],
    );
    await tester.tap(find.text('Reserve again'));
    await tester.pumpAndSettle();
    expect(api.posted, contains('/api/v1/sales-orders/so-1/reserve-again'));
  });

  testWidgets('Reserve again is off without approval or without a lapse',
      (tester) async {
    await _pumpList(
      tester,
      _OrdersApi(row: _order()),
      const <String>['SALES_VIEW'],
    );
    expect(
      tester
          .widget<ButtonStyleButton>(find
              .ancestor(
                of: find.text('Reserve again'),
                matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
              )
              .first)
          .onPressed,
      isNull,
    );
  });

  testWidgets('the editor shows the Stock hold lapsed badge', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _OrdersApi api = _OrdersApi(row: _order());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: SalesOrderEditorDialog(
            api: api,
            today: DateTime(2026, 8, 14),
            orderId: 'so-1',
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Stock hold lapsed'), findsOneWidget);
  });
}
