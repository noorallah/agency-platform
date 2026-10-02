// Cheque printing (ACC-12): print a bank payment onto the bank's cheque leaf,
// and line the leaf up once per bank with a test print.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/contra_voucher.dart';
import '../../models/settlement.dart';
import 'balance_confirmation.dart' show OpenPdfOverride;
import 'printed_document.dart';
import 'save_in_dialog.dart';

/// Whether a payment can be written as a cheque: a bank payment, recorded as a
/// cheque or before the mode was asked for, and not reversed. The server
/// refuses the rest by name; this only decides whether to offer the command.
bool canPrintCheque(Settlement row) =>
    row.direction == 'PAYMENT' &&
    row.method == 'BANK' &&
    (row.paymentMode.isEmpty || row.paymentMode == 'CHEQUE') &&
    row.status == 'POSTED';

/// The payee box and the print button for one payment.
class ChequePrintDialog extends StatefulWidget {
  const ChequePrintDialog({
    super.key,
    required this.api,
    required this.paymentId,
    required this.number,
    required this.partyName,
    required this.amount,
    this.openPdfOverride,
  });

  final ApiClient api;
  final String paymentId;
  final String number;
  final String partyName;
  final String amount;

  /// Tests inject one, because a widget test cannot open a print dialog.
  final OpenPdfOverride? openPdfOverride;

  @override
  State<ChequePrintDialog> createState() => _ChequePrintDialogState();
}

