import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/customers/credit_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The credit policy decides whether a firm's trading stops, so the form that
/// edits it has two jobs beyond collecting three values: it must show a firm
/// that has never chosen a policy that it is looking at a default, and it must
/// stay read-only for the roles the limit exists to constrain.

String _accessToken(Map<String, dynamic> claims) {
  final String payload =
      base64Url.encode(utf8.encode(jsonEncode(claims))).replaceAll('=', '');
  return 'header.$payload.signature';
}

PermissionService _withPermissions(List<String> permissions) {
  final PermissionService service = PermissionService();
  service.applyAccessToken(_accessToken({
    'roles': <String>['user'],
    'permissions': permissions,
  }));
  return service;
}

class _SettingsApi extends ApiClient {
  _SettingsApi({this.isConfigured = true})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final bool isConfigured;
  final List<Json> writes = <Json>[];

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
    if (method == 'PUT') {
      writes.add(Map<String, dynamic>.from(body ?? const <String, dynamic>{}));
      return <String, dynamic>{'success': true, 'data': body};
    }
    return <String, dynamic>{
      'success': true,
      'data': <String, dynamic>{
        'enforcement': 'WARN',
        'warn_at_percent': '80.00',
        'block_at_percent': '100.00',
        'is_configured': isConfigured,
      },
    };
  }
}

Future<void> _open(
  WidgetTester tester,
  _SettingsApi api,
  PermissionService permissions,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: CreditSettingsDialog(api: api, permissions: permissions),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an unconfigured firm is told it is looking at the default',
      (tester) async {
    await _open(
      tester,
      _SettingsApi(isConfigured: false),
      _withPermissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
    );

    expect(find.textContaining('has not set a policy'), findsOneWidget);
  });

  testWidgets('a firm that chose its policy gets no default notice',
      (tester) async {
    await _open(
      tester,
      _SettingsApi(),
      _withPermissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
    );

    expect(find.textContaining('has not set a policy'), findsNothing);
  });

  testWidgets('stored scale is not shown back as 80.00', (tester) async {
    await _open(
      tester,
      _SettingsApi(),
      _withPermissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
    );

    expect(find.widgetWithText(TextField, '80'), findsOneWidget);
    expect(find.widgetWithText(TextField, '80.00'), findsNothing);
  });

  testWidgets('a viewer sees the policy but cannot change it', (tester) async {
    final _SettingsApi api = _SettingsApi();

    await _open(tester, api, _withPermissions(['CUSTOMER_VIEW']));

    expect(find.textContaining('manage customer settings'), findsOneWidget);
    final FilledButton save = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Save'),
    );
    expect(
      save.onPressed,
      isNull,
      reason: 'the role a credit limit constrains must not switch it off',
    );
    expect(api.writes, isEmpty);
  });

  testWidgets('a warning threshold above the block one is refused locally',
      (tester) async {
    final _SettingsApi api = _SettingsApi();
    await _open(
      tester,
      api,
      _withPermissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
    );

    await tester.enterText(find.widgetWithText(TextField, '80'), '120');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(find.textContaining('could never fire'), findsOneWidget);
    expect(
      api.writes,
      isEmpty,
      reason: 'the server rejects this too; catching it here keeps the '
          'numbers on screen',
    );
  });

  testWidgets('a valid policy is sent in the shape the server expects',
      (tester) async {
    final _SettingsApi api = _SettingsApi();
    await _open(
      tester,
      api,
      _withPermissions(['CUSTOMER_VIEW', 'CUSTOMER_MANAGE_SETTINGS']),
    );

    await tester.tap(find.text('Warn'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Warn, then block').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, '80'), '70');
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(api.writes, hasLength(1));
    expect(api.writes.single['enforcement'], 'BLOCK');
    expect(api.writes.single['warn_at_percent'], '70');
    expect(api.writes.single['block_at_percent'], '100');
  });
}
