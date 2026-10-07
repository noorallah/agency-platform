// One question for a dialog that is closed with something typed in it.
//
// Cancel, the cross and Escape closed a typed dialog at once and threw the
// typing away (D-UI-33, then D-UI-51/53/55/57/58: the same defect found one
// dialog at a time). The receipt dialog grew its own answer first; this is
// that answer as a widget, so the next dialog wraps itself rather than
// copying it.

import 'dart:async';

import 'package:flutter/material.dart';

/// Wrap a dialog's content so that leaving it asks first when [touched].
///
/// A Cancel button inside must call `Navigator.maybePop`, which is what lands
/// here; `Navigator.pop` -- what a successful save calls -- closes without
/// asking, as it should.
class AskBeforeClosing extends StatelessWidget {
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

  Future<void> _ask(BuildContext context) async {
    final NavigatorState navigator = Navigator.of(context);
    if (!touched()) {
      navigator.pop();
      return;
    }
    final bool? discard = await showDialog<bool>(
      context: context,
      builder: (BuildContext dialogContext) => AlertDialog(
        title: const Text('Close without saving?'),
        content: Text('The $what and what was typed will be lost.'),
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
          if (didPop || busy) return;
          unawaited(_ask(context));
        },
        child: child,
      );
}
