import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/purchase.dart';

/// Which stages of buying this firm's people type, and which the server raises
/// (backlog §38, the twin of the sales stages).
///
/// The chain is purchase order, goods receipt, bill. A firm run by one person
/// types the supplier's bill and nothing else. Switching a stage off never
/// removes the document -- the goods still arrive on a receipt and stock still
/// moves with it -- it means the bill raises that document itself.
///
/// Orders on with receipts off is allowed (the bill receives the goods);
/// receipts on with orders off is not, because a receipt continues an order
/// and nobody would ever have typed one. The switches keep to that as they
/// move, and the server refuses it regardless.
///
/// Reading needs only `PURCHASE_VIEW`. Changing needs
/// `PURCHASE_MANAGE_SETTINGS`, deliberately not granted to purchase roles:
/// turning receipts off means the bill confirms what arrived rather than
/// whoever counted it in.
class PurchaseWorkflowSettingsDialog extends StatefulWidget {
  const PurchaseWorkflowSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<PurchaseWorkflowSettingsDialog> createState() =>
      _PurchaseWorkflowSettingsDialogState();
}

class _PurchaseWorkflowSettingsDialogState
    extends State<PurchaseWorkflowSettingsDialog> {
  PurchaseWorkflowSettings _settings = PurchaseWorkflowSettings.wholeChain;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// True only once the firm's own settings arrived. The switches start from
  /// the whole chain, so saving after a failed read would replace whatever
  /// the firm chose with a chain nobody picked (D-CFG-14): the dialog must
  /// prove it read the settings before it may write them.
  bool _read = false;

  final TextEditingController _percent = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  String? _toleranceError;

  @override
  void dispose() {
    _percent.dispose();
    _amount.dispose();
    super.dispose();
  }

  static String _shown(double? value) {
    if (value == null) return '';
    return value == value.roundToDouble()
        ? value.toStringAsFixed(0)
        : value.toString();
  }

  /// Blank is no check (null); anything else must be a number in range.
  /// Returns false, with [_toleranceError] set, when a box is not valid.
  bool _applyTolerances() {
    final String p = _percent.text.trim();
    final String a = _amount.text.trim();
    final double? percent = p.isEmpty ? null : double.tryParse(p);
    final double? amount = a.isEmpty ? null : double.tryParse(a);
    if (p.isNotEmpty && (percent == null || percent < 0 || percent > 100)) {
      _toleranceError = 'The rate tolerance is a percentage from 0 to 100.';
      return false;
    }
    if (a.isNotEmpty && (amount == null || amount < 0)) {
      _toleranceError = 'The bill tolerance is an amount of 0 or more.';
      return false;
    }
    _toleranceError = null;
    _settings = _settings.copyWith(
      billPriceTolerancePercent: percent,
      clearPercent: percent == null,
      billToleranceAmount: amount,
      clearAmount: amount == null,
    );
    return true;
  }

  bool get _mayManage =>
      widget.permissions.hasPermission('PURCHASE_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _retry() {
    setState(() {
      _loading = true;
      _read = false;
      _error = null;
    });
    _load();
  }

  Future<void> _load() async {
    try {
      final PurchaseWorkflowSettings settings =
          await widget.api.purchaseWorkflowSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _percent.text = _shown(settings.billPriceTolerancePercent);
        _amount.text = _shown(settings.billToleranceAmount);
        _read = true;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'The buying stages could not be read, so they cannot be '
            'saved: ${error.message}';
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    if (!_read) return;
    if (!_applyTolerances()) {
      setState(() {});
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.updatePurchaseWorkflowSettings(_settings);
      if (!mounted) return;
      // Announce before popping: the notification reads the theme off this
      // context, and after the pop it is no longer mounted.
      NotificationService.show(
        context,
        'Buying stages saved.',
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

  /// What the firm's people will actually type, in one sentence.
  String get _summary {
    final List<String> typed = [
      if (_settings.purchaseOrderStage) 'purchase order',
      if (_settings.goodsReceiptStage) 'goods receipt',
      "supplier's bill",
    ];
    if (typed.length == 1) {
      return "One screen: the supplier's bill. The order and the receipt "
          'behind it are raised for you.';
    }
    return 'Your people raise the ${typed.join(', ')}.';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      // An AlertDialog gives its content unbounded height; two switches,
      // four notices and an error overflow a short window without this.
      scrollable: true,
      icon: const Icon(Icons.linear_scale_outlined),
      title: const Text('Buying stages'),
      content: SizedBox(
        width: 520,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Turn off the stages nobody here fills in. They are still '
                    "raised and still recorded — the supplier's bill raises "
                    'them as it saves — so stock, cost and the audit trail '
                    'are unchanged.',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (_read && !_settings.isConfigured) ...[
                    const SizedBox(height: AppSpacing.md),
                    _Notice(
                      icon: Icons.info_outline,
                      text: 'This firm has not chosen, so it is using the '
                          'whole chain shown here. Saving makes it the '
                          "firm's own.",
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  _StageSwitch(
                    label: 'Purchase order',
                    detail: 'What was asked of the supplier, before it '
                        'arrives. Turning this off turns receipts off too: '
                        'a receipt continues an order.',
                    value: _settings.purchaseOrderStage,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings = _settings.copyWith(
                        purchaseOrderStage: value,
                        goodsReceiptStage: value ? null : false,
                      ),
                    ),
                  ),
                  _StageSwitch(
                    label: 'Goods receipt',
                    detail: 'Confirms what arrived. Turning this off means '
                        "the supplier's bill confirms it instead.",
                    value: _settings.goodsReceiptStage,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings = _settings.copyWith(
                        goodsReceiptStage: value,
                        purchaseOrderStage: value ? true : null,
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  _Notice(icon: Icons.receipt_long_outlined, text: _summary),
                  if (!_settings.goodsReceiptStage) ...[
                    const SizedBox(height: AppSpacing.md),
                    _Notice(
                      icon: Icons.warehouse_outlined,
                      text: _settings.purchaseOrderStage
                          ? 'A bill names the approved order it is for, and '
                              'saving it receives the goods into the '
                              "order's warehouse."
                          : 'Goods come into this firm’s default branch and '
                              'warehouse. Without those, a bill cannot decide '
                              'where its stock goes.',
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  Text('Bill matching', style: theme.textTheme.titleSmall),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'A supplier bill priced past either limit over its order '
                    'is refused at approval, unless the approver may approve '
                    'over tolerance. Leave a box blank for no check.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    key: const ValueKey('bill-tolerance-percent'),
                    controller: _percent,
                    enabled: _mayManage && _read && !_saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Rate may exceed the order by (%)',
                      helperText: 'Blank means no check on the rate.',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    key: const ValueKey('bill-tolerance-amount'),
                    controller: _amount,
                    enabled: _mayManage && _read && !_saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Whole bill may exceed the order by (amount)',
                      helperText: 'Blank means no check on the bill total.',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  if (_toleranceError != null) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      _toleranceError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    _Notice(
                      icon: Icons.lock_outline,
                      text: 'Changing the stages needs the manage purchase '
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
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        if (!_read && !_loading)
          TextButton(
            key: const ValueKey('purchase-stages-retry'),
            onPressed: _retry,
            child: const Text('Try again'),
          ),
        FilledButton(
          onPressed:
              _mayManage && _read && !_loading && !_saving ? _save : null,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}

class _StageSwitch extends StatelessWidget {
  const _StageSwitch({
    required this.label,
    required this.detail,
    required this.value,
    required this.enabled,
    required this.onChanged,
  });

  final String label;
  final String detail;
  final bool value;
  final bool enabled;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      value: value,
      onChanged: enabled ? onChanged : null,
      title: Text(label),
      subtitle: Text(detail, style: theme.textTheme.bodySmall),
    );
  }
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