class _ChequePrintDialogState extends State<ChequePrintDialog>
    with SaveInDialog<ChequePrintDialog> {
  final TextEditingController _payee = TextEditingController();

  @override
  void dispose() {
    _payee.dispose();
    super.dispose();
  }

  Future<void> _print() async {
    final String name = 'Cheque ${widget.number}';
    await saveAndClose<bool>(() async {
      final List<int> pdf = await widget.api.paymentChequePdf(
        widget.paymentId,
        payee: _payee.text.trim().isEmpty ? null : _payee.text.trim(),
      );
      if (!mounted) return false;
      if (widget.openPdfOverride != null) {
        await widget.openPdfOverride!(name, pdf);
      } else {
        await printDocument(context, bytes: pdf, documentName: name);
      }
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final TextStyle? small = Theme.of(context).textTheme.bodySmall;
    return AlertDialog(
      title: Text('Print cheque · ${widget.number}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text(
                'Pay ${widget.partyName}',
                key: const ValueKey<String>('cheque-summary'),
              ),
              const SizedBox(height: AppSpacing.xs),
              Text('Amount ${widget.amount}', style: small),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey<String>('cheque-payee'),
                controller: _payee,
                enabled: !saving,
                maxLength: 120,
                decoration: const InputDecoration(
                  labelText: 'Payee',
                  helperText: "Blank prints the supplier's legal name",
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey<String>('cheque-print'),
          onPressed: saving ? null : _print,
          child: const Text('Print'),
        ),
      ],
    );
  }
}

/// Lines a bank's cheque leaf up: move right, move down, A/c Payee crossing.
class ChequeLayoutDialog extends StatefulWidget {
  const ChequeLayoutDialog({
    super.key,
    required this.api,
    this.openPdfOverride,
  });

  final ApiClient api;

  /// Tests inject one, because a widget test cannot open a print dialog.
  final OpenPdfOverride? openPdfOverride;

  @override
  State<ChequeLayoutDialog> createState() => _ChequeLayoutDialogState();
}

class _ChequeLayoutDialogState extends State<ChequeLayoutDialog>
    with SaveInDialog<ChequeLayoutDialog> {
  final TextEditingController _x = TextEditingController();
  final TextEditingController _y = TextEditingController();
  List<MoneyAccount> _banks = const [];
  String? _accountId;
  ChequeLayout? _saved;
  bool _acPayee = true;
  bool _loadingAccounts = true;
  bool _loadingLayout = false;
  String? _fieldError;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  @override
  void dispose() {
    _x.dispose();
    _y.dispose();
    super.dispose();
  }

  Future<void> _loadAccounts() async {
    try {
      final List<MoneyAccount> all = await widget.api.contraMoneyAccounts();
      if (!mounted) return;
      setState(() {
        _banks = [
          for (final MoneyAccount account in all)
            if (!account.isCash) account,
        ];
        _loadingAccounts = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _loadingAccounts = false;
        saveError = exception.message;
      });
    }
  }

  Future<void> _pick(String? id) async {
    if (id == null) return;
    setState(() {
      _accountId = id;
      _saved = null;
      _loadingLayout = true;
      _fieldError = null;
      _notice = null;
      saveError = null;
    });
    try {
      final ChequeLayout layout = await widget.api.chequeLayout(id);
      if (!mounted || _accountId != id) return;
      setState(() {
        _saved = layout;
        _x.text = layout.offsetXMm;
        _y.text = layout.offsetYMm;
        _acPayee = layout.printAcPayee;
        _loadingLayout = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _loadingLayout = false;
        saveError = exception.message;
      });
    }
  }

  /// One decimal, -30.0 to 30.0, or null.
  static String? _mm(String text) {
    final String value = text.trim();
    if (!RegExp(r'^-?\d{1,2}(\.\d)?$').hasMatch(value)) return null;
    final double parsed = double.parse(value);
    if (parsed < -30 || parsed > 30) return null;
    return parsed.toStringAsFixed(1);
  }

  bool get _dirty {
    final ChequeLayout? saved = _saved;
    if (saved == null) return false;
    return _mm(_x.text) != _mm(saved.offsetXMm) ||
        _mm(_y.text) != _mm(saved.offsetYMm) ||
        _acPayee != saved.printAcPayee;
  }

  /// Saves what is on screen; false when a box is wrong or the server refused.
  Future<bool> _save() async {
    final String? x = _mm(_x.text);
    final String? y = _mm(_y.text);
    if (x == null || y == null) {
      setState(() => _fieldError =
          'Each move must be -30 to 30 mm, with at most one decimal.');
      return false;
    }
    final ChequeLayout saved = await widget.api.saveChequeLayout(
      _accountId!,
      offsetXMm: x,
      offsetYMm: y,
      printAcPayee: _acPayee,
    );
    if (!mounted) return false;
    setState(() {
      _saved = saved;
      _x.text = saved.offsetXMm;
      _y.text = saved.offsetYMm;
      _acPayee = saved.printAcPayee;
    });
    return true;
  }

  Future<void> _run(Future<void> Function() call) async {
    if (saving) return;
    setState(() {
      saving = true;
      saveError = null;
      _fieldError = null;
      _notice = null;
    });
    try {
      await call();
    } on ApiException catch (exception) {
      if (mounted) setState(() => saveError = exception.message);
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _saveOnly() => _run(() async {
        if (await _save() && mounted) {
          setState(() => _notice = 'Layout saved.');
        }
      });

  Future<void> _testPrint() => _run(() async {
        if (_dirty && !await _save()) return;
        final List<int> pdf = await widget.api.chequeTestPdf(_accountId!);
        if (!mounted) return;
        if (widget.openPdfOverride != null) {
          await widget.openPdfOverride!('Cheque test', pdf);
        } else {
          await printDocument(context, bytes: pdf, documentName: 'Cheque test');
        }
      });

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool ready = _accountId != null && _saved != null;
    final String? shown = _fieldError;
    return AlertDialog(
      title: const Text('Cheque layout'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (shown != null)
                Container(
                  key: const ValueKey<String>('cheque-field-error'),
                  margin: const EdgeInsets.only(bottom: AppSpacing.md),
                  padding: const EdgeInsets.all(AppSpacing.md),
                  color: theme.colorScheme.errorContainer,
                  child: Text(
                    shown,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              if (_loadingAccounts || _loadingLayout)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: LinearProgressIndicator(),
                ),
              DropdownButtonFormField<String>(
                key: const ValueKey<String>('cheque-account'),
                initialValue: _accountId,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: 'Bank account',
                  helperText: !_loadingAccounts && _banks.isEmpty
                      ? 'The firm has no bank account yet.'
                      : null,
                ),
                items: [
                  for (final MoneyAccount account in _banks)
                    DropdownMenuItem<String>(
                      value: account.id,
                      child: Text(account.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: saving ? null : _pick,
              ),
              if (ready) ...[
                const SizedBox(height: AppSpacing.md),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _mmBox('cheque-offset-x', _x, 'Move right (mm)')),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(child: _mmBox('cheque-offset-y', _y, 'Move down (mm)')),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'A negative number moves it left or up, from -30 to 30 mm.',
                  style: theme.textTheme.bodySmall,
                ),
                SwitchListTile(
                  key: const ValueKey<String>('cheque-ac-payee'),
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Print A/c Payee crossing'),
                  value: _acPayee,
                  onChanged: saving
                      ? null
                      : (bool value) => setState(() => _acPayee = value),
                ),
                Text(
                  'Test print saves any change first, then prints a sample '
                  'cheque with these positions.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
              if (_notice != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: Text(_notice!, key: const ValueKey<String>('cheque-notice')),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Close')),
        OutlinedButton(
          key: const ValueKey<String>('cheque-test-print'),
          onPressed: saving || !ready ? null : _testPrint,
          child: const Text('Test print'),
        ),
        FilledButton(
          key: const ValueKey<String>('cheque-layout-save'),
          onPressed: saving || !ready ? null : _saveOnly,
          child: const Text('Save'),
        ),
      ],
    );
  }

  Widget _mmBox(String key, TextEditingController controller, String label) =>
      TextField(
        key: ValueKey<String>(key),
        controller: controller,
        enabled: !saving,
        keyboardType: const TextInputType.numberWithOptions(
          decimal: true,
          signed: true,
        ),
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[-0-9.]'))],
        onChanged: (_) => setState(() {}),
        decoration: InputDecoration(labelText: label),
      );
}
