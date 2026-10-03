// STK-8, the desktop half: approval for large stock adjustments.
//
//   * the Adjustment limits dialog saves the whole list with the declared keys;
//   * a write-off the server refuses as too large keeps the dialog open,
//     offers "Submit for approval" and posts kind WRITE_OFF with the write-off
//     body to adjustment-requests;
//   * the approvals grid approves and rejects a request, and bulk-approves
//     the ticked rows.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/product.dart';
import 'package:agency_desktop/ui/inventory/adjustment_approvals_page.dart';
import 'package:agency_desktop/ui/inventory/adjustment_limits_dialog.dart';
import 'package:agency_desktop/ui/inventory/stock_action_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions(List<String> codes) => PermissionService()
  ..applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': codes,
  }));

Json _request(String id, {String kind = 'WRITE_OFF', String status = 'PENDING'}) =>
    <String, dynamic>{
      'id': id,
      'kind': kind,
      'product_id': 'p-1',
      'warehouse_id': 'w-1',
      'quantity': '40.0000',
      'estimated_value': '12000.00',
      'status': status,
      'requested_by': 'u-1',
      'requested_at': '2026-10-03T09:30:00Z',
      'version': 2,
    };

class _Call {
  _Call(this.method, this.path, this.body, this.query);
  final String method;
  final String path;
  final Json? body;
  final Map<String, String>? query;
}

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<_Call> calls = [];

  _Call callTo(String suffix) =>
      calls.firstWhere((call) => call.path.endsWith(suffix));

  @override
  Future<PagedResult<Product>> products({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
    ProductQuery filters = const ProductQuery(),
  }) async =>
      PagedResult<Product>(items: [
        Product.fromJson(const {
          'id': 'p-1',
          'code': 'P1',
          'name': 'Detergent',
          'product_type': 'STOCK_ITEM',
          'status': 'ACTIVE',
          'unit': 'BOX',
        }),
      ], total: 1);

  @override
  Future<PagedResult<Role>> roles({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String sortBy = 'created_at',
    bool descending = true,
  }) async =>
      PagedResult<Role>(items: const [], total: 0);

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
    if (path.endsWith('/adjustment-limits')) {
      return {
        'success': true,
        'data': method == 'PUT'
            ? (body!['limits'] as List)
            : [
                {'role_code': 'STOREKEEPER', 'max_value': '5000.00'},
              ],
      };
    }
    if (path.endsWith('/adjustment-requests') && method == 'GET') {
      return {
        'success': true,
        'data': [_request('r-1'), _request('r-2', kind: 'ADJUSTMENT')],
      };
    }
    if (path.endsWith('/bulk-approve')) {
      return {
        'success': true,
        'data': {
          'done': 2,
          'refused': 0,
          'results': [
            {'id': 'r-1', 'outcome': 'DONE'},
            {'id': 'r-2', 'outcome': 'DONE'},
          ],
        },
      };
    }
    return {'success': true, 'data': _request('r-1', status: 'APPROVED')};
  }
}

