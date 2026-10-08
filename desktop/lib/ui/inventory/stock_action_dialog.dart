import 'package:file_selector/file_selector.dart' show XFile;
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/serial_pick_chips.dart';
import 'stock_evidence_picker.dart';

/// What is being done to the stock on a selected row.
enum StockAction {
  /// Moved to another warehouse. Still owned, still worth the same.
  transfer,

  /// Taken off the books, with a reason.
  writeOff,

  /// Held back from sale, or let go again.
  quarantine,
}

/// Set on the value a [StockActionDialog] closes with when the movement was
/// sent for approval instead of posted (STK-8).
const String stockSubmittedForApprovalKey = '_submitted_for_approval';

/// A write-off or adjustment reason, reduced to what a dropdown needs.
class StockReasonOption {
  const StockReasonOption({required this.code, required this.name});

  final String code;
  final String name;
}

/// A customer a write-off can be given to, reduced to what a picker needs.
class StockCustomerOption {
  const StockCustomerOption({required this.id, required this.label});

  final String id;
  final String label;
}

/// The write-off reason that names a customer, and the one that may (BUY-1).
const String freeToCustomerReason = 'FREE_TO_CUSTOMER';
const String sampleReason = 'SAMPLE';

/// The six reasons every firm has, offered when the firm's own list could not
/// be read (STK-7) so a write-off is never blocked by a failed lookup.
const List<StockReasonOption> fallbackStockReasons = [
  StockReasonOption(code: 'DAMAGE', name: 'Damage'),
  StockReasonOption(code: 'EXPIRY', name: 'Expiry'),
  StockReasonOption(code: 'LOSS', name: 'Loss'),
  StockReasonOption(code: 'INTERNAL_USE', name: 'Internal use'),
  StockReasonOption(code: 'STAFF', name: 'Given to staff'),
  StockReasonOption(code: 'DISPLAY', name: 'Display / sample / demo'),
];

/// A warehouse, reduced to what this dialog needs.
class WarehouseOption {
  const WarehouseOption({required this.id, required this.name, this.code = ''});

  final String id;
  final String name;
  final String code;

  /// How the destination reads: the code first, the way every other
  /// warehouse picker names one. Plan item 8.3 asked for `WHL_DC` and the
  /// list offered "Bulk Goods Warehouse1", which nobody could match.
  String get label => code.isEmpty ? name : '$code - $name';
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
  // Optional: left blank, the server numbers the movement from its series
  // (D-QA-16). Typed, it is the paper slip's number, and the server's
  // two-character floor applies.
  final String typed = reference.trim();
  if (typed.isNotEmpty && typed.length < 2) {
    return 'A reference needs at least two characters, or leave it blank '
        'to have it numbered.';
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
    this.reasons = fallbackStockReasons,
    this.onSave,
    this.onSubmitForApproval,
    this.pickFiles,
    this.searchCustomers,
    this.trackSerial = false,
    this.loadSerials,
  });

  /// Whether the product carries a serial number on every unit. A transfer of
  /// such a product names the units moving (D-STK-40).
  final bool trackSerial;

  /// The AVAILABLE serials of the product in the source warehouse; null hides
  /// the picker.
  final Future<List<PickedSerial>> Function()? loadSerials;

  /// Finds customers by what was typed, for the write-off reasons that name
  /// one (BUY-1). Null: the picker finds nothing.
  final Future<List<StockCustomerOption>> Function(String text)?
      searchCustomers;

  /// Sends the draft for approval when the server says it is above the
  /// limit of whoever posts it (STK-8). Null: the refusal is only shown.
  final Future<void> Function(Json draft)? onSubmitForApproval;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  /// Carries the action out; throws [ApiException] on a refusal, which the
  /// dialog shows without closing. Null closes with the draft at once.
  final Future<void> Function(Json draft)? onSave;

  final StockAction action;
  final String productLabel;
  final String warehouseLabel;
  final String sourceWarehouseId;

  /// What can be moved out: current less what is already reserved.
  final double available;

  /// What is already held back, which is what a release can let go.
  final double quarantined;
  final List<WarehouseOption> warehouses;

  /// What a write-off can be put down to: the firm's active reasons.
  final List<StockReasonOption> reasons;

  @override
  State<StockActionDialog> createState() => _StockActionDialogState();
}

