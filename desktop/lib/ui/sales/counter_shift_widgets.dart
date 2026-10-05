// What the counter bill shows around holding a bill and the shift (backlog 87
// #7, SG-7): the strip above the lines, the dialogs that open and close a
// till, the list of held bills to recall, and the note asked when a bill is
// parked. The editor owns when each is shown; nothing here writes a bill.

import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

String _money(dynamic value) {
  final double? parsed = double.tryParse(stringValue(value));
  return parsed == null ? stringValue(value) : parsed.toStringAsFixed(2);
}

String _two(int value) => value.toString().padLeft(2, '0');

/// A stored timestamp as the cashier's own clock reads it: `2026-10-05 09:15`.
String shiftStamp(dynamic value) {
  final DateTime? parsed = DateTime.tryParse(stringValue(value))?.toLocal();
  if (parsed == null) return stringValue(value);
  return '${parsed.year}-${_two(parsed.month)}-${_two(parsed.day)} '
      '${_two(parsed.hour)}:${_two(parsed.minute)}';
}

Json _summaryOf(Json shift) {
  final dynamic summary = shift['summary'];
  return summary is Map ? Map<String, dynamic>.from(summary) : <String, dynamic>{};
}

/// What a difference reads as: negative is short, positive is over.
String differenceLabel(double difference) {
  if (difference.abs() < 0.005) return 'Cash is exact';
  final String amount = difference.abs().toStringAsFixed(2);
  return difference < 0 ? 'Short by $amount' : 'Over by $amount';
}

/// Save the shift's PDF report where the cashier says. Tests inject
/// [saveBytesOverride], because a widget test cannot open a save panel.
Future<void> saveShiftReport(
  ApiClient api,
  String shiftId,
  String shiftNumber, {
  SaveBytesOverride? saveBytesOverride,
}) async {
  final List<int> pdf = await api.counterShiftReportPdf(shiftId);
  final String name =
      'Shift ${shiftNumber.isEmpty ? 'report' : shiftNumber}.pdf';
  if (saveBytesOverride != null) {
    await saveBytesOverride(name, pdf);
    return;
  }
  final FileSaveLocation? location = await getSaveLocation(
    suggestedName: name,
    acceptedTypeGroups: const [
      XTypeGroup(label: 'PDF file', extensions: ['pdf']),
    ],
  );
  if (location == null) return;
  await File(location.path).writeAsBytes(pdf, flush: true);
}

/// The strip above the counter's lines: no shift open, or the one that is.
/// It wraps rather than overflows at a narrow window.
class CounterShiftStrip extends StatelessWidget {
  const CounterShiftStrip({
    super.key,
    required this.shift,
    required this.busy,
    required this.onOpen,
    required this.onClose,
  });

  /// The caller's open shift, or null when their till is shut.
  final Json? shift;
  final bool busy;
  final VoidCallback onOpen;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Json? open = shift;
    final TextStyle? text = theme.textTheme.bodySmall;
    final List<Widget> facts = <Widget>[];
    if (open == null) {
      facts.add(Text('No shift open',
          key: const ValueKey('counter-shift-none'), style: text));
    } else {
      final Json summary = _summaryOf(open);
      facts.addAll(<Widget>[
        Text('Shift ${stringValue(open['shift_number'])}',
            key: const ValueKey('counter-shift-number'),
            style: text?.copyWith(fontWeight: FontWeight.w600)),
        Text('opened ${shiftStamp(open['opened_at'])}', style: text),
        Text('${summary['bills'] ?? 0} bills',
            key: const ValueKey('counter-shift-bills'), style: text),
        Text('cash expected ${_money(open['expected_cash'])}',
            key: const ValueKey('counter-shift-expected'), style: text),
      ]);
    }
    return Container(
      key: const ValueKey('counter-shift-strip'),
      margin: const EdgeInsets.fromLTRB(12, 2, 12, 2),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Wrap(
        spacing: 14,
        runSpacing: 2,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Icon(Icons.point_of_sale_outlined,
              size: 16, color: theme.colorScheme.onSurfaceVariant),
          ...facts,
          if (open == null)
            TextButton(
              key: const ValueKey('counter-shift-open'),
              onPressed: busy ? null : onOpen,
              child: const Text('Open shift'),
            )
          else
            TextButton(
              key: const ValueKey('counter-shift-close'),
              onPressed: busy ? null : onClose,
              child: const Text('Close shift'),
            ),
        ],
      ),
    );
  }
}

/// Ask how much is in the till at the start. Pops the shift the server made;
/// stays open with the server's message when it refuses.
class OpenShiftDialog extends StatefulWidget {
  const OpenShiftDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<OpenShiftDialog> createState() => _OpenShiftDialogState();
}

class _OpenShiftDialogState extends State<OpenShiftDialog> with SaveInDialog {
  final TextEditingController _float = TextEditingController(text: '0');
  String? _problem;

  @override
  void dispose() {
    _float.dispose();
    super.dispose();
  }

