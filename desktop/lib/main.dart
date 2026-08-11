import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/branding/branding_config.dart';
import 'core/diagnostics/crash_reporter.dart';
import 'core/diagnostics/report_queue.dart';
import 'core/logging/app_log.dart';
import 'core/preferences/desktop_preferences_service.dart';
import 'core/preferences/desktop_window_controller.dart';

const String _buildNumber =
    String.fromEnvironment('BUILD_NUMBER', defaultValue: 'Unknown');

/// Set at build time: `--dart-define=LOG_LEVEL=debug`. Unrecognised values fall
/// back to the build's default rather than silencing the log by typo.
const String _logLevel = String.fromEnvironment('LOG_LEVEL');

LogLevel? _configuredLogLevel() {
  for (final LogLevel level in LogLevel.values) {
    if (level.name == _logLevel.trim().toLowerCase()) return level;
  }
  return null;
}

/// Held for the process lifetime so the exit hook is not garbage collected.
AppLifecycleListener? lifecycleListener;

Future<void> main() async {
  // Everything runs inside the guarded zone, including binding initialization,
  // so an error thrown before the first frame is recorded rather than lost.
  runZonedGuarded<Future<void>>(_run, (error, stack) {
    CrashReporter.recordError('Uncaught zone error', error, stack);
  });
}

Future<void> _run() async {
  WidgetsFlutterBinding.ensureInitialized();
  AppLog.initialize(level: _configuredLogLevel());
  AppLog.info(
    'Startup: build $_buildNumber, level ${AppLog.minimumLevel.name}, '
    '${Platform.operatingSystem} ${Platform.operatingSystemVersion}, '
    'dart ${Platform.version}',
  );
  // Reads the previous run's verdict before claiming the marker for this one.
  CrashReporter.beginSession();

  FlutterError.onError = (details) {
    CrashReporter.recordError(
      'Flutter framework error${details.context == null ? '' : ' '
          '(${details.context!.toDescription()})'}',
      details.exception,
      details.stack,
    );
    FlutterError.presentError(details);
  };

  // Returning true keeps the application alive. An uncaught async error should
  // leave a record and a usable window, not an empty desktop.
  PlatformDispatcher.instance.onError = (error, stack) {
    CrashReporter.recordError('Uncaught platform error', error, stack);
    return true;
  };

  // A build failure renders this instead of the red screen, so one broken
  // widget does not read as a dead application.
  ErrorWidget.builder = (details) {
    CrashReporter.recordError(
      'Widget build error',
      details.exception,
      details.stack,
    );
    return _InlineErrorBox(message: details.exceptionAsString());
  };

  // Marks a deliberate close. If the log ends without this line, the process
  // did not choose to exit -- that is the difference between a shutdown and a
  // crash, and it is the first thing worth knowing.
  lifecycleListener = AppLifecycleListener(
    onExitRequested: () async {
      AppLog.info('Exit requested by the operating system.');
      // Clears the marker, so the next launch does not report this as a crash.
      CrashReporter.endSessionCleanly();
      return AppExitResponse.exit;
    },
    onStateChange: (state) => AppLog.info('Lifecycle: ${state.name}'),
  );

  try {
    final DesktopPreferencesService preferences = DesktopPreferencesService();
    await preferences.load();
    AppLog.info('Preferences loaded.');
    final BrandingConfig branding = await BrandingConfig.load();
    AppLog.info('Branding loaded: ${branding.appName}.');
    try {
      await DesktopWindowController(preferences).initialize(branding);
      AppLog.info('Window initialized.');
    } catch (error, stack) {
      AppLog.recordError('Window initialization failed', error, stack);
    }
    // Queued now rather than sent: this runs before anyone has signed in, and
    // the previous session's verdict is exactly the report worth keeping.
    ReportQueue().enqueueSession(
      appVersion: branding.version,
      buildNumber: _buildNumber,
    );
    runApp(AgencyApp(preferences: preferences, branding: branding));
    AppLog.info('Application started.');
  } catch (error, stack) {
    AppLog.recordError('Unhandled startup error', error, stack);
    runApp(_StartupErrorApp(error: error, stackTrace: stack));
  }
}

/// Replaces the red error screen for a single failed widget.
class _InlineErrorBox extends StatelessWidget {
  const _InlineErrorBox({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        color: const Color(0xfffdecec),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.report_problem_outlined,
                    size: 18, color: Color(0xffb42318)),
                SizedBox(width: 8),
                Flexible(
                  child: Text(
                    'This section failed to render. The rest of the app is '
                    'still usable.',
                    style: TextStyle(
                      color: Color(0xffb42318),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              message,
              maxLines: 6,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11, fontFamily: 'monospace'),
            ),
            if (AppLog.filePath != null) ...[
              const SizedBox(height: 6),
              Text(
                'Logged to ${AppLog.filePath}',
                style: const TextStyle(fontSize: 11),
              ),
            ],
          ],
        ),
      );
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
                        style: const TextStyle(
                            fontSize: 12, fontFamily: 'monospace'),
                      ),
                      if (AppLog.filePath != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          'Details were written to ${AppLog.filePath}',
                          style: const TextStyle(fontSize: 12),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
}
