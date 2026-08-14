import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// What is being done to the stock on a selected row.
enum StockAction {
  /// Moved to another warehouse. Still owned, still worth the same.
  transfer,

  /// Taken off the books, with a reason.
  writeOff,

  /// Held back from sale, or let go again.
  quarantine,
}

/// A warehouse, reduced to what this dialog needs.
class WarehouseOption {
  const WarehouseOption({required this.id, required this.name});

  final String id;
  final String name;
}

/// Check what is about to be sent, in the words a storeman would use.
///
/// The server refuses all of this too, and has to. Doing it here is about not
/// making somebody re-key a form to find out they typed a digit twice.
String? validateStockAction({
  required StockAction action,
  required String quantity,
  required double available,
  required String reference,
  String? destinationWarehouseId,
  String? sourceWarehouseId,
}) {
  if (reference.trim().length < 2) {
    return 'Give it a reference, so the movement can be found later.';
  }
  final double amount = double.tryParse(quantity.trim()) ?? 0;
  if (amount <= 0) return 'Enter how much is moving.';
  if (amount - available > 0.0001) {
    return 'This location holds ${available.toStringAsFixed(4)}, so '
        '${amount.toStringAsFixed(4)} cannot be moved out of it.';
  }
  if (action == StockAction.transfer) {
    if (destinationWarehouseId == null || destinationWarehouseId.isEmpty) {
      return 'Choose the warehouse it is going to.';
    }
    if (destinationWarehouseId == sourceWarehouseId) {
      return 'A transfer must move stock somewhere else than where it is.';
    }
  }
  return null;
}

/// Move, condemn, or hold back the stock on one row.
///
/// One dialog for the three because they ask nearly the same questions -- how
/// much, when, and under what reference -- and differ in one field each. Three
/// dialogs would be three places for the same quantity check to drift.
class StockActionDialog extends StatefulWidget {
  const StockActionDialog({
    super.key,
    required this.action,
    required this.productLabel,
    required this.warehouseLabel,
    required this.sourceWarehouseId,
    required this.available,
    required this.quarantined,
    required this.warehouses,
  });

  final StockAction action;
  final String productLabel;
  final String warehouseLabel;
  final String sourceWarehouseId;

  /// What can be moved out: current less what is already reserved.
  final double available;

  /// What is already held back, which is what a release can let go.
  final double quarantined;
  final List<WarehouseOption> warehouses;

  @override
  State<StockActionDialog> createState() => _StockActionDialogState();
}

class _StockActionDialogState extends State<StockActionDialog> {
  final TextEditingController _quantity = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  String _destination = '';
  String _reason = 'DAMAGE';
  bool _releasing = false;
  DateTime _when = DateTime.now();
  String? _error;

  @override
  void dispose() {
    _quantity.dispose();
    _reference.dispose();
    _remarks.dispose();
    super.dispose();
  }

  String get _title => switch (widget.action) {
        StockAction.transfer => 'Transfer stock',
        StockAction.writeOff => 'Write off stock',
        StockAction.quarantine => 'Quarantine stock',
      };

  /// What this action can draw on, which is not the same for a release.
  double get _available =>
      widget.action == StockAction.quarantine && _releasing
          ? widget.quarantined
          : widget.available;

