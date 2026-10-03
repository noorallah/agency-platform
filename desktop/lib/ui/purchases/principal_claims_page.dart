// Claims on principals (SEL-11): what a principal owes the firm for the
// schemes it funded, stock that expired and goods that broke. A claim is
// previewed, raised, then settled by the principal's credit note (a party
// adjustment against the supplier's bills) or by a payment received. Phase 2
// only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/contra_voucher.dart';
import '../../models/entities.dart';
import '../../models/party_adjustment.dart';
import '../../models/principal_claim.dart';
import '../../models/product.dart';
import '../../models/settlement.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import '../workspace/reason_prompt.dart';

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

String _words(String status) => status.isEmpty
    ? status
    : (status[0] + status.substring(1).toLowerCase()).replaceAll('_', ' ');

const List<(String, String)> _kinds = [
  ('SCHEME', 'Schemes'),
  ('EXPIRY', 'Expired stock'),
  ('BREAKAGE', 'Breakage'),
];

/// The lines of a claim (or of a preview), grouped by what they are for.
class _ClaimLines extends StatelessWidget {
  const _ClaimLines({required this.lines});

  final List<PrincipalClaimLine> lines;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (lines.isEmpty) {
      return Text('Nothing to claim for this period.',
          style: theme.textTheme.bodySmall);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (String code, String label) in _kinds)
          if (lines.any((line) => line.kind == code)) ...[
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(label, style: theme.textTheme.titleSmall),
            ),
            for (final PrincipalClaimLine line
                in lines.where((line) => line.kind == code))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      [
                        if (line.sourceNumber.isNotEmpty) line.sourceNumber,
                        if (line.productName.isNotEmpty) line.productName,
                        if (line.quantity.isNotEmpty) '× ${line.quantity}',
                        if (line.description.isNotEmpty) line.description,
                      ].join(' · '),
                      style: theme.textTheme.bodySmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(_money(line.amount), style: theme.textTheme.bodySmall),
                ]),
              ),
          ],
      ],
    );
  }
}

/// List the claims and move each one along.
class PrincipalClaimsPage extends StatefulWidget {
  const PrincipalClaimsPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.openPdfOverride,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Test hook: receives the statement instead of the print dialog.
  final Future<void> Function(String name, List<int> bytes)? openPdfOverride;

  @override
  State<PrincipalClaimsPage> createState() => _PrincipalClaimsPageState();
}

class _PrincipalClaimsPageState extends State<PrincipalClaimsPage> {
  List<PrincipalClaim> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  final TextEditingController _search = TextEditingController();

  bool get _mayView => widget.permissions.hasPermission('PURCHASE_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('PURCHASE_APPROVE');

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
      final List<PrincipalClaim> rows = await widget.api.principalClaims();
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

  List<PrincipalClaim> get _shown {
    final String q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.claimNumber.toLowerCase().contains(q) ||
            row.principalName.toLowerCase().contains(q))
        .toList();
  }

  PrincipalClaim? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  /// Selects a row and reads it afresh, so the lines and payments beside the
  /// grid are what the server holds now rather than what the list carried.
  void _choose(PrincipalClaim row) {
    setState(() => _selectedId = row.id);
    unawaited(_reread(row.id));
  }

  Future<void> _reread(String id) async {
    try {
      final PrincipalClaim fresh = await widget.api.principalClaim(id);
      if (!mounted) return;
      setState(() {
        _rows = [for (final PrincipalClaim r in _rows) r.id == id ? fresh : r];
      });
    } on ApiException {
      // The list row stays on show; the next refresh will say what is wrong.
    }
  }

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _raise() async {
    final PrincipalClaim? saved = await showDialog<PrincipalClaim>(
      context: context,
      barrierDismissible: false,
      builder: (_) => NewPrincipalClaimDialog(api: widget.api),
    );
    if (saved == null || !mounted) return;
    setState(() => _selectedId = saved.id);
    _tell('Claim ${saved.claimNumber} raised.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _receive(PrincipalClaim claim) async {
    final PrincipalClaim? saved = await showDialog<PrincipalClaim>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RecordClaimPaymentDialog(api: widget.api, claim: claim),
    );
    if (saved == null || !mounted) return;
    _tell('Payment recorded against ${claim.claimNumber}.',
        AppNotificationKind.success);
    await _load();
  }

