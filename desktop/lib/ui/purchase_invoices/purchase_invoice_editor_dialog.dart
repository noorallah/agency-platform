import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';

/// One line of a supplier bill, as it is being typed.
///
/// A bill line always continues a receipt line -- the backend requires
/// `source_document_line_id` -- so lines are seeded from the receipt being
/// billed rather than typed. What the clerk supplies is how much of it this
/// bill covers and, where the supplier's price differs from the order's, the
/// price on the paper.
class PurchaseInvoiceDraftLine {
  PurchaseInvoiceDraftLine({
    required this.sourceDocumentId,
    required this.sourceDocumentLineId,
    required this.lineNumber,
    required this.productId,
    required this.description,
    required this.receivedQuantity,
    required this.alreadyInvoiced,
    required this.receiptUnitPrice,
    required this.purchaseUomId,
    required this.taxProfileId,
    required this.warehouseId,
    required this.batchNumber,
    required this.invoiceQuantity,
    this.unitPrice = '',
    this.remarks = '',
  });

  final String sourceDocumentId;
  final String sourceDocumentLineId;
  final int lineNumber;
  final String productId;
  final String description;
  final String receivedQuantity;
  final String alreadyInvoiced;

  /// What the receipt recorded, which is what a blank price box takes.
  final String receiptUnitPrice;
  final String purchaseUomId;
  final String taxProfileId;
  final String warehouseId;
  final String batchNumber;

  String invoiceQuantity;
  String unitPrice;
  String remarks;

  /// What the receipt still has to be billed for.
  double get outstanding {
    final double received = double.tryParse(receivedQuantity) ?? 0;
    final double invoiced = double.tryParse(alreadyInvoiced) ?? 0;
    final double left = received - invoiced;
    return left < 0 ? 0 : left;
  }

  Json toJson() => {
        'source_document_type': 'GOODS_RECEIPT',
        'source_document_id': sourceDocumentId,
        'source_document_line_id': sourceDocumentLineId,
        'line_number': lineNumber,
        // No description: the server derives it from the receipt line, and
        // PurchaseInvoiceLineWrite forbids the key -- the same refusal every
        // purchase return met before its editor stopped sending one.
        'current_invoice_quantity':
            invoiceQuantity.trim().isEmpty ? '0' : invoiceQuantity.trim(),
        // A blank price is left out rather than sent as '0'. Absent means the
        // server takes the receipt line's price; zero means the supplier
        // charged nothing, which is a different statement.
        if (unitPrice.trim().isNotEmpty) 'unit_price': unitPrice.trim(),
        // No discount either way: silence takes the rate the receipt line
        // carries, and a literal zero would refuse it.
        if (taxProfileId.isNotEmpty) 'tax_profile_id': taxProfileId,
        if (purchaseUomId.isNotEmpty) 'purchase_uom_id': purchaseUomId,
        if (purchaseUomId.isNotEmpty) 'invoice_uom_id': purchaseUomId,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (batchNumber.isNotEmpty) 'batch_number': batchNumber,
        if (remarks.trim().isNotEmpty) 'remarks': remarks.trim(),
      };
}

/// Record the supplier's bill for goods a receipt brought in.
///
/// The twin of the purchase return editor: both pick a completed goods
/// receipt and seed their lines from it, because the server refuses a line
/// that names no receipt line. What differs is the question each line asks --
/// a return asks how much is going back, a bill asks how much of what arrived
/// this piece of paper charges for -- and the header, which here is the
/// supplier's own invoice number and date, since that is what the payment
/// will be matched to.
class PurchaseInvoiceEditorDialog extends StatefulWidget {
  const PurchaseInvoiceEditorDialog({
    super.key,
    required this.api,
    required this.receipts,
    required this.products,
  });

  final ApiClient api;

  /// Completed goods receipts, which are what can be billed.
  final List<GoodsReceiptRecord> receipts;
  final List<Product> products;

  @override
  State<PurchaseInvoiceEditorDialog> createState() =>
      _PurchaseInvoiceEditorDialogState();
}

