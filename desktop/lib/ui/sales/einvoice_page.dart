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
        message: 'Register an approved invoice from the invoice itself; what '
            'the authority answered appears here.',
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
