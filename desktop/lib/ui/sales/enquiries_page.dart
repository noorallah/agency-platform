// Enquiries and leads (SEL-10): what a prospect asked for before there is a
// quotation. An enquiry is followed up, then either lost with a reason or
// converted into a quotation (a prospect becomes a customer on the way).
// Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/enquiry.dart';
import '../workspace/desktop_framework.dart';
import 'enquiry_editor_dialog.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) => status.isEmpty
    ? status
    : (status[0] + status.substring(1).toLowerCase()).replaceAll('_', ' ');

String _labelOf(List<(String, String)> options, String code) {
  for (final (String value, String label) in options) {
    if (value == code) return label;
  }
  return _words(code);
}

const List<String> _statuses = ['OPEN', 'QUOTED', 'WON', 'LOST'];

/// List the enquiries and move each one along.
class EnquiriesPage extends StatefulWidget {
  const EnquiriesPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.onOpenQuotations,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Takes the person to Quotations after a conversion, when the host can.
  final VoidCallback? onOpenQuotations;

  @override
  State<EnquiriesPage> createState() => _EnquiriesPageState();
}

class _EnquiriesPageState extends State<EnquiriesPage> {
  List<Enquiry> _rows = const [];
  String? _error;
  String? _selectedId;
  String? _status;
  bool _dueOnly = false;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('SALES_VIEW');
  bool get _mayCreate =>
      widget.permissions.hasPermission('SALES_QUOTATION_CREATE');
  bool get _mayUpdate => widget.permissions.hasPermission('SALES_UPDATE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<Enquiry> rows = _dueOnly
          ? await fetchAllPages<Enquiry>(
              (int page) => widget.api.followUpsDue(page: page),
            )
          : await fetchAllPages<Enquiry>(
              (int page) => widget.api.enquiries(page: page, status: _status),
            );
      if (!mounted) return;
      setState(() {
        _rows = rows;
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

  List<Enquiry> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.enquiryNumber.toLowerCase().contains(q) ||
            row.buyer.toLowerCase().contains(q) ||
            row.prospectName.toLowerCase().contains(q))
        .toList();
  }

  Enquiry? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  /// Selects a row and reads it afresh, so the lines and the follow-up log
  /// beside the grid are what the server holds now.
  void _choose(Enquiry row) {
    setState(() => _selectedId = row.id);
    unawaited(_reread(row.id));
  }

  Future<void> _reread(String id) async {
    try {
      final Enquiry fresh = await widget.api.enquiry(id);
      if (!mounted) return;
      setState(() {
        _rows = [for (final Enquiry r in _rows) r.id == id ? fresh : r];
      });
    } on ApiException {
      // The list row stays on show; the next refresh will say what is wrong.
    }
  }

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _edit({Enquiry? enquiry}) async {
    final Enquiry? saved = await showDialog<Enquiry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => EnquiryEditorDialog(api: widget.api, enquiry: enquiry),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Enquiry ${saved.enquiryNumber} saved.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _followUp(Enquiry enquiry) async {
    final Enquiry? saved = await showDialog<Enquiry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => LogFollowUpDialog(api: widget.api, enquiry: enquiry),
    );
    if (saved == null || !mounted) return;
    _tell('Follow-up logged.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _lost(Enquiry enquiry) async {
    final Enquiry? saved = await showDialog<Enquiry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => MarkLostDialog(api: widget.api, enquiry: enquiry),
    );
    if (saved == null || !mounted) return;
    _tell('Enquiry ${saved.enquiryNumber} marked lost.',
        AppNotificationKind.success);
    await _load();
  }

  Future<void> _convert(Enquiry enquiry) async {
    final Enquiry? saved = await showDialog<Enquiry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ConvertEnquiryDialog(api: widget.api, enquiry: enquiry),
    );
    if (saved == null || !mounted) return;
    final VoidCallback? open = widget.onOpenQuotations;
    _tell(
      'Quotation raised from ${saved.enquiryNumber}'
      '${saved.quotationId == null ? '' : ' (${saved.quotationId})'}.'
      '${open == null ? '' : ' Open Quotations to see it.'}',
      AppNotificationKind.success,
    );
    await _load();
    if (open != null && mounted) {
      final bool? go = await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          title: const Text('Quotation raised'),
          content: Text('${saved.enquiryNumber} is now quoted. Open the '
              'Quotations screen?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialog, false),
              child: const Text('Stay here'),
            ),
            FilledButton(
              key: const ValueKey('enquiry-open-quotations'),
              onPressed: () => Navigator.pop(dialog, true),
              child: const Text('Open Quotations'),
            ),
          ],
        ),
      );
      if (go == true) open();
    }
  }

  Future<void> _lostReasons() => showDialog<void>(
        context: context,
        builder: (_) => LostReasonsDialog(api: widget.api),
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Enquiries belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see enquiries',
        message: 'Reading them needs the view sales permission.',
      );
    }
    final Enquiry? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'What prospects and customers have asked for before there is a '
          'quotation. Follow each one up, then quote it or record why it was '
          'lost.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number or buyer',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.enquiryNumber,
              party: picked.buyer,
              status: picked.status,
              total: picked.expectedValue,
              onClear: () => setState(() => _selectedId = null),
            ),
      detailsWidth: 380,
      detailsPanel: picked == null ? null : _details(picked),
      primaryContent: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _filters(),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.sm),
                    child: Text(_error!,
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error)),
                  ),
                const SizedBox(height: AppSpacing.md),
                Expanded(child: _grid()),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: _dueOnly ? 'Follow-ups due' : 'Enquiries',
      ),
    );
  }

  Widget _filters() => Padding(
        padding: const EdgeInsets.only(top: AppSpacing.sm),
        child: Row(children: [
          SizedBox(
            width: 200,
            child: DropdownButtonFormField<String?>(
              key: const ValueKey('enquiry-status-filter'),
              isExpanded: true,
              initialValue: _status,
              decoration: const InputDecoration(
                  labelText: 'Status', isDense: true),
              items: [
                const DropdownMenuItem<String?>(
                    value: null, child: Text('All')),
                for (final String s in _statuses)
                  DropdownMenuItem<String?>(value: s, child: Text(_words(s))),
              ],
              onChanged: _dueOnly
                  ? null
                  : (value) {
                      setState(() => _status = value);
                      unawaited(_load());
                    },
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          FilterChip(
            key: const ValueKey('enquiry-due-toggle'),
            label: const Text('Follow-ups due'),
            avatar: const Icon(Icons.alarm_outlined, size: 16),
            selected: _dueOnly,
            onSelected: (on) {
              setState(() => _dueOnly = on);
              unawaited(_load());
            },
          ),
        ]),
      );

  WorkspaceToolbar _toolbar(Enquiry? selected) {
    final Enquiry? e = selected;
    return WorkspaceToolbar(
      trailing: [
        ColumnsButton(
          onPressed: () async {
            if (await _columns.choose(context) && mounted) setState(() {});
          },
        ),
      ],
      actions: [
        ToolbarAction.refresh,
        if (_mayCreate) ToolbarAction.newItem,
      ],
      isEnabled: (action) => true,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_edit());
          default:
            unawaited(_load());
        }
      },
      commands: [
        if (_mayUpdate) ...[
          ToolbarCommand(
            id: 'edit-enquiry',
            label: 'Edit',
            icon: Icons.edit_outlined,
            onPressed: e != null && e.isOpen
                ? () => unawaited(_edit(enquiry: e))
                : null,
          ),
          ToolbarCommand(
            id: 'log-follow-up',
            label: 'Log follow-up',
            icon: Icons.phone_callback_outlined,
            onPressed: e != null && e.isLive
                ? () => unawaited(_followUp(e))
                : null,
          ),
          ToolbarCommand(
            id: 'mark-lost',
            label: 'Mark lost',
            icon: Icons.thumb_down_outlined,
            onPressed:
                e != null && e.isLive ? () => unawaited(_lost(e)) : null,
          ),
        ],
        if (_mayCreate)
          ToolbarCommand(
            id: 'convert-enquiry',
            label: 'Convert to quotation',
            icon: Icons.request_quote_outlined,
            onPressed:
                e != null && e.isOpen ? () => unawaited(_convert(e)) : null,
          ),
        ToolbarCommand(
          id: 'lost-reasons',
          label: 'Lost reasons',
          icon: Icons.insights_outlined,
          onPressed: () => unawaited(_lostReasons()),
        ),
      ],
    );
  }

  Widget _details(Enquiry e) {
    final ThemeData theme = Theme.of(context);
    Widget fact(String label, String value) => value.isEmpty
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                  width: 110,
                  child: Text(label, style: theme.textTheme.bodySmall)),
              Expanded(child: Text(value, style: theme.textTheme.bodyMedium)),
            ]),
          );
    return SingleChildScrollView(
      key: const ValueKey('enquiry-details'),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child:
                  Text(e.enquiryNumber, style: theme.textTheme.titleMedium),
            ),
            StatusBadge.fromStatus(e.status),
          ]),
          Text(e.buyer, style: theme.textTheme.bodySmall),
          const SizedBox(height: AppSpacing.md),
          fact('Contact', e.prospectName),
          fact('Phone', e.prospectPhone),
          fact('Email', e.prospectEmail),
          fact('City', e.prospectCity),
          fact('Source', _labelOf(enquirySources, e.source)),
          fact('Expected value', _money(e.expectedValue)),
          fact('Expected close', e.expectedCloseOn ?? ''),
          fact('Next follow-up', e.nextFollowUpOn ?? ''),
          if (e.lostReason != null)
            fact(
              'Lost because',
              [
                _labelOf(enquiryLostReasons, e.lostReason!),
                if (e.lostRemarks.isNotEmpty) e.lostRemarks,
              ].join(' · '),
            ),
          if (e.quotationId != null) fact('Quotation', e.quotationId!),
          fact('Remarks', e.remarks),
          const SizedBox(height: AppSpacing.md),
          Text('Lines', style: theme.textTheme.titleSmall),
          if (e.lines.isEmpty)
            Text('Nothing listed.', style: theme.textTheme.bodySmall)
          else
            for (final EnquiryLine line in e.lines)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      '${line.label} × ${line.quantity}',
                      style: theme.textTheme.bodySmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (line.expectedPrice != null)
                    Text(_money(line.expectedPrice!),
                        style: theme.textTheme.bodySmall),
                ]),
              ),
          const SizedBox(height: AppSpacing.md),
          Text('Follow-ups', style: theme.textTheme.titleSmall),
          if (e.followUps.isEmpty)
            Text('None yet.', style: theme.textTheme.bodySmall)
          else
            for (final EnquiryFollowUp f in e.followUps)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text(
                  [
                    f.followedOn,
                    f.note,
                    if (f.nextFollowUpOn != null) 'next ${f.nextFollowUpOn}',
                  ].join(' · '),
                  style: theme.textTheme.bodySmall,
                ),
              ),
        ],
      ),
    );
  }

  late final ColumnChoice<Enquiry> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'enquiries.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.enquiryNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date', priority: 2),
        cell: (item) => item.enquiryDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'buyer', label: 'Buyer'),
        cell: (item) => item.buyer,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'source', label: 'Source', priority: 2),
        cell: (item) => _labelOf(enquirySources, item.source),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'value', label: 'Expected value', numeric: true),
        cell: (item) => _money(item.expectedValue),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'follow-up', label: 'Next follow-up', priority: 2),
        cell: (item) => item.nextFollowUpOn ?? '',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => _words(item.status),
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    final List<Enquiry> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _dueOnly ? 'No follow-ups due' : 'No enquiries yet',
        message: _dueOnly
            ? 'Nothing is waiting for a call today.'
            : (_mayCreate
                ? 'Record what a prospect asked for with New.'
                : 'Recording one needs the create quotations permission.'),
      );
    }
    return EnterpriseDataGrid<Enquiry>(
      items: rows,
      total: rows.length,
      pageOffset: 0,
      rowsPerPage: rows.length,
      availableRowsPerPage: [rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: _choose,
      onOpen: _choose,
      onPageChanged: (_) {},
    );
  }
}

