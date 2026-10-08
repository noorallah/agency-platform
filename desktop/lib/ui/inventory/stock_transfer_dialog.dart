import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';
import '../../models/stock_transfer.dart';
import '../workspace/save_in_dialog.dart';
import '../workspace/serial_pick_chips.dart';

/// A choice in one of the transfer dialog's pickers: an id and how it reads.
class TransferOption {
  const TransferOption({
    required this.id,
    required this.label,
    this.trackSerial = false,
  });

  final String id;
  final String label;

  /// Whether the product carries a serial number on every unit.
  final bool trackSerial;
}

class _LineDraft {
  _LineDraft();

  String? productId;
  String? batchId;
  List<TransferOption> batches = const [];
  bool serialTracked = false;
  List<String> serialIds = [];
  List<PickedSerial> onShelf = const [];
  final TextEditingController quantity = TextEditingController();

  void dispose() => quantity.dispose();
}

/// Write or change a draft stock transfer (STK-1): the two warehouses, the
/// vehicle, and the lines to move. Nothing leaves the source until the draft
/// is dispatched.
///
/// The dialog runs the save itself through [onSave] and stays open with the
/// server's refusal (D-DLG-1). Pass [existing] to edit a draft.
class StockTransferDialog extends StatefulWidget {
  const StockTransferDialog({
    super.key,
    required this.warehouses,
    required this.products,
    required this.onSave,
    this.existing,
    this.loadBatches,
    this.loadSerials,
  });

  final List<TransferOption> warehouses;
  final List<TransferOption> products;
  final StockTransferRecord? existing;

  /// The AVAILABLE serials of a product in a warehouse; null hides the
  /// picker.
  final Future<List<PickedSerial>> Function(
    String productId,
    String warehouseId,
  )? loadSerials;

  /// Batches of a product in a warehouse; null hides the batch box.
  final Future<List<TransferOption>> Function(
    String productId,
    String warehouseId,
  )? loadBatches;

  /// Saves the body; a refusal is an `ApiException` the dialog shows.
  final Future<void> Function(Json body) onSave;

  @override
  State<StockTransferDialog> createState() => _StockTransferDialogState();
}

