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

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final SalesWorkflowSettings settings =
          await widget.api.salesWorkflowSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
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

  Future<void> _save() async {
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
                  if (!_settings.isConfigured) ...[
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
                    enabled: _mayManage && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(quotationStage: value),
                    ),
                  ),
                  _StageSwitch(
                    label: 'Sales order',
                    detail: 'What the customer asked for, before it ships.',
                    value: _settings.salesOrderStage,
                    enabled: _mayManage && !_saving,
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
                    enabled: _mayManage && !_saving,
                    onChanged: (value) => setState(
                      () => _settings =
                          _settings.copyWith(deliveryNoteStage: value),
                    ),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  _Notice(icon: Icons.receipt_long_outlined, text: _summary),
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
        FilledButton(
          onPressed: _mayManage && !_loading && !_saving ? _save : null,
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
