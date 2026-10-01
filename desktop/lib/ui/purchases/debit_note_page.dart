// Debit notes: a claim on a supplier without goods going back.
//
// A purchase return is the other case -- goods leave and stock moves. This
// screen covers a price difference found after the bill or a short supply
// nobody disputes, and it takes the input tax off at the rate the bill
// charged. Phase 2 only: it is raised on its own document screen.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/debit_note.dart';
import '../../models/entities.dart';
import '../../models/vendor.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

part 'debit_note_editor_phase2.dart';

/// List the firm's debit notes, raise one, approve it or take it back.
class DebitNotePage extends StatefulWidget {
  const DebitNotePage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;

  /// Where the grid's chosen columns are remembered.
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<DebitNotePage> createState() => _DebitNotePageState();
}

class _DebitNotePageState extends State<DebitNotePage> {
  List<DebitNoteRecord> _notes = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  /// Search (number, vendor or bill) and the Period, as the other lists.
  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from =>
      _period.from == null ? null : DatePeriod.iso(_period.from!);
  String? get _to => _period.to == null ? null : DatePeriod.iso(_period.to!);

  Widget _periodFilter() => DateRangeFilter(
        value: _period,
        onChanged: (period) {
          setState(() => _period = period);
          unawaited(_load());
        },
      );

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  bool get _mayView => widget.permissions.hasPermission('DEBIT_NOTE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('DEBIT_NOTE_MANAGE');

  /// Approving moves what the firm owes and the input tax it claims, so it is
  /// its own permission; the screen hides the action rather than letting the
  /// server refuse after the click.
  bool get _mayApprove =>
      widget.permissions.hasPermission('DEBIT_NOTE_APPROVE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<DebitNoteRecord> rows = await fetchAllPages<DebitNoteRecord>(
        (page) => widget.api.debitNotes(
          page: page,
          search: _search.text.trim(),
          debitNoteFrom: _from,
          debitNoteTo: _to,
        ),
      );
      if (!mounted) return;
      setState(() {
        _notes = rows;
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

  Future<void> _raise() async {
    final bool? saved = await showDocument<bool>(
      context,
      title: 'New debit note',
      builder: (_) => DebitNoteDialog(api: widget.api),
    );
    if (saved == true) await _load();
  }

  Future<void> _act(
    DebitNoteRecord note,
    Future<DebitNoteRecord> Function() action,
    String done,
  ) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${note.debitNoteNumber} — $done',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  /// A cancel is explained afterwards, so it asks why first.
  Future<void> _cancel(DebitNoteRecord note) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${note.debitNoteNumber}',
      explanation: 'Whatever the note did is put back. The reason is kept '
          'on the note.',
      confirmLabel: 'Cancel note',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    await _act(
      note,
      () => widget.api.cancelDebitNote(
        note.id,
        reason,
        expectedVersion: note.version,
      ),
      'cancelled. Whatever it did has been put back.',
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Debit notes are raised against one firm’s supplier bills.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see debit notes',
        message: 'Reading them needs the view debit notes permission.',
      );
    }
    final DebitNoteRecord? picked = _selectedNote;
    return ManagementWorkspaceLayout(
      notice: DebitNoteNotice.text,
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number, vendor or bill',
        onSearch: (_) => unawaited(_load()),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.debitNoteNumber,
              party: picked.vendorName,
              status: picked.status,
              total: picked.totalAmount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _notes.length,
        selected: _selectedId != null,
        message: 'Approving takes the input tax off.',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(_error!, style: const TextStyle(color: Colors.redAccent)),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _grid()),
      ],
    );
  }

  /// The picked note, while it is still on the list.
  DebitNoteRecord? get _selectedNote =>
      _notes.where((note) => note.id == _selectedId).firstOrNull;

  /// Period and Columns after the search, Refresh, "+ New" last; Approve and
  /// Cancel go on the bar when a note is picked.
  WorkspaceToolbar _toolbar(DebitNoteRecord? selected) {
    return WorkspaceToolbar(
      trailing: [
        _periodFilter(),
        ColumnsButton(
          onPressed: () async {
            if (await _columns.choose(context) && mounted) setState(() {});
          },
        ),
      ],
      actions: [
        ToolbarAction.view,
        ToolbarAction.refresh,
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) =>
          action != ToolbarAction.view || selected != null,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_raise());
          case ToolbarAction.view:
            if (selected != null) unawaited(_openNote(selected));
          default:
            unawaited(_load());
        }
      },
      commands: [
        ToolbarCommand(
          id: 'approve',
          label: 'Approve',
          icon: Icons.check_circle_outline,
          onPressed: selected != null && selected.isDraft && _mayApprove
              ? () => _act(
                    selected,
                    () => widget.api.approveDebitNote(
                      selected.id,
                      expectedVersion: selected.version,
                    ),
                    'approved. The claim and the tax are on the ledger.',
                  )
              : null,
        ),
        ToolbarCommand(
          id: 'cancel',
          label: 'Cancel',
          icon: Icons.cancel_outlined,
          onPressed: selected != null &&
                  (selected.isDraft || selected.isApproved) &&
                  _mayApprove
              ? () => unawaited(_cancel(selected))
              : null,
        ),
      ],
    );
  }

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC.
  late final ColumnChoice<DebitNoteRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'debit-notes.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.debitNoteNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.debitNoteDate,
        shownByDefault: true,
      ),
      // Whose bill it is; kept at any width.
      ChoosableColumn(
        column: const GridColumn(key: 'vendor', label: 'Vendor', priority: 1),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'bill', label: 'Bill'),
        cell: (item) => item.purchaseInvoiceNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reason', label: 'Reason'),
        cell: (item) => item.reasonLabel,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'taxable', label: 'Taxable Value', numeric: true),
        cell: (item) => _money(item.taxableAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => _money(item.taxAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Total', numeric: true),
        cell: (item) => _money(item.totalAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reference', label: 'Reference'),
        cell: (item) => item.referenceNumber,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  /// Read one note: the bill it claims on, why, and each line's claim.
  /// Approve and Cancel stay on the bar above the grid, so this only reads.
  Future<void> _openNote(DebitNoteRecord note) async {
    setState(() => _selectedId = note.id);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final TextStyle? small = Theme.of(dialogContext).textTheme.bodySmall;
        return AlertDialog(
          title: Row(children: [
            Expanded(child: Text(note.debitNoteNumber)),
            StatusBadge.fromStatus(note.status),
          ]),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(note.vendorName),
                  Text(
                    'Against ${note.purchaseInvoiceNumber} · '
                    '${note.debitNoteDate} · ${note.reasonLabel}',
                    style: small,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  for (final DebitNoteLineRecord line in note.lines)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        '${line.productName.isEmpty ? line.description : line.productName}'
                        ' — ${_money(line.taxableAmount)} before tax',
                        style: small,
                      ),
                    ),
                  const Divider(),
                  Text(
                    '${_money(note.taxableAmount)} + '
                    '${_money(note.taxAmount)} tax = '
                    '${_money(note.totalAmount)} claimed',
                  ),
                  if (note.remarks.isNotEmpty) Text(note.remarks, style: small),
                  if (note.cancelReason.isNotEmpty)
                    Text('Cancelled: ${note.cancelReason}', style: small),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  Widget _grid() {
    if (_notes.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No debit notes yet',
        message: _mayManage
            ? 'Raise one against an approved supplier bill to claim a price '
                'difference or a short supply.'
            : 'Raising one needs the manage debit notes permission.',
      );
    }
    return EnterpriseDataGrid<DebitNoteRecord>(
      items: _notes,
      total: _notes.length,
      pageOffset: 0,
      rowsPerPage: _notes.length,
      availableRowsPerPage: [_notes.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedId = row.id),
      onOpen: (row) => unawaited(_openNote(row)),
      onPageChanged: (_) {},
    );
  }
}

/// Show money at two decimals; the API answers at four.
String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// Say plainly which document does what, because choosing wrong is silent.
class DebitNoteNotice {
  const DebitNoteNotice._();

  /// What the notice says; phase 2 shows it behind the page line's (i).
  static const String text =
      'Use a debit note when the money changes and the goods do not '
      '— a price difference found after the bill, or a short supply. It '
      'takes the input tax off at the rate the bill charged. Goods actually '
      'going back are a purchase return, which moves stock as well.';
}

/// Raise one debit note against an approved supplier bill.
class DebitNoteDialog extends StatefulWidget {
  const DebitNoteDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<DebitNoteDialog> createState() => _DebitNoteDialogState();
}

class _DebitNoteDialogState extends State<DebitNoteDialog> {
  final TextEditingController _remarks = TextEditingController();
  final TextEditingController _reference = TextEditingController();

  String _reason = 'PRICE_DIFFERENCE';
  String? _error;
  bool _saving = false;
  bool _loading = true;

  /// The supplier, then one of their bills, then that bill's lines.
  List<Vendor> _vendors = const <Vendor>[];
  String _vendorId = '';
  List<Json> _bills = const <Json>[];
  String _billId = '';
  bool _loadingBills = false;
  List<DebitNoteClaimableLine> _lines = const <DebitNoteClaimableLine>[];
  bool _loadingLines = false;

  /// What is typed on each bill line: the claim before tax and the quantity
  /// short, keyed by the bill line's id.
  final Map<String, String> _amounts = <String, String>{};
  final Map<String, String> _quantities = <String, String>{};
  DebitNoteRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;

  void _setState(VoidCallback change) => setState(change);

  @override
  void initState() {
    super.initState();
    unawaited(_loadVendors());
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _remarks.dispose();
    _reference.dispose();
    super.dispose();
  }

  Future<void> _loadVendors() async {
    try {
      final List<Vendor> vendors = await fetchAllPages<Vendor>(
        (page) => widget.api.vendors(page: page),
      );
      if (!mounted) return;
      setState(() {
        _vendors = vendors;
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

  /// The supplier's bills a claim can stand on: approved, or closed once
  /// paid. A draft was never owed and a cancelled bill is owed nothing.
  Future<void> _loadBills(String vendorId) async {
    setState(() {
      _vendorId = vendorId;
      _bills = const <Json>[];
      _billId = '';
      _lines = const <DebitNoteClaimableLine>[];
      _amounts.clear();
      _quantities.clear();
      _preview = null;
      _current = 0;
      _loadingBills = true;
      _error = null;
    });
    try {
      final List<Json> bills = <Json>[];
      for (final String status in const <String>['APPROVED', 'CLOSED']) {
        final Json response = await widget.api.documentPage(
          'purchase-invoices',
          pageSize: 100,
          additionalQuery: {'vendor_id': vendorId, 'status': status},
        );
        final dynamic data = response['data'];
        for (final dynamic row in data is List ? data : const []) {
          if (row is Map) bills.add(Map<String, dynamic>.from(row));
        }
      }
      if (!mounted || _vendorId != vendorId) return;
      setState(() {
        _bills = bills;
        _loadingBills = false;
      });
    } on ApiException catch (error) {
      if (!mounted || _vendorId != vendorId) return;
      setState(() {
        _error = error.message;
        _loadingBills = false;
      });
    }
  }

  Future<void> _loadLines(String billId) async {
    setState(() {
      _billId = billId;
      _lines = const <DebitNoteClaimableLine>[];
      _amounts.clear();
      _quantities.clear();
      _preview = null;
      _current = 0;
      _loadingLines = true;
      _error = null;
    });
    try {
      final List<DebitNoteClaimableLine> lines =
          await widget.api.debitNoteClaimableLines(billId);
      if (!mounted || _billId != billId) return;
      setState(() {
        _lines = lines;
        _loadingLines = false;
      });
    } on ApiException catch (error) {
      if (!mounted || _billId != billId) return;
      setState(() {
        _error = error.message;
        _loadingLines = false;
      });
    }
  }

  /// Price the note again once the typing pauses; only the latest answer
  /// lands. A note with nothing on it is not sent.
  void _schedulePreview() {
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      final Json? draft = _payload();
      if (draft == null || !mounted) {
        if (mounted) setState(() => _preview = null);
        return;
      }
      final int serial = ++_previewSerial;
      try {
        final DebitNoteRecord priced = await widget.api.previewDebitNote(draft);
        if (!mounted || serial != _previewSerial) return;
        setState(() {
          _preview = priced;
          _error = null;
        });
      } on ApiException catch (error) {
        // A line claimed past what is left on it is refused here, before the
        // note is raised; say so rather than keep stale figures.
        if (!mounted || serial != _previewSerial) return;
        setState(() {
          _preview = null;
          _error = refusalMessage(error);
        });
      }
    });
  }

  static String _today() {
    final DateTime now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

  /// The note as the server is sent it: every line with an amount on it, and
  /// only the fields the server declares.
  Json? _payload() {
    if (_billId.isEmpty) return null;
    final List<DebitNoteClaimableLine> claiming = [
      for (final DebitNoteClaimableLine line in _lines)
        if (_number(_amounts[line.purchaseInvoiceLineId] ?? '') > 0) line,
    ];
    if (claiming.isEmpty) return null;
    return <String, dynamic>{
      'purchase_invoice_id': _billId,
      'debit_note_date': _today(),
      'reason': _reason,
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      'lines': [
        for (int i = 0; i < claiming.length; i++)
          <String, dynamic>{
            'purchase_invoice_line_id': claiming[i].purchaseInvoiceLineId,
            'line_number': i + 1,
            if (_number(_quantities[claiming[i].purchaseInvoiceLineId] ?? '') >
                0)
              'quantity': _quantities[claiming[i].purchaseInvoiceLineId]!.trim(),
            // The tax comes off at the rate the bill line charged, which is
            // why nothing here names one.
            'taxable_amount':
                _amounts[claiming[i].purchaseInvoiceLineId]!.trim(),
          },
      ],
    };
  }

  double _number(String value) => double.tryParse(value.trim()) ?? 0;

  /// Runs the save itself and stays open with the server's message on a
  /// refusal, so nothing typed is lost.
  Future<void> _save() async {
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = 'Enter what is being claimed, before tax, on '
          'at least one line.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createDebitNote(payload);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = refusalMessage(error);
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => _phase2Page(context);
}