Future<DateTime?> _pickDay(BuildContext context, DateTime initial) =>
    showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );

/// Record a contact with the buyer: pops the updated [Enquiry]; stays open
/// with the server's message on a refusal.
class LogFollowUpDialog extends StatefulWidget {
  const LogFollowUpDialog({super.key, required this.api, required this.enquiry});

  final ApiClient api;
  final Enquiry enquiry;

  @override
  State<LogFollowUpDialog> createState() => _LogFollowUpDialogState();
}

class _LogFollowUpDialogState extends State<LogFollowUpDialog>
    with SaveInDialog {
  final TextEditingController _note = TextEditingController();
  DateTime _on = DateTime.now();
  DateTime? _next;
  String? _problem;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  void _save() {
    if (_note.text.trim().isEmpty) {
      setState(() => _problem = 'Say what was discussed.');
      return;
    }
    setState(() => _problem = null);
    unawaited(saveAndClose<Enquiry>(
      () => widget.api.logEnquiryFollowUp(widget.enquiry.id, <String, dynamic>{
        'followed_on': _iso(_on),
        'note': _note.text.trim(),
        'next_follow_up_on': _next == null ? null : _iso(_next!),
      }),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Follow-up on ${widget.enquiry.enquiryNumber}'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Row(children: [
                Expanded(
                  child: InkWell(
                    key: const ValueKey('followup-date'),
                    onTap: saving
                        ? null
                        : () async {
                            final DateTime? d = await _pickDay(context, _on);
                            if (d != null) setState(() => _on = d);
                          },
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Spoke on'),
                      child: Text(_iso(_on)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: InkWell(
                    key: const ValueKey('followup-next'),
                    onTap: saving
                        ? null
                        : () async {
                            final DateTime? d =
                                await _pickDay(context, _next ?? _on);
                            if (d != null) setState(() => _next = d);
                          },
                    child: InputDecorator(
                      decoration:
                          const InputDecoration(labelText: 'Call again on'),
                      child: Text(_next == null ? 'Not set' : _iso(_next!)),
                    ),
                  ),
                ),
              ]),
              TextField(
                key: const ValueKey('followup-note'),
                controller: _note,
                enabled: !saving,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Note'),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('followup-problem'),
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
          key: const ValueKey('followup-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Log follow-up'),
        ),
      ],
    );
  }
}

