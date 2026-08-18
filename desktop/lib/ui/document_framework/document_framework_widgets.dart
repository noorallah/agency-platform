import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';

enum DocumentToolbarAction {
  newDocument,
  save,
  printDocument,
  exportDocument,
  emailDocument,
  requestApproval,
  approve,
  /// Send the goods. On a delivery note this is what moves the stock, which
  /// is why it is its own action rather than something borrowed: it used to
  /// ride on `requestApproval`, so the button that dispatched a load was
  /// labelled "Request approval".
  dispatch,
  /// Finish the document. Posts stock on a goods receipt, takes it off on a
  /// return.
  complete,
  reject,
  cancel,
  close,
  archive,
}

extension DocumentToolbarActionDetails on DocumentToolbarAction {
  String get label => switch (this) {
        DocumentToolbarAction.newDocument => 'New',
        DocumentToolbarAction.save => 'Save',
        DocumentToolbarAction.printDocument => 'Print',
        DocumentToolbarAction.exportDocument => 'Export',
        DocumentToolbarAction.emailDocument => 'Email',
        DocumentToolbarAction.requestApproval => 'Submit',
        DocumentToolbarAction.approve => 'Approve',
        DocumentToolbarAction.dispatch => 'Dispatch',
        DocumentToolbarAction.complete => 'Complete',
        DocumentToolbarAction.reject => 'Reject',
        DocumentToolbarAction.cancel => 'Cancel',
        DocumentToolbarAction.close => 'Close',
        DocumentToolbarAction.archive => 'Archive',
      };

  IconData get icon => switch (this) {
        DocumentToolbarAction.newDocument => Icons.add,
        DocumentToolbarAction.save => Icons.save_outlined,
        DocumentToolbarAction.printDocument => Icons.print_outlined,
        DocumentToolbarAction.exportDocument => Icons.file_download_outlined,
        DocumentToolbarAction.emailDocument => Icons.email_outlined,
        DocumentToolbarAction.requestApproval => Icons.how_to_reg_outlined,
        DocumentToolbarAction.approve => Icons.check_circle_outline,
        DocumentToolbarAction.dispatch => Icons.local_shipping_outlined,
        DocumentToolbarAction.complete => Icons.task_alt_outlined,
        DocumentToolbarAction.reject => Icons.block_outlined,
        DocumentToolbarAction.cancel => Icons.cancel_outlined,
        DocumentToolbarAction.close => Icons.lock_outline,
        DocumentToolbarAction.archive => Icons.archive_outlined,
      };
}

class EnterpriseDocumentStatusBadge extends StatelessWidget {
  const EnterpriseDocumentStatusBadge({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final String normalized = status.trim().toUpperCase();
    final StatusBadgeTone tone = switch (normalized) {
      'DRAFT' ||
      'PENDING APPROVAL' ||
      'PARTIALLY PROCESSED' =>
        StatusBadgeTone.warning,
      'APPROVED' || 'PROCESSED' || 'COMPLETED' => StatusBadgeTone.success,
      'REJECTED' || 'CANCELLED' => StatusBadgeTone.danger,
      'CLOSED' || 'ARCHIVED' => StatusBadgeTone.neutral,
      _ => StatusBadgeTone.info,
    };
    return StatusBadge(
      label: normalized.replaceAll('_', ' '),
      tone: tone,
    );
  }
}

class EnterpriseDocumentHeader extends StatelessWidget {
  const EnterpriseDocumentHeader({
    super.key,
    required this.header,
    this.leadingActions = const [],
  });

  final DocumentHeaderSnapshot header;
  final List<Widget> leadingActions;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          header.documentNumber,
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Wrap(
                          spacing: AppSpacing.sm,
                          runSpacing: AppSpacing.sm,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(header.documentTypeName),
                            EnterpriseDocumentStatusBadge(
                                status: header.status),
                          ],
                        ),
                      ],
                    ),
                  ),
                  if (leadingActions.isNotEmpty) ...[
                    const SizedBox(width: AppSpacing.lg),
                    Wrap(spacing: AppSpacing.sm, children: leadingActions),
                  ],
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Wrap(
                spacing: AppSpacing.lg,
                runSpacing: AppSpacing.md,
                children: [
                  _headerField('Document date', header.documentDate),
                  _headerField('Reference', header.reference),
                  _headerField('Branch', header.branch),
                  _headerField('Warehouse', header.warehouse),
                  _headerField('Firm', header.firm),
                  _headerField('Business profile', header.businessProfile),
                  _headerField('Currency', header.currency),
                  _headerField('Exchange rate', header.exchangeRate),
                  _headerField('Created by', header.createdBy),
                  _headerField('Approved by', header.approvedBy),
                ],
              ),
              if (header.remarks.trim().isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  header.remarks,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ],
          ),
        ),
      );

  Widget _headerField(String label, String value) => SizedBox(
        width: 220,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 2),
            SelectableText(value.isEmpty ? '-' : value),
          ],
        ),
      );
}

