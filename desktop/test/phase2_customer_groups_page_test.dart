import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/phase2/customer_groups_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Masters > Parties > Customer Groups in the phase 2 app: a list screen like
/// Customers, not the phase 1 dialog stretched into a page.
class _GroupsApi extends ApiClient {
  _GroupsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> created = [];

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
      created.add(body!);
      return {'data': {...body, 'id': 'g-new', 'version': 1}};
    }
    return {
      'data': [
        {
          'id': 'g-1',
          'code': 'RETAILER',
          'name': 'Retailer',
          'default_discount_percent': '1.7500',
          'is_active': true,
          'version': 1,
        },
      ],
      'pagination': {'total_records': 1},
    };
  }
}

PermissionService _holding(List<String> codes) {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': codes,
    'roles': const <String>[],
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

Future<_GroupsApi> _pump(WidgetTester tester, List<String> codes) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _GroupsApi api = _GroupsApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: CustomerGroupsPage(api: api, permissions: _holding(codes)),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

void main() {
  testWidgets('a list screen: the page line, a grid, + New', (tester) async {
    await _pump(tester, const ['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']);
    expect(find.text('Customer Groups'), findsOneWidget);
    expect(find.byType(DataTable), findsOneWidget);
    expect(find.text('RETAILER'), findsOneWidget);
    // The rate as typed, not the server's four decimals.
    expect(find.text('1.75'), findsOneWidget);
    expect(find.byKey(const ValueKey('toolbar-new')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('+ New opens a small form and saves the group', (tester) async {
    final _GroupsApi api =
        await _pump(tester, const ['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']);
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Code'), 'dealer');
    await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Dealer');
    await tester.enterText(find.widgetWithText(TextField, 'Rate'), '2');
    await tester.tap(find.text('Add group'));
    await tester.pumpAndSettle();
    expect(api.created.single, {
      'code': 'DEALER',
      'name': 'Dealer',
      'default_discount_percent': '2',
      'is_active': true,
    });
  });

  testWidgets('who may only look is offered no New, Edit or Delete',
      (tester) async {
    await _pump(tester, const ['CUSTOMER_VIEW']);
    expect(find.byKey(const ValueKey('toolbar-new')), findsNothing);
    expect(find.text('RETAILER'), findsOneWidget);
  });
}
