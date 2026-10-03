// Export to Tally (MSG-5): download the period's ledgers and vouchers as a
// TallyPrime import file, and say what each account is called there.
// Phase 2 only.

import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart' show Json;
import '../workspace/desktop_framework.dart';

/// The groups a firm most often needs; the box also takes any other name.
const List<String> tallyGroups = [
  'Sundry Debtors',
  'Sundry Creditors',
  'Bank Accounts',
  'Cash-in-Hand',
  'Duties & Taxes',
  'Sales Accounts',
  'Purchase Accounts',
  'Stock-in-Hand',
  'Current Assets',
  'Current Liabilities',
  'Direct Incomes',
  'Indirect Incomes',
  'Direct Expenses',
  'Indirect Expenses',
  'Capital Account',
  'Suspense A/c',
];

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

class _MapRow {
  _MapRow(Json json)
      : id = '${json['ledger_account_id']}',
        code = '${json['account_code'] ?? ''}',
        name = '${json['account_name'] ?? ''}',
        mapped = json['mapped'] == true,
        initialName = '${json['tally_name'] ?? ''}',
        initialParent = '${json['tally_parent'] ?? ''}',
        tallyName = TextEditingController(text: '${json['tally_name'] ?? ''}'),
        tallyParent =
            TextEditingController(text: '${json['tally_parent'] ?? ''}');

  final String id;
  final String code;
  final String name;
  final bool mapped;
  final String initialName;
  final String initialParent;
  final TextEditingController tallyName;
  final TextEditingController tallyParent;

  bool get changed =>
      tallyName.text != initialName || tallyParent.text != initialParent;
}

/// Pick the period, download the file, and edit the Tally names.
class TallyExportPage extends StatefulWidget {
  const TallyExportPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveBytesOverride,
    this.today,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Tests inject this, because a widget test cannot open a save panel.
  final SaveBytesOverride? saveBytesOverride;

  /// For tests; the clock otherwise.
  final DateTime? today;

  @override
  State<TallyExportPage> createState() => _TallyExportPageState();
}

class _TallyExportPageState extends State<TallyExportPage> {
  List<_MapRow> _rows = const [];
  String? _error;
  bool _loading = true;
  bool _busy = false;
  late DateTime _from;
  late DateTime _to;

  bool get _mayView => widget.permissions.hasPermission('LEDGER_VIEW');
  bool get _maySave => widget.permissions.hasPermission('JOURNAL_POST');

  @override
  void initState() {
    super.initState();
    final DateTime now = widget.today ?? DateTime.now();
    // The last full month.
    _from = DateTime(now.year, now.month - 1, 1);
    _to = DateTime(now.year, now.month, 0);
    if (widget.hasActiveFirm && _mayView) {
      unawaited(_load());
    } else {
      _loading = false;
    }
  }

  @override
  void dispose() {
    _disposeRows();
    super.dispose();
  }

  void _disposeRows() {
    for (final _MapRow row in _rows) {
      row.tallyName.dispose();
      row.tallyParent.dispose();
    }
  }

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<Json> data = await widget.api.tallyMappings();
      if (!mounted) return;
      setState(() {
        _disposeRows();
        _rows = data.map(_MapRow.new).toList();
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

  Future<void> _pick(bool from) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: from ? _from : _to,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() => from ? _from = picked : _to = picked);
  }

