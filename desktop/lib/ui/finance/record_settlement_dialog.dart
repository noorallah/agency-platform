import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../../models/tds.dart';
import '../../models/settlement_direction.dart';
import '../../models/vendor.dart';
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

  /// Tax deducted at source out of the amount (backlog 53.1): on a payment
  /// the firm deducted it, on a receipt the customer did. The amount stays
  /// what settles the party; the bank moves the rest.
  final TextEditingController _tds = TextEditingController();
  String? _tdsSection;

  /// What else comes off the amount before the money moves: a rounding or
  /// short payment, bank charges (receipts only) and a discount allowed or
  /// received. Each settles the party without being cash, like the TDS.
  final TextEditingController _rounding = TextEditingController();
  final TextEditingController _bankCharges = TextEditingController();
  final TextEditingController _discount = TextEditingController();

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
  /// How the money moved (ACC-3); the method follows from it -- cash is
  /// cash, every other mode goes through the bank.
  String _mode = 'BANK_TRANSFER';
  String get _method => _mode == 'CASH' ? 'CASH' : 'BANK';

  /// The cheque's or draft's own date, asked only for those two.
  DateTime? _instrumentDate;
  bool get _hasInstrumentDate =>
      _mode == 'CHEQUE' || _mode == 'DEMAND_DRAFT';
  DateTime _date = DateTime.now();

  /// Section 194Q (ACC-8): the chosen supplier's position this Income-tax
  /// year, asked for when a supplier or date is chosen on a payment. Advice
  /// that prefills the TDS boxes; a typed figure is never overwritten.
  Json? _tds194q;
  bool _tdsTyped = false;
  bool _tdsPrefilled = false;

  /// The section came from the supplier's usual one (ACC-7), not from the
  /// person; it is cleared with the supplier, and 194Q replaces it.
  bool _sectionDefaulted = false;
  String? _tdsNote;
  List<OutstandingInvoice> _invoices = const [];

  /// Bills a receipt on this date may take an early-payment discount on
  /// (SEL-14). Advice shown beside the deductions; the discount box is filled
  /// only when the person presses Apply.
  List<Json> _offers = const <Json>[];

  /// What the chosen supplier owes the firm from returns and debit notes,
  /// not yet set against a bill. Said before the money goes, because paying a bill
  /// in full while a credit stands pays the supplier twice (D-FIN-19).
  List<SupplierCredit> _credits = const [];
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
    _tds.dispose();
    _rounding.dispose();
    _bankCharges.dispose();
    _discount.dispose();
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

  Future<void> _loadCashDiscounts() async {
    if (widget.direction != SettlementDirection.receipt) return;
    final String partyId = _partyId;
    if (partyId.isEmpty) return;
    try {
      final List<Json> rows = await widget.api.cashDiscountOffers(
        customerId: partyId,
        on: _date.toIso8601String().substring(0, 10),
      );
      if (!mounted || _partyId != partyId) return;
      setState(() => _offers = rows);
    } on ApiException {
      // Advice, not a gate: failing to read it must not stop a receipt.
      if (mounted) setState(() => _offers = const <Json>[]);
    }
  }

  /// The offers on bills this receipt is actually applied to.
  List<Json> get _applicableOffers => [
        for (final Json offer in _offers)
          if ((double.tryParse(
                      _allocations['${offer['invoice_id']}']?.text.trim() ??
                          '') ??
                  0) >
              0)
            offer,
      ];

  static const List<String> _months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  static String _dayMonth(String iso) {
    final DateTime? parsed = DateTime.tryParse(iso);
    return parsed == null ? iso : '${parsed.day} ${_months[parsed.month - 1]}';
  }

  /// "Cash discount available: ₹X (2% until 30 Apr)" with an Apply action.
  Widget _cashDiscountNotice(BuildContext context) {
    final List<Json> offers = _applicableOffers;
    if (offers.isEmpty) return const SizedBox.shrink();
    final double total =
        offers.fold(0.0, (sum, offer) => sum + _figure(offer['amount']));
    if (total <= 0) return const SizedBox.shrink();
    final String detail = offers
        .map((offer) => '${_figure(offer['percent']).toString().replaceAll(RegExp(r'\.0$'), '')}% '
            'until ${_dayMonth('${offer['discount_until']}')}')
        .toSet()
        .join(', ');
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Row(
        key: const ValueKey('settlement-cash-discount-offer'),
        children: [
          Expanded(
            child: Text(
              'Cash discount available: ₹${total.toStringAsFixed(2)} '
              '($detail)',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          TextButton(
            key: const ValueKey('settlement-cash-discount-apply'),
            onPressed: () => setState(
              () => _discount.text = total.toStringAsFixed(2),
            ),
            child: const Text('Apply'),
          ),
        ],
      ),
    );
  }

  Future<void> _loadCredits(String partyId) async {
    setState(() => _credits = const []);
    try {
      final List<SupplierCredit> rows =
          await widget.api.supplierCredits(partyId);
      if (!mounted || _partyId != partyId) return;
      setState(() => _credits = rows);
    } on ApiException {
      // The notice is advice, not a gate: failing to read it must not stop a
      // payment being recorded.
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

  Future<void> _loadTds194q() async {
    if (widget.direction != SettlementDirection.payment) return;
    if (!Phase2Scope.of(context)) return;
    final String partyId = _partyId;
    if (partyId.isEmpty) return;
    try {
      final Json answer = await widget.api.tds194qSupplier(
        partyId,
        on: _date.toIso8601String().substring(0, 10),
      );
      if (!mounted || _partyId != partyId) return;
      _tds194q = answer;
      _applyTds194q();
    } on ApiException {
      // Advice, not a gate: failing to read it changes nothing.
    }
  }

  /// Prefill the section from the supplier's usual one. Only into an empty
  /// box, so a section somebody chose is never overwritten, and the 194Q
  /// prefill (which sets the section itself) wins where it applies.
  Future<void> _loadDefaultTdsSection(PartyOption party) async {
    String section = party.defaultTdsSection;
    if (section.isEmpty) {
      // The money screens' party list does not carry it, so read the
      // supplier; a role without the vendor view code simply gets no hint.
      try {
        final PagedResult<Vendor> found = await widget.api.vendors(
          search: party.code.isNotEmpty ? party.code : party.name,
        );
        section = found.items
                .where((vendor) => vendor.id == party.id)
                .firstOrNull
                ?.defaultTdsSection ??
            '';
      } on Exception {
        return;
      }
    }
    if (!mounted || _partyId != party.id || section.isEmpty) return;
    if (_tdsSection != null || _tdsTyped) return;
    if (!tdsSections.containsKey(section)) return;
    setState(() {
      _tdsSection = section;
      _sectionDefaulted = true;
    });
  }

  static double _figure(Object? value) =>
      double.tryParse('${value ?? ''}') ?? 0;

  /// Prefill the TDS boxes from the 194Q position, unless somebody has typed
  /// a deduction. Re-run when the amount changes, since it caps the figure.
  void _applyTds194q() {
    final Json? position = _tds194q;
    if (position == null || _tdsTyped) return;
    final double toDeduct = _figure(position['to_deduct']);
    if (position['applies'] != true || toDeduct <= 0) return;
    final double amount = _amountEntered;
    double deduct = toDeduct;
    if (amount > 0 && deduct >= amount) deduct = amount - 0.01;
    if (deduct <= 0) return;
    setState(() {
      _tds.text = deduct.toStringAsFixed(2);
      _tdsSection = '194Q';
      _sectionDefaulted = false;
      _tdsPrefilled = true;
      _tdsNote = '194Q: ₹${_figure(position['purchases']).toStringAsFixed(2)}'
          ' bought this year, ₹${_figure(position['due']).toStringAsFixed(2)}'
          ' due, ₹${_figure(position['deducted']).toStringAsFixed(2)}'
          ' already deducted';
    });
  }

  double get _amountEntered => double.tryParse(_amount.text.trim()) ?? 0;

  double _value(TextEditingController box) =>
      double.tryParse(box.text.trim()) ?? 0;

  /// Rounding, bank charges and discount together. Bank charges count only
  /// on a receipt, where the box is shown.
  double get _deductionsTotal =>
      _value(_rounding) +
      (widget.direction == SettlementDirection.receipt
          ? _value(_bankCharges)
          : 0) +
      _value(_discount);

  /// Mirrors what the server refuses, so it is said before the save. The
  /// firm's rounding limit is the server's to judge.
  String? _deductionProblem(Map<String, String> allocations) {
    for (final TextEditingController box in [
      _rounding,
      if (widget.direction == SettlementDirection.receipt) _bankCharges,
      _discount,
    ]) {
      final String typed = box.text.trim();
      if (typed.isNotEmpty && (double.tryParse(typed) ?? -1) < 0) {
        return 'A deduction must be a number, 0 or more.';
      }
    }
    final double deductions = _deductionsTotal;
    if (deductions <= 0) return null;
    final double allocated = allocations.values
        .fold(0.0, (sum, value) => sum + (double.tryParse(value) ?? 0));
    if (deductions - allocated > 0.005) {
      return 'Deductions of ${deductions.toStringAsFixed(2)} cannot be more '
          'than the ${allocated.toStringAsFixed(2)} applied to bills.';
    }
    if (_amountEntered - _value(_tds) - deductions <= 0) {
      return 'The deductions and TDS leave no money moved; they must come to '
          'less than the amount.';
    }
    return null;
  }

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
    final String? tdsProblemText = widget.direction.allocates
        ? tdsProblem(
            amount: _amount.text,
            tdsAmount: _tds.text,
            section: _tdsSection,
          )
        : null;
    final String? deductionProblem = widget.direction.allocates
        ? _deductionProblem(allocations)
        : null;
    if (problem != null || tdsProblemText != null || deductionProblem != null) {
      setState(
          () => _error = problem ?? tdsProblemText ?? deductionProblem);
      return;
    }
    final double deducted = double.tryParse(_tds.text.trim()) ?? 0;
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
          'payment_mode': _mode,
          if (_reference.text.trim().isNotEmpty)
            'instrument_reference': _reference.text.trim(),
          if (_hasInstrumentDate && _instrumentDate != null)
            'instrument_date':
                _instrumentDate!.toIso8601String().substring(0, 10),
          if (_narration.text.trim().isNotEmpty)
            'narration': _narration.text.trim(),
          if (widget.direction.allocates && deducted > 0) ...{
            'tds_amount': _tds.text.trim(),
            'tds_section': _tdsSection,
          },
          // Sent only when something was deducted. Bank charges are a
          // receipt's alone: the server refuses them on a payment.
          if (widget.direction.allocates && _value(_rounding) > 0)
            'rounding_amount': _rounding.text.trim(),
          if (widget.direction == SettlementDirection.receipt &&
              _value(_bankCharges) > 0)
            'bank_charges_amount': _bankCharges.text.trim(),
          if (widget.direction.allocates && _value(_discount) > 0)
            'discount_amount': _discount.text.trim(),
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
                    decoration: InputDecoration(
                      labelText: _referenceLabel,
                    ),
                  ),
                ),
                if (_hasInstrumentDate) ...[
                  const SizedBox(width: AppSpacing.md),
                  SizedBox(width: 170, child: _instrumentDateField(context)),
                ],
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    controller: _narration,
                    decoration: const InputDecoration(labelText: 'Narration'),
                  ),
                ),
              ]),
              // A refund hands the customer's own money back; nobody
              // deducts tax from that, and the server refuses it.
              if (widget.direction.allocates) ...[
                const SizedBox(height: AppSpacing.md),
                _tdsRow(context, amount),
                const SizedBox(height: AppSpacing.md),
                _deductionsRow(context, amount),
                if (widget.direction == SettlementDirection.receipt)
                  _cashDiscountNotice(context),
              ],
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
                if (_credits.isNotEmpty) ...[
                  Text(
                    'This supplier owes the firm '
                    '${_credits.fold<double>(0, (sum, c) => sum + c.available).toStringAsFixed(2)} '
                    'in supplier credit '
                    '(${_credits.map((c) => c.label).join(', ')}). '
                    'Set it against a bill with Supplier credits on the '
                    'Payments screen first, and pay only what is left.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                ],
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

  /// TDS deducted, its section, and what the cash or bank actually moves.
  Widget _tdsRow(BuildContext context, double amount) {
    final double deducted = double.tryParse(_tds.text.trim()) ?? 0;
    final bool receipt = widget.direction == SettlementDirection.receipt;
    final String party = receipt ? 'customer' : 'supplier';
    final String account = _method == 'CASH' ? 'cash' : 'bank';
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        width: 160,
        child: TextField(
          key: const ValueKey('settlement-tds-amount'),
          controller: _tds,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => setState(() {
            _tdsTyped = true;
            _tdsPrefilled = false;
            _tdsNote = null;
          }),
          decoration: InputDecoration(
            labelText: 'TDS deducted',
            helperText: _tdsNote ?? (receipt ? 'By the customer' : 'By us'),
            helperMaxLines: 3,
          ),
        ),
      ),
      const SizedBox(width: AppSpacing.md),
      SizedBox(
        width: 280,
        child: DropdownButtonFormField<String>(
          key: const ValueKey('settlement-tds-section'),
          initialValue: _tdsSection,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'TDS section'),
          items: [
            for (final MapEntry<String, String> entry in tdsSections.entries)
              DropdownMenuItem(
                value: entry.key,
                child: Text(
                  '${entry.key} - ${entry.value}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: (value) => setState(() {
            _tdsSection = value;
            _sectionDefaulted = false;
          }),
        ),
      ),
      const SizedBox(width: AppSpacing.md),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.only(top: AppSpacing.md),
          child: Text(
            deducted > 0 && amount > deducted
                ? '${receipt ? 'Received in' : 'Paid from'} $account: '
                    '${(amount - deducted - _deductionsTotal).toStringAsFixed(2)}. The amount '
                    'above is what settles the $party.'
                : 'Leave blank when nothing was deducted.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ),
    ]);
  }

  /// A deduction box that sends nothing while blank.
  Widget _deductionField({
    required Key key,
    required TextEditingController controller,
    required String label,
    String? helper,
  }) =>
      SizedBox(
        width: 190,
        child: TextField(
          key: key,
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(labelText: label, helperText: helper),
        ),
      );

  /// Rounding, bank charges and discount, and the money that actually moves.
  ///
  /// Like the TDS they settle the party without being cash: the amount above
  /// is the bill value, and the bank moves what is left of it. Bank charges
  /// are the bank's cut of money it received, so a payment has no such box.
  Widget _deductionsRow(BuildContext context, double amount) {
    final bool receipt = widget.direction == SettlementDirection.receipt;
    final double moved = amount - _value(_tds) - _deductionsTotal;
    final String account = _method == 'CASH' ? 'cash' : 'bank';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Deductions', style: Theme.of(context).textTheme.titleSmall),
      const SizedBox(height: AppSpacing.sm),
      Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.sm,
        crossAxisAlignment: WrapCrossAlignment.start,
        children: [
          _deductionField(
            key: const ValueKey('settlement-rounding-amount'),
            controller: _rounding,
            label: 'Rounding / short paid',
          ),
          if (receipt)
            _deductionField(
              key: const ValueKey('settlement-bank-charges-amount'),
              controller: _bankCharges,
              label: 'Bank charges',
            ),
          _deductionField(
            key: const ValueKey('settlement-discount-amount'),
            controller: _discount,
            label: receipt ? 'Discount allowed' : 'Discount received',
          ),
        ],
      ),
      const SizedBox(height: AppSpacing.sm),
      Text(
        amount > 0 && _deductionsTotal > 0
            ? '${receipt ? 'Money received' : 'Money paid'} in $account: '
                '${moved.toStringAsFixed(2)}'
            : 'Leave blank when nothing was deducted. The amount above is '
                'what settles the ${receipt ? 'customer' : 'supplier'}.',
        key: const ValueKey('settlement-money-moved'),
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ]);
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
  /// the whole list is already in hand -- every page of it, since the route
  /// stopped capping at 200 (D-SELL-18) -- so a round trip per character
  /// would be slower and would make the field stutter.
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
      _offers = const <Json>[];
      _tcs = null;
      // The previous supplier's 194Q position is not this one's.
      _tds194q = null;
      _tdsNote = null;
      if (_tdsPrefilled) {
        _tds.clear();
        _tdsSection = null;
        _tdsPrefilled = false;
        _sectionDefaulted = false;
      } else if (_sectionDefaulted) {
        _tdsSection = null;
        _sectionDefaulted = false;
      }
    });
    if (widget.direction == SettlementDirection.payment) {
      unawaited(_loadDefaultTdsSection(party));
      unawaited(_loadTds194q());
    }
    if (widget.direction.allocates) unawaited(_loadInvoices(party.id));
    if (widget.direction == SettlementDirection.payment) {
      unawaited(_loadCredits(party.id));
    }
    // The notice was read only when the amount changed, so a customer chosen
    // after the amount cleared it and nothing brought it back (plan item
    // 9.19, 2026-09-13).
    if (widget.direction == SettlementDirection.receipt) {
      unawaited(_loadTcs());
      unawaited(_loadOrders(party.id));
      unawaited(_loadCashDiscounts());
    }
  }

  Widget _amountField() => TextField(
        controller: _amount,
        decoration: const InputDecoration(labelText: 'Amount'),
        keyboardType: TextInputType.number,
        onChanged: (_) {
          setState(() {});
          if (widget.direction == SettlementDirection.receipt) {
            unawaited(_loadCashDiscounts());
            unawaited(_loadTcs());
          } else {
            _applyTds194q();
          }
        },
      );

  Widget _methodPicker() => DropdownButtonFormField<String>(
        key: const ValueKey('settlement-mode'),
        initialValue: _mode,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Mode'),
        items: [
          for (final MapEntry<String, String> mode in paymentModeLabels.entries)
            DropdownMenuItem<String>(value: mode.key, child: Text(mode.value)),
        ],
        onChanged: (value) =>
            setState(() => _mode = value ?? 'BANK_TRANSFER'),
      );

  /// What the reference box asks for, by mode.
  String get _referenceLabel => switch (_mode) {
        'CHEQUE' => 'Cheque number',
        'DEMAND_DRAFT' => 'Draft number',
        'UPI' => 'UPI reference',
        'BANK_TRANSFER' => 'UTR / transfer reference',
        'CARD' => 'Card slip reference',
        'CASH' => 'Receipt or note reference',
        _ => 'Reference',
      };

  Widget _instrumentDateField(BuildContext context) => InkWell(
        key: const ValueKey('settlement-instrument-date'),
        onTap: () async {
          final DateTime? picked = await showDatePicker(
            context: context,
            initialDate: _instrumentDate ?? _date,
            firstDate: DateTime(2000),
            lastDate: DateTime(2100),
          );
          if (picked == null) return;
          setState(() => _instrumentDate = picked);
        },
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: _mode == 'CHEQUE' ? 'Cheque date' : 'Draft date',
          ),
          child: Text(
            _instrumentDate == null
                ? 'Not given'
                : _instrumentDate!.toIso8601String().substring(0, 10),
          ),
        ),
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
          if (widget.direction == SettlementDirection.payment) {
            unawaited(_loadTds194q());
          }
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
              DataCell(Row(mainAxisSize: MainAxisSize.min, children: [
                Text(invoice.invoiceNumber),
                if (invoice.isOpeningBill) ...[
                  const SizedBox(width: 6),
                  const StatusBadge(label: 'Opening'),
                ],
              ])),
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
