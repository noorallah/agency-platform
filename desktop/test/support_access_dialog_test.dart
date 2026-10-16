import 'dart:convert';

import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/core/security/permission_service.dart';
import 'package:agency_desktop/models/entities.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:agency_desktop/ui/identity/support_access_dialog.dart';
import 'package:agency_desktop/ui/resource_management_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The customer's administrator switches the support account off and on
/// (backlog 29s, part b). Offered on the support row alone, to a platform
/// administrator, and never sent without a reason.
PermissionService _permissions({required bool platformAdmin}) {
  const List<String> codes = ['USER_VIEW', 'USER_UPDATE', 'ROLE_VIEW', 'ROLE_ASSIGN'];
  final String payload = base64Url.encode(utf8.encode(jsonEncode({
    'permissions': platformAdmin ? codes : const <String>[],
    'roles': const <String>[],
    'platform_admin': platformAdmin,
    if (platformAdmin) 'platform_admin_scope': 'PLATFORM',
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
  final List<(String, bool, String)> switches = [];

  @override
  Future<PlatformUser> setSupportAccess(
    String id, {
    required bool active,
    required String reason,
  }) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    switches.add((id, active, reason));
    return PlatformUser(
      id: id,
      email: _support.email,
      fullName: _support.fullName,
      isActive: active,
      forcePasswordChange: false,
      expiresAt: '',
      isSupportAccount: true,
    );
  }
}

const PlatformUser _support = PlatformUser(
  id: 'u-support',
  email: 'support@vendor.example',
  fullName: 'Support',
  isActive: true,
  forcePasswordChange: false,
  expiresAt: '',
  department: 'Support',
  isSupportAccount: true,
);

const PlatformUser _ordinary = PlatformUser(
  id: 'u-7',
  email: 'clerk@example.com',
  fullName: 'Clerk',
  isActive: true,
  forcePasswordChange: false,
  expiresAt: '',
  department: 'Support',
);

Future<List<PlatformUser?>> _open(
  WidgetTester tester,
  _Api api, [
  PlatformUser user = _support,
]) async {
  final List<PlatformUser?> answers = [];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async => answers
              .add(await switchSupportAccess(context, api: api, user: user)),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return answers;
}

void main() {
  group('the dialog', () {
    testWidgets('switches it off with the reason typed', (tester) async {
      final _Api api = _Api();
      final List<PlatformUser?> answers = await _open(tester, api);
      expect(find.text('Switch support access off'), findsOneWidget);

      await tester.enterText(find.byType(TextFormField), '  Visit finished ');
      await tester.tap(find.widgetWithText(FilledButton, 'Switch off'));
      await tester.pumpAndSettle();

      expect(api.switches, [('u-support', false, 'Visit finished')]);
      expect(answers.single?.isActive, isFalse);
    });

    testWidgets('an inactive account is offered Switch on', (tester) async {
      final _Api api = _Api();
      await _open(
        tester,
        api,
        const PlatformUser(
          id: 'u-support',
          email: 'support@vendor.example',
          fullName: 'Support',
          isActive: false,
          forcePasswordChange: false,
          expiresAt: '',
          isSupportAccount: true,
        ),
      );

      await tester.enterText(find.byType(TextFormField), 'Ticket 42');
      await tester.tap(find.widgetWithText(FilledButton, 'Switch on'));
      await tester.pumpAndSettle();

      expect(api.switches, [('u-support', true, 'Ticket 42')]);
    });

    testWidgets('no reason, nothing sent', (tester) async {
      final _Api api = _Api();
      final List<PlatformUser?> answers = await _open(tester, api);

      await tester.enterText(find.byType(TextFormField), '   ');
      await tester.tap(find.widgetWithText(FilledButton, 'Switch off'));
      await tester.pumpAndSettle();

      expect(find.text('Say why support access is being changed.'),
          findsOneWidget);
      expect(api.switches, isEmpty);
      expect(answers, isEmpty);
    });

    testWidgets('the server\'s refusal is shown and the dialog stays',
        (tester) async {
      final List<PlatformUser?> answers = await _open(
        tester,
        _Api(refuse: 'The support account cannot switch itself off or on.'),
      );
      await tester.enterText(find.byType(TextFormField), 'Leaving');
      await tester.tap(find.widgetWithText(FilledButton, 'Switch off'));
      await tester.pumpAndSettle();

      expect(find.textContaining('cannot switch itself'), findsOneWidget);
      expect(answers, isEmpty);
    });
  });

  group('where it is offered', () {
    Future<void> footer(
      WidgetTester tester,
      ResourceDefinition<PlatformUser> definition,
      PlatformUser user,
    ) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) =>
                definition.dialogLeadingAction?.call(context, user) ??
                const SizedBox.shrink(),
          ),
        ),
      ));
      await tester.pump();
    }

    testWidgets('on the support row, to a platform administrator',
        (tester) async {
      await footer(
        tester,
        userDefinition(_Api(), _permissions(platformAdmin: true)),
        _support,
      );

      expect(find.text('Support access: on'), findsOneWidget);
      // Its password is the command line's (`--reset-password`), not this
      // footer's.
      expect(find.text('Reset password'), findsNothing);
    });

    testWidgets('not on anybody else\'s row, whatever their department',
        (tester) async {
      await footer(
        tester,
        userDefinition(_Api(), _permissions(platformAdmin: true)),
        _ordinary,
      );

      expect(find.textContaining('Support access'), findsNothing);
      expect(find.text('Reset password'), findsOneWidget);
    });

    testWidgets('not to a firm administrator', (tester) async {
      await footer(
        tester,
        userDefinition(_Api(), _permissions(platformAdmin: false)),
        _support,
      );

      expect(find.textContaining('Support access'), findsNothing);
    });
  });
}
