// GSTR-2B reconciliation (backlog 78 row 3).
//
// Input tax credit is claimable only on what a supplier has filed, and the
// portal's monthly GSTR-2B statement is what says so. The file is imported
// here, each supplier document in it is matched to a bill in the books, and
// the screen names what differs, what the books lack and what 2B lacks.

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// A file the person chose: its name and its text.
typedef Gstr2bFile = ({String name, String text});

/// Which list is on screen.
enum _Gstr2bView { portal, booksOnly }

/// Import a GSTR-2B file and reconcile it with the supplier bills.
class Gstr2bPage extends StatefulWidget {
  const Gstr2bPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.today,
    this.pickFile,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// For tests; the clock otherwise.
  final DateTime? today;

  /// For tests; the system file dialog otherwise.
  final Future<Gstr2bFile?> Function()? pickFile;

  @override
  State<Gstr2bPage> createState() => _Gstr2bPageState();
}

class _Gstr2bPageState extends State<Gstr2bPage> {
  late final DateTime _today = widget.today ?? DateTime.now();
  late String _period = _month(DateTime(_today.year, _today.month - 1));
  _Gstr2bView _view = _Gstr2bView.portal;
  Json? _data;
  String? _error;
  bool _loading = false;

  static String _month(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}';

  List<String> get _months => [
        for (int back = 0; back < 24; back++)
          _month(DateTime(_today.year, _today.month - back)),
      ];

  bool get _canView =>
      widget.permissions.hasPermission('ACCOUNT_VIEW') ||
      widget.permissions.hasPermission('SALES_VIEW');
  bool get _canPost => widget.permissions.hasPermission('JOURNAL_POST');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _canView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json data = await widget.api.gstr2bReconciliation(_period);
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

  Future<Gstr2bFile?> _choose() async {
    if (widget.pickFile != null) return widget.pickFile!();
    final XFile? file = await openFile(
      acceptedTypeGroups: const [
        XTypeGroup(label: 'GSTR-2B (JSON)', extensions: ['json']),
      ],
    );
    if (file == null) return null;
    return (name: file.name, text: await file.readAsString());
  }

