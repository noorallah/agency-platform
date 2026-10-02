// Rule 37 (backlog 78 row 4): input credit on a supplier bill unpaid 180 days
// after its date is reversed in proportion to what is unpaid, and reclaimed as
// it is paid. The screen lists what is due as of a date and, where the firm
// has switched posting on, posts it.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// The 180-day unpaid-bill list, and the action that posts it.
class Rule37Page extends StatefulWidget {
  const Rule37Page({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<Rule37Page> createState() => _Rule37PageState();
}

class _Rule37PageState extends State<Rule37Page> {
  late DateTime _asOf = widget.today ?? DateTime.now();
  Json? _data;
  String? _error;
  bool _loading = false;
  final Set<String> _selected = <String>{};

  bool get _canView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('SALES_VIEW');
  bool get _canPost => widget.permissions.hasPermission('JOURNAL_POST');

  String get _asOfText => _asOf.toIso8601String().split('T').first;

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _canView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _selected.clear();
    });
    try {
      final Json data = await widget.api.rule37(_asOfText);
      if (!mounted) return;
      setState(() {
        _data = data;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _data = null;
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _asOf,
      firstDate: DateTime(2017),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() => _asOf = picked);
    await _load();
  }

  Future<void> _post() async {
    setState(() => _loading = true);
    try {
      await widget.api.postRule37(
        _asOfText,
        purchaseInvoiceIds: _selected.isEmpty ? null : _selected.toList(),
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        _selected.isEmpty
            ? 'Rule 37 reversals and reclaims posted.'
            : 'Rule 37 posted for ${_selected.length} selected bill(s).',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
      return;
    }
    await _load();
  }

  static List<Json> _rows(Object? value) => value is List
      ? [for (final Object? row in value) Map<String, dynamic>.from(row as Map)]
      : <Json>[];

  static double _num(Object? value) => double.tryParse('${value ?? 0}') ?? 0;

  static String _money(Object? value) => _num(value).toStringAsFixed(2);

  /// The four heads of a tax block added up.
  static String _tax(Object? block) {
    if (block is! Map) return '0.00';
    return _money(_num(block['igst']) +
        _num(block['cgst']) +
        _num(block['sgst']) +
        _num(block['cess']));
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Rule 37 (180 days)',
        message: 'You do not have permission to see this.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Rule 37 (180 days)',
        message: 'Choose a firm to see its unpaid bills.',
      );
    }
    final ThemeData theme = Theme.of(context);
    final String mode = stringValue(_data?['mode']);
    final List<Json> rows = _rows(_data?['rows']);
    return LoadingOverlay(
      loading: _loading,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              OutlinedButton.icon(
                key: const ValueKey('rule37-as-of'),
                onPressed: _loading ? null : _pickDate,
                icon: const Icon(Icons.event, size: 18),
                label: Text('As of $_asOfText'),
              ),
              if (mode == 'POST' && _canPost)
                FilledButton.icon(
                  key: const ValueKey('rule37-post'),
                  onPressed: _loading || rows.isEmpty ? null : _post,
                  icon: const Icon(Icons.playlist_add_check),
                  label: Text(_selected.isEmpty
                      ? 'Post reversals and reclaims'
                      : 'Post ${_selected.length} selected'),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          if (_error != null)
            Text(_error!,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error))
          else if (_data != null) ...[
            if (mode == 'OFF')
              Text(
                'Rule 37 is turned off in Settings > Tax > GST Documents.',
                key: const ValueKey('rule37-off'),
                style: theme.textTheme.bodyMedium,
              )
            else ...[
              Text(
                mode == 'POST'
                    ? 'Credit on a bill unpaid 180 days is reversed in '
                        'proportion to what is unpaid, and reclaimed as it '
                        'is paid. Posting writes the journals.'
                    : 'Report only: nothing is posted. GSTR-3B is not '
                        'changed until the firm chooses Report and post in '
                        'Settings > Tax > GST Documents.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              _table(theme, rows, mode == 'POST' && _canPost),
            ],
          ],
        ],
      ),
    );
  }

  Widget _table(ThemeData theme, List<Json> rows, bool selectable) {
    if (rows.isEmpty) {
      return Text('No bill is due for a reversal or a reclaim as of this date.',
          key: const ValueKey('rule37-none'), style: theme.textTheme.bodySmall);
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Bill')),
          DataColumn(label: Text('Supplier')),
          DataColumn(label: Text('Bill date')),
          DataColumn(label: Text('Days'), numeric: true),
          DataColumn(label: Text('Total'), numeric: true),
          DataColumn(label: Text('Outstanding'), numeric: true),
          DataColumn(label: Text('Credit'), numeric: true),
          DataColumn(label: Text('Action')),
          DataColumn(label: Text('Amount'), numeric: true),
        ],
        rows: [
          for (final Json row in rows)
            DataRow(
              key: ValueKey('rule37-row-${row['purchase_invoice_id']}'),
              selected: _selected.contains('${row['purchase_invoice_id']}'),
              onSelectChanged: selectable
                  ? (bool? value) => setState(() {
                        final String id = '${row['purchase_invoice_id']}';
                        if (value == true) {
                          _selected.add(id);
                        } else {
                          _selected.remove(id);
                        }
                      })
                  : null,
              cells: [
                DataCell(Text(stringValue(row['invoice_number']))),
                DataCell(Text(stringValue(row['vendor_name']))),
                DataCell(Text(stringValue(row['bill_date']))),
                DataCell(Text(stringValue(row['days']))),
                DataCell(Text(_money(row['bill_total']))),
                DataCell(Text(_money(row['outstanding']))),
                DataCell(Text(_tax(row['credit']))),
                DataCell(_action(stringValue(row['action']))),
                DataCell(Text(_tax(row['amount']))),
              ],
            ),
        ],
      ),
    );
  }

  Widget _action(String action) => switch (action) {
        'REVERSE' =>
          const StatusBadge(label: 'Reverse', tone: StatusBadgeTone.warning),
        'RECLAIM' =>
          const StatusBadge(label: 'Reclaim', tone: StatusBadgeTone.success),
        _ => StatusBadge(label: action),
      };
}
