// Tax collected at source: the policy, and what it has actually collected.
//
// The thing this screen has to make plain is that **two** facts decide whether
// anything is collected — the firm has switched the section on, and the firm's
// own turnover puts it in scope. One switch would hide the second, and a firm
// that had switched it on and collected nothing would have no way to find out
// why.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/tcs.dart';
import '../workspace/desktop_framework.dart';

/// Show the 206C(1H) policy and the register of what it has collected.
class TcsPage extends StatefulWidget {
  const TcsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<TcsPage> createState() => _TcsPageState();
}

class _TcsPageState extends State<TcsPage> {
  TcsSettings? _settings;
  List<TcsCollectionRecord> _rows = const [];
  String? _error;
  bool _loading = true;

  bool get _mayView => widget.permissions.hasPermission('TCS_VIEW');

  /// The policy decides what every buyer is charged, so changing it is its
  /// own permission — the role a rule constrains must not switch it off.
  bool get _mayManage => widget.permissions.hasPermission('TCS_MANAGE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final TcsSettings settings = await widget.api.tcsSettings();
      final List<TcsCollectionRecord> rows =
          await fetchAllPages<TcsCollectionRecord>(
        (page) => widget.api.tcsCollections(page: page),
      );
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _rows = rows;
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

  Future<void> _edit() async {
    final TcsSettings? current = _settings;
    if (current == null) return;
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => _TcsSettingsDialog(
        api: widget.api,
        settings: current,
      ),
    );
    if (saved == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'The section applies to a seller, so a firm has to be chosen.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading what buyers are charged needs the view TCS '
            'permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
          FilledButton.icon(
            onPressed: _mayManage ? _edit : null,
            icon: const Icon(Icons.tune),
            label: const Text('Settings'),
          ),
        ],
      ),
      searchPanel: _policyBanner(),
      primaryContent: _register(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: false,
        message: 'Charged on money received, not on what was invoiced.',
      ),
    );
  }

  Widget _policyBanner() {
    final TcsSettings? settings = _settings;
    if (settings == null) return const SizedBox.shrink();
    // Two facts, said separately. A firm that switched it on and collected
    // nothing has no other way to discover that its stated turnover is what
    // is holding it back.
    final String state = settings.collecting
        ? 'Collecting under section ${_section(settings.sectionCode)}'
        : !settings.isEnabled
            ? 'Not collecting: the section is switched off.'
            : 'Not collecting: the stated turnover is below the seller '
                'threshold.';
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Icon(
            settings.collecting ? Icons.verified_outlined : Icons.pause_circle_outline,
            size: 18,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              '$state  •  ${_money(settings.thresholdAmount)} per buyer per '
              'year, then ${settings.ratePercent}% '
              '(${settings.rateWithoutPanPercent}% without a PAN)',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  Widget _register() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing collected yet',
        message: 'The tax is charged when a buyer pays more than the '
            'threshold in a financial year. Until one does, there is nothing '
            'here.',
      );
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SingleChildScrollView(
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Receipt')),
            DataColumn(label: Text('Buyer')),
            DataColumn(label: Text('On')),
            DataColumn(label: Text('Received')),
            DataColumn(label: Text('Paid before')),
            DataColumn(label: Text('Chargeable')),
            DataColumn(label: Text('Rate')),
            DataColumn(label: Text('Collected')),
            DataColumn(label: Text('Status')),
          ],
          rows: [
            for (final TcsCollectionRecord row in _rows)
              DataRow(cells: [
                DataCell(Text(row.settlementNumber)),
                DataCell(Text(row.customerName)),
                DataCell(Text(row.collectedOn)),
                DataCell(Text(_money(row.considerationAmount))),
                // The two figures that explain the third. Without them the
                // collected amount is a number nobody can check.
                DataCell(Text(_money(row.cumulativeBefore))),
                DataCell(Text(_money(row.taxableAmount))),
                DataCell(Text(
                  row.withoutPan ? '${row.ratePercent}% (no PAN)' : '${row.ratePercent}%',
                )),
                DataCell(Text(_money(row.tcsAmount))),
                DataCell(StatusBadge.fromStatus(row.status)),
              ]),
          ],
        ),
      ),
    );
  }

  /// Render the stored code the way the Act writes it: 206C_1H is
  /// 206C(1H). Spelled out rather than done with string surgery, so a second
  /// section added later reads as itself instead of coming out mangled.
  static String _section(String code) =>
      code == '206C_1H' ? '206C(1H)' : code.replaceAll('_', ' ');

  static String _money(double value) => value.toStringAsFixed(2);
}

/// Edit the policy. Only what this form shows is sent, so nothing else moves.
class _TcsSettingsDialog extends StatefulWidget {
  const _TcsSettingsDialog({required this.api, required this.settings});

  final ApiClient api;
  final TcsSettings settings;

  @override
  State<_TcsSettingsDialog> createState() => _TcsSettingsDialogState();
}

class _TcsSettingsDialogState extends State<_TcsSettingsDialog> {
  late bool _enabled = widget.settings.isEnabled;
  late final TextEditingController _threshold =
      TextEditingController(text: widget.settings.thresholdAmount.toString());
  late final TextEditingController _rate =
      TextEditingController(text: widget.settings.ratePercent.toString());
  late final TextEditingController _rateNoPan = TextEditingController(
      text: widget.settings.rateWithoutPanPercent.toString());
  late final TextEditingController _turnover = TextEditingController(
      text: widget.settings.precedingYearTurnover.toString());
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _threshold.dispose();
    _rate.dispose();
    _rateNoPan.dispose();
    _turnover.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.saveTcsSettings(<String, dynamic>{
        'is_enabled': _enabled,
        'threshold_amount': _threshold.text.trim(),
        'rate_percent': _rate.text.trim(),
        'rate_without_pan_percent': _rateNoPan.text.trim(),
        'preceding_year_turnover': _turnover.text.trim(),
      });
      if (!mounted) return;
      NotificationService.show(
        context,
        'TCS settings saved.',
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

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Tax collected at source'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Charged when a buyer pays more than the threshold in a '
                  'financial year, and only on the part above it. It is '
                  'collected on the money received, so it raises what the '
                  'buyer owes rather than coming out of what they paid.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.md),
                SwitchListTile(
                  value: _enabled,
                  onChanged: (value) => setState(() => _enabled = value),
                  title: const Text('Collect under section 206C(1H)'),
                  contentPadding: EdgeInsets.zero,
                ),
                TextField(
                  controller: _turnover,
                  decoration: const InputDecoration(
                    labelText: 'Preceding year turnover',
                    // Stated rather than derived: the preceding year may
                    // predate this system entirely.
                    helperText: 'Nothing is collected unless this is above '
                        'the seller threshold.',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _threshold,
                  decoration: const InputDecoration(
                    labelText: 'Threshold per buyer, per financial year',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _rate,
                  decoration: const InputDecoration(labelText: 'Rate %'),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _rateNoPan,
                  decoration: const InputDecoration(
                    labelText: 'Rate % without a PAN',
                    helperText: 'Section 206CC, on the same collection.',
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: const Text('Save'),
          ),
        ],
      );
}
