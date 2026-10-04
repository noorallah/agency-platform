/// A document's next steps, stated once and offered in two places: the list
/// toolbar's commands and the document's own window (D-BUY-22).
///
/// A goods receipt could only be completed from the list. Its window offered
/// *Save receipt* and nothing else, so the owner saved two receipts, closed
/// them, and took them for completed -- both were drafts, with no stock
/// posted. ERPNext puts Submit on the form and Zoho offers "Save as draft"
/// beside "Save"; the step belongs where the document is being looked at.
///
/// Each document's page builds its list of [DocumentStep]s from the checks
/// its toolbar already made -- the permission code the server enforces and
/// the [DocumentStatusGate] for its status -- and the same list drives the
/// toolbar commands and the [DocumentStepStrip] in each window, so the two
/// can never disagree about one record.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_refusal.dart';
import '../../core/notifications/notification_service.dart';
import '../workspace/workspace_components.dart';

/// What a document window closes with after it moved its document along:
/// what to tell the user, said by the page once its list is read again.
class DocumentStepDone {
  const DocumentStepDone(this.message, {this.warning = false, this.step = ''});

  final String message;

  /// Which step ran, for a page with something to add after a particular
  /// one (an e-way bill nudge after approving or dispatching).
  final String step;

  /// Said as a warning rather than a success: the step ran, and the server
  /// had something to add (a late GST credit, an e-way bill missing).
  final bool warning;
}

/// The little a step needs to know of a document: which one it is, what it
/// is called and where it stands. Pages that hold a private row type and
/// windows that hold the server's JSON both reduce to it, so one definition
/// of a document's steps serves both.
class DocumentRef {
  const DocumentRef({
    required this.id,
    required this.number,
    required this.status,
  });

  /// [numberKey] names the document's number in the server's JSON
  /// (`invoice_number`, `return_number`); a `data` envelope is unwrapped.
  factory DocumentRef.fromJson(
    Map<String, dynamic> json, {
    required String numberKey,
  }) {
    final Object? data = json['data'];
    final Map<String, dynamic> body =
        data is Map<String, dynamic> ? data : json;
    return DocumentRef(
      id: '${body['id'] ?? ''}',
      number: '${body[numberKey] ?? ''}',
      status: '${body['status'] ?? ''}',
    );
  }

  final String id;
  final String number;
  final String status;
}

/// One next step a document can take.
class DocumentStep<T> {
  const DocumentStep({
    required this.id,
    required this.label,
    required this.icon,
    required this.permitted,
    required this.allows,
    required this.run,
    this.forward = false,
    this.afterSave,
  });

  /// Keys the toolbar command `toolbar-command-<id>` and the window's
  /// control `document-step-<id>`.
  final String id;
  final String label;
  final IconData icon;

  /// Whether the signed-in user holds the code the server asks for.
  final bool permitted;

  /// Whether the record's state lets the step run.
  final bool Function(T record) allows;

  /// Take the step: ask whatever it asks first (a reason, a licence check, a
  /// credit warning), then call the server.
  ///
  /// Returns what to tell the user, or null when the user backed out of one
  /// of those questions. A refusal is thrown as an [ApiException], for the
  /// caller to show where it shows refusals.
  final Future<DocumentStepDone?> Function(BuildContext context, T record) run;

  /// The step that moves the document on rather than ending it -- Approve,
  /// Complete, Dispatch. A window shows it as a button; Cancel, Close and
  /// the like sit behind "More".
  final bool forward;

  /// The label this step takes when a window offers it together with a save
  /// of the draft being typed ("Save & complete"); null where it is not
  /// offered that way.
  final String? afterSave;

  bool enabledFor(T? record) =>
      record != null && permitted && allows(record);

  /// The same step over another shape of the same document: a window that
  /// holds the server's JSON where the list holds a parsed row.
  DocumentStep<S> on<S>(T Function(S source) convert) => DocumentStep<S>(
        id: id,
        label: label,
        icon: icon,
        permitted: permitted,
        allows: (S source) => allows(convert(source)),
        run: (BuildContext context, S source) => run(context, convert(source)),
        forward: forward,
        afterSave: afterSave,
      );

