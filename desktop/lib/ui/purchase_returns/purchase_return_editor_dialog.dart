import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

/// One line going back to the supplier, as it is being edited.
///
/// A return line always belongs to a source document line -- the backend
/// requires `source_document_line_id` -- so lines are seeded from the receipt
/// being sent back rather than typed. What the storeman supplies is how much is
/// going, what condition it is in, and which batch it is coming out of.
class PurchaseReturnDraftLine {
  PurchaseReturnDraftLine({
    required this.sourceDocumentId,
    required this.sourceDocumentLineId,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.receivedQuantity,
    required this.alreadyReturned,
    required this.unitPrice,
    required this.purchaseUomId,
    required this.taxProfileId,
    required this.warehouseId,
    required this.receiptBatchNumber,
    required this.returnQuantity,
    this.rejectedQuantity = '0',
    this.batchNumber = '',
    this.itemCondition = '',
    this.isDamaged = false,
    this.isScrap = false,
    this.reasonCode = '',
    this.remarks = '',
  });

  final String sourceDocumentId;
  final String sourceDocumentLineId;
  final int lineNumber;
  final String productId;
  final String description;
  final String receivedQuantity;
  final String alreadyReturned;
  final String unitPrice;
  final String purchaseUomId;
  final String taxProfileId;
  final String warehouseId;

  /// What the receipt recorded, which is the batch these goods arrived in.
  final String receiptBatchNumber;

  String returnQuantity;
  String rejectedQuantity;
  String batchNumber;
  String itemCondition;
  bool isDamaged;
  bool isScrap;
  String reasonCode;
  String remarks;

  double get outstanding {
    final double received = double.tryParse(receivedQuantity) ?? 0;
    final double returned = double.tryParse(alreadyReturned) ?? 0;
    final double left = received - returned;
    return left < 0 ? 0 : left;
  }

