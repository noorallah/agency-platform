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
}
