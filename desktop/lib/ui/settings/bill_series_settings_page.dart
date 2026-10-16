import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/document_framework.dart';
import '../workspace/desktop_framework.dart';

/// Which series the firm's sales bills take (backlog 157):
/// `GET`/`PUT /api/v1/document-framework/bill-series-settings`.
///
/// One series for every bill, or a series per company -- a bill of one
/// company's goods then takes that company's prefix (ASIAN-26-27-0001), and a
/// bill mixing companies takes the general series. Reading needs
/// `SETTINGS_VIEW`; changing needs `SETTINGS_UPDATE`, as the numbering series
/// do. The server enforces the same code; this only decides whether the
/// controls are worth offering.
class BillSeriesSettingsPage extends StatefulWidget {
  const BillSeriesSettingsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<BillSeriesSettingsPage> createState() => _BillSeriesSettingsPageState();
}

class _BillSeriesSettingsPageState extends State<BillSeriesSettingsPage> {
  BillSeriesSettings? _settings;

  /// The choice on screen, which differs from [_settings] until it is saved.
  String _choice = BillSeriesSettings.oneSeries;
  bool _loading = false;
  bool _saving = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('SETTINGS_VIEW');
  bool get _canEdit => widget.permissions.hasPermission('SETTINGS_UPDATE');

  /// True only once the firm's own setting arrived -- saving before that
  /// would replace whatever the firm chose with the default nobody picked.
  bool get _read => _settings != null;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final BillSeriesSettings settings = await widget.api.billSeriesSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _choice = settings.seriesDriver;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'The bill series setting could not be read, so it cannot '
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
      final BillSeriesSettings saved =
          await widget.api.saveBillSeriesSettings(_choice);
      if (!mounted) return;
      setState(() {
        _settings = saved;
        _choice = saved.seriesDriver;
        _saving = false;
      });
      NotificationService.show(
        context,
        'Bill series setting saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      // The choice stays on screen, so nothing typed is lost to a refusal.
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  static String _label(String driver) => switch (driver) {
        BillSeriesSettings.oneSeries => 'One series for every bill',
        BillSeriesSettings.byCompany => 'A series per company',
        _ => driver,
      };

  static String? _detail(String driver) => switch (driver) {
        BillSeriesSettings.oneSeries =>
          "Every sales bill takes the firm's general series.",
        BillSeriesSettings.byCompany =>
          "A bill of one company's goods takes that company's prefix. A bill "
              'mixing companies, or of a company with no prefix, takes the '
              'general series.',
        _ => null,
      };

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Bill series',
        message: 'You do not have permission to view settings.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Bill series',
        message: "Choose a firm to see how its sales bills are numbered.",
      );
    }
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final ThemeData theme = Theme.of(context);
    final BillSeriesSettings? settings = _settings;
    final List<String> drivers = settings == null || settings.drivers.isEmpty
        ? const [BillSeriesSettings.oneSeries, BillSeriesSettings.byCompany]
        : settings.drivers;
    final bool enabled = _canEdit && _read && !_saving;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Which series the firm\'s sales bills are numbered from.',
              style: theme.textTheme.bodyMedium,
            ),
            if (settings != null && !settings.isConfigured) ...[
              const SizedBox(height: AppSpacing.md),
              const _Notice(
                icon: Icons.info_outline,
                text: 'This firm has not chosen, so every bill takes one '
                    "series. Saving makes it the firm's own.",
              ),
            ],
            const SizedBox(height: AppSpacing.lg),
            AbsorbPointer(
              absorbing: !enabled,
              child: RadioGroup<String>(
                groupValue: _choice,
                onChanged: (next) =>
                    setState(() => _choice = next ?? _choice),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final String driver in drivers)
                      RadioListTile<String>(
                        key: ValueKey('bill-series-driver-$driver'),
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        value: driver,
                        enabled: enabled,
                        title: Text(_label(driver)),
                        subtitle: _detail(driver) == null
                            ? null
                            : Text(_detail(driver)!),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            // Design section 3 and 5: counters are per prefix and year, so a
            // switch at any time resets nothing and reuses no number.
            const _Notice(
              key: ValueKey('bill-series-new-bills-only'),
              icon: Icons.schedule_outlined,
              text: 'Switching affects new bills only. A bill already '
                  'numbered keeps its number, and every series carries on '
                  'from where it was -- nothing is reset or reused.',
            ),
            if (settings != null && settings.longestPrefix > 0) ...[
              const SizedBox(height: AppSpacing.sm),
              // The figure is worked out by the server from the sales-bill
              // layout (design section 8), never written into this sentence.
              _Notice(
                key: const ValueKey('bill-series-longest-prefix'),
                icon: Icons.straighten_outlined,
                text: "Under the firm's sales-bill layout, a company prefix of "
                    'up to ${settings.longestPrefix} '
                    '${settings.longestPrefix == 1 ? 'character' : 'characters'}'
                    ' fits the 16-character GST limit.',
              ),
            ],
            if (!_canEdit) ...[
              const SizedBox(height: AppSpacing.lg),
              const _Notice(
                icon: Icons.lock_outline,
                text: 'Changing this needs the update settings permission.',
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(
                _error!,
                key: const ValueKey('bill-series-error'),
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ],
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: [
                if (!_read)
                  TextButton(
                    key: const ValueKey('bill-series-retry'),
                    onPressed: _load,
                    child: const Text('Try again'),
                  ),
                const Spacer(),
                if (_canEdit)
                  FilledButton(
                    key: const ValueKey('bill-series-save'),
                    // Nothing to save until the choice moves -- except on a
                    // firm that never chose, where saving makes the default
                    // the firm's own.
                    onPressed: enabled &&
                            (_choice != settings!.seriesDriver ||
                                !settings.isConfigured)
                        ? _save
                        : null,
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

class _Notice extends StatelessWidget {
  const _Notice({super.key, required this.icon, required this.text});

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
