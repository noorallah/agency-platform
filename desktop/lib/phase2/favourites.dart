import 'dart:async';

import 'package:flutter/foundation.dart';

/// The screens a person has starred (D-UI-3, UI_PHASE_2_DESIGN.md 4.3): the
/// star in any drop-down, Home's FAVOURITES box and the top of Ctrl+K all
/// read and change this one list.
///
/// It is kept on the server in the person's preferences, under
/// `dashboard_layout.favourites`, so it follows them to every PC -- and it
/// costs no read of its own, because those preferences are already read at
/// sign-in. A change is saved once, [delay] after the last of a run of them:
/// starring five screens in a row is one request, not five (owner, 10-04).
class Favourites extends ChangeNotifier {
  Favourites({
    required List<String>? stored,
    required List<String> defaults,
    required this.save,
    this.delay = const Duration(milliseconds: 800),
  }) : _paths = List<String>.of(stored ?? defaults);

  /// What [Favourites] keeps under `dashboard_layout`.
  static const String layoutKey = 'favourites';

  /// The stored list in [layout], or null when the person has never chosen
  /// -- which is not the same as having removed every one.
  static List<String>? read(Map<String, dynamic>? layout) {
    final Object? stored = layout?[layoutKey];
    if (stored is! List) return null;
    return [
      for (final Object? path in stored)
        if (path is String) path,
    ];
  }

  /// Keep the list; called once per run of changes.
  final Future<void> Function(List<String> paths) save;
  final Duration delay;

  final List<String> _paths;
  Timer? _pending;

  /// The starred screens' router paths, in the person's order.
  List<String> get paths => List.unmodifiable(_paths);

  bool contains(String path) => _paths.contains(path);

  /// Star [path], or unstar it if it is starred. A new one goes last.
  void toggle(String path) {
    if (!_paths.remove(path)) _paths.add(path);
    _changed();
  }

  void remove(String path) {
    if (_paths.remove(path)) _changed();
  }

  /// Put [path] where [target] is, as dropping one box on another does:
  /// [target] steps aside towards where [path] came from.
  void move(String path, String target) {
    final int to = _paths.indexOf(target);
    if (path == target || to < 0 || !_paths.remove(path)) return;
    _paths.insert(to, path);
    _changed();
  }

  void _changed() {
    notifyListeners();
    _pending?.cancel();
    _pending = Timer(delay, flush);
  }

  /// Save now what is waiting to be saved, if anything.
  void flush() {
    if (_pending == null) return;
    _pending!.cancel();
    _pending = null;
    unawaited(save(paths));
  }

  /// A change still waiting is saved rather than lost.
  @override
  void dispose() {
    flush();
    super.dispose();
  }
}
