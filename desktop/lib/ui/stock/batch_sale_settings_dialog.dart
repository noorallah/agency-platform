import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/batch_sale_settings.dart';
import '../workspace/save_in_dialog.dart';

/// The firm's batch rules (backlog 79 row 6): when a batch counts as near
/// expiry, what leaving one behind or skipping an earlier-expiring batch needs
/// at dispatch, and whether a near-expiry batch may be sold below the floor.
///
/// Reading needs only a stock or sales view, so the people a rule reaches can
/// see it. Changing it needs `SALES_MANAGE_SETTINGS`, which sales roles do not
/// hold -- the rule exists to constrain them.
class BatchSaleSettingsDialog extends StatefulWidget {
  const BatchSaleSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<BatchSaleSettingsDialog> createState() =>
      _BatchSaleSettingsDialogState();
}

class _BatchSaleSettingsDialogState extends State<BatchSaleSettingsDialog>
    with SaveInDialog<BatchSaleSettingsDialog> {
  static const List<String> _nearExpiryPolicies = ['WARN', 'REASON'];
  static const List<String> _fefoPolicies = ['RECORD', 'REASON'];

  // The server's defaults, so nothing reads Off while the rule loads.
  final TextEditingController _days = TextEditingController(text: '30');
  String _nearExpiryPolicy = 'WARN';
  String _fefoSkipPolicy = 'RECORD';
  String _shelfLifePolicy = 'BLOCK';
  bool _belowFloor = true;
  bool _priceFromBatch = false;
  bool _isConfigured = false;
  bool _loading = true;
  String? _loadError;
  String? _daysError;

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _days.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final BatchSaleSettings settings = await widget.api.batchSaleSettings();
      if (!mounted) return;
      setState(() {
        _days.text = '${settings.nearExpiryDays}';
        _nearExpiryPolicy = _nearExpiryPolicies.contains(
          settings.nearExpiryPolicy,
        )
            ? settings.nearExpiryPolicy
            : 'WARN';
        _fefoSkipPolicy = _fefoPolicies.contains(settings.fefoSkipPolicy)
            ? settings.fefoSkipPolicy
            : 'RECORD';
        _shelfLifePolicy =
            settings.shelfLifePolicy == 'WARN' ? 'WARN' : 'BLOCK';
        _belowFloor = settings.nearExpiryBelowFloor;
        _priceFromBatch = settings.priceFromBatch;
        _isConfigured = settings.isConfigured;
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

  Future<void> _save() {
    final int? days = int.tryParse(_days.text.trim());
    if (days == null || days < 0 || days > 730) {
      setState(() => _daysError = 'Enter a whole number from 0 to 730.');
      return Future<void>.value();
    }
    setState(() => _daysError = null);
    return saveAndClose<bool>(() async {
      await widget.api.updateBatchSaleSettings(
        BatchSaleSettings(
          nearExpiryDays: days,
          nearExpiryPolicy: _nearExpiryPolicy,
          fefoSkipPolicy: _fefoSkipPolicy,
          nearExpiryBelowFloor: _belowFloor,
          shelfLifePolicy: _shelfLifePolicy,
          priceFromBatch: _priceFromBatch,
          isConfigured: true,
        ),
      );
      if (mounted) {
        // Announce before the pop: the notification reads the theme off
        // this context.
        NotificationService.show(
          context,
          'Batch rules saved.',
          kind: AppNotificationKind.success,
        );
      }
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool editable = _mayManage && !_loading && _loadError == null;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.event_busy_outlined),
      title: const Text('Batch rules'),
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
                    'Applies to every batch-tracked product in this firm, '
                    'when a delivery note is dispatched.',
                    style: theme.textTheme.bodySmall,
                  ),
                  if (!_isConfigured && _loadError == null) ...[
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'This firm has not chosen, so it is using the default '
                      "shown here. Saving makes it the firm's own.",
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  if (_loadError != null)
                    Text(
                      _loadError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    )
                  else ...[
                    saveErrorBanner(),
                    TextField(
                      key: const ValueKey('batch-rules-days'),
                      controller: _days,
                      enabled: editable && !saving,
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        labelText: 'A batch is near expiry within (days)',
                        helperText: 'From 0 to 730.',
                        errorText: _daysError,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('batch-rules-near-expiry'),
                      isExpanded: true,
                      initialValue: _nearExpiryPolicy,
                      decoration: const InputDecoration(
                        labelText: 'A near-expiry batch left behind',
                      ),
                      items: const [
                        DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                        DropdownMenuItem(
                          value: 'REASON',
                          child: Text('Need a reason'),
                        ),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(
                              () => _nearExpiryPolicy = value ?? _nearExpiryPolicy)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('batch-rules-fefo'),
                      isExpanded: true,
                      initialValue: _fefoSkipPolicy,
                      decoration: const InputDecoration(
                        labelText: 'Skipping an earlier-expiring batch',
                      ),
                      items: const [
                        DropdownMenuItem(
                          value: 'RECORD',
                          child: Text('Record'),
                        ),
                        DropdownMenuItem(
                          value: 'REASON',
                          child: Text('Need a reason'),
                        ),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(
                              () => _fefoSkipPolicy = value ?? _fefoSkipPolicy)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      key: const ValueKey('batch-rules-shelf-life'),
                      isExpanded: true,
                      initialValue: _shelfLifePolicy,
                      decoration: const InputDecoration(
                        labelText:
                            "Batch short of the customer's minimum shelf life",
                      ),
                      items: const [
                        DropdownMenuItem(value: 'BLOCK', child: Text('Block')),
                        DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(
                              () => _shelfLifePolicy = value ?? _shelfLifePolicy)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    CheckboxListTile(
                      key: const ValueKey('batch-rules-below-floor'),
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: const Text(
                        'A near-expiry batch may be sold below the price floor',
                      ),
                      value: _belowFloor,
                      onChanged: editable && !saving
                          ? (value) => setState(() => _belowFloor = value ?? true)
                          : null,
                    ),
                    CheckboxListTile(
                      key: const ValueKey('batch-rules-price-from-batch'),
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: const Text(
                        "Take a line's rate from its batch's selling price",
                      ),
                      value: _priceFromBatch,
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _priceFromBatch = value ?? false)
                          : null,
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      'Changing the batch rules needs the manage sales '
                      'settings permission.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        FilledButton(
          key: const ValueKey('batch-rules-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