/// Record why the enquiry did not become a sale: pops the updated [Enquiry];
/// stays open with the server's message on a refusal.
class MarkLostDialog extends StatefulWidget {
  const MarkLostDialog({super.key, required this.api, required this.enquiry});

  final ApiClient api;
  final Enquiry enquiry;

  @override
  State<MarkLostDialog> createState() => _MarkLostDialogState();
}

class _MarkLostDialogState extends State<MarkLostDialog> with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  String? _reason;
  String? _problem;

  @override
  void dispose() {
    _remarks.dispose();
    super.dispose();
  }

  void _save() {
    if (_reason == null) {
      setState(() => _problem = 'Choose why it was lost.');
      return;
    }
    setState(() => _problem = null);
    final String remarks = _remarks.text.trim();
    unawaited(saveAndClose<Enquiry>(
      () => widget.api.markEnquiryLost(widget.enquiry.id, <String, dynamic>{
        'reason': _reason,
        'remarks': remarks.isEmpty ? null : remarks,
      }),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Mark ${widget.enquiry.enquiryNumber} lost'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            DropdownButtonFormField<String>(
              key: const ValueKey('lost-reason'),
              isExpanded: true,
              initialValue: _reason,
              decoration: const InputDecoration(labelText: 'Reason'),
              items: [
                for (final (String code, String label) in enquiryLostReasons)
                  DropdownMenuItem<String>(value: code, child: Text(label)),
              ],
              onChanged: saving ? null : (id) => setState(() => _reason = id),
            ),
            TextField(
              key: const ValueKey('lost-remarks'),
              controller: _remarks,
              enabled: !saving,
              decoration: const InputDecoration(labelText: 'Remarks'),
            ),
            if (_problem != null)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text(_problem!,
                    key: const ValueKey('lost-problem'),
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('lost-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Mark lost'),
        ),
      ],
    );
  }
}