  Future<void> _import() async {
    final Gstr2bFile? file = await _choose();
    if (file == null || !mounted) return;
    setState(() => _loading = true);
    try {
      final Json result = await widget.api.importGstr2b(
        returnPeriod: _period,
        content: file.text,
        sourceName: file.name,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        'GSTR-2B for $_period: ${result['document_count'] ?? 0} documents.',
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

  Future<void> _match(Json row) async {
    final String? billId = await showDialog<String>(
      context: context,
      builder: (_) => _BillPicker(
        api: widget.api,
        supplierName: stringValue(row['supplier_name']),
        supplierGstin: stringValue(row['supplier_gstin']),
      ),
    );
    if (billId == null || !mounted) return;
    await _send(row, billId);
  }

  Future<void> _send(Json row, String? billId) async {
    setState(() => _loading = true);
    try {
      await widget.api.matchGstr2bDocument('${row['id']}', billId);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loading = false);
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
      return;
    }
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'GSTR-2B reconciliation',
        message: 'You do not have permission to see this.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'GSTR-2B reconciliation',
        message: 'Choose a firm to reconcile its input credit.',
      );
    }
    final ThemeData theme = Theme.of(context);
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
              SizedBox(
                width: 150,
                child: DropdownButtonFormField<String>(
                  key: const ValueKey('gstr2b-period'),
                  initialValue: _period,
                  decoration: const InputDecoration(
                      labelText: 'Return month', isDense: true),
                  items: [
                    for (final String month in _months)
                      DropdownMenuItem(value: month, child: Text(month)),
                  ],
                  onChanged: (value) {
                    if (value == null) return;
                    setState(() => _period = value);
                    _load();
                  },
                ),
              ),
              FilledButton.icon(
                key: const ValueKey('gstr2b-import'),
                onPressed: _canPost && !_loading ? _import : null,
                icon: const Icon(Icons.upload_file),
                label: const Text('Import 2B file'),
              ),
              if (!_canPost)
                Text(
                  'Importing needs the post journals permission.',
                  style: theme.textTheme.bodySmall,
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          if (_error != null)
            Text(_error!,
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error))
          else if (_data != null)
            ..._body(theme, _data!),
        ],
      ),
    );
  }

  List<Widget> _body(ThemeData theme, Json data) {
    if (data['imported'] != true) {
      return [
        Text(
          'No GSTR-2B has been imported for $_period. Download the file from '
          'the GST portal and choose Import 2B file.',
          key: const ValueKey('gstr2b-none'),
          style: theme.textTheme.bodyMedium,
        ),
      ];
    }
    final Map<String, dynamic> counts =
        (data['counts'] as Map?)?.cast<String, dynamic>() ?? const {};
    final String skipped = stringValue(data['skipped_sections']);
    final List<Json> documents = _rows(data['documents']);
    final List<Json> booksOnly = _rows(data['in_books_only']);
    const List<(String, String)> chips = [
      ('MATCHED', 'Matched'),
      ('DIFFERENT', 'Different'),
      ('NOT_IN_BOOKS', 'Not in books'),
      ('MANUAL', 'Matched by hand'),
      ('IN_BOOKS_ONLY', 'In books, not in 2B'),
    ];
    return [
      Text(
        'From ${stringValue(data['source_name']).isEmpty ? 'a file' : stringValue(data['source_name'])}, '
        'imported ${stringValue(data['imported_at'])}.',
        style: theme.textTheme.bodySmall,
      ),
      if (skipped.isNotEmpty) ...[
        const SizedBox(height: AppSpacing.xs),
        Row(
          key: const ValueKey('gstr2b-skipped'),
          children: [
            Icon(Icons.info_outline,
                size: 16, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: AppSpacing.xs),
            Expanded(
              child: Text('Not read from this file: $skipped',
                  style: theme.textTheme.bodySmall),
            ),
          ],
        ),
      ],
      const SizedBox(height: AppSpacing.md),
      Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          for (final (String key, String label) in chips)
            if (key == 'IN_BOOKS_ONLY' || counts[key] != null)
              Chip(
                key: ValueKey('gstr2b-count-$key'),
                label: Text('$label: ${counts[key] ?? 0}'),
              ),
        ],
      ),
      const SizedBox(height: AppSpacing.md),
      SegmentedButton<_Gstr2bView>(
        segments: const [
          ButtonSegment(
              value: _Gstr2bView.portal, label: Text('In GSTR-2B')),
          ButtonSegment(
              value: _Gstr2bView.booksOnly,
              label: Text('In books, not in 2B')),
        ],
        selected: {_view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) =>
            setState(() => _view = selection.first),
      ),
      const SizedBox(height: AppSpacing.md),
      if (_view == _Gstr2bView.portal)
        _portalTable(theme, documents)
      else
        _booksOnlyTable(theme, booksOnly),
    ];
  }

  static List<Json> _rows(Object? value) => value is List
      ? [for (final Object? row in value) Map<String, dynamic>.from(row as Map)]
      : <Json>[];

  static String _money(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }

  static double _num(Object? value) => double.tryParse('${value ?? 0}') ?? 0;

  Widget _status(String status) => switch (status) {
        'MATCHED' =>
          const StatusBadge(label: 'Matched', tone: StatusBadgeTone.success),
        'DIFFERENT' =>
          const StatusBadge(label: 'Different', tone: StatusBadgeTone.warning),
        'NOT_IN_BOOKS' => const StatusBadge(
            label: 'Not in books', tone: StatusBadgeTone.danger),
        'MANUAL' =>
          const StatusBadge(label: 'Manual', tone: StatusBadgeTone.info),
        _ => StatusBadge(label: status),
      };

  Widget _portalTable(ThemeData theme, List<Json> rows) {
    if (rows.isEmpty) {
      return Text('Nothing in this file.', style: theme.textTheme.bodySmall);
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Supplier')),
          DataColumn(label: Text('GSTIN')),
          DataColumn(label: Text('Type')),
          DataColumn(label: Text('Number')),
          DataColumn(label: Text('Date')),
          DataColumn(label: Text('Taxable'), numeric: true),
          DataColumn(label: Text('Tax'), numeric: true),
          DataColumn(label: Text('Status')),
          DataColumn(label: Text('Note')),
          DataColumn(label: Text('')),
        ],
        rows: [
          for (final Json row in rows)
            DataRow(
              key: ValueKey('gstr2b-row-${row['id']}'),
              cells: [
                DataCell(Text(stringValue(row['supplier_name']))),
                DataCell(Text(stringValue(row['supplier_gstin']))),
                DataCell(Text(stringValue(row['document_type']))),
                DataCell(Text(stringValue(row['document_number']))),
                DataCell(Text(stringValue(row['document_date']))),
                DataCell(Text(_money(row['taxable_value']))),
                DataCell(Text(_money(_num(row['igst']) +
                    _num(row['cgst']) +
                    _num(row['sgst']) +
                    _num(row['cess'])))),
                DataCell(_status(stringValue(row['match_status']))),
                DataCell(ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 280),
                  child: Text(stringValue(row['match_note']),
                      overflow: TextOverflow.ellipsis),
                )),
                DataCell(_action(row)),
              ],
            ),
        ],
      ),
    );
  }

  Widget _action(Json row) {
    final String status = stringValue(row['match_status']);
    final bool invoice = stringValue(row['document_type']) == 'INVOICE';
    if (!_canPost) return const SizedBox.shrink();
    if (status == 'MANUAL') {
      return TextButton(
        key: ValueKey('gstr2b-undo-${row['id']}'),
        onPressed: () => _send(row, null),
        child: const Text('Undo match'),
      );
    }
    if (invoice && (status == 'NOT_IN_BOOKS' || status == 'DIFFERENT')) {
      return TextButton(
        key: ValueKey('gstr2b-match-${row['id']}'),
        onPressed: () => _match(row),
        child: const Text('Match to bill…'),
      );
    }
    return const SizedBox.shrink();
  }

  Widget _booksOnlyTable(ThemeData theme, List<Json> rows) {
    if (rows.isEmpty) {
      return Text('Every bill in the books is in this 2B.',
          style: theme.textTheme.bodySmall);
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Bill')),
          DataColumn(label: Text('Supplier invoice')),
          DataColumn(label: Text('Date')),
          DataColumn(label: Text('Supplier')),
          DataColumn(label: Text('GSTIN')),
          DataColumn(label: Text('Tax'), numeric: true),
        ],
        rows: [
          for (final Json row in rows)
            DataRow(
              key: ValueKey('gstr2b-books-${row['purchase_invoice_id']}'),
              cells: [
                DataCell(Text(stringValue(row['invoice_number']))),
                DataCell(Text(stringValue(row['supplier_invoice_number']))),
                DataCell(Text(stringValue(row['supplier_invoice_date']))),
                DataCell(Text(stringValue(row['supplier_name']))),
                DataCell(Text(stringValue(row['supplier_gstin']))),
                DataCell(Text(_money(row['tax_total']))),
              ],
            ),
        ],
      ),
    );
  }
}

