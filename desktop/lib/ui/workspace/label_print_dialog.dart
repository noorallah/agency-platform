// Barcode labels (STK-16): pick the label stock, say how much of a part-used
// sheet is gone, and print the PDF the server lays out.
//
// Shared by the Products screen (a copies box per product) and the Goods
// Receipts screen (one label per piece received).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import 'balance_confirmation.dart' show OpenPdfOverride;
import 'printed_document.dart';
import 'save_in_dialog.dart';

/// One product whose labels are asked for.
class LabelProduct {
  const LabelProduct({required this.id, required this.name});

  final String id;
  final String name;
}

/// The label stocks the server lays out, and how many labels one sheet holds
/// (0 for a roll, which has no sheet to part-use).
const List<({String code, String label, int perSheet})> labelLayouts = [
  (code: 'A4_65', label: 'A4 sheet, 65 labels (38 x 21 mm)', perSheet: 65),
  (code: 'A4_24', label: 'A4 sheet, 24 labels (64 x 34 mm)', perSheet: 24),
  (code: 'ROLL_50X25', label: 'Thermal roll 50 x 25 mm', perSheet: 0),
];

/// Name [products] for a product print, or [receiptId] for a receipt's.
class LabelPrintDialog extends StatefulWidget {
  const LabelPrintDialog({
    super.key,
    required this.api,
    required this.subtitle,
    this.products = const [],
    this.receiptId,
    this.openPdfOverride,
  }) : assert(receiptId != null || products.length > 0);

  final ApiClient api;

  /// What the labels are for, e.g. the receipt number or the product count.
  final String subtitle;
  final List<LabelProduct> products;
  final String? receiptId;

  /// Tests inject one, because a widget test cannot open a print dialog.
  final OpenPdfOverride? openPdfOverride;

  @override
  State<LabelPrintDialog> createState() => _LabelPrintDialogState();
}

class _LabelPrintDialogState extends State<LabelPrintDialog>
    with SaveInDialog<LabelPrintDialog> {
  String _layout = labelLayouts.first.code;
  bool _showPrice = true;
  final TextEditingController _skip = TextEditingController(text: '0');
  late final Map<String, TextEditingController> _copies = {
    for (final LabelProduct product in widget.products)
      product.id: TextEditingController(text: '1'),
  };
  String? _fieldError;

  int get _perSheet =>
      labelLayouts.firstWhere((layout) => layout.code == _layout).perSheet;

  @override
  void dispose() {
    _skip.dispose();
    for (final TextEditingController box in _copies.values) {
      box.dispose();
    }
    super.dispose();
  }

  /// The skip as the server will read it: a roll has no sheet to part-use.
  int get _skipCount => _perSheet == 0 ? 0 : int.tryParse(_skip.text) ?? -1;

  String? _check() {
    if (_perSheet > 0 && (_skipCount < 0 || _skipCount >= _perSheet)) {
      return 'Labels already used must be 0 to ${_perSheet - 1}.';
    }
    for (final LabelProduct product in widget.products) {
      final int? copies = int.tryParse(_copies[product.id]!.text);
      if (copies == null || copies < 1 || copies > 5000) {
        return 'Copies of ${product.name} must be 1 to 5000.';
      }
    }
    return null;
  }

  Future<void> _print() async {
    final String? problem = _check();
    if (problem != null) {
      setState(() => _fieldError = problem);
      return;
    }
    setState(() => _fieldError = null);
    final String name = widget.receiptId != null
        ? 'Labels ${widget.subtitle}'
        : 'Product labels';
    await saveAndClose<bool>(() async {
      final List<int> pdf = widget.receiptId != null
          ? await widget.api.goodsReceiptLabelsPdf(
              widget.receiptId!,
              layout: _layout,
              skip: _skipCount,
              showPrice: _showPrice,
            )
          : await widget.api.productLabelsPdf(
              items: [
                for (final LabelProduct product in widget.products)
                  {
                    'product_id': product.id,
                    'copies': int.parse(_copies[product.id]!.text),
                  },
              ],
              layout: _layout,
              skip: _skipCount,
              showPrice: _showPrice,
            );
      if (!mounted) return false;
      if (widget.openPdfOverride != null) {
        await widget.openPdfOverride!(name, pdf);
      } else {
        await printDocument(context, bytes: pdf, documentName: name);
      }
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? shown = _fieldError;
    return AlertDialog(
      title: Text('Print labels · ${widget.subtitle}'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (shown != null)
                Container(
                  key: const ValueKey<String>('label-field-error'),
                  margin: const EdgeInsets.only(bottom: AppSpacing.md),
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: theme.colorScheme.errorContainer,
                  child: Text(
                    shown,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              DropdownButtonFormField<String>(
                key: const ValueKey<String>('label-layout'),
                initialValue: _layout,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Label stock'),
                items: [
                  for (final layout in labelLayouts)
                    DropdownMenuItem<String>(
                      value: layout.code,
                      child: Text(layout.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: saving
                    ? null
                    : (String? value) =>
                        setState(() => _layout = value ?? _layout),
              ),
              if (_perSheet > 0) ...[
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey<String>('label-skip'),
                  controller: _skip,
                  enabled: !saving,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(
                    labelText: 'Labels already used on the sheet',
                    helperText: 'A partly used sheet can be fed again: the '
                        'first labels are left blank (0 to ${_perSheet - 1}).',
                    helperMaxLines: 2,
                  ),
                ),
              ],
              SwitchListTile(
                key: const ValueKey<String>('label-show-price'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Print our price'),
                subtitle: const Text('The MRP always prints.'),
                value: _showPrice,
                onChanged: saving
                    ? null
                    : (bool value) => setState(() => _showPrice = value),
              ),
              if (widget.receiptId != null)
                const Padding(
                  padding: EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(
                    'One label is printed for every piece received, with its '
                    'batch and expiry.',
                  ),
                ),
              for (final LabelProduct product in widget.products)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          product.name,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      SizedBox(
                        width: 110,
                        child: TextField(
                          key: ValueKey<String>('label-copies-${product.id}'),
                          controller: _copies[product.id],
                          enabled: !saving,
                          keyboardType: TextInputType.number,
                          inputFormatters: [
                            FilteringTextInputFormatter.digitsOnly,
                          ],
                          decoration: const InputDecoration(labelText: 'Copies'),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey<String>('label-print'),
          onPressed: saving ? null : _print,
          child: const Text('Print'),
        ),
      ],
    );
  }
}
