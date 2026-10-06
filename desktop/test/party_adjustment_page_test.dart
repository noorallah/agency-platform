// Party adjustments: clearing a balance with no money moving.
//
// Phase 2 only. The screen lists the adjustments, drafts a write-off against
// a customer's open bill, drafts a set-off naming both a customer and a
// supplier, approves a draft and cancels only once a reason is given.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/party_adjustment_page.dart';
import 'package:agency_desktop/ui/workspace/desktop_framework.dart'
    show Phase2Scope;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

String _accessToken(Map<String, dynamic> claims) =>
    'header.${base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '')}.sig';

PermissionService _permissions({
  List<String> perms = const [
    'PARTY_ADJUSTMENT_VIEW',
    'PARTY_ADJUSTMENT_MANAGE',
    'PARTY_ADJUSTMENT_APPROVE',
  ],
}) =>
    PermissionService()
      ..applyAccessToken(_accessToken({
        'roles': <String>['user'],
        'permissions': perms,
      }));

/// One draft write-off of 500 against Kumar Stores.
Json _adjustment({
  String status = 'DRAFT',
  String kind = 'CUSTOMER_WRITE_OFF',
  bool needsSecond = false,
}) =>
    <String, dynamic>{
      'id': 'pa-1',
      'adjustment_number': 'PADJ-2026-0001',
      'adjustment_date': '2026-09-02',
      'kind': kind,
      'status': status,
      'customer_id': 'cus-1',
      'customer_name': 'Kumar Stores',
      'vendor_id': null,
      'vendor_name': null,
      'amount': '500.00',
      'reason': 'Shop closed',
      'customer_allocated': '500.00',
      'supplier_allocated': '0.00',
      'needs_second_approver': needsSecond,
      'journal_entry_id': null,
      'cancel_reason': null,
      'version': 3,
      'allocations': const <Json>[],
    };

Json _bill(String id, String number, String outstanding) => <String, dynamic>{
      'invoice_id': id,
      'invoice_number': number,
      'invoice_date': '2026-08-01',
      'invoice_total': outstanding,
      'allocated_amount': '0.00',
      'outstanding_amount': outstanding,
      'party_id': 'p',
      'due_date': null,
      'is_opening_bill': false,
    };

class _AdjustmentApi extends ApiClient {
  _AdjustmentApi({this.rows = const []})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> rows;
  final List<String> requested = <String>[];
  final List<Map<String, String>> queries = <Map<String, String>>[];
  int? sentVersion;
  Json? cancelBody;
  Json? created;
  Json? updated;
  Json? limitsSaved;

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
    queries.add(query ?? const <String, String>{});
    if (path == '/api/v1/customers') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{'id': 'cus-1', 'name': 'Kumar Stores'},
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/vendors') {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'ven-1',
            'name': 'Kumar Wholesale',
            'display_name': 'Kumar Wholesale',
          },
        ],
        'pagination': <String, dynamic>{'total_records': 1},
      };
    }
    if (path == '/api/v1/party-adjustments/open-bills') {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'customer_bills': query?['customer_id'] == null
              ? const <Json>[]
              : <Json>[_bill('sb-1', 'SI-0001', '800.00')],
          'supplier_bills': query?['vendor_id'] == null
              ? const <Json>[]
              : <Json>[_bill('pb-1', 'PI-0001', '700.00')],
          'customer_balance': query?['customer_id'] == null ? null : '800.00',
          'supplier_outstanding':
              query?['vendor_id'] == null ? null : '700.00',
        },
      };
    }
    if (path == '/api/v1/party-adjustments/settings') {
      if (method == 'PUT') limitsSaved = body;
      return <String, dynamic>{
        'data': <String, dynamic>{
          'approval_threshold': '10000.00',
          'rounding_limit': '10.00',
          'is_default': true,
        },
      };
    }
    if (method == 'POST' && path == '/api/v1/party-adjustments') {
      created = body;
      return <String, dynamic>{'data': _adjustment()};
    }
    if (method == 'PUT' && path.startsWith('/api/v1/party-adjustments/')) {
      updated = body;
      sentVersion = expectedVersion;
      return <String, dynamic>{'data': _adjustment()};
    }
    if (path.startsWith('/api/v1/party-adjustments/')) {
      sentVersion = expectedVersion;
      if (path.endsWith('/cancel')) cancelBody = body;
      return <String, dynamic>{'data': _adjustment()};
    }
    if (path == '/api/v1/party-adjustments') {
      return <String, dynamic>{
        'data': rows,
        'pagination': <String, dynamic>{'total_records': rows.length},
      };
    }
    return <String, dynamic>{'data': const <Json>[]};
  }
}

