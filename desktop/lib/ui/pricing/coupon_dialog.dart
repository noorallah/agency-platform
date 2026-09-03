// Minting a code somebody presents to claim an offer.
//
// A coupon is a *way of reaching* an offer, not a second kind of one: the
// benefit, the conditions and the stacking rule all live on the promotion.
// This form therefore asks for a promotion and a code, and then only for the
// limits that decide who may reach it and how often -- there is deliberately
// no discount field here, because a coupon that carried its own benefit would
// be a second place to look when somebody asks why a price is what it is.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../workspace/desktop_framework.dart';

/// Create a coupon, or change the limits on one that exists.
class CouponDialog extends StatefulWidget {
  const CouponDialog({
    super.key,
    required this.api,
    required this.promotions,
    this.existing,
  });

  final ApiClient api;

  /// The offers a coupon can point at. Chosen when it is minted and fixed
  /// afterwards, because a code on a leaflet promises one thing.
  final List<PromotionRecord> promotions;

  final PromotionCouponRecord? existing;

  @override
  State<CouponDialog> createState() => _CouponDialogState();
}

class _CouponDialogState extends State<CouponDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  late final TextEditingController _code =
      TextEditingController(text: widget.existing?.code ?? '');
  late final TextEditingController _description =
      TextEditingController(text: widget.existing?.description ?? '');
  late final TextEditingController _total = TextEditingController(
      text: widget.existing?.maxRedemptions?.toString() ?? '');
  late final TextEditingController _perCustomer = TextEditingController(
      text: widget.existing?.maxRedemptionsPerCustomer?.toString() ?? '');
  late final TextEditingController _from =
      TextEditingController(text: widget.existing?.effectiveFrom ?? '');
  late final TextEditingController _to =
      TextEditingController(text: widget.existing?.effectiveTo ?? '');

  late String _promotionId = widget.existing?.promotionId ??
      (widget.promotions.isEmpty ? '' : widget.promotions.first.id);
  late String _status = widget.existing?.status ?? 'ACTIVE';
  bool _saving = false;
  String? _error;

  bool get _isNew => widget.existing == null;

  @override
  void dispose() {
    // Owned here, not by the caller: disposing after `showDialog` returns
    // disposes mid-animation, with the fields still rebuilding.
    _code.dispose();
    _description.dispose();
    _total.dispose();
    _perCustomer.dispose();
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  /// A blank limit means no limit, which is a real answer rather than zero.
  int? _limit(TextEditingController field) {
    final String text = field.text.trim();
    return text.isEmpty ? null : int.tryParse(text);
  }

  String? _validateLimit(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final int? parsed = int.tryParse(text);
    // Zero would mean a coupon nobody can use, which nobody means.
    if (parsed == null || parsed < 1) return 'A whole number, or blank for none';
    return null;
  }

  String? _validateDate(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    return DateTime.tryParse(text) == null ? 'YYYY-MM-DD, or blank' : null;
  }

  Json _payload() => <String, dynamic>{
        'promotion_id': _promotionId,
        'code': _code.text.trim(),
        'description': _description.text.trim(),
        'status': _status,
        // Sent explicitly, including as null: the server reads an absent
        // field as "leave it alone" and an explicit null as "clear it", so a
        // form that shows every limit has to say what each one now is or
        // emptying a box would do nothing.
        'max_redemptions': _limit(_total),
        'max_redemptions_per_customer': _limit(_perCustomer),
        'effective_from': _from.text.trim().isEmpty ? null : _from.text.trim(),
        'effective_to': _to.text.trim().isEmpty ? null : _to.text.trim(),
      };

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      if (_isNew) {
        await widget.api.createPromotionCoupon(_payload());
      } else {
        await widget.api.updatePromotionCoupon(
          widget.existing!.id,
          _payload(),
          expectedVersion: widget.existing!.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.isConflict
            ? concurrencyMessage('coupon', changesKept: true)
            : error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: _isNew ? 'New coupon' : 'Coupon ${widget.existing!.code}',
        subtitle: 'A code that reaches an offer. The benefit stays on the '
            'offer.',
        icon: Icons.confirmation_number_outlined,
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Form(
            key: _form,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null) ...[
                  Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                  const SizedBox(height: AppSpacing.sm),
                ],
                DropdownButtonFormField<String>(
                  initialValue: _promotionId.isEmpty ? null : _promotionId,
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Offer',
                    helperText: 'What the code gives. Fixed once the coupon '
                        'exists — a code on a leaflet promises one thing.',
                    helperMaxLines: 2,
                  ),
                  items: [
                    for (final PromotionRecord promotion in widget.promotions)
                      DropdownMenuItem<String>(
                        value: promotion.id,
                        child: Text('${promotion.code} — ${promotion.name}',
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: _isNew
                      ? (value) =>
                          setState(() => _promotionId = value ?? _promotionId)
                      : null,
                  validator: (value) =>
                      (value ?? '').isEmpty ? 'Choose the offer' : null,
                ),
                const SizedBox(height: AppSpacing.sm),
                TextFormField(
                  controller: _code,
                  // Fixed once minted: a claim already made names it.
                  enabled: _isNew,
                  textCapitalization: TextCapitalization.characters,
                  decoration: InputDecoration(
                    labelText: 'Code',
                    helperText: _isNew
                        ? 'What the customer presents. Cannot be changed later.'
                        : 'Fixed: claims already made name this code.',
                    helperMaxLines: 2,
                  ),
                  validator: (value) => (value ?? '').trim().isEmpty
                      ? 'A coupon needs a code'
                      : null,
                ),
                const SizedBox(height: AppSpacing.sm),
                TextFormField(
                  controller: _description,
                  decoration: const InputDecoration(labelText: 'Description'),
                ),
                const SizedBox(height: AppSpacing.sm),
                DropdownButtonFormField<String>(
                  initialValue: _status,
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: const [
                    DropdownMenuItem(value: 'DRAFT', child: Text('Draft')),
                    DropdownMenuItem(value: 'ACTIVE', child: Text('Active')),
                    DropdownMenuItem(value: 'INACTIVE', child: Text('Inactive')),
                  ],
                  onChanged: (value) => setState(() => _status = value ?? _status),
                ),
                const SizedBox(height: AppSpacing.sm),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _total,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Total claims allowed',
                          helperText: 'Blank for no limit.',
                        ),
                        validator: _validateLimit,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: TextFormField(
                        controller: _perCustomer,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Per customer',
                          helperText: 'Blank for no limit.',
                        ),
                        validator: _validateLimit,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _from,
                        decoration: const InputDecoration(
                          labelText: 'Live from',
                          helperText: 'YYYY-MM-DD. Blank for no start.',
                        ),
                        validator: _validateDate,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: TextFormField(
                        controller: _to,
                        decoration: const InputDecoration(
                          labelText: 'Live until',
                          helperText: 'YYYY-MM-DD. Blank for no end.',
                        ),
                        validator: _validateDate,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.md),
                Text(
                  'Only an approved document claims a coupon, so a limit '
                  'counts what was actually taken up rather than every draft '
                  'that quoted it.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
        onClose: () => Navigator.of(context).pop(false),
        onSave: _saving ? null : _save,
        saveLabel: _isNew ? 'Create' : 'Save',
      );
}
