// The Buying stages dialog (backlog §38): the twin of the sales one, so it
// keeps D-CFG-14's rules -- no save until the firm's own settings were read,
// and only the two switches are sent -- and it never offers the one pair the
// server refuses, receipts typed with orders not.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/purchase.dart';
import 'package:agency_desktop/ui/purchases/purchase_workflow_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _StagesApi extends ApiClient {
  _StagesApi({required this.failReads, this.ordersOn = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// How many reads fail before one succeeds.
  int failReads;
  final bool ordersOn;
  final List<Json> saved = [];

  @override
  Future<PurchaseWorkflowSettings> purchaseWorkflowSettings() async {
    if (failReads > 0) {
      failReads -= 1;
      throw const ApiException('The server is not answering.');
    }
    return PurchaseWorkflowSettings.fromJson(<String, dynamic>{
      'purchase_order_stage': ordersOn,
      'goods_receipt_stage': ordersOn,
      'default_branch_id': 'branch-1',
      'default_warehouse_id': 'warehouse-1',
      'is_configured': true,
    });
  }

  @override
  Future<PurchaseWorkflowSettings> updatePurchaseWorkflowSettings(
    PurchaseWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

PermissionService _holder(List<String> codes) {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{'permissions': codes})))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.signature');
}

Future<void> _open(
  WidgetTester tester,
  _StagesApi api, {
  List<String> codes = const ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS'],
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PurchaseWorkflowSettingsDialog(
          api: api,
          permissions: _holder(codes),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

FilledButton _saveButton(WidgetTester tester) => tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );

bool _on(WidgetTester tester, String label) => tester
    .widget<SwitchListTile>(find.widgetWithText(SwitchListTile, label))
    .value;

void main() {
  testWidgets('a failed read offers no save until a read succeeds',
      (tester) async {
    final _StagesApi api = _StagesApi(failReads: 1);
    await _open(tester, api);

    expect(find.textContaining('could not be read'), findsOneWidget);
    expect(_saveButton(tester).onPressed, isNull);

    await tester.tap(find.byKey(const ValueKey('purchase-stages-retry')));
    await tester.pumpAndSettle();
    expect(_saveButton(tester).onPressed, isNotNull);
  });

  testWidgets('switching orders off switches receipts off with it, and a save '
      'sends only the two switches', (tester) async {
    final _StagesApi api = _StagesApi(failReads: 0);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Purchase order'));
    await tester.pumpAndSettle();
    expect(_on(tester, 'Purchase order'), isFalse);
    expect(_on(tester, 'Goods receipt'), isFalse);
    expect(find.textContaining("One screen: the supplier's bill"),
        findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved.single, <String, dynamic>{
      'purchase_order_stage': false,
      'goods_receipt_stage': false,
      'bill_price_tolerance_percent': null,
      'bill_tolerance_amount': null,
      'order_quantity_policy': 'WARN',
    });
  });

  testWidgets('switching receipts on switches orders on with it',
      (tester) async {
    final _StagesApi api = _StagesApi(failReads: 0, ordersOn: false);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Goods receipt'));
    await tester.pumpAndSettle();
    expect(_on(tester, 'Goods receipt'), isTrue);
    expect(_on(tester, 'Purchase order'), isTrue);
  });

  testWidgets('without the settings permission the switches are shut',
      (tester) async {
    final _StagesApi api = _StagesApi(failReads: 0);
    await _open(tester, api, codes: const ['PURCHASE_VIEW']);

    expect(
      tester
          .widget<SwitchListTile>(
            find.widgetWithText(SwitchListTile, 'Purchase order'),
          )
          .onChanged,
      isNull,
    );
    expect(_saveButton(tester).onPressed, isNull);
    expect(find.textContaining('manage purchase settings'), findsOneWidget);
  });
}