  Future<void> _reverse(PrincipalClaim claim) async {
    final PrincipalClaim? saved = await showDialog<PrincipalClaim>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ReverseClaimPaymentDialog(api: widget.api, claim: claim),
    );
    if (saved == null || !mounted) return;
    _tell('Payment reversed.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _settle(PrincipalClaim claim) async {
    final PartyAdjustment? draft = await showDialog<PartyAdjustment>(
      context: context,
      barrierDismissible: false,
      builder: (_) => SettleClaimDialog(api: widget.api, claim: claim),
    );
    if (draft == null || !mounted) return;
    _tell(
      'Settlement ${draft.adjustmentNumber} drafted. It now awaits approval '
      'in Party Adjustments.',
      AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _cancel(PrincipalClaim claim) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel claim ${claim.claimNumber}',
      explanation: 'The claim is withdrawn and its posting reversed. It is '
          'refused once anything has been settled.',
      confirmLabel: 'Cancel claim',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelPrincipalClaim(claim.id, reason);
      if (!mounted) return;
      _tell('Claim ${claim.claimNumber} cancelled.',
          AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  Future<void> _print(PrincipalClaim claim) async {
    try {
      final List<int> pdf = await widget.api.principalClaimStatement(claim.id);
      if (!mounted) return;
      final String name = 'Claim ${claim.claimNumber}';
      if (widget.openPdfOverride != null) {
        await widget.openPdfOverride!(name, pdf);
      } else {
        await printDocument(context, bytes: pdf, documentName: name);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Principal claims belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see principal claims',
        message: 'Reading them needs the view purchases permission.',
      );
    }
    final PrincipalClaim? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'What a principal owes for the schemes it funded, stock that '
          'expired and goods that broke. Preview a period, raise the claim, '
          'then settle it by their credit note or a payment received.',
      toolbar: _toolbar(picked),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search number or principal',
        onSearch: (_) => setState(() {}),
      ),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.claimNumber,
              party: picked.principalName,
              status: picked.status,
              total: picked.totalAmount,
              onClear: () => setState(() => _selectedId = null),
            ),
      detailsWidth: 380,
      detailsPanel: picked == null ? null : _details(picked),
      primaryContent: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
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
        message: 'Principal claims',
      ),
    );
  }

  WorkspaceToolbar _toolbar(PrincipalClaim? selected) {
    final PrincipalClaim? c = selected;
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
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) => true,
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            unawaited(_raise());
          default:
            unawaited(_load());
        }
      },
      commands: [
        ToolbarCommand(
          id: 'print-statement',
          label: 'Print statement',
          icon: Icons.print_outlined,
          onPressed: c != null && !c.isCancelled
              ? () => unawaited(_print(c))
              : null,
        ),
        if (_mayManage) ...[
          ToolbarCommand(
            id: 'record-payment',
            label: 'Record payment',
            icon: Icons.payments_outlined,
            onPressed: c != null && c.isOpen && c.outstandingAmount > 0
                ? () => unawaited(_receive(c))
                : null,
          ),
          ToolbarCommand(
            id: 'reverse-payment',
            label: 'Reverse payment',
            icon: Icons.undo_outlined,
            onPressed: c != null &&
                    !c.isCancelled &&
                    c.receipts.any((receipt) => receipt.isPosted)
                ? () => unawaited(_reverse(c))
                : null,
          ),
          ToolbarCommand(
            id: 'settle-claim',
            label: 'Settle by credit note',
            icon: Icons.price_check_outlined,
            onPressed: c != null && c.canSettleByCreditNote
                ? () => unawaited(_settle(c))
                : null,
          ),
          ToolbarCommand(
            id: 'cancel',
            label: 'Cancel',
            icon: Icons.cancel_outlined,
            onPressed: c != null && !c.isCancelled
                ? () => unawaited(_cancel(c))
                : null,
          ),
        ],
      ],
    );
  }

  Widget _amountRow(String label, String value, {bool strong = false}) {
    final TextStyle? style = strong
        ? Theme.of(context).textTheme.titleSmall
        : Theme.of(context).textTheme.bodyMedium;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        Expanded(child: Text(label, style: style)),
        Text(_money(value), style: style),
      ]),
    );
  }

  Widget _details(PrincipalClaim claim) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      key: const ValueKey('claim-details'),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: Text(claim.claimNumber, style: theme.textTheme.titleMedium),
            ),
            StatusBadge.fromStatus(claim.status),
          ]),
          Text(
            '${claim.principalName} · ${claim.periodFrom} to ${claim.periodTo}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          _amountRow('Schemes', claim.schemeAmount),
          _amountRow('Expired stock', claim.expiryAmount),
          _amountRow('Breakage', claim.breakageAmount),
          const Divider(),
          _amountRow('Total', claim.totalAmount, strong: true),
          _amountRow('Settled by credit note', claim.settledByCreditNote),
          _amountRow('Settled by payment', claim.settledByPayment),
          _amountRow('Outstanding', claim.outstanding, strong: true),
          if (claim.vendorId.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(
                'This principal is bought through no supplier, so only a '
                'payment can settle the claim.',
                style: theme.textTheme.bodySmall,
              ),
            ),
          if (claim.cancelReason.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text('Cancelled: ${claim.cancelReason}',
                  style: theme.textTheme.bodySmall),
            ),
          const SizedBox(height: AppSpacing.md),
          Text('Lines', style: theme.textTheme.titleSmall),
          _ClaimLines(lines: claim.lines),
          const SizedBox(height: AppSpacing.md),
          Text('Payments received', style: theme.textTheme.titleSmall),
          if (claim.receipts.isEmpty)
            Text('None yet.', style: theme.textTheme.bodySmall)
          else
            for (final PrincipalClaimReceipt receipt in claim.receipts)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      [
                        receipt.receivedOn,
                        if (receipt.reference.isNotEmpty) receipt.reference,
                        if (!receipt.isPosted) _words(receipt.status),
                      ].join(' · '),
                      style: theme.textTheme.bodySmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(_money(receipt.amount),
                      style: theme.textTheme.bodySmall),
                ]),
              ),
        ],
      ),
    );
  }

  late final ColumnChoice<PrincipalClaim> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'principal-claims.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Number'),
        cell: (item) => item.claimNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Date', priority: 2),
        cell: (item) => item.claimDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'principal', label: 'Principal'),
        cell: (item) => item.principalName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'period', label: 'Period', priority: 2),
        cell: (item) => '${item.periodFrom} to ${item.periodTo}',
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Total', numeric: true),
        cell: (item) => _money(item.totalAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(
            key: 'outstanding', label: 'Outstanding', numeric: true),
        cell: (item) => _money(item.outstanding),
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
    final List<PrincipalClaim> rows = _shown;
    if (rows.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No claims yet',
        message: _mayManage
            ? 'Raise a claim on a principal for a period.'
            : 'Raising one needs the approve purchases permission.',
      );
    }
    return EnterpriseDataGrid<PrincipalClaim>(
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

/// Preview a period, then raise the claim: pops the raised [PrincipalClaim];
/// stays open with the server's message on a refusal.
class NewPrincipalClaimDialog extends StatefulWidget {
  const NewPrincipalClaimDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<NewPrincipalClaimDialog> createState() =>
      _NewPrincipalClaimDialogState();
}

class _NewPrincipalClaimDialogState extends State<NewPrincipalClaimDialog>
    with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  final Set<String> _selectedKinds = <String>{for (final (c, _) in _kinds) c};
  List<PrincipalRecord> _principals = const [];
  String? _principalId;
  DateTime? _from;
  DateTime? _to;
  DateTime _claimDate = DateTime.now();
  PrincipalClaimPreview? _preview;
  bool _previewing = false;
  String? _problem;
  String? _loadNote;

  @override
  void initState() {
    super.initState();
    unawaited(_readPrincipals());
  }

  @override
  void dispose() {
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _readPrincipals() async {
    try {
      final List<PrincipalRecord> found = await widget.api.principals();
      if (!mounted) return;
      setState(() => _principals = found.where((p) => p.isActive).toList());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loadNote = error.message);
    }
  }

  /// Any change to the inputs makes the shown preview stale.
  void _changed(VoidCallback change) => setState(() {
        change();
        _preview = null;
        _problem = null;
      });

  Future<void> _pick(String which) async {
    final DateTime? current = switch (which) {
      'from' => _from,
      'to' => _to,
      _ => _claimDate,
    };
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    _changed(() {
      switch (which) {
        case 'from':
          _from = picked;
        case 'to':
          _to = picked;
        default:
          _claimDate = picked;
      }
    });
  }

  String? _check() {
    if (_principalId == null) return 'Choose the principal.';
    if (_from == null || _to == null) return 'Choose the period to claim for.';
    if (_to!.isBefore(_from!)) return 'The period cannot end before it starts.';
    if (_selectedKinds.isEmpty) return 'Choose what to claim for.';
    return null;
  }

  Json _body() => <String, dynamic>{
        'principal_id': _principalId,
        'period_from': _iso(_from!),
        'period_to': _iso(_to!),
        'claim_date': _iso(_claimDate),
        'kinds': [
          for (final (String code, _) in _kinds)
            if (_selectedKinds.contains(code)) code,
        ],
        if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      };

  Future<void> _runPreview() async {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    setState(() {
      _previewing = true;
      saveError = null;
    });
    try {
      final PrincipalClaimPreview found =
          await widget.api.previewPrincipalClaim(_body());
      if (!mounted) return;
      setState(() {
        _preview = found;
        _previewing = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _previewing = false;
      });
    }
  }

  void _raise() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<PrincipalClaim>(
      () => widget.api.raisePrincipalClaim(_body()),
    ));
  }

  Widget _dateField(String key, String label, DateTime? value) => InkWell(
        key: ValueKey(key),
        onTap: saving ? null : () => unawaited(_pick(key.split('-').last)),
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(value == null ? 'Choose' : _iso(value)),
        ),
      );

  Widget _previewTotals(PrincipalClaimPreview preview) {
    final ThemeData theme = Theme.of(context);
    Widget row(String label, String value, {bool strong = false}) => Row(
          children: [
            Expanded(
              child: Text(label,
                  style: strong
                      ? theme.textTheme.titleSmall
                      : theme.textTheme.bodyMedium),
            ),
            Text(_money(value),
                style: strong
                    ? theme.textTheme.titleSmall
                    : theme.textTheme.bodyMedium),
          ],
        );
    return Column(
      key: const ValueKey('claim-preview-result'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        row('Schemes', preview.schemeAmount),
        row('Expired stock', preview.expiryAmount),
        row('Breakage', preview.breakageAmount),
        const Divider(),
        row('Total', preview.totalAmount, strong: true),
        _ClaimLines(lines: preview.lines),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final PrincipalClaimPreview? preview = _preview;
    final bool busy = saving || _previewing;
    return AlertDialog(
      title: const Text('New claim on a principal'),
      content: SizedBox(
        width: 620,
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
              DropdownButtonFormField<String>(
                key: const ValueKey('claim-principal'),
                isExpanded: true,
                initialValue: _principalId,
                decoration: const InputDecoration(labelText: 'Principal'),
                items: [
                  for (final PrincipalRecord p in _principals)
                    DropdownMenuItem<String>(
                      value: p.id,
                      child: Text(p.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged:
                    busy ? null : (id) => _changed(() => _principalId = id),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(child: _dateField('claim-from', 'Period from', _from)),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: _dateField('claim-to', 'Period to', _to)),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                    child:
                        _dateField('claim-date', 'Claim date', _claimDate)),
              ]),
              const SizedBox(height: AppSpacing.sm),
              Wrap(spacing: AppSpacing.md, children: [
                for (final (String code, String label) in _kinds)
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    Checkbox(
                      key: ValueKey('claim-kind-$code'),
                      value: _selectedKinds.contains(code),
                      onChanged: busy
                          ? null
                          : (on) => _changed(() => on == true
                              ? _selectedKinds.add(code)
                              : _selectedKinds.remove(code)),
                    ),
                    Text(label),
                  ]),
              ]),
              TextField(
                key: const ValueKey('claim-remarks'),
                controller: _remarks,
                enabled: !busy,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  key: const ValueKey('claim-preview'),
                  onPressed: busy ? null : () => unawaited(_runPreview()),
                  icon: const Icon(Icons.visibility_outlined),
                  label: Text(_previewing ? 'Working…' : 'Preview'),
                ),
              ),
              if (preview != null) ...[
                const SizedBox(height: AppSpacing.sm),
                _previewTotals(preview),
              ],
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('claim-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('claim-raise'),
          onPressed: busy || preview == null ? null : _raise,
          child: Text(saving ? 'Raising…' : 'Raise claim'),
        ),
      ],
    );
  }
}

