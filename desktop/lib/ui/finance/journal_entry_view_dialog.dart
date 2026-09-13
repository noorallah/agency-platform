import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';

/// One journal entry's lines: which account, debit, credit, and why.
///
/// The Journal Entries screen listed a reference, a date, a description and
/// a total, and nothing else -- so "does approving an invoice debit
/// receivables and credit sales?" could not be answered from the product at
/// all (plan item 10.9, 2026-09-13). Accounts are named by code and name,
/// read from the chart when the dialog opens; a line whose account is not in
/// the chart shows its id rather than nothing.
class JournalEntryViewDialog extends StatefulWidget {
  const JournalEntryViewDialog({
    super.key,
    required this.api,
    required this.entry,
  });

  final ApiClient api;
  final JournalEntry entry;

  static Future<void> show(
    BuildContext context, {
    required ApiClient api,
    required JournalEntry entry,
  }) =>
      showDialog<void>(
        context: context,
        builder: (_) => JournalEntryViewDialog(api: api, entry: entry),
      );

  @override
  State<JournalEntryViewDialog> createState() => _JournalEntryViewDialogState();
}

class _JournalEntryViewDialogState extends State<JournalEntryViewDialog> {
  Map<String, String> _accountNames = const <String, String>{};

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  Future<void> _loadAccounts() async {
    try {
      final PagedResult<LedgerAccount> accounts =
          await widget.api.ledgerAccounts();
      if (!mounted) return;
      setState(() {
        _accountNames = <String, String>{
          for (final LedgerAccount account in accounts.items)
            account.id: '${account.code} ${account.name}',
        };
      });
    } on ApiException {
      // The ids stay readable; a missing name is not a reason to hide lines.
    }
  }

  String _account(String id) => _accountNames[id] ?? id;

  String _money(String value) {
    final double amount = double.tryParse(value) ?? 0;
    return amount == 0 ? '' : amount.toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) {
    final JournalEntry entry = widget.entry;
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('${entry.referenceNumber}  ·  ${entry.journalDate}'),
      content: SizedBox(
        width: 760,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                [
                  entry.status,
                  if (entry.sourceModule.isNotEmpty)
                    'posted by ${entry.sourceModule}',
                  if (entry.description.isNotEmpty) entry.description,
                ].join('  ·  '),
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  columns: const [
                    DataColumn(label: Text('Account')),
                    DataColumn(label: Text('Debit'), numeric: true),
                    DataColumn(label: Text('Credit'), numeric: true),
                    DataColumn(label: Text('Narration')),
                  ],
                  rows: [
                    for (final JournalLine line in entry.lines)
                      DataRow(cells: [
                        DataCell(Text(_account(line.ledgerAccountId))),
                        DataCell(Text(_money(line.debitAmount))),
                        DataCell(Text(_money(line.creditAmount))),
                        DataCell(Text(line.description)),
                      ]),
                    DataRow(cells: [
                      DataCell(Text('Total', style: theme.textTheme.titleSmall)),
                      DataCell(Text(_money(entry.totalDebit),
                          style: theme.textTheme.titleSmall)),
                      DataCell(Text(_money(entry.totalCredit),
                          style: theme.textTheme.titleSmall)),
                      const DataCell(Text('')),
                    ]),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
