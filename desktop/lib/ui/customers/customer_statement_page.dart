// What a customer's account did over a period, and what of it is overdue.
//
// Two questions with different shapes, so two views rather than one screen
// trying to be both. A **statement** is a movement — what the account stood at,
// everything that happened to it in date order, what it stands at now. An
// **ageing** is a position — which bills are still unpaid, and for how long.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// Which of the two questions is on screen.
enum _View { statement, ageing }

/// Show one customer's account, and the firm's receivables ageing.
class CustomerStatementPage extends StatefulWidget {
  const CustomerStatementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CustomerStatementPage> createState() => _CustomerStatementPageState();
}

class _CustomerStatementPageState extends State<CustomerStatementPage> {
  late final TextEditingController _from =
      TextEditingController(text: _isoMonthsAgo(3));
  late final TextEditingController _to = TextEditingController(text: _isoToday());

  _View _view = _View.ageing;
  List<Json> _ageing = const [];
  Json? _statement;
  String? _selectedCustomerId;
  String? _error;
  bool _loading = false;

  bool get _mayView => widget.permissions.hasPermission('CUSTOMER_VIEW');

  static String _isoToday() => _iso(DateTime.now());

  static String _isoMonthsAgo(int months) {
    final DateTime now = DateTime.now();
    return _iso(DateTime(now.year, now.month - months, now.day));
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _loadAgeing();
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _loadAgeing() async {
    setState(() {
      _loading = true;
      _error = null;
      _ageing = const [];
    });
    try {
      final List<Json> rows = await widget.api.customerAgeing();
      if (!mounted) return;
      setState(() {
        _ageing = rows;
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

  Future<void> _loadStatement(String customerId) async {
    setState(() {
      _loading = true;
      _error = null;
      // Dropped on the way in. A refusal is reported in place of the
      // account below, so this is belt and braces rather than the thing that
      // stops one customer's figures appearing under another's name.
      _statement = null;
      _selectedCustomerId = customerId;
      _view = _View.statement;
    });
    try {
      final Json answer = await widget.api.customerStatement(
        customerId,
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
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
        message: 'Reading what customers owe needs the view customers '
            'permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          OutlinedButton.icon(
            onPressed: _view == _View.ageing
                ? _loadAgeing
                : () {
                    final String? id = _selectedCustomerId;
                    if (id != null) _loadStatement(id);
                  },
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: _periodPanel(),
      viewBar: SegmentedButton<_View>(
        segments: const [
          ButtonSegment(value: _View.ageing, label: Text('Ageing')),
          ButtonSegment(value: _View.statement, label: Text('Statement')),
        ],
        selected: {_view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) {
          setState(() => _view = selection.first);
          if (_view == _View.ageing && _ageing.isEmpty) _loadAgeing();
        },
      ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _view == _View.ageing ? _ageing.length : _lines().length,
        selected: false,
        message: _view == _View.ageing
            ? 'What each bill still owes, off the receipts against it.'
            : 'Balances recomputed in date order.',
      ),
    );
  }

  Widget _periodPanel() => Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _from,
                decoration: const InputDecoration(labelText: 'From'),
              ),
            ),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: TextField(
                controller: _to,
                decoration: const InputDecoration(labelText: 'To'),
              ),
            ),
          ],
        ),
      );

