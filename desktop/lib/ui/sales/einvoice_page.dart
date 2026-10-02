// What the tax authority knows about this firm's invoices, and their movement.
//
// The one thing every view here must make impossible to miss is **which mode**
// a reference was made in. A sandbox registration is a rehearsal: nothing was
// filed, and the number means nothing outside this database. A screen that
// showed the reference alone would be handing somebody a document to present
// at a check post.

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/einvoice.dart';
import '../../models/entities.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'eway_bill_actions.dart';

/// List what has been registered, and act on one invoice at a time.
class EInvoicePage extends StatefulWidget {
  const EInvoicePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.pickResultFile,
    this.saveExportFile,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Choose the portal's result file. Tests inject one, because a widget
  /// test cannot open a native dialog.
  final Future<XFile?> Function()? pickResultFile;

  /// Write the export for the portal; returns where, or null on a cancel.
  final Future<String?> Function(String suggestedName, List<int> bytes)?
      saveExportFile;

  @override
  State<EInvoicePage> createState() => _EInvoicePageState();
}

class _EInvoicePageState extends State<EInvoicePage> {
  List<EInvoiceRegistrationRecord> _rows = const [];
  final Map<String, EWayBillRecord> _bills = <String, EWayBillRecord>{};
  String? _error;
  String? _selectedId;

  EInvoiceRegistrationRecord? get _selectedRow {
    for (final EInvoiceRegistrationRecord row in _rows) {
      if (row.id == _selectedId) return row;
    }
    return null;
  }
  bool _loading = true;
  // How this firm's e-invoices reach the portal (A42); null where unknown.
  EInvoiceSettings? _filing;

  bool get _isOffline => _filing?.isOffline ?? false;

  bool get _mayView => widget.permissions.hasPermission('EINVOICE_VIEW');

  /// Registering files a document with the authority — in sandbox today, for
  /// real the day the firm switches. Its own permission, not a sales one.
  bool get _mayManage => widget.permissions.hasPermission('EINVOICE_MANAGE');

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
      try {
        _filing = await widget.api.einvoiceSettings();
      } on ApiException {
        _filing = null;
      }
      final List<EInvoiceRegistrationRecord> rows =
          await fetchAllPages<EInvoiceRegistrationRecord>(
        (page) => widget.api.einvoiceRegistrations(page: page),
      );
      final Map<String, EWayBillRecord> bills = <String, EWayBillRecord>{};
      for (final EInvoiceRegistrationRecord row in rows) {
        if (!row.isRegistered) continue;
        final EWayBillRecord? bill =
            await widget.api.ewayBill(row.salesInvoiceId);
        if (bill != null) bills[row.salesInvoiceId] = bill;
      }
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _bills
          ..clear()
          ..addAll(bills);
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

