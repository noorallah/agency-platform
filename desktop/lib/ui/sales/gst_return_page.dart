// What this firm declares for a period, read off what it actually sold.
//
// Nothing here is stored. A return is a view of the documents, so what the
// screen shows is what the invoices and credit notes say right now — a
// cancelled invoice drops out of it, and a credit note raised late appears in
// the month it was issued.

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// Which return is on screen.
enum _ReturnView { gstr1, gstr3b }

/// Show GSTR-1 section by section, and the outward half of GSTR-3B.
class GstReturnPage extends StatefulWidget {
  const GstReturnPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<GstReturnPage> createState() => _GstReturnPageState();
}

class _GstReturnPageState extends State<GstReturnPage> {
  late final TextEditingController _from =
      TextEditingController(text: _firstOfThisMonth());
  late final TextEditingController _to =
      TextEditingController(text: _lastOfThisMonth());

  _ReturnView _view = _ReturnView.gstr1;
  Json? _gstr1;
  Json? _gstr3b;
  String? _error;
  bool _loading = false;

  bool get _mayView => widget.permissions.hasPermission('SALES_VIEW');

  static String _firstOfThisMonth() {
    final DateTime now = DateTime.now();
    return _iso(DateTime(now.year, now.month));
  }

  static String _lastOfThisMonth() {
    final DateTime now = DateTime.now();
    return _iso(DateTime(now.year, now.month + 1, 0));
  }

  static String _iso(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      // Dropped on the way in. A refusal is reported in place of the
      // figures below, so this is belt and braces rather than the thing that
      // stops last month's numbers appearing under this month's dates.
      _gstr1 = null;
      _gstr3b = null;
    });
    try {
      final Json one = await widget.api.gstr1(
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
      );
      final Json summary = await widget.api.gstr3b(
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _gstr1 = one;
        _gstr3b = summary;
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
        message: 'A return is filed by one firm’s GST number.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see returns',
        message: 'A return lists every sale of the period, so reading it '
            'needs the view sales permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: _periodPanel(),
      viewBar: SegmentedButton<_ReturnView>(
        segments: const [
          ButtonSegment(value: _ReturnView.gstr1, label: Text('GSTR-1')),
          ButtonSegment(value: _ReturnView.gstr3b, label: Text('GSTR-3B')),
        ],
        selected: {_view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) =>
            setState(() => _view = selection.first),
      ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _declared(),
        selected: false,
        message: 'Derived from the documents on every read, never stored.',
      ),
    );
  }

  /// How many documents the return declares, off the series it reports.
  int _declared() {
    final List<dynamic> docs = _gstr1?['docs'] as List<dynamic>? ?? const [];
    return docs.fold<int>(
      0,
      (running, row) => running + ((row as Map)['count'] as int? ?? 0),
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

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'The return cannot be built',
        message: _error!,
      );
    }
    final Json? data = _view == _ReturnView.gstr1 ? _gstr1 : _gstr3b;
    if (data == null) {
      return const WorkspaceEmptyState(
        title: 'Nothing yet',
        message: 'Choose a period and refresh.',
      );
    }
    return SingleChildScrollView(
      child: _view == _ReturnView.gstr1 ? _one(data) : _summary(data),
    );
  }

  Widget _one(Json data) {
    final List<dynamic> b2b = data['b2b'] as List<dynamic>? ?? const [];
    final List<dynamic> b2cs = data['b2cs'] as List<dynamic>? ?? const [];
    final List<dynamic> cdnr = data['cdnr'] as List<dynamic>? ?? const [];
    final List<dynamic> hsn = data['hsn'] as List<dynamic>? ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Filing as ${stringValue(data['gstin'])}',
            style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: AppSpacing.md),
        _Section(
          title: 'B2B — registered buyers, invoice by invoice',
          // Invoice-wise because the buyer claims credit against the number.
          rows: [
            for (final dynamic party in b2b)
              for (final dynamic invoice
                  in (party as Map)['invoices'] as List<dynamic>? ?? const [])
                ([
                  stringValue((invoice as Map)['invoice_number']),
                  stringValue(party['gstin']),
                  _money(invoice['taxable_value']),
                  _money(invoice['central_tax']),
                  _money(invoice['state_tax']),
                  _money(invoice['integrated_tax']),
                ]),
          ],
          headers: const [
            'Invoice',
            'Buyer GSTIN',
            'Taxable',
            'CGST',
            'SGST',
            'IGST',
          ],
        ),
        _Section(
          title: 'B2CS — unregistered, summarised by place and rate',
          rows: [
            for (final dynamic row in b2cs)
              ([
                stringValue((row as Map)['place_of_supply']),
                '${row['rate']}%',
                _money(row['taxable_value']),
                _money(row['central_tax']),
                _money(row['state_tax']),
              ]),
          ],
          headers: const ['Place', 'Rate', 'Taxable', 'CGST', 'SGST'],
        ),
        _Section(
          title: 'CDNR — credit notes to registered buyers',
          rows: [
            for (final dynamic row in cdnr)
              ([
                stringValue((row as Map)['note_number']),
                stringValue(row['against_invoice']),
                _money(row['taxable_value']),
                _money(row['central_tax']),
                _money(row['state_tax']),
              ]),
          ],
          headers: const ['Note', 'Against', 'Taxable', 'CGST', 'SGST'],
        ),
        _Section(
          title: 'HSN summary',
          rows: [
            for (final dynamic row in hsn)
              ([
                stringValue((row as Map)['hsn']),
                '${row['rate']}%',
                '${row['quantity']}',
                _money(row['taxable_value']),
                _money(row['central_tax']),
                _money(row['state_tax']),
              ]),
          ],
          headers: const ['HSN', 'Rate', 'Quantity', 'Taxable', 'CGST', 'SGST'],
        ),
      ],
    );
  }

  Widget _summary(Json data) {
    final Map<String, dynamic> outward =
        (data['outward_taxable_supplies'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final Map<String, dynamic> credited =
        (data['credit_notes_deducted'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Section(
          title: '3.1(a) — outward taxable supplies',
          headers: const ['Taxable', 'IGST', 'CGST', 'SGST', 'Cess'],
          rows: [
            ([
              _money(outward['taxable_value']),
              _money(outward['integrated_tax']),
              _money(outward['central_tax']),
              _money(outward['state_tax']),
              _money(outward['cess']),
            ]),
          ],
        ),
        _Section(
          title: 'Credit notes already deducted above',
          headers: const ['Taxable', 'Tax'],
          rows: [
            ([_money(credited['taxable_value']), _money(credited['tax'])]),
          ],
        ),
        Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Text(
            // Said rather than shown as zero: a zero would read as "no input
            // credit", which is a different claim from "not derived here".
            stringValue(data['inward_supplies']),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ],
    );
  }

  static String _money(Object? value) {
    final double? parsed = double.tryParse('${value ?? 0}');
    return parsed == null ? '${value ?? ''}' : parsed.toStringAsFixed(2);
  }
}

/// One section of a return, with its own heading and columns.
class _Section extends StatelessWidget {
  const _Section({
    required this.title,
    required this.headers,
    required this.rows,
  });

  final String title;
  final List<String> headers;
  final List<List<String>> rows;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          if (rows.isEmpty)
            Text('Nothing in this section.', style: theme.textTheme.bodySmall)
          else
            // Wide sections scroll inside themselves rather than pushing the
            // page sideways.
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: [
                  for (final String header in headers)
                    DataColumn(label: Text(header)),
                ],
                rows: [
                  for (final List<String> row in rows)
                    DataRow(
                      cells: [for (final String cell in row) DataCell(Text(cell))],
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