  /// The list toolbar's command for this step against [record].
  ToolbarCommand command(
    T? record,
    void Function(DocumentStep<T> step, T record) onRun,
  ) =>
      ToolbarCommand(
        id: id,
        label: label,
        icon: icon,
        onPressed: enabledFor(record) ? () => onRun(this, record as T) : null,
      );
}

/// The step a window offers together with a save of its draft: the first one
/// that names an [DocumentStep.afterSave] label and that the user may take.
DocumentStep<T>? stepAfterSave<T>(List<DocumentStep<T>> steps) {
  for (final DocumentStep<T> step in steps) {
    if (step.afterSave != null && step.permitted) return step;
  }
  return null;
}

/// Show what a step said, as a list page does once it has read itself again.
///
/// An empty message says nothing: a step that asked something first -- a
/// credit warning before an approval -- leaves that on screen rather than
/// covering it with "approved".
void showStepDone(BuildContext context, DocumentStepDone done) {
  if (done.message.isEmpty) return;
  NotificationService.show(
    context,
    done.message,
    kind: done.warning
        ? AppNotificationKind.warning
        : AppNotificationKind.success,
  );
}

/// Take [step] from a list page: the window's call, then the page's reload
/// and the step's message; a refusal goes to a toast, as the list's always
/// did. Returns what the step said, or null where it did not run.
Future<DocumentStepDone?> runStepFromList<T>(
  BuildContext context,
  DocumentStep<T> step,
  T record, {
  required Future<void> Function() reload,
}) async {
  try {
    final DocumentStepDone? done = await step.run(context, record);
    if (done == null) return null;
    await reload();
    if (context.mounted) showStepDone(context, done);
    return done;
  } on ApiException catch (error) {
    if (!context.mounted) return null;
    NotificationService.show(
      context,
      refusalMessage(error),
      kind: AppNotificationKind.error,
    );
    return null;
  }
}

/// Save the draft a window is typing, then take [step] on what was saved
/// ("Save & complete").
///
/// [save] returns the saved document, or null when the save was refused --
/// it has already said why. A step that succeeds closes the window with its
/// message; a step that is refused, or that the user backs out of, leaves the
/// window open on the saved draft: [onStopped] gets the saved document and
/// the server's sentence (null for a back-out), so the window can hold the
/// draft rather than raise a second one on the next save.
Future<void> saveThenStep<T>(
  BuildContext context, {
  required Future<T?> Function() save,
  required DocumentStep<T> step,
  required void Function(T saved, String? refusal) onStopped,
}) async {
  final T? saved = await save();
  if (saved == null || !context.mounted) return;
  if (!step.allows(saved)) {
    onStopped(saved, null);
    return;
  }
  try {
    final DocumentStepDone? done = await step.run(context, saved);
    if (!context.mounted) return;
    if (done == null) {
      onStopped(saved, null);
      return;
    }
    Navigator.of(context).pop(done);
  } on ApiException catch (error) {
    if (!context.mounted) return;
    onStopped(saved, refusalMessage(error));
  }
}

/// A window's save, and beside it [stepLabel] -- *Save & complete*, *Save &
/// approve* -- where the user may take that step (D-BUY-22).
///
/// Saving is the filled button and the step the outlined one: the coloured
/// button is the one people press, and pressing it must not post stock or
/// money the user meant only to draft (D-UI-8). Finishing is the deliberate
/// second choice, as in Tally and Zoho.
List<Widget> saveButtons({
  required Key saveKey,
  required String saveLabel,
  required VoidCallback? onSave,
  required Key stepKey,
  required String? stepLabel,
  required VoidCallback? onStep,
}) =>
    [
      if (stepLabel == null)
        FilledButton(key: saveKey, onPressed: onSave, child: Text(saveLabel))
      else ...[
        OutlinedButton(
          key: stepKey,
          onPressed: onStep,
          child: Text(stepLabel),
        ),
        FilledButton(
          key: saveKey,
          onPressed: onSave,
          child: Text(saveLabel),
        ),
      ],
    ];

