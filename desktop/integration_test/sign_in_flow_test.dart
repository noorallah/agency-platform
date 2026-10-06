import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'harness.dart';

/// The proof that the harness works: the real app, the real server, a real
/// sign-in. Run from `desktop/` with the backend up:
///
///     flutter test integration_test/sign_in_flow_test.dart -d windows \
///         --dart-define=API_BASE_URL=http://127.0.0.1:8000
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a person signs in and reaches the phase 2 frame',
      (WidgetTester tester) async {
    await startAndSignIn(tester);
    // ignore: avoid_print
    print('SIGNED IN. On screen: ${textOnScreen(tester).take(60).join(' | ')}');
  });
}
