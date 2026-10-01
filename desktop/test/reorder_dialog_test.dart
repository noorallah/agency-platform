// Below reorder level, and the draft orders that put it right (backlog 42.9).
//
// The dialog lists what is short, ticks every row that can be ordered, lets a
// quantity be changed, and sends the ticked rows to the server in one call.
// A row no supplier has billed cannot be ticked, and a refusal keeps the
// dialog open with the server's words.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/reorder_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _ReorderApi extends ApiClient {
  _ReorderApi({this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuse;
  final List<Json> sent = <Json>[];

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
    if (path.endsWith('/reports/below-reorder')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'warehouse_id': 'wh-1',
            'warehouse_code': 'MAIN',
            'product_id': 'p-1',
            'product_code': 'SKU-001',
            'product_name': 'Basmati 5kg',
            'available_quantity': '3.0000',
            'reorder_level': '5.0000',
            'on_order_quantity': '0.0000',
            'suggested_quantity': '17.0000',
            'basis': 'SALES',
            'average_daily_sales': '1.5000',
            'supplier_id': 'v-1',
            'supplier_name': 'Sri Ganesh Traders',
          },
          <String, dynamic>{
            'warehouse_id': 'wh-1',
            'warehouse_code': 'MAIN',
            'product_id': 'p-2',
            'product_code': 'SKU-002',
            'product_name': 'Toor dal 1kg',
            'available_quantity': '1.0000',
            'reorder_level': '4.0000',
            'on_order_quantity': '0.0000',
            'suggested_quantity': '3.0000',
            'basis': 'LEVEL',
            'average_daily_sales': null,
            'supplier_id': null,
            'supplier_name': null,
          },
        ],
      };
    }
    if (path.endsWith('/reorder-planning')) {
      return <String, dynamic>{
        'data': <String, dynamic>{
          'basis': 'SALES',
          'sales_window_days': 30,
          'lead_time_days': 7,
          'safety_days': 3,
          'cover_days': 30,
          'is_configured': true,
        },
      };
    }
    if (path.endsWith('/reorder-drafts')) {
      sent.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      if (refuse != null) throw ApiException(refuse!);
      return <String, dynamic>{
        'data': <Json>[],
        'message': '1 draft purchase order(s) raised.',
      };
    }
    return <String, dynamic>{'data': <Json>[]};
  }
}

Future<void> _open(WidgetTester tester, _ReorderApi api) async {
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
              builder: (_) => ReorderDialog(api: api),
            ),
            child: const Text('Open'),
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('ticked rows are raised with the quantity typed',
      (tester) async {
    final _ReorderApi api = _ReorderApi();
    await _open(tester, api);

    expect(find.text('SKU-001 · Basmati 5kg'), findsOneWidget);
    // The unbilled product is listed but cannot be ticked.
    final Checkbox unbilled =
        tester.widget(find.byKey(const ValueKey('reorder-tick-1')));
    expect(unbilled.onChanged, isNull);
    expect(find.text('No supplier has billed it yet'), findsOneWidget);

    await tester.enterText(
        find.byKey(const ValueKey('reorder-quantity-0')), '20');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reorder-raise')));
    await tester.pumpAndSettle();

    expect(api.sent.single['items'], <Json>[
      <String, dynamic>{
        'warehouse_id': 'wh-1',
        'product_id': 'p-1',
        'quantity': '20',
      },
    ]);
    expect(find.byType(ReorderDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('each row says its basis and the firm basis is noted',
      (tester) async {
    await _open(tester, _ReorderApi());

    expect(find.byKey(const ValueKey('reorder-planning-note')), findsOneWidget);
    expect(find.textContaining('30-day average'), findsOneWidget);
    expect(find.text('Basis'), findsOneWidget);
    expect(find.text('Avg/day'), findsOneWidget);
    expect(find.text('Sales'), findsOneWidget);
    expect(find.text('Level'), findsOneWidget);
    expect(find.text('1.5'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a refusal keeps the dialog open with the reason',
      (tester) async {
    final _ReorderApi api =
        _ReorderApi(refuse: 'No order was raised. SKU-001: nothing to order.');
    await _open(tester, api);

    await tester.tap(find.byKey(const ValueKey('reorder-raise')));
    await tester.pumpAndSettle();

    expect(find.byType(ReorderDialog), findsOneWidget);
    expect(find.textContaining('nothing to order'), findsOneWidget);
  });
}
