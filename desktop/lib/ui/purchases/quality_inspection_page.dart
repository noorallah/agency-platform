// The quality inspection hold (BUY-9): receipt lines whose product, or whose
// category, is marked "inspect on receipt" wait in quarantine here until
// somebody passes them. Rejected goods are written off at once or kept for
// return to the supplier. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/quality_inspection.dart';
import '../workspace/desktop_framework.dart';

/// List the goods held for inspection and pass or reject them.
class QualityInspectionPage extends StatefulWidget {
  const QualityInspectionPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<QualityInspectionPage> createState() => _QualityInspectionPageState();
}

class _QualityInspectionPageState extends State<QualityInspectionPage> {
  List<QualityInspection> _rows = const [];
  String? _error;
  String? _selectedKey;
  bool _loading = true;
  String _status = 'PENDING';

  bool get _mayView =>
      widget.permissions.hasPermission('PURCHASE_VIEW') ||
      widget.permissions.hasPermission('PURCHASE_INSPECT');
  bool get _mayInspect => widget.permissions.hasPermission('PURCHASE_INSPECT');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<QualityInspection> rows =
          await widget.api.listQualityInspections(status: _status);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  QualityInspection? get _selected =>
      _rows.where((row) => row.key == _selectedKey).firstOrNull;

  Future<void> _inspect(QualityInspection row) async {
    final QualityInspection? saved = await showDialog<QualityInspection>(
      context: context,
      barrierDismissible: false,
      builder: (_) => InspectGoodsDialog(api: widget.api, row: row),
    );
    if (saved == null || !mounted) return;
    NotificationService.show(
      context,
      '${row.productName} on ${row.grnNumber} — inspected.',
      kind: AppNotificationKind.success,
    );
    setState(() => _selectedKey = null);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Inspections belong to one firm’s receipts.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see inspections',
        message: 'Reading them needs the view purchases permission.',
      );
    }
    final QualityInspection? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Goods marked “inspect on receipt” wait here, out of stock, '
          'until they are passed. Pass what is good; rejected goods are '
          'written off now or kept to return to the supplier.',
      toolbar: _toolbar(picked),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.grnNumber,
              party: picked.vendorName,
              status: picked.status,
              onClear: () => setState(() => _selectedKey = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedKey != null,
        message: _status == 'PENDING' ? 'Pending inspections' : 'Inspected',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _grid()),
      ],
    );
  }

  WorkspaceToolbar _toolbar(QualityInspection? selected) {
    final bool canInspect =
        selected != null && selected.isPending && _mayInspect;
    return WorkspaceToolbar(
      trailing: [
        Phase2MenuChip<String>(
          key: const ValueKey('inspection-status-filter'),
          label: 'Show: ${_status == 'PENDING' ? 'Pending' : 'Done'}',
          itemBuilder: (_) => const [
            PopupMenuItem<String>(value: 'PENDING', child: Text('Pending')),
            PopupMenuItem<String>(value: 'DONE', child: Text('Done')),
          ],
          onSelected: (value) {
            setState(() {
              _status = value;
              _selectedKey = null;
            });
            unawaited(_load());
          },
        ),
        ColumnsButton(
          onPressed: () async {
            if (await _columns.choose(context) && mounted) setState(() {});
          },
        ),
      ],
      actions: const [ToolbarAction.refresh],
      isEnabled: (action) => true,
      onAction: (action) => unawaited(_load()),
      commands: [
        if (_mayInspect)
          ToolbarCommand(
            id: 'inspect',
            label: 'Inspect',
            icon: Icons.fact_check_outlined,
            onPressed: canInspect ? () => unawaited(_inspect(selected)) : null,
          ),
      ],
    );
  }

  late final ColumnChoice<QualityInspection> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'quality-inspection.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Received'),
        cell: (item) => item.receiptDate,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'grn', label: 'Receipt'),
        cell: (item) => item.grnNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'vendor', label: 'Supplier', priority: 1),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'product', label: 'Product'),
        cell: (item) => item.productName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'batch', label: 'Batch', priority: 1),
        cell: (item) => item.batchNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'qty', label: 'Quantity', numeric: true),
        cell: (item) => _qty(item.quantity),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'passed', label: 'Passed', numeric: true),
        cell: (item) => item.isPending ? '' : _qty(item.passedQuantity),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column:
            const GridColumn(key: 'rejected', label: 'Rejected', numeric: true),
        cell: (item) => item.isPending ? '' : _qty(item.rejectedQuantity),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'action', label: 'Rejected goods'),
        cell: (item) => _actionLabel(item.rejectedAction),
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _status == 'PENDING'
            ? 'Nothing is waiting for inspection'
            : 'Nothing has been inspected yet',
        message: 'Mark a product or a category “inspect on receipt” and its '
            'received goods wait here until they are passed.',
      );
    }
    return EnterpriseDataGrid<QualityInspection>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedKey,
      columns: _columns.gridColumns,
      id: (row) => row.key,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedKey = row.key),
      onOpen: (row) => setState(() => _selectedKey = row.key),
      onPageChanged: (_) {},
    );
  }
}

