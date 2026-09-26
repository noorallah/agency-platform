import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/sales/sales_order_management_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Sales Orders' views in the phase 2 app: counters that filter, and Home's
/// "Orders to approve" landing on the drafts (the owner, 2026-09-26).
class _OrdersApi extends ApiClient {
  _OrdersApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// The status each list request asked for; '' for every status.
  final List<String> statuses = [];

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
    if (path.endsWith('/summary')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'total': 12,
          'draft': 4,
          'approved': 5,
          'cancelled': 1,
          'closed': 2,
        },
      };
    }
    if (path == '/api/v1/sales-orders') {
      statuses.add(query?['status'] ?? '');
    }
    return <String, dynamic>{
      'data': const <Json>[],
      'pagination': <String, dynamic>{'total_records': 0},
    };
  }
}

PermissionService _permissions() {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': ['SALES_VIEW'],
    'roles': const <String>[],
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Future<_OrdersApi> _pump(
  WidgetTester tester, {
  ListViewRequest? request,
  bool phase2 = true,
}) async {
  tester.view.physicalSize = const Size(1600, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final Directory temp = Directory.systemTemp.createTempSync('so-views');
  addTearDown(() => temp.deleteSync(recursive: true));
  final _OrdersApi api = _OrdersApi();
  final Widget page = ListViewRequestScope(
    request: request,
    child: SalesOrderManagementPage(
      api: api,
      preferences: DesktopPreferencesService(directory: temp),
      permissions: _permissions(),
      hasActiveFirm: true,
    ),
  );
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: phase2 ? Phase2Scope(child: page) : page),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets("Home's request lands on the drafts", (tester) async {
    final _OrdersApi api = await _pump(
      tester,
      request: const ListViewRequest(
          path: 'salesOrders', view: 'draft', serial: 1),
    );
    expect(api.statuses.last, 'DRAFT');
    final SummaryCount draft = tester
        .widget(find.byKey(const ValueKey('view-counter-draft')));
    expect(draft.selected, isTrue);
  });

  testWidgets('a request for another screen changes nothing', (tester) async {
    final _OrdersApi api = await _pump(
      tester,
      request: const ListViewRequest(
          path: 'purchaseInvoices', view: 'draft', serial: 1),
    );
    expect(api.statuses, everyElement(''));
  });

  testWidgets('a counter filters; clicking it again shows every order',
      (tester) async {
    final _OrdersApi api = await _pump(tester);
    expect(find.text('Draft'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('view-counter-approved')));
    await tester.pumpAndSettle();
    expect(api.statuses.last, 'APPROVED');
    await tester.tap(find.byKey(const ValueKey('view-counter-approved')));
    await tester.pumpAndSettle();
    expect(api.statuses.last, '');
  });

  testWidgets('phase 1 keeps its cards and asks for every order',
      (tester) async {
    final _OrdersApi api = await _pump(tester, phase2: false);
    expect(find.byKey(const ValueKey('view-counter-draft')), findsNothing);
    expect(api.statuses, everyElement(''));
  });
}
