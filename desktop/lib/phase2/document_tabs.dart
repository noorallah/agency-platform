import 'dart:async';

import 'package:flutter/material.dart';

/// One document open as a tab: an order, an invoice, a receipt being entered.
class OpenDocument {
  OpenDocument._(this.id, this.title, this.route);

  /// Its address among the open-screen tabs, `doc:<n>`.
  final String id;
  final String title;

  /// The route the document is shown in, inside its own navigator.
  final Route<Object?> route;
}

/// The documents open as tabs in the phase 2 app (UI_PHASE_2_DESIGN.md 4.8,
/// decision 4: documents are full-page tabs, not dialogs).
///
/// Each editor was written as a dialog: shown with `showDialog`, closed with
/// `Navigator.pop(result)`, its caller awaiting the result. [showDocument]
/// keeps all of that true. A document is a route in a navigator of its own,
/// so the editor's own `pop(result)` closes the tab and hands the result back
/// to whoever opened it -- no editor changes to become a tab, and none can
/// forget to close one.
class DocumentTabsController extends ChangeNotifier {
  final List<OpenDocument> _documents = [];
  int _next = 1;

  List<OpenDocument> get documents => List.unmodifiable(_documents);

  /// Called with each document as it opens, so the shell can show it.
  ValueChanged<OpenDocument>? onOpened;

  /// Called with each document once it has closed.
  ValueChanged<OpenDocument>? onClosed;

  static const String prefix = 'doc:';

  static bool isDocument(String id) => id.startsWith(prefix);

  OpenDocument? find(String id) =>
      _documents.where((document) => document.id == id).firstOrNull;

  /// Open [builder] as a document titled [title]; completes with what the
  /// document popped with, as `showDialog` would.
  Future<T?> open<T>({required String title, required WidgetBuilder builder}) {
    final Completer<T?> result = Completer<T?>();
    final PageRouteBuilder<T> route = PageRouteBuilder<T>(
      pageBuilder: (context, _, __) =>
          DocumentTabScope(child: builder(context)),
      transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
    );
    final OpenDocument document =
        OpenDocument._('$prefix${_next++}', title, route);
    unawaited(route.popped.then((value) {
      _documents.remove(document);
      notifyListeners();
      onClosed?.call(document);
      if (!result.isCompleted) result.complete(value);
    }));
    _documents.add(document);
    notifyListeners();
    onOpened?.call(document);
    return result.future;
  }

  /// Close a document the way its own Cancel would: through `maybePop`, so
  /// a document that asks before discarding work still gets to ask.
  void close(String id) {
    final OpenDocument? document = find(id);
    final NavigatorState? navigator = document?.route.navigator;
    if (navigator != null) unawaited(navigator.maybePop());
  }
}

/// Where [showDocument] finds the phase 2 app's document tabs.
class DocumentTabsScope extends InheritedWidget {
  const DocumentTabsScope({
    super.key,
    required this.controller,
    required super.child,
  });

  final DocumentTabsController controller;

  static DocumentTabsController? maybeOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<DocumentTabsScope>()?.controller;

  @override
  bool updateShouldNotify(DocumentTabsScope oldWidget) =>
      controller != oldWidget.controller;
}

/// Marks a subtree as a document open in a tab, so `WorkspaceDialog` draws
/// itself as a full page rather than as a dialog floating over one.
class DocumentTabScope extends InheritedWidget {
  const DocumentTabScope({super.key, required super.child});

  static bool of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<DocumentTabScope>() != null;

  @override
  bool updateShouldNotify(DocumentTabScope oldWidget) => false;
}

/// Show a document editor: in a tab of its own in the phase 2 app, as a
/// dialog in phase 1 -- which is exactly what it was.
///
/// A drop-in for `showDialog`: same builder, same result.
Future<T?> showDocument<T>(
  BuildContext context, {
  required String title,
  required WidgetBuilder builder,
}) {
  final DocumentTabsController? tabs = DocumentTabsScope.maybeOf(context);
  if (tabs == null) return showDialog<T>(context: context, builder: builder);
  return tabs.open<T>(title: title, builder: builder);
}

/// A document's own navigator: a blank page beneath it, so the document's
/// `pop` has somewhere to return to, and the document above.
class DocumentNavigator extends StatefulWidget {
  const DocumentNavigator({super.key, required this.document});

  final OpenDocument document;

  @override
  State<DocumentNavigator> createState() => _DocumentNavigatorState();
}

class _DocumentNavigatorState extends State<DocumentNavigator> {
  @override
  Widget build(BuildContext context) => Navigator(
        onGenerateInitialRoutes: (navigator, _) => [
          PageRouteBuilder<void>(
            pageBuilder: (context, _, __) => const SizedBox.shrink(),
            transitionDuration: Duration.zero,
          ),
          widget.document.route,
        ],
      );
}
