// A refused save leaves the record as it was, and says so where it can be seen.
//
// Raised from manual testing (plan item 6.5): editing the WHOLESALE business
// profile and ticking an unimplemented feature was refused by the server --
// the features write answered 422 -- yet the profile read as saved. The
// dialog writes a record in two requests, the record's own fields and then
// its assignments, and the first had already gone through when the second
// was refused. The refusal itself sat in the summary at the top of a form
// whose features picker is at the foot, out of view.
//
// On an edit the assignments go first now, so a refusal writes nothing, and
// the form scrolls back to the summary when it shows one.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const String _refusal =
    'These features are not implemented yet and cannot be enabled: IMEI.';

class _Api extends ApiClient {
  _Api()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  int updates = 0;
  int creates = 0;

  @override
  Future<Json> update(
    String resource,
    String id,
    Json body, {
    bool partial = false,
    int? expectedVersion,
  }) async {
    updates++;
    return <String, dynamic>{'data': <String, dynamic>{'id': id, ...body}};
  }

  @override
  Future<Json> create(String resource, Json body) async {
    creates++;
    return <String, dynamic>{
      'data': <String, dynamic>{'id': 'thing-new', ...body},
    };
  }
}

/// A resource whose assignments the server refuses, the way a business
/// profile's features are refused when one of them is roadmap.
ResourceDefinition<Json> _definition(_Api api) => ResourceDefinition<Json>(
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
          PagedResult<Json>(
            items: <Json>[
              <String, dynamic>{'id': 'thing-1', 'code': 'T1', 'name': 'One'},
            ],
            total: 1,
          ),
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
      saveAssignments: (id, values) async =>
          throw const ApiException(_refusal, statusCode: 422),
    );

Future<void> _pump(WidgetTester tester, _Api api) async {
  tester.view.physicalSize = const Size(1600, 1200);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: ResourceManagementPage<Json>(
          api: api,
          definition: _definition(api),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an edit whose assignments are refused writes nothing',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    // The row's own Edit action, which opens the editor without a selection.
    await tester.tap(find.byTooltip('Edit').last);
    await tester.pumpAndSettle();
    expect(find.text('Save & Close'), findsOneWidget, reason: 'editor open');

    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Two');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.updates, 0,
        reason: 'the record must not be written when its assignments are refused');
    expect(find.text(_refusal), findsOneWidget,
        reason: 'the refusal is shown, and the dialog stays open');
    expect(find.text('Things saved.'), findsNothing);
  });

  testWidgets('a create whose assignments are refused is not created twice',
      (tester) async {
    final _Api api = _Api();
    await _pump(tester, api);

    await tester.tap(find.byTooltip('New'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Code'), 'T2');
    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Two');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();
    expect(api.creates, 1);
    expect(find.text(_refusal), findsOneWidget);

    // The record exists now; a second Save must attach to it, not create
    // another.
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();
    expect(api.creates, 1);
  });
}
