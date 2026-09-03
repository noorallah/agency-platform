// Credit notes: money credited to a customer without goods coming back.
//
// A sales return is the other case — goods arrive and stock moves. This screen
// covers a rate agreed after invoicing, a discount given later, or a shortfall
// nobody disputes, and it is the only path that **reverses the output tax the
// invoice charged**. The older receivable adjustment on the customer record
// does not, so a firm using that one keeps declaring tax on a price nobody
// paid.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/credit_note.dart';
import '../../models/sales_return.dart';
import '../workspace/desktop_framework.dart';

/// List the firm's credit notes, raise one, approve it or take it back.
class CreditNotePage extends StatefulWidget {
  const CreditNotePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CreditNotePage> createState() => _CreditNotePageState();
}

class _CreditNotePageState extends State<CreditNotePage> {
  List<CreditNoteRecord> _notes = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  bool get _mayView => widget.permissions.hasPermission('CREDIT_NOTE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('CREDIT_NOTE_MANAGE');

  /// Approving reverses tax the firm has declared to the authority, so it is
  /// its own permission — the same split as accruing a commission payout
  /// versus paying one. The screen hides the action rather than letting the
  /// server refuse after the click.
  bool get _mayApprove =>
      widget.permissions.hasPermission('CREDIT_NOTE_APPROVE');

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
      final List<CreditNoteRecord> rows =
          await fetchAllPages<CreditNoteRecord>(
        (page) => widget.api.creditNotes(page: page),
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
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => CreditNoteDialog(api: widget.api),
    );
    if (saved == true) await _load();
  }

  Future<void> _act(
    CreditNoteRecord note,
    Future<CreditNoteRecord> Function() action,
    String done,
  ) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${note.creditNoteNumber} — $done',
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
        message: 'Credit notes are raised against one firm’s invoices.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see credit notes',
        message: 'Reading them needs the view credit notes permission.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (_mayManage)
            FilledButton.icon(
              onPressed: _raise,
              icon: const Icon(Icons.add),
              label: const Text('Raise credit note'),
            ),
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      // A search box over a handful of rows is furniture; the list is short
      // and the number is on every row.
      searchPanel: const SizedBox.shrink(),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _notes.length,
        selected: _selectedId != null,
        message: 'Approving reverses the output tax the invoice charged.',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CreditNoteNotice(),
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(_error!, style: const TextStyle(color: Colors.redAccent)),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _grid()),
      ],
    );
  }

  Widget _grid() {
    if (_notes.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No credit notes yet',
        message: _mayManage
            ? 'Raise one against an approved invoice to credit a rate '
                'difference or a discount agreed after the sale.'
            : 'Raising one needs the manage credit notes permission.',
      );
    }
    return EnterpriseDataGrid<CreditNoteRecord>(
      items: _notes,
      total: _notes.length,
      pageOffset: 0,
      rowsPerPage: _notes.length,
      availableRowsPerPage: [_notes.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'number', label: 'Number'),
        GridColumn(key: 'customer', label: 'Customer'),
        GridColumn(key: 'total', label: 'Credited'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'actions', label: ''),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.creditNoteNumber,
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

  Widget _actions(CreditNoteRecord row) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (row.isDraft && _mayApprove)
          TextButton(
            onPressed: () => _act(
              row,
              () => widget.api
                  .approveCreditNote(row.id, expectedVersion: row.version),
              'approved. The credit and the tax are on the ledger.',
            ),
            child: const Text('Approve'),
          ),
        if ((row.isDraft || row.isApproved) && _mayApprove)
          TextButton(
            onPressed: () => _act(
              row,
              () => widget.api
                  .cancelCreditNote(row.id, expectedVersion: row.version),
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
class CreditNoteNotice extends StatelessWidget {
  const CreditNoteNotice({super.key});

  @override
  Widget build(BuildContext context) {
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
              'Use a credit note when the money changes and the goods do not '
              '— a rate agreed after invoicing, or a discount given later. It '
              'reverses the tax the invoice charged. Goods actually coming '
              'back are a sales return, which moves stock as well.',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

/// Raise one credit note against an approved invoice.
class CreditNoteDialog extends StatefulWidget {
  const CreditNoteDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<CreditNoteDialog> createState() => _CreditNoteDialogState();
}

class _CreditNoteDialogState extends State<CreditNoteDialog> {
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _remarks = TextEditingController();

  String _reason = 'RATE_DIFFERENCE';
  String? _error;
  bool _saving = false;
  bool _loading = true;

  /// The invoices that can be credited, and which one is selected. Read from
  /// the same list a sales return offers, filtered to invoices: a credit note
  /// corrects a *bill*, and a delivery note is not one.
  List<ReturnableDocument> _invoices = const <ReturnableDocument>[];
  String _invoiceId = '';

  /// The line the credit lands on. Most corrections are one line; a document
  /// with several offers a choice rather than guessing.
  String _lineId = '';

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
    _amount.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<ReturnableDocument> all =
          await widget.api.returnableDocuments();
      final List<ReturnableDocument> invoices = all
          .where((row) => row.sourceType == SalesReturnSource.salesInvoice)
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
      setState(() => _error = 'Choose the invoice line being credited.');
      return;
    }
    final double? amount = double.tryParse(_amount.text.trim());
    if (amount == null || amount <= 0) {
      setState(() => _error = 'Enter what is being credited, before tax.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.createCreditNote(<String, dynamic>{
        'sales_invoice_id': _invoiceId,
        'credit_note_date': _today(),
        'reason': _reason,
        if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
        'lines': [
          <String, dynamic>{
            'sales_invoice_line_id': _lineId,
            'line_number': 1,
            // The value is what is credited; the tax is worked out from the
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
    final ThemeData theme = Theme.of(context);
    final ReturnableDocument? invoice = _selected;
    return AlertDialog(
      title: const Text('Raise a credit note'),
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
                        'No approved invoice to credit. A credit note always '
                        'names the supply it corrects, because only that line '
                        'knows the rate its tax was charged at.',
                        style: theme.textTheme.bodySmall,
                      )
                    else ...[
                      DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: _invoiceId,
                        decoration: const InputDecoration(
                          labelText: 'Invoice',
                          helperText: 'The supply being corrected.',
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
                          value: 'RATE_DIFFERENCE',
                          child: Text('Rate difference'),
                        ),
                        DropdownMenuItem(
                          value: 'POST_SALE_DISCOUNT',
                          child: Text('Discount after the sale'),
                        ),
                        DropdownMenuItem(
                          value: 'DEFICIENCY_IN_SERVICE',
                          child: Text('Deficiency'),
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
                        labelText: 'Credit, before tax',
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
