import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../workspace/desktop_framework.dart';

/// A customer or vendor, reduced to what this dialog needs.
class PartyOption {
  const PartyOption({required this.id, required this.code, required this.name});

  final String id;
  final String code;
  final String name;

  String get label => '$code  $name';
}

/// Validate what is about to be sent, in the words a cashier would use.
///
/// The server refuses all of this too, and has to: the client is not the
/// authority on anybody's books. Doing it here as well is about not making
/// somebody re-key a cheque to find out they typed a digit twice.
String? validateSettlement({
  required String partyId,
  required String amount,
  required Map<String, String> allocations,
  required List<OutstandingInvoice> invoices,
}) {
  if (partyId.isEmpty) return 'Choose who the money is from or to.';
  final double total = double.tryParse(amount.trim()) ?? -1;
  if (total <= 0) return 'Enter how much money moved.';
  double allocated = 0;
  final Map<String, double> outstanding = {
    for (final OutstandingInvoice invoice in invoices)
      invoice.invoiceId: invoice.outstanding,
  };
  for (final MapEntry<String, String> entry in allocations.entries) {
    final double value = double.tryParse(entry.value.trim()) ?? 0;
    if (value <= 0) continue;
    final double owed = outstanding[entry.key] ?? 0;
    if (value - owed > 0.005) {
      final String number = invoices
          .firstWhere((invoice) => invoice.invoiceId == entry.key)
          .invoiceNumber;
      return 'Invoice $number owes ${owed.toStringAsFixed(2)}, so '
          '${value.toStringAsFixed(2)} cannot be applied to it.';
    }
    allocated += value;
  }
  if (allocated - total > 0.005) {
    return 'Applied ${allocated.toStringAsFixed(2)} across invoices, which is '
        'more than the ${total.toStringAsFixed(2)} that moved.';
  }
  return null;
}

/// Record money that has already moved, and say what it settles.
class RecordSettlementDialog extends StatefulWidget {
  const RecordSettlementDialog({
    super.key,
    required this.api,
    required this.direction,
    required this.parties,
  });

  final ApiClient api;
  final SettlementDirection direction;
  final List<PartyOption> parties;

  @override
  State<RecordSettlementDialog> createState() => _RecordSettlementDialogState();
}

class _RecordSettlementDialogState extends State<RecordSettlementDialog> {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _narration = TextEditingController();
  final Map<String, TextEditingController> _allocations = {};

  String _partyId = '';
  String _method = 'BANK';
  DateTime _date = DateTime.now();
  List<OutstandingInvoice> _invoices = const [];
  bool _busy = false;
  String? _error;

