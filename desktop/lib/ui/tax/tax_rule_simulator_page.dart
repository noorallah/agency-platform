// Tax Rule Simulator — two-panel layout: inputs (left) + results (right)

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';

// ─── Main Page ────────────────────────────────────────────────────────────────

class TaxRuleSimulatorPage extends StatefulWidget {
  const TaxRuleSimulatorPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TaxRuleSimulatorPage> createState() => _TaxRuleSimulatorPageState();
}

class _TaxRuleSimulatorPageState extends State<TaxRuleSimulatorPage> {
  // ─── Simulation state ───────────────────────────────────────────────────────
  bool _running = false;
  String? _error;
  Map<String, dynamic>? _result;

  // ─── Form state ─────────────────────────────────────────────────────────────
  final _formKey = GlobalKey<FormState>();
  String _transactionType = 'SALE';
  DateTime _transactionDate = DateTime.now();
  String? _customerType;
  String? _vendorType;
  String? _productType;

  final _invoiceValueCtrl = TextEditingController();
  final _quantityCtrl = TextEditingController();
  final _currencyCodeCtrl = TextEditingController(text: 'INR');
  final _stateCtrl = TextEditingController();
  final _originCtrl = TextEditingController();
  final _destinationCtrl = TextEditingController();
  final _customerCategoryCtrl = TextEditingController();
  final _vendorCategoryCtrl = TextEditingController();

  final _leftScroll = ScrollController();
  final _rightScroll = ScrollController();

  static const _transactionTypes = [
    'SALE',
    'PURCHASE',
    'SALE_RETURN',
    'PURCHASE_RETURN',
    'TRANSFER',
    'ADJUSTMENT',
  ];
  static const _customerTypes = [
    'LOCAL',
    'EXPORT',
    'SEZ',
    'DEEMED_EXPORT',
    'IMPORT',
  ];
  static const _vendorTypes = ['DOMESTIC', 'IMPORT', 'SEZ'];
  static const _productTypes = ['GOODS', 'SERVICE', 'MIXED', 'DIGITAL_SERVICE'];

  bool get _showCustomerType =>
      _transactionType == 'SALE' || _transactionType == 'SALE_RETURN';
  bool get _showVendorType =>
      _transactionType == 'PURCHASE' || _transactionType == 'PURCHASE_RETURN';

  @override
  void dispose() {
    _invoiceValueCtrl.dispose();
    _quantityCtrl.dispose();
    _currencyCodeCtrl.dispose();
    _stateCtrl.dispose();
    _originCtrl.dispose();
    _destinationCtrl.dispose();
    _customerCategoryCtrl.dispose();
    _vendorCategoryCtrl.dispose();
    _leftScroll.dispose();
    _rightScroll.dispose();
    super.dispose();
  }

  // ─── Simulation ─────────────────────────────────────────────────────────────

