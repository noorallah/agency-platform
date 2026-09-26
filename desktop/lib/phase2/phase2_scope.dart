import 'package:flutter/widgets.dart';

/// Marks a subtree as drawn by the phase 2 app.
///
/// The shared framework (`ModuleWorkspaceFrame`, `ManagementWorkspaceLayout`,
/// `FilterPanel`, `SummaryMetricCard`) reads it to draw the compact page
/// frame of UI_PHASE_2_DESIGN.md 4.5 -- one line above the grid instead of a
/// title band, a search row, a filter tile and a row of cards. Only
/// `DesktopShell` in the phase 2 app puts it in the tree, so phase 1 draws
/// exactly what it always drew and every screen gains the frame at once,
/// without any screen's own code changing.
class Phase2Scope extends InheritedWidget {
  const Phase2Scope({super.key, required super.child});

  /// Whether [context] is inside the phase 2 app.
  static bool of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<Phase2Scope>() != null;

  @override
  bool updateShouldNotify(Phase2Scope oldWidget) => false;
}

/// What a page frame hands to the one line of its list (4.5).
///
/// Phase 1 stacks a title band, a row of summary cards and a search row.
/// Phase 2 draws them as **one** line -- `Sales Orders  Draft 3  Approved 5
/// ... [Filters] [search] [+ New]` -- but they are built by three different
/// widgets: the frame knows the title, `SummaryCards` the figures, and the
/// list layout the search and actions. The frame puts this in the tree; the
/// figures are published into [counters]; the list layout [claim]s the line
/// and draws all of it, and the frame then draws no title line of its own.
/// A page with no list (a settings form, a dashboard) never claims it, and
/// the frame keeps a compact title line with the figures on it.
class Phase2PageBar extends InheritedWidget {
  const Phase2PageBar._({
    required this.title,
    required this.description,
    required this.tabs,
    required this.counters,
    required this.claimed,
    required bool Function() alive,
    required super.child,
  }) : _alive = alive;

  /// Whether the frame is still on screen; a deferred update must not land
  /// on notifiers its page has already disposed.
  final bool Function() _alive;

  final String title;
  final String description;

  /// The page's own tabs, drawn on the same line.
  final Widget? tabs;

  /// The summary figures, as counters.
  final ValueNotifier<List<Widget>> counters;

  /// Whether a list layout below draws the line.
  final ValueNotifier<bool> claimed;

  static Phase2PageBar? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<Phase2PageBar>();

  /// Take the line. Deferred to after the frame: it changes what an
  /// ancestor draws, which may not happen while the tree is being built.
  void claim() {
    if (claimed.value) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) claimed.value = true;
    });
  }

  /// Show [figures] on the line, after the frame for the same reason.
  void publish(List<Widget> figures) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) counters.value = figures;
    });
  }

  @override
  bool updateShouldNotify(Phase2PageBar oldWidget) =>
      title != oldWidget.title ||
      description != oldWidget.description ||
      tabs != oldWidget.tabs;
}

/// Puts a [Phase2PageBar] in the tree and owns its notifiers, which must
/// outlive the frame's rebuilds -- a frame rebuilds on every keystroke in its
/// search box, and a fresh notifier each time would drop the figures.
class Phase2PageBarHost extends StatefulWidget {
  const Phase2PageBarHost({
    super.key,
    required this.title,
    required this.description,
    this.tabs,
    required this.builder,
  });

  final String title;
  final String description;
  final Widget? tabs;

  /// The frame's body; [claimed] says whether a list below draws the line.
  final Widget Function(
    BuildContext context,
    Phase2PageBar bar,
    bool claimed,
  ) builder;

  @override
  State<Phase2PageBarHost> createState() => _Phase2PageBarHostState();
}

class _Phase2PageBarHostState extends State<Phase2PageBarHost> {
  final ValueNotifier<List<Widget>> _counters = ValueNotifier(const []);
  final ValueNotifier<bool> _claimed = ValueNotifier(false);

  @override
  void dispose() {
    _counters.dispose();
    _claimed.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<bool>(
        valueListenable: _claimed,
        builder: (context, claimed, _) {
          late final Phase2PageBar bar;
          bar = Phase2PageBar._(
            title: widget.title,
            description: widget.description,
            tabs: widget.tabs,
            counters: _counters,
            claimed: _claimed,
            alive: () => mounted,
            child: Builder(
              builder: (context) => widget.builder(context, bar, claimed),
            ),
          );
          return bar;
        },
      );
}
