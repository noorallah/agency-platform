import 'package:flutter/foundation.dart';

class WorkspaceLocation {
  const WorkspaceLocation(this.module, [this.tab]);

  final String module;
  final String? tab;

  String get path => tab == null || tab!.isEmpty ? module : '$module/$tab';

  static WorkspaceLocation parse(String? value) {
    final List<String> segments = (value ?? '')
        .split('/')
        .map((segment) => segment.trim())
        .where((segment) => segment.isNotEmpty)
        .toList();
    return WorkspaceLocation(
      segments.isEmpty ? 'dashboard' : segments.first,
      segments.length > 1 ? segments[1] : null,
    );
  }
}

class WorkspaceRouter extends ChangeNotifier {
  WorkspaceRouter({
    String? initialLocation,
    Future<void> Function(String location)? onPersist,
  })  : _current = WorkspaceLocation.parse(initialLocation),
        _onPersist = onPersist;

  final Future<void> Function(String location)? _onPersist;
  final List<WorkspaceLocation> _backStack = [];
  final List<WorkspaceLocation> _forwardStack = [];
  WorkspaceLocation _current;

  WorkspaceLocation get current => _current;
  bool get canGoBack => _backStack.isNotEmpty;
  bool get canGoForward => _forwardStack.isNotEmpty;

  void navigate(String module, {String? tab, bool replace = false}) {
    final WorkspaceLocation next = WorkspaceLocation(module, tab);
    if (next.path == _current.path) return;
    if (!replace) _backStack.add(_current);
    _current = next;
    _forwardStack.clear();
    _changed();
  }

  void selectTab(String tab) => navigate(_current.module, tab: tab);

  void back() {
    if (!canGoBack) return;
    _forwardStack.add(_current);
    _current = _backStack.removeLast();
    _changed();
  }

  void forward() {
    if (!canGoForward) return;
    _backStack.add(_current);
    _current = _forwardStack.removeLast();
    _changed();
  }

  void _changed() {
    notifyListeners();
    _onPersist?.call(_current.path);
  }
}
