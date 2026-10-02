// Copy last season's offers with new dates (SEL-8): the chosen offers are
// copied as drafts with a suffix on each code, so DIWALI becomes DIWALI-26.
// A refusal -- a code already taken, a backwards window -- stays in the dialog
// with everything typed.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/pricing.dart';
import '../workspace/save_in_dialog.dart';

/// Copy [promotions] with a new window. Closes with the list of copies once
/// the server has made them, so the caller reloads its list.
class PromotionCopyDialog extends StatefulWidget {
  const PromotionCopyDialog({
    super.key,
    required this.api,
    required this.promotions,
  });

  final ApiClient api;
  final List<PromotionRecord> promotions;

  @override
  State<PromotionCopyDialog> createState() => _PromotionCopyDialogState();
}

class _PromotionCopyDialogState extends State<PromotionCopyDialog>
    with SaveInDialog<PromotionCopyDialog> {
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  final TextEditingController _suffix = TextEditingController();

  /// Once the person types a suffix themselves, the From year stops
  /// overwriting it.
  bool _suffixEdited = false;
  String? _fieldError;

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    _suffix.dispose();
    super.dispose();
  }

  void _fromChanged(String text) {
    if (_suffixEdited) return;
    final DateTime? date = DateTime.tryParse(text.trim());
    final String year =
        date == null ? '' : (date.year % 100).toString().padLeft(2, '0');
    setState(() => _suffix.text = date == null ? '' : '-$year');
  }

  String? _check() {
    final DateTime? from = DateTime.tryParse(_from.text.trim());
    final DateTime? to = DateTime.tryParse(_to.text.trim());
    if (from == null || to == null) {
      return 'Both dates are needed, as YYYY-MM-DD.';
    }
    if (to.isBefore(from)) return 'Until cannot be before From.';
    if (_suffix.text.trim().isEmpty) {
      return 'A code suffix is needed, so the copies get codes of their own.';
    }
    return null;
  }

  Future<void> _copy() async {
    final String? problem = _check();
    if (problem != null) {
      setState(() => _fieldError = problem);
      return;
    }
    setState(() => _fieldError = null);
    await saveAndClose<List<PromotionRecord>>(
      () => widget.api.copyPromotions(
        [for (final PromotionRecord offer in widget.promotions) offer.id],
        effectiveFrom: DateTime.parse(_from.text.trim()),
        effectiveTo: DateTime.parse(_to.text.trim()),
        codeSuffix: _suffix.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? shown = _fieldError;
    return AlertDialog(
      title: const Text('Copy with new dates'),
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
                  key: const ValueKey<String>('promotion-copy-field-error'),
                  margin: const EdgeInsets.only(bottom: AppSpacing.md),
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: theme.colorScheme.errorContainer,
                  child: Text(
                    shown,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              Text('Offers to copy', style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.xs),
              Text(
                widget.promotions.map((offer) => offer.code).join(', '),
                key: const ValueKey<String>('promotion-copy-codes'),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      key: const ValueKey<String>('promotion-copy-from'),
                      controller: _from,
                      enabled: !saving,
                      onChanged: _fromChanged,
                      decoration: const InputDecoration(
                        labelText: 'From',
                        helperText: 'YYYY-MM-DD',
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: TextField(
                      key: const ValueKey<String>('promotion-copy-to'),
                      controller: _to,
                      enabled: !saving,
                      decoration: const InputDecoration(
                        labelText: 'Until',
                        helperText: 'YYYY-MM-DD',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                key: const ValueKey<String>('promotion-copy-suffix'),
                controller: _suffix,
                enabled: !saving,
                onChanged: (_) => _suffixEdited = true,
                decoration: const InputDecoration(
                  labelText: 'Code suffix',
                  helperText: 'DIWALI becomes DIWALI-26; copies start as drafts',
                  helperMaxLines: 2,
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey<String>('promotion-copy-save'),
          onPressed: saving ? null : _copy,
          child: const Text('Copy'),
        ),
      ],
    );
  }
}