  Future<void> _export() async {
    if (_to.isBefore(_from)) {
      _tell('The end date is before the start date.',
          AppNotificationKind.error);
      return;
    }
    setState(() => _busy = true);
    try {
      final List<int> bytes =
          await widget.api.tallyExport(_iso(_from), _iso(_to));
      if (!mounted) return;
      final String name =
          'tally-${_iso(_from).replaceAll('-', '')}-${_iso(_to).replaceAll('-', '')}.xml';
      String where = name;
      if (widget.saveBytesOverride != null) {
        await widget.saveBytesOverride!(name, bytes);
      } else {
        final FileSaveLocation? location = await getSaveLocation(
          suggestedName: name,
          acceptedTypeGroups: const [
            XTypeGroup(label: 'XML file', extensions: ['xml']),
          ],
        );
        if (location == null) return;
        await File(location.path).writeAsBytes(bytes, flush: true);
        where = location.path;
      }
      if (!mounted) return;
      _tell('The Tally file was saved to $where.',
          AppNotificationKind.success);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final List<Json> sent = [
      for (final _MapRow row in _rows)
        if (row.mapped || row.changed)
          <String, dynamic>{
            'ledger_account_id': row.id,
            'tally_name': row.tallyName.text.trim(),
            'tally_parent': row.tallyParent.text.trim().isEmpty
                ? null
                : row.tallyParent.text.trim(),
          },
    ];
    setState(() => _busy = true);
    try {
      await widget.api.replaceTallyMappings({'mappings': sent});
      if (!mounted) return;
      _tell('Tally names saved.', AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _dateButton(String key, String label, DateTime value, bool from) =>
      OutlinedButton.icon(
        key: ValueKey(key),
        icon: const Icon(Icons.calendar_today, size: 16),
        label: Text('$label ${_iso(value)}'),
        onPressed: _busy ? null : () => unawaited(_pick(from)),
      );

  Widget _row(_MapRow row) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          SizedBox(width: 90, child: Text(row.code)),
          Expanded(
            flex: 3,
            child: Text(row.name, overflow: TextOverflow.ellipsis),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 3,
            child: TextField(
              key: ValueKey('tally-name-${row.id}'),
              controller: row.tallyName,
              enabled: _maySave,
              decoration: const InputDecoration(
                  isDense: true, border: OutlineInputBorder()),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 3,
            child: TextField(
              key: ValueKey('tally-parent-${row.id}'),
              controller: row.tallyParent,
              enabled: _maySave,
              decoration: InputDecoration(
                isDense: true,
                border: const OutlineInputBorder(),
                suffixIcon: PopupMenuButton<String>(
                  key: ValueKey('tally-group-${row.id}'),
                  tooltip: 'Common Tally groups',
                  icon: const Icon(Icons.arrow_drop_down),
                  enabled: _maySave,
                  onSelected: (String value) =>
                      setState(() => row.tallyParent.text = value),
                  itemBuilder: (_) => [
                    for (final String group in tallyGroups)
                      PopupMenuItem<String>(value: group, child: Text(group)),
                  ],
                ),
              ),
            ),
          ),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'The export is made from one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        title: 'Not available',
        message: 'You do not have permission to export the books.',
      );
    }
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
          spacing: 12,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _dateButton('tally-from', 'From', _from, true),
            _dateButton('tally-to', 'To', _to, false),
            FilledButton.icon(
              key: const ValueKey('tally-export'),
              icon: const Icon(Icons.file_download_outlined),
              label: const Text('Export'),
              onPressed: _busy ? null : () => unawaited(_export()),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'Party ledgers are created from customer and supplier names under '
          'Sundry Debtors / Creditors. Import the file in TallyPrime: '
          'Gateway > Import > Masters, then Vouchers.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        Row(children: [
          Text('Ledger names in Tally',
              style: Theme.of(context).textTheme.titleMedium),
          const Spacer(),
          if (_maySave)
            FilledButton(
              key: const ValueKey('tally-save'),
              onPressed: _busy || _loading ? null : () => unawaited(_save()),
              child: const Text('Save names'),
            ),
        ]),
        const SizedBox(height: 8),
        Row(children: const [
          SizedBox(width: 90, child: Text('Code')),
          Expanded(flex: 3, child: Text('Name')),
          SizedBox(width: 8),
          Expanded(flex: 3, child: Text('Tally name')),
          SizedBox(width: 8),
          Expanded(flex: 3, child: Text('Tally group')),
        ]),
        const Divider(),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(child: Text(_error!))
                  : ListView(children: [for (final _MapRow r in _rows) _row(r)]),
        ),
      ]),
    );
  }
}