/// Choose one of the supplier's bills; pops its id.
class _BillPicker extends StatefulWidget {
  const _BillPicker({
    required this.api,
    required this.supplierName,
    required this.supplierGstin,
  });

  final ApiClient api;
  final String supplierName;
  final String supplierGstin;

  @override
  State<_BillPicker> createState() => _BillPickerState();
}

class _BillPickerState extends State<_BillPicker> {
  late final TextEditingController _search =
      TextEditingController(text: widget.supplierName);
  List<Json> _bills = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _find();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _find() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json page = await widget.api.documentPage(
        'purchase-invoices',
        pageSize: 50,
        search: _search.text.trim(),
      );
      final dynamic data = page['data'];
      if (!mounted) return;
      setState(() {
        _bills = data is List
            ? [
                for (final Object? row in data)
                  if (row is Map &&
                      '${row['status']}'.toUpperCase() != 'CANCELLED')
                    Map<String, dynamic>.from(row),
              ]
            : <Json>[];
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

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Match to bill'),
      content: SizedBox(
        width: 520,
        height: 380,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${widget.supplierName} ${widget.supplierGstin}',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              key: const ValueKey('gstr2b-bill-search'),
              controller: _search,
              decoration: const InputDecoration(
                labelText: 'Search bills',
                isDense: true,
                suffixIcon: Icon(Icons.search),
              ),
              onSubmitted: (_) => _find(),
            ),
            const SizedBox(height: AppSpacing.sm),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Text(_error!)
                      : _bills.isEmpty
                          ? const Text('No bills found.')
                          : ListView(
                              children: [
                                for (final Json bill in _bills)
                                  ListTile(
                                    key: ValueKey('gstr2b-bill-${bill['id']}'),
                                    dense: true,
                                    title: Text(
                                        '${stringValue(bill['invoice_number'])}'
                                        ' · ${stringValue(bill['vendor_name'])}'),
                                    subtitle: Text(
                                        'Supplier invoice '
                                        '${stringValue(bill['supplier_invoice_number'])}'
                                        ' · ${stringValue(bill['grand_total'])}'),
                                    onTap: () => Navigator.of(context)
                                        .pop('${bill['id']}'),
                                  ),
                              ],
                            ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
