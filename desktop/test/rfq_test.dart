// Requests for quotation (PG-8): the list, the create body, quote entry, the
// comparison (lowest highlighted, a dearer choice asks why), raising orders,
// the Create RFQ action on an approved requisition, and no overflow at the two
// sizes the desktop is held to.

import 'dart:convert';
import 'dart:io';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/preferences/desktop_preferences_service.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/purchase_requisition_page.dart';
import 'package:agency_desktop/ui/purchases/rfq_page.dart';
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

Json _rfq(String id, String status) => {
      'id': id,
      'rfq_number': 'RFQ-$id',
      'rfq_date': '2026-10-05',
      'required_by': '2026-10-12',
      'branch_id': 'b-1',
      'warehouse_id': 'w-1',
      'status': status,
      'notes': null,
      'source_requisition_id': null,
      'sent_at': null,
      'closed_at': null,
      'cancel_reason': null,
      'version': 3,
      'lines': [
        {
          'id': 'rl-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'RICE',
          'product_name': 'Basmati rice',
          'quantity': '12.0000',
          'uom_id': null,
          'notes': null,
          'selected_quotation_line_id': null,
          'selection_reason': null,
        },
      ],
      'suppliers': [
        {
          'id': 's-1',
          'vendor_id': 'v-1',
          'vendor_code': 'SG',
          'vendor_name': 'Sri Ganesh Traders',
          'quotation_id': null,
          'purchase_order_id': null,
        },
        {
          'id': 's-2',
          'vendor_id': 'v-2',
          'vendor_code': 'AA',
          'vendor_name': 'Anand Agencies',
          'quotation_id': null,
          'purchase_order_id': null,
        },
      ],
    };

Json _comparison({String selected = '', String reason = ''}) => {
      'rfq_id': '2',
      'rfq_number': 'RFQ-2',
      'status': 'SENT',
      'version': 3,
      'lines': [
        {
          'rfq_line_id': 'rl-1',
          'line_number': 1,
          'product_id': 'p-1',
          'product_code': 'RICE',
          'product_name': 'Basmati rice',
          'quantity': '12.0000',
          'uom_id': null,
          'lowest_quotation_line_id': 'ql-1',
          'selected_quotation_line_id': selected.isEmpty ? null : selected,
          'selection_reason': reason.isEmpty ? null : reason,
          'quotes': [
            {
              'quotation_id': 'q-1',
              'quotation_line_id': 'ql-1',
              'vendor_id': 'v-1',
              'vendor_name': 'Sri Ganesh Traders',
              'rate': '100.0000',
              'discount_percent': '5.0000',
              'landed_rate': '95.0000',
              'lead_time_days': 4,
              'valid_until': null,
              'notes': null,
              'is_lowest': true,
            },
            {
              'quotation_id': 'q-2',
              'quotation_line_id': 'ql-2',
              'vendor_id': 'v-2',
              'vendor_name': 'Anand Agencies',
              'rate': '98.0000',
              'discount_percent': '0.0000',
              'landed_rate': '98.0000',
              'lead_time_days': 2,
              'valid_until': null,
              'notes': null,
              'is_lowest': false,
            },
          ],
        },
      ],
    };

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<String> calls = <String>[];
  final Map<String, Json?> bodies = <String, Json?>{};
  String selected = '';
  String reason = '';

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
    switch (call) {
      case 'GET /api/v1/rfqs':
        return {
          'data': [_rfq('1', 'DRAFT'), _rfq('2', 'SENT'), _rfq('3', 'CLOSED')],
          'pagination': {'total_records': 3},
        };
      case 'POST /api/v1/rfqs':
        return {'data': _rfq('9', 'DRAFT')};
      case 'GET /api/v1/rfqs/2/quotations':
        return {'data': <Json>[]};
      case 'PUT /api/v1/rfqs/2/quotations/v-1':
        return {
          'data': {
            'id': 'q-1',
            'rfq_id': '2',
            'vendor_id': 'v-1',
            'vendor_name': 'Sri Ganesh Traders',
            'quote_ref': 'Q-77',
            'quote_date': '2026-10-05',
            'version': 1,
            'lines': [
              {
                'id': 'ql-1',
                'rfq_line_id': 'rl-1',
                'rate': '100.0000',
                'discount_percent': '5.0000',
                'landed_rate': '95.0000',
                'lead_time_days': 4,
              },
            ],
          },
        };
      case 'GET /api/v1/rfqs/2/comparison':
        return {'data': _comparison(selected: selected, reason: reason)};
      case 'PUT /api/v1/rfqs/2/selections':
        final List<dynamic> sent = body!['selections'] as List<dynamic>;
        final Map<String, dynamic> first = sent.first as Map<String, dynamic>;
        selected = first['quotation_line_id'] as String;
        reason = (first['reason'] as String?) ?? '';
        return {'data': _comparison(selected: selected, reason: reason)};
      case 'POST /api/v1/rfqs/2/raise-orders':
        return {
          'data': [
            {'id': 'po-1', 'po_number': 'PO-0001'},
          ],
        };
      case 'POST /api/v1/rfqs/from-requisition/r-1':
        return {'data': _rfq('7', 'DRAFT')};
      case 'GET /api/v1/purchases/requisitions':
        return {
          'data': [
            {
              'id': 'r-1',
              'branch_id': 'b-1',
              'warehouse_id': 'w-1',
              'requisition_number': 'REQ-1',
              'requisition_date': '2026-10-03',
              'status': 'APPROVED',
              'version': 1,
              'lines': <Json>[],
            },
          ],
        };
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
          {'id': 'v-2', 'code': 'AA', 'name': 'Anand Agencies'},
        ],
        'pagination': {'total_records': 2},
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
    return {'data': const <dynamic>[]};
  }
}

