// Plan an order by company from average sales (backlog 130).
//
// Nothing is listed until Show; the rows carry the sum's figures; a row with
// nothing to order or no supplier is not ticked; Raise sends the choices the
// shown rows were computed with plus the ticked items; a refusal keeps the
// dialog open.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/order_plan_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _PlanApi extends ApiClient {
  _PlanApi({this.refuse, this.planningRefused = false})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuse;
  final bool planningRefused;
  final List<Uri> planReads = <Uri>[];
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
    if (path.contains('/purchases/order-plan/drafts')) {
      sent.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      if (refuse != null) throw ApiException(refuse!);
      return <String, dynamic>{
        'data': <Json>[],
        'message': '1 draft purchase order(s) raised.',
      };
    }
    if (path.contains('/purchases/order-plan')) {
      planReads.add(Uri.parse(path));
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'product_id': 'p-1',
            'product_code': 'SKU-001',
            'product_name': 'Basmati 5kg',
            'brand_name': 'Royal',
            'sold_quantity': '900.0000',
            'average_daily_sales': '10.0000',
            'required_quantity': '300.0000',
            'available_quantity': '40.0000',
            'on_order_quantity': '10.0000',
            'suggested_quantity': '250.0000',
            'supplier_id': 'v-1',
            'supplier_name': 'Sri Ganesh Traders',
          },
          <String, dynamic>{
            'product_id': 'p-2',
            'product_code': 'SKU-002',
            'product_name': 'Toor dal 1kg',
            'brand_name': 'Royal',
            'sold_quantity': '90.0000',
            'average_daily_sales': '1.0000',
            'required_quantity': '30.0000',
            'available_quantity': '80.0000',
            'on_order_quantity': '0.0000',
            'suggested_quantity': '0.0000',
            'supplier_id': 'v-1',
            'supplier_name': 'Sri Ganesh Traders',
          },
          <String, dynamic>{
            'product_id': 'p-3',
            'product_code': 'SKU-003',
            'product_name': 'Sona rice 1kg',
            'brand_name': 'Royal',
            'sold_quantity': '45.0000',
            'average_daily_sales': '0.5000',
            'required_quantity': '15.0000',
            'available_quantity': '0.0000',
            'on_order_quantity': '0.0000',
            'suggested_quantity': '15.0000',
            'supplier_id': null,
            'supplier_name': null,
          },
        ],
      };
    }
    if (path.endsWith('/reorder-planning')) {
      if (planningRefused) throw const ApiException('No permission.');
      return <String, dynamic>{
        'data': <String, dynamic>{
          'basis': 'SALES',
          'sales_window_days': 60,
          'lead_time_days': 7,
          'safety_days': 3,
          'cover_days': 21,
          'is_configured': true,
        },
      };
    }
    if (path.contains('/api/v1/warehouses')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'wh-1',
            'code': 'MAIN',
            'name': 'Main godown',
          },
        ],
      };
    }
    if (path.contains('/products/principals')) {
      return <String, dynamic>{
        'data': <Json>[
          <String, dynamic>{
            'id': 'co-1',
            'code': 'ROY',
            'name': 'Royal Foods',
            'is_active': true,
          },
        ],
      };
    }
    return <String, dynamic>{'data': <Json>[]};
  }
}

