import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/commission.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/models/firm_member.dart';
import 'package:agency_desktop/ui/commission/sales_target_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Setting a target for one person.
///
/// The dialog sent no `salesman_id`, so every target made on the desktop was
/// "Whole firm" and a salesperson's own number could be set only over HTTP
/// (BL-31.15).
PermissionService _permissions() {
  final String payload = base64Url.encode(
    utf8.encode(jsonEncode({
      'permissions': ['SALES_TARGET_VIEW', 'SALES_TARGET_MANAGE'],
    })),
  );
  return PermissionService()..applyAccessToken('h.$payload.s');
}

class _TargetApi extends ApiClient {
  _TargetApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> created = [];

  @override
  Future<PagedResult<SalesTargetRecord>> salesTargets({
    int page = 1,
    int pageSize = 50,
  }) async =>
      const PagedResult<SalesTargetRecord>(items: [], total: 0);

  @override
  Future<List<FirmMember>> firmMembers() async => const [
        FirmMember(userId: 'user-asha', fullName: 'Asha Rao'),
        FirmMember(userId: 'user-ravi', fullName: 'Ravi Kumar'),
      ];

  @override
  Future<SalesTargetRecord> createSalesTarget(Json body) async {
    created.add(body);
    return const SalesTargetRecord(
      id: 't-1',
      periodStart: '2026-09-01',
      periodEnd: '2026-09-30',
      targetAmount: '1000',
    );
  }
}

Future<void> _newTarget(WidgetTester tester, _TargetApi api,
    {required String salesperson}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: SalesTargetPage(
        api: api,
        permissions: _permissions(),
        hasActiveFirm: true,
      ),
    ),
  ));
  await tester.pumpAndSettle();

  await tester.tap(find.widgetWithText(FilledButton, 'New target'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'From'), '2026-09-01');
  await tester.enterText(find.widgetWithText(TextField, 'To'), '2026-09-30');
  await tester.enterText(
      find.widgetWithText(TextField, 'Target amount'), '1000');

  await tester.tap(find.byKey(const ValueKey('sales-target-salesperson')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(salesperson).last);
  await tester.pumpAndSettle();

  await tester.tap(find.widgetWithText(FilledButton, 'Save'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('choosing a person sends their id', (tester) async {
    final _TargetApi api = _TargetApi();
    await _newTarget(tester, api, salesperson: 'Ravi Kumar');

    expect(api.created, hasLength(1));
    expect(api.created.single['salesman_id'], 'user-ravi');
  });

  testWidgets('choosing "Whole firm" sends null', (tester) async {
    final _TargetApi api = _TargetApi();
    await _newTarget(tester, api, salesperson: 'Whole firm');

    expect(api.created, hasLength(1));
    expect(api.created.single.containsKey('salesman_id'), isTrue,
        reason: 'on an edit, an absent key would leave the person in place');
    expect(api.created.single['salesman_id'], isNull);
  });
}