  void _save() {
    final String? problem = validateStockAction(
      action: widget.action,
      quantity: _quantity.text,
      available: _available,
      reference: _reference.text,
      destinationWarehouseId: _destination,
      sourceWarehouseId: widget.sourceWarehouseId,
    );
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    Navigator.of(context).pop(<String, dynamic>{
      'quantity': _quantity.text.trim(),
      'reference_number': _reference.text.trim(),
      'transaction_date': _when.toIso8601String().substring(0, 10),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      if (widget.action == StockAction.transfer)
        'to_warehouse_id': _destination,
      if (widget.action == StockAction.writeOff) 'reason': _reason,
      if (widget.action == StockAction.quarantine)
        'action': _releasing ? 'RELEASE' : 'HOLD',
    });
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: _title,
        subtitle: '${widget.productLabel} · ${widget.warehouseLabel}',
        onClose: () => Navigator.of(context).pop(),
        onSave: _save,
        body: SingleChildScrollView(
          child: Column(
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
              // What the action can draw on, said before the quantity box
              // rather than after the refusal.
              Text(
                widget.action == StockAction.quarantine && _releasing
                    ? '${widget.quarantined} held back and available to release'
                    : '${widget.available} available here',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.lg),
              Row(children: [
                SizedBox(width: 160, child: _quantityField()),
                const SizedBox(width: AppSpacing.md),
                SizedBox(width: 220, child: _dateField(context)),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    controller: _reference,
                    decoration: const InputDecoration(
                      labelText: 'Reference',
                      hintText: 'TRF-0001',
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              ..._actionFields(),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _remarks,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text(_footnote(), style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      );

  /// What this action does to the books, said on the screen that does it.
  String _footnote() => switch (widget.action) {
        StockAction.transfer =>
          'The firm still owns the same goods at the same value, so a transfer '
              'writes no journal.',
        StockAction.writeOff =>
          'The value leaves the books through the inventory adjustment '
              'account, under the reason chosen.',
        StockAction.quarantine =>
          'Held stock is still owned and still worth what it was, so nothing '
              'is posted. Writing it off is a separate decision.',
      };

  List<Widget> _actionFields() => switch (widget.action) {
        StockAction.transfer => [
            DropdownButtonFormField<String>(
              initialValue: _destination.isEmpty ? null : _destination,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Move it to'),
              items: [
                for (final WarehouseOption warehouse in widget.warehouses)
                  if (warehouse.id != widget.sourceWarehouseId)
                    DropdownMenuItem<String>(
                      value: warehouse.id,
                      child: Text(warehouse.name, overflow: TextOverflow.ellipsis),
                    ),
              ],
              onChanged: (value) => setState(() => _destination = value ?? ''),
            ),
          ],
        StockAction.writeOff => [
            DropdownButtonFormField<String>(
              initialValue: _reason,
              decoration: const InputDecoration(labelText: 'Reason'),
              items: const [
                DropdownMenuItem<String>(value: 'DAMAGE', child: Text('Damage')),
                DropdownMenuItem<String>(value: 'EXPIRY', child: Text('Expiry')),
                DropdownMenuItem<String>(value: 'LOSS', child: Text('Loss')),
              ],
              onChanged: (value) => setState(() => _reason = value ?? 'DAMAGE'),
            ),
          ],
        StockAction.quarantine => [
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment<bool>(value: false, label: Text('Hold back')),
                ButtonSegment<bool>(value: true, label: Text('Release')),
              ],
              selected: {_releasing},
              onSelectionChanged: (value) =>
                  setState(() => _releasing = value.first),
            ),
          ],
      };

  Widget _quantityField() => TextField(
        controller: _quantity,
        decoration: const InputDecoration(labelText: 'Quantity'),
        keyboardType: TextInputType.number,
        onChanged: (_) => setState(() {}),
      );

  Widget _dateField(BuildContext context) => InkWell(
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
            labelText: 'Date',
            suffixIcon: Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(_when.toIso8601String().substring(0, 10)),
        ),
      );
}

/// Build the request body for one action, given the row it applies to.
Json stockActionBody({
  required StockAction action,
  required Json draft,
  required String branchId,
  required String warehouseId,
  required String productId,
  String? batchId,
}) =>
    <String, dynamic>{
      'branch_id': branchId,
      'product_id': productId,
      if (batchId != null && batchId.isNotEmpty) 'batch_id': batchId,
      if (action == StockAction.transfer) ...{
        'from_warehouse_id': warehouseId,
      } else ...{
        'warehouse_id': warehouseId,
      },
      ...draft,
    };
