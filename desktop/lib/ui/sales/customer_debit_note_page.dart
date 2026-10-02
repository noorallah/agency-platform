// Debit notes to customers: more charged on a sale already invoiced -- a price
// raised after billing, a line under-billed, a charge added later.
//
// It is owed on the invoice it names and taxed at that invoice line's rate, so
// the output tax follows the extra charge. Unlike a credit note nothing caps
// it: a line can take any positive amount, and the invoice line's own value is
// shown for reference only.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bulk_action.dart';
import '../../models/customer_debit_note.dart';
import '../../models/entities.dart';
import '../../models/sales_return.dart';
import '../workspace/bulk_action.dart';
import '../workspace/desktop_framework.dart';
import 'note_einvoice_dialog.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';

part 'customer_debit_note_editor_phase2.dart';

/// List the firm's debit notes, raise one, approve it or take it back.
class CustomerDebitNotePage extends StatefulWidget {
  const CustomerDebitNotePage({
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
  State<CustomerDebitNotePage> createState() => _CustomerDebitNotePageState();
}

class _CustomerDebitNotePageState extends State<CustomerDebitNotePage> {
  List<CustomerDebitNoteRecord> _notes = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  /// The rows ticked for a bulk approve (backlog 56 A). There is no bulk
  /// cancel for debit notes.
  Set<String> _ticked = <String>{};

  /// Search (number or customer) and the Period, on phase 2's page line
  /// (owner, 2026-09-27), as the other sales lists.
  final TextEditingController _search = TextEditingController();
  DatePeriod _period = const DatePeriod.all();

  String? get _from => _period.from == null ? null : DatePeriod.iso(_period.from!);
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

  bool get _mayView => widget.permissions.hasPermission('CUSTOMER_DEBIT_NOTE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('CUSTOMER_DEBIT_NOTE_MANAGE');

  /// Approving puts output tax on the firm's return, so it is
  /// its own permission — the same split as accruing a commission payout
  /// versus paying one. The screen hides the action rather than letting the
  /// server refuse after the click.
  bool get _mayApprove =>
      widget.permissions.hasPermission('CUSTOMER_DEBIT_NOTE_APPROVE');

  bool get _mayEInvoice => widget.permissions.hasPermission('EINVOICE_VIEW');
  bool get _mayEInvoiceManage =>
      widget.permissions.hasPermission('EINVOICE_MANAGE');

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
      final List<CustomerDebitNoteRecord> rows =
          await fetchAllPages<CustomerDebitNoteRecord>(
        (page) => widget.api.customerDebitNotes(
          page: page,
          search: _search.text.trim(),
          debitNoteFrom: _from,
          debitNoteTo: _to,
        ),
      );
      if (!mounted) return;
      setState(() {
        _notes = rows;
        _ticked =
            _ticked.where((id) => rows.any((row) => row.id == id)).toSet();
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

  /// More than one row ticked: the bar names the batch and offers the bulk
  /// approve instead of the one row's steps.
  bool get _bulkMode => _ticked.length > 1;

  List<CustomerDebitNoteRecord> get _tickedRows =>
      _notes.where((row) => _ticked.contains(row.id)).toList();

  SelectionSummary _bulkSummary() {
    double total = 0;
    for (final CustomerDebitNoteRecord row in _tickedRows) {
      total += double.tryParse(row.totalAmount) ?? 0;
    }
    return SelectionSummary(
      title: '${_ticked.length} selected',
      detail: indianAmount(total, full: true),
      onClear: () => setState(() => _ticked = <String>{}),
    );
  }

  /// The one bulk action, behind the permission the single approve takes.
  List<ToolbarCommand> _bulkCommands() => [
        ToolbarCommand(
          id: 'bulk-approve',
          label: 'Approve selected',
          icon: Icons.check_circle_outline,
          onPressed: _loading || !_mayApprove
              ? null
              : () => unawaited(_bulkApprove()),
        ),
      ];

  Future<void> _bulkApprove() async {
    final List<BulkRow> rows = [
      for (final CustomerDebitNoteRecord row in _tickedRows)
        (id: row.id, version: row.version),
    ];
    await runBulkAction(
      context,
      verb: 'Approved',
      rows: rows,
      send: widget.api.bulkApproveCustomerDebitNotes,
    );
    if (!mounted) return;
    setState(() => _ticked = <String>{});
    await _load();
  }

  Future<void> _raise() async {
    // Phase 2 raises on its own screen, every invoice line on show; phase 1
    // keeps its dialog.
    final bool? saved = Phase2Scope.of(context)
        ? await showDocument<bool>(
            context,
            title: 'New debit note',
            builder: (_) => CustomerDebitNoteDialog(api: widget.api),
          )
        : await showDialog<bool>(
            context: context,
            builder: (context) => CustomerDebitNoteDialog(api: widget.api),
          );
    if (saved == true) await _load();
  }

  /// The note's e-invoice: its IRN where it has one, Register where it has
  /// not (backlog 77 row 4).
  Future<void> _eInvoice(CustomerDebitNoteRecord note) async {
    final bool changed = await showNoteEInvoice(
      context,
      widget.api,
      kind: debitNotesEInvoiceKind,
      noteId: note.id,
      noteNumber: note.debitNoteNumber,
      mayManage: _mayEInvoiceManage,
    );
    if (changed && mounted) await _load();
  }

  Future<void> _act(
    CustomerDebitNoteRecord note,
    Future<CustomerDebitNoteRecord> Function() action,
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

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Debit notes are raised against one firm’s invoices.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see debit notes',
        message: 'Reading them needs the view debit notes permission.',
      );
    }
    return ManagementWorkspaceLayout(
      notice: CustomerDebitNoteNotice.text,
      // Phase 2: Refresh as the line's icon and "+ New" last, as every list.
      toolbar: Phase2Scope.of(context)
          ? _phase2Toolbar()
          : Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (_mayManage)
            FilledButton.icon(
              onPressed: _raise,
              icon: const Icon(Icons.add),
              label: const Text('Raise debit note'),
            ),
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
      // Phase 2: searchable by number or customer and narrowed by date, as
      // every sales list (owner, 2026-09-27) -- the list grows all year.
      searchPanel: Phase2Scope.of(context)
          ? SearchFilterPanel(
              controller: _search,
              hintText: 'Search number or customer',
              onSearch: (_) => unawaited(_load()),
            )
          : const SizedBox.shrink(),
      // Option C (owner, 2026-09-27): the note's steps on a bar that names
      // it, above the grid.
      selectionBar: true,
      selection: _bulkMode
          ? _bulkSummary()
          : _selectedNote == null
          ? null
          : SelectionSummary.document(
              number: _selectedNote!.debitNoteNumber,
              party: _selectedNote!.customerName,
              status: _selectedNote!.status,
              total: _selectedNote!.totalAmount,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _notes.length,
        selected: _selectedId != null,
        message: 'Approving adds the extra charge and its output tax.',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CustomerDebitNoteNotice(),
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
  CustomerDebitNoteRecord? get _selectedNote =>
      _notes.where((note) => note.id == _selectedId).firstOrNull;

  /// Phase 2: Period and Columns after the search, Refresh, "+ New" last;
  /// Approve and Cancel go on the bar when a note is picked.
  WorkspaceToolbar _phase2Toolbar() {
    final CustomerDebitNoteRecord? selected = _selectedNote;
    return WorkspaceToolbar(
      // Period right after the search, then Columns (owner).
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
          action != ToolbarAction.view || (selected != null && !_bulkMode),
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
      commands: _bulkMode
          ? _bulkCommands()
          : [
        ToolbarCommand(
          id: 'approve',
          label: 'Approve',
          icon: Icons.check_circle_outline,
          onPressed: selected != null && selected.isDraft && _mayApprove
              ? () => _act(
                    selected,
                    () => widget.api.approveCustomerDebitNote(
                      selected.id,
                      expectedVersion: selected.version,
                    ),
                    'approved. The charge and the tax are on the ledger.',
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
              ? () => _act(
                    selected,
                    () => widget.api.cancelCustomerDebitNote(
                      selected.id,
                      expectedVersion: selected.version,
                    ),
                    'cancelled. Whatever it did has been put back.',
                  )
              : null,
        ),
        ToolbarCommand(
          id: 'einvoice',
          label: 'E-invoice',
          icon: Icons.qr_code_2_outlined,
          onPressed: selected != null && selected.isApproved && _mayEInvoice
              ? () => unawaited(_eInvoice(selected))
              : null,
        ),
      ],
    );
  }

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<CustomerDebitNoteRecord> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'customer-debit-notes.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.debitNoteNumber,
        required: true,
      ),
      // Whose debit it is; kept at any width.
      ChoosableColumn(
        column:
            const GridColumn(key: 'customer', label: 'Customer', priority: 1),
        cell: (item) => item.customerName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date'),
        cell: (item) => item.debitNoteDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'invoice', label: 'Invoice'),
        cell: (item) => item.salesInvoiceNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'reason', label: 'Reason'),
        cell: (item) => item.reasonLabel,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'taxable', label: 'Taxable Value', numeric: true),
        cell: (item) => item.taxableAmount,
      ),
      // The tax is the whole reason this document exists rather than a
      // receivable adjustment, so it is shown by default.
      ChoosableColumn(
        column: const GridColumn(key: 'tax', label: 'Tax', numeric: true),
        cell: (item) => item.taxAmount,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Charged'),
        cell: (item) => item.totalAmount,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  /// Read one note: the invoice it adds to, why, and each line's charge.
  /// Approve and Cancel stay on the bar above the grid, so this only reads.
  Future<void> _openNote(CustomerDebitNoteRecord note) async {
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
                  Text(note.customerName),
                  Text(
                    'Against ${note.salesInvoiceNumber} · ${note.debitNoteDate}'
                    ' · ${note.reasonLabel}',
                    style: small,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  for (final CustomerDebitNoteLineRecord line in note.lines)
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
                    '${_money(note.totalAmount)} charged',
                  ),
                  if (note.remarks.isNotEmpty) Text(note.remarks, style: small),
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
            ? 'Raise one against an approved invoice to charge a price '
                'raised, a line under-billed or a charge added after the sale.'
            : 'Raising one needs the manage debit notes permission.',
      );
    }
    // Phase 2: the chosen columns, with the steps on the bar rather than in
    // an actions column.
    if (Phase2Scope.of(context)) {
      return EnterpriseDataGrid<CustomerDebitNoteRecord>(
        items: _notes,
        total: _notes.length,
        pageOffset: 0,
        rowsPerPage: _notes.length,
        availableRowsPerPage: [_notes.length],
        selectedId: _selectedId,
        // Ticks, for a bulk approve. A single row is still chosen by
        // clicking it.
        selectedIds: _ticked,
        onSelectionChanged: (ticked) => setState(() => _ticked = ticked),
        columns: _columns.gridColumns,
        id: (row) => row.id,
        cells: _columns.cells,
        onSelect: (row) => setState(() => _selectedId = row.id),
        onOpen: (row) => unawaited(_openNote(row)),
        onPageChanged: (_) {},
      );
    }
    return EnterpriseDataGrid<CustomerDebitNoteRecord>(
      items: _notes,
      total: _notes.length,
      pageOffset: 0,
      rowsPerPage: _notes.length,
      availableRowsPerPage: [_notes.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'number', label: 'Number'),
        GridColumn(key: 'customer', label: 'Customer'),
        GridColumn(key: 'total', label: 'Charged'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'actions', label: ''),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.debitNoteNumber,
        // The invoice is named on the record and in the dialog that raised
        // the note. It is not a column here because every column costs about
        // 230 pixels and a sixth put the row's own actions past the right
        // edge at 1366 -- an Approve nobody can reach without scrolling
        // sideways is one nobody finds.
        row.customerName,
        // The tax is shown beside the total, because it is the whole reason
        // this document exists rather than a receivable adjustment.
        '${_money(row.totalAmount)} (tax ${_money(row.taxAmount)})',
        // The reason rides with the status rather than taking a column of its
        // own: every column costs about 230 pixels, and a seventh put the
        // row's actions past the right edge at 1366, where an Approve nobody
        // can reach without scrolling sideways is one nobody finds.
        '${row.status} · ${row.reasonLabel}',
        '',
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      cellBuilder: (columnIndex, value, row) =>
          columnIndex == 4 ? _actions(row) : Text(value),
    );
  }

  Widget _actions(CustomerDebitNoteRecord row) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (row.isDraft && _mayApprove)
          TextButton(
            onPressed: () => _act(
              row,
              () => widget.api
                  .approveCustomerDebitNote(
                    row.id,
                    expectedVersion: row.version,
                  ),
              'approved. The charge and the tax are on the ledger.',
            ),
            child: const Text('Approve'),
          ),
        if ((row.isDraft || row.isApproved) && _mayApprove)
          TextButton(
            onPressed: () => _act(
              row,
              () => widget.api
                  .cancelCustomerDebitNote(
                    row.id,
                    expectedVersion: row.version,
                  ),
              'cancelled. Whatever it did has been put back.',
            ),
            child: const Text('Cancel'),
          ),
      ],
    );
  }
}