class _StockActionDialogState extends State<StockActionDialog>
    with SaveInDialog<StockActionDialog> {
  final TextEditingController _quantity = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  String _destination = '';
  late String _reason = widget.reasons.isEmpty
      ? 'DAMAGE'
      : widget.reasons.any((reason) => reason.code == 'DAMAGE')
          ? 'DAMAGE'
          : widget.reasons.first.code;
  bool _releasing = false;
  DateTime _when = DateTime.now();
  String? _error;
  String? _customerId;
  List<Json> _attachments = const [];
  List<PickedSerial> _onShelf = const [];
  final List<String> _serialIds = [];

  /// The draft the server refused as too large, kept so it can be sent for
  /// approval as it stands (STK-8).
  Json? _refused;

  Future<void> _post(Json draft) async {
    final Future<void> Function(Json draft)? onSave = widget.onSave;
    if (onSave == null) {
      Navigator.pop(context, draft);
      return;
    }
    await saveAndClose<Json>(() async {
      try {
        await onSave(draft);
      } on ApiException catch (error) {
        _refused = error.needsApproval && widget.onSubmitForApproval != null
            ? draft
            : null;
        rethrow;
      }
      _refused = null;
      return draft;
    });
  }

  Future<void> _submitForApproval() async {
    final Json? draft = _refused;
    if (draft == null) return;
    await saveAndClose<Json>(() async {
      await widget.onSubmitForApproval!(draft);
      return <String, dynamic>{...draft, stockSubmittedForApprovalKey: true};
    });
  }

  bool get _namesUnits =>
      widget.action == StockAction.transfer &&
      widget.trackSerial &&
      widget.loadSerials != null;

  @override
  void initState() {
    super.initState();
    if (_namesUnits) _readSerials();
  }

  Future<void> _readSerials() async {
    try {
      final List<PickedSerial> found = await widget.loadSerials!();
      if (mounted) setState(() => _onShelf = found);
    } on ApiException {
      // The picker then says there is nothing to pick; the server decides.
    }
  }

  /// How many units are moving, where the quantity is a whole number.
  int? get _unitsMoving {
    final double? quantity = double.tryParse(_quantity.text.trim());
    if (quantity == null || quantity != quantity.roundToDouble()) return null;
    return quantity.toInt();
  }

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
  double get _available => widget.action == StockAction.quarantine && _releasing
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
    final int? units = _unitsMoving;
    if (_namesUnits && units != null && _serialIds.length != units) {
      setState(() => _error = 'Pick one serial number per unit moving: '
          '$units needed, ${_serialIds.length} picked.');
      return;
    }
    if (widget.action == StockAction.writeOff &&
        _reason == freeToCustomerReason &&
        _customerId == null) {
      setState(() => _error = 'Choose the customer it was given to.');
      return;
    }
    _post(<String, dynamic>{
      'quantity': _quantity.text.trim(),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      'transaction_date': _when.toIso8601String().substring(0, 10),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      if (widget.action == StockAction.transfer)
        'to_warehouse_id': _destination,
      if (_namesUnits && _serialIds.isNotEmpty) 'serial_ids': [..._serialIds],
      if (widget.action == StockAction.writeOff) 'reason': _reason,
      if (widget.action == StockAction.writeOff &&
          _customerId != null &&
          (_reason == freeToCustomerReason || _reason == sampleReason))
        'customer_id': _customerId,
      if (widget.action == StockAction.quarantine)
        'action': _releasing ? 'RELEASE' : 'HOLD',
      // Photos and documents (STK-9); a hold or release takes none.
      if (widget.action != StockAction.quarantine && _attachments.isNotEmpty)
        'attachments': _attachments,
    });
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: _title,
        subtitle: '${widget.productLabel} · ${widget.warehouseLabel}',
        loading: saving,
        onClose: saving ? null : () => Navigator.of(context).pop(),
        onSave: saving ? null : _save,
        saveLabel: switch (widget.action) {
          StockAction.transfer => 'Transfer',
          StockAction.writeOff => 'Write off',
          StockAction.quarantine => _releasing ? 'Release' : 'Hold back',
        },
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              saveErrorBanner(),
              if (_refused != null && !saving)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: FilledButton.icon(
                    key: const ValueKey('submit-for-approval'),
                    onPressed: _submitForApproval,
                    icon: const Icon(Icons.send_outlined),
                    label: const Text('Submit for approval'),
                  ),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: MaterialBanner(
                    leading: const Icon(Icons.error_outline),
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
                      labelText: 'Reference (optional)',
                      helperText: 'Blank: numbered from the series',
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              ..._actionFields(),
              if (_namesUnits && _destination.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                SerialPickChips(
                  title: 'Pick the units that are moving',
                  onShelf: _onShelf,
                  picked: _serialIds,
                  needed: _unitsMoving,
                  enabled: !saving,
                  onToggle: (id, picked) => setState(() {
                    if (picked) {
                      _serialIds.add(id);
                    } else {
                      _serialIds.remove(id);
                    }
                  }),
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _remarks,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              if (widget.action != StockAction.quarantine) ...[
                StockEvidencePicker(
                  pickFiles: widget.pickFiles,
                  onChanged: (files) => _attachments = files,
                ),
                const SizedBox(height: AppSpacing.md),
              ],
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
                      child: Text(warehouse.label,
                          overflow: TextOverflow.ellipsis),
                    ),
              ],
              onChanged: (value) => setState(() => _destination = value ?? ''),
            ),
          ],
        StockAction.writeOff => [
            DropdownButtonFormField<String>(
              isExpanded: true,
              initialValue: _reason,
              decoration: const InputDecoration(labelText: 'Reason'),
              items: [
                for (final StockReasonOption reason in widget.reasons)
                  DropdownMenuItem<String>(
                    value: reason.code,
                    child: Text(reason.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) => setState(() {
                _reason = value ?? 'DAMAGE';
                if (_reason != freeToCustomerReason &&
                    _reason != sampleReason) {
                  _customerId = null;
                }
              }),
            ),
            if (_reason == freeToCustomerReason || _reason == sampleReason) ...[
              const SizedBox(height: AppSpacing.md),
              _customerPicker(),
            ],
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

  /// Who the goods were given to: required for a free gift, optional for a
  /// sample.
  Widget _customerPicker() => Autocomplete<StockCustomerOption>(
        key: const ValueKey('stock-write-off-customer'),
        optionsBuilder: (value) async {
          final String text = value.text.trim();
          final Future<List<StockCustomerOption>> Function(String)? search =
              widget.searchCustomers;
          if (text.length < 2 || search == null) {
            return const <StockCustomerOption>[];
          }
          try {
            return await search(text);
          } on ApiException {
            return const <StockCustomerOption>[];
          }
        },
        displayStringForOption: (option) => option.label,
        onSelected: (option) => setState(() => _customerId = option.id),
        fieldViewBuilder: (context, controller, focusNode, onSubmitted) =>
            TextField(
          controller: controller,
          focusNode: focusNode,
          decoration: InputDecoration(
            labelText: _reason == freeToCustomerReason
                ? 'Customer'
                : 'Customer (optional)',
            helperText: 'Type two letters of the name or code',
          ),
          // Typing again means the earlier pick no longer stands.
          onChanged: (_) {
            if (_customerId != null) setState(() => _customerId = null);
          },
        ),
      );

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