  Future<void> _runSimulation() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _running = true;
      _error = null;
      _result = null;
    });
    try {
      final invoiceVal = double.tryParse(_invoiceValueCtrl.text.trim());
      final qty = int.tryParse(_quantityCtrl.text.trim());
      final body = <String, dynamic>{
        'transaction_type': _transactionType,
        'transaction_date': _transactionDate.toIso8601String().substring(0, 10),
        if (_customerType != null && _showCustomerType)
          'customer_type': _customerType,
        if (_vendorType != null && _showVendorType)
          'vendor_type': _vendorType,
        if (_productType != null) 'product_type': _productType,
        if (invoiceVal != null) 'invoice_value': invoiceVal,
        if (qty != null) 'quantity': qty,
        if (_currencyCodeCtrl.text.trim().isNotEmpty)
          'currency_code': _currencyCodeCtrl.text.trim(),
        if (_stateCtrl.text.trim().isNotEmpty) 'state': _stateCtrl.text.trim(),
        if (_originCtrl.text.trim().isNotEmpty)
          'origin': _originCtrl.text.trim(),
        if (_destinationCtrl.text.trim().isNotEmpty)
          'destination': _destinationCtrl.text.trim(),
        if (_customerCategoryCtrl.text.trim().isNotEmpty)
          'customer_category': _customerCategoryCtrl.text.trim(),
        if (_vendorCategoryCtrl.text.trim().isNotEmpty)
          'vendor_category': _vendorCategoryCtrl.text.trim(),
      };
      final resp = await widget.api.request(
        'POST',
        '/api/v1/tax-framework/simulate',
        body: body,
      );
      if (!mounted) return;
      setState(() => _result = resp['data'] as Map<String, dynamic>?);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _transactionDate,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _transactionDate = picked);
  }

  // ─── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 420,
          child: _buildLeftPanel(),
        ),
        const VerticalDivider(width: 1),
        Expanded(child: _buildRightPanel()),
      ],
    );
  }

  // ─── Left panel ─────────────────────────────────────────────────────────────

  Widget _buildLeftPanel() {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
          decoration: BoxDecoration(
            color: cs.surface,
            border: Border(bottom: BorderSide(color: cs.outlineVariant)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Transaction Context',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 15,
                  color: cs.onSurface,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'Fill in the fields that apply to your scenario. Leave others blank.',
                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
              ),
            ],
          ),
        ),
        Expanded(
          child: Scrollbar(
            controller: _leftScroll,
            child: SingleChildScrollView(
              controller: _leftScroll,
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildTransactionTypeField(cs),
                    const SizedBox(height: 14),
                    _buildDateField(cs),
                    const SizedBox(height: 14),
                    if (_showCustomerType) ...[
                      _buildDropdown(
                        label: 'Customer Type',
                        value: _customerType,
                        items: _customerTypes,
                        onChanged: (v) => setState(() => _customerType = v),
                      ),
                      const SizedBox(height: 14),
                    ],
                    if (_showVendorType) ...[
                      _buildDropdown(
                        label: 'Vendor Type',
                        value: _vendorType,
                        items: _vendorTypes,
                        onChanged: (v) => setState(() => _vendorType = v),
                      ),
                      const SizedBox(height: 14),
                    ],
                    _buildDropdown(
                      label: 'Product Type',
                      value: _productType,
                      items: _productTypes,
                      onChanged: (v) => setState(() => _productType = v),
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _invoiceValueCtrl,
                      label: 'Invoice Value (₹)',
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(
                            RegExp(r'[0-9.]'))
                      ],
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _quantityCtrl,
                      label: 'Quantity',
                      keyboardType: TextInputType.number,
                      inputFormatters: [
                        FilteringTextInputFormatter.digitsOnly
                      ],
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _currencyCodeCtrl,
                      label: 'Currency Code',
                      maxLength: 10,
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _stateCtrl,
                      label: 'State (e.g. MH, DL, KA)',
                      maxLength: 3,
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _originCtrl,
                      label: 'Origin (optional)',
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _destinationCtrl,
                      label: 'Destination (optional)',
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _customerCategoryCtrl,
                      label: 'Customer Category (optional)',
                    ),
                    const SizedBox(height: 14),
                    _buildTextField(
                      controller: _vendorCategoryCtrl,
                      label: 'Vendor Category (optional)',
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            onPressed: _running ? null : _runSimulation,
            icon: _running
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.play_arrow_rounded, size: 18),
            label: Text(_running ? 'Running…' : '▶  Run Simulation'),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 14),
              textStyle: const TextStyle(
                  fontSize: 14, fontWeight: FontWeight.w600),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTransactionTypeField(ColorScheme cs) {
    return DropdownButtonFormField<String>(
      initialValue: _transactionType,
      decoration: const InputDecoration(
        labelText: 'Transaction Type *',
        border: OutlineInputBorder(),
        isDense: true,
      ),
      items: _transactionTypes
          .map((t) => DropdownMenuItem(value: t, child: Text(t)))
          .toList(),
      onChanged: (v) {
        if (v == null) return;
        setState(() {
          _transactionType = v;
          _customerType = null;
          _vendorType = null;
        });
      },
      validator: (v) =>
          (v == null || v.isEmpty) ? 'Transaction type is required' : null,
    );
  }

  Widget _buildDateField(ColorScheme cs) {
    final label =
        '${_transactionDate.year}-${_transactionDate.month.toString().padLeft(2, '0')}-${_transactionDate.day.toString().padLeft(2, '0')}';
    return InkWell(
      onTap: _pickDate,
      borderRadius: BorderRadius.circular(4),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Transaction Date',
          border: OutlineInputBorder(),
          isDense: true,
          suffixIcon: Icon(Icons.calendar_today_outlined, size: 16),
        ),
        child: Text(label,
            style: const TextStyle(fontSize: 14)),
      ),
    );
  }

  Widget _buildDropdown({
    required String label,
    required String? value,
    required List<String> items,
    required ValueChanged<String?> onChanged,
  }) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        isDense: true,
      ),
      hint: const Text('— none —'),
      items: items
          .map((t) => DropdownMenuItem(value: t, child: Text(t)))
          .toList(),
      onChanged: onChanged,
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    TextInputType? keyboardType,
    List<TextInputFormatter>? inputFormatters,
    int? maxLength,
  }) {
    return TextFormField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        isDense: true,
        counterText: '',
      ),
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      maxLength: maxLength,
    );
  }

  // ─── Right panel ────────────────────────────────────────────────────────────

  Widget _buildRightPanel() {
    if (_running) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: _SimErrorCard(
            message: _error!,
            onDismiss: () => setState(() => _error = null),
            onRetry: _runSimulation,
          ),
        ),
      );
    }

    if (_result == null) {
      return const _EmptyState();
    }

    return Scrollbar(
      controller: _rightScroll,
      child: SingleChildScrollView(
        controller: _rightScroll,
        padding: const EdgeInsets.all(20),
        child: _SimulationResult(result: _result!),
      ),
    );
  }
}

