// What the tax authority knows about this firm's invoices, and their movement.
//
// The one thing every view here must make impossible to miss is **which mode**
// a reference was made in. A sandbox registration is a rehearsal: nothing was
// filed, and the number means nothing outside this database. A screen that
// showed the reference alone would be handing somebody a document to present
// at a check post.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/einvoice.dart';
import '../../models/entities.dart';
import '../workspace/desktop_framework.dart';

/// List what has been registered, and act on one invoice at a time.
class EInvoicePage extends StatefulWidget {
  const EInvoicePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<EInvoicePage> createState() => _EInvoicePageState();
}

class _EInvoicePageState extends State<EInvoicePage> {
  List<EInvoiceRegistrationRecord> _rows = const [];
  final Map<String, EWayBillRecord> _bills = <String, EWayBillRecord>{};
  String? _error;
  String? _selectedId;
  bool _loading = true;

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
    final Set<String> registered = <String>{
      for (final EInvoiceRegistrationRecord row in _rows)
        if (row.isRegistered) row.salesInvoiceId,
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
      builder: (context) => const EWayBillDialog(),
    );
    if (details == null) return;
    await _run(
      () => widget.api
          .generateEwayBill(row.salesInvoiceId, details)
          .then((_) {}),
      'E-way bill raised.',
    );
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
  }) async {
    final TextEditingController controller = TextEditingController();
    final String? answer = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 420,
          child: TextField(
            controller: controller,
            autofocus: true,
            decoration: InputDecoration(labelText: 'Reason', helperText: hint),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('Withdraw'),
          ),
        ],
      ),
    );
    controller.dispose();
    return (answer == null || answer.isEmpty) ? null : answer;
  }

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
          FilledButton.icon(
            onPressed: _mayManage && !_loading ? _register : null,
            icon: const Icon(Icons.verified_outlined),
            label: const Text('Register an invoice'),
          ),
        ],
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
    return EnterpriseDataGrid<EInvoiceRegistrationRecord>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'reference', label: 'Reference'),
        GridColumn(key: 'eway', label: 'E-way bill'),
        GridColumn(key: 'actions', label: ''),
      ],
      id: (row) => row.id,
      cells: (row) => [
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
      cellBuilder: (columnIndex, value, row) =>
          columnIndex == 2 ? _actions(row) : Text(value),
    );
  }

  Widget _actions(EInvoiceRegistrationRecord row) {
    if (!_mayManage) return const SizedBox.shrink();
    final EWayBillRecord? bill = _bills[row.salesInvoiceId];
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (row.isRegistered && bill == null)
          TextButton(
            onPressed: () => _raiseEwayBill(row),
            // Not just "E-way bill": that is the column header beside it, and
            // a button whose label matches a header is one nobody can point
            // at -- including a test, which is how this was noticed.
            child: const Text('Raise e-way bill'),
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
        // the same call rather than a second kind of registration.
        if (!row.isRegistered)
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
  const EWayBillDialog({super.key});

  @override
  State<EWayBillDialog> createState() => _EWayBillDialogState();
}

class _EWayBillDialogState extends State<EWayBillDialog> {
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
    final double? distance = double.tryParse(_distance.text.trim());
    if (distance == null || distance <= 0) {
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
    Navigator.of(context).pop(<String, dynamic>{
      'distance_km': _distance.text.trim(),
      'transport_mode': _mode,
      if (_transporterId.text.trim().isNotEmpty)
        'transporter_id': _transporterId.text.trim(),
      if (_transporterName.text.trim().isNotEmpty)
        'transporter_name': _transporterName.text.trim(),
      if (_vehicle.text.trim().isNotEmpty)
        'vehicle_number': _vehicle.text.trim(),
    });
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
              TextField(
                controller: _distance,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Distance (km)',
                  helperText: 'The authority sets the validity from this.',
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
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(onPressed: _submit, child: const Text('Raise')),
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
                      child: Text(
                        '${invoice['invoice_number']} — '
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
