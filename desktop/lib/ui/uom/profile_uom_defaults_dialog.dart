import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/uom_packaging.dart';

/// The default units a business profile trades in.
///
/// These are not fields on the profile itself: the profile is platform-wide
/// while the units are firm-owned, so they live on their own endpoint and are
/// edited from here. Reading needs `UOM_VIEW`; saving needs
/// `CONVERSION_RULE_MANAGE`.
///
/// A firm inherits its profile's seeded defaults until it saves its own. The
/// dialog says which of the two it is showing, because "PHARMACY sells in
/// strips" and "we sell in strips" are different statements and only the
/// second one is this firm's to change.
class ProfileUomDefaultsDialog extends StatefulWidget {
  const ProfileUomDefaultsDialog({
    super.key,
    required this.api,
    required this.permissions,
    required this.profileId,
    required this.profileName,
  });

  final ApiClient api;
  final PermissionService permissions;
  final String profileId;
  final String profileName;

  @override
  State<ProfileUomDefaultsDialog> createState() =>
      _ProfileUomDefaultsDialogState();
}

class _ProfileUomDefaultsDialogState extends State<ProfileUomDefaultsDialog> {
  List<UomRecord> _units = const [];
  String? _base;
  String? _inventory;
  String? _purchase;
  String? _sales;
  bool _allowFraction = false;
  bool _allowDecimal = true;
  bool _inherited = true;
  bool _hasDefaults = false;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// Whether to write the row every firm on the profile inherits.
  bool _forEveryFirm = false;

  bool get _mayManage =>
      widget.permissions.hasPermission('CONVERSION_RULE_MANAGE');

  /// Setting what every firm on the profile inherits reaches beyond this firm.
  bool get _mayManageProfile =>
      widget.permissions.hasPermission('PLATFORM_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final List<UomRecord> units = await widget.api.uoms();
      final BusinessProfileUomDefaults? defaults =
          await widget.api.businessProfileUomDefaults(widget.profileId);
      if (!mounted) return;
      setState(() {
        _units = units;
        _hasDefaults = defaults != null;
        _inherited = defaults?.isInherited ?? true;
        _base = _known(defaults?.baseUomId, units);
        _inventory = _known(defaults?.inventoryUomId, units);
        _purchase = _known(defaults?.purchaseUomId, units);
        _sales = _known(defaults?.salesUomId, units);
        _allowFraction = defaults?.allowFraction ?? false;
        _allowDecimal = defaults?.allowDecimal ?? true;
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

  /// Drop an id the unit list does not contain.
  ///
  /// A stored default can point at a unit that was since deactivated, and a
  /// DropdownButtonFormField throws when its value is absent from its items.
  static String? _known(String? id, List<UomRecord> units) =>
      units.any((unit) => unit.id == id) ? id : null;

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final BusinessProfileUomDefaults saved =
          await widget.api.updateBusinessProfileUomDefaults(
        widget.profileId,
        BusinessProfileUomDefaults(
          businessProfileId: widget.profileId,
          firmId: null,
          baseUomId: _base,
          inventoryUomId: _inventory,
          purchaseUomId: _purchase,
          salesUomId: _sales,
          allowFraction: _allowFraction,
          allowDecimal: _allowDecimal,
        ).toJson(),
        forEveryFirm: _forEveryFirm,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        _forEveryFirm
            ? 'Default units saved for every firm on ${widget.profileName}.'
            : 'Default units saved for this firm on ${widget.profileName}.',
        kind: AppNotificationKind.success,
      );
      Navigator.of(context).pop(saved);
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
      icon: const Icon(Icons.straighten_outlined),
      title: Text('Default units — ${widget.profileName}'),
      content: SizedBox(
        width: 520,
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
                      'The units a firm on this profile normally buys, stocks '
                      'and sells in.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    _Notice(
                      icon: _inherited
                          ? Icons.inventory_2_outlined
                          : Icons.business_outlined,
                      text: !_hasDefaults
                          ? 'Neither this profile nor this firm has default '
                              'units yet. Saving sets them for this firm.'
                          : _inherited
                              ? 'Showing the defaults that come with this '
                                  "profile. Saving makes them this firm's own, "
                                  'leaving other firms on the profile as they '
                                  'are.'
                              : "Showing this firm's own defaults, which "
                                  'override the profile.',
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    Row(
                      children: [
                        Expanded(
                          child: _unitField(
                            label: 'Base unit',
                            helper: 'What stock is counted in',
                            value: _base,
                            onChanged: (value) =>
                                setState(() => _base = value),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.lg),
                        Expanded(
                          child: _unitField(
                            label: 'Inventory unit',
                            helper: 'What the ledger reports',
                            value: _inventory,
                            onChanged: (value) =>
                                setState(() => _inventory = value),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    Row(
                      children: [
                        Expanded(
                          child: _unitField(
                            label: 'Purchase unit',
                            helper: 'What suppliers quote',
                            value: _purchase,
                            onChanged: (value) =>
                                setState(() => _purchase = value),
                          ),
                        ),
                        const SizedBox(width: AppSpacing.lg),
                        Expanded(
                          child: _unitField(
                            label: 'Sales unit',
                            helper: 'What customers order',
                            value: _sales,
                            onChanged: (value) =>
                                setState(() => _sales = value),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.md),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _allowDecimal,
                      title: const Text('Allow decimal quantities'),
                      subtitle: const Text('1.5 boxes'),
                      onChanged: _mayManage && !_saving
                          ? (value) => setState(() => _allowDecimal = value)
                          : null,
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      value: _allowFraction,
                      title: const Text('Allow fractional quantities'),
                      subtitle: const Text('Half of a base unit'),
                      onChanged: _mayManage && !_saving
                          ? (value) => setState(() => _allowFraction = value)
                          : null,
                    ),
                    _Notice(
                      icon: Icons.info_outline,
                      text: 'These pre-fill a new product\'s units, which can '
                          'still be changed before it is saved.',
                    ),
                    if (_mayManageProfile) ...[
                      const Divider(height: AppSpacing.xl),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        value: _forEveryFirm,
                        title: const Text('Save for every firm on this profile'),
                        subtitle: Text(
                          _forEveryFirm
                              ? 'Sets what firms on ${widget.profileName} '
                                  'inherit. A firm that has chosen its own '
                                  'units keeps them.'
                              : 'Off, so this saves units for this firm only.',
                        ),
                        onChanged: _saving
                            ? null
                            : (value) =>
                                setState(() => _forEveryFirm = value),
                      ),
                    ],
                    if (!_mayManage) ...[
                      const SizedBox(height: AppSpacing.lg),
                      _Notice(
                        icon: Icons.lock_outline,
                        text: 'Changing these needs the manage conversion '
                            'rules permission.',
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
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
        FilledButton(
          onPressed: _mayManage && !_loading && !_saving ? _save : null,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _unitField({
    required String label,
    required String helper,
    required String? value,
    required ValueChanged<String?> onChanged,
  }) =>
      DropdownButtonFormField<String?>(
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(labelText: label, helperText: helper),
        items: [
          const DropdownMenuItem<String?>(value: null, child: Text('Not set')),
          for (final UomRecord unit in _units)
            DropdownMenuItem<String?>(
              value: unit.id,
              child: Text('${unit.name} (${unit.code})',
                  overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: _mayManage && !_saving ? onChanged : null,
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
