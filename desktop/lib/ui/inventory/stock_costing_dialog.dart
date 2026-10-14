import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/stock_costing.dart';
import '../../phase2/indian_format.dart';
import '../workspace/save_in_dialog.dart';

/// How the firm costs its stock (L2 step 9): Average, or each purchase by its
/// own lot from a chosen day. The switch is one way, so the dialog shows what
/// it will do before it is done and offers it only when nothing refuses it.
///
/// **Server calls: on opening, one `GET /inventory/lot-settings`, and on
/// Average one `GET .../switch-preview` for today to learn the suggested day.
/// One preview per "Show what will happen"; none on typing.** Switching is
/// one `POST .../switch`, whose answer is the new settings, so nothing is
/// read again; the billing switch is one `PUT` per change.
///
/// Reading needs `INVENTORY_VIEW`; switching and the billing switch need
/// `INVENTORY_MANAGE_SETTINGS`, like the other Stock settings. The server
/// stays the gate.
class StockCostingDialog extends StatefulWidget {
  const StockCostingDialog({
    super.key,
    required this.api,
    required this.permissions,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;

  /// The day asked about on opening, `YYYY-MM-DD`; this machine's date when
  /// null. Only its suggested day is used, so a day out does no harm.
  final String? today;

  @override
  State<StockCostingDialog> createState() => _StockCostingDialogState();
}

class _StockCostingDialogState extends State<StockCostingDialog>
    with SaveInDialog<StockCostingDialog> {
  final TextEditingController _date = TextEditingController();
  LotSettings? _settings;
  LotSwitchPreview? _preview;
  bool _loading = true;
  bool _previewing = false;
  String? _loadError;

  bool get _mayManage =>
      widget.permissions.hasPermission('INVENTORY_MANAGE_SETTINGS');

  static final RegExp _isoDay = RegExp(r'^\d{4}-\d{2}-\d{2}$');

  String get _typedDay => _date.text.trim();

  bool get _dayIsValid =>
      _isoDay.hasMatch(_typedDay) && DateTime.tryParse(_typedDay) != null;

  /// The preview counts only for the day it was taken for.
  bool get _previewIsForTypedDay => _preview?.on == _typedDay;

  bool get _maySwitch =>
      _mayManage &&
      !saving &&
      !_previewing &&
      _previewIsForTypedDay &&
      _preview!.refusals.isEmpty;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _date.dispose();
    super.dispose();
  }

  static String _day(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  Future<void> _load() async {
    try {
      final LotSettings settings = await widget.api.lotSettings();
      LotSwitchPreview? preview;
      if (!settings.byLot) {
        final LotSwitchPreview first = await widget.api
            .lotSwitchPreview(widget.today ?? _day(DateTime.now()));
        final String suggested =
            first.suggestedOn.isEmpty ? first.on : first.suggestedOn;
        _date.text = suggested;
        // Shown only when it was taken for the day now in the box.
        if (first.on == suggested) preview = first;
      }
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _preview = preview;
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

  Future<void> _showPreview() async {
    if (!_dayIsValid) {
      setState(() => saveError = 'Type the day as YYYY-MM-DD.');
      return;
    }
    setState(() {
      _previewing = true;
      saveError = null;
    });
    try {
      final LotSwitchPreview preview =
          await widget.api.lotSwitchPreview(_typedDay);
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _previewing = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _previewing = false;
        saveError = error.message;
      });
    }
  }

  Future<void> _pickDay() async {
    final DateTime initial = DateTime.tryParse(_typedDay) ?? DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() => _date.text = _day(picked));
  }

  /// Runs a write and keeps the dialog open: a refusal lands in the banner,
  /// an answer replaces the settings shown.
  Future<bool> _write(Future<LotSettings> Function() call) async {
    if (saving) return false;
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final LotSettings settings = await call();
      if (!mounted) return true;
      setState(() {
        _settings = settings;
        saving = false;
      });
      return true;
    } on ApiException catch (error) {
      if (!mounted) return false;
      setState(() {
        saving = false;
        saveError = error.message;
      });
      return false;
    }
  }