  Json toJson() => {
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': sourceDocumentId,
        'source_document_line_id': sourceDocumentLineId,
        'line_number': lineNumber,
        if (description.isNotEmpty) 'description': description,
        'current_return_quantity':
            returnQuantity.trim().isEmpty ? '0' : returnQuantity.trim(),
        'rejected_quantity':
            rejectedQuantity.trim().isEmpty ? '0' : rejectedQuantity.trim(),
        'unit_price': unitPrice.isEmpty ? '0' : unitPrice,
        'is_damaged': isDamaged,
        'is_scrap': isScrap,
        if (itemCondition.isNotEmpty) 'item_condition': itemCondition,
        if (reasonCode.trim().isNotEmpty) 'reason_code': reasonCode.trim(),
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (batchNumber.trim().isNotEmpty) 'batch_number': batchNumber.trim(),
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

/// Send goods back to the supplier they came from.
///
/// The third document the desktop can create, and the third shape. A receipt
/// takes a batch number as free text because the goods are on the dock and the
/// number is on the carton. A delivery note takes none, because the server
/// allocates at dispatch. A return is neither: the batch has to be one that was
/// actually received, so this offers the register rather than a text box --
/// the server refuses a number nobody received, and a picker means nobody
/// discovers that by typing.
class PurchaseReturnEditorDialog extends StatefulWidget {
  const PurchaseReturnEditorDialog({
    super.key,
    required this.api,
    required this.receipts,
    required this.products,
  });

  final ApiClient api;

  /// Completed goods receipts, which are what can be sent back.
  final List<GoodsReceiptRecord> receipts;
  final List<Product> products;

  @override
  State<PurchaseReturnEditorDialog> createState() =>
      _PurchaseReturnEditorDialogState();
}

class _PurchaseReturnEditorDialogState
    extends State<PurchaseReturnEditorDialog> {
  GoodsReceiptRecord? _receipt;
  List<PurchaseReturnDraftLine> _lines = const [];
  // Registered batches per product, so a line can only name one that exists.
  Map<String, List<BatchRecord>> _batchesByProduct = const {};
  String _returnDate = _today();
  String _supplierReturnNumber = '';
  String _returnReason = '';
  String _remarks = '';
  bool _saving = false;
  bool _loadingLines = false;
  String? _error;

  static String _today() => DateTime.now().toIso8601String().split('T').first;

  String _productLabel(String productId) {
    for (final Product product in widget.products) {
      if (product.id == productId) return '${product.code} — ${product.name}';
    }
    return productId;
  }

  Future<void> _selectReceipt(GoodsReceiptRecord receipt) async {
    setState(() {
      _receipt = receipt;
      _loadingLines = true;
      _error = null;
    });
    final Map<String, double> returned = await _returnedByLine(receipt);
    final Map<String, List<BatchRecord>> batches =
        await _batchesFor(receipt.lines.map((line) => line.productId).toSet());
    if (!mounted) return;
    setState(() {
      _lines = [
        for (int index = 0; index < receipt.lines.length; index++)
          _draftLine(
            receipt,
            receipt.lines[index],
            index + 1,
            returned[receipt.lines[index].id] ?? 0,
            batches[receipt.lines[index].productId] ?? const [],
          ),
      ];
      _batchesByProduct = batches;
      _loadingLines = false;
    });
  }

  /// Sum what earlier returns already sent back off each receipt line.
  ///
  /// The server enforces this too -- a return past the received quantity is
  /// refused -- but it decides after the whole document is typed. Defaulting
  /// to what is left means the common case never meets that refusal.
  Future<Map<String, double>> _returnedByLine(GoodsReceiptRecord receipt) async {
    final Map<String, double> returned = <String, double>{};
    try {
      final Json page = await widget.api.documentPage(
        'purchase-returns',
        page: 1,
        pageSize: 100,
      );
      final dynamic data = page['data'];
      for (final dynamic row in data is List ? data : const []) {
        if (row is! Map) continue;
        if (stringValue(row['status']).trim().toUpperCase() == 'CANCELLED') {
          continue;
        }
        for (final dynamic line in (row['lines'] as List<dynamic>? ?? const [])) {
          if (line is! Map) continue;
          final String id = stringValue(line['source_document_line_id']);
          if (id.isEmpty) continue;
          returned[id] = (returned[id] ?? 0) +
              (double.tryParse(
                      stringValue(line['current_return_quantity'])) ??
                  0);
        }
      }
    } on ApiException catch (exception) {
      _error = 'Could not read earlier returns: ${exception.message}. '
          'Quantities default to the full receipt.';
    }
    return returned;
  }

  /// Read the registered batches for these products, one call per product.
  ///
  /// A return may only name a batch that was actually received, so this is
  /// what the picker offers. An empty list means the product has no batches
  /// registered and the line goes back against the product, which is what the
  /// server does with a blank number.
  Future<Map<String, List<BatchRecord>>> _batchesFor(
    Set<String> productIds,
  ) async {
    final Map<String, List<BatchRecord>> byProduct = {};
    for (final String productId in productIds) {
      try {
        final PagedResult<BatchRecord> page = await widget.api.batches(
          page: 1,
          pageSize: 100,
          filters: BatchQuery(productId: productId),
        );
        if (page.items.isNotEmpty) byProduct[productId] = page.items;
      } on ApiException {
        // Losing the register turns the picker into "no batch", which the
        // server accepts unless the product requires one. It must not stop a
        // return being recorded.
        continue;
      }
    }
    return byProduct;
  }

  PurchaseReturnDraftLine _draftLine(
    GoodsReceiptRecord receipt,
    GoodsReceiptLine line,
    int lineNumber,
    double alreadyReturned,
    List<BatchRecord> batches,
  ) {
    final PurchaseReturnDraftLine draft = PurchaseReturnDraftLine(
      sourceDocumentId: receipt.id,
      sourceDocumentLineId: line.id,
      lineNumber: lineNumber,
      productId: line.productId,
      description: line.description,
      receivedQuantity: line.acceptedQuantity,
      alreadyReturned: _trim(alreadyReturned),
      unitPrice: line.unitPrice,
      purchaseUomId: line.purchaseUomId,
      taxProfileId: line.taxProfileId,
      warehouseId: line.warehouseId,
      receiptBatchNumber: line.batchNumber,
      returnQuantity: '0',
    );
    draft.returnQuantity = _trim(draft.outstanding);
    // The batch these goods arrived in is the one going back, so it is the
    // default -- but only if it is still in the register, because a picker
    // offering a value it cannot show would clear itself on the first edit.
    final bool receiptBatchKnown = batches.any(
      (batch) => batch.batchNumber == line.batchNumber,
    );
    if (line.batchNumber.isNotEmpty && receiptBatchKnown) {
      draft.batchNumber = line.batchNumber;
    }
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  List<PurchaseReturnDraftLine> _sendableLines() => [
        for (final PurchaseReturnDraftLine line in _lines)
          if ((double.tryParse(line.returnQuantity) ?? 0) > 0) line,
      ];

  String? _validation() {
    if (_receipt == null) return 'Choose the goods receipt being sent back.';
    final List<PurchaseReturnDraftLine> sending = _sendableLines();
    if (sending.isEmpty) {
      return 'Enter a return quantity on at least one line.';
    }
    for (final PurchaseReturnDraftLine line in sending) {
      final double rejected = double.tryParse(line.rejectedQuantity) ?? 0;
      final double returning = double.tryParse(line.returnQuantity) ?? 0;
      if (rejected > returning) {
        return 'Line ${line.lineNumber}: rejected cannot exceed the quantity '
            'being returned.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final String? problem = _validation();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final List<PurchaseReturnDraftLine> sending = _sendableLines();
      final Json payload = {
        'warehouse_id': _warehouseForDocument(sending),
        'return_date': _returnDate,
        if (_supplierReturnNumber.trim().isNotEmpty)
          'supplier_return_number': _supplierReturnNumber.trim(),
        if (_returnReason.trim().isNotEmpty)
          'return_reason': _returnReason.trim(),
        if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
        'reference_grn_number': _receipt!.grnNumber,
        'source_documents': [
          {
            'source_document_type': 'GOODS_RECEIPT',
            'source_document_id': _receipt!.id,
          }
        ],
        'lines': [
          for (int index = 0; index < sending.length; index++)
            {...sending[index].toJson(), 'line_number': index + 1},
        ],
      };
      final Json response = await widget.api.create('purchase-returns', payload);
      if (!mounted) return;
      final dynamic data = response['data'];
      Navigator.pop(context, data is Json ? data : response);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _saving = false;
      });
    }
  }

  /// The document needs one warehouse; the lines carry their own.
  String _warehouseForDocument(List<PurchaseReturnDraftLine> lines) {
    for (final PurchaseReturnDraftLine line in lines) {
      if (line.warehouseId.isNotEmpty) return line.warehouseId;
    }
    return '';
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'New Purchase Return',
        subtitle: _receipt == null
            ? 'Choose the goods receipt being sent back'
            : 'Against ${_receipt!.grnNumber}',
        icon: Icons.assignment_return_outlined,
        loading: _saving || _loadingLines,
        onClose: _saving ? null : () => Navigator.pop(context),
        onSave: _saving ? null : _save,
        footer: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton(
                onPressed: _saving ? null : () => Navigator.pop(context),
                child: const Text('Cancel'),
              ),
              const SizedBox(width: AppSpacing.md),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: const Icon(Icons.save_outlined),
                label: const Text('Save Return'),
              ),
            ],
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null) ...[
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              const SectionHeader(
                title: 'Return',
                description:
                    'Which delivery is going back, when, and why.',
              ),
              const SizedBox(height: AppSpacing.md),
              _headerFields(),
              const SizedBox(height: AppSpacing.xl),
              SectionHeader(
                title: 'Items Going Back',
                description: _receipt == null
                    ? 'Lines appear once a goods receipt is chosen.'
                    : 'Lines come from the receipt. The batch must be one that '
                        'was actually received, so it is chosen rather than '
                        'typed.',
              ),
              const SizedBox(height: AppSpacing.md),
              if (_receipt == null)
                const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No goods receipt chosen',
                  message: 'A return sends back what a receipt brought in, so '
                      'pick the receipt above.',
                )
              else
                ..._lineCards(),
            ],
          ),
        ),
      );

  Widget _headerFields() => Wrap(
        spacing: AppSpacing.lg,
        runSpacing: AppSpacing.lg,
        children: [
          SizedBox(
            width: 320,
            child: DropdownButtonFormField<String>(
              initialValue: _receipt?.id,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Goods Receipt *',
                helperText: 'Completed receipts only',
              ),
              items: [
                for (final GoodsReceiptRecord receipt in widget.receipts)
                  DropdownMenuItem<String>(
                    value: receipt.id,
                    child: Text(
                      '${receipt.grnNumber} • ${receipt.receiptDate}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: _saving
                  ? null
                  : (value) {
                      final Iterable<GoodsReceiptRecord> match =
                          widget.receipts.where((row) => row.id == value);
                      if (match.isNotEmpty) _selectReceipt(match.first);
                    },
            ),
          ),
          _text('Return Date *', _returnDate, (value) => _returnDate = value,
              'YYYY-MM-DD'),
          _text('Supplier Return Number', _supplierReturnNumber,
              (value) => _supplierReturnNumber = value, null),
          _text('Reason', _returnReason, (value) => _returnReason = value, null),
          _text('Remarks', _remarks, (value) => _remarks = value, null),
        ],
      );

  Widget _text(
    String label,
    String value,
    ValueChanged<String> onChanged,
    String? hint, {
    double width = 220,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label, hintText: hint),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );

  List<Widget> _lineCards() => [
        for (final PurchaseReturnDraftLine line in _lines) ...[
          Card(
            clipBehavior: Clip.antiAlias,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Line ${line.lineNumber} · '
                          '${_productLabel(line.productId)}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      Text(
                        'Received ${line.receivedQuantity} · already returned '
                        '${line.alreadyReturned}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Wrap(
                    spacing: AppSpacing.lg,
                    runSpacing: AppSpacing.lg,
                    children: [
                      _lineField(
                        'Returning *',
                        line.returnQuantity,
                        (value) => line.returnQuantity = value,
                        width: 130,
                      ),
                      _lineField(
                        'Rejected',
                        line.rejectedQuantity,
                        (value) => line.rejectedQuantity = value,
                        width: 120,
                      ),
                      _batchPicker(line),
                      _lineField(
                        'Reason Code',
                        line.reasonCode,
                        (value) => line.reasonCode = value,
                        width: 180,
                      ),
                      _lineField(
                        'Remarks',
                        line.remarks,
                        (value) => line.remarks = value,
                        width: 240,
                      ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Wrap(
                    spacing: AppSpacing.lg,
                    children: [
                      FilterChip(
                        label: const Text('Damaged'),
                        selected: line.isDamaged,
                        onSelected: (value) =>
                            setState(() => line.isDamaged = value),
                      ),
                      FilterChip(
                        label: const Text('Scrap'),
                        selected: line.isScrap,
                        onSelected: (value) =>
                            setState(() => line.isScrap = value),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
        ],
      ];

  /// Offer the batches this product actually has, not a text box.
  ///
  /// The server refuses a batch number that was never received, because a
  /// number nobody took in names stock that never arrived. Typing here would
  /// mean discovering that on save; choosing means it cannot be got wrong.
  Widget _batchPicker(PurchaseReturnDraftLine line) {
    final List<BatchRecord> batches = _batchesByProduct[line.productId] ?? [];
    if (batches.isEmpty) {
      return SizedBox(
        width: 260,
        child: InputDecorator(
          decoration: const InputDecoration(
            labelText: 'Batch',
            helperText: 'No batches registered for this product',
          ),
          child: Text(
            line.receiptBatchNumber.isEmpty
                ? 'Returned against the product'
                : 'Receipt said ${line.receiptBatchNumber}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      );
    }
    return SizedBox(
      width: 260,
      child: DropdownButtonFormField<String>(
        initialValue: line.batchNumber.isEmpty ? null : line.batchNumber,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: 'Batch',
          helperText: line.receiptBatchNumber.isEmpty
              ? 'Received batches only'
              : 'Receipt said ${line.receiptBatchNumber}',
        ),
        items: [
          for (final BatchRecord batch in batches)
            DropdownMenuItem<String>(
              value: batch.batchNumber,
              child: Text(
                batch.expiryDate.isEmpty
                    ? '${batch.batchNumber} · holds ${batch.quantity}'
                    : '${batch.batchNumber} · holds ${batch.quantity} · '
                        'expires ${batch.expiryDate}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) => setState(() => line.batchNumber = value ?? ''),
      ),
    );
  }

  Widget _lineField(
    String label,
    String value,
    ValueChanged<String> onChanged, {
    required double width,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );
}
