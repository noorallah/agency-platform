// Ask why, before an action that has to be explained afterwards.
//
// Written once because the obvious way to do it is wrong twice over, and both
// mistakes were made before this file existed:
//
// **The controller must belong to the dialog, not the caller.** A caller that
// creates one, awaits `showDialog`, then disposes it, disposes it while the
// dialog is still animating out — and the `TextField` rebuilding during that
// animation throws "A TextEditingController was used after being disposed".
//
// **The content needs a width.** An `AlertDialog` gives its content unbounded
// height, so a bare `Column` with `crossAxisAlignment: stretch` overflows by
// tens of thousands of pixels rather than laying out.

import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';

/// Ask for a reason, returning what was typed or null if nothing was.
///
/// Returns null when the dialog is dismissed **and** when the box was left
/// empty: an action that needs a reason should not proceed without one, and
/// the caller gets one answer to check rather than two.
Future<String?> askForReason(
  BuildContext context, {
  required String title,
  required String explanation,
  String label = 'Reason',
  String confirmLabel = 'Confirm',
  String cancelLabel = 'Cancel',
}) =>
    showDialog<String>(
      context: context,
      builder: (context) => _ReasonDialog(
        title: title,
        explanation: explanation,
        label: label,
        confirmLabel: confirmLabel,
        cancelLabel: cancelLabel,
      ),
    );

class _ReasonDialog extends StatefulWidget {
  const _ReasonDialog({
    required this.title,
    required this.explanation,
    required this.label,
    required this.confirmLabel,
    required this.cancelLabel,
  });

  final String title;
  final String explanation;
  final String label;
  final String confirmLabel;
  final String cancelLabel;

  @override
  State<_ReasonDialog> createState() => _ReasonDialogState();
}

class _ReasonDialogState extends State<_ReasonDialog> {
  final TextEditingController _reason = TextEditingController();

  @override
  void dispose() {
    // Disposed here, when the dialog's own element goes, rather than by the
    // caller the moment `showDialog` returns — which is mid-animation, with
    // the field still rebuilding.
    _reason.dispose();
    super.dispose();
  }

  void _confirm() {
    final String text = _reason.text.trim();
    Navigator.of(context).pop(text.isEmpty ? null : text);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: SizedBox(
          // A width, because AlertDialog gives its content unbounded height
          // and a stretched Column with none overflows rather than lays out.
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                widget.explanation,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _reason,
                decoration: InputDecoration(labelText: widget.label),
                autofocus: true,
                onSubmitted: (_) => _confirm(),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(widget.cancelLabel),
          ),
          FilledButton(
            onPressed: _confirm,
            child: Text(widget.confirmLabel),
          ),
        ],
      );
}