// ─── Empty State ──────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.science_outlined, size: 56, color: Colors.grey),
          SizedBox(height: 14),
          Text(
            'Configure inputs and run the simulation',
            style: TextStyle(color: Colors.grey, fontSize: 14),
          ),
        ],
      ),
    );
  }
}

// ─── Error Card ───────────────────────────────────────────────────────────────

class _SimErrorCard extends StatelessWidget {
  const _SimErrorCard({
    required this.message,
    required this.onDismiss,
    required this.onRetry,
  });
  final String message;
  final VoidCallback onDismiss;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.red.shade50,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: Colors.red.shade200),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, color: Colors.red.shade700, size: 36),
            const SizedBox(height: 10),
            Text(
              message,
              style:
                  TextStyle(color: Colors.red.shade800, fontSize: 13),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                OutlinedButton(
                    onPressed: onDismiss,
                    child: const Text('Dismiss')),
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Retry'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Simulation Result ───────────────────────────────────────────────────────

class _SimulationResult extends StatelessWidget {
  const _SimulationResult({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SummaryBanner(result: result),
        const SizedBox(height: 14),
        _TaxSummaryRow(result: result),
        const SizedBox(height: 14),
        _ComponentsCard(result: result),
        const SizedBox(height: 14),
        _EvaluationTraceCard(result: result),
        const SizedBox(height: 20),
      ],
    );
  }
}

// ─── Summary Banner ───────────────────────────────────────────────────────────