  Future<void> _run(Future<void> Function() action, String done) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(
        context,
        done,
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

  /// Register an approved invoice with the portal.
  ///
  /// This screen listed registrations and could not make one, so from the
  /// desktop no invoice had ever been registered -- the module could not do
  /// the single thing it exists for. The empty state even said to register
  /// "from the invoice itself", which was a promise about a control nobody
  /// had built.
  ///
  /// Here rather than on the invoice screen because this is the compliance
  /// view -- and because that toolbar already carries eight controls, which
  /// is what pushed the deposits panel off the sales-order toolbar in #195.
  Future<void> _register() async {
    final List<Json> invoices = await _registerable();
    if (!mounted) return;
    if (invoices.isEmpty) {
      NotificationService.show(
        context,
        'Every approved invoice is already registered.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final String? invoiceId = await showDialog<String>(
      context: context,
      builder: (context) => _RegisterInvoiceDialog(invoices: invoices),
    );
    if (invoiceId == null) return;
    await _registerOne(invoiceId);
  }

  /// Send one invoice, and say what the portal actually answered.
  ///
  /// A refusal is not an exception here -- the service records what the
  /// portal said and returns the row FAILED. Reporting that as a success
  /// because no exception was thrown would tell somebody their invoice is
  /// filed when it is not.
  Future<void> _registerOne(String invoiceId) async {
    try {
      final EInvoiceRegistrationRecord row =
          await widget.api.registerEInvoice(invoiceId);
      if (!mounted) return;
      NotificationService.show(
        context,
        row.isRegistered
            ? 'Registered in ${row.mode} mode as ${row.irn}.'
            : 'The portal refused it: '
                '${row.errorMessage.isEmpty ? row.status : row.errorMessage}',
        kind: row.isRegistered
            ? AppNotificationKind.success
            : AppNotificationKind.error,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  /// The invoices a registration can still be raised for.
  ///
  /// Approved only -- the payload builder refuses anything else, and offering
  /// a draft would spend a round trip to be told so. An invoice whose last
  /// attempt FAILED is offered again, because the service keeps the row and
  /// counts the attempt rather than treating a refusal as final.
  Future<List<Json>> _registerable() async {
    // Only a refusal can be sent again. A registered invoice already has its
    // IRN, and a withdrawn one can never have another under the same number
    // (D-CMP-6) -- the server refuses it, so it is not offered.
    final Set<String> registered = <String>{
      for (final EInvoiceRegistrationRecord row in _rows)
        if (!row.isFailed) row.salesInvoiceId,
    };
    try {
      final Json response = await widget.api.documentPage(
        'sales-invoices',
        pageSize: 100,
      );
      final dynamic data = response['data'];
      if (data is! List) return const <Json>[];
      return data
          .whereType<Map>()
          .map(Map<String, dynamic>.from)
          .where((row) => '${row['status']}' == 'APPROVED')
          .where((row) => !registered.contains('${row['id']}'))
          .toList();
    } on ApiException {
      return const <Json>[];
    }
  }

  /// Offline filing, step one: choose approved invoices and save the JSON the
  /// portal's bulk upload takes. Each chosen invoice becomes a registration
  /// waiting for its IRN.
  Future<void> _exportForPortal() async {
    final List<Json> invoices = await _registerable();
    if (!mounted) return;
    if (invoices.isEmpty) {
      NotificationService.show(
        context,
        'Every approved invoice is already registered.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final List<String>? ids = await showDialog<List<String>>(
      context: context,
      builder: (context) => _ExportInvoicesDialog(invoices: invoices),
    );
    if (ids == null || ids.isEmpty) return;
    try {
      final List<int> bytes = await widget.api.exportOfflineEinvoices(ids);
      final String stamp = DateTime.now()
          .toIso8601String()
          .substring(0, 16)
          .replaceAll(RegExp(r'[-:]'), '')
          .replaceAll('T', '-');
      final String? path = await (widget.saveExportFile ?? _saveToDisk)(
        'einvoice-$stamp.json',
        bytes,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        path == null
            ? 'Export cancelled. The invoices now wait for the portal, but no '
                'file was saved.'
            : 'Saved to $path. Upload it on the e-invoice portal, then use '
                '"Import portal result".',
        kind: path == null
            ? AppNotificationKind.warning
            : AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<String?> _saveToDisk(String suggestedName, List<int> bytes) async {
    final FileSaveLocation? location = await getSaveLocation(
      suggestedName: suggestedName,
      acceptedTypeGroups: const [
        XTypeGroup(label: 'JSON', extensions: ['json']),
      ],
    );
    if (location == null) return null;
    await File(location.path).writeAsBytes(bytes, flush: true);
    return location.path;
  }

  /// Offline filing, step two: the portal's result file, matched to the
  /// waiting registrations by invoice number.
  Future<void> _importPortalResult() async {
    final XFile? file = await (widget.pickResultFile ??
        () => openFile(acceptedTypeGroups: const [
              XTypeGroup(
                label: 'Portal result',
                extensions: ['json', 'csv', 'xlsx'],
              ),
            ]))();
    if (file == null) return;
    try {
      final OfflineEInvoiceImport result =
          await widget.api.importOfflineEinvoiceResult(
        // Only the last segment: some platforms give a path here.
        fileName: file.name.split(RegExp(r'[/\\]')).last,
        bytes: await file.readAsBytes(),
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => _ImportResultDialog(result: result),
      );
      if (!mounted) return;
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _cancelRegistration(EInvoiceRegistrationRecord row) async {
    final String? reason = await _askReason(
      title: 'Withdraw registration',
      hint: 'The authority requires a reason, and allows 24 hours.',
    );
    if (reason == null) return;
    await _run(
      () => widget.api
          .cancelEInvoice(row.salesInvoiceId, reason: reason)
          .then((_) {}),
      'Registration withdrawn.',
    );
  }

  Future<void> _raiseEwayBill(EInvoiceRegistrationRecord row) async {
    final Json? details = await showDialog<Json>(
      context: context,
      builder: (context) => EWayBillDialog(
        onSave: (Json values) =>
            widget.api.generateEwayBill(row.salesInvoiceId, values),
      ),
    );
    if (details == null || !mounted) return;
    NotificationService.show(
      context,
      'E-way bill raised.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  /// The consignments above the firm's limit with no e-way bill, from where
  /// each can be raised or recorded. Reloads afterwards: a bill raised here
  /// shows against its invoice's row.
  Future<void> _showEwayBillsDue() async {
    await showDialog<void>(
      context: context,
      builder: (context) => _EWayBillsDueDialog(
        api: widget.api,
        mayManage: _mayManage,
      ),
    );
    if (!mounted) return;
    await _load();
  }

  Future<void> _cancelEwayBill(EInvoiceRegistrationRecord row) async {
    final String? reason = await _askReason(
      title: 'Withdraw e-way bill',
      hint: 'The authority requires a reason.',
    );
    if (reason == null) return;
    await _run(
      () => widget.api
          .cancelEwayBill(row.salesInvoiceId, reason: reason)
          .then((_) {}),
      'E-way bill withdrawn.',
    );
  }

  Future<String?> _askReason({
    required String title,
    required String hint,
  }) =>
      askForReason(
        context,
        title: title,
        explanation: hint,
        confirmLabel: 'Withdraw',
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Registrations belong to one firm’s GST number.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see registrations',
        message: 'Reading them needs the view e-invoice permission.',
      );
    }
    final EInvoiceRegistrationRecord? chosen = _selectedRow;
    return ManagementWorkspaceLayout(
      notice: SandboxNotice.text,
      // Phase 2: Refresh as the line's icon, the e-way bill steps as its
      // commands, and registering -- this screen's "new" -- last.
      toolbar: Phase2Scope.of(context)
          ? WorkspaceToolbar(
              actions: [
                ToolbarAction.refresh,
                if (_mayManage) ToolbarAction.newItem,
              ],
              newLabel: '+ Register',
              isEnabled: (action) =>
                  action == ToolbarAction.refresh || !_loading,
              onAction: (action) =>
                  action == ToolbarAction.newItem ? _register() : _load(),
              commands: [
                if (_mayManage && _isOffline) ...[
                  ToolbarCommand(
                    id: 'export-portal',
                    label: 'Export for portal',
                    icon: Icons.upload_file_outlined,
                    onPressed: _loading ? null : _exportForPortal,
                  ),
                  ToolbarCommand(
                    id: 'import-portal',
                    label: 'Import portal result',
                    icon: Icons.download_outlined,
                    onPressed: _loading ? null : _importPortalResult,
                  ),
                ],
                ToolbarCommand(
                  id: 'eway-bills-due',
                  label: 'E-way bills due',
                  icon: Icons.local_shipping_outlined,
                  // About the firm's books, not the selected row: behind "...".
                  menuOnly: true,
                  onPressed: _loading ? null : _showEwayBillsDue,
                ),
                if (_mayManage) ...[
                  ToolbarCommand(
                    id: 'raise-bill',
                    label: 'Raise bill',
                    icon: Icons.local_shipping_outlined,
                    onPressed: chosen != null && _mayRaiseBill(chosen)
                        ? () => _raiseEwayBill(chosen)
                        : null,
                  ),
                  ToolbarCommand(
                    id: 'cancel-bill',
                    label: 'Cancel bill',
                    icon: Icons.cancel_outlined,
                    onPressed: chosen != null &&
                            (_bills[chosen.salesInvoiceId]?.isGenerated ??
                                false)
                        ? () => _cancelEwayBill(chosen)
                        : null,
                  ),
                  // Were only in the row's own column (review, 2026-09-27).
                  ToolbarCommand(
                    id: 'withdraw',
                    label: 'Withdraw',
                    icon: Icons.undo,
                    onPressed: chosen != null && chosen.isRegistered
                        ? () => _cancelRegistration(chosen)
                        : null,
                  ),
                  ToolbarCommand(
                    id: 'try-again',
                    label: 'Try again',
                    icon: Icons.replay,
                    onPressed: chosen != null && chosen.isFailed
                        ? () => _registerOne(chosen.salesInvoiceId)
                        : null,
                  ),
                ],
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
          FilledButton.icon(
            onPressed: _mayManage && !_loading ? _register : null,
            icon: const Icon(Icons.verified_outlined),
            label: const Text('Register an invoice'),
          ),
          // The same actions as the row's last column, for the selected row.
          // With five columns the row's buttons sit past the right edge of a
          // laptop screen, and the owner could not find "Raise e-way bill"
          // at all (plan item 12.6, 2026-09-13).
          if (_mayManage && _isOffline) ...[
            OutlinedButton.icon(
              onPressed: _loading ? null : _exportForPortal,
              icon: const Icon(Icons.upload_file_outlined),
              label: const Text('Export for portal'),
            ),
            OutlinedButton.icon(
              onPressed: _loading ? null : _importPortalResult,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Import portal result'),
            ),
          ],
          if (_mayManage) ...[
            OutlinedButton.icon(
              onPressed: _selectedRow != null && _mayRaiseBill(_selectedRow!)
                  ? () => _raiseEwayBill(_selectedRow!)
                  : null,
              icon: const Icon(Icons.local_shipping_outlined),
              // Short, and not "E-way bill" (the column header): the toolbar has to
              // fit a 1366 window beside Register.
              label: const Text('Raise bill'),
            ),
            OutlinedButton.icon(
              onPressed: _selectedRow != null &&
                      (_bills[_selectedRow!.salesInvoiceId]?.isGenerated ?? false)
                  ? () => _cancelEwayBill(_selectedRow!)
                  : null,
              icon: const Icon(Icons.cancel_outlined),
              label: const Text('Cancel bill'),
            ),
          ],
        ],
      ),
      // Option C (owner, 2026-09-27): the registration's actions on a bar
      // that names it, above the grid. No total rides on the record or the
      // grid, so the bar names only the number, party and status.
      selectionBar: true,
      selection: chosen == null
          ? null
          : SelectionSummary.document(
              number: chosen.invoiceNumber,
              party: chosen.customerName,
              status: chosen.status,
              onClear: () => setState(() => _selectedId = null),
            ),
      searchPanel: const SizedBox.shrink(),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'A sandbox reference files nothing with the authority.',
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SandboxNotice(),
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
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing registered yet',
        message: 'Use “Register an invoice” above; what the authority '
            'answered appears here, refusals included.',
      );
    }
    // Phase 2: every step is on the selection bar, so no actions column, and
    // the grid truncates long references itself.
    if (Phase2Scope.of(context)) {
      return EnterpriseDataGrid<EInvoiceRegistrationRecord>(
        items: _rows,
        total: _rows.length,
        pageOffset: 0,
        rowsPerPage: _rows.length,
        availableRowsPerPage: [_rows.length],
        selectedId: _selectedId,
        columns: const [
          GridColumn(key: 'invoice', label: 'Invoice'),
          GridColumn(key: 'customer', label: 'Customer', priority: 1),
          GridColumn(key: 'filing', label: 'Filing', priority: 1),
          GridColumn(key: 'reference', label: 'Reference'),
          GridColumn(key: 'eway', label: 'E-way bill'),
        ],
        id: (row) => row.id,
        cells: (row) => [
          row.invoiceNumber.isEmpty ? '—' : row.invoiceNumber,
          row.customerName.isEmpty ? '—' : row.customerName,
          _providerLabel(row.provider),
          row.isRegistered
              ? row.referenceLabel
              : '${statusInWords(row.status)}'
                  '${row.errorMessage.isEmpty ? '' : ' — ${row.errorMessage}'}',
          _bills[row.salesInvoiceId]?.referenceLabel ?? '—',
        ],
        onSelect: (row) => setState(() => _selectedId = row.id),
        onPageChanged: (_) {},
      );
    }
    return EnterpriseDataGrid<EInvoiceRegistrationRecord>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'invoice', label: 'Invoice'),
        GridColumn(key: 'customer', label: 'Customer'),
        GridColumn(key: 'filing', label: 'Filing'),
        GridColumn(key: 'reference', label: 'Reference'),
        GridColumn(key: 'eway', label: 'E-way bill'),
        GridColumn(key: 'actions', label: ''),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.invoiceNumber.isEmpty ? '—' : row.invoiceNumber,
        row.customerName.isEmpty ? '—' : row.customerName,
        _providerLabel(row.provider),
        // Mode and reference together, always. A reference shown alone is one
        // somebody eventually presents at a check post.
        row.isRegistered
            ? row.referenceLabel
            : '${row.status}${row.errorMessage.isEmpty ? '' : ' — ${row.errorMessage}'}',
        _bills[row.salesInvoiceId]?.referenceLabel ?? '—',
        '',
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      // A real reference is 64 characters and, printed whole, pushed the
      // row's actions off the right of a 1366 screen; the cell truncates and
      // the whole value is in its tooltip.
      cellBuilder: (columnIndex, value, row) => switch (columnIndex) {
        5 => _actions(row),
        1 || 3 => Tooltip(
            message: value,
            child: SizedBox(
              width: columnIndex == 3 ? 200 : 160,
              child: Text(value, overflow: TextOverflow.ellipsis),
            ),
          ),
        _ => Text(value),
      },
    );
  }

  static String _providerLabel(String provider) => switch (provider) {
        'SANDBOX' => 'Sandbox',
        'OFFLINE' => 'Offline',
        '' => '—',
        _ => provider,
      };

  /// A registered invoice may carry a bill unless one already stands. A
  /// withdrawn or refused bill does not stand -- the service raises a fresh
  /// one over it -- so it is offered again rather than left to the API alone
  /// (D-CMP-13).
  bool _mayRaiseBill(EInvoiceRegistrationRecord row) {
    final EWayBillRecord? bill = _bills[row.salesInvoiceId];
    return row.isRegistered && (bill == null || !bill.isGenerated);
  }

  Widget _actions(EInvoiceRegistrationRecord row) {
    if (!_mayManage) return const SizedBox.shrink();
    final EWayBillRecord? bill = _bills[row.salesInvoiceId];
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_mayRaiseBill(row))
          TextButton(
            onPressed: () => _raiseEwayBill(row),
            // Not just "E-way bill": that is the column header beside it, and
            // a button whose label matches a header is one nobody can point
            // at -- including a test, which is how this was noticed.
            child: Text(bill == null ? 'Raise e-way bill' : 'Raise bill again'),
          ),
        if (bill != null && bill.isGenerated)
          TextButton(
            onPressed: () => _cancelEwayBill(row),
            child: const Text('Withdraw bill'),
          ),
        if (row.isRegistered)
          TextButton(
            onPressed: () => _cancelRegistration(row),
            child: const Text('Withdraw'),
          ),
        // A refusal was a dead end: the row showed why and offered nothing.
        // The service keeps the row and counts the attempt, so the retry is
        // the same call rather than a second kind of registration. Only a
        // refusal: a withdrawn IRN is never reissued for the same number
        // (D-CMP-6), so a withdrawn row offers nothing to press.
        if (row.isFailed)
          TextButton(
            onPressed: () => _registerOne(row.salesInvoiceId),
            child: const Text('Try again'),
          ),
      ],
    );
  }
}

/// Say, once and plainly, that nothing here reached the authority.
class SandboxNotice extends StatelessWidget {
  const SandboxNotice({super.key});

  /// What the notice says; phase 2 shows it behind the page line's (i).
  static const String text =
      'References marked sandbox are a rehearsal: nothing was filed '
      'with the tax authority and the number means nothing outside '
      'this system. Live filing needs this firm’s GSP credentials.';

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
          const Icon(Icons.science_outlined, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              'References marked sandbox are a rehearsal: nothing was filed '
              'with the tax authority and the number means nothing outside '
              'this system. Live filing needs this firm’s GSP credentials.',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}

/// Ask for what an e-way bill needs that the invoice cannot supply.
class EWayBillDialog extends StatefulWidget {
  const EWayBillDialog({super.key, this.onSave});

  /// Raises the bill; throws [ApiException] on a refusal, which the dialog
  /// shows without closing. Null closes with the details at once.
  final Future<void> Function(Json details)? onSave;

  @override
  State<EWayBillDialog> createState() => _EWayBillDialogState();
}

class _EWayBillDialogState extends State<EWayBillDialog>
    with SaveInDialog<EWayBillDialog> {
  final TextEditingController _distance = TextEditingController();
  final TextEditingController _vehicle = TextEditingController();
  final TextEditingController _transporterId = TextEditingController();
  final TextEditingController _transporterName = TextEditingController();

  String _mode = 'ROAD';
  String? _error;

  @override
  void dispose() {
    _distance.dispose();
    _vehicle.dispose();
    _transporterId.dispose();
    _transporterName.dispose();
    super.dispose();
  }

  void _submit() {
    // Optional: blank takes the distance on the delivery note(s) billed, and
    // the server says so if there is none. Typed, it has to be a distance.
    final String typed = _distance.text.trim();
    final double? distance = double.tryParse(typed);
    if (typed.isNotEmpty && (distance == null || distance <= 0)) {
      setState(() => _error = 'Enter how far the goods travel, in kilometres.');
      return;
    }
    // The server refuses this too. Restating it here keeps the typing on
    // screen rather than losing it to a round trip.
    if (_mode == 'ROAD' && _vehicle.text.trim().isEmpty) {
      setState(() => _error =
          'Goods moving by road need a vehicle number on the bill.');
      return;
    }
    submit<Json>(<String, dynamic>{
      if (typed.isNotEmpty) 'distance_km': typed,
      'transport_mode': _mode,
      if (_transporterId.text.trim().isNotEmpty)
        'transporter_id': _transporterId.text.trim(),
      if (_transporterName.text.trim().isNotEmpty)
        'transporter_name': _transporterName.text.trim(),
      if (_vehicle.text.trim().isNotEmpty)
        'vehicle_number': _vehicle.text.trim(),
    }, widget.onSave);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Raise an e-way bill'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              TextField(
                controller: _distance,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Distance (km)',
                  helperText: "Blank takes the delivery note's. The "
                      'authority sets the validity from this.',
                  helperMaxLines: 2,
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _mode,
                decoration: const InputDecoration(labelText: 'Moving by'),
                items: const [
                  DropdownMenuItem(value: 'ROAD', child: Text('Road')),
                  DropdownMenuItem(value: 'RAIL', child: Text('Rail')),
                  DropdownMenuItem(value: 'AIR', child: Text('Air')),
                  DropdownMenuItem(value: 'SHIP', child: Text('Ship')),
                ],
                onChanged: (value) => setState(() => _mode = value ?? _mode),
              ),
              if (_mode == 'ROAD') ...[
                const SizedBox(height: AppSpacing.md),
                TextField(
                  controller: _vehicle,
                  textCapitalization: TextCapitalization.characters,
                  decoration: const InputDecoration(
                    labelText: 'Vehicle number',
                    helperText: 'Required for road.',
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _transporterId,
                decoration: const InputDecoration(
                  labelText: 'Transporter GSTIN or enrolment number',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _transporterName,
                decoration:
                    const InputDecoration(labelText: 'Transporter name'),
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
        TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
        FilledButton(
          onPressed: saving ? null : _submit,
          child: const Text('Raise'),
        ),
      ],
    );
  }
}


/// The consignments of the last 30 days above the firm's e-way bill limit
/// that have none (backlog 77 row 10), each with the two ways to put that
/// right: raise the bill here, or record one raised on the portal.
class _EWayBillsDueDialog extends StatefulWidget {
  const _EWayBillsDueDialog({required this.api, required this.mayManage});

  final ApiClient api;
  final bool mayManage;

  @override
  State<_EWayBillsDueDialog> createState() => _EWayBillsDueDialogState();
}

class _EWayBillsDueDialogState extends State<_EWayBillsDueDialog> {
  EWayBillDueList? _due;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final EWayBillDueList due = await widget.api.ewayBillsDue();
      if (!mounted) return;
      setState(() {
        _due = due;
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

  Future<void> _step(
    Future<bool> Function(
      BuildContext,
      ApiClient, {
      String? invoiceId,
      String? noteId,
    }) step,
    EWayBillDue item,
    String done,
  ) async {
    final bool ok = await step(
      context,
      widget.api,
      invoiceId: item.isNote ? null : item.documentId,
      noteId: item.isNote ? item.documentId : null,
    );
    if (!ok || !mounted) return;
    NotificationService.show(context, done, kind: AppNotificationKind.success);
    await _load();
  }

  String _amount(String value) {
    final double? parsed = double.tryParse(value);
    return parsed == null ? value : '₹${indianAmount(parsed, full: true)}';
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final EWayBillDueList? due = _due;
    return AlertDialog(
      title: const Text('E-way bills due'),
      content: SizedBox(
        width: 640,
        height: 380,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Text(_error!, style: TextStyle(color: theme.colorScheme.error))
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Consignments of the last 30 days worth more than '
                        '${_amount(due?.limit ?? '')} with no e-way bill.',
                        key: const ValueKey('eway-due-limit'),
                        style: theme.textTheme.bodySmall,
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      Expanded(
                        child: (due?.items.isEmpty ?? true)
                            ? const Center(
                                child: Text(
                                  'Nothing is waiting for an e-way bill.',
                                ),
                              )
                            : ListView(
                                children: [
                                  for (final EWayBillDue item in due!.items)
                                    ListTile(
                                      key: ValueKey(
                                        'eway-due-${item.documentId}',
                                      ),
                                      dense: true,
                                      contentPadding: EdgeInsets.zero,
                                      title: Text(
                                        '${item.number}  ·  ${item.typeLabel}',
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      subtitle: Text(
                                        '${item.on}  ·  ${_amount(item.value)}',
                                      ),
                                      trailing: widget.mayManage
                                          ? Row(
                                              mainAxisSize: MainAxisSize.min,
                                              children: [
                                                TextButton(
                                                  onPressed: () => _step(
                                                    raiseEwayBillFor,
                                                    item,
                                                    'E-way bill raised.',
                                                  ),
                                                  child: const Text(
                                                    'Raise e-way bill',
                                                  ),
                                                ),
                                                TextButton(
                                                  onPressed: () => _step(
                                                    recordEwayBillFor,
                                                    item,
                                                    'E-way bill recorded.',
                                                  ),
                                                  child: const Text(
                                                    'Record e-way bill...',
                                                  ),
                                                ),
                                              ],
                                            )
                                          : null,
                                    ),
                                ],
                              ),
                      ),
                    ],
                  ),
      ),
      actions: [
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }
}

/// Choose the invoice to register.
///
/// A list rather than a free-text id: the person doing compliance knows the
/// invoice by its number and its customer, and neither is a UUID.
class _RegisterInvoiceDialog extends StatefulWidget {
  const _RegisterInvoiceDialog({required this.invoices});

  final List<Json> invoices;

  @override
  State<_RegisterInvoiceDialog> createState() => _RegisterInvoiceDialogState();
}

class _RegisterInvoiceDialogState extends State<_RegisterInvoiceDialog> {
  late String _invoiceId = '${widget.invoices.first['id']}';

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Register an invoice'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'The invoice is sent as it stands. A registration can only be '
                'withdrawn within 24 hours; after that a credit note is the '
                'way.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _invoiceId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Sales invoice'),
                items: [
                  for (final Json invoice in widget.invoices)
                    DropdownMenuItem<String>(
                      value: '${invoice['id']}',
                      // Whose bill it is: the list holds every customer's
                      // approved invoices, and number and total alone could
                      // not find one customer's (plan item 12.5, 2026-09-13).
                      child: Text(
                        '${invoice['invoice_number']} — '
                        '${invoice['customer_name'] ?? ''} — '
                        '${invoice['grand_total']}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (value) =>
                    setState(() => _invoiceId = value ?? _invoiceId),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_invoiceId),
            child: const Text('Register'),
          ),
        ],
      );
}

/// Choose the approved invoices to put in the portal's upload file.
class _ExportInvoicesDialog extends StatefulWidget {
  const _ExportInvoicesDialog({required this.invoices});

  final List<Json> invoices;

  @override
  State<_ExportInvoicesDialog> createState() => _ExportInvoicesDialogState();
}

class _ExportInvoicesDialogState extends State<_ExportInvoicesDialog> {
  final Set<String> _chosen = <String>{};

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Export for the portal'),
        content: SizedBox(
          width: 460,
          height: 360,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Each chosen invoice waits for its IRN until you import the '
                "portal's result.",
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.sm),
              Expanded(
                child: ListView(
                  children: [
                    for (final Json invoice in widget.invoices)
                      CheckboxListTile(
                        dense: true,
                        value: _chosen.contains('${invoice['id']}'),
                        onChanged: (on) => setState(() => on == true
                            ? _chosen.add('${invoice['id']}')
                            : _chosen.remove('${invoice['id']}')),
                        title: Text(
                          '${invoice['invoice_number']} — '
                          '${invoice['customer_name'] ?? ''} — '
                          '${invoice['grand_total']}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _chosen.isEmpty
                ? null
                : () => Navigator.of(context).pop(_chosen.toList()),
            child: Text('Export ${_chosen.length}'),
          ),
        ],
      );
}

/// What importing the portal's result did, with the numbers that need a look.
class _ImportResultDialog extends StatelessWidget {
  const _ImportResultDialog({required this.result});

  final OfflineEInvoiceImport result;

  Widget _line(BuildContext context, String label, List<String> numbers) {
    if (numbers.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Text(
        '$label: ${numbers.join(', ')}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Portal result imported'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('${result.registered.length} registered, '
                    '${result.failed.length} refused, '
                    '${result.unmatched.length} not matched, '
                    '${result.already.length} already registered.'),
                _line(context, 'Refused', result.failed),
                _line(context, 'Not matched', result.unmatched),
                _line(context, 'Already registered', result.already),
              ],
            ),
          ),
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      );
}
