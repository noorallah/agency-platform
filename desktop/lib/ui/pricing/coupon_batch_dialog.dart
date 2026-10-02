// Bulk single-use coupon codes (SEL-5): pick an offer, say how many, and the
// server mints that many unguessable codes, each claimable once. The codes
// themselves are not listed here -- a few thousand of them are for a printer,
// so the dialog offers the offer's CSV instead.

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/pricing.dart';
import '../workspace/master_import_dialog.dart' show SaveBytesOverride;
import '../workspace/save_in_dialog.dart';

/// Fetch an offer's codes as CSV and save them where the user chooses, saying
/// what the server said when it refuses. Tests inject [saveBytesOverride],
/// because a widget test cannot open a save panel.
Future<void> saveCouponCodesCsv(
  BuildContext context,
  ApiClient api,
  PromotionRecord offer, {
  SaveBytesOverride? saveBytesOverride,
}) async {
  try {
    final List<int> csv = await api.exportCouponsCsv(offer.id);
    if (!context.mounted) return;
    final String name = 'Coupons ${offer.code}.csv';
    if (saveBytesOverride != null) {
      await saveBytesOverride(name, csv);
    } else {
      final FileSaveLocation? location = await getSaveLocation(
        suggestedName: name,
        acceptedTypeGroups: const [
          XTypeGroup(label: 'CSV file', extensions: ['csv']),
        ],
      );
      if (location == null) return;
      await File(location.path).writeAsBytes(csv, flush: true);
    }
    if (!context.mounted) return;
    NotificationService.show(
      context,
      'The codes were saved.',
      kind: AppNotificationKind.success,
    );
  } on ApiException catch (error) {
    if (!context.mounted) return;
    NotificationService.show(
      context,
      error.message,
      kind: AppNotificationKind.error,
    );
  }
}

/// Generate a batch of single-use codes for one of [promotions]. Closes with
/// `true` once codes were generated, so the caller reloads its list.
class CouponBatchDialog extends StatefulWidget {
  const CouponBatchDialog({
    super.key,
    required this.api,
    required this.promotions,
    this.initialPromotionId,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final List<PromotionRecord> promotions;
  final String? initialPromotionId;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<CouponBatchDialog> createState() => _CouponBatchDialogState();
}

class _CouponBatchDialogState extends State<CouponBatchDialog>
    with SaveInDialog<CouponBatchDialog> {
  final TextEditingController _count = TextEditingController(text: '100');
  final TextEditingController _prefix = TextEditingController();
  final TextEditingController _description = TextEditingController();
  final TextEditingController _from = TextEditingController();
  final TextEditingController _to = TextEditingController();
  late String _promotionId = widget.promotions
          .any((offer) => offer.id == widget.initialPromotionId)
      ? widget.initialPromotionId!
      : (widget.promotions.isEmpty ? '' : widget.promotions.first.id);
  String? _fieldError;
  int? _generated;

  @override
  void dispose() {
    _count.dispose();
    _prefix.dispose();
    _description.dispose();
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  PromotionRecord? get _offer => widget.promotions
      .where((offer) => offer.id == _promotionId)
      .firstOrNull;

  String? _check() {
    final int? count = int.tryParse(_count.text.trim());
    if (count == null || count < 1 || count > 5000) {
      return 'How many must be 1 to 5000.';
    }
    for (final TextEditingController date in [_from, _to]) {
      final String text = date.text.trim();
      if (text.isNotEmpty && DateTime.tryParse(text) == null) {
        return 'Dates are YYYY-MM-DD, or blank.';
      }
    }
    return _promotionId.isEmpty ? 'Choose the offer.' : null;
  }

  Future<void> _generate() async {
    final String? problem = _check();
    if (problem != null) {
      setState(() => _fieldError = problem);
      return;
    }
    setState(() {
      _fieldError = null;
      saving = true;
      saveError = null;
    });
    try {
      final List<String> codes = await widget.api.generateCoupons(
        _promotionId,
        count: int.parse(_count.text.trim()),
        prefix: _prefix.text.trim(),
        description: _description.text.trim(),
        effectiveFrom: _from.text.trim(),
        effectiveTo: _to.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        saving = false;
        _generated = codes.length;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = exception.message;
      });
    }
  }

  Widget _done() => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$_generated codes generated',
            key: const ValueKey<String>('coupon-batch-done'),
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: AppSpacing.sm),
          const Text(
            'Each code can be claimed once. Save them as a CSV to print or '
            'send out; the same file is available later from Export codes.',
          ),
        ],
      );

  Widget _form(ThemeData theme) {
    final String? shown = _fieldError;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        saveErrorBanner(),
        if (shown != null)
          Container(
            key: const ValueKey<String>('coupon-batch-field-error'),
            margin: const EdgeInsets.only(bottom: AppSpacing.md),
            padding: const EdgeInsets.all(AppSpacing.md),
            color: theme.colorScheme.errorContainer,
            child: Text(
              shown,
              style: TextStyle(color: theme.colorScheme.onErrorContainer),
            ),
          ),
        DropdownButtonFormField<String>(
          key: const ValueKey<String>('coupon-batch-offer'),
          initialValue: _promotionId.isEmpty ? null : _promotionId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Offer'),
          items: [
            for (final PromotionRecord offer in widget.promotions)
              DropdownMenuItem<String>(
                value: offer.id,
                child: Text('${offer.code} — ${offer.name}',
                    overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: saving
              ? null
              : (String? value) =>
                  setState(() => _promotionId = value ?? _promotionId),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const ValueKey<String>('coupon-batch-count'),
                controller: _count,
                enabled: !saving,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                  labelText: 'How many',
                  helperText: '1 to 5000 in one go.',
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: TextField(
                key: const ValueKey<String>('coupon-batch-prefix'),
                controller: _prefix,
                enabled: !saving,
                textCapitalization: TextCapitalization.characters,
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]')),
                  LengthLimitingTextInputFormatter(12),
                ],
                decoration: const InputDecoration(
                  labelText: 'Prefix',
                  helperText: 'Optional, up to 12 letters or digits.',
                  helperMaxLines: 2,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        TextField(
          key: const ValueKey<String>('coupon-batch-description'),
          controller: _description,
          enabled: !saving,
          decoration: const InputDecoration(labelText: 'Description'),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const ValueKey<String>('coupon-batch-from'),
                controller: _from,
                enabled: !saving,
                decoration: const InputDecoration(
                  labelText: 'Live from',
                  helperText: 'YYYY-MM-DD. Blank for no start.',
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: TextField(
                key: const ValueKey<String>('coupon-batch-to'),
                controller: _to,
                enabled: !saving,
                decoration: const InputDecoration(
                  labelText: 'Live until',
                  helperText: 'YYYY-MM-DD. Blank for no end.',
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool done = _generated != null;
    return AlertDialog(
      title: const Text('Generate coupon codes'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: done ? _done() : _form(Theme.of(context)),
        ),
      ),
      actions: [
        if (done) ...[
          OutlinedButton(
            key: const ValueKey<String>('coupon-batch-save-csv'),
            onPressed: () => saveCouponCodesCsv(
              context,
              widget.api,
              _offer!,
              saveBytesOverride: widget.saveBytesOverride,
            ),
            child: const Text('Save as CSV'),
          ),
          FilledButton(
            key: const ValueKey<String>('coupon-batch-close'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Close'),
          ),
        ] else ...[
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey<String>('coupon-batch-generate'),
            onPressed: saving ? null : _generate,
            child: const Text('Generate'),
          ),
        ],
      ],
    );
  }
}