/// Raise the quotation from an enquiry: pops the updated [Enquiry]; stays
/// open with the server's message on a refusal (an unmatched line, say).
class ConvertEnquiryDialog extends StatefulWidget {
  const ConvertEnquiryDialog(
      {super.key, required this.api, required this.enquiry});

  final ApiClient api;
  final Enquiry enquiry;

  @override
  State<ConvertEnquiryDialog> createState() => _ConvertEnquiryDialogState();
}

class _ConvertEnquiryDialogState extends State<ConvertEnquiryDialog>
    with SaveInDialog {
  final TextEditingController _code = TextEditingController();
  List<WarehouseRecord> _warehouses = const [];
  String? _warehouseId;
  DateTime _quotationDate = DateTime.now();
  late DateTime _validUntil = DateTime.now().add(const Duration(days: 30));
  String _customerType = 'BUSINESS';
  String? _loadNote;
  String? _problem;

  bool get _isProspect => widget.enquiry.customerId == null;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<WarehouseRecord> found = await fetchAllPages<WarehouseRecord>(
        (int page) =>
            widget.api.warehouses(page: page, pageSize: maxApiPageSize),
      );
      if (!mounted) return;
      setState(() {
        _warehouses = found;
        _warehouseId = preferredWarehouseId(found,
            branchId: widget.enquiry.branchId);
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loadNote = error.message);
    }
  }

  void _save() {
    if (_warehouseId == null) {
      setState(() => _problem = 'Choose the warehouse the quotation ships from.');
      return;
    }
    if (_validUntil.isBefore(_quotationDate)) {
      setState(() => _problem = 'The quotation cannot expire before its date.');
      return;
    }
    setState(() => _problem = null);
    final String code = _code.text.trim();
    unawaited(saveAndClose<Enquiry>(
      () => widget.api.convertEnquiry(widget.enquiry.id, <String, dynamic>{
        'warehouse_id': _warehouseId,
        'quotation_date': _iso(_quotationDate),
        'valid_until': _iso(_validUntil),
        'customer_type': _customerType,
        'customer_code': _isProspect && code.isNotEmpty ? code : null,
      }),
    ));
  }

  Widget _day(String key, String label, DateTime value, ValueChanged<DateTime> set) =>
      InkWell(
        key: ValueKey(key),
        onTap: saving
            ? null
            : () async {
                final DateTime? d = await _pickDay(context, value);
                if (d != null) setState(() => set(d));
              },
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(_iso(value)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Quote ${widget.enquiry.enquiryNumber}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_loadNote != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_loadNote!,
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
              Text(
                _isProspect
                    ? 'This raises a draft quotation for ${widget.enquiry.buyer} '
                        'and makes them a customer. Every line must be matched '
                        'to a product first.'
                    : 'This raises a draft quotation for '
                        '${widget.enquiry.buyer}.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                key: const ValueKey('convert-warehouse'),
                isExpanded: true,
                initialValue: _warehouseId,
                decoration: const InputDecoration(labelText: 'Warehouse'),
                items: [
                  for (final WarehouseRecord w in _warehouses)
                    DropdownMenuItem<String>(
                      value: w.id,
                      child: Text(w.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged:
                    saving ? null : (id) => setState(() => _warehouseId = id),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                    child: _day('convert-date', 'Quotation date',
                        _quotationDate, (d) => _quotationDate = d)),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                    child: _day('convert-valid', 'Valid until', _validUntil,
                        (d) => _validUntil = d)),
              ]),
              if (_isProspect) ...[
                const SizedBox(height: AppSpacing.md),
                DropdownButtonFormField<String>(
                  key: const ValueKey('convert-customer-type'),
                  isExpanded: true,
                  initialValue: _customerType,
                  decoration:
                      const InputDecoration(labelText: 'Customer type'),
                  items: const [
                    DropdownMenuItem<String>(
                        value: 'BUSINESS', child: Text('Business')),
                    DropdownMenuItem<String>(
                        value: 'INDIVIDUAL', child: Text('Individual')),
                  ],
                  onChanged: saving
                      ? null
                      : (type) => setState(
                          () => _customerType = type ?? _customerType),
                ),
                TextField(
                  key: const ValueKey('convert-customer-code'),
                  controller: _code,
                  enabled: !saving,
                  decoration: const InputDecoration(
                    labelText: 'Customer code',
                    helperText: 'Blank takes the next one in the firm’s series.',
                  ),
                ),
              ],
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('convert-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('convert-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Working…' : 'Raise quotation'),
        ),
      ],
    );
  }
}

