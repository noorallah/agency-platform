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
import '../../models/gst_registration.dart';
import '../workspace/desktop_framework.dart';

/// Which return is on screen.
enum _ReturnView { gstr1, gstr3b, gstr1Quarter, iff }

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
  // Quarterly filers (GST-7): the quarter's GSTR-1 and the optional IFF.
  bool _quarterly = false;
  String? _qPeriod;
  Json? _quarterData;
  String? _error;
  bool _loading = false;
  // Every GSTIN the firm files under; the picker shows only for 2 or more.
  List<GstRegistration> _registrations = const [];
  String? _gstin;

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
    if (widget.hasActiveFirm && _mayView) {
      _load();
      _loadPlan();
      _loadRegistrations();
    }
  }

  Future<void> _loadRegistrations() async {
    try {
      final List<GstRegistration> found = await widget.api.gstRegistrations();
      if (!mounted) return;
      setState(() => _registrations = found);
    } catch (_) {
      // Without the list the page files under the firm's own GSTIN.
    }
  }

  Future<void> _loadPlan() async {
    try {
      final Json plan = await widget.api.gstFilingPlan();
      if (!mounted) return;
      setState(() => _quarterly = plan['filing_frequency'] == 'QUARTERLY');
    } on ApiException {
      // Without a plan the screen stays what a monthly filer sees.
    }
  }

  /// Month options for the quarterly modes: quarter ends for GSTR-1, the
  /// first two months of a quarter for the IFF. Newest first.
  List<String> _quarterMonths() {
    final DateTime now = DateTime.now();
    final List<String> out = [];
    for (int back = 0; back < 24; back++) {
      final DateTime month = DateTime(now.year, now.month - back);
      if ((month.month % 3 == 0) == (_view == _ReturnView.gstr1Quarter)) {
        out.add('${month.year.toString().padLeft(4, '0')}-'
            '${month.month.toString().padLeft(2, '0')}');
      }
    }
    return out;
  }

  Future<void> _loadQuarter() async {
    final List<String> options = _quarterMonths();
    final String period =
        options.contains(_qPeriod) ? _qPeriod! : options.first;
    setState(() {
      _qPeriod = period;
      _loading = true;
      _error = null;
      _quarterData = null;
    });
    try {
      final Json data = _view == _ReturnView.iff
          ? await widget.api.gstIff(period)
          : await widget.api.gstr1Quarterly(period);
      if (!mounted) return;
      setState(() {
        _quarterData = data;
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

  void _chooseView(_ReturnView view) {
    setState(() => _view = view);
    if (view == _ReturnView.gstr1Quarter || view == _ReturnView.iff) {
      _loadQuarter();
    }
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
        gstin: _gstin,
      );
      final Json summary = await widget.api.gstr3b(
        fromDate: _from.text.trim(),
        toDate: _to.text.trim(),
        gstin: _gstin,
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
    final bool phase2 = Phase2Scope.of(context);
    return ManagementWorkspaceLayout(
      // Phase 2 (review, 2026-09-27): the return's period is the Period
      // control on the page line, not a panel squeezed into the search slot.
      toolbar: phase2
          ? WorkspaceToolbar(
              actions: const [ToolbarAction.refresh],
              isEnabled: (_) => !_loading,
              onAction: (_) => _load(),
              trailing: [
                DateRangeFilter(
                  value: DatePeriod.custom(
                    _parse(_from.text, DateTime.now()),
                    _parse(_to.text, DateTime.now()),
                  ),
                  onChanged: (period) {
                    // A return is always for a period; "all" is not one.
                    if (period.from == null || period.to == null) return;
                    setState(() {
                      _from.text = _iso(period.from!);
                      _to.text = _iso(period.to!);
                    });
                    _load();
                  },
                ),
              ],
            )
          : Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                Phase2Refresh(
                  onPressed: _load,
                  child: OutlinedButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Refresh'),
                  ),
                ),
              ],
            ),
      searchPanel: phase2 ? const SizedBox.shrink() : _periodPanel(),
      notice: _gstr1 == null
          ? null
          : 'Filing as ${stringValue(_gstr1!['gstin'])}. Derived from the '
              'documents on every read, never stored.',
      viewBar: Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.sm,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (_registrations.length > 1)
            SizedBox(
              width: 340,
              child: DropdownButtonFormField<String>(
                key: const ValueKey('gst-registration'),
                isExpanded: true,
                initialValue: _gstin ?? _registrations.first.gstin,
                decoration: const InputDecoration(
                  labelText: 'GSTIN',
                  isDense: true,
                ),
                items: [
                  for (final GstRegistration entry in _registrations)
                    DropdownMenuItem(
                      value: entry.gstin,
                      child: Text(entry.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (value) {
                  if (value == null) return;
                  setState(() => _gstin = value);
                  _load();
                },
              ),
            ),
          SegmentedButton<_ReturnView>(
            segments: [
              const ButtonSegment(
                  value: _ReturnView.gstr1, label: Text('GSTR-1')),
              const ButtonSegment(
                  value: _ReturnView.gstr3b, label: Text('GSTR-3B')),
              if (_quarterly) ...const [
                ButtonSegment(
                    value: _ReturnView.gstr1Quarter,
                    label: Text('Quarterly GSTR-1')),
                ButtonSegment(value: _ReturnView.iff, label: Text('IFF')),
              ],
            ],
            selected: {_view},
            showSelectedIcon: false,
            onSelectionChanged: (selection) => _chooseView(selection.first),
          ),
          if (_view == _ReturnView.gstr1Quarter || _view == _ReturnView.iff)
            SizedBox(
              width: 150,
              child: DropdownButtonFormField<String>(
                key: const ValueKey('gst-quarter-period'),
                initialValue: _qPeriod,
                decoration: InputDecoration(
                  labelText:
                      _view == _ReturnView.iff ? 'IFF month' : 'Quarter ending',
                  isDense: true,
                ),
                items: [
                  for (final String month in _quarterMonths())
                    DropdownMenuItem(value: month, child: Text(month)),
                ],
                onChanged: (value) {
                  if (value == null) return;
                  setState(() => _qPeriod = value);
                  _loadQuarter();
                },
              ),
            ),
        ],
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

  /// The period is chosen, not typed.
  ///
  /// Both dates were free text and a malformed one was caught only by the
  /// server (plan item 12.1, BACKLOG 31.15). A return is filed by month, so the
  /// arrows step a whole calendar month; either box opens one range calendar
  /// for an odd period. Every change reads the return again.
  Widget _periodPanel() => Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Previous month',
              onPressed: () => _shiftMonth(-1),
              icon: const Icon(Icons.chevron_left),
            ),
            Expanded(child: _dateBox(_from, 'From', isStart: true)),
            const SizedBox(width: AppSpacing.lg),
            Expanded(child: _dateBox(_to, 'To', isStart: false)),
            IconButton(
              tooltip: 'Next month',
              onPressed: () => _shiftMonth(1),
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      );

  Widget _dateBox(
    TextEditingController controller,
    String label, {
    required bool isStart,
  }) =>
      TextField(
        controller: controller,
        readOnly: true,
        onTap: () => _pickDate(isStart: isStart),
        decoration: InputDecoration(
          labelText: label,
          suffixIcon: const Icon(Icons.calendar_month),
        ),
      );

  static DateTime _parse(String text, DateTime fallback) =>
      DateTime.tryParse(text.trim()) ?? fallback;

  /// One calendar for both ends of the period: tap the first day, then the
  /// last. Two separate pickers made choosing a range two trips (plan item
  /// 12.1, 2026-09-13).
  Future<void> _pickDate({required bool isStart}) async {
    final DateTime now = DateTime.now();
    final DateTime from = _parse(_from.text, DateTime(now.year, now.month));
    final DateTime to = _parse(_to.text, DateTime(now.year, now.month + 1, 0));
    final DateTimeRange? picked = await showDateRangePicker(
      context: context,
      initialDateRange: DateTimeRange(
        start: from,
        end: to.isBefore(from) ? from : to,
      ),
      firstDate: DateTime(2000),
      lastDate: DateTime(now.year + 1, 12, 31),
      helpText: 'Return period',
      saveText: 'Use this period',
    );
    if (picked == null || !mounted) return;
    setState(() {
      _from.text = _iso(picked.start);
      _to.text = _iso(picked.end);
    });
    await _load();
  }

  Future<void> _shiftMonth(int months) async {
    final DateTime now = DateTime.now();
    final DateTime from = _parse(_from.text, DateTime(now.year, now.month));
    final DateTime start = DateTime(from.year, from.month + months);
    setState(() {
      _from.text = _iso(start);
      _to.text = _iso(DateTime(start.year, start.month + 1, 0));
    });
    await _load();
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        icon: Icons.error_outline,
        title: 'The return cannot be built',
        message: _error!,
      );
    }
    final Json? data = switch (_view) {
      _ReturnView.gstr1 => _gstr1,
      _ReturnView.gstr3b => _gstr3b,
      _ => _quarterData,
    };
    if (data == null) {
      return const WorkspaceEmptyState(
        title: 'Nothing yet',
        message: 'Choose a period and refresh.',
      );
    }
    return SingleChildScrollView(
      child: switch (_view) {
        _ReturnView.gstr1 => _one(data),
        _ReturnView.gstr3b => _summary(data),
        _ReturnView.gstr1Quarter => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [_quarterNotes(data), _one(data)],
          ),
        _ReturnView.iff => _iffView(data),
      },
    );
  }

  /// What a quarter's GSTR-1 needs said: its due date and what was already
  /// furnished through the IFF in months 1 and 2.
  Widget _quarterNotes(Json data) {
    final ThemeData theme = Theme.of(context);
    final List<dynamic> furnished =
        data['furnished_in_iff'] as List<dynamic>? ?? const [];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Quarter ${stringValue(data['quarter'])}, due '
            '${stringValue(data['due_date'])}.',
            key: const ValueKey('gst-quarter-due'),
            style: theme.textTheme.titleSmall,
          ),
          if (furnished.isNotEmpty)
            Text(
              'Already furnished through the IFF for '
              '${furnished.map(stringValue).join(', ')}; those invoices are '
              'not repeated by the buyer, but stay in this return.',
              key: const ValueKey('gst-quarter-furnished'),
              style: theme.textTheme.bodySmall,
            ),
        ],
      ),
    );
  }

  /// The invoice furnishing facility: B2B invoices and credit notes of month
  /// 1 or 2, optional, with a limit on what it may carry.
  Widget _iffView(Json data) {
    final ThemeData theme = Theme.of(context);
    final List<dynamic> b2b = data['b2b'] as List<dynamic>? ?? const [];
    final List<dynamic> cdnr = data['cdnr'] as List<dynamic>? ?? const [];
    final List<dynamic> unplaced =
        data['unplaced_invoices'] as List<dynamic>? ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: Text(
            'IFF for ${stringValue(data['return_period'])} '
            '(${stringValue(data['from_date'])} to '
            '${stringValue(data['to_date'])}), optional, by '
            '${stringValue(data['due_date'])}. B2B value '
            '${_money(data['b2b_value'])} of a ${_money(data['limit'])} limit.'
            '${data['filed'] == true ? ' Marked filed.' : ''}',
            key: const ValueKey('gst-iff-summary'),
            style: theme.textTheme.titleSmall,
          ),
        ),
        if (data['over_limit'] == true)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Text(
              'Over the limit: the portal will not take more than '
              '${_money(data['limit'])} of B2B value in one IFF. Leave some '
              'invoices for the quarterly GSTR-1.',
              key: const ValueKey('gst-iff-over-limit'),
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: theme.colorScheme.error),
            ),
          ),
        _Section(
          title: 'B2B — registered buyers, invoice by invoice',
          headers: const [
            'Invoice',
            'Buyer GSTIN',
            'Taxable',
            'CGST',
            'SGST',
            'IGST',
          ],
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
        ),
        _Section(
          title: 'CDNR — credit notes to registered buyers',
          headers: const ['Note', 'Against', 'Taxable', 'CGST', 'SGST'],
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
        ),
        _Section(
          title: 'Invoices without a place of supply — named here, not filed',
          headers: const ['Invoice'],
          rows: [
            for (final dynamic number in unplaced) [stringValue(number)],
          ],
        ),
      ],
    );
  }

  Widget _one(Json data) {
    final List<dynamic> b2b = data['b2b'] as List<dynamic>? ?? const [];
    final List<dynamic> b2cs = data['b2cs'] as List<dynamic>? ?? const [];
    final List<dynamic> cdnr = data['cdnr'] as List<dynamic>? ?? const [];
    final List<dynamic> cdnur = data['cdnur'] as List<dynamic>? ?? const [];
    final List<dynamic> hsn = data['hsn'] as List<dynamic>? ?? const [];
    final List<dynamic> nil =
        data['nil_exempt'] as List<dynamic>? ?? const [];
    final List<dynamic> docs = data['docs'] as List<dynamic>? ?? const [];
    final List<dynamic> unplaced =
        data['unplaced_invoices'] as List<dynamic>? ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Phase 2 says who is filing behind the page line's (i).
        if (!Phase2Scope.of(context)) ...[
          Text('Filing as ${stringValue(data['gstin'])}',
              style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.md),
        ],
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
        // Nil-rated, exempt and non-GST supplies are their own table, not a
        // 0% row in B2B or B2CS (D-CMP-10).
        _Section(
          title: 'Table 8 — nil-rated, exempt and non-GST supplies',
          headers: const ['Supply', 'Nil rated', 'Exempted', 'Non-GST'],
          rows: [
            for (final dynamic row in nil)
              ([
                stringValue((row as Map)['supply_type']),
                _money(row['nil_rated']),
                _money(row['exempted']),
                _money(row['non_gst']),
              ]),
          ],
        ),
        // Credits to an unregistered buyer against a B2CL bill: declared note
        // by note, because the bill was (Table 9B).
        if (cdnur.isNotEmpty)
          _Section(
            title: 'CDNUR — credits against large inter-state B2C bills',
            rows: [
              for (final dynamic row in cdnur)
                ([
                  stringValue((row as Map)['note_number']),
                  stringValue(row['against_invoice']),
                  _money(row['taxable_value']),
                  _money(row['integrated_tax']),
                ]),
            ],
            headers: const ['Note', 'Against', 'Taxable', 'IGST'],
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
        // Every number in the range is accounted for: a cancelled bill is a
        // gap the return has to explain (D-CMP-10).
        _Section(
          title: 'Documents issued',
          headers: const ['Series', 'Range', 'Total', 'Cancelled', 'Net'],
          rows: [
            for (final dynamic row in docs)
              ([
                stringValue((row as Map)['prefix']),
                '${stringValue(row['from'])} to ${stringValue(row['to'])}',
                '${row['total_number'] ?? row['count'] ?? 0}',
                '${row['cancelled'] ?? 0}',
                '${row['net_issued'] ?? row['count'] ?? 0}',
              ]),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        // The server names an invoice it could not place rather than filing
        // a blank row the portal would reject; the screen never showed the
        // list (mapping section 12, 2026-09-13).
        _Section(
          title: 'Invoices without a place of supply — named here, not filed',
          headers: const ['Invoice'],
          rows: [
            for (final dynamic number in unplaced) [stringValue(number)],
          ],
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
    final Map<String, dynamic> nilExempt =
        (data['nil_rated_and_exempt_supplies'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final Map<String, dynamic> nonGst =
        (data['non_gst_supplies'] as Map?)?.cast<String, dynamic>() ??
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
          title: '3.1(c) — nil-rated and exempt supplies',
          headers: const ['Taxable'],
          rows: [
            ([_money(nilExempt['taxable_value'])]),
          ],
        ),
        _Section(
          title: '3.1(e) — non-GST supplies',
          headers: const ['Value'],
          rows: [
            ([_money(nonGst['taxable_value'])]),
          ],
        ),
        _Section(
          title: 'Credit notes already deducted above',
          headers: const ['Taxable', 'Tax'],
          rows: [
            ([_money(credited['taxable_value']), _money(credited['tax'])]),
          ],
        ),
        _inputCredit(data),
      ],
    );
  }

  /// Table 4: the credit claimed and what is taken off it. A block the server
  /// did not send is left out rather than shown as zero, so an older server
  /// never reads as "no blocked credit".
  Widget _inputCredit(Json data) {
    const List<(String, String)> lines = [
      ('eligible_itc', '4(A)(5) All other ITC (includes blocked credit)'),
      ('itc_reverse_charge', '4(A)(3) Reverse charge'),
      ('itc_reversed_blocked', '4(B)(1) ITC reversed — blocked (s.17(5))'),
      ('itc_reversed', '4(B)(2) ITC reversed — returns and others'),
      ('itc_reversed_rule37', 'of which rule 37'),
      ('net_itc', '4(C) Net ITC available'),
      ('itc_reclaimed', '4(D)(1) Reclaimed (rule 37)'),
      ('itc_ineligible', '4(D)(2) Ineligible ITC'),
    ];
    final List<List<String>> rows = [];
    for (final (String key, String label) in lines) {
      final Object? block = data[key];
      if (block is! Map) continue;
      rows.add([
        label,
        _money(block['integrated_tax']),
        _money(block['central_tax']),
        _money(block['state_tax']),
        _money(block['cess']),
      ]);
    }
    if (rows.isEmpty) {
      // Said rather than shown as zero: a zero would read as "no input
      // credit", which is a different claim from "not sent" (D-UI-1).
      return Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.lg),
        child: Text(
          'Table 4 (input tax credit) was not sent by the server, '
          'so it is not shown here.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }
    // Credit held back until the supplier files it (backlog 78 row 3); only
    // nonzero when the firm claims on 2B-matched bills only.
    final Object? held = data['itc_awaiting_2b'];
    if (held is Map &&
        <String>['integrated_tax', 'central_tax', 'state_tax', 'cess']
            .any((key) => (double.tryParse('${held[key] ?? 0}') ?? 0) != 0)) {
      rows.add([
        'Held back — not yet in GSTR-2B',
        _money(held['integrated_tax']),
        _money(held['central_tax']),
        _money(held['state_tax']),
        _money(held['cess']),
      ]);
    }
    return _Section(
      title: '4 — eligible input tax credit',
      headers: const ['Line', 'IGST', 'CGST', 'SGST', 'Cess'],
      rows: rows,
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
