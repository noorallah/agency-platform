import 'package:flutter/material.dart';

import 'core/auth/session_controller.dart';
import 'ui/auth_screens.dart';
import 'ui/desktop_shell.dart';

const String _configuredApiUrl =
    String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000');

class AgencyApp extends StatefulWidget {
  const AgencyApp({super.key, this.session});
  final SessionController? session;

  @override
  State<AgencyApp> createState() => _AgencyAppState();
}

class _AgencyAppState extends State<AgencyApp> {
  late final SessionController _session =
      widget.session ?? SessionController(baseUrl: _configuredApiUrl);

  @override
  void initState() {
    super.initState();
    _session.restore();
  }

  @override
  void dispose() {
    _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Agency Platform',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff155eef)),
          useMaterial3: true,
          inputDecorationTheme: const InputDecorationTheme(
            border: OutlineInputBorder(),
          ),
        ),
        home: AnimatedBuilder(
          animation: _session,
          builder: (context, _) {
            switch (_session.status) {
              case SessionStatus.restoring:
              case SessionStatus.authenticating:
                return const _StatusPage(
                  message: 'Restoring your secure session…',
                  loading: true,
                );
              case SessionStatus.signedOut:
              case SessionStatus.error:
                return LoginScreen(
                  session: _session,
                  error: _session.status == SessionStatus.error
                      ? _session.error
                      : null,
                  notice: _session.notice,
                );
              case SessionStatus.requiresPasswordChange:
                return ChangeInitialPasswordScreen(session: _session);
              case SessionStatus.authenticated:
                return DesktopShell(session: _session);
            }
          },
        ),
      );
}

class _StatusPage extends StatelessWidget {
  const _StatusPage({required this.message, required this.loading});
  final String message;
  final bool loading;
  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (loading) const CircularProgressIndicator(),
              const SizedBox(height: 16),
              Text(message),
            ],
          ),
        ),
      );
}
