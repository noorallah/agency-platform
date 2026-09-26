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