class _SummaryBanner extends StatelessWidget {
  const _SummaryBanner({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final exempt = result['exempt'] as bool? ?? false;
    final zeroRated = result['zero_rated'] as bool? ?? false;
    final matchedRuleId = result['matched_rule_id'];
    final hasMatch = matchedRuleId != null && matchedRuleId.toString().isNotEmpty;

    final Color bgColor;
    final Color fgColor;
    final IconData icon;

    if (exempt) {
      bgColor = Colors.orange.shade100;
      fgColor = Colors.orange.shade900;
      icon = Icons.block_outlined;
    } else if (zeroRated) {
      bgColor = Colors.blue.shade100;
      fgColor = Colors.blue.shade900;
      icon = Icons.info_outlined;
    } else if (hasMatch) {
      bgColor = Colors.green.shade100;
      fgColor = Colors.green.shade900;
      icon = Icons.check_circle_outline;
    } else {
      bgColor = Colors.grey.shade200;
      fgColor = Colors.grey.shade800;
      icon = Icons.help_outline;
    }

    // Find matched rule code + name from decisions
    String matchLabel;
    if (hasMatch) {
      final decisions = (result['decisions'] as List? ?? []);
      final matched = decisions
          .whereType<Map>()
          .where((d) => d['matched'] == true)
          .toList();
      if (matched.isNotEmpty) {
        final m = matched.first;
        matchLabel =
            'Matched: ${m['code'] ?? ''} ${m['name'] ?? ''}'.trim();
      } else {
        matchLabel = 'Rule matched';
      }
    } else {
      matchLabel = 'No rule matched — using default profile';
    }

    final reason = result['matched_rule_reason'] as String?;
    final txType = result['transaction_type'] as String? ?? '';
    final txDate = result['transaction_date'] as String? ?? '';

    return Card(
      color: bgColor,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: bgColor),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, size: 36, color: fgColor),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    matchLabel,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: fgColor,
                    ),
                  ),
                  if (reason != null && reason.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(reason,
                        style:
                            TextStyle(fontSize: 12, color: fgColor)),
                  ],
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      _smallBadge(txType, fgColor),
                      const SizedBox(width: 8),
                      _smallBadge(txDate, fgColor),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _smallBadge(String text, Color color) {
    if (text.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }
}

// ─── Tax Summary Row ──────────────────────────────────────────────────────────