  String get _noun => widget.direction.noun;

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    _narration.dispose();
    for (final TextEditingController controller in _allocations.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadInvoices(String partyId) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final List<OutstandingInvoice> rows = await widget.api.outstandingInvoices(
        direction: widget.direction,
        partyId: partyId,
      );
      if (!mounted) return;
      for (final TextEditingController controller in _allocations.values) {
        controller.dispose();
      }
      _allocations.clear();
      setState(() {
        _invoices = rows;
        for (final OutstandingInvoice invoice in rows) {
          _allocations[invoice.invoiceId] = TextEditingController();
        }
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Spread the amount over the oldest invoices, the way it is done by hand.
  void _autoAllocate() {
    final Map<String, String> spread =
        allocateOldestFirst(_invoices, _amount.text.trim());
    setState(() {
      for (final MapEntry<String, TextEditingController> entry
          in _allocations.entries) {
        entry.value.text = spread[entry.key] ?? '';
      }
    });
  }

  double get _amountEntered => double.tryParse(_amount.text.trim()) ?? 0;

  double get _allocatedTotal => _allocations.values.fold(
        0,
        (sum, controller) => sum + (double.tryParse(controller.text.trim()) ?? 0),
      );

  Future<void> _save() async {
    final Map<String, String> allocations = {
      for (final MapEntry<String, TextEditingController> entry
          in _allocations.entries)
        if (entry.value.text.trim().isNotEmpty) entry.key: entry.value.text.trim(),
    };
    final String? problem = validateSettlement(
      partyId: _partyId,
      amount: _amount.text,
      allocations: allocations,
      invoices: _invoices,
    );
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final Settlement saved = await widget.api.recordSettlement(
        direction: widget.direction,
        data: <String, dynamic>{
          'party_id': _partyId,
          'settlement_date':
              _date.toIso8601String().substring(0, 10),
          'amount': _amount.text.trim(),
          'method': _method,
          if (_reference.text.trim().isNotEmpty)
            'instrument_reference': _reference.text.trim(),
          if (_narration.text.trim().isNotEmpty)
            'narration': _narration.text.trim(),
          'allocations': [
            for (final MapEntry<String, String> entry in allocations.entries)
              {'invoice_id': entry.key, 'amount': entry.value},
          ],
        },
      );
      if (!mounted) return;
      Navigator.of(context).pop(saved);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final double amount = double.tryParse(_amount.text.trim()) ?? 0;
    final double unapplied = amount - _allocatedTotal;
    return WorkspaceDialog(
      title: 'Record a ${widget.direction.noun}',
      subtitle: switch (widget.direction) {
        SettlementDirection.receipt =>
          'Money already received. Recording it posts to the ledger.',
        SettlementDirection.payment =>
          'Money already paid. Recording it posts to the ledger.',
        SettlementDirection.refund =>
          'Money already handed back. It reduces what the customer paid '
              'in advance, and posts to the ledger.',
      },
      loading: _busy,
      onClose: _busy ? null : () => Navigator.of(context).pop(),
      onSave: _busy ? null : () => unawaited(_save()),
      saveLabel: 'Record ${widget.direction.noun}',
      body: LoadingOverlay(
        loading: _busy,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: MaterialBanner(
                    content: Text(_error!),
                    actions: [
                      TextButton(
                        onPressed: () => setState(() => _error = null),
                        child: const Text('Dismiss'),
                      ),
                    ],
                  ),
                ),
              Row(children: [
                Expanded(child: _partyPicker()),
                const SizedBox(width: AppSpacing.md),
                SizedBox(width: 160, child: _amountField()),
                const SizedBox(width: AppSpacing.md),
                SizedBox(width: 150, child: _methodPicker()),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                SizedBox(width: 200, child: _dateField(context)),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 220,
                  child: TextField(
                    controller: _reference,
                    decoration: const InputDecoration(
                      labelText: 'Cheque or transfer reference',
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    controller: _narration,
                    decoration: const InputDecoration(labelText: 'Narration'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.lg),
              // A refund returns money held on account, which is the
              // opposite of settling a document -- so there is nothing
              // to apply it to, and the server refuses it if asked.
              if (widget.direction.allocates) ...[
                _allocationHeader(context, unapplied),
                const SizedBox(height: AppSpacing.sm),
                _invoiceTable(context),
              ] else
                Text(
                  'A refund returns money the customer paid in advance. '
                  'It is not applied to an invoice, and cannot be more '
                  'than the advance they are holding.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _partyPicker() => DropdownButtonFormField<String>(
        initialValue: _partyId.isEmpty ? null : _partyId,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: switch (widget.direction) {
            SettlementDirection.receipt => 'Received from',
            SettlementDirection.payment => 'Paid to',
            SettlementDirection.refund => 'Refunded to',
          },
        ),
        items: [
          for (final PartyOption party in widget.parties)
            DropdownMenuItem<String>(
              value: party.id,
              child: Text(party.label, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: (value) {
          if (value == null) return;
          setState(() => _partyId = value);
          if (widget.direction.allocates) unawaited(_loadInvoices(value));
        },
      );

  Widget _amountField() => TextField(
        controller: _amount,
        decoration: const InputDecoration(labelText: 'Amount'),
        keyboardType: TextInputType.number,
        onChanged: (_) => setState(() {}),
      );

  Widget _methodPicker() => DropdownButtonFormField<String>(
        initialValue: _method,
        decoration: const InputDecoration(labelText: 'Method'),
        items: const [
          DropdownMenuItem<String>(value: 'BANK', child: Text('Bank')),
          DropdownMenuItem<String>(value: 'CASH', child: Text('Cash')),
        ],
        onChanged: (value) => setState(() => _method = value ?? 'BANK'),
      );

  Widget _dateField(BuildContext context) => InkWell(
        onTap: () async {
          final DateTime? picked = await showDatePicker(
            context: context,
            initialDate: _date,
            firstDate: DateTime(2000),
            lastDate: DateTime(2100),
          );
          if (picked != null) setState(() => _date = picked);
        },
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: 'Date the money moved',
            suffixIcon: const Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(_date.toIso8601String().substring(0, 10)),
        ),
      );

  Widget _allocationHeader(BuildContext context, double unapplied) => Row(
        children: [
          Text(
            widget.direction.isCustomer ? 'Apply to invoices' : 'Apply to bills',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          const SizedBox(width: AppSpacing.md),
          if (_invoices.isNotEmpty)
            TextButton.icon(
              onPressed: _autoAllocate,
              icon: const Icon(Icons.playlist_add_check, size: 18),
              label: const Text('Oldest first'),
            ),
          const Spacer(),
          // The running figure, because finding out on save that 40 paise are
          // unaccounted for is finding out too late. With no amount entered
          // there is nothing to say -- "all of it applied" over an empty
          // amount box reads as a tick against a form nobody has filled in.
          Text(
            _amountEntered <= 0
                ? 'Enter the amount to apply it'
                : unapplied.abs() < 0.005
                    ? 'All of it applied'
                    : unapplied > 0
                        ? '${unapplied.toStringAsFixed(2)} left on account'
                        : '${(-unapplied).toStringAsFixed(2)} more applied than '
                            'was $_noun',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ],
      );

  Widget _invoiceTable(BuildContext context) {
    if (_partyId.isEmpty) {
      return Text(
        widget.direction.isCustomer
            ? 'Choose a customer to see what they owe.'
            : 'Choose a vendor to see what the firm owes them.',
        style: Theme.of(context).textTheme.bodySmall,
      );
    }
    if (_invoices.isEmpty) {
      // Not an error. Money can arrive before an invoice does, and it is
      // recorded on account.
      return Text(
        widget.direction.isCustomer
            ? 'Nothing is outstanding for this customer. The whole amount will '
                'be held on account.'
            : 'Nothing is outstanding for this vendor. The whole amount will '
                'be held on account.',
        style: Theme.of(context).textTheme.bodySmall,
      );
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Invoice')),
          DataColumn(label: Text('Date')),
          DataColumn(label: Text('Total'), numeric: true),
          DataColumn(label: Text('Outstanding'), numeric: true),
          DataColumn(label: Text('Apply'), numeric: true),
        ],
        rows: [
          for (final OutstandingInvoice invoice in _invoices)
            DataRow(cells: [
              DataCell(Text(invoice.invoiceNumber)),
              DataCell(Text(invoice.invoiceDate)),
              DataCell(Text(invoice.invoiceTotal)),
              DataCell(Text(invoice.outstandingAmount)),
              DataCell(
                SizedBox(
                  width: 120,
                  child: TextField(
                    controller: _allocations[invoice.invoiceId],
                    textAlign: TextAlign.right,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(isDense: true),
                    onChanged: (_) => setState(() {}),
                  ),
                ),
              ),
            ]),
        ],
      ),
    );
  }
}
