// Correct a customer's loyalty balance by hand, saying why.
//
// The route has existed since the scheme was built; no screen called it
// (D-QA-8), so a goodwill grant or a points-credited-in-error correction could
// only be made through the API. Points are signed: positive grants, negative
// takes back. The reason is required and lands on the ledger entry.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer.dart';

/// Ask for a customer, a signed number of points and a reason, then post it.
///
/// Pops `true` once the adjustment is recorded.
class LoyaltyAdjustDialog extends StatefulWidget {
  const LoyaltyAdjustDialog({
    super.key,
    required this.api,
    this.customerId,
    this.customerName,
  });

  final ApiClient api;

  /// The customer the page already had chosen, if any.
  final String? customerId;
  final String? customerName;

  @override
  State<LoyaltyAdjustDialog> createState() => _LoyaltyAdjustDialogState();
}

class _LoyaltyAdjustDialogState extends State<LoyaltyAdjustDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _points = TextEditingController();
  final TextEditingController _reason = TextEditingController();
  late String? _customerId = widget.customerId;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _points.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<Iterable<Customer>> _search(TextEditingValue value) async {
    final String text = value.text.trim();
    if (text.length < 2) return const <Customer>[];
    try {
      return (await widget.api.customers(search: text, pageSize: 20)).items;
    } on ApiException {
      return const <Customer>[];
    }
  }

  static String _label(Customer customer) =>
      '${customer.code} - ${customer.name}';

  String? _validatePoints(String? value) {
    final num? parsed = num.tryParse(value?.trim() ?? '');
    if (parsed == null || parsed == 0) {
      return 'A number other than zero: positive grants, negative takes back';
    }
    return null;
  }

  Future<void> _save() async {
    if (_customerId == null) {
      setState(() => _error = 'Choose the customer whose balance to correct.');
      return;
    }
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.adjustLoyalty(
        customerId: _customerId!,
        points: _points.text.trim(),
        reason: _reason.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Adjust points'),
        content: SizedBox(
          width: 480,
          child: Form(
            key: _form,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Autocomplete<Customer>(
                  key: const ValueKey('loyalty-adjust-customer'),
                  initialValue: TextEditingValue(
                    text: widget.customerName ?? '',
                  ),
                  optionsBuilder: _search,
                  displayStringForOption: _label,
                  onSelected: (customer) =>
                      setState(() => _customerId = customer.id),
                  fieldViewBuilder:
                      (context, controller, focusNode, onSubmitted) =>
                          TextField(
                    controller: controller,
                    focusNode: focusNode,
                    decoration: const InputDecoration(
                      labelText: 'Customer',
                      helperText: 'Type two letters of the name or code',
                    ),
                    // Typing again means the earlier pick no longer stands.
                    onChanged: (_) {
                      if (_customerId != null) {
                        setState(() => _customerId = null);
                      }
                    },
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                TextFormField(
                  key: const ValueKey('loyalty-adjust-points'),
                  controller: _points,
                  validator: _validatePoints,
                  decoration: const InputDecoration(
                    labelText: 'Points',
                    helperText: 'Positive grants points; negative takes '
                        'back points credited in error',
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                TextFormField(
                  key: const ValueKey('loyalty-adjust-reason'),
                  controller: _reason,
                  maxLines: 2,
                  validator: (value) => (value?.trim().isEmpty ?? true)
                      ? 'Say why, so the ledger can answer later'
                      : null,
                  decoration: const InputDecoration(labelText: 'Reason'),
                ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'Granted points cost the firm when they are granted, the '
                  'same as earned ones: the liability moves with the count.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    _error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : () => unawaited(_save()),
            child: const Text('Record adjustment'),
          ),
        ],
      );
}
