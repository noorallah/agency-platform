// A new outlet waits for office approval (SEL-15).
//
// A PENDING customer takes orders but cannot be billed until somebody with
// CUSTOMER_APPROVE approves it. The list shows it as "Pending approval",
// filters on it, and offers Approve (one row) and Approve selected (ticked
// rows) only to somebody who holds the code; the editor says so in a banner;
// and the Sales stages dialog carries the switch that makes it happen.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/customer.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/ui/customers/customer_management_page.dart';
import 'package:agency_desktop/ui/sales/sales_workflow_settings_dialog.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/gestures.dart' show kDoubleTapTimeout;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PermissionService _permissions(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'roles': <String>['user'],
        'permissions': codes,
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.signature');
}

Json _customer(int n, String status) => <String, dynamic>{
      'id': 'cust-$n',
      'code': 'C00$n',
      'name': 'Shop $n',
      'display_name': 'Shop $n',
      'customer_type': 'BUSINESS',
      'currency_code': 'INR',
      'status': status,
      'credit_limit': '0',
      'default_discount_percent': '0',
      'version': n + 2,
      'addresses': const <Json>[],
      'contacts': const <Json>[],
    };

class _OutletApi extends ApiClient {
  _OutletApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows = <Json>[
    _customer(1, 'PENDING'),
    _customer(2, 'PENDING'),
    _customer(3, 'ACTIVE'),
  ];
  final List<(String, String, Json?)> calls = <(String, String, Json?)>[];
  final List<Map<String, String>?> listQueries = <Map<String, String>?>[];

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
    if (method == 'POST' && path.contains('/approve') ||
        path.endsWith('/bulk-approve')) {
      calls.add((method, path, body));
      if (path.endsWith('/bulk-approve')) {
        final List<Json> items = (body!['items'] as List).cast<Json>();
        return <String, dynamic>{
          'data': <String, dynamic>{
            'done': items.length,
            'refused': 0,
            'results': [
              for (final Json item in items)
                <String, dynamic>{
                  'id': item['id'],
                  'number': 'NUM-${item['id']}',
                  'outcome': 'DONE',
                  'message': null,
                },
            ],
          },
        };
      }
      return <String, dynamic>{'data': _customer(1, 'ACTIVE')};
    }
    if (method == 'GET' && path == '/api/v1/customers') {
      listQueries.add(query);
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': <String, dynamic>{}};
  }
}

