// The Sales stages dialog saves only what it read, and only the stages.
//
// D-CFG-14: the dialog starts from the whole chain and, when its read failed,
// still offered Save -- so one click replaced whatever the firm had chosen
// with a chain nobody picked. And it sent the default branch and warehouse it
// never shows, which the server wrote as null when they were absent. It now
// refuses to save until the read succeeds, and sends the three switches only.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/sales_invoice.dart';
import 'package:agency_desktop/ui/sales/sales_workflow_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _StagesApi extends ApiClient {
  _StagesApi({required this.failReads})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  /// How many reads fail before one succeeds.
  int failReads;
  final List<Json> saved = [];

  @override
  Future<SalesWorkflowSettings> salesWorkflowSettings() async {
    if (failReads > 0) {
      failReads -= 1;
      throw const ApiException('The server is not answering.');
    }
    return SalesWorkflowSettings.fromJson(<String, dynamic>{
      'quotation_stage': false,
      'sales_order_stage': false,
      'delivery_note_stage': false,
      'default_branch_id': 'branch-1',
      'default_warehouse_id': 'warehouse-1',
      'is_configured': true,
    });
  }

  @override
  Future<SalesWorkflowSettings> updateSalesWorkflowSettings(
    SalesWorkflowSettings settings,
  ) async {
    saved.add(settings.toJson());
    return settings;
  }
}

PermissionService _manager() {
  final String payload = base64Url
      .encode(utf8.encode(jsonEncode(<String, dynamic>{
        'permissions': ['SALES_VIEW', 'SALES_MANAGE_SETTINGS'],
      })))
      .replaceAll('=', '');
  return PermissionService()..applyAccessToken('header.$payload.signature');
}

Future<void> _open(WidgetTester tester, _StagesApi api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SalesWorkflowSettingsDialog(api: api, permissions: _manager()),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

FilledButton _saveButton(WidgetTester tester) => tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );

void main() {
  testWidgets('a failed read offers no save, and the switches stay shut',
      (tester) async {
    final _StagesApi api = _StagesApi(failReads: 1);
    await _open(tester, api);

    expect(find.textContaining('could not be read'), findsOneWidget);
    expect(_saveButton(tester).onPressed, isNull);
    final SwitchListTile orderSwitch = tester.widget<SwitchListTile>(
      find.widgetWithText(SwitchListTile, 'Sales order'),
    );
    expect(orderSwitch.onChanged, isNull);
    // Nor does it claim the firm has not chosen: nothing was read.
    expect(find.textContaining('has not chosen'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('sales-stages-retry')));
    await tester.pumpAndSettle();

    expect(_saveButton(tester).onPressed, isNotNull);
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(api.saved, hasLength(1));
    expect(api.saved.single['sales_order_stage'], isFalse);
  });

  testWidgets('a save sends the stages and never the defaults it does not show',
      (tester) async {
    final _StagesApi api = _StagesApi(failReads: 0);
    await _open(tester, api);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Quotation'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.saved.single, <String, dynamic>{
      'quotation_stage': true,
      'sales_order_stage': false,
      'delivery_note_stage': false,
    });
  });
}
