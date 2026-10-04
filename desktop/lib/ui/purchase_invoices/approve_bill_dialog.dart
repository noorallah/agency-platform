import 'package:flutter/material.dart';

import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/settlement.dart';
import '../workspace/save_in_dialog.dart';

/// Approve a supplier bill, and pay it in the same step when it was a cash
/// purchase (PG-3, backlog 86 #19).
///
/// Offered only to somebody holding `PAYMENT_CREATE`, because the server
/// refuses the payment block without it and approves nothing. The dialog runs
/// the approval itself ([SaveInDialog]): a refusal -- an overpayment, a
/// missing permission -- stays on screen with the server's words and
/// everything typed, and the server has rolled the bill back too.
///
/// With "Paid now" unticked the call carries no payment block, which is
/// exactly the approval there was before. A blank amount means the whole bill
/// and a blank date means the bill's own date; neither is ever prefilled.
class ApproveBillDialog extends StatefulWidget {
  const ApproveBillDialog({
    super.key,
    required this.number,
    required this.onApprove,
    this.canPay = true,
    this.loadProposal,
  });

  final String number;

  /// Whether the "Paid now" section is offered (it needs `PAYMENT_CREATE`).
  final bool canPay;

  /// Reads the TDS the server would deduct on this bill (PG-5). Advice, not
  /// a gate: null, or a failure, simply shows no proposal.
  final Future<Json?> Function()? loadProposal;

  /// Approves the bill, with a body carrying `payment` when it is paid now.
  final Future<Json> Function(Json? body) onApprove;

  @override
  State<ApproveBillDialog> createState() => _ApproveBillDialogState();
}

