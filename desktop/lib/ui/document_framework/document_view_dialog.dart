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
/// This viewer stays read-only because the six screens that use it have not
/// been given the same treatment yet, not because they should not be. Three
/// things have to be settled first: `GoodsReceiptViewDialog` is a second copy
/// of this widget and would need the same slot; sales orders and sales
/// invoices run a credit-exposure warning before Approve, which from in here
/// would be a dialog over a dialog; and the goods receipt page has no
/// permission check on its lifecycle buttons at all. Until then, those six act
/// from the workspace toolbar.
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
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final DocumentHeaderSnapshot header;
  final List<DocumentLineSnapshot> lines;
  final DocumentTotalsSnapshot totals;
  final List<DocumentTimelineSnapshot> history;

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
              EnterpriseDocumentHeader(header: header),
              const SizedBox(height: 12),
              EnterpriseDocumentLines(lines: lines),
              const SizedBox(height: 12),
              EnterpriseTotalsPanel(totals: totals),
              const SizedBox(height: 12),
              EnterpriseTimeline(entries: history),
            ],
          ),
        ),
        onClose: () => Navigator.of(context).pop(),
      );
}
