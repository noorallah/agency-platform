// One question for a dialog that is closed with something typed in it.
//
// Cancel, the cross and Escape closed a typed dialog at once and threw the
// typing away (D-UI-33, then D-UI-51/53/55/57/58: the same defect found one
// dialog at a time). The receipt dialog grew its own answer first; this is
// that answer as a widget, so the next dialog wraps itself rather than
// copying it.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Wrap a dialog's content so that leaving it asks first when [touched], or
/// when any input under it no longer holds what it held at the first touch.
///
/// The second half is D-UI-63: a dialog reports its typed boxes through
/// [touched] (usually `Form.onChanged`), which a switch, a checkbox, a
/// segmented control, a chip, a date or a row added to a list never reach --
/// so a promotion changed only by a switch closed without a question. Rather
/// than ask every dialog to report every control, the wrapper reads the
/// inputs under it the way the document tabs' guard does ([inputSnapshot]),
/// once when a pointer or key first touches the dialog and again when a close
/// is asked for. An untouched dialog still closes at once, and so does one
/// that put everything back.
///
/// A Cancel button inside must call `Navigator.maybePop`, which is what lands
/// here; `Navigator.pop` -- what a successful save calls -- closes without
/// asking, as it should.
class AskBeforeClosing extends StatefulWidget {
  const AskBeforeClosing({
    super.key,
    required this.touched,
    required this.what,
    required this.child,
    this.busy = false,
  });

  /// Whether anything has been chosen or typed, so closing would lose it.
  final bool Function() touched;

  /// What is lost, as it reads after "The ": `coupon has not been saved`.
  final String what;

  /// A save is in flight: closing waits for its answer.
  final bool busy;

  final Widget child;

  @override
  State<AskBeforeClosing> createState() => _AskBeforeClosingState();
}

class _AskBeforeClosingState extends State<AskBeforeClosing> {
  List<String>? _baseline;

  bool _touched() {
    if (widget.touched()) return true;
    final List<String>? before = _baseline;
    return before != null && !snapshotsEqual(before, inputSnapshot(context));
  }

  Future<void> _ask(BuildContext context) async {
    final NavigatorState navigator = Navigator.of(context);
    if (!_touched()) {
      navigator.pop();
      return;
    }
    final bool? discard = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Close without saving?'),
        content: Text('The ${widget.what} and what was typed will be lost.'),
        actions: [
          TextButton(
            key: const ValueKey('discard-keep-editing'),
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep editing'),
          ),
          FilledButton(
            key: const ValueKey('discard-and-close'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Discard and close'),
          ),
        ],
      ),
    );
    if (discard == true && navigator.mounted) navigator.pop();
  }

  @override
  Widget build(BuildContext context) => PopScope<Object?>(
        canPop: false,
        onPopInvokedWithResult: (bool didPop, Object? result) {
          if (didPop || widget.busy) return;
          unawaited(_ask(context));
        },
        child: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (_) => _baseline ??= inputSnapshot(context),
          child: Focus(
            canRequestFocus: false,
            skipTraversal: true,
            onKeyEvent: (FocusNode node, KeyEvent event) {
              if (event is KeyDownEvent) _baseline ??= inputSnapshot(context);
              return KeyEventResult.ignored;
            },
            child: widget.child,
          ),
        ),
      );
}

/// The state of every input under [context], as comparable strings: what a
/// text box, switch, checkbox, drop-down, chip, segmented control or slider
/// holds, and the text shown in a date box.
List<String> inputSnapshot(BuildContext context) {
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

/// Whether two [inputSnapshot]s read the same.
bool snapshotsEqual(List<String> before, List<String> now) {
  if (before.length != now.length) return false;
  for (int i = 0; i < now.length; i++) {
    if (before[i] != now[i]) return false;
  }
  return true;
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
