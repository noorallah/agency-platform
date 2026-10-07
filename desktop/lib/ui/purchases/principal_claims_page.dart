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
import '../workspace/discard_prompt.dart';
import '../workspace/printed_document.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_requisition_page.dart' show ProductSearchBox;

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
  ('FREE_GOODS', 'Free goods'),
  ('EXPIRY', 'Expired stock'),
  ('BREAKAGE', 'Breakage'),
];

/// The groups a claim's lines fall into: the four a period claims, then a
/// price cut, which stands on a claim of its own.
const List<(String, String)> _groups = [
  ..._kinds,
  ('RATE_DIFFERENCE', 'Rate difference'),
];

/// One line in words: what it is for, then the stock and rates a price cut
/// states. A line taking back from an earlier claim is negative and says so in
/// its description, as the server sent it.
String _lineText(PrincipalClaimLine line) => [
      if (line.sourceNumber.isNotEmpty) line.sourceNumber,
      if (line.productName.isNotEmpty) line.productName,
      if (line.batchNumber.isNotEmpty) 'Batch ${line.batchNumber}',
      if (line.quantity.isNotEmpty) '× ${line.quantity}',
      if (line.oldRate.isNotEmpty || line.newRate.isNotEmpty)
        'Old rate ${line.oldRate.isEmpty ? '-' : _money(line.oldRate)} → '
            'new rate ${line.newRate.isEmpty ? '-' : _money(line.newRate)}',
      if (line.description.isNotEmpty) line.description,
    ].join(' · ');

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
        for (final (String code, String label) in _groups)
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
                      _lineText(line),
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

  Future<void> _raisePriceCut() async {
    final PrincipalClaim? saved = await showDialog<PrincipalClaim>(
      context: context,
      barrierDismissible: false,
      builder: (_) => NewPriceCutClaimDialog(api: widget.api),
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
          'then settle it by their credit note or a payment received. A price '
          'cut on stock in hand is claimed with Price cut claim.',
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
        if (_mayManage)
          OutlinedButton.icon(
            key: const ValueKey('claim-new-price-cut'),
            onPressed: () => unawaited(_raisePriceCut()),
            icon: const Icon(Icons.trending_down),
            label: const Text('Price cut claim'),
          ),
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
            claim.lines.any((line) => line.kind == 'RATE_DIFFERENCE')
                ? '${claim.principalName} · price cut from ${claim.periodFrom}'
                : '${claim.principalName} · ${claim.periodFrom} to '
                    '${claim.periodTo}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.md),
          _amountRow('Schemes', claim.schemeAmount),
          _amountRow('Free goods', claim.freeGoodsAmount),
          _amountRow('Expired stock', claim.expiryAmount),
          _amountRow('Breakage', claim.breakageAmount),
          if ((double.tryParse(claim.rateDifferenceAmount) ?? 0) != 0)
            _amountRow('Rate difference', claim.rateDifferenceAmount),
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
        column: const GridColumn(
            key: 'rate-difference', label: 'Rate difference', numeric: true),
        cell: (item) => _money(item.rateDifferenceAmount),
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
        row('Free goods', preview.freeGoodsAmount),
        row('Expired stock', preview.expiryAmount),
        row('Breakage', preview.breakageAmount),
        const Divider(),
        row('Total', preview.totalAmount, strong: true),
        if (preview.carriedForward > 0)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              'Carried to the next claim: '
              '${_money(preview.adjustmentsCarriedForward)}',
              key: const ValueKey('claim-carried-forward'),
              style: theme.textTheme.bodySmall,
            ),
          ),
        _ClaimLines(lines: preview.lines),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final PrincipalClaimPreview? preview = _preview;
    final bool busy = saving || _previewing;
    return AskBeforeClosing(
      touched: () =>
          _principalId != null ||
          _from != null ||
          _to != null ||
          _remarks.text.trim().isNotEmpty,
      what: 'claim has not been raised',
      busy: saving,
      child: _dialog(theme, preview, busy),
    );
  }

  Widget _dialog(ThemeData theme, PrincipalClaimPreview? preview, bool busy) {
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

/// A rate with trailing zeros dropped, kept to at least two places.
String _rate(String value) {
  final double? parsed = double.tryParse(value);
  if (parsed == null) return value;
  String text = parsed.toStringAsFixed(4);
  while (text.endsWith('0') && text.indexOf('.') < text.length - 3) {
    text = text.substring(0, text.length - 1);
  }
  return text;
}

/// A quantity with trailing zeros dropped.
String _quantity(String value) {
  final double? parsed = double.tryParse(value);
  if (parsed == null) return value;
  String text = parsed.toStringAsFixed(4);
  while (text.endsWith('0')) {
    text = text.substring(0, text.length - 1);
  }
  return text.endsWith('.') ? text.substring(0, text.length - 1) : text;
}

/// One row of a price cut: a product (and batch) with the stock the server
/// counted and the two rates the person may correct. A rate is sent only
/// once it has been typed; an untouched one is sent as null so the server
/// takes the rate it has recorded.
class _RateRow {
  _RateRow({
    required this.productId,
    required this.item,
    this.batchId = '',
    this.batchNumber = '',
    this.stock = '',
    this.amount = '',
    String oldRate = '',
    String newRate = '',
    this.oldTyped = false,
    this.newTyped = false,
    this.manual = false,
  })  : oldBox = TextEditingController(text: oldRate),
        newBox = TextEditingController(text: newRate);

  final String productId;
  final String item;
  final String batchId;
  final String batchNumber;
  final String stock;
  final String amount;
  final TextEditingController oldBox;
  final TextEditingController newBox;
  bool oldTyped;
  bool newTyped;

  /// Added by hand rather than proposed by the server.
  final bool manual;

  String get key => '$productId-$batchId';

  String? _sent(TextEditingController box, bool typed) {
    final String text = box.text.trim();
    return typed && text.isNotEmpty ? text : null;
  }

  Json toJson() => <String, dynamic>{
        'product_id': productId,
        'batch_id': batchId.isEmpty ? null : batchId,
        'old_rate': _sent(oldBox, oldTyped),
        'new_rate': _sent(newBox, newTyped),
      };

  void dispose() {
    oldBox.dispose();
    newBox.dispose();
  }
}

/// Claim a principal's price cut on the stock in hand: the server proposes a
/// line for every product that dropped in price on the day, the person
/// corrects, removes or adds, and the claim is exactly the grid. Pops the
/// raised [PrincipalClaim]; stays open with the server's message on a refusal.
class NewPriceCutClaimDialog extends StatefulWidget {
  const NewPriceCutClaimDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<NewPriceCutClaimDialog> createState() => _NewPriceCutClaimDialogState();
}

class _NewPriceCutClaimDialogState extends State<NewPriceCutClaimDialog>
    with SaveInDialog {
  final TextEditingController _remarks = TextEditingController();
  final TextEditingController _addProduct = TextEditingController();
  final TextEditingController _addOld = TextEditingController();
  final TextEditingController _addNew = TextEditingController();
  final List<_RateRow> _graveyard = <_RateRow>[];
  List<PrincipalRecord> _principals = const [];
  List<_RateRow> _rows = <_RateRow>[];
  String? _principalId;
  DateTime? _effective;
  DateTime _claimDate = DateTime.now();
  PrincipalClaimPreview? _preview;
  Product? _picked;
  bool _started = false;
  bool _dirty = false;
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
    _addProduct.dispose();
    _addOld.dispose();
    _addNew.dispose();
    for (final _RateRow row in [..._rows, ..._graveyard]) {
      row.dispose();
    }
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

  /// Retires the rows; their boxes are disposed with the dialog, not while the
  /// frame that still draws them is running.
  void _retire(List<_RateRow> rows) => _graveyard.addAll(rows);

  /// A new principal or day starts the claim again.
  void _restart(VoidCallback change) => setState(() {
        change();
        _retire(_rows);
        _rows = <_RateRow>[];
        _preview = null;
        _started = false;
        _dirty = false;
        _problem = null;
        saveError = null;
      });

  Future<void> _pick(bool effective) async {
    final DateTime today = DateTime.now();
    final DateTime? current = effective ? _effective : _claimDate;
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current ?? today,
      firstDate: DateTime(2000),
      lastDate: effective ? today : DateTime(2100),
    );
    if (picked == null) return;
    if (effective) {
      _restart(() => _effective = picked);
    } else {
      setState(() {
        _claimDate = picked;
        _problem = null;
      });
    }
  }

  String? _check() {
    if (_principalId == null) return 'Choose the principal.';
    if (_effective == null) {
      return 'Choose the day the new rates take effect from.';
    }
    if (_claimDate.isBefore(_effective!)) {
      return 'The claim cannot be dated before the new rates took effect.';
    }
    for (final _RateRow row in _rows) {
      for (final (TextEditingController box, bool typed) in [
        (row.oldBox, row.oldTyped),
        (row.newBox, row.newTyped),
      ]) {
        final String text = box.text.trim();
        if (typed && text.isNotEmpty && double.tryParse(text) == null) {
          return 'A rate on ${row.item} is not a number.';
        }
      }
    }
    return null;
  }

  Json _body({required bool withLines}) => <String, dynamic>{
        'principal_id': _principalId,
        'kinds': ['RATE_DIFFERENCE'],
        'effective_date': _iso(_effective!),
        'claim_date': _iso(_claimDate),
        if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
        if (withLines)
          'rate_lines': [for (final _RateRow r in _rows) r.toJson()],
      };

  /// Asks for the proposal the first time (no lines sent) and recalculates
  /// from the grid afterwards.
  Future<void> _calculate() async {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    setState(() {
      _previewing = true;
      saveError = null;
    });
    try {
      final PrincipalClaimPreview found = await widget.api
          .previewPrincipalClaim(_body(withLines: _started));
      if (!mounted) return;
      final List<_RateRow> before = _rows;
      setState(() {
        _rows = [
          for (final PrincipalClaimLine line in found.lines)
            if (line.kind == 'RATE_DIFFERENCE') _rowFor(line, before),
        ];
        _retire(before);
        _preview = found;
        _started = true;
        _dirty = false;
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

  /// The row for a line the server sent back, keeping what the person typed
  /// on the row it replaces.
  _RateRow _rowFor(PrincipalClaimLine line, List<_RateRow> before) {
    final String key = '${line.productId}-${line.batchId}';
    final _RateRow? old = before.where((r) => r.key == key).firstOrNull ??
        before
            .where((r) =>
                r.manual && r.batchId.isEmpty && r.productId == line.productId)
            .firstOrNull;
    return _RateRow(
      productId: line.productId,
      batchId: line.batchId,
      batchNumber: line.batchNumber,
      item: [
        if (line.sourceNumber.isNotEmpty) line.sourceNumber,
        if (line.productName.isNotEmpty) line.productName,
      ].join(' · '),
      stock: line.quantity,
      amount: line.amount,
      oldRate: old != null && old.oldTyped
          ? old.oldBox.text
          : (line.oldRate.isEmpty ? '' : _rate(line.oldRate)),
      newRate: old != null && old.newTyped
          ? old.newBox.text
          : (line.newRate.isEmpty ? '' : _rate(line.newRate)),
      oldTyped: old?.oldTyped ?? false,
      newTyped: old?.newTyped ?? false,
      manual: old?.manual ?? false,
    );
  }

  void _raise() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<PrincipalClaim>(
      () => widget.api.raisePrincipalClaim(_body(withLines: true)),
    ));
  }

  void _remove(_RateRow row) => setState(() {
        _rows = [
          for (final _RateRow r in _rows)
            if (r != row) r,
        ];
        _retire([row]);
        _dirty = true;
        _problem = null;
      });

  void _add() {
    final Product? product = _picked;
    String? problem;
    if (product == null) {
      problem = 'Pick the product to add.';
    } else if (_rows
        .any((r) => r.productId == product.id && r.batchId.isEmpty)) {
      problem = '${product.name} is already in the list.';
    } else if ((_addOld.text.trim().isNotEmpty &&
            double.tryParse(_addOld.text.trim()) == null) ||
        (_addNew.text.trim().isNotEmpty &&
            double.tryParse(_addNew.text.trim()) == null)) {
      problem = 'Type the rates as numbers.';
    }
    setState(() => _problem = problem);
    if (problem != null || product == null) return;
    setState(() {
      _rows = [
        ..._rows,
        _RateRow(
          productId: product.id,
          item: '${product.code} · ${product.name}',
          oldRate: _addOld.text.trim(),
          newRate: _addNew.text.trim(),
          oldTyped: _addOld.text.trim().isNotEmpty,
          newTyped: _addNew.text.trim().isNotEmpty,
          manual: true,
        ),
      ];
      _picked = null;
      _addProduct.clear();
      _addOld.clear();
      _addNew.clear();
      _dirty = true;
    });
  }

  Widget _dateField(String key, String label, DateTime? value,
          {required bool effective}) =>
      InkWell(
        key: ValueKey(key),
        onTap: saving ? null : () => unawaited(_pick(effective)),
        child: InputDecorator(
          decoration: InputDecoration(labelText: label),
          child: Text(value == null ? 'Choose' : _iso(value)),
        ),
      );

  Widget _cell(double width, Widget child) =>
      SizedBox(width: width, child: child);

  Widget _rateBox(
          Key key, TextEditingController box, VoidCallback typed, bool on) =>
      TextField(
        key: key,
        controller: box,
        enabled: on,
        textAlign: TextAlign.end,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(isDense: true),
        onChanged: (_) => setState(() {
          typed();
          _dirty = true;
        }),
      );

  Widget _header(ThemeData theme) {
    final TextStyle? style = theme.textTheme.labelMedium;
    return Row(children: [
      Expanded(child: Text('Item', style: style)),
      _cell(80, Text('Batch', style: style)),
      _cell(80, Text('Stock on hand', style: style, textAlign: TextAlign.end)),
      const SizedBox(width: AppSpacing.sm),
      _cell(90, Text('Old rate', style: style, textAlign: TextAlign.end)),
      const SizedBox(width: AppSpacing.sm),
      _cell(90, Text('New rate', style: style, textAlign: TextAlign.end)),
      _cell(90, Text('Amount', style: style, textAlign: TextAlign.end)),
      const SizedBox(width: 40),
    ]);
  }

  Widget _rowWidget(_RateRow row, ThemeData theme, bool on) {
    final String id = row.key;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        Expanded(
          child: Text(row.item,
              style: theme.textTheme.bodySmall,
              overflow: TextOverflow.ellipsis),
        ),
        _cell(
            80,
            Text(row.batchNumber.isEmpty ? '-' : row.batchNumber,
                style: theme.textTheme.bodySmall,
                overflow: TextOverflow.ellipsis)),
        _cell(
            80,
            Text(row.stock.isEmpty ? '-' : _quantity(row.stock),
                key: ValueKey('pc-stock-$id'),
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.end)),
        const SizedBox(width: AppSpacing.sm),
        _cell(
            90,
            _rateBox(ValueKey('pc-old-$id'), row.oldBox,
                () => row.oldTyped = true, on)),
        const SizedBox(width: AppSpacing.sm),
        _cell(
            90,
            _rateBox(ValueKey('pc-new-$id'), row.newBox,
                () => row.newTyped = true, on)),
        _cell(
            90,
            Text(row.amount.isEmpty ? '-' : _money(row.amount),
                key: ValueKey('pc-amount-$id'),
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.end)),
        SizedBox(
          width: 40,
          child: IconButton(
            key: ValueKey('pc-remove-$id'),
            tooltip: 'Take this row off the claim',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.close, size: 18),
            onPressed: on ? () => _remove(row) : null,
          ),
        ),
      ]),
    );
  }

  Widget _grid(ThemeData theme, bool busy) {
    final PrincipalClaimPreview preview = _preview!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_rows.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
            child: Text(
              preview.lines.isEmpty
                  ? 'No price drop is recorded for this principal on that day. '
                      'Add the products by hand below, with their old and new '
                      'rates.'
                  : 'Nothing is left on the claim. Add a product below.',
              key: const ValueKey('pc-empty'),
              style: theme.textTheme.bodySmall,
            ),
          )
        else ...[
          _header(theme),
          const Divider(height: 8),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 280),
            child: ListView(
              shrinkWrap: true,
              children: [
                for (final _RateRow row in _rows) _rowWidget(row, theme, !busy),
              ],
            ),
          ),
          const Divider(height: 8),
          Row(children: [
            Expanded(
              child:
                  Text('Rate difference', style: theme.textTheme.titleSmall),
            ),
            Text(_money(preview.rateDifferenceAmount),
                key: const ValueKey('pc-total'),
                style: theme.textTheme.titleSmall),
          ]),
          if (_dirty)
            Text('Recalculate to refresh the stock and amounts.',
                key: const ValueKey('pc-stale'),
                style: theme.textTheme.bodySmall),
          if (preview.carriedForward > 0)
            Text(
                'Carried to the next claim: '
                '${_money(preview.adjustmentsCarriedForward)}',
                key: const ValueKey('claim-carried-forward'),
                style: theme.textTheme.bodySmall),
        ],
        const SizedBox(height: AppSpacing.md),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(
            child: ProductSearchBox(
              fieldKey: const ValueKey('pc-add-product'),
              api: widget.api,
              controller: _addProduct,
              enabled: !busy,
              onPicked: (Product p) => _picked = p,
              onCleared: () => _picked = null,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(
            width: 90,
            child: TextField(
              key: const ValueKey('pc-add-old'),
              controller: _addOld,
              enabled: !busy,
              textAlign: TextAlign.end,
              decoration:
                  const InputDecoration(labelText: 'Old rate', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          SizedBox(
            width: 90,
            child: TextField(
              key: const ValueKey('pc-add-new'),
              controller: _addNew,
              enabled: !busy,
              textAlign: TextAlign.end,
              decoration:
                  const InputDecoration(labelText: 'New rate', isDense: true),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          OutlinedButton.icon(
            key: const ValueKey('pc-add'),
            onPressed: busy ? null : _add,
            icon: const Icon(Icons.add),
            label: const Text('Add product'),
          ),
        ]),
        Text(
          'A rate left blank is taken from the price recorded for that day.',
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool busy = saving || _previewing;
    return AlertDialog(
      title: const Text('Claim a price cut on stock in hand'),
      content: SizedBox(
        width: 840,
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
                key: const ValueKey('pc-principal'),
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
                    busy ? null : (id) => _restart(() => _principalId = id),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                    child: _dateField(
                        'pc-effective', 'New rates effective from', _effective,
                        effective: true)),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                    child: _dateField('pc-claim-date', 'Claim date', _claimDate,
                        effective: false)),
              ]),
              TextField(
                key: const ValueKey('pc-remarks'),
                controller: _remarks,
                enabled: !busy,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
              const SizedBox(height: AppSpacing.md),
              Align(
                alignment: Alignment.centerLeft,
                child: _started
                    ? OutlinedButton.icon(
                        key: const ValueKey('pc-recalculate'),
                        onPressed: busy || _rows.isEmpty
                            ? null
                            : () => unawaited(_calculate()),
                        icon: const Icon(Icons.refresh),
                        label: Text(_previewing ? 'Working…' : 'Recalculate'),
                      )
                    : OutlinedButton.icon(
                        key: const ValueKey('pc-preview'),
                        onPressed: busy ? null : () => unawaited(_calculate()),
                        icon: const Icon(Icons.visibility_outlined),
                        label: Text(_previewing ? 'Working…' : 'Preview'),
                      ),
              ),
              if (_started) ...[
                const SizedBox(height: AppSpacing.sm),
                _grid(theme, busy),
              ],
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('pc-problem'),
                      style: TextStyle(color: theme.colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          key: const ValueKey('pc-raise'),
          onPressed: busy || !_started || _rows.isEmpty ? null : _raise,
          child: Text(saving ? 'Raising…' : 'Raise claim'),
        ),
      ],
    );
  }
}
