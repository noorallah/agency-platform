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
/// Read-only on purpose. Approve, cancel, complete and close act on the
/// selected row from the workspace toolbar; a document that can be acted on
/// from two places is a document somebody acts on twice.
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