class _TaxSummaryRow extends StatelessWidget {
  const _TaxSummaryRow({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final baseAmt = (result['base_amount'] as num?)?.toDouble();
    final totalTax = (result['total_tax_amount'] as num?)?.toDouble();
    final exempt = result['exempt'] as bool? ?? false;
    final zeroRated = result['zero_rated'] as bool? ?? false;
    final reverseCharge = result['reverse_charge'] as bool? ?? false;
    final inputCredit = result['input_credit_allowed'] as bool?;

    String fmt(double? v) =>
        v != null ? '₹${v.toStringAsFixed(2)}' : '—';

    return Wrap(
      spacing: 10,
      runSpacing: 8,
      children: [
        _SummaryChip(
          label: 'Base',
          value: fmt(baseAmt),
          color: cs.secondaryContainer,
          textColor: cs.onSecondaryContainer,
        ),
        _SummaryChip(
          label: 'Total Tax',
          value: fmt(totalTax),
          color: cs.primaryContainer,
          textColor: cs.onPrimaryContainer,
        ),
        if (exempt)
          _SummaryChip(
            label: 'EXEMPT',
            value: '',
            color: Colors.orange.shade100,
            textColor: Colors.orange.shade900,
          ),
        if (zeroRated)
          _SummaryChip(
            label: 'ZERO RATED',
            value: '',
            color: Colors.blue.shade100,
            textColor: Colors.blue.shade900,
          ),
        if (reverseCharge)
          _SummaryChip(
            label: 'REVERSE CHARGE',
            value: '',
            color: Colors.amber.shade100,
            textColor: Colors.amber.shade900,
          ),
        if (inputCredit != null)
          _SummaryChip(
            label: 'Input Credit',
            value: inputCredit ? 'ALLOWED' : 'BLOCKED',
            color: inputCredit
                ? Colors.green.shade100
                : Colors.red.shade100,
            textColor: inputCredit
                ? Colors.green.shade900
                : Colors.red.shade900,
          ),
      ],
    );
  }
}

class _SummaryChip extends StatelessWidget {
  const _SummaryChip({
    required this.label,
    required this.value,
    required this.color,
    required this.textColor,
  });
  final String label;
  final String value;
  final Color color;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(20),
      ),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(
              text: label,
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                  color: textColor.withAlpha(180)),
            ),
            if (value.isNotEmpty) ...[
              TextSpan(
                text: '  $value',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: textColor),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ─── Applied Components Card ──────────────────────────────────────────────────

class _ComponentsCard extends StatelessWidget {
  const _ComponentsCard({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final rawComps = result['applied_components'] as List? ?? [];
    final comps = rawComps.whereType<Map>().toList();

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Applied Components',
              style: TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
                color: cs.onSurface,
              ),
            ),
            const SizedBox(height: 12),
            if (comps.isEmpty)
              Text(
                'No components — tax may be exempt or zero-rated',
                style:
                    TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
              )
            else
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  headingRowHeight: 36,
                  dataRowMinHeight: 36,
                  dataRowMaxHeight: 44,
                  columnSpacing: 20,
                  headingTextStyle: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                    color: cs.onSurfaceVariant,
                  ),
                  columns: const [
                    DataColumn(label: Text('Component')),
                    DataColumn(label: Text('Rate %'), numeric: true),
                    DataColumn(label: Text('Amount'), numeric: true),
                    DataColumn(label: Text('Included')),
                    DataColumn(label: Text('Recoverable')),
                    DataColumn(label: Text('Source')),
                  ],
                  rows: comps.map((c) {
                    final pct =
                        (c['percentage'] as num?)?.toDouble() ?? 0.0;
                    final amt =
                        (c['amount'] as num?)?.toDouble() ?? 0.0;
                    final included =
                        c['included_in_price'] as bool? ?? false;
                    final recoverable =
                        c['recoverable'] as bool? ?? false;
                    final source =
                        (c['source'] as String? ?? 'RULE').toUpperCase();
                    final code = c['code'] as String? ?? '';
                    final label = c['label'] as String? ?? code;

                    return DataRow(cells: [
                      DataCell(Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(code,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13)),
                          if (label != code)
                            Text(label,
                                style: TextStyle(
                                    fontSize: 11,
                                    color: cs.onSurfaceVariant)),
                        ],
                      )),
                      DataCell(Text('${pct.toStringAsFixed(2)}%')),
                      DataCell(Text('₹${amt.toStringAsFixed(2)}')),
                      DataCell(Icon(
                        included ? Icons.check : Icons.remove,
                        size: 16,
                        color: included
                            ? Colors.green.shade600
                            : cs.onSurfaceVariant,
                      )),
                      DataCell(Icon(
                        recoverable ? Icons.check : Icons.close,
                        size: 16,
                        color: recoverable
                            ? Colors.green.shade600
                            : Colors.red.shade400,
                      )),
                      DataCell(_SourceChip(source: source)),
                    ]);
                  }).toList(),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SourceChip extends StatelessWidget {
  const _SourceChip({required this.source});
  final String source;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (source) {
      'RULE' => (Colors.blue.shade100, Colors.blue.shade800),
      'PROFILE' => (Colors.grey.shade200, Colors.grey.shade700),
      'OVERRIDE' => (Colors.orange.shade100, Colors.orange.shade800),
      _ => (Colors.grey.shade200, Colors.grey.shade700),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
          color: bg, borderRadius: BorderRadius.circular(10)),
      child: Text(source,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: fg)),
    );
  }
}

// ─── Evaluation Trace Card ────────────────────────────────────────────────────

