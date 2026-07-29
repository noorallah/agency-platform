import 'package:agency_desktop/app.dart';
import 'package:agency_desktop/core/auth/refresh_token_store.dart';
import 'package:agency_desktop/core/auth/session_controller.dart';
import 'package:agency_desktop/ui/desktop_shell.dart';
import 'package:flutter_test/flutter_test.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  String? token;
  @override
  Future<void> clear() async => token = null;
  @override
  Future<String?> read() async => token;
  @override
  Future<void> write(String value) async => token = value;
}

void main() {
  test('core navigation labels stay mapped to administration sections', () {
    expect(AppSection.firms.label, 'Firm Management');
    expect(AppSection.permissions.label, 'Permission Management');
  });

  testWidgets('restored signed-out session opens login navigation', (tester) async {
    final SessionController session = SessionController(
      baseUrl: 'http://localhost:8000',
      tokenStore: _MemoryTokenStore(),
    );

    await tester.pumpWidget(AgencyApp(session: session));
    await tester.pump();

    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Agency Platform'), findsOneWidget);
  });
}