/// A quantity without the trailing zeros the API answers with.
String _qty(String value) {
  final double? parsed = double.tryParse(value);
  if (parsed == null) return value;
  final String text = parsed.toStringAsFixed(3);
  return text.replaceFirst(RegExp(r'\.?0+$'), '');
}

String _actionLabel(String action) => switch (action) {
      'WRITE_OFF' => 'Written off',
      'RETURN' => 'Kept for return',
      _ => '',
    };

/// Pass and reject the quantity on one line. Pops the saved
/// [QualityInspection]; stays open with the server's message when refused.
class InspectGoodsDialog extends StatefulWidget {
  const InspectGoodsDialog({super.key, required this.api, required this.row});

  final ApiClient api;
  final QualityInspection row;

  @override
  State<InspectGoodsDialog> createState() => _InspectGoodsDialogState();
}

class _InspectGoodsDialogState extends State<InspectGoodsDialog>
    with SaveInDialog {
  // A quantity, not a discount: the full receipt is the sensible start.
  late final TextEditingController _passed =
      TextEditingController(text: _qty(widget.row.quantity));
  final TextEditingController _rejected = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  String? _action;
  String? _problem;

  @override
  void dispose() {
    _passed.dispose();
    _rejected.dispose();
    _remarks.dispose();
    super.dispose();
  }

  void _save() {
    final double? passed = double.tryParse(_passed.text.trim());
    final String rejectedText = _rejected.text.trim();
    final double? rejected =
        rejectedText.isEmpty ? 0 : double.tryParse(rejectedText);
    String? problem;
    if (passed == null || passed < 0 || rejected == null || rejected < 0) {
      problem = 'Passed and rejected are quantities of zero or more.';
    } else if (rejected > 0 && _action == null) {
      problem = 'Say what happens to the rejected goods.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<QualityInspection>(
      () => widget.api.inspectGoodsReceiptLine(
        receiptId: widget.row.goodsReceiptId,
        lineId: widget.row.lineId,
        body: <String, dynamic>{
          'passed_quantity': _passed.text.trim(),
          'rejected_quantity': rejectedText.isEmpty ? '0' : rejectedText,
          'rejected_action': rejected! > 0 ? _action : null,
          'remarks': remarks.isEmpty ? null : remarks,
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final QualityInspection row = widget.row;
    return AlertDialog(
      title: Text('Inspect ${row.productName}'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(
                    _problem!,
                    key: const ValueKey('inspection-problem'),
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              Text(
                '${row.grnNumber} · ${row.vendorName} · '
                '${_qty(row.quantity)} received',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('inspection-passed'),
                    controller: _passed,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Passed qty'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    key: const ValueKey('inspection-rejected'),
                    controller: _rejected,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration:
                        const InputDecoration(labelText: 'Rejected qty'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                key: const ValueKey('inspection-action'),
                initialValue: _action,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Rejected goods',
                  helperText: 'Required when something is rejected.',
                ),
                items: const [
                  DropdownMenuItem(
                      value: 'WRITE_OFF', child: Text('Write off now')),
                  DropdownMenuItem(
                      value: 'RETURN',
                      child: Text('Keep for return to supplier')),
                ],
                onChanged: saving ? null : (v) => setState(() => _action = v),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('inspection-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('inspection-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save inspection'),
        ),
      ],
    );
  }
}