Future<_OutletApi> _pumpList(
  WidgetTester tester,
  List<String> codes,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final _OutletApi api = _OutletApi();
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Phase2Scope(
        child: CustomerManagementPage(
          api: api,
          permissions: _permissions(codes),
          hasActiveFirm: true,
        ),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return api;
}

const List<String> _viewer = ['CUSTOMER_VIEW', 'CUSTOMER_UPDATE'];
const List<String> _approver = [..._viewer, 'CUSTOMER_APPROVE'];

Finder _bar(String text) => find.descendant(
      of: find.byKey(const ValueKey('selection-bar')),
      matching: find.textContaining(text, findRichText: true),
    );

/// A row that opens on double-click waits out the double-click before a
/// single click selects it.
Future<void> _choose(WidgetTester tester, String code) async {
  await tester.tap(find.text(code));
  await tester.pump(kDoubleTapTimeout + const Duration(milliseconds: 50));
  await tester.pumpAndSettle();
}

class _StagesApi extends ApiClient {
  _StagesApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> saved = [];

  @override
  Future<SalesWorkflowSettings> salesWorkflowSettings() async =>
      SalesWorkflowSettings.fromJson(<String, dynamic>{
        'quotation_stage': true,
        'sales_order_stage': true,
        'delivery_note_stage': true,
        'is_configured': true,
      });

  @override
  Future<SalesWorkflowSettings> updateSalesWorkflowSettings(
    SalesWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

void main() {
  testWidgets('a pending customer reads "Pending approval" in the list',
      (tester) async {
    await _pumpList(tester, _viewer);

    expect(find.text('Pending approval'), findsWidgets);
  });

  testWidgets('the status filter offers Pending approval and sends PENDING',
      (tester) async {
    final _OutletApi api = await _pumpList(tester, _viewer);

    // The phase 2 counter filters the list to the status.
    await tester.tap(find.byKey(const ValueKey('customer-counter-pending')));
    await tester.pumpAndSettle();

    expect(api.listQueries.last?['status'], 'PENDING');
  });

  testWidgets('Approve on a selected pending customer posts to its path',
      (tester) async {
    final _OutletApi api = await _pumpList(tester, _approver);

    await _choose(tester, 'C001');
    await tester.tap(find.byKey(const ValueKey('selection-approve')));
    await tester.pumpAndSettle();

    expect(api.calls.single.$1, 'POST');
    expect(api.calls.single.$2, '/api/v1/customers/cust-1/approve');
  });

  testWidgets('Approve is disabled on a customer that is not pending',
      (tester) async {
    final _OutletApi api = await _pumpList(tester, _approver);

    await _choose(tester, 'C003');

    // The selection bar offers only what the row can take now.
    expect(find.byKey(const ValueKey('selection-approve')), findsNothing);
    expect(api.calls, isEmpty);
  });

  testWidgets('Approve selected sends the ticked ids', (tester) async {
    final _OutletApi api = await _pumpList(tester, _approver);

    await tester.tap(find.byType(Checkbox).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Checkbox).at(2));
    await tester.pumpAndSettle();
    expect(_bar('2 selected'), findsOneWidget);

    await tester.tap(find.text('Approve selected'));
    await tester.pumpAndSettle();

    expect(api.calls.single.$2, '/api/v1/customers/bulk-approve');
    final List<Json> items =
        (api.calls.single.$3!['items'] as List).cast<Json>();
    expect(items.map((item) => item['id']).toSet(), {'cust-1', 'cust-2'});
    expect(find.text('Approved 2 of 2'), findsOneWidget);
  });

  testWidgets('without CUSTOMER_APPROVE no approve action is offered',
      (tester) async {
    final _OutletApi api = await _pumpList(tester, _viewer);

    await _choose(tester, 'C001');

    expect(find.byKey(const ValueKey('selection-approve')), findsNothing);
    // No tick boxes either: they exist only for the bulk approve.
    expect(find.byType(Checkbox), findsNothing);
    expect(api.calls, isEmpty);
  });

  testWidgets('the editor of a pending customer says so, and offers Approve',
      (tester) async {
    tester.view.physicalSize = const Size(1700, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    bool approved = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(_customer(1, 'PENDING')),
            loadPlaces: (level, {parentId = ''}) async => const [],
            onSave: (payload) async => Customer.fromJson(_customer(1, 'PENDING')),
            onApprove: () async {
              approved = true;
              return Customer.fromJson(_customer(1, 'ACTIVE'));
            },
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(
      find.text('Waiting for office approval — orders allowed, billing '
          'blocked'),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('customer-approve')));
    await tester.pumpAndSettle();
    expect(approved, isTrue);
  });

  testWidgets('the editor hides Approve without the permission',
      (tester) async {
    tester.view.physicalSize = const Size(1700, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Phase2Scope(
          child: CustomerWorkspaceDialog(
            mode: CustomerDialogMode.edit,
            customer: Customer.fromJson(_customer(1, 'PENDING')),
            loadPlaces: (level, {parentId = ''}) async => const [],
            onSave: (payload) async => Customer.fromJson(_customer(1, 'PENDING')),
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('customer-pending-banner')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('customer-approve')), findsNothing);
  });

  testWidgets('the sales stages switch is sent on save', (tester) async {
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _StagesApi api = _StagesApi();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SalesWorkflowSettingsDialog(
          api: api,
          permissions: _permissions(['SALES_VIEW', 'SALES_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final Finder tile = find.byKey(
      const ValueKey('sales-settings-new-outlets-approval'),
    );
    await tester.ensureVisible(tile);
    expect(find.textContaining('takes orders but cannot be billed'),
        findsOneWidget);
    await tester.tap(tile);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved.single['new_outlets_need_approval'], isTrue);
  });
}
