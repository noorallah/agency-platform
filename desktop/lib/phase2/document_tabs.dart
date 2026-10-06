import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
      // A SelectionArea of the tab's own (backlog 83): any label, value,
      // total or refusal in the document can be selected and copied, and a
      // select-all stays inside the document rather than taking the shell
      // around it. Safe here: the route sits in its navigator's overlay.
      pageBuilder: (context, _, __) => DocumentTabScope(
        child: _UnsavedWorkGuard(child: SelectionArea(child: builder(context))),
      ),
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

/// Leave the document the way its Cancel button and Esc should (D-UI-21).
///
/// `maybePop` rather than `pop`, so the tab's unsaved-work guard gets to ask
/// "Close without saving?" when something was typed, and the document closes
/// at once when nothing was. [saved] says the document has already been
/// saved from this window (its button reads Close, not Cancel): there is
/// nothing left to lose, so it closes directly and does not ask again.
void leaveDocument(
  BuildContext context, {
  Object? result,
  bool saved = false,
}) {
  final NavigatorState navigator = Navigator.of(context);
  if (saved) {
    navigator.pop(result);
  } else {
    unawaited(navigator.maybePop(result));
  }
}

/// Asks before a document tab that has been typed in is closed by its tab's
/// X (or anything else that goes through `maybePop`).
///
/// Decision 3 of the design: a tab with unsaved work is never closed
/// silently. The editors were dialogs, closed only by their own buttons, so
/// none guards its route; this does it once for all of them. It counts a
/// document as touched when a character is typed in it -- the work a closed
/// tab would lose. The editor's own Save and Cancel pop the route directly,
/// which this does not stand in the way of.
class _UnsavedWorkGuard extends StatefulWidget {
  const _UnsavedWorkGuard({required this.child});

  final Widget child;

  @override
  State<_UnsavedWorkGuard> createState() => _UnsavedWorkGuardState();
}

class _UnsavedWorkGuardState extends State<_UnsavedWorkGuard> {
  bool _typed = false;

  /// What the document's inputs held at the first touch (D-DLG-8).
  ///
  /// Typed characters were the only thing the guard noticed, so a document
  /// changed only by a drop-down, a switch, a chip or a date picker closed
  /// without a warning. Rather than ask every editor to report its changes --
  /// dozens of them, each a chance to forget -- the guard reads the inputs
  /// themselves: it takes a snapshot at the first pointer press or key press
  /// inside the document (before anything the user did has landed) and
  /// compares it with the inputs as they are when a close is asked for.
  /// Values that load in the background change nothing, because the snapshot
  /// is taken at a touch and not at open.
  List<String>? _baseline;

  KeyEventResult _watch(FocusNode _, KeyEvent event) {
    final String? character = event.character;
    if (event is KeyDownEvent) _baseline ??= _snapshot();
    if (!_typed &&
        event is KeyDownEvent &&
        character != null &&
        character.isNotEmpty &&
        character.codeUnitAt(0) >= 0x20) {
      setState(() => _typed = true);
    }
    return KeyEventResult.ignored;
  }

  /// The state of every input under this guard, as comparable strings.
  List<String> _snapshot() {
    final List<String> out = <String>[];
    void visit(Element element) {
      final Widget widget = element.widget;
      if (widget is EditableText) {
        out.add('text:${widget.controller.text}');
      } else if (widget is Switch) {
        out.add('switch:${widget.value}');
      } else if (widget is Checkbox) {
        out.add('check:${widget.value}');
      } else if (widget is DropdownButton) {
        out.add('drop:${widget.value}');
      } else if (widget is FilterChip) {
        out.add('filter:${widget.selected}');
      } else if (widget is ChoiceChip) {
        out.add('choice:${widget.selected}');
      } else if (widget is SegmentedButton) {
        out.add('segment:${widget.selected.toList()}');
      } else if (widget is Slider) {
        out.add('slider:${widget.value}');
      } else if (widget is InputDecorator) {
        // A date box shows its value as text in the decorator's child.
        element.visitChildren(_collectText(out));
      }
      element.visitChildren(visit);
    }

    context.visitChildElements(visit);
    return out;
  }

  bool get _dirty {
    if (_typed) return true;
    final List<String>? before = _baseline;
    if (before == null) return false;
    final List<String> now = _snapshot();
    if (before.length != now.length) return true;
    for (int i = 0; i < now.length; i++) {
      if (before[i] != now[i]) return true;
    }
    return false;
  }

  Future<void> _ask(bool didPop, Object? result) async {
    if (didPop) return;
    if (!_dirty) {
      Navigator.of(context).pop(result);
      return;
    }
    final bool? discard = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Close without saving?'),
        content: const Text(
          'What was changed in this document has not been saved and will be '
          'lost.',
        ),
        actions: [
          TextButton(
            key: const ValueKey('document-keep-editing'),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep editing'),
          ),
          FilledButton(
            key: const ValueKey('document-discard'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Discard and close'),
          ),
        ],
      ),
    );
    if (discard != true || !mounted) return;
    setState(() {
      _typed = false;
      _baseline = null;
    });
    Navigator.of(context).pop(result);
  }

  @override
  Widget build(BuildContext context) => PopScope<Object?>(
        // Always intercepted: whether the document is dirty is worked out
        // when a close is asked for, by comparing its inputs, and `canPop`
        // is read before that comparison could run.
        canPop: false,
        onPopInvokedWithResult: (didPop, result) =>
            unawaited(_ask(didPop, result)),
        child: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (_) => _baseline ??= _snapshot(),
          child: Focus(
            canRequestFocus: false,
            skipTraversal: true,
            onKeyEvent: _watch,
            child: widget.child,
          ),
        ),
      );
}

/// A visitor that appends the text of every `Text` below an element.
void Function(Element) _collectText(List<String> out) {
  void collect(Element element) {
    final Widget widget = element.widget;
    if (widget is Text) {
      out.add('label:${widget.data ?? widget.textSpan?.toPlainText() ?? ''}');
    }
    element.visitChildren(collect);
  }

  return collect;
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