/// Show money at two decimals.
///
/// The API answers at four, which is right for arithmetic and wrong for a
/// column: the extra digits push every later column right, and it was the
/// row's own actions that fell off the edge at 1366.
String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// Say plainly which document does what, because choosing wrong is silent.
class CustomerDebitNoteNotice extends StatelessWidget {
  const CustomerDebitNoteNotice({super.key});

  /// What the notice says; phase 2 shows it behind the page line's (i).
  static const String text =
      'Use a debit note when a customer owes more on a sale already '
      'invoiced — a price raised after billing, a line under-billed, a charge '
      'added later. It is taxed at the rate that invoice line charged, and '
      'it is owed on the invoice it names.';

  @override
  Widget build(BuildContext context) {
    // Phase 2 allows no box above the grid (4.5): the page line's (i) says it.
    if (Phase2Scope.of(context)) return const SizedBox.shrink();
    final ThemeData theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.receipt_long_outlined, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              CustomerDebitNoteNotice.text,
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

/// Raise one debit note against an approved invoice.
class CustomerDebitNoteDialog extends StatefulWidget {
  const CustomerDebitNoteDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<CustomerDebitNoteDialog> createState() => _CustomerDebitNoteDialogState();
}

class _CustomerDebitNoteDialogState extends State<CustomerDebitNoteDialog> {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _remarks = TextEditingController();

  String _reason = 'PRICE_INCREASE';
  String? _error;
  bool _saving = false;
  bool _loading = true;

  /// The invoices that can be debited, and which one is selected. Read from
  /// the same list a sales return offers, filtered to invoices: a debit note
  /// corrects a *bill*, and a delivery note is not one.
  List<ReturnableDocument> _invoices = const <ReturnableDocument>[];
  String _invoiceId = '';

  /// The line the charge lands on. Most corrections are one line; a document
  /// with several offers a choice rather than guessing.
  String _lineId = '';

  /// Phase 2: the charge before tax typed on each invoice line, the note as
  /// the server priced it last, and the line the side panel follows.
  final Map<String, String> _amounts = <String, String>{};
  CustomerDebitNoteRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;

  void _setState(VoidCallback change) => setState(change);

  /// Price the note again once the typing pauses; only the latest answer
  /// lands. A note with nothing on it is not sent.
  void _schedulePreview() {
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      final Json? draft = _phase2Payload();
      if (draft == null || !mounted) {
        if (mounted) setState(() => _preview = null);
        return;
      }
      final int serial = ++_previewSerial;
      try {
        final CustomerDebitNoteRecord priced =
            await widget.api.previewCustomerDebitNote(draft);
        if (!mounted || serial != _previewSerial) return;
        setState(() => _preview = priced);
      } on ApiException catch (error) {
        // A refusal (an invoice no longer approved, say) is shown here,
        // before the note is raised, rather than leaving stale figures.
        if (!mounted || serial != _previewSerial) return;
        setState(() {
          _preview = null;
          _error = error.message;
        });
      }
    });
  }