/// Record money received from the principal: pops the updated
/// [PrincipalClaim]; stays open with the server's message on a refusal.
class RecordClaimPaymentDialog extends StatefulWidget {
  const RecordClaimPaymentDialog(
      {super.key, required this.api, required this.claim});

  final ApiClient api;
  final PrincipalClaim claim;

  @override
  State<RecordClaimPaymentDialog> createState() =>
      _RecordClaimPaymentDialogState();
}

class _RecordClaimPaymentDialogState extends State<RecordClaimPaymentDialog>
    with SaveInDialog {
  late final TextEditingController _amount =
      TextEditingController(text: _money(widget.claim.outstanding));
  final TextEditingController _reference = TextEditingController();
  List<MoneyAccount> _accounts = const [];
  String? _accountId;
  DateTime _date = DateTime.now();
  String? _problem;
  String? _loadNote;

  @override
  void initState() {
    super.initState();
    unawaited(_readAccounts());
  }

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    super.dispose();
  }

  Future<void> _readAccounts() async {
    try {
      final List<MoneyAccount> found = await widget.api.contraMoneyAccounts();
      if (!mounted) return;
      setState(() => _accounts = found);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _loadNote = error.message);
    }
  }

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  void _save() {
    final double? amount = double.tryParse(_amount.text.trim());
    String? problem;
    if (amount == null || amount <= 0) {
      problem = 'Enter the amount received.';
    } else if (amount - widget.claim.outstandingAmount > 0.005) {
      problem = 'Only ${_money(widget.claim.outstanding)} is outstanding.';
    } else if (_accountId == null) {
      problem = 'Choose the account the money went into.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String reference = _reference.text.trim();
    unawaited(saveAndClose<PrincipalClaim>(
      () => widget.api.receivePrincipalClaimPayment(
        widget.claim.id,
        <String, dynamic>{
          'received_on': _iso(_date),
          'amount': _amount.text.trim(),
          'money_account_id': _accountId,
          'reference': reference.isEmpty ? null : reference,
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Payment for ${widget.claim.claimNumber}'),
      content: SizedBox(
        width: 460,
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
                '${widget.claim.principalName}: '
                '${_money(widget.claim.outstanding)} outstanding.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: InkWell(
                    key: const ValueKey('claim-payment-date'),
                    onTap: saving ? null : () => unawaited(_pickDate()),
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Received on'),
                      child: Text(_iso(_date)),
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: TextField(
                    key: const ValueKey('claim-payment-amount'),
                    controller: _amount,
                    enabled: !saving,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Amount'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                key: const ValueKey('claim-payment-account'),
                isExpanded: true,
                initialValue: _accountId,
                decoration: const InputDecoration(labelText: 'Paid into'),
                items: [
                  for (final MoneyAccount a in _accounts)
                    DropdownMenuItem<String>(
                      value: a.id,
                      child: Text(a.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged:
                    saving ? null : (id) => setState(() => _accountId = id),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('claim-payment-reference'),
                controller: _reference,
                enabled: !saving,
                decoration: const InputDecoration(
                    labelText: 'Reference (cheque or transfer no.)'),
              ),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('claim-payment-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('claim-payment-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Record payment'),
        ),
      ],
    );
  }
}

/// Pick a posted payment and reverse it: pops the updated [PrincipalClaim];
/// stays open with the server's message on a refusal.
class ReverseClaimPaymentDialog extends StatefulWidget {
  const ReverseClaimPaymentDialog(
      {super.key, required this.api, required this.claim});

  final ApiClient api;
  final PrincipalClaim claim;

  @override
  State<ReverseClaimPaymentDialog> createState() =>
      _ReverseClaimPaymentDialogState();
}

class _ReverseClaimPaymentDialogState extends State<ReverseClaimPaymentDialog>
    with SaveInDialog {
  String? _receiptId;

  @override
  Widget build(BuildContext context) {
    final List<PrincipalClaimReceipt> posted =
        widget.claim.receipts.where((receipt) => receipt.isPosted).toList();
    return AlertDialog(
      title: Text('Reverse a payment on ${widget.claim.claimNumber}'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            const Text('Choose the payment to take off again. Its posting is '
                'reversed and the amount becomes outstanding.'),
            const SizedBox(height: AppSpacing.sm),
            RadioGroup<String>(
              groupValue: _receiptId,
              onChanged: (id) {
                if (!saving) setState(() => _receiptId = id);
              },
              child: Column(children: [
                for (final PrincipalClaimReceipt receipt in posted)
                  RadioListTile<String>(
                    key: ValueKey('claim-reverse-${receipt.id}'),
                    value: receipt.id,
                    title: Text('${_money(receipt.amount)} · '
                        '${receipt.receivedOn}'),
                    subtitle: receipt.reference.isEmpty
                        ? null
                        : Text(receipt.reference),
                  ),
              ]),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Back')),
        FilledButton(
          key: const ValueKey('claim-reverse-confirm'),
          onPressed: saving || _receiptId == null
              ? null
              : () => unawaited(saveAndClose<PrincipalClaim>(
                    () => widget.api.reversePrincipalClaimPayment(
                        widget.claim.id, _receiptId!),
                  )),
          child: Text(saving ? 'Working…' : 'Reverse payment'),
        ),
      ],
    );
  }
}

/// Draft the party adjustment that takes the principal's credit note off the
/// supplier's open bills: pops the drafted [PartyAdjustment]; stays open with
/// the server's message on a refusal. Approval happens in Party Adjustments.
class SettleClaimDialog extends StatefulWidget {
  const SettleClaimDialog({super.key, required this.api, required this.claim});

  final ApiClient api;
  final PrincipalClaim claim;

  @override
  State<SettleClaimDialog> createState() => _SettleClaimDialogState();
}

class _SettleClaimDialogState extends State<SettleClaimDialog>
    with SaveInDialog {
  late final TextEditingController _reason = TextEditingController(
      text: 'Principal credit note for ${widget.claim.claimNumber}');
  final Map<String, TextEditingController> _boxes =
      <String, TextEditingController>{};
  List<OutstandingInvoice> _bills = const [];
  DateTime _date = DateTime.now();
  bool _loading = true;
  String? _problem;
  String? _loadNote;

  double get _cap => widget.claim.outstandingAmount;

  @override
  void initState() {
    super.initState();
    unawaited(_readBills());
  }

  @override
  void dispose() {
    _reason.dispose();
    for (final TextEditingController box in _boxes.values) {
      box.dispose();
    }
    super.dispose();
  }

  Future<void> _readBills() async {
    try {
      final PartyAdjustmentOpenBills found = await widget.api
          .partyAdjustmentOpenBills(vendorId: widget.claim.vendorId);
      if (!mounted) return;
      setState(() {
        _bills = found.supplierBills;
        for (final OutstandingInvoice bill in _bills) {
          _boxes[bill.invoiceId] = TextEditingController();
        }
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadNote = error.message;
        _loading = false;
      });
    }
  }

  double _number(String text) => double.tryParse(text.trim()) ?? 0;

  double get _total {
    double sum = 0;
    for (final TextEditingController box in _boxes.values) {
      sum += _number(box.text);
    }
    return sum;
  }

  void _save() {
    String? problem;
    for (final OutstandingInvoice bill in _bills) {
      final double value = _number(_boxes[bill.invoiceId]!.text);
      if (value - bill.outstanding > 0.005) {
        problem = 'Bill ${bill.invoiceNumber} owes '
            '${bill.outstanding.toStringAsFixed(2)}, so '
            '${value.toStringAsFixed(2)} cannot be taken off it.';
        break;
      }
    }
    if (problem == null) {
      if (_total <= 0) {
        problem = 'Enter an amount against at least one bill.';
      } else if (_total - _cap > 0.005) {
        problem = 'No more than ${_cap.toStringAsFixed(2)} is left to settle.';
      } else if (_reason.text.trim().isEmpty) {
        problem = 'Say why the balance is being adjusted.';
      }
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    final String amount = _total.toStringAsFixed(2);
    unawaited(saveAndClose<PartyAdjustment>(
      () => widget.api.createPartyAdjustment(<String, dynamic>{
        'kind': 'PRINCIPAL_CLAIM',
        'vendor_id': widget.claim.vendorId,
        'amount': amount,
        'reason': _reason.text.trim(),
        'adjustment_date': _iso(_date),
        'principal_claim_id': widget.claim.id,
        'allocations': [
          for (final OutstandingInvoice bill in _bills)
            if (_number(_boxes[bill.invoiceId]!.text) > 0)
              <String, dynamic>{
                'side': 'SUPPLIER',
                'bill_id': bill.invoiceId,
                'amount': _boxes[bill.invoiceId]!.text.trim(),
              },
        ],
      }),
    ));
  }

  Future<void> _pickDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Widget _billRow(OutstandingInvoice bill) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(children: [
          Expanded(
            flex: 3,
            child: Text(
              '${bill.invoiceNumber} · ${bill.invoiceDate}',
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Expanded(
            flex: 2,
            child: Text('Owes ${_money(bill.outstandingAmount)}',
                textAlign: TextAlign.end),
          ),
          const SizedBox(width: AppSpacing.md),
          SizedBox(
            width: 130,
            child: TextField(
              key: ValueKey('settle-bill-${bill.invoiceId}'),
              controller: _boxes[bill.invoiceId],
              enabled: !saving,
              onChanged: (_) => setState(() {}),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration:
                  const InputDecoration(labelText: 'Amount', isDense: true),
            ),
          ),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Settle claim ${widget.claim.claimNumber}'),
      content: SizedBox(
        width: 620,
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
                '${widget.claim.principalName}: ${_cap.toStringAsFixed(2)} '
                'left to settle. Choose how much of their credit note comes '
                'off each open bill of the supplier; this drafts a party '
                'adjustment that is approved in Party Adjustments.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              if (_loading)
                const Center(child: CircularProgressIndicator())
              else if (_bills.isEmpty)
                const Text('This supplier has no open bills.')
              else
                for (final OutstandingInvoice bill in _bills) _billRow(bill),
              const SizedBox(height: AppSpacing.sm),
              Text('Total ${_total.toStringAsFixed(2)} of '
                  '${_cap.toStringAsFixed(2)}',
                  key: const ValueKey('settle-total'),
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                    key: const ValueKey('settle-reason'),
                    controller: _reason,
                    enabled: !saving,
                    decoration: const InputDecoration(labelText: 'Reason'),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  flex: 2,
                  child: InkWell(
                    key: const ValueKey('settle-date'),
                    onTap: saving ? null : () => unawaited(_pickDate()),
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'Date'),
                      child: Text(_iso(_date)),
                    ),
                  ),
                ),
              ]),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('settle-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('settle-save'),
          onPressed: saving || _loading ? null : _save,
          child: Text(saving ? 'Saving…' : 'Draft settlement'),
        ),
      ],
    );
  }
}
