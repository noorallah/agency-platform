// Revalue foreign payables (PG-12 part A): at a period end, restate what the
// firm still owes suppliers abroad at that day's rates. Posts one journal and
// its reversal on the next day, and refuses a second run on the same date.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';

String _money(Object? value) {
  final double? parsed = double.tryParse('${value ?? ''}');
  return parsed == null ? '—' : parsed.toStringAsFixed(2);
}

/// Ask for the date and one rate per currency, post, and show what moved.
/// Pops the server's answer; stays open with its message when refused.
class FxRevaluationDialog extends StatefulWidget {
  const FxRevaluationDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<FxRevaluationDialog> createState() => _FxRevaluationDialogState();
}

class _FxRevaluationDialogState extends State<FxRevaluationDialog>
    with SaveInDialog<FxRevaluationDialog> {
  late String _asOf;
  bool _loading = true;
  String? _problem;
  Json? _result;
  final Map<String, TextEditingController> _rates = {};
  final TextEditingController _extra = TextEditingController();

  @override
  void initState() {
    super.initState();
    _asOf = DateTime.now().toIso8601String().split('T').first;
    unawaited(_loadCurrencies());
  }

  @override
  void dispose() {
    for (final TextEditingController c in _rates.values) {
      c.dispose();
    }
    _extra.dispose();
    super.dispose();
  }

  /// The currencies suppliers are billed in: one rate box each. A currency
  /// left blank is not revalued.
  Future<void> _loadCurrencies() async {
    try {
      final List<Vendor> vendors =
          await fetchAllPages((page) => widget.api.vendors(page: page));
      if (!mounted) return;
      final Set<String> codes = {
        for (final Vendor v in vendors)
          if (v.currencyCode.isNotEmpty &&
              v.currencyCode.toUpperCase() != 'INR')
            v.currencyCode.toUpperCase(),
      };
      setState(() {
        for (final String code in (codes.toList()..sort())) {
          _rates[code] = TextEditingController();
        }
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loading = false;
      });
    }
  }

  void _addExtra() {
    final String code = _extra.text.trim().toUpperCase();
    if (!RegExp(r'^[A-Z]{3}$').hasMatch(code) || code == 'INR') {
      setState(() => _problem = 'A currency is a three-letter code, such as '
          'USD. Rupees are the books\' own currency.');
      return;
    }
    setState(() {
      _problem = null;
      _rates.putIfAbsent(code, TextEditingController.new);
      _extra.clear();
    });
  }

  Future<String?> _pick() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(_asOf) ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    return picked?.toIso8601String().split('T').first;
  }

  Future<void> _post() async {
    final Map<String, String> rates = {};
    for (final MapEntry<String, TextEditingController> entry
        in _rates.entries) {
      final String text = entry.value.text.trim();
      if (text.isEmpty) continue;
      if ((double.tryParse(text) ?? 0) <= 0) {
        setState(() => _problem = 'The rate for ${entry.key} must be a number '
            'above 0.');
        return;
      }
      rates[entry.key] = text;
    }
    if (rates.isEmpty) {
      setState(() => _problem = 'Type the rate of at least one currency.');
      return;
    }
    setState(() => _problem = null);
    if (saving) return;
    setState(() {
      saving = true;
      saveError = null;
    });
    try {
      final Json done = await widget.api.fxRevaluation(_asOf, rates);
      if (!mounted) return;
      setState(() {
        _result = done;
        saving = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saving = false;
        saveError = error.message;
      });
    }
  }

  Widget _resultView() {
    final Json r = _result!;
    final ThemeData theme = Theme.of(context);
    final double total = double.tryParse('${r['total_difference'] ?? 0}') ?? 0;
    final List<dynamic> lines = r['lines'] as List<dynamic>? ?? const [];
    final bool posted = '${r['journal_entry_id'] ?? ''}'.isNotEmpty &&
        '${r['journal_entry_id']}' != 'null';
    return Column(
      key: const ValueKey('fx-result'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          posted
              ? '${r['reference']} posted as at ${r['as_of']}, with its '
                  'reversal on the next day.'
              : 'Nothing moved, so nothing was posted.',
          style: theme.textTheme.titleSmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          total == 0
              ? 'No net exchange difference.'
              : total > 0
                  ? 'Net exchange loss ₹${_money(total)}.'
                  : 'Net exchange gain ₹${_money(-total)}.',
          key: const ValueKey('fx-total'),
        ),
        const SizedBox(height: AppSpacing.sm),
        for (final dynamic line in lines)
          if (line is Map)
            Text(
              '${line['invoice_number']} · ${line['currency_code']} '
              '${_money(line['currency_outstanding'])}: carried ₹'
              '${_money(line['carried_amount'])}, now ₹'
              '${_money(line['revalued_amount'])} '
              '(${(double.tryParse('${line['difference']}') ?? 0) > 0 ? 'loss' : 'gain'} '
              '₹${_money((double.tryParse('${line['difference']}') ?? 0).abs())})',
              style: theme.textTheme.bodySmall,
            ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final double width =
        (MediaQuery.sizeOf(context).width - 120).clamp(360.0, 560.0);
    return AlertDialog(
      title: const Text('Revalue foreign payables'),
      content: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width, maxHeight: 440),
        child: SizedBox(
          width: width,
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      saveErrorBanner(),
                      if (_problem != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: Text(_problem!,
                              key: const ValueKey('fx-problem'),
                              style: TextStyle(color: theme.colorScheme.error)),
                        ),
                      if (_result != null)
                        _resultView()
                      else ...[
                        Text(
                          'Restates what is still owed in each currency at '
                          'the rate on the period end, and posts the '
                          'difference with a reversal the next day. A '
                          'currency left blank is not revalued, and a date '
                          'can be revalued once.',
                          style: theme.textTheme.bodySmall,
                        ),
                        const SizedBox(height: AppSpacing.md),
                        InkWell(
                          key: const ValueKey('fx-as-of'),
                          onTap: saving
                              ? null
                              : () async {
                                  final String? v = await _pick();
                                  if (v != null) setState(() => _asOf = v);
                                },
                          child: InputDecorator(
                            decoration: const InputDecoration(
                              labelText: 'As of',
                              isDense: true,
                              suffixIcon: Icon(Icons.event, size: 16),
                            ),
                            child: Text(_asOf),
                          ),
                        ),
                        const SizedBox(height: AppSpacing.md),
                        for (final MapEntry<String, TextEditingController> e
                            in _rates.entries) ...[
                          TextField(
                            key: ValueKey('fx-rate-${e.key}'),
                            controller: e.value,
                            enabled: !saving,
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: InputDecoration(
                              labelText: '${e.key}: rupees per unit',
                              isDense: true,
                            ),
                          ),
                          const SizedBox(height: AppSpacing.sm),
                        ],
                        Row(children: [
                          Expanded(
                            child: TextField(
                              key: const ValueKey('fx-extra-code'),
                              controller: _extra,
                              enabled: !saving,
                              maxLength: 3,
                              textCapitalization:
                                  TextCapitalization.characters,
                              decoration: const InputDecoration(
                                labelText: 'Another currency',
                                isDense: true,
                                counterText: '',
                              ),
                            ),
                          ),
                          IconButton(
                            key: const ValueKey('fx-add-currency'),
                            tooltip: 'Add currency',
                            onPressed: saving ? null : _addExtra,
                            icon: const Icon(Icons.add),
                          ),
                        ]),
                      ],
                    ],
                  ),
                ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(_result),
          child: Text(_result == null ? 'Cancel' : 'Close'),
        ),
        if (_result == null)
          FilledButton(
            key: const ValueKey('fx-post'),
            onPressed: saving ? null : () => unawaited(_post()),
            child: const Text('Post revaluation'),
          ),
      ],
    );
  }
}
