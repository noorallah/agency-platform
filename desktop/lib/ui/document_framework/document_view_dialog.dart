import 'package:flutter/material.dart';

import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';
import 'document_framework_widgets.dart';

/// One document: its header, its lines, its totals and its timeline.
///
/// Purchase orders, goods receipts, purchase invoices and purchase returns all
/// pinned this beside their list — typically at `flex: 4` against a `flex: 3`
/// list, so the preview of the record pointed at had *more* room than every
/// record. It is a dialog now, opened by double-click, which gives the table
/// the whole width and the document room to be read.
///
/// Still read-only, but no longer on the grounds it used to claim. This said
/// "a document that can be acted on from two places is a document somebody
/// acts on twice", which was over-cautious: purchase orders offer Submit and
/// Approve inside their own editor dialog as of 2026-08-18, and the double
/// action cannot happen because the dialog holds the **returned** document and
/// re-gates every button on it -- Submit stops being pressable the instant the
/// order stops being a draft, and the server is authoritative either way.
///
/// Since D-BUY-22 the screens that use it pass their document's next steps
/// in [steps] -- a [DocumentStepStrip] built from the same definitions as
/// their toolbar, so the permission code and the status gate are the
/// toolbar's. A sales order's or invoice's credit warning before Approve is
/// a dialog over this one, which is acceptable; a step that succeeds closes
/// this viewer so the list reads itself again.
///
/// Generic because the four documents differ only in what they call their
/// number: each page already builds these snapshots for the pane this
/// replaces.
class DocumentViewDialog extends StatelessWidget {
  const DocumentViewDialog({
    super.key,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.header,
    required this.lines,
    required this.totals,
    required this.history,
    this.extra,
    this.steps,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final DocumentHeaderSnapshot header;
  final List<DocumentLineSnapshot> lines;
  final DocumentTotalsSnapshot totals;
  final List<DocumentTimelineSnapshot> history;

  /// Anything else this particular document has to say, shown with its
  /// totals. A slot rather than a screen-specific field, because the money
  /// that matters about a document is not always on the document.
  final Widget? extra;

  /// The document's next steps: a [DocumentStepStrip] the page builds from
  /// the same definitions as its toolbar (D-BUY-22).
  final Widget? steps;

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: title,
        subtitle: subtitle,
        icon: icon,
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (steps != null)
                Align(alignment: Alignment.centerRight, child: steps),
              EnterpriseDocumentHeader(header: header, history: history),
              const SizedBox(height: 12),
              EnterpriseDocumentLines(lines: lines),
              const SizedBox(height: 12),
              EnterpriseTotalsPanel(totals: totals),
              if (extra != null) ...[
                const SizedBox(height: 12),
                extra!,
              ],
              const SizedBox(height: 12),
              EnterpriseTimeline(entries: history),
            ],
          ),
        ),
        onClose: () => Navigator.of(context).pop(),
      );
}
