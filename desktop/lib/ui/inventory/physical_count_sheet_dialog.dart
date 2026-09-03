import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/physical_count.dart';
import '../workspace/desktop_framework.dart';

/// Open a sheet over a warehouse.
///
/// Naming no products counts the whole warehouse, which is what a counter
/// walks out with; the sheet is drawn up from what the system currently holds.
class OpenCountDialog extends StatefulWidget {
  const OpenCountDialog({
    super.key,
    required this.branches,
    required this.warehouses,
  });

  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;

  @override
  State<OpenCountDialog> createState() => _OpenCountDialogState();
}

class _OpenCountDialogState extends State<OpenCountDialog> {
  String _branchId = '';
  String _warehouseId = '';
  DateTime _when = DateTime.now();
  String _remarks = '';
  String? _error;

  @override
  void initState() {
    super.initState();
    _branchId = widget.branches.isEmpty ? '' : widget.branches.first.id;
    _warehouseId = widget.warehouses.isEmpty ? '' : widget.warehouses.first.id;
  }

  void _save() {
    if (_branchId.isEmpty || _warehouseId.isEmpty) {
      setState(() => _error = 'Choose the branch and warehouse being counted.');
      return;
    }
    Navigator.of(context).pop(<String, dynamic>{
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'count_date': _when.toIso8601String().substring(0, 10),
      if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
    });
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'Open a count',
        subtitle: 'The sheet is drawn up from what the warehouse holds now.',
        onClose: () => Navigator.of(context).pop(),
        onSave: _save,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
              ),
            Row(children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _branchId.isEmpty ? null : _branchId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Branch'),
                  items: [
                    for (final BranchRecord branch in widget.branches)
                      DropdownMenuItem<String>(
                        value: branch.id,
                        child: Text(branch.name, overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: (value) => setState(() => _branchId = value ?? ''),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: DropdownButtonFormField<String>(
                  initialValue: _warehouseId.isEmpty ? null : _warehouseId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Warehouse'),
                  items: [
                    for (final WarehouseRecord warehouse in widget.warehouses)
                      DropdownMenuItem<String>(
                        value: warehouse.id,
                        child:
                            Text(warehouse.name, overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: (value) => setState(() => _warehouseId = value ?? ''),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              SizedBox(
                width: 220,
                child: InkWell(
                  onTap: () async {
                    final DateTime? picked = await showDatePicker(
                      context: context,
                      initialDate: _when,
                      firstDate: DateTime(2000),
                      lastDate: DateTime(2100),
                    );
                    if (picked != null) setState(() => _when = picked);
                  },
                  child: InputDecorator(
                    decoration: const InputDecoration(
                      labelText: 'Count date',
                      suffixIcon: Icon(Icons.calendar_today, size: 18),
                    ),
                    child: Text(_when.toIso8601String().substring(0, 10)),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextField(
                  decoration: const InputDecoration(labelText: 'Remarks'),
                  onChanged: (value) => _remarks = value,
                ),
              ),
            ]),
          ],
        ),
      );
}

/// Fill in a sheet, and post it when the walking is done.
///
/// Saving and posting are separate on purpose. A count is walked over hours,
/// so what has been found so far belongs on the server rather than in a form
/// somebody might close; posting is the irreversible step that writes the
/// adjustments.
class PhysicalCountSheetDialog extends StatefulWidget {
  const PhysicalCountSheetDialog({
    super.key,
    required this.api,
    required this.sheet,
    required this.canCount,
  });

  final ApiClient api;
  final PhysicalCountSheet sheet;
  final bool canCount;

  @override
  State<PhysicalCountSheetDialog> createState() =>
      _PhysicalCountSheetDialogState();
}

class _PhysicalCountSheetDialogState extends State<PhysicalCountSheetDialog> {
  final Map<String, TextEditingController> _counted = {};
  late PhysicalCountSheet _sheet;
  bool _busy = false;
  bool _changed = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _sheet = widget.sheet;
    for (final PhysicalCountLine line in _sheet.lines) {
      _counted[line.id] = TextEditingController(text: line.countedQuantity);
    }
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _counted.values) {
      controller.dispose();
    }
    super.dispose();
  }

  /// What has been typed, as the request body.
  ///
  /// A line left blank is sent as no count rather than as zero: an uncounted
  /// line is not a line that found nothing, and the server skips it when the
  /// sheet is posted.
  Json _body() => <String, dynamic>{
        'lines': [
          for (final PhysicalCountLine line in _sheet.lines)
            <String, dynamic>{
              'product_id': line.productId,
              if (line.batchId.isNotEmpty) 'batch_id': line.batchId,
              if ((_counted[line.id]?.text.trim() ?? '').isNotEmpty)
                'counted_quantity': _counted[line.id]!.text.trim(),
            },
        ],
      };

  Future<void> _save({bool thenPost = false}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      PhysicalCountSheet updated =
          await widget.api.recordPhysicalCount(_sheet.id, _body());
      if (thenPost) {
        updated = await widget.api.postPhysicalCount(_sheet.id);
      }
      if (!mounted) return;
      _changed = true;
      setState(() => _sheet = updated);
      if (thenPost) Navigator.of(context).pop(true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// How many lines have something typed against them.
  int _countedSoFar() =>
      _counted.values.where((c) => c.text.trim().isNotEmpty).length;

  /// Abandon a sheet that will not be posted.
  ///
  /// `cancelPhysicalCount` had a route and a client method and no control, so
  /// a sheet opened by mistake -- or against the wrong warehouse -- stayed
  /// DRAFT for ever, holding a warehouse's expected quantities from whenever
  /// it was drawn up and cluttering the list it appears in.
  ///
  /// Confirmed first, and the confirmation says what is lost: the counting
  /// itself. Nothing about the sheet reaches stock until it is posted, so
  /// abandoning it moves no quantity and writes no adjustment -- but a
  /// half-counted sheet represents somebody's afternoon in the aisles.
  Future<void> _abandon() async {
    final int counted = _countedSoFar();
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Abandon ${_sheet.countNumber}?',
      message: counted == 0
          ? 'The sheet is dropped. No stock moves and no adjustment is '
              'written — nothing on a sheet reaches the ledger until it is '
              'posted.'
          : '$counted counted line(s) are dropped with it, and cannot be got '
              'back. No stock moves and no adjustment is written.',
      confirmLabel: 'Abandon',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.cancelPhysicalCount(_sheet.id);
      if (!mounted) return;
      _changed = true;
      Navigator.of(context).pop(true);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _busy = false;
      });
    }
  }

  Future<void> _confirmPost() async {
    final int uncounted = _sheet.lines.length - _countedSoFar();
    final bool? go = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Post ${_sheet.countNumber}'),
        content: SizedBox(
          width: 460,
          child: Text(
            uncounted == 0
                ? 'Every difference becomes a stock adjustment, and adjustments '
                    'reach the ledger. A posted sheet cannot be changed.'
                : '$uncounted line(s) have not been counted and will be left '
                    'alone -- a line nobody walked is not a line that found '
                    'nothing. Everything counted becomes a stock adjustment, '
                    'and a posted sheet cannot be changed.',
            style: Theme.of(dialogContext).textTheme.bodyMedium,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Post count'),
          ),
        ],
      ),
    );
    if (go == true) await _save(thenPost: true);
  }

