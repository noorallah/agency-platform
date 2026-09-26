import 'package:flutter/widgets.dart';

/// "Open this screen showing that": the view a screen should show when it
/// was opened for a reason -- Home's "Orders to approve" opens Sales Orders
/// showing the drafts, "Invoices overdue" opens Reports on the overdue
/// report (the owner's request, 2026-09-26).
///
/// One request at a time, numbered so a screen applies each once. The shell
/// makes one when something opens a screen for a reason and drops it when the
/// screen is opened any other way, so the menu, a tab or Ctrl+K still open a
/// screen as it always opened.
class ListViewRequest {
  const ListViewRequest({
    required this.path,
    required this.view,
    required this.serial,
  });

  /// The screen, as the menu addresses it.
  final String path;

  /// What to show there: a view's name, a report's id.
  final String view;

  final int serial;
}

/// Where a screen finds the request meant for it.
class ListViewRequestScope extends InheritedWidget {
  const ListViewRequestScope({
    super.key,
    required this.request,
    required super.child,
  });

  final ListViewRequest? request;

  /// The request for the screen at [path], if there is one. Read from
  /// `didChangeDependencies`, and applied only when its serial is new.
  static ListViewRequest? of(BuildContext context, String path) {
    final ListViewRequest? request = context
        .dependOnInheritedWidgetOfExactType<ListViewRequestScope>()
        ?.request;
    return request?.path == path ? request : null;
  }

  @override
  bool updateShouldNotify(ListViewRequestScope oldWidget) =>
      request?.serial != oldWidget.request?.serial;
}