  void _save() {
    final String typed = _float.text.trim();
    final double? amount = double.tryParse(typed.isEmpty ? '0' : typed);
    if (amount == null || amount < 0) {
      setState(() => _problem = 'The opening float must be a number, zero or more.');
      return;
    }
    setState(() => _problem = null);
    unawaited(saveAndClose<Json>(
      () => widget.api.openCounterShift(openingFloat: typed.isEmpty ? '0' : typed),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Open shift'),
      content: SizedBox(
        width: 380,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              const Text('The cash already in the till as you start. The '
                  'shift is counted against it when you close.'),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('shift-opening-float'),
                controller: _float,
                enabled: !saving,
                autofocus: true,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Opening float'),
                onSubmitted: (_) => saving ? null : _save(),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('shift-open-problem'),
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('shift-open-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Opening…' : 'Open shift'),
        ),
      ],
    );
  }
}

/// Count the till against the shift. Reads the shift afresh, shows what it
/// took by mode, asks what was counted and says at once whether that is
/// short or over. After a successful close it offers the report; the dialog
/// pops the closed shift on Done.
class CloseShiftDialog extends StatefulWidget {
  const CloseShiftDialog({
    super.key,
    required this.api,
    required this.shiftId,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final String shiftId;
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<CloseShiftDialog> createState() => _CloseShiftDialogState();
}

class _CloseShiftDialogState extends State<CloseShiftDialog>
    with SaveInDialog {
  final TextEditingController _counted = TextEditingController();
  final TextEditingController _note = TextEditingController();
  Json? _shift;
  Json? _closed;
  String? _loadError;
  String? _reportMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_read());
  }

  @override
  void dispose() {
    _counted.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _read() async {
    try {
      final Json shift = await widget.api.counterShift(widget.shiftId);
      if (mounted) setState(() => _shift = shift);
    } on ApiException catch (error) {
      if (mounted) setState(() => _loadError = error.message);
    }
  }

  double get _expected =>
      double.tryParse(stringValue(_shift?['expected_cash'])) ?? 0;

  double? get _countedValue => double.tryParse(_counted.text.trim());

  Future<void> _close() async {
    final double? counted = _countedValue;
    if (counted == null || counted < 0) {
      setState(() => saveError = 'Enter the cash counted, zero or more.');
      return;
    }
    if (saving) return;
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final Json closed = await widget.api.closeCounterShift(
        widget.shiftId,
        countedCash: _counted.text.trim(),
        note: _note.text,
      );
      if (!mounted) return;
      setState(() {
        saving = false;
        _closed = closed;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = error.message;
      });
    }
  }

  Future<void> _print() async {
    final Json closed = _closed ?? const <String, dynamic>{};
    try {
      await saveShiftReport(
        widget.api,
        widget.shiftId,
        stringValue(closed['shift_number']),
        saveBytesOverride: widget.saveBytesOverride,
      );
      if (mounted) setState(() => _reportMessage = 'The shift report was saved.');
    } on ApiException catch (error) {
      if (mounted) setState(() => _reportMessage = error.message);
    }
  }

  Widget _tenders(Json shift, TextTheme theme) {
    final Json summary = _summaryOf(shift);
    final dynamic raw = summary['tenders'];
    final Map<String, dynamic> tenders =
        raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final MapEntry<String, dynamic> entry in tenders.entries)
          _line(entry.key, _money(entry.value)),
        _line('Opening float', _money(shift['opening_float'])),
        _line('Cash expected', _money(shift['expected_cash']), bold: true),
      ],
    );
  }

  Widget _line(String label, String value, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 1),
        child: Row(
          children: [
            Expanded(child: Text(label)),
            Text(value,
                style: bold ? const TextStyle(fontWeight: FontWeight.w600) : null),
          ],
        ),
      );

  Widget _body(BuildContext context) {
    final Json? shift = _shift;
    final ThemeData theme = Theme.of(context);
    if (_loadError != null) {
      return Text(_loadError!, style: TextStyle(color: theme.colorScheme.error));
    }
    if (shift == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final Json? closed = _closed;
    if (closed != null) {
      final double difference =
          double.tryParse(stringValue(closed['difference'])) ?? 0;
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Shift ${stringValue(closed['shift_number'])} is closed.',
              style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          _line('Cash counted', _money(closed['counted_cash'])),
          Text(differenceLabel(difference),
              key: const ValueKey('shift-closed-difference')),
          if (_reportMessage != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_reportMessage!,
                  key: const ValueKey('shift-report-message')),
            ),
        ],
      );
    }
    final int held = (_summaryOf(shift)['held_bills'] as num?)?.toInt() ?? 0;
    final double? counted = _countedValue;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        saveErrorBanner(),
        Text('Shift ${stringValue(shift['shift_number'])}, opened '
            '${shiftStamp(shift['opened_at'])}',
            style: theme.textTheme.titleSmall),
        const SizedBox(height: AppSpacing.sm),
        _tenders(shift, theme.textTheme),
        if (held > 0)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              '$held bill${held == 1 ? ' is' : 's are'} still held. Recall '
              'and finish ${held == 1 ? 'it' : 'them'}, or close the shift '
              'and leave ${held == 1 ? 'it' : 'them'} for the next one.',
              key: const ValueKey('shift-held-warning'),
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ),
        const SizedBox(height: AppSpacing.md),
        TextField(
          key: const ValueKey('shift-counted-cash'),
          controller: _counted,
          enabled: !saving,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Counted cash'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          counted == null
              ? 'Count the till to see the difference.'
              : differenceLabel(counted - _expected),
          key: const ValueKey('shift-difference'),
        ),
        const SizedBox(height: AppSpacing.md),
        TextField(
          key: const ValueKey('shift-closing-note'),
          controller: _note,
          enabled: !saving,
          maxLength: 200,
          decoration: const InputDecoration(labelText: 'Note (optional)'),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool done = _closed != null;
    return AlertDialog(
      title: const Text('Close shift'),
      content: SizedBox(
        width: 420,
        child: SingleChildScrollView(child: _body(context)),
      ),
      actions: done
          ? [
              TextButton(
                key: const ValueKey('shift-print-report'),
                onPressed: () => unawaited(_print()),
                child: const Text('Print report'),
              ),
              FilledButton(
                key: const ValueKey('shift-closed-done'),
                onPressed: () => Navigator.pop(context, _closed),
                child: const Text('Done'),
              ),
            ]
          : [
              TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
              FilledButton(
                key: const ValueKey('shift-close-save'),
                onPressed: saving || _shift == null ? null : () => unawaited(_close()),
                child: Text(saving ? 'Closing…' : 'Close shift'),
              ),
            ],
    );
  }
}

