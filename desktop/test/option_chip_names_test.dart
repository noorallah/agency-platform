import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/finance/finance_workspace.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A single-choice picker names what each chip is, not only its code.
///
/// The Chart of Accounts form offered an Account Group as five chips reading
/// CA, CL, EQ, EXP and REV. Picking "Direct Expenses" meant knowing it was EXP
/// (manual plan item 13.1, 2026-09-14).
class _GroupsApi extends ApiClient {
  _GroupsApi()
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

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
    return {
      'data': [
        {'id': 'g-exp', 'code': 'EXP', 'name': 'Direct Expenses'},
        {'id': 'g-same', 'code': 'EQ', 'name': 'EQ'},
        {'id': 'g-bare', 'code': 'CA'},
      ],
      'pagination': {'total_records': 3},
    };
  }
}

PermissionService _permissions() {
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': ['ACCOUNT_VIEW', 'ACCOUNT_MANAGE']
  })));
  return PermissionService()..applyAccessToken('h.$payload.s');
}

void main() {
  test('an option carries its name when it differs from the code', () async {
    final List<AssignmentOption> options =
        await _GroupsApi().options('finance/account-groups');

    expect(options.map((option) => option.label), ['EXP', 'EQ', 'CA']);
    expect(options.map((option) => option.detail),
        ['Direct Expenses', null, null]);
  });

  testWidgets('the account group chips read code and name', (tester) async {
    final _GroupsApi api = _GroupsApi();
    await tester.binding.setSurfaceSize(const Size(1366, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final definition = ledgerAccountDefinition(api, _permissions());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CrudWorkspaceDialog(
          title: 'New account',
          fields: definition.fields,
          values: const <String, dynamic>{},
          api: api,
          mode: CrudDialogMode.create,
          onSave: (_) async {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('EXP · Direct Expenses'), findsOneWidget);
    expect(find.text('EQ'), findsOneWidget, reason: 'a name equal to the code');
    expect(find.text('CA'), findsOneWidget, reason: 'no name to add');
  });

  testWidgets('a chip field shows the helper text that says what it does',
      (tester) async {
    // "Ignored when a job template is named above." was written under the
    // Roles chips and never drawn (manual plan item 17.4c).
    final _GroupsApi api = _GroupsApi();
    await tester.binding.setSurfaceSize(const Size(1366, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CrudWorkspaceDialog(
          title: 'New user',
          fields: const [
            FieldSpec(
              key: 'role_ids',
              label: 'Roles in this firm',
              helperText: 'Held in your firm only. '
                  'Ignored when a job template is named above.',
              optionsResource: 'roles',
            ),
          ],
          values: const <String, dynamic>{},
          api: api,
          mode: CrudDialogMode.create,
          onSave: (_) async {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(
      find.text(
          'Held in your firm only. Ignored when a job template is named above.'),
      findsOneWidget,
    );
  });

  testWidgets('roles lock while a job is chosen, and unlock when it is cleared',
      (tester) async {
    // A named job decides the roles; the chips stayed clickable beside it
    // (manual plan item 17.4c).
    final _GroupsApi api = _GroupsApi();
    await tester.binding.setSurfaceSize(const Size(1366, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CrudWorkspaceDialog(
          title: 'New user',
          fields: const [
            FieldSpec(
              key: 'template_id',
              label: 'Job template',
              optionsResource: 'user-templates',
              singleSelection: true,
            ),
            FieldSpec(
              key: 'role_ids',
              label: 'Roles in this firm',
              optionsResource: 'roles',
              lockedWhileSet: 'template_id',
            ),
          ],
          values: const <String, dynamic>{},
          api: api,
          mode: CrudDialogMode.create,
          onSave: (_) async {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // The fake serves the same three options to both fields: the job chips are
    // the single-selection ones and carry the name, the role chips do not.
    FilterChip roleChip() => tester.widget<FilterChip>(
          find.widgetWithText(FilterChip, 'CA').last,
        );
    expect(roleChip().onSelected, isNotNull, reason: 'no job chosen yet');

    await tester.tap(find.widgetWithText(FilterChip, 'EXP · Direct Expenses'));
    await tester.pumpAndSettle();
    expect(roleChip().onSelected, isNull, reason: 'the job decides the roles');

    await tester.tap(find.widgetWithText(FilterChip, 'EXP · Direct Expenses'));
    await tester.pumpAndSettle();
    expect(roleChip().onSelected, isNotNull, reason: 'job cleared, roles back');
  });

  testWidgets('editing an account offers no group, type or code to change',
      (tester) async {
    // readOnlyWhenEditing reached the text box alone, so the edit form let a
    // person pick another group and type, said it saved, and sent neither
    // (manual plan item 13.1).
    final _GroupsApi api = _GroupsApi();
    await tester.binding.setSurfaceSize(const Size(1366, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final definition = ledgerAccountDefinition(api, _permissions());
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: CrudWorkspaceDialog(
          title: 'Edit account',
          fields: definition.fields,
          values: const <String, dynamic>{
            'account_group_id': 'g-exp',
            'code': '9999',
            'name': 'Manual test account',
            'account_type': 'EXPENSE',
            'description': '',
            'requires_cost_center': false,
            'requires_profit_center': false,
            'is_active': true,
          },
          api: api,
          mode: CrudDialogMode.edit,
          onSave: (_) async {},
        ),
      ),
    ));
    await tester.pumpAndSettle();

    for (final FilterChip chip
        in tester.widgetList<FilterChip>(find.byType(FilterChip))) {
      expect(chip.onSelected, isNull, reason: 'the group is fixed');
    }
    final DropdownButton<String> type = tester.widget<DropdownButton<String>>(
      find.byType(DropdownButton<String>),
    );
    expect(type.onChanged, isNull, reason: 'the type is fixed');
    final TextField code = tester.widget<TextField>(
      find.widgetWithText(TextField, 'Code'),
    );
    expect(code.readOnly, isTrue, reason: 'the code is fixed');
    final TextField name = tester.widget<TextField>(
      find.widgetWithText(TextField, 'Name'),
    );
    expect(name.readOnly, isFalse, reason: 'the name can still be changed');
  });
}