void _viewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('the limits dialog saves the whole list with the declared keys',
      (tester) async {
    _viewport(tester);
    final _Api api = _Api();
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: AdjustmentLimitsDialog(
          api: api,
          permissions: _permissions(['INVENTORY_VIEW', 'INVENTORY_MANAGE_SETTINGS']),
        ),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, '5000.00'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('adjustment-limit-amount-0')), '7500');
    await tester.tap(find.byKey(const ValueKey('adjustment-limits-save')));
    await tester.pumpAndSettle();

    final _Call put = api.calls.firstWhere((call) => call.method == 'PUT');
    expect(put.path, '/api/v1/inventory/adjustment-limits');
    expect(put.body, {
      'limits': [
        {'role_code': 'STOREKEEPER', 'max_value': '7500'},
      ],
    });
    expect(tester.takeException(), isNull);
  });

  testWidgets('a refused write-off offers Submit for approval and posts it',
      (tester) async {
    _viewport(tester);
    final _Api api = _Api();
    Json? closedWith;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: FilledButton(
              onPressed: () async {
                closedWith = await showDialog<Json>(
                  context: context,
                  builder: (_) => StockActionDialog(
                    action: StockAction.writeOff,
                    productLabel: 'Detergent',
                    warehouseLabel: 'North',
                    sourceWarehouseId: 'w-1',
                    available: 100,
                    quarantined: 0,
                    warehouses: const [],
                    onSave: (Json draft) async {
                      throw const ApiException(
                        'This moves stock worth 12000.00, above your limit of '
                        '5000.00. Submit it for approval instead.',
                        statusCode: 422,
                        details: {'needs_approval': true},
                      );
                    },
                    onSubmitForApproval: (Json draft) =>
                        api.submitAdjustmentRequest('WRITE_OFF', {
                      'branch_id': 'b-1',
                      'warehouse_id': 'w-1',
                      'product_id': 'p-1',
                      ...draft,
                    }),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('submit-for-approval')), findsNothing);
    await tester.enterText(find.widgetWithText(TextField, 'Quantity'), '40');
    await tester.tap(find.widgetWithText(FilledButton, 'Write off'));
    await tester.pumpAndSettle();

    // Still open, with the server's words and the way out.
    expect(find.textContaining('Submit it for approval instead'),
        findsOneWidget);
    expect(find.byKey(const ValueKey('submit-for-approval')), findsOneWidget);
    expect(closedWith, isNull);

    await tester.tap(find.byKey(const ValueKey('submit-for-approval')));
    await tester.pumpAndSettle();

    final _Call post = api.callTo('/adjustment-requests');
    expect(post.method, 'POST');
    expect(post.body!['kind'], 'WRITE_OFF');
    expect(post.body!['adjustment'], isNull);
    final Json writeOff = post.body!['write_off'] as Json;
    expect(writeOff['product_id'], 'p-1');
    expect(writeOff['quantity'], '40');
    expect(writeOff['reason'], 'DAMAGE');
    expect(closedWith![stockSubmittedForApprovalKey], true);
    expect(tester.takeException(), isNull);
  });

  group('the Adjustment approvals grid', () {
    Future<_Api> pump(WidgetTester tester, List<String> codes) async {
      _viewport(tester);
      final _Api api = _Api();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: AdjustmentApprovalsPage(
            api: api,
            permissions: _permissions(codes),
          ),
        ),
      ));
      await tester.pumpAndSettle();
      return api;
    }

    testWidgets('lists pending requests and approves the picked one',
        (tester) async {
      final _Api api = await pump(tester, ['INVENTORY_ADJUST']);

      expect(api.callTo('/adjustment-requests').query, {'status': 'PENDING'});
      expect(find.text('Write-off'), findsOneWidget);
      expect(find.text('Adjustment'), findsOneWidget);
      expect(find.text('P1 - Detergent'), findsNWidgets(2));
      expect(find.text('12000.00'), findsNWidgets(2));

      await tester.tap(find.text('Write-off'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('adjustment-approve')));
      await tester.pumpAndSettle();

      final _Call approve = api.callTo('/adjustment-requests/r-1/approve');
      expect(approve.method, 'POST');
      expect(tester.takeException(), isNull);
    });

    testWidgets('rejects with a reason', (tester) async {
      final _Api api = await pump(tester, ['INVENTORY_ADJUST']);

      await tester.tap(find.text('Write-off'));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('adjustment-reject')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Count it again');
      await tester.tap(find.widgetWithText(FilledButton, 'Reject').last);
      await tester.pumpAndSettle();

      final _Call reject = api.callTo('/adjustment-requests/r-1/reject');
      expect(reject.body, {'reason': 'Count it again'});
      expect(tester.takeException(), isNull);
    });

    testWidgets('the status toggle asks for the other statuses',
        (tester) async {
      final _Api api = await pump(tester, ['INVENTORY_ADJUST']);

      await tester.tap(find.text('Rejected'));
      await tester.pumpAndSettle();

      expect(
        api.calls
            .where((call) => call.method == 'GET' && call.query != null)
            .last
            .query,
        {'status': 'REJECTED'},
      );
      // A decided request has nothing left to approve.
      expect(find.byKey(const ValueKey('adjustment-approve')), findsNothing);
    });

    testWidgets('bulk approve sends every ticked row with its version',
        (tester) async {
      final _Api api = await pump(tester, ['INVENTORY_ADJUST']);

      final Finder boxes = find.byType(Checkbox);
      await tester.tap(boxes.at(1));
      await tester.pumpAndSettle();
      await tester.tap(boxes.at(2));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('adjustment-bulk-approve')));
      await tester.pumpAndSettle();

      final _Call bulk = api.callTo('/adjustment-requests/bulk-approve');
      expect(bulk.body, {
        'items': [
          {'id': 'r-1', 'version': 2},
          {'id': 'r-2', 'version': 2},
        ],
      });
      expect(find.text('Approved 2 of 2'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('without INVENTORY_ADJUST nothing can be approved',
        (tester) async {
      await pump(tester, ['INVENTORY_VIEW']);
      await tester.tap(find.text('Write-off'));
      await tester.pumpAndSettle();
      final FilledButton approve = tester.widget<FilledButton>(
          find.byKey(const ValueKey('adjustment-approve')));
      expect(approve.onPressed, isNull);
    });
  });
}
