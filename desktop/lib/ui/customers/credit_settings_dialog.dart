import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';

/// The firm's credit policy: what happens as a customer approaches their limit.
///
/// Reading the policy needs only `CUSTOMER_VIEW`, so anyone who is warned by it
/// can see the rule behind the warning. Changing it needs
/// `CUSTOMER_MANAGE_SETTINGS`, which is deliberately not granted to sales
/// roles — the limit exists to constrain them.
class CreditSettingsDialog extends StatefulWidget {
  const CreditSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<CreditSettingsDialog> createState() => _CreditSettingsDialogState();
}

class _CreditSettingsDialogState extends State<CreditSettingsDialog> {
  static const List<String> _enforcements = ['OFF', 'WARN', 'BLOCK'];

  final TextEditingController _warn = TextEditingController();
  final TextEditingController _block = TextEditingController();
  String _enforcement = 'WARN';
  bool _loading = true;
  bool _saving = false;
  bool _isConfigured = false;
  String? _error;

  bool get _mayManage =>
      widget.permissions.hasPermission('CUSTOMER_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _warn.dispose();
    _block.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final CreditControlSettings settings =
          await widget.api.creditControlSettings();
      if (!mounted) return;
      setState(() {
        _enforcement = _enforcements.contains(settings.enforcement)
            ? settings.enforcement
            : 'WARN';
        _warn.text = _trim(settings.warnAtPercent);
        _block.text = _trim(settings.blockAtPercent);
        _isConfigured = settings.isConfigured;
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

  /// Render `80.00` as `80` — the server stores a scale nobody types.
  static String _trim(String value) {
    if (!value.contains('.')) return value;
    final String trimmed =
        value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
    return trimmed.isEmpty ? '0' : trimmed;
  }

  /// Say what is wrong, or nothing.
  ///
  /// These are the server's rules restated, so a mistake is caught while the
  /// numbers are still on screen rather than coming back as a rejection.
  String? _validate() {
    final double? warn = double.tryParse(_warn.text.trim());
    final double? block = double.tryParse(_block.text.trim());
    if (warn == null || block == null) {
      return 'Both thresholds must be numbers.';
    }
    if (warn < 1 || warn > 500 || block < 1 || block > 500) {
      return 'Thresholds must be between 1 and 500 percent.';
    }
    if (warn > block) {
      return 'The warning threshold must not be above the blocking one, '
          'or it could never fire.';
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
      await widget.api.updateCreditControlSettings(
        CreditControlSettings(
          enforcement: _enforcement,
          warnAtPercent: _warn.text.trim(),
          blockAtPercent: _block.text.trim(),
          isConfigured: true,
        ),
      );
      if (!mounted) return;
      // Announce before popping: the notification reads the theme off this
      // context, and after the pop it is no longer mounted.
      NotificationService.show(
        context,
        'Credit policy saved.',
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

  /// What the selected enforcement actually does, in one line.
  String get _explanation => switch (_enforcement) {
        'OFF' => 'Credit limits are recorded but never checked.',
        'BLOCK' =>
          'Warn at the first threshold; refuse the document at the second.',
        _ => 'Warn at the threshold. No document is ever refused.',
      };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      icon: const Icon(Icons.account_balance_wallet_outlined),
      title: const Text('Credit policy'),
      content: SizedBox(
        width: 460,
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
                    'Applies to every customer in this firm, at sales order '
                    'and sales invoice approval.',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (!_isConfigured) ...[
                    const SizedBox(height: AppSpacing.md),
                    _Notice(
                      icon: Icons.info_outline,
                      text: 'This firm has not set a policy, so it is using '
                          'the default shown here. Saving makes it the '
                          "firm's own.",
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  DropdownButtonFormField<String>(
                    initialValue: _enforcement,
                    decoration: const InputDecoration(
                      labelText: 'When a customer reaches their limit',
                    ),
                    items: const [
                      DropdownMenuItem(value: 'OFF', child: Text('Do nothing')),
                      DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                      DropdownMenuItem(
                          value: 'BLOCK', child: Text('Warn, then block')),
                    ],
                    onChanged: _mayManage && !_saving
                        ? (value) =>
                            setState(() => _enforcement = value ?? _enforcement)
                        : null,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(_explanation, style: theme.textTheme.bodySmall),
                  const SizedBox(height: AppSpacing.lg),
                  Row(
                    children: [
                      Expanded(
                        child: _percentField(
                          controller: _warn,
                          label: 'Warn at',
                          helper: 'Percent of the limit',
                        ),
                      ),
                      const SizedBox(width: AppSpacing.lg),
                      Expanded(
                        child: _percentField(
                          controller: _block,
                          label: 'Block at',
                          helper: _enforcement == 'BLOCK'
                              ? 'Percent of the limit'
                              : 'Unused unless blocking',
                        ),
                      ),
                    ],
                  ),
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    _Notice(
                      icon: Icons.lock_outline,
                      text: 'Changing the policy needs the manage customer '
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

  Widget _percentField({
    required TextEditingController controller,
    required String label,
    required String helper,
  }) =>
      TextField(
        controller: controller,
        enabled: _mayManage && !_saving,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        inputFormatters: [
          FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
        ],
        decoration: InputDecoration(
          labelText: label,
          helperText: helper,
          suffixText: '%',
        ),
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
