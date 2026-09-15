import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';

/// The firm's loyalty scheme: what a point is earned for and what it is worth.
///
/// Reading the scheme needs only `LOYALTY_VIEW`, so anybody who can see a
/// customer's balance can see the rule that produced it. Changing it needs
/// `LOYALTY_MANAGE_SETTINGS`, which is deliberately not granted to
/// `SALES_MANAGER` — the same split as the credit policy and the TCS policy:
/// whoever a scheme constrains must not be able to rewrite what it is worth.
///
/// Until 2026-09-15 there was no screen at all. `PUT /api/v1/loyalty/settings`
/// existed, the permission was seeded and granted, and `api_client.dart`
/// carried only the GET — so the orphan-route guard read the path as reachable
/// (it asks whether a path is named, not whether a *method* is) and a firm
/// administrator could see the scheme and not change it.
class LoyaltySettingsDialog extends StatefulWidget {
  const LoyaltySettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<LoyaltySettingsDialog> createState() => _LoyaltySettingsDialogState();
}

class _LoyaltySettingsDialogState extends State<LoyaltySettingsDialog> {
  final TextEditingController _pointsPer = TextEditingController();
  final TextEditingController _amountPer = TextEditingController();
  final TextEditingController _minimum = TextEditingController();
  final TextEditingController _expiry = TextEditingController();

  bool _enabled = false;
  bool _expires = false;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  bool get _mayManage =>
      widget.permissions.hasPermission('LOYALTY_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pointsPer.dispose();
    _amountPer.dispose();
    _minimum.dispose();
    _expiry.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final Json settings = await widget.api.loyaltySettings();
      if (!mounted) return;
      setState(() {
        _enabled = settings['is_enabled'] == true;
        _pointsPer.text = _trim('${settings['points_per_amount'] ?? 0}');
        _amountPer.text = _trim('${settings['amount_per_point'] ?? 0}');
        _minimum.text = '${settings['minimum_redemption_points'] ?? 0}';
        // Null is a real answer here, not a missing one: points that never
        // expire. The switch is what carries that, so the box below it is
        // only read when the switch is on.
        _expires = settings['expiry_months'] != null;
        _expiry.text = _expires ? '${settings['expiry_months']}' : '12';
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Render `1.0000` as `1` — the server stores a scale nobody types.
  static String _trim(String value) {
    if (!value.contains('.')) return value;
    final String trimmed =
        value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
    return trimmed.isEmpty ? '0' : trimmed;
  }

  /// Say what is wrong, or nothing.
  ///
  /// The server's rules restated, so a mistake is caught while the numbers are
  /// still on screen rather than coming back as a rejection.
  String? _validate() {
    final double? points = double.tryParse(_pointsPer.text.trim());
    final double? amount = double.tryParse(_amountPer.text.trim());
    final int? minimum = int.tryParse(_minimum.text.trim());
    if (points == null || amount == null || minimum == null) {
      return 'Earning, worth and the minimum must all be numbers.';
    }
    if (points < 0 || amount < 0 || minimum < 0) {
      return 'None of these can be negative.';
    }
    if (_expires) {
      final int? months = int.tryParse(_expiry.text.trim());
      if (months == null || months < 1 || months > 600) {
        return 'Expiry must be between 1 and 600 months.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    final String? problem = _validate();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.updateLoyaltySettings(<String, dynamic>{
        'is_enabled': _enabled,
        'points_per_amount': _pointsPer.text.trim(),
        'amount_per_point': _amountPer.text.trim(),
        'minimum_redemption_points': int.parse(_minimum.text.trim()),
        // Sent explicitly either way. Omitting it would mean "leave it alone",
        // which is not what switching expiry off says.
        'expiry_months': _expires ? int.parse(_expiry.text.trim()) : null,
      });
      if (!mounted) return;
      // Announce before popping: the notification reads the theme off this
      // context, and after the pop it is no longer mounted.
      NotificationService.show(
        context,
        'Loyalty scheme saved.',
        kind: AppNotificationKind.success,
      );
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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      icon: const Icon(Icons.card_giftcard_outlined),
      title: const Text('Loyalty scheme'),
      content: SizedBox(
        width: 460,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Applies to every customer in this firm. Points cost the '
                      'firm when they are earned, not when they are spent, so '
                      'the rate decides what the scheme costs.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _enabled,
                      title: const Text('Scheme is running'),
                      subtitle: const Text(
                        'Off: nothing is earned and nothing can be spent. '
                        'Balances already earned are kept.',
                      ),
                      onChanged: _mayManage && !_saving
                          ? (value) => setState(() => _enabled = value)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    Row(
                      children: [
                        Expanded(
                          child: _numberField(
                            controller: _pointsPer,
                            label: 'Points earned',
                            helper: 'Per unit of currency spent',
                            decimal: true,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.lg),
                        Expanded(
                          child: _numberField(
                            controller: _amountPer,
                            label: 'A point is worth',
                            helper: 'When redeemed',
                            decimal: true,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    _numberField(
                      controller: _minimum,
                      label: 'Minimum to redeem',
                      helper: 'Points a customer must hold before spending any',
                      decimal: false,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _expires,
                      title: const Text('Points expire'),
                      subtitle: const Text(
                        'Off: they never lapse. Lapsing reverses what the '
                        'points cost, out of whatever is left of each batch.',
                      ),
                      onChanged: _mayManage && !_saving
                          ? (value) => setState(() => _expires = value)
                          : null,
                    ),
                    if (_expires) ...[
                      const SizedBox(height: AppSpacing.md),
                      _numberField(
                        controller: _expiry,
                        label: 'Expire after',
                        helper: 'Months from the day they were earned',
                        decimal: false,
                      ),
                    ],
                    if (!_mayManage) ...[
                      const SizedBox(height: AppSpacing.lg),
                      _Notice(
                        icon: Icons.lock_outline,
                        text: 'Changing the scheme needs the manage loyalty '
                            'settings permission.',
                      ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: AppSpacing.lg),
                      Text(
                        _error!,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.colorScheme.error),
                      ),
                    ],
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        FilledButton(
          onPressed: _mayManage && !_loading && !_saving ? _save : null,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _numberField({
    required TextEditingController controller,
    required String label,
    required String helper,
    required bool decimal,
  }) =>
      TextField(
        controller: controller,
        enabled: _mayManage && !_saving,
        keyboardType: TextInputType.numberWithOptions(decimal: decimal),
        inputFormatters: [
          FilteringTextInputFormatter.allow(
            decimal ? RegExp(r'[0-9.]') : RegExp(r'[0-9]'),
          ),
        ],
        decoration: InputDecoration(labelText: label, helperText: helper),
      );
}

class _Notice extends StatelessWidget {
  const _Notice({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            text,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      ],
    );
  }
}