Future<void> _open(
  WidgetTester tester,
  _PlanApi api, {
  Size size = const Size(1366, 768),
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => Center(
          child: FilledButton(
            onPressed: () => showDialog<Object>(
              context: context,
              builder: (_) => OrderPlanDialog(api: api),
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

Future<void> _chooseCompany(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('order-plan-company')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Royal Foods').last);
  await tester.pumpAndSettle();
}

Future<void> _show(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('order-plan-show')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('Show sends the choices and lists the figures', (tester) async {
    final _PlanApi api = _PlanApi();
    await _open(tester, api);

    // Nothing is listed until Show.
    expect(api.planReads, isEmpty);
    expect(find.text('SKU-001 · Basmati 5kg'), findsNothing);

    await _chooseCompany(tester);
    await _show(tester);

    final Map<String, List<String>> asked =
        api.planReads.single.queryParametersAll;
    expect(asked['warehouse_id'], ['wh-1']);
    expect(asked['company_id'], ['co-1']);
    expect(asked['sales_days'], ['60']);
    expect(asked['cover_days'], ['21']);
    expect(asked.containsKey('vendor_id'), isFalse);

    expect(find.text('SKU-001 · Basmati 5kg'), findsOneWidget);
    expect(find.text('900'), findsOneWidget);
    expect(find.text('10'), findsWidgets);
    expect(find.text('300'), findsOneWidget);
    expect(find.text('250'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('nothing to order is not ticked and no supplier cannot be',
      (tester) async {
    await _open(tester, _PlanApi());
    await _show(tester);

    expect(
        tester
            .widget<Checkbox>(find.byKey(const ValueKey('order-plan-tick-0')))
            .value,
        isTrue);
    final Checkbox noNeed =
        tester.widget(find.byKey(const ValueKey('order-plan-tick-1')));
    expect(noNeed.value, isFalse);
    final Checkbox noSupplier =
        tester.widget(find.byKey(const ValueKey('order-plan-tick-2')));
    expect(noSupplier.value, isFalse);
    expect(noSupplier.onChanged, isNull);
    expect(find.text('No supplier known'), findsOneWidget);
    expect(find.text('Raise draft orders (1)'), findsOneWidget);
  });

  testWidgets('Raise posts the kept choices and the ticked quantities',
      (tester) async {
    final _PlanApi api = _PlanApi();
    await _open(tester, api);
    await _chooseCompany(tester);
    await _show(tester);

    // Changing a box after Show does not change what is raised.
    await tester.enterText(
        find.byKey(const ValueKey('order-plan-sales-days')), '30');
    await tester.enterText(
        find.byKey(const ValueKey('order-plan-quantity-0')), '260');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('order-plan-raise')));
    await tester.pumpAndSettle();

    expect(api.sent.single, <String, dynamic>{
      'warehouse_id': 'wh-1',
      'company_id': 'co-1',
      'brand_ids': <String>[],
      'vendor_id': null,
      'sales_days': 60,
      'cover_days': 21,
      'items': <Json>[
        <String, dynamic>{'product_id': 'p-1', 'quantity': '260'},
      ],
    });
    expect(find.byType(OrderPlanDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a refusal keeps the dialog open with the reason',
      (tester) async {
    final _PlanApi api =
        _PlanApi(refuse: 'No order was raised. SKU-001: not sold by anyone.');
    await _open(tester, api);
    await _show(tester);

    await tester.tap(find.byKey(const ValueKey('order-plan-raise')));
    await tester.pumpAndSettle();

    expect(find.byType(OrderPlanDialog), findsOneWidget);
    expect(find.textContaining('not sold by anyone'), findsOneWidget);
  });

  testWidgets('the days start at the firm planning figures', (tester) async {
    await _open(tester, _PlanApi());
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('order-plan-sales-days')))
            .controller!
            .text,
        '60');
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('order-plan-cover-days')))
            .controller!
            .text,
        '21');
  });

  testWidgets('the days fall back to 90 and 30 when planning is refused',
      (tester) async {
    await _open(tester, _PlanApi(planningRefused: true));
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('order-plan-sales-days')))
            .controller!
            .text,
        '90');
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('order-plan-cover-days')))
            .controller!
            .text,
        '30');
  });

  testWidgets('fits the 800x600 window with rows shown', (tester) async {
    await _open(tester, _PlanApi(), size: const Size(800, 600));
    await _show(tester);

    expect(find.byKey(const ValueKey('order-plan-row-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('order-plan-download')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
