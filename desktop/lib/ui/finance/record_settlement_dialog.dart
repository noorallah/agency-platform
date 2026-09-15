import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../../models/settlement_direction.dart';
import '../workspace/desktop_framework.dart';

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

  /// The party picker's own text. It holds the chosen party's label once one
  /// is picked, and whatever is being typed before that.
  final TextEditingController _partySearch = TextEditingController();
  final FocusNode _partyFocus = FocusNode();

  String _partyId = '';
  /// The order a deposit came in against, where it came in against one. A
  /// note about why the money arrived, not a ring-fence: cancelling the order
  /// does not make the deposit vanish.
  String _orderId = '';
  List<Json> _orders = const <Json>[];

  /// What tax collected at source this receipt would attract, answered before
  /// the money is taken rather than discovered after.
  Json? _tcs;
  String _method = 'BANK';
  DateTime _date = DateTime.now();
  List<OutstandingInvoice> _invoices = const [];
  bool _busy = false;
  String? _error;

  String get _noun => widget.direction.noun;

  @override
  void initState() {
    super.initState();
    // The helper under the party field reports how many names a query would
    // offer, and `RawAutocomplete` does not rebuild its field view when the
    // text changes -- the `TextFormField` owns that. Without this the helper
    // stays on whatever it said when the dialog opened.
    _partySearch.addListener(_onPartyQueryChanged);
  }

  void _onPartyQueryChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _partySearch.removeListener(_onPartyQueryChanged);
    _amount.dispose();
    _reference.dispose();
    _narration.dispose();
    for (final TextEditingController controller in _allocations.values) {
      controller.dispose();
    }
    _partySearch.dispose();
    _partyFocus.dispose();
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
          // Only where one was named: blank is "no particular order", which
          // is what most receipts are.
          if (_orderId.isNotEmpty) 'sales_order_id': _orderId,
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
          padding: const EdgeInsets.all(AppSpacing.xl),
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
              if (widget.direction == SettlementDirection.receipt) ...[
                const SizedBox(height: AppSpacing.md),
                _orderPicker(),
                _tcsNotice(context),
              ],
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

  /// The customer's live orders, so a deposit can say which one it is for.
  Future<void> _loadOrders(String partyId) async {
    try {
      final Json response = await widget.api.documentPage(
        'sales-orders',
        pageSize: 100,
        additionalQuery: <String, String>{'customer_id': partyId},
      );
      final dynamic data = response['data'];
      if (!mounted || data is! List) return;
      setState(() {
        _orders = data
            .whereType<Map>()
            .map(Map<String, dynamic>.from)
            .where((order) => '${order['customer_id']}' == partyId)
            .where((order) => '${order['status']}' != 'CANCELLED')
            .toList();
      });
    } on ApiException {
      // A picker that could not be filled is left empty rather than blocking
      // the receipt: naming the order is a note, not a requirement.
      if (mounted) setState(() => _orders = const <Json>[]);
    }
  }

  /// Ask what this receipt would attract in tax collected at source.
  ///
  /// Before the money is taken, because the figure is needed when it is asked
  /// for rather than discovered afterwards. Silent where the firm collects
  /// none, which is most firms.
  Future<void> _loadTcs() async {
    final double amount = _amountEntered;
    if (_partyId.isEmpty || amount <= 0) {
      if (mounted) setState(() => _tcs = null);
      return;
    }
    try {
      final Json answer = await widget.api.tcsPreview(
        customerId: _partyId,
        amount: _amount.text.trim(),
        on: _date.toIso8601String().substring(0, 10),
      );
      if (!mounted) return;
      setState(() => _tcs = answer);
    } on ApiException {
      if (mounted) setState(() => _tcs = null);
    }
  }

  /// Which order this money came in against, where it came in against one.
  Widget _orderPicker() => DropdownButtonFormField<String>(
        initialValue: _orderId.isEmpty ? null : _orderId,
        isExpanded: true,
        decoration: const InputDecoration(
          labelText: 'Against order (optional)',
          helperText: 'A note about why the money arrived. Cancelling the '
              'order does not take the deposit back.',
          helperMaxLines: 2,
        ),
        items: [
          const DropdownMenuItem<String>(
            value: '',
            child: Text('No particular order'),
          ),
          for (final Json order in _orders)
            DropdownMenuItem<String>(
              value: '${order['id']}',
              child: Text(
                '${order['order_number']} — ${order['grand_total']}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
        onChanged: (value) => setState(() => _orderId = value ?? ''),
      );

  /// What the buyer will be charged on top, where anything is.
  Widget _tcsNotice(BuildContext context) {
    final Json? answer = _tcs;
    if (answer == null || answer['applicable'] != true) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Text(
        // Owed on top of what is being paid, not taken out of it -- said
        // plainly, because the other reading is the natural one.
        'Tax collected at source: ${answer['tcs_amount']} on '
        '${answer['taxable_amount']} above the threshold, at '
        '${answer['rate_percent']}%. The buyer owes it on top of this '
        'receipt.',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }

  /// Choose the party by typing, not by scrolling.
  ///
  /// This was a plain `DropdownButtonFormField` listing every party the firm
  /// has. A firm with a handful is fine; a distributor with hundreds hands
  /// somebody a scrollbar and asks them to find a name in it, at the till,
  /// with a customer waiting. Reported by the owner at plan step 22.4,
  /// 2026-09-15.
  ///
  /// Filtered here rather than by re-asking the server on every keystroke:
  /// the route caps at 200 and the list is already in hand, so a round trip
  /// per character would be slower and would make the field stutter. The
  /// route's own `search` is there for the firm whose list is longer than the
  /// cap, and is the next step if one appears.
  ///
  /// Matching is on code **and** name, because either is what somebody has in
  /// front of them -- a code off a bill, a name off a cheque.
  Widget _partyPicker() => RawAutocomplete<PartyOption>(
        textEditingController: _partySearch,
        focusNode: _partyFocus,
        displayStringForOption: (party) => party.label,
        optionsBuilder: (TextEditingValue value) {
          final String query = value.text.trim().toLowerCase();
          if (query.isEmpty) return widget.parties;
          return widget.parties.where((party) =>
              party.code.toLowerCase().contains(query) ||
              party.name.toLowerCase().contains(query));
        },
        onSelected: _choosePartyOption,
        fieldViewBuilder: (context, field, node, onFieldSubmitted) =>
            TextFormField(
          controller: field,
          focusNode: node,
          decoration: InputDecoration(
            labelText: switch (widget.direction) {
              SettlementDirection.receipt => 'Received from',
              SettlementDirection.payment => 'Paid to',
              SettlementDirection.refund => 'Refunded to',
            },
            helperText: _partyMatches(field.text) == 0
                ? 'Nobody matches that.'
                : 'Type a code or a name to narrow the list.',
            prefixIcon: const Icon(Icons.search),
            // Clearing the box reopens the whole list, which is the way back
            // from a search that matched nothing.
            suffixIcon: field.text.isEmpty
                ? const Icon(Icons.expand_more)
                : IconButton(
                    icon: const Icon(Icons.close),
                    tooltip: 'Clear',
                    onPressed: () => setState(() {
                      field.clear();
                      _partyId = '';
                    }),
                  ),
          ),
          onTap: () {
            // Tapping a field that already holds a choice should offer the
            // list again rather than making somebody delete the name first.
            if (field.text.isNotEmpty) {
              field.selection = TextSelection(
                baseOffset: 0,
                extentOffset: field.text.length,
              );
            }
          },
        ),
        optionsViewBuilder: (context, onOptionSelected, options) {
          final ThemeData theme = Theme.of(context);
          return Align(
            alignment: Alignment.topLeft,
            child: Material(
              elevation: 4,
              borderRadius: AppRadius.medium,
              color: theme.colorScheme.surfaceContainerLowest,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420, maxHeight: 260),
                // No empty state here: `RawAutocomplete` does not open this
                // view at all when nothing matches, so a message inside it
                // would be unreachable. The field's helper says it instead.
                child: ListView.builder(
                  padding: EdgeInsets.zero,
                  shrinkWrap: true,
                  itemCount: options.length,
                  itemBuilder: (context, index) {
                    final PartyOption party = options.elementAt(index);
                    // One line, `CODE  Name`, as the dropdown showed it. A
                    // two-line row with the code beneath was tried and the
                    // owner preferred this: a list of codes down the left
                    // edge is what you scan, and stacking halves how many
                    // rows fit above the fold.
                    return ListTile(
                      dense: true,
                      title: Text(party.label, overflow: TextOverflow.ellipsis),
                      onTap: () => onOptionSelected(party),
                    );
                  },
                ),
              ),
            ),
          );
        },
      );

  /// How many parties a query would offer. Zero is worth saying out loud.
  int _partyMatches(String text) {
    final String query = text.trim().toLowerCase();
    if (query.isEmpty) return widget.parties.length;
    return widget.parties
        .where((party) =>
            party.code.toLowerCase().contains(query) ||
            party.name.toLowerCase().contains(query))
        .length;
  }

  /// Everything that has to follow from choosing who the money is with.
  void _choosePartyOption(PartyOption party) {
    setState(() {
      _partyId = party.id;
      // The previous customer's orders and tax are not this one's.
      _orderId = '';
      _orders = const <Json>[];
      _tcs = null;
    });
    if (widget.direction.allocates) unawaited(_loadInvoices(party.id));
    // The notice was read only when the amount changed, so a customer chosen
    // after the amount cleared it and nothing brought it back (plan item
    // 9.19, 2026-09-13).
    if (widget.direction == SettlementDirection.receipt) {
      unawaited(_loadTcs());
      unawaited(_loadOrders(party.id));
    }
  }

  Widget _amountField() => TextField(
        controller: _amount,
        decoration: const InputDecoration(labelText: 'Amount'),
        keyboardType: TextInputType.number,
        onChanged: (_) {
          setState(() {});
          if (widget.direction == SettlementDirection.receipt) {
            unawaited(_loadTcs());
          }
        },
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
          if (picked == null) return;
          setState(() => _date = picked);
          // The threshold resets with the financial year, so the date is
          // part of the answer.
          if (widget.direction == SettlementDirection.receipt) {
            unawaited(_loadTcs());
          }
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
