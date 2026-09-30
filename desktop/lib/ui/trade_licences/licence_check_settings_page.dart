import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/trade_licence.dart';

/// What a missing or lapsed licence does to a sale, and to a purchase
/// (backlog 54): `GET`/`PUT /api/v1/trade-licences/settings`.
///
/// Reading needs `TRADE_LICENCE_VIEW`; changing needs
/// `TRADE_LICENCE_MANAGE_SETTINGS`. Sits beside Licence Types under
/// Configuration, since the two are read together -- a firm that names a
/// licence type on a category has to decide, in the same breath, what a sale
/// or a purchase missing it actually does.
class LicenceCheckSettingsPage extends StatefulWidget {
  const LicenceCheckSettingsPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<LicenceCheckSettingsPage> createState() =>
      _LicenceCheckSettingsPageState();
}

class _LicenceCheckSettingsPageState extends State<LicenceCheckSettingsPage> {
  TradeLicenceSettingsRecord _settings = const TradeLicenceSettingsRecord(
    saleEnforcement: 'WARN',
    purchaseEnforcement: 'WARN',
    isConfigured: false,
  );
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// True only once the firm's own settings arrived -- saving before that
  /// would replace whatever the firm chose with the default nobody picked.
  bool _read = false;

  bool get _mayManage =>
      widget.permissions.hasPermission('TRADE_LICENCE_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final TradeLicenceSettingsRecord settings =
          await widget.api.licenceSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _read = true;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'The licence check policy could not be read, so it cannot '
            'be saved: ${error.message}';
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    if (!_read) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final TradeLicenceSettingsRecord saved =
          await widget.api.updateLicenceSettings(_settings);
      if (!mounted) return;
      setState(() {
        _settings = saved;
        _saving = false;
      });
      NotificationService.show(
        context,
        'Licence check policy saved.',
        kind: AppNotificationKind.success,
      );
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
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'What a sale, and a purchase, do when a party is missing a '
              "licence a product needs. A purchase only ever warns -- the "
              'goods a receipt records have already arrived.',
              style: theme.textTheme.bodyMedium,
            ),
            if (_read && !_settings.isConfigured) ...[
              const SizedBox(height: AppSpacing.md),
              _Notice(
                icon: Icons.info_outline,
                text: 'This firm has not chosen, so it is warning on both '
                    "sides. Saving makes it the firm's own.",
              ),
            ],
            const SizedBox(height: AppSpacing.xl),
            Text('Sale', style: theme.textTheme.titleSmall),
            _EnforcementChoice(
              value: _settings.saleEnforcement,
              enabled: _mayManage && _read && !_saving,
              choices: const ['OFF', 'WARN', 'BLOCK'],
              labels: const {
                'OFF': 'Off -- never checked',
                'WARN': 'Warn -- approval still goes ahead',
                'BLOCK': 'Block -- unless overridden with a reason',
              },
              onChanged: (value) => setState(
                () => _settings = _settings.copyWith(saleEnforcement: value),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text('Purchase', style: theme.textTheme.titleSmall),
            _EnforcementChoice(
              value: _settings.purchaseEnforcement,
              enabled: _mayManage && _read && !_saving,
              choices: const ['OFF', 'WARN'],
              labels: const {
                'OFF': 'Off -- never checked',
                'WARN': 'Warn -- approval still goes ahead',
              },
              onChanged: (value) => setState(
                () =>
                    _settings = _settings.copyWith(purchaseEnforcement: value),
              ),
            ),
            if (!_mayManage) ...[
              const SizedBox(height: AppSpacing.lg),
              const _Notice(
                icon: Icons.lock_outline,
                text: 'Changing this needs the manage licence settings '
                    'permission.',
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
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: [
                if (!_read && !_loading)
                  TextButton(
                    key: const ValueKey('licence-check-settings-retry'),
                    onPressed: _load,
                    child: const Text('Try again'),
                  ),
                const Spacer(),
                FilledButton(
                  onPressed:
                      _mayManage && _read && !_saving ? _save : null,
                  child: Text(_saving ? 'Saving…' : 'Save'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _EnforcementChoice extends StatelessWidget {
  const _EnforcementChoice({
    required this.value,
    required this.enabled,
    required this.choices,
    required this.labels,
    required this.onChanged,
  });

  final String value;
  final bool enabled;
  final List<String> choices;
  final Map<String, String> labels;
  final ValueChanged<String> onChanged;

  // RadioGroup.onChanged is not nullable, so "disabled" is expressed by
  // absorbing the gesture rather than by passing null (Flutter 3.32 moved
  // groupValue/onChanged off RadioListTile onto this ancestor).
  @override
  Widget build(BuildContext context) => AbsorbPointer(
        absorbing: !enabled,
        child: RadioGroup<String>(
          groupValue: value,
          onChanged: (next) => onChanged(next ?? value),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final String choice in choices)
                RadioListTile<String>(
                  key: ValueKey('licence-enforcement-$choice'),
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: choice,
                  title: Text(labels[choice] ?? choice),
                ),
            ],
          ),
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