/// A document window's next steps: the forward ones as buttons, the rest
/// behind "More".
///
/// Only the steps the record allows and the user may take are shown -- a
/// window is not a toolbar that has to keep its shape. A step that succeeds
/// closes the window with a [DocumentStepDone], so the page reads its list
/// again and the document is never shown in a state it has left. A refusal
/// leaves the window open with the server's message: in the window's own
/// banner where [onRefused] is given, under the buttons otherwise.
class DocumentStepStrip<T> extends StatefulWidget {
  const DocumentStepStrip({
    super.key,
    required this.record,
    required this.steps,
    this.onRefused,
    this.enabled = true,
  });

  /// The saved document; null shows nothing, since nothing can act on a
  /// document that is not saved yet.
  final T? record;
  final List<DocumentStep<T>> steps;
  final ValueChanged<String>? onRefused;

  /// False while the window is busy with something else (a save).
  final bool enabled;

  @override
  State<DocumentStepStrip<T>> createState() => _DocumentStepStripState<T>();
}

class _DocumentStepStripState<T> extends State<DocumentStepStrip<T>> {
  bool _running = false;
  String? _refusal;

  Future<void> _run(DocumentStep<T> step) async {
    final T? record = widget.record;
    if (record == null || _running) return;
    setState(() {
      _running = true;
      _refusal = null;
    });
    try {
      final DocumentStepDone? done = await step.run(context, record);
      if (done == null || !mounted) return;
      Navigator.of(context).pop(done);
    } on ApiException catch (error) {
      if (!mounted) return;
      final String message = refusalMessage(error);
      final ValueChanged<String>? onRefused = widget.onRefused;
      if (onRefused != null) {
        onRefused(message);
      } else {
        setState(() => _refusal = message);
      }
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<DocumentStep<T>> open = [
      for (final DocumentStep<T> step in widget.steps)
        if (step.enabledFor(widget.record)) step,
    ];
    if (open.isEmpty) return const SizedBox.shrink();
    final bool live = widget.enabled && !_running;
    final List<DocumentStep<T>> more = [
      for (final DocumentStep<T> step in open)
        if (!step.forward) step,
    ];
    final Widget buttons = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final DocumentStep<T> step in open)
          if (step.forward)
            Padding(
              padding: const EdgeInsets.only(left: 6),
              child: OutlinedButton(
                key: ValueKey<String>('document-step-${step.id}'),
                onPressed: live ? () => unawaited(_run(step)) : null,
                child: Text(step.label),
              ),
            ),
        if (more.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(left: 6),
            child: PopupMenuButton<DocumentStep<T>>(
              key: const ValueKey<String>('document-steps-more'),
              tooltip: 'More steps',
              enabled: live,
              onSelected: (step) => unawaited(_run(step)),
              itemBuilder: (_) => [
                for (final DocumentStep<T> step in more)
                  PopupMenuItem<DocumentStep<T>>(
                    key: ValueKey<String>('document-step-${step.id}'),
                    value: step,
                    child: Row(children: [
                      Icon(step.icon, size: 18),
                      const SizedBox(width: 8),
                      Text(step.label),
                    ]),
                  ),
              ],
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(
                    'More',
                    style: TextStyle(
                      color: live
                          ? Theme.of(context).colorScheme.primary
                          : Theme.of(context).disabledColor,
                    ),
                  ),
                  const Icon(Icons.arrow_drop_down, size: 18),
                ]),
              ),
            ),
          ),
      ],
    );
    final String? refusal = _refusal;
    if (refusal == null) return buttons;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        buttons,
        const SizedBox(height: 4),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Text(
            refusal,
            key: const ValueKey<String>('document-step-refusal'),
            textAlign: TextAlign.end,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ),
      ],
    );
  }
}
