import 'package:flutter/widgets.dart';

import 'app.dart';
import 'core/branding/branding_config.dart';
import 'core/preferences/desktop_preferences_service.dart';
import 'core/preferences/desktop_window_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final DesktopPreferencesService preferences = DesktopPreferencesService();
  await preferences.load();
  final BrandingConfig branding = await BrandingConfig.load();
  await DesktopWindowController(preferences).initialize(branding);
  runApp(AgencyApp(preferences: preferences, branding: branding));
}