/// Lost enquiries by reason for a date range: how many and how much.
class LostReasonsDialog extends StatefulWidget {
  const LostReasonsDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<LostReasonsDialog> createState() => _LostReasonsDialogState();
}

class _LostReasonsDialogState extends State<LostReasonsDialog> {
  late DateTime _from = DateTime(DateTime.now().year, DateTime.now().month, 1)
      .subtract(const Duration(days: 90));
  DateTime _to = DateTime.now();
  List<EnquiryLostRow> _rows = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<EnquiryLostRow> rows =
          await widget.api.enquiryLostReport(_iso(_from), _iso(_to));
      if (!mounted) return;
      setState(() {
        _rows = rows;
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

  Widget _day(String key, String label, DateTime value, bool from) => InkWell(
        key: ValueKey(key),
        onTap: () async {
          final DateTime? d = await _pickDay(context, value);
          if (d == null) return;
          setState(() => from ? _from = d : _to = d);
          unawaited(_load());
        },
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(_iso(value)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Why enquiries were lost'),
      content: SizedBox(
        width: 520,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Expanded(child: _day('lost-from', 'From', _from, true)),
              const SizedBox(width: AppSpacing.md),
              Expanded(child: _day('lost-to', 'To', _to, false)),
            ]),
            const SizedBox(height: AppSpacing.md),
            if (_loading)
              const Center(child: CircularProgressIndicator())
            else if (_error != null)
              Text(_error!, style: TextStyle(color: theme.colorScheme.error))
            else if (_rows.isEmpty)
              const Text('Nothing was lost in this period.')
            else
              for (final EnquiryLostRow row in _rows)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    Expanded(
                        child: Text(_labelOf(enquiryLostReasons, row.reason))),
                    SizedBox(
                      width: 60,
                      child: Text('${row.count}', textAlign: TextAlign.end),
                    ),
                    SizedBox(
                      width: 120,
                      child: Text(_money(row.expectedValue),
                          textAlign: TextAlign.end),
                    ),
                  ]),
                ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
      ],
    );
  }
}