const List<String> _all = [
  'RFQ_VIEW',
  'RFQ_MANAGE',
  'PURCHASE_CREATE',
  'PURCHASE_VIEW',
  'PURCHASE_REQUISITION_CREATE',
];

Future<void> _pump(
  WidgetTester tester,
  _Api api, {
  Size size = const Size(1366, 768),
  List<String> perms = _all,
  bool requisitions = false,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final DesktopPreferencesService preferences = DesktopPreferencesService(
    directory: Directory.systemTemp.createTempSync('rfqs'),
  );
  await tester.pumpWidget(MaterialApp(
    builder: (context, child) => Phase2Scope(child: child!),
    home: Scaffold(
      body: requisitions
          ? PurchaseRequisitionPage(
              api: api,
              preferences: preferences,
              permissions: _permissions(perms),
              hasActiveFirm: true,
            )
          : RfqPage(
              api: api,
              preferences: preferences,
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

Future<void> _openComparison(WidgetTester tester) async {
  await _select(tester, 'RFQ-2');
  await _command(tester, 'compare');
}

void main() {
  testWidgets('the list shows number, date, status, lines and suppliers',
      (tester) async {
    await _pump(tester, _Api());

    expect(find.text('RFQ-1'), findsOneWidget);
    expect(find.text('RFQ-3'), findsOneWidget);
    expect(find.text('2026-10-12'), findsWidgets);
    expect(find.text('Draft'), findsOneWidget);
    expect(find.text('Sent'), findsOneWidget);
    expect(find.text('Closed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('creating sends only the fields the server declares',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byKey(const ValueKey('toolbar-new')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rfq-warehouse-b-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Main').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rfq-product-0')), 'Rice');
    await tester.pumpAndSettle();
    await tester.tap(find.text('RICE · Basmati rice').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const ValueKey('rfq-quantity-0')), '12');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('rfq-add-supplier-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sri Ganesh Traders').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rfq-save')));
    await tester.pumpAndSettle();

    final Json sent = api.bodies['POST /api/v1/rfqs']!;
    expect(
        sent.keys.toSet(),
        <String>{
          'branch_id',
          'warehouse_id',
          'rfq_date',
          'lines',
          'vendor_ids',
        });
    expect(sent['branch_id'], 'b-1');
    expect(sent['warehouse_id'], 'w-1');
    expect(sent['vendor_ids'], <String>['v-1']);
    expect(sent['lines'], <Json>[
      <String, dynamic>{'product_id': 'p-1', 'quantity': '12'},
    ]);
    expect(find.byType(RfqDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a sent request opens read-only', (tester) async {
    await _pump(tester, _Api());

    await _select(tester, 'RFQ-2');
    await tester.tap(find.byKey(const ValueKey('selection-edit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('rfq-read-only')), findsOneWidget);
    expect(find.byKey(const ValueKey('rfq-save')), findsNothing);
  });

  testWidgets('send hits its own path and cancel asks for a reason',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'RFQ-1');
    await _command(tester, 'send');
    expect(api.calls, contains('POST /api/v1/rfqs/1/send'));

    await _command(tester, 'cancel');
    await tester.enterText(find.byType(TextField).last, 'Bought elsewhere');
    await tester.pump();
    await tester.tap(find.text('Cancel request'));
    await tester.pumpAndSettle();
    expect(api.bodies['POST /api/v1/rfqs/1/cancel'],
        {'reason': 'Bought elsewhere'});
  });

  testWidgets('keying a quote PUTs it to that supplier', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await _select(tester, 'RFQ-2');
    await _command(tester, 'quotes');
    await tester.enterText(find.byKey(const ValueKey('quote-ref')), 'Q-77');
    await tester.enterText(find.byKey(const ValueKey('quote-rate-0')), '100');
    await tester.enterText(
        find.byKey(const ValueKey('quote-discount-0')), '5');
    await tester.enterText(find.byKey(const ValueKey('quote-lead-0')), '4');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('quote-save')));
    await tester.pumpAndSettle();

    final Json sent = api.bodies['PUT /api/v1/rfqs/2/quotations/v-1']!;
    expect(sent['quote_ref'], 'Q-77');
    expect(sent['quote_date'], isNotEmpty);
    expect(sent['lines'], <Json>[
      <String, dynamic>{
        'rfq_line_id': 'rl-1',
        'rate': '100',
        'discount_percent': '5',
        'lead_time_days': 4,
      },
    ]);
    expect(find.byKey(const ValueKey('quote-done')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the comparison highlights the lowest landed rate',
      (tester) async {
    await _pump(tester, _Api());
    await _openComparison(tester);

    expect(find.byKey(const ValueKey('cmp-lowest-rl-1-v-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('cmp-lowest-rl-1-v-2')), findsNothing);
    expect(find.text('95.0000'), findsOneWidget);
    expect(find.text('98.0000'), findsOneWidget);
    expect(find.text('4 days'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('choosing a dearer quote asks why and sends the reason',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _openComparison(tester);

    await tester.tap(find.byKey(const ValueKey('cmp-cell-rl-1-v-2')));
    await tester.pumpAndSettle();
    expect(find.text('Not the lowest rate'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, 'Faster delivery');
    await tester.pump();
    await tester.tap(find.text('Choose it'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('cmp-save')));
    await tester.pumpAndSettle();
    expect(api.bodies['PUT /api/v1/rfqs/2/selections'], {
      'selections': [
        {
          'rfq_line_id': 'rl-1',
          'quotation_line_id': 'ql-2',
          'reason': 'Faster delivery',
        },
      ],
    });
  });

  testWidgets('choosing the lowest asks nothing; raising orders posts',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);
    await _openComparison(tester);

    // Nothing is chosen yet, so orders cannot be raised.
    expect(
        tester
            .widget<FilledButton>(find.byKey(const ValueKey('cmp-raise')))
            .onPressed,
        isNull);
    await tester.tap(find.byKey(const ValueKey('cmp-cell-rl-1-v-1')));
    await tester.pumpAndSettle();
    expect(find.text('Not the lowest rate'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('cmp-save')));
    await tester.pumpAndSettle();
    expect(api.bodies['PUT /api/v1/rfqs/2/selections'], {
      'selections': [
        {'rfq_line_id': 'rl-1', 'quotation_line_id': 'ql-1'},
      ],
    });

    await tester.tap(find.byKey(const ValueKey('cmp-raise')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('rfq-raise-confirm')));
    await tester.pumpAndSettle();

    expect(api.calls, contains('POST /api/v1/rfqs/2/raise-orders'));
    expect(find.byKey(const ValueKey('rfq-orders-raised')), findsOneWidget);
    expect(find.text('PO-0001'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an approved requisition can ask for quotes', (tester) async {
    final _Api api = _Api();
    await _pump(tester, api, requisitions: true);

    await _select(tester, 'REQ-1');
    await _command(tester, 'rfq');

    expect(api.calls, contains('POST /api/v1/rfqs/from-requisition/r-1'));
    expect(find.textContaining('RFQ-7 created from REQ-1'), findsOneWidget);
  });

  for (final Size size in const [Size(1366, 768), Size(800, 600)]) {
    testWidgets('no overflow at ${size.width.toInt()}x${size.height.toInt()}',
        (tester) async {
      final _Api api = _Api();
      await _pump(tester, api, size: size);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byKey(const ValueKey('toolbar-new')));
      await tester.pumpAndSettle();
      expect(find.byType(RfqDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      await _select(tester, 'RFQ-2');
      await _command(tester, 'quotes');
      expect(find.byType(RfqQuotesDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const ValueKey('quote-close')));
      await tester.pumpAndSettle();

      await _command(tester, 'compare');
      expect(find.byType(RfqComparisonDialog), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
