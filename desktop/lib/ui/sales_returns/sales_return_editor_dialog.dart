import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/sales_return.dart';
import '../workspace/desktop_framework.dart';

/// Raising a return against goods that already went out.
///
/// A return line belongs to a line of a delivery note or a sales invoice, so
/// the form is a document picker and then its lines: there is nothing to type
/// that the source document does not already say. The quantity is the only
/// number that has to be entered, and how much of it came back fit to sell is
/// the only judgement the person booking it makes.
class SalesReturnEditorDialog extends StatefulWidget {
  const SalesReturnEditorDialog({
    super.key,
    required this.documents,
    required this.warehouses,
    required this.today,
  });

  final List<ReturnableDocument> documents;
  final List<WarehouseRecord> warehouses;

  /// Passed in rather than read here, so the dialog is testable and so the
  /// date shown is the one the caller decided on.
  final DateTime today;

  @override
  State<SalesReturnEditorDialog> createState() =>
      _SalesReturnEditorDialogState();
}

class _SalesReturnEditorDialogState extends State<SalesReturnEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _quantity = TextEditingController(text: '1');
  final TextEditingController _damaged = TextEditingController(text: '0');
  final TextEditingController _scrap = TextEditingController(text: '0');
  final TextEditingController _customerNumber = TextEditingController();
  final TextEditingController _reason = TextEditingController();
  final TextEditingController _remarks = TextEditingController();

  ReturnableDocument? _document;
  ReturnableLine? _line;
  String? _warehouseId;

  @override
  void initState() {
    super.initState();
    if (widget.documents.isNotEmpty) _selectDocument(widget.documents.first);
    if (widget.warehouses.isNotEmpty) _warehouseId = widget.warehouses.first.id;
  }

  @override
  void dispose() {
    _quantity.dispose();
    _damaged.dispose();
    _scrap.dispose();
    _customerNumber.dispose();
    _reason.dispose();
    _remarks.dispose();
    super.dispose();
  }

  void _selectDocument(ReturnableDocument document) {
    setState(() {
      _document = document;
      _line = document.lines.isEmpty ? null : document.lines.first;
    });
  }

  double get _returned => double.tryParse(_quantity.text.trim()) ?? 0;
  double get _damagedQuantity => double.tryParse(_damaged.text.trim()) ?? 0;
  double get _scrapQuantity => double.tryParse(_scrap.text.trim()) ?? 0;

  /// What goes back on the shelf, derived rather than entered: a clerk knows
  /// how many were broken, and the rest is sellable by definition.
  double get _restock => _returned - _damagedQuantity - _scrapQuantity;

  String? _validateQuantity(String? value) {
    final double quantity = double.tryParse((value ?? '').trim()) ?? -1;
    if (quantity <= 0) return 'Enter how many came back.';
    final double sent = double.tryParse(_line?.quantity ?? '0') ?? 0;
    if (quantity > sent) {
      // The server refuses this too. Saying so here means the refusal does not
      // arrive after the form has been filled in.
      return 'Only $sent went out on this line.';
    }
    return null;
  }

  String? _validateCondition(String? value) {
    if ((double.tryParse((value ?? '').trim()) ?? -1) < 0) {
      return 'Enter a quantity.';
    }
    if (_restock < 0) return 'That is more than came back.';
    return null;
  }

  Json? _payload() {
    final ReturnableDocument? document = _document;
    final ReturnableLine? line = _line;
    if (document == null || line == null || _warehouseId == null) return null;
    if (!(_form.currentState?.validate() ?? false)) return null;
    return <String, dynamic>{
      'warehouse_id': _warehouseId,
      'return_date': widget.today.toIso8601String().split('T').first,
      if (_customerNumber.text.trim().isNotEmpty)
        'customer_return_number': _customerNumber.text.trim(),
      if (_reason.text.trim().isNotEmpty) 'return_reason': _reason.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        <String, dynamic>{
          'source_document_type': document.sourceType.code,
          'source_document_id': document.id,
          'source_document_line_id': line.id,
          'line_number': 1,
          'current_return_quantity': _quantity.text.trim(),
          'damaged_quantity': _damaged.text.trim(),
          'scrap_quantity': _scrap.text.trim(),
          if (_reason.text.trim().isNotEmpty) 'reason_code': _reason.text.trim(),
        }
      ],
    };
  }

  @override
  Widget build(BuildContext context) {
    final ReturnableDocument? document = _document;
    return WorkspaceDialog(
      title: 'New sales return',
      saveLabel: 'Create draft',
      onSave: () {
        final Json? payload = _payload();
        if (payload != null) Navigator.of(context).pop(payload);
      },
      body: widget.documents.isEmpty
          ? const StandardEmptyState(
              type: EmptyStateType.noRecords,
              title: 'Nothing has gone out yet',
              message: 'A return is raised against a delivery note or a sales '
                  'invoice, so there has to be one before goods can come back.',
            )
          : Form(
              key: _form,
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    DropdownButtonFormField<String>(
                      initialValue: document?.id,
                      decoration: const InputDecoration(
                        labelText: 'Returned against',
                        helperText: 'The document the goods went out on.',
                      ),
                      items: [
                        for (final ReturnableDocument item in widget.documents)
                          DropdownMenuItem(
                            value: item.id,
                            child: Text(
                              '${item.sourceType.label}  ${item.label}',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (value) {
                        final ReturnableDocument next = widget.documents
                            .firstWhere((item) => item.id == value);
                        _selectDocument(next);
                      },
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      initialValue: _line?.id,
                      decoration: const InputDecoration(labelText: 'Line'),
                      items: [
                        for (final ReturnableLine item
                            in document?.lines ?? const <ReturnableLine>[])
                          DropdownMenuItem(
                            value: item.id,
                            child: Text(item.label,
                                overflow: TextOverflow.ellipsis),
                          ),
                      ],
                      validator: (value) =>
                          value == null ? 'Choose the line that came back.' : null,
                      onChanged: (value) => setState(
                        () => _line = document?.lines
                            .firstWhere((item) => item.id == value),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      initialValue: _warehouseId,
                      decoration: const InputDecoration(
                        labelText: 'Taken back into',
                        helperText: 'Where the goods are being received.',
                      ),
                      items: [
                        for (final WarehouseRecord item in widget.warehouses)
                          DropdownMenuItem(
                            value: item.id,
                            child: Text(item.displayName),
                          ),
                      ],
                      validator: (value) =>
                          value == null ? 'Choose a warehouse.' : null,
                      onChanged: (value) => setState(() => _warehouseId = value),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Row(children: [
                      Expanded(
                        child: TextFormField(
                          controller: _quantity,
                          decoration: const InputDecoration(
                            labelText: 'Quantity returned',
                          ),
                          keyboardType: TextInputType.number,
                          validator: _validateQuantity,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextFormField(
                          controller: _damaged,
                          decoration:
                              const InputDecoration(labelText: 'Of which damaged'),
                          keyboardType: TextInputType.number,
                          validator: _validateCondition,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: TextFormField(
                          controller: _scrap,
                          decoration:
                              const InputDecoration(labelText: 'Of which scrap'),
                          keyboardType: TextInputType.number,
                          validator: _validateCondition,
                          onChanged: (_) => setState(() {}),
                        ),
                      ),
                    ]),
                    const SizedBox(height: AppSpacing.sm),
                    // The consequence of the three numbers above, said in
                    // words: what actually returns to the sellable shelf.
                    Text(
                      _restock < 0
                          ? 'That is more than came back.'
                          : '$_restock back on the shelf; the rest is owned but '
                              'not sellable.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      controller: _customerNumber,
                      decoration: const InputDecoration(
                        labelText: 'Customer’s reference',
                        helperText: 'What they called it on their paperwork.',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      controller: _reason,
                      decoration: const InputDecoration(labelText: 'Reason'),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      controller: _remarks,
                      decoration: const InputDecoration(labelText: 'Remarks'),
                      maxLines: 2,
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
