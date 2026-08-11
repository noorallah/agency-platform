// A rejected field must not lock the dialog.
//
// The server rejects a profile photo URL over 1000 characters, which is right.
// What was wrong is what came next: the field validators return
// `_fieldErrors[key]` regardless of what the box now holds, and `_save`
// cleared that map *after* its `validate()` guard. So the second Save kept
// failing on the first attempt's message, and the line that would have
// cleared it was never reached. Correcting the URL changed nothing; the only
// way out was to cancel and lose the form.

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Refuses an over-long photo URL the way the backend does, then accepts.
class _PickyApi extends ApiClient {
  _PickyApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final List<Json> accepted = <Json>[];

  @override
  Future<Json> request(
    String method,
    String path, {
    Json? body,
    Map<String, String>? query,
    bool authenticated = true,
    bool retrying = false,
  }) async =>
      <String, dynamic>{'data': <String, dynamic>{}};

  Future<void> save(Map<String, dynamic> values) async {
    final String url = (values['profile_photo_url'] ?? '').toString();
    if (url.length > 1000) {
      // The shape the backend actually sends: a list of {field, message},
      // where `field` carries the `body.` prefix from the request location.
      // See _validation_error_handler in backend/app/core/exceptions/handlers.py.
      throw const ApiException(
        'Validation failed.',
        statusCode: 422,
        details: [
          {
            'field': 'body.profile_photo_url',
            'message': 'String should have at most 1000 characters',
          },
        ],
      );
    }
    accepted.add(Json.from(values));
  }
}

void main() {
  testWidgets('a corrected field can be submitted after the server refused it',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final _PickyApi api = _PickyApi();

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => CrudWorkspaceDialog(
            title: 'User',
            fields: const [
              FieldSpec(key: 'full_name', label: 'Full name', required: true),
              FieldSpec(key: 'profile_photo_url', label: 'Profile photo URL'),
            ],
            values: const {
              'full_name': 'Probe Person',
              'profile_photo_url': '',
            },
            api: api,
            mode: CrudDialogMode.create,
            onSave: api.save,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    Finder box(String label) => find.widgetWithText(TextFormField, label);

    // Too long: the server refuses, and says which field.
    await tester.enterText(box('Profile photo URL'), 'https://${'x' * 1200}');
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.accepted, isEmpty);
    expect(find.textContaining('at most 1000 characters'), findsWidgets,
        reason: 'the refusal has to be shown against the field');

    // Correct it, and save again.
    await tester.enterText(
      box('Profile photo URL'),
      'https://photos.example.test/p.png',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(api.accepted, hasLength(1),
        reason: 'the corrected value never reached the server');
    expect(
      api.accepted.single['profile_photo_url'],
      'https://photos.example.test/p.png',
    );
  });

  testWidgets('a validation message in a dialog can be selected and copied',
      (tester) async {
    // The app-level SelectionArea wraps `home`; a dialog is a separate route,
    // so none of its text was selectable. The message naming a limit is
    // exactly what a user wants to quote back, and it is a plain Text.
    await tester.binding.setSurfaceSize(const Size(1200, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final _PickyApi api = _PickyApi();

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => CrudWorkspaceDialog(
            title: 'User',
            fields: const [
              FieldSpec(key: 'full_name', label: 'Full name', required: true),
              FieldSpec(key: 'profile_photo_url', label: 'Profile photo URL'),
            ],
            values: const {
              'full_name': 'Probe Person',
              'profile_photo_url': '',
            },
            api: api,
            mode: CrudDialogMode.create,
            onSave: api.save,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Profile photo URL'),
      'https://${'x' * 1200}',
    );
    await tester.tap(find.text('Save & Close'));
    await tester.pumpAndSettle();

    expect(
      find.ancestor(
        of: find.textContaining('at most 1000 characters').first,
        matching: find.byType(SelectionArea),
      ),
      findsWidgets,
      reason: 'the message sits outside any selectable region',
    );
  });
}
