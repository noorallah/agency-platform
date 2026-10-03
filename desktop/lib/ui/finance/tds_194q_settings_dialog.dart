import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../workspace/save_in_dialog.dart';

/// TDS on purchases under section 194Q (ACC-8): whether the firm deducts, the
/// threshold per supplier per Income-tax year, and the two rates.
///
/// Reading needs `ACCOUNT_VIEW`, changing it `ACCOUNT_MANAGE`. The firm turns
/// the switch on itself, because only it knows its turnover last year passed
/// 10 crore; the server refuses a rate outside 0 to 20.
class Tds194qSettingsDialog extends StatefulWidget {
  const Tds194qSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<Tds194qSettingsDialog> createState() => _Tds194qSettingsDialogState();
}

class _Tds194qSettingsDialogState extends State<Tds194qSettingsDialog>
    with SaveInDialog<Tds194qSettingsDialog> {
  bool _enabled = false;
  final TextEditingController _threshold =
      TextEditingController(text: '5000000');
  final TextEditingController _rate = TextEditingController(text: '0.1');
  final TextEditingController _rateNoPan = TextEditingController(text: '5');
  bool _loading = true;
  String? _loadError;

  bool get _mayManage => widget.permissions.hasPermission('ACCOUNT_MANAGE');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _threshold.dispose();
    _rate.dispose();
    _rateNoPan.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final Map<String, dynamic> settings = await widget.api.tds194qSettings();
      if (!mounted) return;
      setState(() {
        _enabled = settings['is_enabled'] == true;
        _threshold.text = '${settings['threshold_amount'] ?? _threshold.text}';
        _rate.text = '${settings['rate_percent'] ?? _rate.text}';
        _rateNoPan.text =
            '${settings['rate_without_pan_percent'] ?? _rateNoPan.text}';
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _save() => saveAndClose<bool>(() async {
        await widget.api.saveTds194qSettings(<String, dynamic>{
          'is_enabled': _enabled,
          'threshold_amount': _threshold.text.trim(),
          'rate_percent': _rate.text.trim(),
          'rate_without_pan_percent': _rateNoPan.text.trim(),
        });
        if (mounted) {
          NotificationService.show(
            context,
            'TDS on purchases settings saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool editable = _mayManage && !_loading && _loadError == null;
    return AlertDialog(
      scrollable: true,
      title: const Text('TDS on purchases (194Q)'),
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
                    'A buyer whose turnover passed 10 crore last year deducts '
                    'tax from what it pays a supplier once the year\'s '
                    'purchases from that supplier pass the threshold, and only '
                    'on the part above it.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  if (_loadError != null)
                    Text(
                      _loadError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    )
                  else ...[
                    saveErrorBanner(),
                    SwitchListTile(
                      key: const ValueKey('tds194q-enabled'),
                      contentPadding: EdgeInsets.zero,
                      title: const Text(
                        'Our turnover passed ₹10 crore last year '
                        '(deduct 194Q)',
                      ),
                      value: _enabled,
                      onChanged: editable && !saving
                          ? (value) => setState(() => _enabled = value)
                          : null,
                    ),
                    TextField(
                      key: const ValueKey('tds194q-threshold'),
                      controller: _threshold,
                      enabled: editable && !saving,
                      decoration: const InputDecoration(
                        labelText: 'Threshold per supplier, per year',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    TextField(
                      key: const ValueKey('tds194q-rate'),
                      controller: _rate,
                      enabled: editable && !saving,
                      decoration: const InputDecoration(labelText: 'Rate %'),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    TextField(
                      key: const ValueKey('tds194q-rate-no-pan'),
                      controller: _rateNoPan,
                      enabled: editable && !saving,
                      decoration: const InputDecoration(
                        labelText: 'Rate % without a PAN',
                        helperText: 'Section 206AA, when the supplier has '
                            'given none.',
                      ),
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: Text(editable ? 'Cancel' : 'Close'),
        ),
        if (editable)
          FilledButton(
            key: const ValueKey('tds194q-save'),
            onPressed: saving ? null : _save,
            child: const Text('Save'),
          ),
      ],
    );
  }
}
