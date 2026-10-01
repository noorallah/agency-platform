import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/save_in_dialog.dart';

/// How the below-reorder list decides what is short (backlog 69 row 12).
///
/// **Typed levels per product** orders up to the levels typed on each stock
/// row, as before. **From sales** also covers products with no typed level:
/// the average daily net sales over the sales window gives a reorder point of
/// daily x (lead time + safety) and an order-up-to level of daily x (lead time
/// + safety + cover). A level typed on a product always wins.
///
/// Reading needs `PURCHASE_VIEW` or `REPORT_VIEW`; changing needs
/// `PURCHASE_MANAGE_SETTINGS`. The dialog proves it read the firm's own
/// settings before it will save (D-CFG-14), and all five fields are sent.
class ReorderPlanningDialog extends StatefulWidget {
  const ReorderPlanningDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<ReorderPlanningDialog> createState() => _ReorderPlanningDialogState();
}

class _ReorderPlanningDialogState extends State<ReorderPlanningDialog>
    with SaveInDialog<ReorderPlanningDialog> {
  static const String _levels = 'LEVELS';
  static const String _sales = 'SALES';

  final TextEditingController _window = TextEditingController(text: '30');
  final TextEditingController _lead = TextEditingController(text: '7');
  final TextEditingController _safety = TextEditingController(text: '3');
  final TextEditingController _cover = TextEditingController(text: '30');

  String _basis = _levels;
  bool _loading = true;
  bool _read = false;
  bool _configured = true;
  String? _loadError;

  bool get _mayManage =>
      widget.permissions.hasPermission('PURCHASE_MANAGE_SETTINGS');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _window.dispose();
    _lead.dispose();
    _safety.dispose();
    _cover.dispose();
    super.dispose();
  }

  void _retry() {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    _load();
  }

  Future<void> _load() async {
    try {
      final Json data = await widget.api.reorderPlanning();
      if (!mounted) return;
      setState(() {
        _basis = stringValue(data['basis']) == _sales ? _sales : _levels;
        _window.text = _plain(data['sales_window_days'], '30');
        _lead.text = _plain(data['lead_time_days'], '7');
        _safety.text = _plain(data['safety_days'], '3');
        _cover.text = _plain(data['cover_days'], '30');
        _configured = data['is_configured'] != false;
        _read = true;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = 'The planning settings could not be read, so they '
            'cannot be saved: ${error.message}';
        _loading = false;
      });
    }
  }

  static String _plain(dynamic value, String fallback) {
    final String text = stringValue(value);
    return int.tryParse(text) == null ? fallback : text;
  }

  /// The four day counts and the range the server holds each to.
  List<(String, TextEditingController, int, int)> get _fields => [
        ('Sales window', _window, 7, 365),
        ('Lead time', _lead, 0, 365),
        ('Safety stock', _safety, 0, 365),
        ('Cover', _cover, 1, 365),
      ];

  /// The first field outside its range, named; null when all are fine.
  String? get _problem {
    if (_basis != _sales) return null;
    for (final (String, TextEditingController, int, int) field in _fields) {
      final int? value = int.tryParse(field.$2.text.trim());
      if (value == null || value < field.$3 || value > field.$4) {
        return '${field.$1} must be a whole number of days from ${field.$3} '
            'to ${field.$4}.';
      }
    }
    return null;
  }

  Future<void> _save() async {
    if (!_read || _problem != null) return;
    int days(TextEditingController c) => int.tryParse(c.text.trim()) ?? 0;
    final Json body = <String, dynamic>{
      'basis': _basis,
      'sales_window_days': days(_window),
      'lead_time_days': days(_lead),
      'safety_days': days(_safety),
      'cover_days': days(_cover),
    };
    await saveAndClose<Json>(() => widget.api.updateReorderPlanning(body));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool fromSales = _basis == _sales;
    final bool editable = _mayManage && _read && !saving;
    final String? problem = _problem;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.inventory_2_outlined),
      title: const Text('Reorder planning'),
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
                    'Decides what the Below reorder level list calls short. A '
                    'level typed on a product always wins.',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  saveErrorBanner(),
                  if (_loadError != null)
                    Text(
                      _loadError!,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    ),
                  if (_read && !_configured)
                    Text(
                      'This firm has not chosen, so it plans on typed levels. '
                      "Saving makes the choice the firm's own.",
                      style: theme.textTheme.bodySmall,
                    ),
                  RadioGroup<String>(
                    groupValue: _basis,
                    onChanged: (value) {
                      if (editable && value != null) {
                        setState(() => _basis = value);
                      }
                    },
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        RadioListTile<String>(
                          key: const ValueKey('reorder-basis-levels'),
                          contentPadding: EdgeInsets.zero,
                          enabled: editable,
                          value: _levels,
                          title: const Text('Typed levels per product'),
                          subtitle: Text(
                            'Order up to the reorder and maximum levels typed '
                            'on each stock row.',
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                        RadioListTile<String>(
                          key: const ValueKey('reorder-basis-sales'),
                          contentPadding: EdgeInsets.zero,
                          enabled: editable,
                          value: _sales,
                          title: const Text('From sales'),
                          subtitle: Text(
                            'Products with no typed level are planned from '
                            'what they sold.',
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (fromSales) ...[
                    const SizedBox(height: AppSpacing.sm),
                    _dayBox(
                      'reorder-window',
                      'Sales window (days)',
                      _window,
                      'How far back sales are averaged (7 to 365).',
                      editable,
                    ),
                    _dayBox(
                      'reorder-lead',
                      'Lead time (days)',
                      _lead,
                      'How long a supplier takes to deliver (0 to 365).',
                      editable,
                    ),
                    _dayBox(
                      'reorder-safety',
                      'Safety stock (days)',
                      _safety,
                      'Extra days of sales kept as a buffer (0 to 365).',
                      editable,
                    ),
                    _dayBox(
                      'reorder-cover',
                      'Cover (days)',
                      _cover,
                      "Cover 30 = keep a month's stock: what sold is ordered "
                          'back (1 to 365).',
                      editable,
                    ),
                    if (problem != null)
                      Text(
                        problem,
                        key: const ValueKey('reorder-problem'),
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.colorScheme.error),
                      ),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'Changing the planning needs the manage purchase '
                      'settings permission.',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Close'),
        ),
        if (!_read && !_loading)
          TextButton(
            key: const ValueKey('reorder-planning-retry'),
            onPressed: _retry,
            child: const Text('Try again'),
          ),
        FilledButton(
          key: const ValueKey('reorder-planning-save'),
          onPressed:
              editable && !_loading && problem == null ? _save : null,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _dayBox(
    String key,
    String label,
    TextEditingController controller,
    String help,
    bool enabled,
  ) =>
      Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: TextField(
          key: ValueKey(key),
          controller: controller,
          enabled: enabled,
          keyboardType: TextInputType.number,
          decoration: InputDecoration(
            labelText: label,
            helperText: help,
            helperMaxLines: 2,
            isDense: true,
          ),
          onChanged: (_) => setState(() {}),
        ),
      );
}