class EnterpriseDocumentLines extends StatelessWidget {
  const EnterpriseDocumentLines({
    super.key,
    required this.lines,
    this.readOnly = true,
    this.onAddLine,
    this.onRemoveLine,
  });

  final List<DocumentLineSnapshot> lines;
  final bool readOnly;
  final VoidCallback? onAddLine;
  final ValueChanged<DocumentLineSnapshot>? onRemoveLine;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Document lines',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  if (!readOnly && onAddLine != null)
                    TextButton.icon(
                      onPressed: onAddLine,
                      icon: const Icon(Icons.add),
                      label: const Text('Add line'),
                    ),
                ],
              ),
              const Divider(),
              if (lines.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
                  child: Text('No document lines.'),
                )
              else
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: DataTable(
                    columns: [
                      const DataColumn(label: Text('#')),
                      const DataColumn(label: Text('Product')),
                      const DataColumn(label: Text('Description')),
                      const DataColumn(label: Text('UOM')),
                      const DataColumn(label: Text('Packaging')),
                      const DataColumn(label: Text('Qty')),
                      const DataColumn(label: Text('Free Qty')),
                      const DataColumn(label: Text('Unit Price')),
                      const DataColumn(label: Text('Discount')),
                      const DataColumn(label: Text('Tax Profile')),
                      const DataColumn(label: Text('Amount')),
                      const DataColumn(label: Text('Net Amount')),
                      const DataColumn(label: Text('Remarks')),
                      if (!readOnly && onRemoveLine != null)
                        const DataColumn(label: Text('')),
                    ],
                    rows: [
                      for (final DocumentLineSnapshot line in lines)
                        DataRow(
                          cells: [
                            DataCell(Text(line.lineNumber.toString())),
                            DataCell(Text(
                                line.product.isEmpty ? '-' : line.product)),
                            DataCell(Text(line.description.isEmpty
                                ? '-'
                                : line.description)),
                            DataCell(Text(line.uom.isEmpty ? '-' : line.uom)),
                            DataCell(Text(
                                line.packaging.isEmpty ? '-' : line.packaging)),
                            DataCell(Text(
                                line.quantity.isEmpty ? '0' : line.quantity)),
                            DataCell(Text(line.freeQuantity.isEmpty
                                ? '0'
                                : line.freeQuantity)),
                            DataCell(Text(
                                line.unitPrice.isEmpty ? '0' : line.unitPrice)),
                            DataCell(Text(
                                line.discount.isEmpty ? '0' : line.discount)),
                            DataCell(Text(line.taxProfile.isEmpty
                                ? '-'
                                : line.taxProfile)),
                            DataCell(
                                Text(line.amount.isEmpty ? '0' : line.amount)),
                            DataCell(Text(
                                line.netAmount.isEmpty ? '0' : line.netAmount)),
                            DataCell(Text(
                                line.remarks.isEmpty ? '-' : line.remarks)),
                            if (!readOnly && onRemoveLine != null)
                              DataCell(
                                IconButton(
                                  tooltip: 'Remove line',
                                  icon: const Icon(Icons.delete_outline),
                                  onPressed: () => onRemoveLine!(line),
                                ),
                              ),
                          ],
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      );
}

class EnterpriseTotalsPanel extends StatelessWidget {
  const EnterpriseTotalsPanel({
    super.key,
    required this.totals,
  });

  final DocumentTotalsSnapshot totals;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Totals', style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              _totalRow('Subtotal', totals.subtotal),
              _totalRow('Discount', totals.discount),
              _totalRow('Tax', totals.tax),
              _totalRow('Charges', totals.charges),
              _totalRow('Round off', totals.roundOff),
              const Divider(),
              _totalRow('Grand total', totals.grandTotal, emphasize: true),
            ],
          ),
        ),
      );

  Widget _totalRow(String label, String value, {bool emphasize = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: emphasize
                    ? const TextStyle(fontWeight: FontWeight.w600)
                    : null,
              ),
            ),
            Text(value.isEmpty ? '0' : value),
          ],
        ),
      );
}

