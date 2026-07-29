import 'dart:async';
import 'dart:ui';

import 'package:window_manager/window_manager.dart';

import '../branding/branding_config.dart';
import 'desktop_preferences_service.dart';

class DesktopWindowController with WindowListener {
  DesktopWindowController(this._preferences);

  final DesktopPreferencesService _preferences;

  Future<void> initialize(BrandingConfig branding) async {
    await windowManager.ensureInitialized();
    final Map<String, dynamic> state = _preferences.current.windowState;
    final Size size = Size(
      _dimension(state['width'], 1280),
      _dimension(state['height'], 720),
    );
    await windowManager.waitUntilReadyToShow(
      WindowOptions(
        title: branding.windowName,
        size: size,
        center: !_hasPosition(state),
        minimumSize: const Size(960, 640),
        backgroundColor: branding.loginBackgroundColor,
      ),
    );
    if (_hasPosition(state)) {
      await windowManager.setPosition(
        Offset(
          _dimension(state['x'], 10),
          _dimension(state['y'], 10),
        ),
      );
    }
    if (state['maximized'] == true) {
      await windowManager.maximize();
    }
    await windowManager.show();
    await windowManager.focus();
    windowManager.addListener(this);
  }

  @override
  void onWindowMaximize() => unawaited(_saveState());

  @override
  void onWindowMoved() => unawaited(_saveState());

  @override
  void onWindowResized() => unawaited(_saveState());

  @override
  void onWindowUnmaximize() => unawaited(_saveState());

  Future<void> _saveState() async {
    final Rect bounds = await windowManager.getBounds();
    await _preferences.saveWindowState({
      'x': bounds.left,
      'y': bounds.top,
      'width': bounds.width,
      'height': bounds.height,
      'maximized': await windowManager.isMaximized(),
    });
  }

  bool _hasPosition(Map<String, dynamic> state) =>
      state['x'] is num && state['y'] is num;

  double _dimension(dynamic value, double fallback) =>
      value is num && value > 0 ? value.toDouble() : fallback;
}
