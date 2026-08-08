import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/branding/branding_config.dart';
import 'core/preferences/desktop_preferences_service.dart';
import 'core/preferences/desktop_window_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('Flutter error: ${details.exception}\n${details.stack}');
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('Platform error: $error\n$stack');
    return true;
  };

  try {
    final DesktopPreferencesService preferences = DesktopPreferencesService();
    await preferences.load();
    final BrandingConfig branding = await BrandingConfig.load();
    try {
      await DesktopWindowController(preferences).initialize(branding);
    } catch (error, stack) {
      debugPrint('Window initialization failed: $error\n$stack');
    }
    runApp(AgencyApp(preferences: preferences, branding: branding));
  } catch (error, stack) {
    debugPrint('Unhandled startup error: $error\n$stack');
    runApp(_StartupErrorApp(error: error, stackTrace: stack));
  }
}

class _StartupErrorApp extends StatelessWidget {
  const _StartupErrorApp({required this.error, required this.stackTrace});

  final Object error;
  final StackTrace stackTrace;

  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: const Color(0xff111827),
          body: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 640),
                child: Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.95),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.error_outline, size: 48, color: Color(0xffdc2626)),
                      const SizedBox(height: 16),
                      const Text(
                        'The desktop app could not start cleanly.',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Please check the startup logs and confirm the backend URL.',
                      ),
                      const SizedBox(height: 16),
                      Text(
                        error.toString(),
                        style: const TextStyle(fontSize: 12, fontFamily: 'monospace'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}
