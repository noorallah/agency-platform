// Collection follow-up (backlog 87 #8, SG-8): the collection sheet, the
// promises customers have made, and the dialog that records one. Phase 2 only.

import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/payment_promise.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

const int _pageSize = 50;

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// What the promise status reads as: "Due today", not DUE_TODAY.
String _statusLabel(String status) {
  if (status.isEmpty) return '';
  final String words = status.toLowerCase().replaceAll('_', ' ');
  return words[0].toUpperCase() + words.substring(1);
}

StatusBadgeTone _statusTone(String status) => switch (status) {
      'KEPT' => StatusBadgeTone.success,
      'DUE_TODAY' => StatusBadgeTone.warning,
      'BROKEN' => StatusBadgeTone.danger,
      _ => StatusBadgeTone.neutral,
    };

/// One member picker, shared by the filters and the dialog. Values are user
/// ids; the empty string is "everybody" or "nobody", whichever [anyLabel]
/// says.
Widget _memberPicker({
  required Key key,
  required String label,
  required String anyLabel,
  required List<FirmMember> members,
  required String value,
  required ValueChanged<String>? onChanged,
}) {
  final List<DropdownMenuItem<String>> items = [
    DropdownMenuItem(value: '', child: Text(anyLabel)),
    for (final FirmMember member in members)
      DropdownMenuItem(value: member.userId, child: Text(member.label)),
  ];
  // A collector who has left the firm stays selectable as themselves, or the
  // dropdown asserts on a value it does not hold.
  if (value.isNotEmpty && !members.any((member) => member.userId == value)) {
    items.add(DropdownMenuItem(value: value, child: const Text('Former member')));
  }
  return DropdownButtonFormField<String>(
    key: key,
    isExpanded: true,
    initialValue: value,
    decoration: InputDecoration(labelText: label, isDense: true),
    items: items,
    onChanged: onChanged == null ? null : (picked) => onChanged(picked ?? ''),
  );
}

/// Record what a customer promised to pay and by when. Pops the saved promise
/// map; stays open with the server's message on a refusal.
class PaymentPromiseDialog extends StatefulWidget {
  const PaymentPromiseDialog({
    super.key,
    required this.api,
    required this.customerId,
    required this.customerName,
    this.salesInvoiceId,
    this.invoiceNumber = '',
    this.amount = '',
    this.collectorId,
  });

  final ApiClient api;
  final String customerId;
  final String customerName;

  /// Null makes the promise on the account rather than on a bill.
  final String? salesInvoiceId;
  final String invoiceNumber;

  /// What the box starts at -- the bill's outstanding.
  final String amount;
  final String? collectorId;

  @override
  State<PaymentPromiseDialog> createState() => _PaymentPromiseDialogState();
}