class _ApproveBillDialogState extends State<ApproveBillDialog>
    with SaveInDialog<ApproveBillDialog> {
  bool _paidNow = false;
  String _method = 'CASH';
  String _mode = 'CASH';
  DateTime? _date;
  DateTime? _instrumentDate;
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _tds = TextEditingController();
  Json? _proposal;
  String? _tdsError;

  @override
  void initState() {
    super.initState();
    _readProposal();
  }

  Future<void> _readProposal() async {
    final Future<Json?> Function()? load = widget.loadProposal;
    if (load == null) return;
    try {
      final Json? found = await load();
      if (mounted && found != null) setState(() => _proposal = found);
    } on Exception {
      // Advice only: the approval stands without it.
    }
  }

  static double _figure(Object? value) =>
      double.tryParse('${value ?? ''}') ?? 0;

  /// What the proposal says, or null when no section applies to the bill.
  Widget? _proposalBlock(BuildContext context) {
    final Json? p = _proposal;
    if (p == null) return null;
    final String section = '${p['section'] ?? ''}';
    if (section.isEmpty || section == 'null') return null;
    final ThemeData theme = Theme.of(context);
    final String rate = '${p['rate_percent'] ?? ''}';
    final String basis = '${p['rate_basis'] ?? ''}';
    final bool applies = p['applies'] == true;
    final String lines = [
      'TDS $section at $rate%${basis.isEmpty ? '' : ' ($basis)'}',
      if (p['threshold_crossed'] != null)
        p['threshold_crossed'] == true
            ? 'Threshold crossed.'
            : 'Threshold not yet crossed.',
      'Due so far: ₹${_figure(p['due']).toStringAsFixed(2)}, already '
          'deducted: ₹${_figure(p['deducted']).toStringAsFixed(2)}.',
      applies
          ? 'Proposed on this bill: '
              '₹${_figure(p['proposed']).toStringAsFixed(2)}.'
          : 'Nothing is proposed on this bill.',
    ].join('\n');
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Text(
        lines,
        key: const ValueKey('approve-tds-proposal'),
        style: theme.textTheme.bodySmall,
      ),
    );
  }

  List<Widget> _tdsFields(BuildContext context) {
    final Widget? block = _proposalBlock(context);
    if (block == null) return const <Widget>[];
    final Json p = _proposal!;
    return [
      block,
      const SizedBox(height: AppSpacing.sm),
      TextField(
        key: const ValueKey('approve-tds-amount'),
        controller: _tds,
        enabled: !saving,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(
          labelText: 'TDS to deduct',
          errorText: _tdsError,
          helperText: 'Blank takes the proposal '
              '(₹${_figure(p['proposed']).toStringAsFixed(2)}); '
              '0 deducts nothing.',
          helperMaxLines: 2,
        ),
        onChanged: (_) => setState(() => _tdsError = null),
      ),
    ];
  }

  @override
  void dispose() {
    _tds.dispose();
    _amount.dispose();
    _reference.dispose();
    super.dispose();
  }

  bool get _isInstrument => _mode == 'CHEQUE' || _mode == 'DEMAND_DRAFT';

  String _iso(DateTime day) => day.toIso8601String().substring(0, 10);

  String? _blankAsNull(String text) =>
      text.trim().isEmpty ? null : text.trim();

  /// The typed TDS override, or null when the box is blank.
  String? get _typedTds => _blankAsNull(_tds.text);

  Json? _body() {
    final Json body = <String, dynamic>{};
    if (_typedTds != null) body['tds_amount'] = _typedTds;
    if (_paidNow) {
      body['payment'] = <String, dynamic>{
        'method': _method,
        'payment_mode': _mode,
        'amount': _blankAsNull(_amount.text),
        'payment_date': _date == null ? null : _iso(_date!),
        'instrument_reference': _blankAsNull(_reference.text),
        'instrument_date': _isInstrument && _instrumentDate != null
            ? _iso(_instrumentDate!)
            : null,
      };
    }
    return body.isEmpty ? null : body;
  }

  Future<void> _approve() {
    final String? typed = _typedTds;
    if (typed != null) {
      final double? value = double.tryParse(typed);
      if (value == null || value < 0) {
        setState(() => _tdsError = 'A number, 0 or more.');
        return Future<void>.value();
      }
    }
    return saveAndClose<Json>(() => widget.onApprove(_body()));
  }

  Widget _dateBox(
    String label,
    DateTime? value,
    String blankText,
    ValueChanged<DateTime> onPicked, {
    Key? key,
  }) =>
      InkWell(
        key: key,
        onTap: saving
            ? null
            : () async {
                final DateTime? picked = await showDatePicker(
                  context: context,
                  initialDate: value ?? DateTime.now(),
                  firstDate: DateTime(2000),
                  lastDate: DateTime(2100),
                );
                if (picked != null) setState(() => onPicked(picked));
              },
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            suffixIcon: const Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(value == null ? blankText : _iso(value)),
        ),
      );

  List<Widget> _paymentFields() => [
        const SizedBox(height: AppSpacing.sm),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                key: const ValueKey('paid-now-method'),
                initialValue: _method,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Method'),
                items: const [
                  DropdownMenuItem(value: 'CASH', child: Text('Cash')),
                  DropdownMenuItem(value: 'BANK', child: Text('Bank')),
                ],
                onChanged: saving
                    ? null
                    : (value) => setState(() {
                          _method = value ?? 'CASH';
                          _mode = _method == 'CASH' ? 'CASH' : 'BANK_TRANSFER';
                        }),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: DropdownButtonFormField<String>(
                key: ValueKey<String>('paid-now-mode-$_method'),
                initialValue: _mode,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Mode'),
                items: [
                  for (final MapEntry<String, String> mode
                      in paymentModeLabels.entries)
                    if ((mode.key == 'CASH') == (_method == 'CASH'))
                      DropdownMenuItem<String>(
                        value: mode.key,
                        child: Text(mode.value),
                      ),
                ],
                onChanged: saving
                    ? null
                    : (value) => setState(() => _mode = value ?? _mode),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        TextField(
          key: const ValueKey('paid-now-amount'),
          controller: _amount,
          enabled: !saving,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            labelText: 'Amount',
            helperText: 'Blank pays the full bill.',
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        TextField(
          key: const ValueKey('paid-now-reference'),
          controller: _reference,
          enabled: !saving,
          decoration: const InputDecoration(labelText: 'Reference'),
        ),
        const SizedBox(height: AppSpacing.sm),
        _dateBox(
          'Date paid',
          _date,
          'Blank takes the bill date',
          (day) => _date = day,
          key: const ValueKey('paid-now-date'),
        ),
        if (_isInstrument) ...[
          const SizedBox(height: AppSpacing.sm),
          _dateBox(
            _mode == 'CHEQUE' ? 'Cheque date' : 'Draft date',
            _instrumentDate,
            'Not given',
            (day) => _instrumentDate = day,
          ),
        ],
      ];

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Approve ${widget.number}'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                Text(
                  'Approving posts the bill to the books.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                ..._tdsFields(context),
                if (widget.canPay)
                  CheckboxListTile(
                  key: const ValueKey('paid-now'),
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: const Text('Paid now'),
                  subtitle: const Text(
                    'A cash purchase: record the payment in the same step.',
                  ),
                  value: _paidNow,
                  onChanged: saving
                      ? null
                      : (value) => setState(() => _paidNow = value ?? false),
                ),
                if (widget.canPay && _paidNow) ..._paymentFields(),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey('approve-bill-confirm'),
            onPressed: saving ? null : _approve,
            child: Text(
              widget.canPay && _paidNow ? 'Approve and pay' : 'Approve',
            ),
          ),
        ],
      );
}