class EnterpriseTimeline extends StatelessWidget {
  const EnterpriseTimeline({
    super.key,
    required this.entries,
    this.emptyMessage = 'No document activity yet.',
  });

  final List<DocumentTimelineSnapshot> entries;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Timeline', style: Theme.of(context).textTheme.titleMedium),
              const Divider(),
              if (entries.isEmpty)
                Text(emptyMessage)
              else
                for (final DocumentTimelineSnapshot entry in entries) ...[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Icon(
                          _iconFor(entry.action),
                          size: 18,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              entry.action,
                              style: Theme.of(context).textTheme.labelLarge,
                            ),
                            if (entry.fromState.isNotEmpty ||
                                entry.toState.isNotEmpty)
                              Text(
                                '${entry.fromState.isEmpty ? '-' : entry.fromState} -> ${entry.toState.isEmpty ? '-' : entry.toState}',
                              ),
                            if (entry.actor.isNotEmpty) Text(entry.actor),
                            if (entry.remarks.isNotEmpty) Text(entry.remarks),
                            Text(entry.occurredAt),
                          ],
                        ),
                      ),
                    ],
                  ),
                  if (entry.details.isNotEmpty) ...[
                    const SizedBox(height: AppSpacing.xs),
                    Text(entry.details.toString()),
                  ],
                  const SizedBox(height: AppSpacing.md),
                ],
            ],
          ),
        ),
      );

  IconData _iconFor(String action) {
    final String normalized = action.trim().toUpperCase();
    return switch (normalized) {
      'CREATED' => Icons.add_circle_outline,
      'EDITED' => Icons.edit_outlined,
      'STATUS CHANGED' || 'APPROVED' || 'REJECTED' => Icons.history,
      'PRINTED' => Icons.print_outlined,
      'EXPORTED' => Icons.file_download_outlined,
      'CANCELLED' => Icons.cancel_outlined,
      'ARCHIVED' => Icons.archive_outlined,
      _ => Icons.timeline_outlined,
    };
  }
}

class EnterpriseDocumentToolbar extends StatelessWidget {
  const EnterpriseDocumentToolbar({
    super.key,
    required this.onAction,
    required this.isEnabled,
    this.actions = const [
      DocumentToolbarAction.newDocument,
      DocumentToolbarAction.save,
      DocumentToolbarAction.printDocument,
      DocumentToolbarAction.exportDocument,
      DocumentToolbarAction.emailDocument,
      DocumentToolbarAction.requestApproval,
      DocumentToolbarAction.approve,
      DocumentToolbarAction.reject,
      DocumentToolbarAction.cancel,
      DocumentToolbarAction.close,
      DocumentToolbarAction.archive,
    ],
  });

  final ValueChanged<DocumentToolbarAction> onAction;
  final bool Function(DocumentToolbarAction) isEnabled;
  final List<DocumentToolbarAction> actions;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          for (final DocumentToolbarAction action in actions)
            Tooltip(
              message: action.label,
              child: action == DocumentToolbarAction.save ||
                      action == DocumentToolbarAction.newDocument
                  ? FilledButton.icon(
                      onPressed:
                          isEnabled(action) ? () => onAction(action) : null,
                      icon: Icon(action.icon),
                      label: Text(action.label),
                    )
                  : OutlinedButton.icon(
                      onPressed:
                          isEnabled(action) ? () => onAction(action) : null,
                      icon: Icon(action.icon),
                      label: Text(action.label),
                    ),
            ),
        ],
      );
}

class EnterpriseApprovalPanel extends StatelessWidget {
  const EnterpriseApprovalPanel({
    super.key,
    required this.status,
    this.message = 'Approval workflow placeholder.',
    this.actions = const [],
  });

  final String status;
  final String message;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Card(
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Approval',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  EnterpriseDocumentStatusBadge(status: status),
                ],
              ),
              const Divider(),
              Text(message),
              if (actions.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                Wrap(spacing: AppSpacing.sm, children: actions),
              ],
            ],
          ),
        ),
      );
}
