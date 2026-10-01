// The Reorder planning dialog (backlog 69 row 12): load shows the firm's
// values, switching to From sales and saving sends all five fields, a value
// out of range blocks the save, and a failed read offers no save.

import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/purchases/reorder_planning_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _PlanningApi extends ApiClient {
  _PlanningApi({this.failReads = 0})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int failReads;
  final List<Json> saved = <Json>[];

  @override
  Future<Json> reorderPlanning() async {
    if (failReads > 0) {
      failReads -= 1;
      throw const ApiException('The server is not answering.');
    }
    return <String, dynamic>{
      'basis': 'LEVELS',
      'sales_window_days': 45,
      'lead_time_days': 5,
      'safety_days': 2,
      'cover_days': 30,
      'is_configured': true,
    };
  }

  @override
  Future<Json> updateReorderPlanning(Json settings) async {
    saved.add(settings);
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
  _PlanningApi api, {
  List<String> codes = const ['PURCHASE_VIEW', 'PURCHASE_MANAGE_SETTINGS'],
}) async {
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
              builder: (_) => ReorderPlanningDialog(
                api: api,
                permissions: _holder(codes),
              ),
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

FilledButton _save(WidgetTester tester) => tester.widget<FilledButton>(
      find.byKey(const ValueKey('reorder-planning-save')),
    );

void main() {
  testWidgets('switching to From sales and saving sends all five fields',
      (tester) async {
    final _PlanningApi api = _PlanningApi();
    await _open(tester, api);

    // Typed levels: the day boxes are not offered.
    expect(find.byKey(const ValueKey('reorder-window')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('reorder-basis-sales')));
    await tester.pumpAndSettle();
    final TextField window =
        tester.widget(find.byKey(const ValueKey('reorder-window')));
    expect(window.controller!.text, '45');

    await tester.enterText(find.byKey(const ValueKey('reorder-cover')), '60');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('reorder-planning-save')));
    await tester.pumpAndSettle();

    expect(api.saved.single, <String, dynamic>{
      'basis': 'SALES',
      'sales_window_days': 45,
      'lead_time_days': 5,
      'safety_days': 2,
      'cover_days': 60,
    });
    expect(find.byType(ReorderPlanningDialog), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a value outside the server range blocks the save',
      (tester) async {
    final _PlanningApi api = _PlanningApi();
    await _open(tester, api);
    await tester.tap(find.byKey(const ValueKey('reorder-basis-sales')));
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const ValueKey('reorder-window')), '3');
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('reorder-problem')), findsOneWidget);
    expect(_save(tester).onPressed, isNull);

    await tester.enterText(find.byKey(const ValueKey('reorder-window')), '14');
    await tester.enterText(find.byKey(const ValueKey('reorder-cover')), '0');
    await tester.pumpAndSettle();
    expect(_save(tester).onPressed, isNull);
  });

  testWidgets('a failed read offers no save until a read succeeds',
      (tester) async {
    final _PlanningApi api = _PlanningApi(failReads: 1);
    await _open(tester, api);

    expect(find.textContaining('could not be read'), findsOneWidget);
    expect(_save(tester).onPressed, isNull);

    await tester.tap(find.byKey(const ValueKey('reorder-planning-retry')));
    await tester.pumpAndSettle();
    expect(_save(tester).onPressed, isNotNull);
  });

  testWidgets('without the settings permission nothing can be changed',
      (tester) async {
    final _PlanningApi api = _PlanningApi();
    await _open(tester, api, codes: const ['PURCHASE_VIEW']);

    expect(_save(tester).onPressed, isNull);
    expect(find.textContaining('manage purchase settings'), findsOneWidget);
  });
}