DesktopPreferencesService _preferences() => DesktopPreferencesService(
      directory: Directory.systemTemp.createTempSync('party-adjustments'),
    );

Future<void> _pump(
  WidgetTester tester,
  _AdjustmentApi api, {
  PermissionService? permissions,
  Size size = const Size(1600, 900),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: PartyAdjustmentPage(
        api: api,
        preferences: _preferences(),
        permissions: permissions ?? _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _pick(WidgetTester tester, Key menu, String label) async {
  await tester.tap(find.byKey(menu));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

Future<void> _select(WidgetTester tester) async {
  await tester.tap(find.text('PADJ-2026-0001').first);
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the list shows the number, the kind, the party and the amount',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api);

    expect(find.text('PADJ-2026-0001'), findsOneWidget);
    expect(find.text('Write-off (bad debt)'), findsOneWidget);
    expect(find.text('Kumar Stores'), findsWidgets);
    expect(find.text('500.00'), findsOneWidget);
    expect(find.text('Shop closed'), findsOneWidget);
  });

  testWidgets('the bar approves the picked draft, sending its version',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api);
    await _select(tester);

    await tester.tap(find.byKey(const ValueKey('selection-approve')));
    await tester.pumpAndSettle();
    expect(
      api.requested,
      contains('POST /api/v1/party-adjustments/pa-1/approve'),
    );
    expect(api.sentVersion, 3);
  });

  testWidgets('a draft above the limit says it needs a second person',
      (tester) async {
    final _AdjustmentApi api =
        _AdjustmentApi(rows: <Json>[_adjustment(needsSecond: true)]);
    await _pump(tester, api);
    await _select(tester);

    expect(find.textContaining('needs a second person'), findsWidgets);
  });

  testWidgets('cancelling asks why and sends the reason', (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api);
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-cancel')));
    await tester.pumpAndSettle();

    expect(
      api.requested,
      isNot(contains('POST /api/v1/party-adjustments/pa-1/cancel')),
    );
    await tester.enterText(find.byType(TextField).last, 'Entered twice');
    await tester.pump();
    await tester.tap(find.text('Cancel adjustment'));
    await tester.pumpAndSettle();

    expect(
      api.requested,
      contains('POST /api/v1/party-adjustments/pa-1/cancel'),
    );
    expect(api.cancelBody, <String, dynamic>{'reason': 'Entered twice'});
    expect(api.sentVersion, 3);
  });

  testWidgets('without the approve permission nothing is approved',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(
      tester,
      api,
      permissions: _permissions(
        perms: const ['PARTY_ADJUSTMENT_VIEW', 'PARTY_ADJUSTMENT_MANAGE'],
      ),
    );
    await _select(tester);
    expect(find.byKey(const ValueKey('selection-approve')), findsNothing);
  });

  testWidgets('a firm with no permission sees nothing', (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api, permissions: _permissions(perms: const []));

    expect(find.text('You cannot see party adjustments'), findsOneWidget);
    expect(api.requested, isEmpty);
  });

  testWidgets('the screen fits the smallest supported window, with a row picked',
      (tester) async {
    final _AdjustmentApi api =
        _AdjustmentApi(rows: <Json>[_adjustment(needsSecond: true)]);
    await _pump(tester, api, size: const Size(1366, 768));
    expect(tester.takeException(), isNull);
    await _select(tester);
    expect(tester.takeException(), isNull);
  });

  testWidgets('drafting a write-off allocates against the open bill',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // A write-off names a customer and no supplier.
    expect(find.byKey(const ValueKey('pa-vendor')), findsNothing);
    await _pick(tester, const ValueKey('pa-customer'), 'Kumar Stores');
    expect(
      api.queries.any((q) =>
          q['customer_id'] == 'cus-1' && !q.containsKey('vendor_id')),
      isTrue,
    );
    expect(find.text('SI-0001'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('pa-amount')), '500');
    await tester.enterText(find.byKey(const ValueKey('pa-reason')), 'Closed');
    await tester.enterText(
      find.byKey(const ValueKey('pa-alloc-CUSTOMER-sb-1')),
      '500',
    );
    await tester.tap(find.byKey(const ValueKey('pa-save')));
    await tester.pumpAndSettle();

    expect(api.created?['kind'], 'CUSTOMER_WRITE_OFF');
    expect(api.created?['customer_id'], 'cus-1');
    expect(api.created?['amount'], '500');
    expect(api.created?['reason'], 'Closed');
    expect(api.created?['allocations'], [
      <String, dynamic>{'side': 'CUSTOMER', 'bill_id': 'sb-1', 'amount': '500'},
    ]);
    // Only the keys the server declares.
    expect(
      api.created!.keys.toSet().difference(const {
        'kind',
        'adjustment_date',
        'customer_id',
        'vendor_id',
        'amount',
        'reason',
        'adjustment_number',
        'allocations',
      }),
      isEmpty,
    );
    expect(api.created!.containsKey('vendor_id'), isFalse);
  });

  testWidgets('a set-off is drafted from its own action with both parties',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api, size: const Size(1366, 768));
    // Not about a row, so it lives behind "...".
    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    await tester
        .tap(find.byKey(const ValueKey('toolbar-command-new-set-off-menu')));
    await tester.pumpAndSettle();

    await _pick(tester, const ValueKey('pa-customer'), 'Kumar Stores');
    await _pick(tester, const ValueKey('pa-vendor'), 'Kumar Wholesale');
    expect(find.text('SI-0001'), findsOneWidget);
    expect(find.text('PI-0001'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('pa-amount')), '600');
    await tester.enterText(
        find.byKey(const ValueKey('pa-reason')), 'Same business');
    await tester.enterText(
        find.byKey(const ValueKey('pa-alloc-CUSTOMER-sb-1')), '600');
    await tester.enterText(
        find.byKey(const ValueKey('pa-alloc-SUPPLIER-pb-1')), '600');
    await tester.tap(find.byKey(const ValueKey('pa-save')));
    await tester.pumpAndSettle();

    expect(api.created?['kind'], 'SET_OFF');
    expect(api.created?['customer_id'], 'cus-1');
    expect(api.created?['vendor_id'], 'ven-1');
    expect(
      (api.created?['allocations'] as List).map((a) => (a as Json)['side']),
      <String>['CUSTOMER', 'SUPPLIER'],
    );
  });

  testWidgets('more taken off a bill than it owes is refused before the server',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await _pick(tester, const ValueKey('pa-customer'), 'Kumar Stores');

    await tester.enterText(find.byKey(const ValueKey('pa-amount')), '900');
    await tester.enterText(find.byKey(const ValueKey('pa-reason')), 'Closed');
    await tester.enterText(
        find.byKey(const ValueKey('pa-alloc-CUSTOMER-sb-1')), '900');
    await tester.tap(find.byKey(const ValueKey('pa-save')));
    await tester.pumpAndSettle();

    expect(api.created, isNull);
    expect(find.textContaining('cannot be taken off it'), findsOneWidget);
  });

  testWidgets('editing a draft sends only the declared keys and its version',
      (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api, size: const Size(1366, 768));
    await _select(tester);
    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const ValueKey('pa-reason')), 'Moved');
    await tester.tap(find.byKey(const ValueKey('pa-save')));
    await tester.pumpAndSettle();

    expect(api.requested, contains('PUT /api/v1/party-adjustments/pa-1'));
    expect(api.sentVersion, 3);
    expect(api.updated?['reason'], 'Moved');
    expect(api.updated!.containsKey('kind'), isFalse);
    expect(api.updated!.containsKey('status'), isFalse);
  });

  testWidgets('Limits reads and saves the firm limits', (tester) async {
    final _AdjustmentApi api = _AdjustmentApi(rows: <Json>[_adjustment()]);
    await _pump(tester, api);
    await tester.tap(find.byKey(const ValueKey('toolbar-more')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('toolbar-command-limits-menu')));
    await tester.pumpAndSettle();
    expect(api.requested, contains('GET /api/v1/party-adjustments/settings'));

    await tester.enterText(
        find.byKey(const ValueKey('pa-limit-threshold')), '2500');
    await tester.tap(find.byKey(const ValueKey('pa-limits-save')));
    await tester.pumpAndSettle();

    expect(api.limitsSaved, <String, dynamic>{
      'approval_threshold': '2500',
      'rounding_limit': '10.00',
    });
  });
}
