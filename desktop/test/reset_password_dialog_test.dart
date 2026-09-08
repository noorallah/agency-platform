import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/identity/reset_password_dialog.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A platform administrator sets somebody else's password.
///
/// For the forgotten, the locked-out, and the account handed over after
/// somebody left. Reached from the footer of the person's dialog, beside
/// Roles by firm; not offered to a firm administrator, who would be taking
/// over an account that may also work in a firm they cannot see.
PermissionService _permissions({required bool platformAdmin}) {
  const List<String> codes = ['USER_VIEW', 'USER_UPDATE', 'ROLE_VIEW', 'ROLE_ASSIGN'];
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': platformAdmin ? codes : const <String>[],
    'roles': const <String>[],
    'platform_admin': platformAdmin,
    if (platformAdmin) 'platform_admin_scope': 'ALL_FIRMS',
    'firm_permissions': {'firm-1': codes},
  })));
  return PermissionService()
    ..applyAccessToken('h.$payload.s', activeFirmId: 'firm-1');
}

class _Api extends ApiClient {
  _Api({this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => 'firm-1',
        );

  final String? refuse;
  final List<(String, String, bool)> resets = [];

  @override
  Future<PlatformUser> resetUserPassword(
    String id,
    String newPassword, {
    bool forceChange = true,
  }) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    resets.add((id, newPassword, forceChange));
    return _user;
  }
}

const PlatformUser _user = PlatformUser(
  id: 'u-7',
  email: 'left@example.com',
  fullName: 'Someone Who Left',
  isActive: true,
  forcePasswordChange: false,
  expiresAt: '',
);

Future<List<bool>> _open(WidgetTester tester, _Api api) async {
  final List<bool> answers = [];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async => answers
              .add(await resetUserPassword(context, api: api, user: _user)),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return answers;
}

Future<void> _fill(WidgetTester tester, String next, [String? confirm]) async {
  final Finder fields = find.byType(TextFormField);
  await tester.enterText(fields.at(0), next);
  await tester.enterText(fields.at(1), confirm ?? next);
}

void main() {
  group('the dialog', () {
    testWidgets('names the person and sets a forced change by default',
        (tester) async {
      final _Api api = _Api();
      final List<bool> answers = await _open(tester, api);
      expect(find.textContaining('Someone Who Left'), findsOneWidget);

      await _fill(tester, 'Temp-Passw0rd!!');
      await tester.tap(find.widgetWithText(FilledButton, 'Set password'));
      await tester.pumpAndSettle();

      expect(api.resets, [('u-7', 'Temp-Passw0rd!!', true)]);
      expect(answers, [true]);
    });

    testWidgets('a handover keeps the password: the switch off', (tester) async {
      final _Api api = _Api();
      await _open(tester, api);
      await _fill(tester, 'Temp-Passw0rd!!');
      await tester.tap(find.byType(Checkbox));
      await tester.tap(find.widgetWithText(FilledButton, 'Set password'));
      await tester.pumpAndSettle();

      expect(api.resets.single.$3, isFalse);
    });

    testWidgets('a weak password is refused before the server sees it',
        (tester) async {
      final _Api api = _Api();
      await _open(tester, api);
      await _fill(tester, 'weak');
      await tester.tap(find.widgetWithText(FilledButton, 'Set password'));
      await tester.pumpAndSettle();

      expect(find.text('Use at least 12 characters.'), findsOneWidget);
      expect(api.resets, isEmpty);
    });

    testWidgets('the server\'s refusal is shown and the dialog stays',
        (tester) async {
      // The caller's own account, which the server sends to My profile.
      final List<bool> answers = await _open(
        tester,
        _Api(refuse: 'Change your own password from My profile.'),
      );
      await _fill(tester, 'Temp-Passw0rd!!');
      await tester.tap(find.widgetWithText(FilledButton, 'Set password'));
      await tester.pumpAndSettle();

      expect(find.textContaining('My profile'), findsOneWidget);
      expect(answers, isEmpty);
    });
  });

  group('where it is offered', () {
    Future<void> footer(
      WidgetTester tester,
      ResourceDefinition<PlatformUser> definition,
    ) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) =>
                definition.dialogLeadingAction?.call(context, _user) ??
                const SizedBox.shrink(),
          ),
        ),
      ));
      await tester.pump();
    }

    testWidgets('a platform administrator gets it beside Roles by firm',
        (tester) async {
      await footer(tester, userDefinition(_Api(), _permissions(platformAdmin: true)));

      expect(find.text('Roles by firm'), findsOneWidget);
      expect(find.text('Reset password'), findsOneWidget);
    });

    testWidgets('a firm administrator does not', (tester) async {
      await footer(tester, userDefinition(_Api(), _permissions(platformAdmin: false)));

      expect(find.text('Roles by firm'), findsOneWidget);
      expect(find.text('Reset password'), findsNothing);
    });
  });
}
