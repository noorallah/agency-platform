// Purchase requisitions (BUY-7): the list, the editor's request body, the
// lifecycle actions on their own paths, a convert refusal shown, and Below
// reorder level raising a requisition from the same picks.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/purchase_requisition_page.dart';
import 'package:agency_desktop/ui/purchases/reorder_dialog.dart';
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

Json _requisition(String id, String status, {int version = 1}) => {
      'id': id,
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'requisition_number': 'REQ-$id',
      'requisition_date': '2026-10-03',
      'needed_by': '2026-10-10',
      'status': status,
      'remarks': null,
      'version': version,
      'lines': [
        {
          'id': 'l-$id',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'RICE',
          'product_name': 'Basmati rice',
          'quantity': '12.0000',
          'vendor_id': null,
          'remarks': null,
          'purchase_order_id': null,
        },
      ],
    };

class _Api extends ApiClient {
  _Api({this.refuseConvert})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuseConvert;
  final List<String> calls = <String>[];
  final Map<String, Json?> bodies = <String, Json?>{};

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
    if (call == 'GET /api/v1/purchases/requisitions') {
      return {
        'data': [
          _requisition('1', 'DRAFT'),
          _requisition('2', 'SUBMITTED'),
          _requisition('3', 'APPROVED'),
        ],
      };
    }
    if (call == 'POST /api/v1/purchases/requisitions') {
      return {'data': _requisition('9', 'DRAFT')};
    }
    if (call == 'POST /api/v1/purchases/requisitions/from-reorder') {
      return {'data': <Json>[], 'message': '1 requisition(s) raised.'};
    }
    if (call.startsWith('POST /api/v1/purchases/requisitions/') &&
        call.endsWith('/convert')) {
      if (refuseConvert != null) {
        throw ApiException(refuseConvert!, statusCode: 422);
      }
      return {
        'data': [
          {'id': 'po-1'},
          {'id': 'po-2'},
        ],
      };
    }
    if (call.startsWith('POST /api/v1/purchases/requisitions/')) {
      return {'data': _requisition('1', 'SUBMITTED')};
    }
    if (path == '/api/v1/branches') {
      return {
        'data': [
          {'id': 'b-1', 'code': 'HO', 'name': 'Head office'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/warehouses') {
      return {
        'data': [
          {'id': 'w-1', 'branch_id': 'b-1', 'code': 'MAIN', 'name': 'Main'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/vendors') {
      return {
        'data': [
          {'id': 'v-1', 'code': 'SG', 'name': 'Sri Ganesh Traders'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path == '/api/v1/products') {
      return {
        'data': [
          {'id': 'p-1', 'code': 'RICE', 'name': 'Basmati rice'},
        ],
        'pagination': {'total_records': 1},
      };
    }
    if (path.endsWith('/reports/below-reorder')) {
      return {
        'data': [
          {
            'warehouse_id': 'w-1',
            'warehouse_code': 'MAIN',
            'product_id': 'p-1',
            'product_code': 'RICE',
            'product_name': 'Basmati rice',
            'available_quantity': '3.0000',
            'reorder_level': '5.0000',
            'on_order_quantity': '0.0000',
            'suggested_quantity': '17.0000',
            'supplier_id': 'v-1',
            'supplier_name': 'Sri Ganesh Traders',
          },
        ],
      };
    }
    return {'data': const <dynamic>[]};
  }
}

const List<String> _all = [
  'PURCHASE_VIEW',
  'PURCHASE_REQUISITION_CREATE',
  'PURCHASE_APPROVE',
  'PURCHASE_CREATE',
];

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  List<String> perms = _all,
}) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PurchaseRequisitionPage(
        api: api,
        preferences: DesktopPreferencesService(
          directory: Directory.systemTemp.createTempSync('requisitions'),
        ),
        permissions: _permissions(perms),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester, String number) async {
  await tester.tap(find.text(number).first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

Future<void> _command(WidgetTester tester, String id) async {
  await tester.tap(find.byKey(ValueKey('selection-$id')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows number, date, needed by, status and lines',
      (tester) async {
    await _pump(tester, _Api());

    expect(find.text('REQ-1'), findsOneWidget);
    expect(find.text('REQ-3'), findsOneWidget);
    expect(find.text('2026-10-10'), findsWidgets);
    expect(find.text('Submitted'), findsOneWidget);
    expect(find.text('Approved'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('creating posts the branch, warehouse, dates and lines',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    // One branch: chosen for the user.
    await tester.tap(find.byKey(const ValueKey('requisition-warehouse-b-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Main').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('requisition-product-0')), 'Rice');
    await tester.pumpAndSettle();
    await tester.tap(find.text('RICE · Basmati rice').last);
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('requisition-quantity-0')), '12');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('requisition-supplier-0-')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sri Ganesh Traders').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('requisition-save')));
    await tester.pumpAndSettle();

    final Json sent = api.bodies['POST /api/v1/purchases/requisitions']!;
    expect(sent['branch_id'], 'b-1');
    expect(sent['warehouse_id'], 'w-1');
    expect(sent['requisition_date'], isNotEmpty);
    expect(sent.containsKey('needed_by'), isFalse);
    expect(sent['lines'], <Json>[
      <String, dynamic>{
        'product_id': 'p-1',
        'quantity': '12',
        'vendor_id': 'v-1',
      },
    ]);
    expect(find.byType(RequisitionDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('submit, approve and convert hit their own paths',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'REQ-1');
    await _command(tester, 'submit');
    expect(api.calls, contains('POST /api/v1/purchases/requisitions/1/submit'));

    await _select(tester, 'REQ-2');
    await _command(tester, 'approve');
    expect(
        api.calls, contains('POST /api/v1/purchases/requisitions/2/approve'));

    await _select(tester, 'REQ-3');
    await _command(tester, 'convert');
    expect(
        api.calls, contains('POST /api/v1/purchases/requisitions/3/convert'));
    expect(find.textContaining('2 purchase orders raised'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('cancelling asks for a reason and sends it', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'REQ-1');
    await _command(tester, 'cancel');
    await tester.enterText(find.byType(TextField).last, 'No longer needed');
    await tester.pump();
    await tester.tap(find.text('Cancel requisition'));
    await tester.pumpAndSettle();

    expect(
      api.bodies['POST /api/v1/purchases/requisitions/1/cancel'],
      {'reason': 'No longer needed'},
    );
  });

  testWidgets('a convert refusal is shown with the server message',
      (tester) async {
    final _Api api = _Api(
      refuseConvert: 'No supplier for: RICE. Name one on the line.',
    );
    await _pump(tester, api);

    await _select(tester, 'REQ-3');
    await _command(tester, 'convert');

    expect(find.textContaining('No supplier for: RICE'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('without the approve permission there is no Approve action',
      (tester) async {
    await _pump(tester, _Api(),
        perms: const ['PURCHASE_VIEW', 'PURCHASE_REQUISITION_CREATE']);

    await _select(tester, 'REQ-1');
    expect(find.byKey(const ValueKey('selection-approve')), findsNothing);
    expect(find.byKey(const ValueKey('selection-convert')), findsNothing);
    expect(find.byKey(const ValueKey('selection-submit')), findsOneWidget);
  });

  testWidgets('Below reorder level can raise a requisition instead',
      (tester) async {
    final _Api api = _Api();
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: FilledButton(
              onPressed: () => showDialog<Object>(
                context: context,
                builder: (_) =>
                    ReorderDialog(api: api, canRaiseRequisition: true),
              ),
              child: const Text('Open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reorder-requisition')));
    await tester.pumpAndSettle();

    final Json sent =
        api.bodies['POST /api/v1/purchases/requisitions/from-reorder']!;
    expect(sent['items'], <Json>[
      <String, dynamic>{
        'warehouse_id': 'w-1',
        'product_id': 'p-1',
        'quantity': '17',
      },
    ]);
    expect(api.calls, isNot(contains('POST /api/v1/purchases/reorder-drafts')));
    expect(tester.takeException(), isNull);
  });
}