  Future<void> _switch() async {
    final String day = _typedDay;
    final bool? confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Switch to by lot?'),
        content: SizedBox(
          width: 460,
          child: Text(
            'From $day each purchase is costed by its own lot.\n\n'
            '- This is one way: the firm cannot go back to Average.\n'
            '- Nothing is re-valued and no journal is posted; the stock on '
            'hand becomes lots at the cost it already carries.\n'
            '- Bills already made keep the cost they were made with.\n'
            '- Afterwards, any stock movement dated before $day is refused.',
            key: const ValueKey('stock-costing-confirm-text'),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('stock-costing-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Switch to by lot'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final bool done = await _write(() => widget.api.switchToLotCosting(day));
    if (done && mounted) {
      setState(() => _preview = null);
      NotificationService.show(
        context,
        'Stock is now costed by lot from $day.',
        kind: AppNotificationKind.success,
      );
    }
  }

  Future<void> _setBilling(bool allow) async {
    final bool done = await _write(() => widget.api
        .updateLotSettings(allowBillingWithoutStock: allow));
    if (done && mounted) {
      NotificationService.show(
        context,
        allow
            ? 'Bills may now go out when no lot holds the stock.'
            : 'A bill now needs a lot that holds the stock.',
        kind: AppNotificationKind.success,
      );
    }
  }

  static String _quantity(String value) {
    if (!value.contains('.')) return value;
    final String trimmed = value.replaceFirst(RegExp(r'0+$'), '');
    return trimmed.endsWith('.')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }

  static String _money(String value) {
    final double? number = double.tryParse(value.trim());
    return number == null ? value : indianAmount(number, full: true);
  }

  Widget _figure(ThemeData theme, String label, String value, String key) =>
      Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.xs),
        child: Row(
          children: [
            Expanded(child: Text(label, style: theme.textTheme.bodyMedium)),
            Text(
              value,
              key: ValueKey('stock-costing-$key'),
              style: theme.textTheme.bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
          ],
        ),
      );

  Widget _previewBlock(ThemeData theme) {
    final LotSwitchPreview? preview = _preview;
    if (preview == null) return const SizedBox.shrink();
    final bool stale = !_previewIsForTypedDay;
    return Column(
      key: const ValueKey('stock-costing-preview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          stale
              ? 'This was for ${preview.on}. Show what will happen for the '
                  'day above before switching.'
              : 'Switching on ${preview.on} would:',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        _figure(theme, 'Items with stock', '${preview.items}', 'items'),
        _figure(theme, 'Lots to be made', '${preview.lots}', 'lots'),
        _figure(theme, 'Quantity', _quantity(preview.quantity), 'quantity'),
        _figure(theme, 'Stock value', _money(preview.stockValue), 'value'),
        if (preview.refusals.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(
            'It cannot be switched on this day until these are dealt with:',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.error),
          ),
          for (int i = 0; i < preview.refusals.length; i++)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.block,
                      size: 16, color: theme.colorScheme.error),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      preview.refusals[i],
                      key: ValueKey('stock-costing-refusal-$i'),
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }

  List<Widget> _average(ThemeData theme) => [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: TextField(
                key: const ValueKey('stock-costing-date'),
                controller: _date,
                enabled: _mayManage && !saving,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  labelText: 'Switch on (YYYY-MM-DD)',
                  helperText: 'Best on the first day of a financial year.',
                  suffixIcon: IconButton(
                    tooltip: 'Pick a day',
                    icon: const Icon(Icons.calendar_today_outlined),
                    onPressed: _mayManage && !saving ? _pickDay : null,
                  ),
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: OutlinedButton(
                key: const ValueKey('stock-costing-show'),
                onPressed: !_previewing && !saving ? _showPreview : null,
                child: Text(
                    _previewing ? 'Working it out…' : 'Show what will happen'),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        _previewBlock(theme),
      ];

  List<Widget> _byLot(ThemeData theme, LotSettings settings) => [
        SwitchListTile(
          key: const ValueKey('stock-costing-allow-billing'),
          contentPadding: EdgeInsets.zero,
          value: settings.allowBillingWithoutStock,
          onChanged: _mayManage && !saving ? _setBilling : null,
          title: const Text('Allow billing when no lot holds the stock'),
          subtitle: const Text(
            'The person making the bill is asked each time. The sale is '
            "costed when the purchase comes in and fills the lot it took "
            'from.',
          ),
        ),
      ];

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final LotSettings? settings = _settings;
    return AlertDialog(
      scrollable: true,
      icon: const Icon(Icons.inventory_2_outlined),
      title: const Text('Costing method'),
      content: SizedBox(
        width: 560,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_loadError != null || settings == null)
                    Text(
                      _loadError ?? 'The costing method could not be read.',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.error),
                    )
                  else ...[
                    Text(
                      settings.byLot
                          ? 'By lot, since ${settings.switchedOn ?? ''}'
                          : 'Average cost',
                      key: const ValueKey('stock-costing-method'),
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      settings.byLot
                          ? 'Each purchase is costed by its own lot, and a '
                              'sale takes the cost of the lot it left. This '
                              'cannot be switched back.'
                          : 'Every sale takes the running average cost of '
                              'the item. Switching to by lot costs each '
                              'purchase by its own lot from the day chosen. '
                              'It is one way, and best on the first day of '
                              'a financial year.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    saveErrorBanner(),
                    ...(settings.byLot
                        ? _byLot(theme, settings)
                        : _average(theme)),
                  ],
                  if (!_mayManage) ...[
                    const SizedBox(height: AppSpacing.lg),
                    Text(
                      'Changing the costing method needs the manage '
                      'inventory settings permission.',
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
        if (settings != null && !settings.byLot)
          FilledButton(
            key: const ValueKey('stock-costing-switch'),
            onPressed: _maySwitch ? _switch : null,
            child: Text(saving ? 'Switching…' : 'Switch to by lot'),
          ),
      ],
    );
  }
}
