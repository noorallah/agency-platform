import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/sales_invoice.dart';

/// Which stages of a sale this firm's people type, and which the server raises.
///
/// The chain is quotation, sales order, delivery note, invoice. A firm run by
/// one person has no use for the first three: they are four screens for one
/// counter sale. Switching a stage off never removes the document -- the goods
/// still leave on a delivery note and cost of goods sold still belongs to it --
/// it means the bill raises that document itself.
///
/// A switch per stage rather than one mode, because a firm changes shape.
/// Somebody trading alone hires a salesman, then a warehouse hand, and each
/// step should be a switch rather than a migration.
///
/// Reading needs only `SALES_VIEW`, so anyone whose screens move can see the
/// rule behind it. Changing needs `SALES_MANAGE_SETTINGS`, deliberately not
/// granted to sales roles: turning the delivery-note stage off means dispatch
/// is confirmed by the sale itself rather than by whoever watches goods leave.
class SalesWorkflowSettingsDialog extends StatefulWidget {
  const SalesWorkflowSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<SalesWorkflowSettingsDialog> createState() =>
      _SalesWorkflowSettingsDialogState();
}

class _SalesWorkflowSettingsDialogState
    extends State<SalesWorkflowSettingsDialog> {
  SalesWorkflowSettings _settings = SalesWorkflowSettings.wholeChain;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// True only once the firm's own settings arrived. The switches start from
  /// the whole chain, so saving after a failed read would replace whatever
  /// the firm chose with a chain nobody picked (D-CFG-14): the dialog must
  /// prove it read the settings before it may write them.
  bool _read = false;

  /// Backlog 59 item 3: the cap on one line's combined offer discount.
  final TextEditingController _capController = TextEditingController();

  /// STK-12: days before an unshipped order's stock hold lapses; blank never.
  final TextEditingController _lapseController = TextEditingController();

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _capController.dispose();
    _lapseController.dispose();
    super.dispose();
  }

  /// The lapse days as typed: blank is never, otherwise a whole 1 to 365.
  String? get _lapseError {
    final String text = _lapseController.text.trim();
    if (text.isEmpty) return null;
    final int? value = int.tryParse(text);
    if (value == null || value < 1 || value > 365) {
      return 'A whole number of days from 1 to 365, or blank for never.';
    }
    return null;
  }

  /// The cap as typed: blank is no cap, otherwise 0 to 100.
  String? get _capError {
    final String text = _capController.text.trim();
    if (text.isEmpty) return null;
    final double? value = double.tryParse(text);
    if (value == null || value < 0 || value > 100) {
      return 'A percentage from 0 to 100, or blank for no cap.';
    }
    return null;
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
      final SalesWorkflowSettings settings =
          await widget.api.salesWorkflowSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _capController.text = settings.maxLineDiscountPercent ?? '';
        _lapseController.text = '${settings.reservationLapseDays ?? ''}';
        _read = true;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'The sales stages could not be read, so they cannot be '
            'saved: ${error.message}';
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    if (!_read) return;
    if (_capError != null) {
      setState(() => _error = _capError);
      return;
    }
    if (_lapseError != null) {
      setState(() => _error = _lapseError);
      return;
    }
    final String cap = _capController.text.trim();
    final int? lapse = int.tryParse(_lapseController.text.trim());
    _settings = _settings.copyWith(
        maxLineDiscountPercent: () => cap.isEmpty ? null : cap,
        reservationLapseDays: () => lapse);
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.updateSalesWorkflowSettings(_settings);
      if (!mounted) return;
      // Announce before popping: the notification reads the theme off this
      // context, and after the pop it is no longer mounted.
      NotificationService.show(
        context,
        'Sales stages saved.',
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
      if (_settings.quotationStage) 'quotation',
      if (_settings.salesOrderStage) 'order',
      if (_settings.deliveryNoteStage) 'delivery note',
      'invoice',
    ];
    if (typed.length == 1) {
      return 'One screen: the invoice. Everything behind it is raised for you.';
    }
    return 'Your people raise the ${typed.join(', ')}.';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      // An AlertDialog gives its content unbounded height; three switches,
      // four notices and an error overflow a short window without this.
      scrollable: true,
      icon: const Icon(Icons.linear_scale_outlined),
      title: const Text('Sales stages'),
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
                    'raised and still recorded — the invoice raises them as it '
                    'saves — so stock, cost and the audit trail are unchanged.',
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
                    label: 'Quotation',
                    detail: 'An offer, before there is an order.',
                    value: _settings.quotationStage,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(quotationStage: value),
                    ),
                  ),
                  _StageSwitch(
                    label: 'Sales order',
                    detail: 'What the customer asked for, before it ships.',
                    value: _settings.salesOrderStage,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(salesOrderStage: value),
                    ),
                  ),
                  _StageSwitch(
                    label: 'Delivery note',
                    detail: 'Confirms what left the warehouse. Turning this '
                        'off means the bill confirms it instead.',
                    value: _settings.deliveryNoteStage,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(deliveryNoteStage: value),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  _Notice(icon: Icons.receipt_long_outlined, text: _summary),
                  const SizedBox(height: AppSpacing.lg),
                  // Backlog 59: how matching offers meet on one document.
                  DropdownButtonFormField<String>(
                    key: const ValueKey('sales-settings-promotion-mode'),
                    initialValue: _settings.promotionMode,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'When several offers match',
                      helperText: 'Combine applies each in Applies-at order; '
                          'best offer gives only the one worth most.',
                    ),
                    items: const [
                      DropdownMenuItem(
                          value: 'COMBINE', child: Text('Combine offers')),
                      DropdownMenuItem(
                          value: 'BEST_OFFER', child: Text('Best offer only')),
                    ],
                    onChanged: _mayManage && _read && !_saving
                        ? (value) => setState(
                              () => _settings = _settings.copyWith(
                                  promotionMode: value ?? 'COMBINE'),
                            )
                        : null,
                  ),
                  if (_settings.promotionMode == 'COMBINE') ...[
                    const SizedBox(height: AppSpacing.md),
                    TextFormField(
                      key: const ValueKey('sales-settings-line-discount-cap'),
                      controller: _capController,
                      enabled: _mayManage && _read && !_saving,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: InputDecoration(
                        labelText: 'Most offers may take off one line (%)',
                        helperText: 'Blank is no cap. Past it, the last offer '
                            'applied gives back first; the bill discount is '
                            'not counted.',
                        errorText: _capError,
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.md),
                  // Backlog 64 row 4: the default for a new bill's own switch.
                  _StageSwitch(
                    key: const ValueKey('sales-settings-rate-includes-tax'),
                    label: 'Rates typed on a bill include GST',
                    detail: 'A new bill starts with "Rate includes GST" on, '
                        'so the counter can type the shelf price; the bill '
                        'works out the taxable value. Each bill can still '
                        'switch it.',
                    value: _settings.rateIncludesTax,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(rateIncludesTax: value),
                    ),
                  ),
                  // SEL-15: a new outlet waits for office approval.
                  _StageSwitch(
                    key: const ValueKey('sales-settings-new-outlets-approval'),
                    label: 'New outlets wait for approval',
                    detail: 'A customer added by someone who cannot approve '
                        'customers takes orders but cannot be billed until '
                        'approved.',
                    value: _settings.newOutletsNeedApproval,
                    enabled: _mayManage && _read && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(newOutletsNeedApproval: value),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  // STK-12: stock held for an order nobody ships comes back.
                  TextFormField(
                    key: const ValueKey('sales-settings-reservation-lapse'),
                    controller: _lapseController,
                    enabled: _mayManage && _read && !_saving,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(
                      labelText:
                          'Release stock held by unshipped orders after (days)',
                      helperText: 'Blank is never. A lapsed order stays '
                          'approved and can still be shipped; reserve it '
                          'again to hold the stock once more.',
                      helperMaxLines: 3,
                      errorText: _lapseError,
                    ),
                    onChanged: (_) => setState(() {}),
                  ),
                  if (!_settings.deliveryNoteStage) ...[
                    const SizedBox(height: AppSpacing.md),
                    _Notice(
                      icon: Icons.warehouse_outlined,
                      text: 'Goods ship from this firm’s default branch and '
                          'warehouse. Without those, a bill cannot decide '
                          'where its stock comes from.',
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    _Notice(
                      icon: Icons.lock_outline,
                      text: 'Changing the stages needs the manage sales '
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
            key: const ValueKey('sales-stages-retry'),
            onPressed: _retry,
            child: const Text('Try again'),
          ),
        FilledButton(
          onPressed: _mayManage && _read && !_loading && !_saving
              ? _save
              : null,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}

class _StageSwitch extends StatelessWidget {
  const _StageSwitch({
    super.key,
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
