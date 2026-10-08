import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/product.dart';
import '../workspace/save_in_dialog.dart';

/// The two defaults a firm sets on a goods type -- shared or its own: the HSN
/// code and the tax group a new product of the type starts with.
///
/// Saves through the type's `/use` route with `in_use: true`, so setting
/// defaults on a type also takes it into use. The dialog runs the save itself
/// and stays open with the server's message on a refusal.
Future<bool> showGoodsTypeDefaultsDialog(
  BuildContext context, {
  required ApiClient api,
  required GoodsTypeRecord type,
}) async =>
    (await showDialog<bool>(
      context: context,
      builder: (context) => SelectionArea(
        child: _GoodsTypeDefaultsDialog(api: api, type: type),
      ),
    )) ??
    false;

class _GoodsTypeDefaultsDialog extends StatefulWidget {
  const _GoodsTypeDefaultsDialog({required this.api, required this.type});

  final ApiClient api;
  final GoodsTypeRecord type;

  @override
  State<_GoodsTypeDefaultsDialog> createState() =>
      _GoodsTypeDefaultsDialogState();
}

class _GoodsTypeDefaultsDialogState extends State<_GoodsTypeDefaultsDialog>
    with SaveInDialog<_GoodsTypeDefaultsDialog> {
  late final TextEditingController _hsn =
      TextEditingController(text: widget.type.defaultHsnSac);
  late final TextEditingController _taxGroup =
      TextEditingController(text: widget.type.defaultTaxProfileGroupCode);

  @override
  void dispose() {
    _hsn.dispose();
    _taxGroup.dispose();
    super.dispose();
  }

  String? _blankToNull(String text) {
    final String trimmed = text.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  Future<void> _save() => saveAndClose<bool>(() async {
        await widget.api.useGoodsType(widget.type.id, {
          'in_use': true,
          'default_hsn_sac': _blankToNull(_hsn.text),
          'default_tax_profile_group_code': _blankToNull(_taxGroup.text),
        });
        return true;
      });

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Defaults for ${widget.type.name}'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                Text(
                  'Filled into a new product of this type; the person can '
                  'change it.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('goods-type-defaults-hsn'),
                  controller: _hsn,
                  decoration:
                      const InputDecoration(labelText: 'Default HSN code'),
                ),
                const SizedBox(height: AppSpacing.md),
                TextField(
                  key: const ValueKey('goods-type-defaults-tax-group'),
                  controller: _taxGroup,
                  decoration:
                      const InputDecoration(labelText: 'Default tax group'),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('goods-type-defaults-save'),
            onPressed: saving ? null : _save,
            child: const Text('Save'),
          ),
        ],
      );
}