class _EvaluationTraceCard extends StatelessWidget {
  const _EvaluationTraceCard({required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final rawDecisions = result['decisions'] as List? ?? [];
    final decisions = rawDecisions.whereType<Map>().toList();

    // Sort: matched first, then by priority descending
    final sorted = [...decisions]..sort((a, b) {
        final am = a['matched'] as bool? ?? false;
        final bm = b['matched'] as bool? ?? false;
        if (am && !bm) return -1;
        if (!am && bm) return 1;
        final ap = (a['priority'] as num?)?.toInt() ?? 0;
        final bp = (b['priority'] as num?)?.toInt() ?? 0;
        return bp.compareTo(ap);
      });

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Evaluation Trace — ${decisions.length} rule${decisions.length == 1 ? '' : 's'} evaluated',
              style: TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
                color: cs.onSurface,
              ),
            ),
            const SizedBox(height: 12),
            if (sorted.isEmpty)
              Text(
                'No rule evaluations returned.',
                style:
                    TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
              )
            else
              ...sorted.map((d) => _DecisionRow(decision: d)),
          ],
        ),
      ),
    );
  }
}

class _DecisionRow extends StatefulWidget {
  const _DecisionRow({required this.decision});
  final Map decision;

  @override
  State<_DecisionRow> createState() => _DecisionRowState();
}

class _DecisionRowState extends State<_DecisionRow> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final matched = widget.decision['matched'] as bool? ?? false;
    final code = widget.decision['code'] as String? ?? '';
    final name = widget.decision['name'] as String? ?? '';
    final priority = widget.decision['priority'] as num? ?? 0;
    final version = widget.decision['version_number'] as num? ?? 1;
    final reasons =
        (widget.decision['reasons'] as List? ?? []).cast<String>();

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        border: Border(
          left: BorderSide(
            color: matched ? Colors.green.shade500 : cs.outlineVariant,
            width: matched ? 3 : 1,
          ),
        ),
        color: matched
            ? Colors.green.shade50
            : cs.surfaceContainerLowest,
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(6),
          bottomRight: Radius.circular(6),
        ),
      ),
      child: InkWell(
        onTap: () => setState(() => _expanded = !_expanded),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(6),
          bottomRight: Radius.circular(6),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _PriorityBadge(priority: priority.toInt()),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Row(
                      children: [
                        Text(
                          code,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Text(
                            name,
                            style: TextStyle(
                              fontSize: 12,
                              color: cs.onSurfaceVariant,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'v$version',
                    style: TextStyle(
                        fontSize: 11, color: cs.onSurfaceVariant),
                  ),
                  const SizedBox(width: 8),
                  _MatchedChip(matched: matched),
                  const SizedBox(width: 6),
                  Icon(
                    _expanded
                        ? Icons.expand_less
                        : Icons.expand_more,
                    size: 16,
                    color: cs.onSurfaceVariant,
                  ),
                ],
              ),
              if (_expanded && reasons.isNotEmpty) ...[
                const SizedBox(height: 8),
                ...reasons.map((r) => Padding(
                      padding: const EdgeInsets.only(bottom: 3),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('• ',
                              style: TextStyle(
                                  color: cs.onSurfaceVariant,
                                  fontSize: 12)),
                          Expanded(
                            child: Text(
                              r,
                              style: TextStyle(
                                  fontSize: 12,
                                  color: cs.onSurface),
                            ),
                          ),
                        ],
                      ),
                    )),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PriorityBadge extends StatelessWidget {
  const _PriorityBadge({required this.priority});
  final int priority;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: 40,
      padding: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: cs.primary.withAlpha(20),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        '$priority',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: cs.primary,
        ),
      ),
    );
  }
}

class _MatchedChip extends StatelessWidget {
  const _MatchedChip({required this.matched});
  final bool matched;

  @override
  Widget build(BuildContext context) {
    final bg =
        matched ? Colors.green.shade100 : Colors.grey.shade200;
    final fg =
        matched ? Colors.green.shade800 : Colors.grey.shade700;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
      child: Text(
        matched ? 'MATCHED' : 'SKIPPED',
        style: TextStyle(
            fontSize: 10, fontWeight: FontWeight.w700, color: fg),
      ),
    );
  }
}
