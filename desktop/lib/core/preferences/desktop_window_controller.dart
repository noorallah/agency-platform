import 'dart:async';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:screen_retriever/screen_retriever.dart';
import 'package:window_manager/window_manager.dart';

import '../branding/branding_config.dart';
import 'desktop_preferences_service.dart';
import '../platform/app_storage.dart';

class DesktopWindowController with WindowListener {
  DesktopWindowController(this._preferences);

  final DesktopPreferencesService _preferences;

  Future<void> initialize(BrandingConfig branding) async {
    // A phone has one full-screen window and no window manager plugin;
    // calling it there throws before the first frame.
    if (!AppStorage.isDesktop) return;
    try {
      await windowManager.ensureInitialized();
      final Map<String, dynamic> state = _preferences.current.windowState;
      final Rect? screen = await _workArea();
      // A size saved on a bigger or less-scaled screen is cut to this one:
      // the owner's window came back 1550 px wide on a 1536 px screen, which
      // put minimize, maximize and close past its right edge.
      final Size size = Size(
        _fit(_dimension(state['width'], 1280), screen?.width),
        _fit(_dimension(state['height'], 720), screen?.height),
      );
      final bool placed = _hasPosition(state) &&
          (screen == null ||
              screen.contains(Offset(
                    _dimension(state['x'], 10) + size.width - 1,
                    _dimension(state['y'], 10) + size.height - 1,
                  )) &&
                  screen.contains(Offset(
                    _dimension(state['x'], 10),
                    _dimension(state['y'], 10),
                  )));
      await windowManager.waitUntilReadyToShow(
        WindowOptions(
          title: branding.windowName,
          size: size,
          center: !placed,
          minimumSize: const Size(960, 640),
          backgroundColor: branding.loginBackgroundColor,
        ),
      );
      if (placed) {
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
    } on Exception catch (error, stack) {
      debugPrint('Window manager initialization failed: $error\n$stack');
    }
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

  /// The primary screen's work area (the taskbar left out), in the same
  /// logical pixels the window is sized in; null when it cannot be read.
  Future<Rect?> _workArea() async {
    try {
      final Display display = await screenRetriever.getPrimaryDisplay();
      final Size? visible = display.visibleSize;
      if (visible == null) return null;
      return (display.visiblePosition ?? Offset.zero) & visible;
    } on Exception {
      return null;
    }
  }

  double _fit(double value, double? limit) =>
      limit == null || value <= limit ? value : limit;

  bool _hasPosition(Map<String, dynamic> state) =>
      state['x'] is num && state['y'] is num;

  double _dimension(dynamic value, double fallback) =>
      value is num && value > 0 ? value.toDouble() : fallback;
}