  ReturnableDocument? get _selected {
    for (final ReturnableDocument row in _invoices) {
      if (row.id == _invoiceId) return row;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _amount.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<ReturnableDocument> all =
          await widget.api.returnableDocuments();
      // Invoices, and only ones that were actually issued. The list behind
      // this is the sales-return picker: the 50 most recent notes and the 50
      // most recent invoices, unfiltered. A delivery note is not a bill and a
      // cancelled invoice charged nobody, so offering either gives a
      // selection with nothing to debit and no word about why -- which is
      // how this screen came to look broken.
      final List<ReturnableDocument> invoices = all
          .where((row) =>
              row.sourceType == SalesReturnSource.salesInvoice &&
              row.status == 'APPROVED' &&
              row.lines.isNotEmpty)
          .toList();
      if (!mounted) return;
      setState(() {
        _invoices = invoices;
        _invoiceId = invoices.isEmpty ? '' : invoices.first.id;
        _lineId = invoices.isEmpty || invoices.first.lines.isEmpty
            ? ''
            : invoices.first.lines.first.id;
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

  Future<void> _save() async {
    if (_invoiceId.isEmpty || _lineId.isEmpty) {
      setState(() => _error = 'Choose the invoice line being debited.');
      return;
    }
    final double? amount = double.tryParse(_amount.text.trim());
    if (amount == null || amount <= 0) {
      setState(() => _error = 'Enter the extra amount to charge, before tax.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createCustomerDebitNote(<String, dynamic>{
        'sales_invoice_id': _invoiceId,
        'debit_note_date': _today(),
        'reason': _reason,
        if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
        'lines': [
          <String, dynamic>{
            'sales_invoice_line_id': _lineId,
            'line_number': 1,
            // The value is the extra charge; the tax is worked out from the
            // rate the invoice charged, which is why nothing here names one.
            'taxable_amount': _amount.text.trim(),
          }
        ],
      });
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  static String _today() {
    final DateTime now = DateTime.now();
    return '${now.year.toString().padLeft(4, '0')}-'
        '${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    // Phase 2: the one-screen note (the documents' approved layout).
    if (Phase2Scope.of(context)) return _phase2Page(context);
    final ThemeData theme = Theme.of(context);
    final ReturnableDocument? invoice = _selected;
    return AlertDialog(
      title: const Text('Raise a debit note'),
      content: SizedBox(
        width: 520,
        child: _loading
            ? const SizedBox(
                height: 120, child: Center(child: CircularProgressIndicator()))
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_invoices.isEmpty)
                      Text(
                        'No approved invoice to debit. A debit note always '
                        'names the supply it adds to, because only that line '
                        'knows the rate its tax was charged at.',
                        style: theme.textTheme.bodySmall,
                      )
                    else ...[
                      DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _invoiceId,
                        decoration: const InputDecoration(
                          labelText: 'Invoice',
                          helperText: 'The supply being added to.',
                        ),
                        items: [
                          for (final ReturnableDocument row in _invoices)
                            DropdownMenuItem<String>(
                              value: row.id,
                              child: Text(
                                row.label,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                        ],
                        onChanged: _saving
                            ? null
                            : (value) => setState(() {
                                  _invoiceId = value ?? _invoiceId;
                                  final ReturnableDocument? chosen = _selected;
                                  _lineId = chosen == null ||
                                          chosen.lines.isEmpty
                                      ? ''
                                      : chosen.lines.first.id;
                                }),
                      ),
                      const SizedBox(height: AppSpacing.md),
                      DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _lineId.isEmpty ? null : _lineId,
                        decoration: const InputDecoration(labelText: 'Line'),
                        items: [
                          for (final ReturnableLine line
                              in invoice?.lines ?? const <ReturnableLine>[])
                            DropdownMenuItem<String>(
                              value: line.id,
                              child: Text(
                                line.description.isEmpty
                                    ? 'Line ${line.lineNumber}'
                                    : line.description,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                        ],
                        onChanged: _saving
                            ? null
                            : (value) =>
                                setState(() => _lineId = value ?? _lineId),
                      ),
                    ],
                    const SizedBox(height: AppSpacing.md),
                    DropdownButtonFormField<String>(
                      isExpanded: true,
                      initialValue: _reason,
                      decoration: const InputDecoration(labelText: 'Reason'),
                      items: const [
                        DropdownMenuItem(
                          value: 'PRICE_INCREASE',
                          child: Text('Price increase', overflow: TextOverflow.ellipsis),
                        ),
                        DropdownMenuItem(
                          value: 'SHORT_BILLED',
                          child: Text('Short billed', overflow: TextOverflow.ellipsis),
                        ),
                        DropdownMenuItem(
                          value: 'ADDITIONAL_CHARGES',
                          child: Text('Additional charges', overflow: TextOverflow.ellipsis),
                        ),
                        DropdownMenuItem(value: 'OTHER', child: Text('Other')),
                      ],
                      onChanged: _saving
                          ? null
                          : (value) =>
                              setState(() => _reason = value ?? _reason),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _amount,
                      enabled: !_saving,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'Charge, before tax',
                        helperText: 'The tax comes off at the rate this '
                            'invoice charged, so it is not entered here.',
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    TextField(
                      controller: _remarks,
                      enabled: !_saving,
                      decoration:
                          const InputDecoration(labelText: 'Remarks'),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: AppSpacing.lg),
                      Text(
                        _error!,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.colorScheme.error),
                      ),
                    ],
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving || _invoices.isEmpty ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Raise'),
        ),
      ],
    );
  }
}