/// Ask for a few words to know a held bill by. Blank is a fine answer, so
/// this is not [askForReason]: null is "do not hold", an empty string is
/// "hold it with no note".
Future<String?> askHoldNote(BuildContext context) => showDialog<String>(
      context: context,
      builder: (_) => const _HoldNoteDialog(),
    );

class _HoldNoteDialog extends StatefulWidget {
  const _HoldNoteDialog();

  @override
  State<_HoldNoteDialog> createState() => _HoldNoteDialogState();
}

class _HoldNoteDialogState extends State<_HoldNoteDialog> {
  final TextEditingController _note = TextEditingController();

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Hold this bill'),
      content: SizedBox(
        width: 380,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('It is saved as a draft and put aside; recall it '
                  'when the customer is back.'),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('hold-note'),
                controller: _note,
                autofocus: true,
                maxLength: 200,
                decoration: const InputDecoration(
                    labelText: 'Note, to know it again (optional)'),
                onSubmitted: (_) => Navigator.pop(context, _note.text.trim()),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('hold-confirm'),
          onPressed: () => Navigator.pop(context, _note.text.trim()),
          child: const Text('Hold'),
        ),
      ],
    );
  }
}

/// The bills put aside at the counter. Pops the row chosen, or nothing.
class HeldBillsDialog extends StatefulWidget {
  const HeldBillsDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<HeldBillsDialog> createState() => _HeldBillsDialogState();
}

class _HeldBillsDialogState extends State<HeldBillsDialog> {
  static const int _pageSize = 50;

  List<Json> _rows = const [];
  int _total = 0;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final Json response =
          await widget.api.heldSalesInvoices(page: 1, pageSize: _pageSize);
      final List<Json> rows = [
        for (final dynamic item in (response['data'] as List? ?? const []))
          if (item is Map) Map<String, dynamic>.from(item),
      ];
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _total = pagedTotal(response, fallback: rows.length);
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

  String _who(Json row) {
    final String customer = stringValue(row['customer_name']);
    final String buyer = stringValue(row['buyer_name']);
    return buyer.isEmpty ? customer : '$customer ($buyer)';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    Widget body;
    if (_loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (_error != null) {
      body = Text(_error!, style: TextStyle(color: theme.colorScheme.error));
    } else if (_rows.isEmpty) {
      body = const Text('No bill is held.', key: ValueKey('held-empty'));
    } else {
      body = Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final Json row in _rows)
            ListTile(
              key: ValueKey<String>('held-bill-${row['id']}'),
              dense: true,
              title: Text(
                '${stringValue(row['invoice_number'])}  ·  ${_who(row)}',
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                [
                  'Held ${shiftStamp(row['held_at'])}',
                  if (stringValue(row['held_note']).isNotEmpty)
                    stringValue(row['held_note']),
                ].join('  ·  '),
                overflow: TextOverflow.ellipsis,
              ),
              trailing: Text(_money(row['grand_total'])),
              onTap: () => Navigator.pop(context, row),
            ),
          if (_total > _rows.length)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text('Showing the latest ${_rows.length} of $_total.'),
            ),
        ],
      );
    }
    return AlertDialog(
      title: const Text('Recall a held bill'),
      content: SizedBox(width: 520, child: SingleChildScrollView(child: body)),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