class _PaymentPromiseDialogState extends State<PaymentPromiseDialog>
    with SaveInDialog {
  late final TextEditingController _amount =
      TextEditingController(text: _money(widget.amount));
  final TextEditingController _note = TextEditingController();
  DateTime _promisedOn = DateTime.now();
  late String _collectorId = widget.collectorId ?? '';
  List<FirmMember> _members = const [];
  bool _membersLoaded = false;
  String? _problem;

  @override
  void initState() {
    super.initState();
    unawaited(_loadMembers());
  }

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _loadMembers() async {
    try {
      final List<FirmMember> members = await widget.api.firmMembers();
      if (mounted) {
        setState(() {
          _members = members;
          _membersLoaded = true;
        });
      }
    } on ApiException {
      // No picker, and no collector is sent: a missing list is not a reason
      // to refuse the promise.
    }
  }

  Future<void> _pickDate() async {
    final DateTime today = DateTime.now();
    final DateTime first = DateTime(today.year, today.month, today.day);
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _promisedOn.isBefore(first) ? first : _promisedOn,
      firstDate: first,
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _promisedOn = picked);
  }

  void _save() {
    final double? amount = double.tryParse(_amount.text.trim());
    final DateTime today = DateTime.now();
    final DateTime first = DateTime(today.year, today.month, today.day);
    String? problem;
    if (amount == null || amount <= 0) {
      problem = 'The amount must be more than zero.';
    } else if (DateTime(_promisedOn.year, _promisedOn.month, _promisedOn.day)
        .isBefore(first)) {
      problem = 'The promised date cannot be before today.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<Json>(
      () => widget.api.recordPaymentPromise(
        customerId: widget.customerId,
        salesInvoiceId: widget.salesInvoiceId,
        promisedOn: _iso(_promisedOn),
        amount: _amount.text.trim(),
        note: _note.text,
        collectorId: _membersLoaded && _collectorId.isNotEmpty
            ? _collectorId
            : null,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final String target = widget.invoiceNumber.isEmpty
        ? 'on the account'
        : 'on bill ${widget.invoiceNumber}';
    return AlertDialog(
      title: const Text('Record a payment promise'),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              Text('${widget.customerName}, $target',
                  style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.md),
              InkWell(
                key: const ValueKey('promise-date'),
                onTap: saving ? null : () => unawaited(_pickDate()),
                child: InputDecorator(
                  decoration: const InputDecoration(labelText: 'Promised on'),
                  child: Text(_iso(_promisedOn)),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('promise-amount'),
                controller: _amount,
                enabled: !saving,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Amount'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('promise-note'),
                controller: _note,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Note'),
              ),
              if (_membersLoaded) ...[
                const SizedBox(height: AppSpacing.md),
                _memberPicker(
                  key: const ValueKey('promise-collector'),
                  label: 'Collector',
                  anyLabel: 'Nobody in particular',
                  members: _members,
                  value: _collectorId,
                  onChanged: saving
                      ? null
                      : (value) => setState(() => _collectorId = value),
                ),
              ],
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(_problem!,
                      key: const ValueKey('promise-problem'),
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('promise-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save promise'),
        ),
      ],
    );
  }
}

/// The bills still owing, by collector then customer, with the promise
/// standing against each. Record a promise on a row; print the sheet a
/// collector carries.
class CollectionSheetPage extends StatefulWidget {
  const CollectionSheetPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Tests inject this, because a widget test cannot open a save panel.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<CollectionSheetPage> createState() => _CollectionSheetPageState();
}

class _CollectionSheetPageState extends State<CollectionSheetPage> {
  List<CollectionSheetRow> _rows = const [];
  List<FirmMember> _members = const [];
  String _collectorId = '';
  bool _overdueOnly = false;
  DateTime? _asOf;
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  String? _error;
  String? _selectedId;

  bool get _mayView => widget.permissions.hasPermission('RECEIPT_VIEW');
  bool get _mayWrite => widget.permissions.hasPermission('RECEIPT_CREATE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) {
      unawaited(_loadMembers());
      unawaited(_load());
    }
  }

  Future<void> _loadMembers() async {
    try {
      final List<FirmMember> members = await widget.api.firmMembers();
      if (mounted) setState(() => _members = members);
    } on ApiException {
      // The filter just stays at everybody.
    }
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final Json response = await widget.api.collectionSheet(
        page: _page,
        pageSize: _pageSize,
        collectorId: _collectorId.isEmpty ? null : _collectorId,
        asOf: _asOf == null ? null : _iso(_asOf!),
        overdueOnly: _overdueOnly,
      );
      final List<CollectionSheetRow> rows = [
        for (final dynamic item in (response['data'] as List? ?? const []))
          if (item is Map)
            CollectionSheetRow.fromJson(Map<String, dynamic>.from(item)),
      ];
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _total = pagedTotal(response, fallback: rows.length);
        if (!rows.any((row) => row.rowId == _selectedId)) _selectedId = null;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _rows = const [];
        _total = 0;
        _loading = false;
      });
    }
  }

  CollectionSheetRow? get _selected =>
      _rows.where((row) => row.rowId == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _record(CollectionSheetRow row) async {
    final Object? saved = await showDialog<Object>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PaymentPromiseDialog(
        api: widget.api,
        customerId: row.customerId,
        customerName: row.customerName,
        salesInvoiceId: row.invoiceId,
        invoiceNumber: row.invoiceNumber,
        amount: row.outstanding,
        collectorId: row.collectorId,
      ),
    );
    if (saved == null || !mounted) return;
    _tell('Promise recorded.', AppNotificationKind.success);
    await _load();
  }

  Future<void> _print() async {
    try {
      final List<int> pdf = await widget.api.collectionSheetPdf(
        collectorId: _collectorId.isEmpty ? null : _collectorId,
        asOf: _asOf == null ? null : _iso(_asOf!),
        overdueOnly: _overdueOnly,
      );
      if (!mounted) return;
      const String name = 'Collection sheet.pdf';
      if (widget.saveBytesOverride != null) {
        await widget.saveBytesOverride!(name, pdf);
      } else {
        final FileSaveLocation? location = await getSaveLocation(
          suggestedName: name,
          acceptedTypeGroups: const [
            XTypeGroup(label: 'PDF file', extensions: ['pdf']),
          ],
        );
        if (location == null) return;
        await File(location.path).writeAsBytes(pdf, flush: true);
      }
      if (!mounted) return;
      _tell('The collection sheet was saved.', AppNotificationKind.success);
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  Future<void> _pickAsOf() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _asOf ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    setState(() => _asOf = picked);
    await _load(requestedPage: 1);
  }

  static const List<GridColumn> _columns = [
    GridColumn(key: 'collector', label: 'Collector'),
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'phone', label: 'Phone', priority: 2),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'bill-date', label: 'Bill date', priority: 2),
    GridColumn(key: 'due', label: 'Due', priority: 2),
    GridColumn(key: 'overdue', label: 'Days overdue', numeric: true),
    GridColumn(key: 'outstanding', label: 'Outstanding', numeric: true),
    GridColumn(key: 'promised-on', label: 'Promised on'),
    GridColumn(
        key: 'promised-amount',
        label: 'Promised amount',
        numeric: true,
        priority: 2),
    GridColumn(key: 'promise-status', label: 'Promise status'),
    GridColumn(key: 'note', label: 'Note', priority: 3),
  ];

  List<String> _cells(CollectionSheetRow row) => [
        row.collectorName,
        row.customerName,
        row.customerPhone,
        row.invoiceNumber,
        row.invoiceDate,
        row.dueDate,
        '${row.daysOverdue}',
        row.outstanding,
        row.promisedOn,
        row.promisedAmount,
        row.promiseStatus,
        row.promiseNote,
      ];

  Widget _filters() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 240,
          child: _memberPicker(
            key: ValueKey('sheet-collector-$_collectorId'),
            label: 'Collector',
            anyLabel: 'Everybody',
            members: _members,
            value: _collectorId,
            onChanged: (value) {
              setState(() => _collectorId = value);
              unawaited(_load(requestedPage: 1));
            },
          ),
        ),
        FilterChip(
          key: const ValueKey('sheet-overdue-only'),
          label: const Text('Overdue only'),
          selected: _overdueOnly,
          onSelected: (on) {
            setState(() => _overdueOnly = on);
            unawaited(_load(requestedPage: 1));
          },
        ),
        OutlinedButton.icon(
          key: const ValueKey('sheet-as-of'),
          onPressed: () => unawaited(_pickAsOf()),
          icon: const Icon(Icons.event_outlined, size: 16),
          label: Text(_asOf == null ? 'As of today' : 'As of ${_iso(_asOf!)}'),
        ),
        if (_asOf != null)
          TextButton(
            key: const ValueKey('sheet-as-of-clear'),
            onPressed: () {
              setState(() => _asOf = null);
              unawaited(_load(requestedPage: 1));
            },
            child: const Text('Back to today'),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'The collection sheet belongs to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see the collection sheet',
        message: 'Reading it needs the view receipts permission.',
      );
    }
    final CollectionSheetRow? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Every bill still owing, by collector and customer, with the '
          'promise standing against it. Record what a customer promises, '
          'and print the sheet a collector carries.',
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (action) => true,
        onAction: (action) => unawaited(_load()),
        commands: [
          if (_mayWrite)
            ToolbarCommand(
              id: 'record-promise',
              label: 'Record promise',
              icon: Icons.handshake_outlined,
              onPressed:
                  picked == null ? null : () => unawaited(_record(picked)),
            ),
          ToolbarCommand(
            id: 'print-sheet',
            label: 'Print sheet',
            icon: Icons.print_outlined,
            onPressed: () => unawaited(_print()),
          ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary(
              title: picked.customerName,
              detail: [
                picked.invoiceNumber,
                'owes ${_money(picked.outstanding)}',
              ].where((part) => part.isNotEmpty).join(' · '),
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.sm),
          _filters(),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: AppSpacing.md),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _rows.isEmpty
                    ? const WorkspaceEmptyState(
                        title: 'Nothing to collect',
                        message: 'No bill matches these filters.',
                      )
                    : EnterpriseDataGrid<CollectionSheetRow>(
                        items: _rows,
                        total: _total,
                        pageOffset: (_page - 1) * _pageSize,
                        rowsPerPage: _pageSize,
                        availableRowsPerPage: const [_pageSize],
                        selectedId: _selectedId,
                        columns: _columns,
                        id: (row) => row.rowId,
                        cells: _cells,
                        onSelect: (row) =>
                            setState(() => _selectedId = row.rowId),
                        onOpen: (row) =>
                            setState(() => _selectedId = row.rowId),
                        onPageChanged: (offset) {
                          final int next = offset ~/ _pageSize + 1;
                          if (next != _page) {
                            unawaited(_load(requestedPage: next));
                          }
                        },
                        cellBuilder: (columnIndex, value, item) {
                          if (_columns[columnIndex].key == 'promise-status') {
                            if (value.isEmpty) return const SizedBox.shrink();
                            return Align(
                              alignment: Alignment.centerLeft,
                              child: StatusBadge(
                                label: _statusLabel(value),
                                tone: _statusTone(value),
                              ),
                            );
                          }
                          return Tooltip(
                            message: value,
                            child: SizedBox(
                              width: double.infinity,
                              child: Text(value,
                                  overflow: TextOverflow.ellipsis),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: picked != null,
        message: 'Collection sheet',
      ),
    );
  }
}

/// The promises customers have made, what became of each, and the ones to
/// chase today.
class PaymentPromisesPage extends StatefulWidget {
  const PaymentPromisesPage({
    super.key,
    required this.api,
    required this.preferences,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final DesktopPreferencesService preferences;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PaymentPromisesPage> createState() => _PaymentPromisesPageState();
}

class _PaymentPromisesPageState extends State<PaymentPromisesPage> {
  static const List<String> _statuses = [
    'PENDING',
    'DUE_TODAY',
    'KEPT',
    'BROKEN',
    'WITHDRAWN',
  ];

  List<PaymentPromise> _rows = const [];
  String _status = '';
  bool _dueToday = false;
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  String? _error;
  String? _selectedId;

  bool get _mayView => widget.permissions.hasPermission('RECEIPT_VIEW');
  bool get _mayWrite => widget.permissions.hasPermission('RECEIPT_CREATE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final Json response = _dueToday
          ? await widget.api
              .paymentPromisesDueToday(page: _page, pageSize: _pageSize)
          : await widget.api.paymentPromises(
              page: _page,
              pageSize: _pageSize,
              status: _status.isEmpty ? null : _status,
            );
      final List<PaymentPromise> rows = [
        for (final dynamic item in (response['data'] as List? ?? const []))
          if (item is Map)
            PaymentPromise.fromJson(Map<String, dynamic>.from(item)),
      ];
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _total = pagedTotal(response, fallback: rows.length);
        if (!rows.any((row) => row.id == _selectedId)) _selectedId = null;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _rows = const [];
        _total = 0;
        _loading = false;
      });
    }
  }

  PaymentPromise? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  Future<void> _withdraw(PaymentPromise promise) async {
    final String? reason = await askForReason(
      context,
      title: 'Withdraw the promise',
      explanation: '${promise.customerName}\'s promise of '
          '${_money(promise.amount)} for ${promise.promisedOn} is taken back. '
          'The record stays, with the reason.',
      confirmLabel: 'Withdraw',
      cancelLabel: 'Keep it',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.withdrawPaymentPromise(promise.id, reason: reason);
      if (!mounted) return;
      _tell('The promise was withdrawn.', AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      _tell(error.message, AppNotificationKind.error);
    }
  }

  static const List<GridColumn> _columns = [
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'promised-on', label: 'Promised on'),
    GridColumn(key: 'amount', label: 'Amount', numeric: true),
    GridColumn(key: 'received', label: 'Received', numeric: true),
    GridColumn(key: 'status', label: 'Status'),
    GridColumn(key: 'collector', label: 'Collector', priority: 2),
    GridColumn(key: 'recorded-on', label: 'Recorded on', priority: 2),
    GridColumn(key: 'recorded-by', label: 'Recorded by', priority: 3),
    GridColumn(key: 'note', label: 'Note', priority: 3),
  ];

  List<String> _cells(PaymentPromise row) => [
        row.customerName,
        row.invoiceNumber.isEmpty ? 'On account' : row.invoiceNumber,
        row.promisedOn,
        row.amount,
        row.receivedAmount,
        row.status,
        row.collectorName,
        row.recordedOn,
        row.recordedByName,
        row.note,
      ];

  Widget _filters() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        FilterChip(
          key: const ValueKey('promises-due-today'),
          label: const Text('To chase today'),
          selected: _dueToday,
          onSelected: (on) {
            setState(() => _dueToday = on);
            unawaited(_load(requestedPage: 1));
          },
        ),
        SizedBox(
          width: 200,
          child: DropdownButtonFormField<String>(
            key: ValueKey('promises-status-$_status'),
            isExpanded: true,
            initialValue: _status,
            decoration:
                const InputDecoration(labelText: 'Status', isDense: true),
            items: [
              const DropdownMenuItem(value: '', child: Text('Any status')),
              for (final String status in _statuses)
                DropdownMenuItem(value: status, child: Text(_statusLabel(status))),
            ],
            onChanged: _dueToday
                ? null
                : (value) {
                    setState(() => _status = value ?? '');
                    unawaited(_load(requestedPage: 1));
                  },
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Payment promises belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see payment promises',
        message: 'Reading them needs the view receipts permission.',
      );
    }
    final PaymentPromise? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'What customers have promised to pay and by when. A promise '
          'is kept when the money arrives, and broken when its day passes '
          'without it. Promises move no money.',
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (action) => true,
        onAction: (action) => unawaited(_load()),
        commands: [
          if (_mayWrite)
            ToolbarCommand(
              id: 'withdraw-promise',
              label: 'Withdraw',
              icon: Icons.undo_outlined,
              onPressed: picked != null && picked.isOpen
                  ? () => unawaited(_withdraw(picked))
                  : null,
            ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary(
              title: picked.customerName,
              detail: [
                picked.invoiceNumber,
                _statusLabel(picked.status),
                _money(picked.amount),
              ].where((part) => part.isNotEmpty).join(' · '),
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.sm),
          _filters(),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: AppSpacing.md),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _rows.isEmpty
                    ? WorkspaceEmptyState(
                        title: _dueToday
                            ? 'Nothing to chase today'
                            : 'No promises yet',
                        message: _dueToday
                            ? 'No promise is due today, and none is broken '
                                'and still open.'
                            : 'Record one from the collection sheet.',
                      )
                    : EnterpriseDataGrid<PaymentPromise>(
                        items: _rows,
                        total: _total,
                        pageOffset: (_page - 1) * _pageSize,
                        rowsPerPage: _pageSize,
                        availableRowsPerPage: const [_pageSize],
                        selectedId: _selectedId,
                        columns: _columns,
                        id: (row) => row.id,
                        cells: _cells,
                        onSelect: (row) => setState(() => _selectedId = row.id),
                        onOpen: (row) => setState(() => _selectedId = row.id),
                        onPageChanged: (offset) {
                          final int next = offset ~/ _pageSize + 1;
                          if (next != _page) {
                            unawaited(_load(requestedPage: next));
                          }
                        },
                      ),
          ),
        ],
      ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: picked != null,
        message: 'Payment promises',
      ),
    );
  }
}
