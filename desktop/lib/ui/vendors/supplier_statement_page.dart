// What a supplier's account did over a period.
//
// The mirror of the customer statement: a movement, not a position. The
// balance is what the firm owes the supplier; a negative one is an advance or
// credit held with them. Also draws the balance confirmation letters a firm
// sends its suppliers to agree the figure.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/vendor.dart';
import '../../phase2/indian_format.dart';
import '../workspace/balance_confirmation.dart';
import '../workspace/desktop_framework.dart';

/// Pick a supplier, read their account over a period, send them a letter.
class SupplierStatementPage extends StatefulWidget {
  const SupplierStatementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.letters = const BalanceConfirmationActions(),
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// How letters are shown and saved; tests replace it.
  final BalanceConfirmationActions letters;

  @override
  State<SupplierStatementPage> createState() => _SupplierStatementPageState();
}

class _SupplierStatementPageState extends State<SupplierStatementPage> {
  DateTime _from = _monthsAgo(3);
  DateTime _to = DateTime.now();

  List<Vendor> _vendors = const [];
  String? _vendorId;
  Json? _statement;
  String? _error;
  bool _loading = false;

  bool get _mayView => widget.permissions.hasPermission('VENDOR_VIEW');

  static DateTime _monthsAgo(int months) {
    final DateTime now = DateTime.now();
    return DateTime(now.year, now.month - months, now.day);
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_loadVendors());
  }

  Future<void> _loadVendors() async {
    setState(() => _loading = true);
    try {
      final List<Vendor> vendors = await fetchAllPages<Vendor>(
        (page) => widget.api.vendors(page: page),
      );
      if (!mounted) return;
      setState(() {
        _vendors = vendors;
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

  Future<void> _loadStatement(String vendorId) async {
    setState(() {
      _loading = true;
      _error = null;
      // Dropped on the way in, so one supplier's figures never sit under
      // another's name while the next is read.
      _statement = null;
      _vendorId = vendorId;
    });
    try {
      final Json answer = await widget.api.supplierStatement(
        vendorId,
        fromDate: _iso(_from),
        toDate: _iso(_to),
      );
      if (!mounted) return;
      setState(() {
        _statement = answer;
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

  void _refresh() {
    final String? id = _vendorId;
    if (id != null) {
      unawaited(_loadStatement(id));
    } else {
      unawaited(_loadVendors());
    }
  }

  Vendor? get _vendor => _vendors.where((v) => v.id == _vendorId).firstOrNull;

  Future<void> _confirmation() async {
    final Vendor? vendor = _vendor;
    if (vendor == null) return;
    await widget.letters.letter(
      context,
      fetch: () =>
          widget.api.supplierBalanceConfirmation(vendor.id, asOf: _iso(_to)),
      documentName: 'Balance confirmation ${vendor.displayName}',
    );
  }

  Future<void> _everyone() => widget.letters.everyone(
        context,
        fetch: () => widget.api.supplierBalanceConfirmations(asOf: _iso(_to)),
        suggestedName: 'supplier-balance-confirmations-${_iso(_to)}.zip',
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'An account belongs to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see this',
        message: 'Reading what the firm owes suppliers needs the view '
            'vendors permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (_) => !_loading,
        onAction: (_) => _refresh(),
        trailing: [
          DateRangeFilter(
            value: DatePeriod.custom(_from, _to),
            onChanged: (period) {
              setState(() {
                _from = period.from ?? _from;
                _to = period.to ?? _to;
              });
              final String? id = _vendorId;
              if (id != null) unawaited(_loadStatement(id));
            },
          ),
        ],
        commands: [
          ToolbarCommand(
            id: 'balance-confirmation',
            label: 'Balance confirmation',
            icon: Icons.mark_email_read_outlined,
            menuOnly: true,
            tooltip: 'A letter asking the supplier to confirm the balance '
                'on the period’s end date',
            onPressed:
                _vendorId == null ? null : () => unawaited(_confirmation()),
          ),
          // Not about the supplier on show.
          ToolbarCommand(
            id: 'letters-everyone',
            label: 'Letters for everyone with a balance',
            icon: Icons.folder_zip_outlined,
            menuOnly: true,
            tooltip: 'One letter per supplier with a balance, as of the '
                'period’s end date, saved as a zip',
            onPressed: () => unawaited(_everyone()),
          ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      notice: 'What the firm owes each supplier. A positive balance is owed '
          'to them; a negative one is an advance held with them. Balances '
          'are recomputed in date order.',
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _lines().length,
        selected: false,
        message: 'Positive: the firm owes the supplier.',
      ),
    );
  }

  List<dynamic> _lines() =>
      _statement?['lines'] as List<dynamic>? ?? const <dynamic>[];

  Widget _picker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: DropdownButtonFormField<String>(
        key: const ValueKey('ss-vendor'),
        initialValue: _vendorId,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Supplier'),
        items: [
          for (final Vendor vendor in _vendors)
            DropdownMenuItem<String>(
              value: vendor.id,
              child: Text(
                vendor.code.isEmpty
                    ? vendor.displayName
                    : '${vendor.code} · ${vendor.displayName}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: _loading
            ? null
            : (id) {
                if (id != null) unawaited(_loadStatement(id));
              },
      ),
    );
  }

  Widget _content() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _picker(),
        Expanded(child: _body()),
      ],
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    final Json? statement = _statement;
    if (statement == null) {
      return const WorkspaceEmptyState(
        title: 'Choose a supplier',
        message: 'Pick one above to read their account.',
      );
    }
    final List<dynamic> lines = _lines();
    double amount(Object? value) => double.tryParse('${value ?? 0}') ?? 0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SummaryCards(children: [
          SummaryCount(
            label: stringValue(statement['vendor_name']),
            value: '',
          ),
          SummaryCount(
            label: 'Opening',
            value: indianAmount(amount(statement['opening_balance']),
                full: true),
          ),
          SummaryCount(
            label: 'Debit',
            value:
                indianAmount(amount(statement['total_debit']), full: true),
          ),
          SummaryCount(
            label: 'Credit',
            value:
                indianAmount(amount(statement['total_credit']), full: true),
          ),
          SummaryCount(
            label: 'Closing',
            value: indianAmount(amount(statement['closing_balance']),
                full: true),
          ),
        ]),
        Expanded(
          child: lines.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'Nothing moved',
                  message: 'The account had no activity in this period.',
                )
              : EnterpriseDataGrid<Map>(
                  items: [for (final dynamic line in lines) line as Map],
                  total: lines.length,
                  pageOffset: 0,
                  rowsPerPage: lines.length,
                  availableRowsPerPage: [lines.length],
                  columns: const [
                    GridColumn(key: 'date', label: 'Date'),
                    GridColumn(key: 'type', label: 'Type'),
                    GridColumn(
                        key: 'reference', label: 'Reference', priority: 1),
                    GridColumn(key: 'debit', label: 'Debit', numeric: true),
                    GridColumn(key: 'credit', label: 'Credit', numeric: true),
                    GridColumn(
                        key: 'balance', label: 'Balance', numeric: true),
                  ],
                  id: (line) => '${line['reference_number']}|'
                      '${line['transaction_date']}|${line.hashCode}',
                  cells: (line) => [
                    stringValue(line['transaction_date']),
                    statusInWords(stringValue(line['transaction_type'])),
                    stringValue(line['reference_number']),
                    _money(line['debit']),
                    _money(line['credit']),
                    _money(line['balance']),
                  ],
                  onSelect: (_) {},
                  onPageChanged: (_) {},
                ),
        ),
      ],
    );
  }

  static String _money(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }
}
