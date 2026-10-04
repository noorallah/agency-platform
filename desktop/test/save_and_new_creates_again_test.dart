// Save & New makes a new record every time, and nothing reaches the last one.
//
// Found 2026-10-04 on the purchasing walkthrough (D-UI-5): a platform
// administrator created `admin@qa01.test`, pressed Save & New and "created"
// five more users. The dialog's create checkpoint still held the first
// account's id, so each later save skipped the create and wrote the new
// form's firms and job template onto the first account. Five people never
// existed, the administrator ended up Read Only, and every save said "saved".

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> created = [];

  @override
  Future<Json> create(String resource, Json body) async {
    created.add(body);
    return <String, dynamic>{
      'data': <String, dynamic>{'id': 'thing-${created.length}', ...body},
    };
  }
}

ResourceDefinition<Json> _definition(List<String> assignedTo) =>
    ResourceDefinition<Json>(
      title: 'Things',
      resource: 'things',
      headers: const ['Code', 'Name'],
      cells: (item) => [stringValue(item['code']), stringValue(item['name'])],
      id: (item) => stringValue(item['id']),
      load: ({
        int page = 1,
        String search = '',
        String sortBy = 'created_at',
        bool descending = true,
      }) async =>
          const PagedResult<Json>(items: <Json>[], total: 0),
      fields: const [
        FieldSpec(key: 'code', label: 'Code', required: true),
        FieldSpec(key: 'name', label: 'Name', required: true),
      ],
      initialValues: (item) => <String, dynamic>{
        'code': stringValue(item?['code']),
        'name': stringValue(item?['name']),
      },
      payload: (values, _) => <String, dynamic>{
        'code': values['code'],
        'name': values['name'],
      },
      saveAssignments: (id, values) async => assignedTo.add(id),
    );

Future<void> _type(WidgetTester tester, String code, String name) async {
  await tester.enterText(find.widgetWithText(TextFormField, 'Code'), code);
  await tester.enterText(find.widgetWithText(TextFormField, 'Name'), name);
}

void main() {
  testWidgets('every Save & New creates its own record', (tester) async {
    tester.view.physicalSize = const Size(1600, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final _Api api = _Api();
    final List<String> assignedTo = [];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ResourceManagementPage<Json>(
            api: api,
            definition: _definition(assignedTo),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('New'));
    await tester.pumpAndSettle();
    await _type(tester, 'T1', 'One');
    await tester.tap(find.text('Save & New'));
    await tester.pumpAndSettle();

    await _type(tester, 'T2', 'Two');
    await tester.tap(find.text('Save & New'));
    await tester.pumpAndSettle();

    await _type(tester, 'T3', 'Three');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.created.map((body) => body['code']), ['T1', 'T2', 'T3'],
        reason: 'each save after Save & New is a new record');
    expect(assignedTo, ['thing-1', 'thing-2', 'thing-3'],
        reason: "each form's assignments go to its own record, never the first");
  });
}