class _StockTransferDialogState extends State<StockTransferDialog>
    with SaveInDialog {
  final TextEditingController _vehicle = TextEditingController();
  final TextEditingController _transporter = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  final List<_LineDraft> _lines = [];
  DateTime _when = DateTime.now();
  String? _fromId;
  String? _toId;
  String? _problem;

  @override
  void initState() {
    super.initState();
    final StockTransferRecord? existing = widget.existing;
    if (existing == null) {
      _lines.add(_LineDraft());
      return;
    }
    _when = DateTime.tryParse(existing.transferDate) ?? _when;
    _fromId = existing.fromWarehouseId;
    _toId = existing.toWarehouseId;
    _vehicle.text = existing.vehicleNumber;
    _transporter.text = existing.transporterName;
    _remarks.text = existing.remarks;
    for (final StockTransferLineRecord line in existing.lines) {
      final _LineDraft draft = _LineDraft()
        ..productId = line.productId
        ..quantity.text = line.quantity
        ..serialTracked = line.serialTracked
        ..serialIds = [for (final PickedSerial s in line.serials) s.id]
        ..onShelf = line.serials;
      if (line.batchId.isNotEmpty) {
        draft.batchId = line.batchId;
        draft.batches = [
          TransferOption(id: line.batchId, label: line.batchNumber),
        ];
      }
      _lines.add(draft);
    }
    if (_lines.isEmpty) _lines.add(_LineDraft());
    for (final _LineDraft draft in _lines) {
      _refreshSerials(draft);
    }
  }

  @override
  void dispose() {
    _vehicle.dispose();
    _transporter.dispose();
    _remarks.dispose();
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  Future<void> _productChosen(_LineDraft draft, String? productId) async {
    setState(() {
      draft.productId = productId;
      draft.batchId = null;
      draft.batches = const [];
      draft.serialTracked = widget.products
          .any((product) => product.id == productId && product.trackSerial);
      draft.serialIds = [];
      draft.onShelf = const [];
    });
    await _refreshBatches(draft);
    await _refreshSerials(draft);
  }

  /// Read the units on the source shelf for a serial-tracked line. The ones the
  /// saved draft already names stay offered even if the read fails.
  Future<void> _refreshSerials(_LineDraft draft) async {
    final String? productId = draft.productId;
    final String? fromId = _fromId;
    final loader = widget.loadSerials;
    if (loader == null ||
        !draft.serialTracked ||
        productId == null ||
        fromId == null) {
      return;
    }
    List<PickedSerial> found = const [];
    try {
      found = await loader(productId, fromId);
    } on ApiException {
      found = const [];
    }
    if (!mounted || draft.productId != productId || _fromId != fromId) return;
    setState(() {
      final Set<String> known = {for (final PickedSerial s in found) s.id};
      draft.onShelf = [
        ...found,
        for (final PickedSerial s in draft.onShelf)
          if (draft.serialIds.contains(s.id) && !known.contains(s.id)) s,
      ];
      draft.serialIds.removeWhere((id) => !draft.onShelf.any((s) => s.id == id));
    });
  }

  Future<void> _refreshBatches(_LineDraft draft) async {
    final String? productId = draft.productId;
    final String? fromId = _fromId;
    final loader = widget.loadBatches;
    if (loader == null || productId == null || fromId == null) return;
    List<TransferOption> found = const [];
    try {
      found = await loader(productId, fromId);
    } on ApiException {
      found = const [];
    }
    if (!mounted || draft.productId != productId) return;
    setState(() {
      draft.batches = found;
      if (!found.any((batch) => batch.id == draft.batchId)) {
        draft.batchId = null;
      }
    });
  }

  Future<void> _sourceChosen(String? id) async {
    setState(() {
      _fromId = id;
      // A unit is picked off one shelf; another source un-picks it.
      for (final _LineDraft draft in _lines) {
        draft.serialIds = [];
        draft.onShelf = const [];
      }
    });
    for (final _LineDraft draft in _lines) {
      await _refreshBatches(draft);
      await _refreshSerials(draft);
    }
  }

  List<Json> _linesBody() => [
        for (final _LineDraft draft in _lines)
          if (draft.productId != null || draft.quantity.text.trim().isNotEmpty)
            <String, dynamic>{
              'product_id': draft.productId,
              if (draft.batchId != null) 'batch_id': draft.batchId,
              'quantity': draft.quantity.text.trim(),
              if (draft.serialTracked && draft.serialIds.isNotEmpty)
                'serial_ids': [...draft.serialIds],
            },
      ];

  String? _validate(List<Json> lines) {
    if (_fromId == null) return 'Choose the warehouse the goods leave.';
    if (_toId == null) return 'Choose the warehouse they are going to.';
    if (_fromId == _toId) return 'The two warehouses must be different.';
    if (lines.isEmpty) return 'Add at least one product to move.';
    for (final Json line in lines) {
      if (line['product_id'] == null) return 'Choose a product on every line.';
      final double? quantity = double.tryParse('${line['quantity']}');
      if (quantity == null || quantity <= 0) {
        return 'Enter a quantity above zero on every line.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final List<Json> lines = _linesBody();
    final String? problem = _validate(lines);
    setState(() {
      _problem = problem;
      saveError = null;
    });
    if (problem != null) return;
    final Json body = <String, dynamic>{
      'transfer_date': _when.toIso8601String().substring(0, 10),
      'from_warehouse_id': _fromId,
      'to_warehouse_id': _toId,
      if (_vehicle.text.trim().isNotEmpty)
        'vehicle_number': _vehicle.text.trim(),
      if (_transporter.text.trim().isNotEmpty)
        'transporter_name': _transporter.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': lines,
    };
    await submit<Json>(body, widget.onSave);
  }

  Widget _warehouseBox(
    String key,
    String label,
    String? value,
    void Function(String?) onChanged,
  ) {
    return DropdownButtonFormField<String>(
      key: ValueKey(key),
      isExpanded: true,
      initialValue: value,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final TransferOption warehouse in widget.warehouses)
          DropdownMenuItem(
            value: warehouse.id,
            child: Text(warehouse.label, overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: saving ? null : onChanged,
    );
  }

  Widget _lineEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: Text('Goods to move',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          TextButton.icon(
            key: const ValueKey('transfer-line-add'),
            onPressed:
                saving ? null : () => setState(() => _lines.add(_LineDraft())),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('Add line'),
          ),
        ]),
        for (int index = 0; index < _lines.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _lineRow(index),
                if (widget.loadSerials != null && _lines[index].serialTracked)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: SerialPickChips(
                      title: 'Pick the units that are moving',
                      onShelf: _lines[index].onShelf,
                      picked: _lines[index].serialIds,
                      needed: _unitsMoving(_lines[index]),
                      enabled: !saving,
                      onToggle: (id, picked) => setState(() {
                        if (picked) {
                          _lines[index].serialIds.add(id);
                        } else {
                          _lines[index].serialIds.remove(id);
                        }
                      }),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _lineRow(int index) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 3,
          child: DropdownButtonFormField<String>(
            key: ValueKey('transfer-product-$index'),
            isExpanded: true,
            initialValue: _lines[index].productId,
            decoration: const InputDecoration(labelText: 'Product'),
            items: [
              for (final TransferOption product in widget.products)
                DropdownMenuItem(
                  value: product.id,
                  child: Text(product.label,
                      overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: saving
                ? null
                : (value) =>
                    _productChosen(_lines[index], value),
          ),
        ),
        if (widget.loadBatches != null) ...[
          const SizedBox(width: AppSpacing.md),
          Expanded(
            flex: 2,
            child: DropdownButtonFormField<String>(
              key: ValueKey(
                'transfer-batch-$index-${_lines[index].batches.length}',
              ),
              isExpanded: true,
              initialValue: _lines[index].batchId,
              decoration: const InputDecoration(
                labelText: 'Batch (optional)',
              ),
              items: [
                for (final TransferOption batch
                    in _lines[index].batches)
                  DropdownMenuItem(
                    value: batch.id,
                    child: Text(batch.label,
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: saving || _lines[index].batches.isEmpty
                  ? null
                  : (value) =>
                      setState(() => _lines[index].batchId = value),
            ),
          ),
        ],
        const SizedBox(width: AppSpacing.md),
        SizedBox(
          width: 110,
          child: TextField(
            key: ValueKey('transfer-quantity-$index'),
            controller: _lines[index].quantity,
            enabled: !saving,
            decoration: const InputDecoration(labelText: 'Quantity'),
            keyboardType: TextInputType.number,
            onChanged: (_) => setState(() {}),
          ),
        ),
        IconButton(
          tooltip: 'Remove line',
          onPressed: saving || _lines.length == 1
              ? null
              : () => setState(() {
                    _lines.removeAt(index).dispose();
                  }),
          icon: const Icon(Icons.close),
        ),
      ],
    );
  }

  /// How many units the line moves, where the quantity is a whole number.
  int? _unitsMoving(_LineDraft draft) {
    final double? quantity = double.tryParse(draft.quantity.text.trim());
    if (quantity == null || quantity != quantity.roundToDouble()) return null;
    return quantity.toInt();
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final bool editing = widget.existing != null;
    return AlertDialog(
      title: Text(editing
          ? 'Edit transfer ${widget.existing!.transferNumber}'
          : 'New stock transfer'),
      content: SizedBox(
        width: 760,
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
                  child: _warehouseBox(
                    'transfer-from',
                    'From warehouse',
                    _fromId,
                    (value) => _sourceChosen(value),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _warehouseBox(
                    'transfer-to',
                    'To warehouse',
                    _toId,
                    (value) => setState(() => _toId = value),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('transfer-vehicle'),
                    controller: _vehicle,
                    enabled: !saving,
                    decoration: const InputDecoration(
                      labelText: 'Vehicle number',
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    key: const ValueKey('transfer-transporter'),
                    controller: _transporter,
                    enabled: !saving,
                    decoration: const InputDecoration(
                      labelText: 'Transporter',
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              _lineEditor(),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                key: const ValueKey('transfer-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Saving keeps a draft. Stock leaves the source warehouse when '
                'the transfer is dispatched. Quantities are in the product\'s '
                'stock unit.',
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
          key: const ValueKey('transfer-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving...' : 'Save draft'),
        ),
      ],
    );
  }
}
