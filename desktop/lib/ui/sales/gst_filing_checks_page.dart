// GST checks before filing (GST-5): what a return for the period would get
// wrong -- an invalid GSTIN, a missing or short HSN, no place of supply, no
// IRN, a credit note raised too late or against a cancelled bill -- listed by
// document so each can be fixed before the return is built.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/gst_filing_checks.dart';
import '../workspace/desktop_framework.dart';

/// The list of things to fix for a filing period.
class GstFilingChecksPage extends StatefulWidget {
  const GstFilingChecksPage({
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
  State<GstFilingChecksPage> createState() => _GstFilingChecksPageState();
}

class _GstFilingChecksPageState extends State<GstFilingChecksPage> {
  late DateTime _from;
  late DateTime _to;
  GstFilingChecks? _result;
  String? _error;
  bool _loading = false;
  int? _selected;

  bool get _mayView => widget.permissions.hasPermission('SALES_VIEW');

  @override
  void initState() {
    super.initState();
    final DateTime now = widget.today ?? DateTime.now();
    // Last month: the return most likely about to be filed.
    _from = DateTime(now.year, now.month - 1);
    _to = DateTime(now.year, now.month, 0);
    if (widget.hasActiveFirm && _mayView) _load();
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _selected = null;
      // Cleared before the read so a refusal never leaves another period's
      // findings under this period's dates.
      _result = null;
    });
    try {
      final Json data =
          await widget.api.getGstFilingChecks(from: _from, to: _to);
      if (!mounted) return;
      setState(() {
        _result = GstFilingChecks.fromJson(data);
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

  Future<void> _shiftMonth(int months) async {
    final DateTime start = DateTime(_from.year, _from.month + months);
    setState(() {
      _from = start;
      _to = DateTime(start.year, start.month + 1, 0);
    });
    await _load();
  }

  Future<void> _pickRange() async {
    final DateTime now = widget.today ?? DateTime.now();
    final DateTimeRange? picked = await showDateRangePicker(
      context: context,
      initialDateRange: DateTimeRange(start: _from, end: _to),
      firstDate: DateTime(2000),
      lastDate: DateTime(now.year + 1, 12, 31),
      helpText: 'Period to check',
      saveText: 'Use this period',
    );
    if (picked == null || !mounted) return;
    setState(() {
      _from = picked.start;
      _to = picked.end;
    });
    await _load();
  }

  String _summary(GstFilingChecks result) {
    final String errors =
        '${result.errors} ${result.errors == 1 ? 'error' : 'errors'}';
    final String warnings =
        '${result.warnings} ${result.warnings == 1 ? 'warning' : 'warnings'}';
    final int? digits = result.requiredHsnDigits;
    return '$errors, $warnings'
        '${digits == null ? '' : ' · HSN needs $digits digits at this firm\'s turnover'}';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'GST checks',
        message: 'Choose a firm to check its returns.',
      );
    }
    if (!_mayView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'GST checks',
        message: 'Checking a return needs the view sales permission.',
      );
    }
    final ThemeData theme = Theme.of(context);
    return LoadingOverlay(
      loading: _loading,
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              IconButton(
                key: const ValueKey('gst-checks-prev'),
                tooltip: 'Previous month',
                onPressed: _loading ? null : () => _shiftMonth(-1),
                icon: const Icon(Icons.chevron_left),
              ),
              OutlinedButton.icon(
                key: const ValueKey('gst-checks-period'),
                onPressed: _loading ? null : _pickRange,
                icon: const Icon(Icons.event, size: 18),
                label: Text('${_iso(_from)} to ${_iso(_to)}'),
              ),
              IconButton(
                key: const ValueKey('gst-checks-next'),
                tooltip: 'Next month',
                onPressed: _loading ? null : () => _shiftMonth(1),
                icon: const Icon(Icons.chevron_right),
              ),
              OutlinedButton.icon(
                key: const ValueKey('gst-checks-refresh'),
                onPressed: _loading ? null : _load,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('Refresh'),
              ),
              _openAction(),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          if (_error != null)
            Text(_error!,
                key: const ValueKey('gst-checks-error'),
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error))
          else if (_result != null) ...[
            Text(_summary(_result!),
                key: const ValueKey('gst-checks-summary'),
                style: theme.textTheme.titleSmall),
            const SizedBox(height: AppSpacing.md),
            if (_result!.rows.isEmpty)
              const SizedBox(
                height: 240,
                child: StandardEmptyState(
                  key: ValueKey('gst-checks-none'),
                  type: EmptyStateType.noRecords,
                  title: 'Nothing to fix for this period',
                  message: 'Every check passed for the documents in it.',
                ),
              )
            else
              _table(_result!.rows),
          ],
        ],
      ),
    );
  }

  /// There is no screen that opens one document by its id, so the action
  /// stays off and says where to go instead.
  Widget _openAction() {
    final GstFilingCheckRow? row = _selected == null || _result == null
        ? null
        : _result!.rows[_selected!];
    final String tip = row == null
        ? 'Select a row first'
        : row.documentType == 'FIRM'
            ? 'Fix the firm\'s GSTIN under Firms'
            : row.documentId == null
                ? 'This finding has no document to open'
                : 'Open ${row.documentNumber} from its own list';
    return Tooltip(
      message: tip,
      child: OutlinedButton.icon(
        key: const ValueKey('gst-checks-open'),
        onPressed: null,
        icon: const Icon(Icons.open_in_new, size: 18),
        label: const Text('Open document'),
      ),
    );
  }

  Widget _severity(GstFilingCheckRow row) => row.isError
      ? const StatusBadge(label: 'Error', tone: StatusBadgeTone.danger)
      : const StatusBadge(label: 'Warning', tone: StatusBadgeTone.warning);

  Widget _table(List<GstFilingCheckRow> rows) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        showCheckboxColumn: false,
        columns: const [
          DataColumn(label: Text('Severity')),
          DataColumn(label: Text('Check')),
          DataColumn(label: Text('Document')),
          DataColumn(label: Text('Number')),
          DataColumn(label: Text('Date')),
          DataColumn(label: Text('Party')),
          DataColumn(label: Text('What is wrong')),
        ],
        rows: [
          for (int i = 0; i < rows.length; i++)
            DataRow(
              key: ValueKey('gst-check-row-$i'),
              selected: _selected == i,
              onSelectChanged: (_) => setState(() => _selected = i),
              cells: [
                DataCell(_severity(rows[i])),
                DataCell(Text(rows[i].checkLabel)),
                DataCell(Text(rows[i].documentTypeLabel)),
                DataCell(Text(rows[i].documentNumber)),
                DataCell(Text(rows[i].documentDate)),
                DataCell(Text(rows[i].partyName)),
                DataCell(ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 480),
                  child: Text(rows[i].message,
                      maxLines: 2, overflow: TextOverflow.ellipsis),
                )),
              ],
            ),
        ],
      ),
    );
  }
}