  List<dynamic> _lines() =>
      _statement?['lines'] as List<dynamic>? ?? const <dynamic>[];

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'Nothing could be read',
        message: _error!,
      );
    }
    return _view == _View.ageing ? _ageingView() : _statementView();
  }

  Widget _ageingView() {
    if (_ageing.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing outstanding',
        message: 'Every approved bill has been settled in full.',
      );
    }
    return ListView.builder(
      itemCount: _ageing.length,
      itemBuilder: (context, index) {
        final Json row = _ageing[index];
        final List<dynamic> buckets =
            row['buckets'] as List<dynamic>? ?? const [];
        return Card(
          margin: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.xs,
          ),
          child: ListTile(
            title: Text(
              '${stringValue(row['customer_name'])}  '
              '(${stringValue(row['customer_code'])})',
            ),
            subtitle: Text(
              // Every band, including the empty ones, so the row reads the
              // same shape every time and the eye can compare down a column.
              buckets.map((bucket) {
                final Map cell = bucket as Map;
                final Object? upper = cell['to_days'];
                final String band = upper == null
                    ? '${cell['from_days']}+'
                    : '${cell['from_days']}-$upper';
                return '$band: ${_money(cell['amount'])}';
              }).join('   •   '),
            ),
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  _money(row['total_outstanding']),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                // The bills and the account are not the same number, and a
                // row that showed only the first would disagree with the
                // customer's own balance with nothing to explain the gap.
                if (_gap(row).isNotEmpty)
                  Text(
                    _gap(row),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
              ],
            ),
            onTap: () => _loadStatement(stringValue(row['customer_id'])),
          ),
        );
      },
    );
  }

  Widget _statementView() {
    final Json? statement = _statement;
    if (statement == null) {
      return const WorkspaceEmptyState(
        title: 'Choose a customer',
        message: 'Pick one from the ageing to read their account.',
      );
    }
    final List<dynamic> lines = _lines();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Text(
            '${stringValue(statement['customer_name'])}  •  opened at '
            '${_money(statement['opening_balance'])}, closed at '
            '${_money(statement['closing_balance'])}'
            // Beside the balance rather than folded into it: netting them
            // hides an advance the customer can have applied.
            '${_advanceNote(statement)}',
            style: Theme.of(context).textTheme.titleSmall,
          ),
        ),
        Expanded(
          child: lines.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'Nothing moved',
                  message: 'The account had no activity in this period.',
                )
              : SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SingleChildScrollView(
                    child: DataTable(
                      columns: const [
                        DataColumn(label: Text('Date')),
                        DataColumn(label: Text('Type')),
                        DataColumn(label: Text('Reference')),
                        DataColumn(label: Text('Debit')),
                        DataColumn(label: Text('Credit')),
                        DataColumn(label: Text('Balance')),
                      ],
                      rows: [
                        for (final dynamic line in lines)
                          DataRow(cells: [
                            DataCell(Text(stringValue((line as Map)['transaction_date']))),
                            DataCell(Text(stringValue(line['transaction_type']))),
                            DataCell(Text(stringValue(line['reference_number']))),
                            DataCell(Text(_money(line['debit']))),
                            DataCell(Text(_money(line['credit']))),
                            DataCell(Text(_money(line['balance']))),
                          ]),
                      ],
                    ),
                  ),
                ),
        ),
      ],
    );
  }

  /// Say how the unpaid bills differ from the account, when they do.
  ///
  /// A credit note or a sales return reduces the account and sits on no
  /// invoice; tax collected at source raises it without being billed. Left
  /// unsaid, the two reports simply disagree.
  static String _gap(Json row) {
    final double credits =
        double.tryParse('${row['unapplied_credits'] ?? 0}') ?? 0;
    final double charges =
        double.tryParse('${row['charges_not_billed'] ?? 0}') ?? 0;
    final double balance =
        double.tryParse('${row['account_balance'] ?? 0}') ?? 0;
    if (credits > 0) {
      return 'less ${credits.toStringAsFixed(2)} credit '
          '= ${balance.toStringAsFixed(2)}';
    }
    if (charges > 0) {
      return 'plus ${charges.toStringAsFixed(2)} unbilled '
          '= ${balance.toStringAsFixed(2)}';
    }
    return '';
  }

  static String _advanceNote(Json statement) {
    final double advance =
        double.tryParse('${statement['unapplied_advance'] ?? 0}') ?? 0;
    return advance <= 0
        ? ''
        : '  •  ${advance.toStringAsFixed(2)} held on account';
  }

  static String _money(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }
}
