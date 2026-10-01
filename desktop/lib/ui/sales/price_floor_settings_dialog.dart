import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/price_floor.dart';
import '../workspace/save_in_dialog.dart';

/// The firm's price-floor policy: what happens when a sale is priced below a
/// product's minimum selling price, or below its cost (backlog 64 row 2).
///
/// Reading needs only `SALES_VIEW`, so anyone a refusal reaches can see the
/// rule behind it. Changing it needs `SALES_MANAGE_SETTINGS`, which sales
/// roles do not hold -- the floor exists to constrain them.
class PriceFloorSettingsDialog extends StatefulWidget {
  const PriceFloorSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<PriceFloorSettingsDialog> createState() =>
      _PriceFloorSettingsDialogState();
}

class _PriceFloorSettingsDialogState extends State<PriceFloorSettingsDialog>
    with SaveInDialog<PriceFloorSettingsDialog> {
  static const List<String> _enforcements = ['OFF', 'WARN', 'BLOCK'];

  String _enforcement = 'OFF';
  bool _includeCost = false;
  bool _isConfigured = false;
  bool _loading = true;
  String? _loadError;

  bool get _mayManage =>
      widget.permissions.hasPermission('SALES_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final PriceFloorSettings settings = await widget.api.priceFloorSettings();
      if (!mounted) return;
      setState(() {
        _enforcement = _enforcements.contains(settings.enforcement)
            ? settings.enforcement
            : 'OFF';
        _includeCost = settings.includeCost;
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

  Future<void> _save() => saveAndClose<bool>(() async {
        await widget.api.updatePriceFloorSettings(
          PriceFloorSettings(
            enforcement: _enforcement,
            includeCost: _includeCost,
            isConfigured: true,
          ),
        );
        if (mounted) {
          // Announce before the pop: the notification reads the theme off
          // this context.
          NotificationService.show(
            context,
            'Price floor saved.',
            kind: AppNotificationKind.success,
          );
        }
        return true;
      });

  String get _explanation => switch (_enforcement) {
        'BLOCK' => 'A sale below its floor is refused at approval, unless '
            'someone who may override gives a reason.',
        'WARN' => 'A sale below its floor is flagged at approval and the '
            'warning is kept on the document. Nothing is refused.',
        _ => 'Prices are not checked against any floor.',
      };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool editable = _mayManage && !_loading && _loadError == null;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.price_check_outlined),
      title: const Text('Price floor'),
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
                    'Applies to every product in this firm, at sales order '
                    "and sales invoice approval. A product's floor is its "
                    'minimum selling price; cost can be a floor too.',
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
                    DropdownButtonFormField<String>(
                      key: const ValueKey('price-floor-enforcement'),
                      isExpanded: true,
                      initialValue: _enforcement,
                      decoration: const InputDecoration(
                        labelText: 'When a line is priced below its floor',
                      ),
                      items: const [
                        DropdownMenuItem(value: 'OFF', child: Text('Off')),
                        DropdownMenuItem(value: 'WARN', child: Text('Warn')),
                        DropdownMenuItem(value: 'BLOCK', child: Text('Block')),
                      ],
                      onChanged: editable && !saving
                          ? (value) => setState(
                              () => _enforcement = value ?? _enforcement)
                          : null,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(_explanation, style: theme.textTheme.bodySmall),
                    const SizedBox(height: AppSpacing.md),
                    CheckboxListTile(
                      key: const ValueKey('price-floor-include-cost'),
                      contentPadding: EdgeInsets.zero,
                      controlAffinity: ListTileControlAffinity.leading,
                      title: const Text('Cost is a floor too'),
                      subtitle: const Text(
                        "A line below the product's cost is a finding even "
                        'when it has no minimum selling price.',
                      ),
                      value: _includeCost,
                      onChanged: editable && !saving
                          ? (value) =>
                              setState(() => _includeCost = value ?? false)
                          : null,
                    ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      'Changing the price floor needs the manage sales '
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
          key: const ValueKey('price-floor-save'),
          onPressed: editable && !saving ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