  @override
  Widget build(BuildContext context) {
    final bool editable = _sheet.isDraft && widget.canCount;
    return WorkspaceDialog(
      title: _sheet.countNumber,
      subtitle: _sheet.isPosted
          ? 'Posted. The differences are in the ledger.'
          : '${_sheet.countDate} · ${_sheet.lines.length} lines',
      loading: _busy,
      onClose: () => Navigator.of(context).pop(_changed),
      onSave: editable && !_busy ? () => unawaited(_save()) : null,
      // Both actions are visible buttons. `onSave` alone is a keyboard
      // shortcut, and a sheet somebody fills in over hours needs a Save they
      // can see -- losing an afternoon of counting to an unknown shortcut is
      // the failure this screen exists to avoid.
      footer: editable
          ? Row(children: [
              Text(
                '${_countedSoFar()} of ${_sheet.lines.length} counted',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(width: AppSpacing.md),
              // Left of the spacer, away from the two actions that commit:
              // abandoning and posting are the two irreversible things this
              // dialog does, and they should not sit next to each other.
              TextButton.icon(
                onPressed: _busy ? null : () => unawaited(_abandon()),
                icon: const Icon(Icons.cancel_outlined, size: 18),
                label: const Text('Abandon sheet'),
              ),
              const Spacer(),
              OutlinedButton.icon(
                onPressed: _busy ? null : () => unawaited(_save()),
                icon: const Icon(Icons.save_outlined),
                label: const Text('Save progress'),
              ),
              const SizedBox(width: AppSpacing.md),
              FilledButton.icon(
                onPressed: _busy ? null : () => unawaited(_confirmPost()),
                icon: const Icon(Icons.done_all),
                label: const Text('Post count'),
              ),
            ])
          : null,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: MaterialBanner(
                content: Text(_error!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _error = null),
                    child: const Text('Dismiss'),
                  ),
                ],
              ),
            ),
          Text(
            'Expected is what the system held when the sheet was drawn up. The '
            'difference is measured again when it is posted, because stock '
            'moves while a warehouse is being counted.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          Expanded(child: _table(context, editable)),
        ],
      ),
    );
  }

  Widget _table(BuildContext context, bool editable) => SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: const [
              DataColumn(label: Text('#')),
              DataColumn(label: Text('Product')),
              DataColumn(label: Text('Expected'), numeric: true),
              DataColumn(label: Text('Counted'), numeric: true),
              DataColumn(label: Text('Difference'), numeric: true),
            ],
            rows: [
              for (final PhysicalCountLine line in _sheet.lines)
                DataRow(cells: [
                  DataCell(Text('${line.lineNumber}')),
                  DataCell(
                    SizedBox(
                      width: 260,
                      child: Text(
                        line.productId,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                  DataCell(Text(line.expectedQuantity)),
                  DataCell(
                    SizedBox(
                      width: 120,
                      child: TextField(
                        controller: _counted[line.id],
                        enabled: editable,
                        textAlign: TextAlign.right,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(isDense: true),
                        onChanged: (_) => setState(() {}),
                      ),
                    ),
                  ),
                  // Shown while the sheet is filled in, so a fat-fingered
                  // digit is visible before it posts rather than after.
                  DataCell(Text(
                    _sheet.isPosted
                        ? line.varianceQuantity
                        : _draftDifference(line),
                  )),
                ]),
            ],
          ),
        ),
      );

  String _draftDifference(PhysicalCountLine line) {
    final String typed = _counted[line.id]?.text.trim() ?? '';
    if (typed.isEmpty) return '';
    final double counted = double.tryParse(typed) ?? 0;
    final double expected = double.tryParse(line.expectedQuantity) ?? 0;
    final double difference = counted - expected;
    if (difference == 0) return '—';
    return difference > 0
        ? '+${difference.toStringAsFixed(4)}'
        : difference.toStringAsFixed(4);
  }
}
