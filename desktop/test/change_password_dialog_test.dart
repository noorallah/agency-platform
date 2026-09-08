import 'package:agency_desktop/core/api/api_client.dart';
import 'package:agency_desktop/ui/identity/change_password_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A person changes their own password from My profile.
///
/// The route existed for a year and was reachable only from the screen a
/// *forced* change lands on, so nobody could change a password they simply
/// wanted changed. The dialog names the server's policy beside the box, sends
/// the change, and answers true so the caller can end the session the server
/// has already revoked.
class _Api extends ApiClient {
  _Api({this.refuse})
      : super(
          baseUrl: 'http://localhost:8000',
          accessToken: () => null,
          refreshAccessToken: () async => false,
          activeFirmId: () => null,
        );

  final String? refuse;
  final List<(String, String)> sent = [];

  @override
  Future<void> changePassword(String currentPassword, String newPassword) async {
    if (refuse != null) throw ApiException(refuse!, statusCode: 422);
    sent.add((currentPassword, newPassword));
  }
}

Future<List<bool>> _open(WidgetTester tester, _Api api) async {
  final List<bool> answers = [];
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => TextButton(
          onPressed: () async =>
              answers.add(await changeOwnPassword(context, api: api)),
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return answers;
}

Future<void> _fill(
  WidgetTester tester, {
  String current = 'Old-Passw0rd!!',
  String next = 'New-Passw0rd!!',
  String? confirm,
}) async {
  final Finder fields = find.byType(TextFormField);
  await tester.enterText(fields.at(0), current);
  await tester.enterText(fields.at(1), next);
  await tester.enterText(fields.at(2), confirm ?? next);
}

void main() {
  test('the policy is the server\'s, rule by rule', () {
    expect(_ChangePasswordDialogStatePolicy.policy('Short1!'),
        'Use at least 12 characters.');
    expect(_ChangePasswordDialogStatePolicy.policy('alllowercase1!'),
        'Include an uppercase letter.');
    expect(_ChangePasswordDialogStatePolicy.policy('ALLUPPERCASE1!'),
        'Include a lowercase letter.');
    expect(_ChangePasswordDialogStatePolicy.policy('NoDigitsHere!!'),
        'Include a digit.');
    expect(_ChangePasswordDialogStatePolicy.policy('NoSymbolsHere1'),
        'Include a symbol.');
    expect(_ChangePasswordDialogStatePolicy.policy('Str0ng-Passw0rd!'), isNull);
  });

  testWidgets('a weak password is refused before the server sees it',
      (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fill(tester, next: 'short', confirm: 'short');
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();

    expect(find.text('Use at least 12 characters.'), findsOneWidget);
    expect(api.sent, isEmpty);
  });

  testWidgets('a mismatched confirmation is refused', (tester) async {
    final _Api api = _Api();
    await _open(tester, api);
    await _fill(tester, confirm: 'New-Passw0rd!?');
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();

    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(api.sent, isEmpty);
  });

  testWidgets('a good change goes to the server and answers true',
      (tester) async {
    final _Api api = _Api();
    final List<bool> answers = await _open(tester, api);
    await _fill(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();

    expect(api.sent, [('Old-Passw0rd!!', 'New-Passw0rd!!')]);
    expect(answers, [true]);
  });

  testWidgets('the server\'s refusal is shown where it can be acted on',
      (tester) async {
    // A wrong current password, or one of the last five reused: only the
    // server can say, and it says it here rather than as a generic failure.
    final List<bool> answers =
        await _open(tester, _Api(refuse: 'A recent password cannot be reused.'));
    await _fill(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
    await tester.pumpAndSettle();

    expect(find.text('A recent password cannot be reused.'), findsOneWidget);
    expect(answers, isEmpty, reason: 'still open, for another try');
  });

  testWidgets('a dismissal changes nothing and answers false', (tester) async {
    final _Api api = _Api();
    final List<bool> answers = await _open(tester, api);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(api.sent, isEmpty);
    expect(answers, [false]);
  });
}

/// The policy is a static on the state class, reached through this alias
/// so the test reads as a statement about the rule rather than the widget.
abstract final class _ChangePasswordDialogStatePolicy {
  static String? policy(String? value) => ChangePasswordPolicy.check(value);
}
