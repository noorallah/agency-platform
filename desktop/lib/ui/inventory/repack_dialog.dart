import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../workspace/save_in_dialog.dart';

/// A choice in one of the repack dialog's pickers: an id and how it reads.
class RepackOption {
  const RepackOption({required this.id, required this.label, this.parentId});

  final String id;
  final String label;

  /// For a warehouse, the branch it belongs to.
  final String? parentId;
}

class _LineDraft {
  _LineDraft();

  String? productId;
  final TextEditingController quantity = TextEditingController();

  void dispose() => quantity.dispose();
}

/// Post a repack or bulk-breaking document (STK-4): what is consumed, what is
/// produced, and the wastage the produced stock's value is stated net of.
///
/// The dialog runs the save itself through [onSave] and stays open with the
/// server's refusal (D-DLG-1).
class RepackDialog extends StatefulWidget {
  const RepackDialog({
    super.key,
    required this.branches,
    required this.warehouses,
    required this.products,
    required this.onSave,
  });

  final List<RepackOption> branches;
  final List<RepackOption> warehouses;
  final List<RepackOption> products;

  /// Posts the body; a refusal is an `ApiException` the dialog shows.
  final Future<void> Function(Json body) onSave;

  @override
  State<RepackDialog> createState() => _RepackDialogState();
}

class _RepackDialogState extends State<RepackDialog> with SaveInDialog {
  final TextEditingController _wastage = TextEditingController(text: '0');
  final TextEditingController _remarks = TextEditingController();
  final List<_LineDraft> _consume = [_LineDraft()];
  final List<_LineDraft> _produce = [_LineDraft()];
  DateTime _when = DateTime.now();
  String? _branchId;
  String? _warehouseId;
  String? _problem;

  @override
  void initState() {
    super.initState();
    if (widget.branches.length == 1) _branchId = widget.branches.first.id;
    _keepWarehouseInBranch();
  }

  @override
  void dispose() {
    _wastage.dispose();
    _remarks.dispose();
    for (final _LineDraft line in [..._consume, ..._produce]) {
      line.dispose();
    }
    super.dispose();
  }

  List<RepackOption> get _warehousesHere => [
        for (final RepackOption warehouse in widget.warehouses)
          if (_branchId == null ||
              warehouse.parentId == null ||
              warehouse.parentId == _branchId)
            warehouse,
      ];

  void _keepWarehouseInBranch() {
    final List<RepackOption> here = _warehousesHere;
    if (!here.any((warehouse) => warehouse.id == _warehouseId)) {
      _warehouseId = here.length == 1 ? here.first.id : null;
    }
  }

  List<Json> _linesOf(String kind, List<_LineDraft> drafts) => [
        for (final _LineDraft draft in drafts)
          if (draft.productId != null || draft.quantity.text.trim().isNotEmpty)
            <String, dynamic>{
              'kind': kind,
              'product_id': draft.productId,
              'quantity': draft.quantity.text.trim(),
            },
      ];

  String? _validate(List<Json> consume, List<Json> produce) {
    if (_branchId == null) return 'Choose the branch.';
    if (_warehouseId == null) return 'Choose the warehouse.';
    final double? wastage = double.tryParse(_wastage.text.trim());
    if (wastage == null || wastage < 0 || wastage >= 100) {
      return 'Wastage is a percentage from 0 up to, but not including, 100.';
    }
    if (consume.isEmpty) return 'Add at least one product to consume.';
    if (produce.isEmpty) return 'Add at least one product to produce.';
    for (final Json line in [...consume, ...produce]) {
      if (line['product_id'] == null) return 'Choose a product on every line.';
      final double? quantity = double.tryParse('${line['quantity']}');
      if (quantity == null || quantity <= 0) {
        return 'Enter a quantity above zero on every line.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final List<Json> consume = _linesOf('CONSUME', _consume);
    final List<Json> produce = _linesOf('PRODUCE', _produce);
    final String? problem = _validate(consume, produce);
    setState(() {
      _problem = problem;
      saveError = null;
    });
    if (problem != null) return;
    final Json body = <String, dynamic>{
      'repack_date': _when.toIso8601String().substring(0, 10),
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'wastage_percent': _wastage.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [...consume, ...produce],
    };
    await submit<Json>(body, widget.onSave);
  }

  Widget _lineEditor(String title, List<_LineDraft> drafts, String keyPrefix) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: Text(title, style: Theme.of(context).textTheme.titleSmall),
          ),
          TextButton.icon(
            key: ValueKey('$keyPrefix-add'),
            onPressed:
                saving ? null : () => setState(() => drafts.add(_LineDraft())),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add line'),
          ),
        ]),
        for (int index = 0; index < drafts.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('$keyPrefix-product-$index'),
                    isExpanded: true,
                    initialValue: drafts[index].productId,
                    decoration: const InputDecoration(labelText: 'Product'),
                    items: [
                      for (final RepackOption product in widget.products)
                        DropdownMenuItem(
                          value: product.id,
                          child: Text(
                            product.label,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) =>
                            setState(() => drafts[index].productId = value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 120,
                  child: TextField(
                    key: ValueKey('$keyPrefix-quantity-$index'),
                    controller: drafts[index].quantity,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Quantity'),
                    keyboardType: TextInputType.number,
                  ),
                ),
                IconButton(
                  tooltip: 'Remove line',
                  onPressed: saving || drafts.length == 1
                      ? null
                      : () => setState(() {
                            drafts.removeAt(index).dispose();
                          }),
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('New repack'),
      content: SizedBox(
        width: 720,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(_problem!, style: TextStyle(color: colors.error)),
                ),
              Row(children: [
                Expanded(
                  child: InkWell(
                    onTap: saving
                        ? null
                        : () async {
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
                        labelText: 'Date',
                        suffixIcon: Icon(Icons.calendar_today, size: 18),
                      ),
                      child: Text(_when.toIso8601String().substring(0, 10)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    key: const ValueKey('repack-wastage'),
                    controller: _wastage,
                    enabled: !saving,
                    decoration: const InputDecoration(
                      labelText: 'Wastage %',
                      helperText: 'Lost in the work',
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('repack-branch'),
                    isExpanded: true,
                    initialValue: _branchId,
                    decoration: const InputDecoration(labelText: 'Branch'),
                    items: [
                      for (final RepackOption branch in widget.branches)
                        DropdownMenuItem(
                          value: branch.id,
                          child: Text(branch.label,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() {
                              _branchId = value;
                              _keepWarehouseInBranch();
                            }),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('repack-warehouse-$_branchId'),
                    isExpanded: true,
                    initialValue: _warehouseId,
                    decoration: const InputDecoration(labelText: 'Warehouse'),
                    items: [
                      for (final RepackOption warehouse in _warehousesHere)
                        DropdownMenuItem(
                          value: warehouse.id,
                          child: Text(warehouse.label,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() => _warehouseId = value),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              _lineEditor('Consume', _consume, 'repack-consume'),
              const SizedBox(height: AppSpacing.md),
              _lineEditor('Produce', _produce, 'repack-produce'),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'The consumed stock leaves at its own value and the produced '
                'stock arrives carrying it, less the wastage.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('repack-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Posting...' : 'Post repack'),
        ),
      ],
    );
  }
}