class _PurchaseInvoiceEditorDialogState
    extends State<PurchaseInvoiceEditorDialog> {
  GoodsReceiptRecord? _receipt;
  List<PurchaseInvoiceDraftLine> _lines = const [];
  String _invoiceDate = _today();
  String _supplierInvoiceNumber = '';
  String _supplierInvoiceDate = _today();
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
    final Map<String, double> invoiced = await _invoicedByLine();
    if (!mounted) return;
    setState(() {
      _lines = [
        for (int index = 0; index < receipt.lines.length; index++)
          _draftLine(
            receipt,
            receipt.lines[index],
            index + 1,
            invoiced[receipt.lines[index].id] ?? 0,
          ),
      ];
      _loadingLines = false;
    });
  }

  /// Sum what live bills already charge against each receipt line.
  ///
  /// The server enforces this too -- a bill past the received quantity is
  /// refused -- but it decides after the whole document is typed. Defaulting
  /// to what is left means the common case never meets that refusal. A
  /// cancelled bill charges nothing, so it is not counted.
  Future<Map<String, double>> _invoicedByLine() async {
    final Map<String, double> invoiced = <String, double>{};
    try {
      final List<Json> rows = await fetchAllPages<Json>((page) async {
        final Json response = await widget.api.documentPage(
          'purchase-invoices',
          page: page,
          pageSize: 100,
        );
        final dynamic data = response['data'];
        final List<Json> items = [
          for (final dynamic row in data is List ? data : const [])
            if (row is Map) Map<String, dynamic>.from(row),
        ];
        return PagedResult<Json>(
          items: items,
          total: pagedTotal(response, fallback: items.length),
        );
      });
      for (final Json row in rows) {
        if (stringValue(row['status']).trim().toUpperCase() == 'CANCELLED') {
          continue;
        }
        for (final dynamic line in (row['lines'] as List<dynamic>? ?? const [])) {
          if (line is! Map) continue;
          final String id = stringValue(line['source_document_line_id']);
          if (id.isEmpty) continue;
          invoiced[id] = (invoiced[id] ?? 0) +
              (double.tryParse(
                      stringValue(line['current_invoice_quantity'])) ??
                  0);
        }
      }
    } on ApiException catch (exception) {
      _error = 'Could not read earlier bills: ${exception.message}. '
          'Quantities default to the full receipt.';
    }
    return invoiced;
  }

  PurchaseInvoiceDraftLine _draftLine(
    GoodsReceiptRecord receipt,
    GoodsReceiptLine line,
    int lineNumber,
    double alreadyInvoiced,
  ) {
    final PurchaseInvoiceDraftLine draft = PurchaseInvoiceDraftLine(
      sourceDocumentId: receipt.id,
      sourceDocumentLineId: line.id,
      lineNumber: lineNumber,
      productId: line.productId,
      description: line.description,
      receivedQuantity: line.acceptedQuantity,
      alreadyInvoiced: _trim(alreadyInvoiced),
      receiptUnitPrice: line.unitPrice,
      purchaseUomId: line.purchaseUomId,
      taxProfileId: line.taxProfileId,
      warehouseId: line.warehouseId,
      batchNumber: line.batchNumber,
      invoiceQuantity: '0',
    );
    draft.invoiceQuantity = _trim(draft.outstanding);
    return draft;
  }

  static String _trim(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : '$value';

  List<PurchaseInvoiceDraftLine> _sendableLines() => [
        for (final PurchaseInvoiceDraftLine line in _lines)
          if ((double.tryParse(line.invoiceQuantity) ?? 0) > 0) line,
      ];

  String? _validation() {
    if (_receipt == null) return 'Choose the goods receipt being billed.';
    if (_supplierInvoiceNumber.trim().isEmpty) {
      return "Enter the supplier's invoice number.";
    }
    if (_supplierInvoiceDate.trim().isEmpty) {
      return "Enter the supplier's invoice date.";
    }
    if (_invoiceDate.trim().isEmpty) return 'Enter the invoice date.';
    final List<PurchaseInvoiceDraftLine> sending = _sendableLines();
    if (sending.isEmpty) {
      return 'Enter a quantity on at least one line.';
    }
    for (final PurchaseInvoiceDraftLine line in sending) {
      final double billing = double.tryParse(line.invoiceQuantity) ?? 0;
      if (billing > line.outstanding) {
        return 'Line ${line.lineNumber}: quantity exceeds what the receipt '
            'still has to be billed for (${_trim(line.outstanding)}).';
      }
      final String price = line.unitPrice.trim();
      if (price.isNotEmpty && (double.tryParse(price) ?? -1) < 0) {
        return 'Line ${line.lineNumber}: the unit price must be a number of '
            'zero or more, or blank to take the receipt price.';
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
      final List<PurchaseInvoiceDraftLine> sending = _sendableLines();
      // No vendor or branch: the server takes both from the receipt, and a
      // copy sent from here is one more thing that can disagree with it.
      final Json payload = {
        'invoice_date': _invoiceDate.trim(),
        'supplier_invoice_number': _supplierInvoiceNumber.trim(),
        'supplier_invoice_date': _supplierInvoiceDate.trim(),
        if (_remarks.trim().isNotEmpty) 'remarks': _remarks.trim(),
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
      final Json response = await widget.api.createPurchaseInvoice(payload);
      if (!mounted) return;
      final dynamic data = response['data'];
      Navigator.pop(context, data is Json ? data : response);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = refusalMessage(exception);
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: 'New Purchase Invoice',
        subtitle: _receipt == null
            ? 'Choose the goods receipt being billed'
            : 'Against ${_receipt!.grnNumber}',
        icon: Icons.request_quote_outlined,
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
                label: const Text('Save Invoice'),
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
                title: 'Supplier Bill',
                description:
                    'Which delivery is being billed, and what the supplier '
                    'wrote on the bill.',
              ),
              const SizedBox(height: AppSpacing.md),
              _headerFields(),
              const SizedBox(height: AppSpacing.xl),
              SectionHeader(
                title: 'Items Billed',
                description: _receipt == null
                    ? 'Lines appear once a goods receipt is chosen.'
                    : 'Lines come from the receipt, at what it still has to '
                        'be billed for. A blank price takes the receipt '
                        'price; type one only where the bill differs.',
              ),
              const SizedBox(height: AppSpacing.md),
              if (_receipt == null)
                const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No goods receipt chosen',
                  message: 'A bill charges for what a receipt brought in, so '
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
            width: AppDimensions.documentPickerWidth,
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
          _text('Supplier Invoice Number *', _supplierInvoiceNumber,
              (value) => _supplierInvoiceNumber = value, 'As printed on the bill'),
          _text('Supplier Invoice Date *', _supplierInvoiceDate,
              (value) => _supplierInvoiceDate = value, 'YYYY-MM-DD'),
          _text('Invoice Date *', _invoiceDate, (value) => _invoiceDate = value,
              'YYYY-MM-DD'),
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
        for (final PurchaseInvoiceDraftLine line in _lines) ...[
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
                        'Received ${line.receivedQuantity} · already billed '
                        '${line.alreadyInvoiced}',
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
                        'Billing *',
                        line.invoiceQuantity,
                        (value) => line.invoiceQuantity = value,
                        width: 130,
                      ),
                      _lineField(
                        'Unit Price',
                        line.unitPrice,
                        (value) => line.unitPrice = value,
                        width: 180,
                        helper: line.receiptUnitPrice.isEmpty
                            ? 'Blank takes the receipt price'
                            : 'Blank takes ${line.receiptUnitPrice}',
                      ),
                      _lineField(
                        'Remarks',
                        line.remarks,
                        (value) => line.remarks = value,
                        width: 240,
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

  Widget _lineField(
    String label,
    String value,
    ValueChanged<String> onChanged, {
    required double width,
    String? helper,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          decoration: InputDecoration(labelText: label, helperText: helper),
          onChanged: (next) => setState(() => onChanged(next)),
        ),
      );
}
