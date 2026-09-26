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
    required this.tools,
    required this.claimed,
    required Set<Object> holders,
    required bool Function() alive,
    required super.child,
  })  : _alive = alive,
        _holders = holders;

  /// The lists holding the line; it is claimed while any does.
  final Set<Object> _holders;

  /// Whether the frame is still on screen; a deferred update must not land
  /// on notifiers its page has already disposed.
  final bool Function() _alive;

  final String title;
  final String description;

  /// The page's own tabs, drawn on the same line.
  final Widget? tabs;

  /// The summary figures, as counters.
  final ValueNotifier<List<Widget>> counters;

  /// A screen's own search box and buttons, for a screen that builds its
  /// own header rather than using a list layout: drawn at the right of the
  /// frame's line, so the screen needs no second line of its own.
  final ValueNotifier<List<Widget>> tools;

  /// Whether a list layout below draws the line.
  final ValueNotifier<bool> claimed;

  static Phase2PageBar? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<Phase2PageBar>();

  /// Take the line. Deferred to after the frame: it changes what an
  /// ancestor draws, which may not happen while the tree is being built.
  void claim(Object holder) {
    if (!_holders.add(holder) && claimed.value) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) claimed.value = _holders.isNotEmpty;
    });
  }

  /// Give the line back: the list that took it has gone. Without this a
  /// frame reused for the next screen (the admin area keeps one frame for
  /// all its screens) stayed claimed and drew no title at all.
  void release(Object holder) {
    _holders.remove(holder);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) claimed.value = _holders.isNotEmpty;
    });
  }

  /// Show [figures] on the line, after the frame for the same reason.
  void publish(List<Widget> figures) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) counters.value = figures;
    });
  }

  /// Show a screen's own [widgets] at the right of the line, after the
  /// frame for the same reason.
  void publishTools(List<Widget> widgets) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_alive()) tools.value = widgets;
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
  final ValueNotifier<List<Widget>> _tools = ValueNotifier(const []);
  final ValueNotifier<bool> _claimed = ValueNotifier(false);
  final Set<Object> _holders = <Object>{};

  @override
  void didUpdateWidget(covariant Phase2PageBarHost oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Another screen in the same frame: what the last one put on the line
    // is not this one's.
    if (oldWidget.title != widget.title) {
      _counters.value = const [];
      _tools.value = const [];
    }
  }

  @override
  void dispose() {
    _counters.dispose();
    _tools.dispose();
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
            tools: _tools,
            claimed: _claimed,
            holders: _holders,
            alive: () => mounted,
            child: Builder(
              builder: (context) => widget.builder(context, bar, claimed),
            ),
          );
          return bar;
        },
      );
}

/// The phase 2 window's one bottom bar, as the wireframe draws it: what the
/// screen on show says about itself at the left ("12 records  1 selected",
/// the role on Home), the connection at the right. A list's own status bar
/// hands its line here instead of drawing a second bar above it.
class Phase2StatusScope extends InheritedWidget {
  const Phase2StatusScope({
    super.key,
    required this.left,
    required this.alive,
    required super.child,
  });

  /// What the left of the bar shows; null for nothing.
  final ValueNotifier<Widget?> left;

  /// Whether the shell is still on screen, so a deferred update never lands
  /// on a disposed notifier.
  final bool Function() alive;

  static Phase2StatusScope? of(BuildContext context) =>
      context.getInheritedWidgetOfExactType<Phase2StatusScope>();

  /// Show [line] at the left of the bar. Deferred to after the frame: it
  /// changes what an ancestor draws.
  void publish(Widget line) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (alive()) left.value = line;
    });
  }

  @override
  bool updateShouldNotify(Phase2StatusScope oldWidget) =>
      left != oldWidget.left;
}

/// The name the menu gives the screen on show ("Customers"), which the page
/// line uses as its title as the wireframe does -- rather than the longer
/// heading phase 1 screens carry ("Customer Management").
class Phase2ScreenTitle extends InheritedWidget {
  const Phase2ScreenTitle(
      {super.key, required this.title, required super.child});

  final String? title;

  static String? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<Phase2ScreenTitle>()?.title;

  @override
  bool updateShouldNotify(Phase2ScreenTitle oldWidget) =>
      title != oldWidget.title;
}
