// Bills of Entry (PG-12 part B): the customs document that carries the duty
// on imported goods into the landed cost. A draft is typed and changed; posting
// splits the duty between stock, cost of goods sold and expense and takes the
// IGST as input credit. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bill_of_entry.dart';
import '../../models/entities.dart';
import '../../models/goods_receipt.dart';
import '../../models/product.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'purchase_requisition_page.dart' show ProductSearchBox;

String _vendorName(Vendor v) => v.displayName.isEmpty ? v.name : v.displayName;

String _today() => DateTime.now().toIso8601String().split('T').first;

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? '—' : parsed.toStringAsFixed(2);
}

/// List the Bills of Entry, raise and change drafts, and post or cancel them.
class BillOfEntryPage extends StatefulWidget {
  const BillOfEntryPage({
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
  State<BillOfEntryPage> createState() => _BillOfEntryPageState();
}

class _BillOfEntryPageState extends State<BillOfEntryPage> {
  List<BillOfEntry> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  /// '' all, else DRAFT, POSTED or CANCELLED.
  String _status = '';

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('BILL_OF_ENTRY_VIEW');
  bool get _mayManage => _may('BILL_OF_ENTRY_MANAGE');
  bool get _mayApprove => _may('PURCHASE_APPROVE');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<BillOfEntry> page =
          await widget.api.billsOfEntry(status: _status);
      if (!mounted) return;
      setState(() {
        _rows = page.items;
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

  BillOfEntry? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  void _say(String message, {bool error = false}) {
    if (!mounted) return;
    NotificationService.show(
      context,
      message,
      kind: error ? AppNotificationKind.error : AppNotificationKind.success,
    );
  }

  Future<void> _open(BillOfEntry? row) async {
    // The list row carries everything but is read again, so the editor opens
    // on the version the server holds now.
    BillOfEntry? full = row;
    if (row != null) {
      try {
        full = await widget.api.billOfEntry(row.id);
      } on ApiException catch (error) {
        _say(error.message, error: true);
        return;
      }
    }
    if (!mounted) return;
    final BillOfEntry? saved = await showDialog<BillOfEntry>(
      context: context,
      barrierDismissible: false,
      builder: (_) => BillOfEntryDialog(
        api: widget.api,
        existing: full,
        mayManage: _mayManage,
        mayApprove: _mayApprove,
      ),
    );
    if (saved == null || !mounted) return;
    _say('Bill of Entry ${saved.label} ${_saidAs(saved)}.');
    _selectedId = saved.id;
    await _load();
  }

  String _saidAs(BillOfEntry saved) => switch (saved.status) {
        'POSTED' => 'posted',
        'CANCELLED' => 'cancelled',
        _ => 'saved',
      };

  Future<void> _post(BillOfEntry row) async {
    try {
      final BillOfEntry done = await widget.api.postBillOfEntry(row.id);
      _say('Bill of Entry ${done.label} posted.');
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _cancel(BillOfEntry row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel Bill of Entry ${row.label}',
      explanation: 'The journal is reversed and the duty comes off the '
          'stock cost. The reason is kept with the document.',
      confirmLabel: 'Cancel the Bill of Entry',
    );
    if (reason == null) return;
    try {
      final BillOfEntry done =
          await widget.api.cancelBillOfEntry(row.id, reason);
      _say('Bill of Entry ${done.label} cancelled.');
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  Future<void> _delete(BillOfEntry row) async {
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete draft ${row.label}'),
        content: const Text('Only a draft can be deleted.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          FilledButton(
            key: const ValueKey('boe-delete-confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await widget.api.deleteBillOfEntry(row.id);
      _say('Draft ${row.label} deleted.');
      _selectedId = null;
      await _load();
    } on ApiException catch (error) {
      _say(error.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Bills of Entry belong to one firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see Bills of Entry',
        message: 'Reading them needs the view Bills of Entry permission.',
      );
    }
    final BillOfEntry? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A Bill of Entry carries the customs duty on imported goods. '
          'Posting adds the duty to the stock cost and takes the IGST as '
          'input credit.',
      toolbar: _toolbar(picked),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.label,
              party: picked.vendorName,
              status: picked.status,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Bills of Entry',
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
          Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: AppSpacing.sm),
        Expanded(child: _grid()),
      ],
    );
  }

  WorkspaceToolbar _toolbar(BillOfEntry? row) => WorkspaceToolbar(
        trailing: [
          Phase2MenuChip<String>(
            key: const ValueKey('boe-status-filter'),
            label: 'Show: ${switch (_status) {
              'DRAFT' => 'Drafts',
              'POSTED' => 'Posted',
              'CANCELLED' => 'Cancelled',
              _ => 'All',
            }}',
            itemBuilder: (_) => const [
              PopupMenuItem<String>(value: '', child: Text('All')),
              PopupMenuItem<String>(value: 'DRAFT', child: Text('Drafts')),
              PopupMenuItem<String>(value: 'POSTED', child: Text('Posted')),
              PopupMenuItem<String>(
                  value: 'CANCELLED', child: Text('Cancelled')),
            ],
            onSelected: (value) {
              setState(() {
                _status = value;
                _selectedId = null;
              });
              unawaited(_load());
            },
          ),
        ],
        actions: [
          if (_mayManage) ToolbarAction.newItem,
          ToolbarAction.view,
          ToolbarAction.refresh,
        ],
        isEnabled: (action) => action != ToolbarAction.view || row != null,
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_open(null));
            case ToolbarAction.view:
              if (row != null) unawaited(_open(row));
            default:
              unawaited(_load());
          }
        },
        commands: [
          if (_mayApprove)
            ToolbarCommand(
              id: 'post',
              label: 'Post',
              icon: Icons.task_alt,
              onPressed: row != null && row.isDraft
                  ? () => unawaited(_post(row))
                  : null,
            ),
          if (_mayApprove)
            ToolbarCommand(
              id: 'cancel',
              label: 'Cancel',
              icon: Icons.cancel_outlined,
              onPressed: row != null && row.isPosted
                  ? () => unawaited(_cancel(row))
                  : null,
            ),
          if (_mayManage)
            ToolbarCommand(
              id: 'delete',
              label: 'Delete',
              icon: Icons.delete_outline,
              onPressed: row != null && row.isDraft
                  ? () => unawaited(_delete(row))
                  : null,
            ),
        ],
      );

  late final ColumnChoice<BillOfEntry> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'bills-of-entry.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Document'),
        cell: (item) => item.label,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'boe', label: 'BoE number'),
        cell: (item) => item.boeNumber,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'BoE date'),
        cell: (item) => item.boeDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'port', label: 'Port'),
        cell: (item) => item.portCode,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'supplier', label: 'Supplier'),
        cell: (item) => item.vendorName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'value', label: 'Assessable value'),
        cell: (item) => _money(item.assessableValue),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'duty', label: 'Total duty'),
        cell: (item) => _money(item.totalDuty),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
    ],
  );

  Widget _grid() {
    if (_rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No Bills of Entry',
        message: 'Record the customs paperwork for imported goods.',
      );
    }
    return EnterpriseDataGrid<BillOfEntry>(
      items: _rows,
      total: _rows.length,
      pageOffset: 0,
      rowsPerPage: _rows.length,
      availableRowsPerPage: [_rows.length],
      selectedId: _selectedId,
      columns: _columns.gridColumns,
      id: (row) => row.id,
      cells: _columns.cells,
      onSelect: (row) => setState(() => _selectedId = row.id),
      onOpen: (row) {
        setState(() => _selectedId = row.id);
        unawaited(_open(row));
      },
      onPageChanged: (_) {},
    );
  }
}

/// One item while it is being typed. A blank amount is left out of the call,
/// and the server works it out from its rate.
class _LineEdit {
  _LineEdit([BoeLine? line]) {
    if (line == null) return;
    productId = line.productId;
    product.text = line.productCode.isEmpty && line.productName.isEmpty
        ? ''
        : '${line.productCode} · ${line.productName}';
    quantity.text = _trimZeros(line.quantity);
    assessable.text = _trimZeros(line.assessableValue);
    bcdRate.text = _trimZeros(line.bcdRate);
    swsRate.text = _trimZeros(line.swsRate);
    igstRate.text = _trimZeros(line.igstRate);
    // A typed amount wins over its rate, so an amount the server worked out
    // is not put back in its box: it would turn a computed figure into an
    // override.
    computed = line;
  }

  String productId = '';
  BoeLine? computed;
  final TextEditingController product = TextEditingController();
  final TextEditingController quantity = TextEditingController();
  final TextEditingController assessable = TextEditingController();
  final TextEditingController bcdRate = TextEditingController();
  final TextEditingController bcdAmount = TextEditingController();
  final TextEditingController swsRate = TextEditingController();
  final TextEditingController swsAmount = TextEditingController();
  final TextEditingController igstRate = TextEditingController();
  final TextEditingController igstAmount = TextEditingController();
  final TextEditingController cessAmount = TextEditingController();

  static String _trimZeros(String value) {
    if (!value.contains('.')) return value;
    return value.replaceFirst(RegExp(r'\.?0+$'), '');
  }

  List<TextEditingController> get _all => [
        product,
        quantity,
        assessable,
        bcdRate,
        bcdAmount,
        swsRate,
        swsAmount,
        igstRate,
        igstAmount,
        cessAmount,
      ];

  void dispose() {
    for (final TextEditingController c in _all) {
      c.dispose();
    }
  }

  /// A number typed in one of the optional boxes: null when blank, NaN when
  /// it is not a number or is negative.
  static double? optional(TextEditingController c) {
    final String text = c.text.trim();
    if (text.isEmpty) return null;
    final double? value = double.tryParse(text);
    return value == null || value < 0 ? double.nan : value;
  }

  Json toJson() {
    final Json body = <String, dynamic>{
      'product_id': productId,
      'quantity': quantity.text.trim(),
      'assessable_value': assessable.text.trim(),
    };
    final Map<String, TextEditingController> optionals = {
      'bcd_rate': bcdRate,
      'bcd_amount': bcdAmount,
      'sws_rate': swsRate,
      'sws_amount': swsAmount,
      'igst_rate': igstRate,
      'igst_amount': igstAmount,
      'cess_amount': cessAmount,
    };
    for (final MapEntry<String, TextEditingController> entry
        in optionals.entries) {
      if (entry.value.text.trim().isNotEmpty) {
        body[entry.key] = entry.value.text.trim();
      }
    }
    return body;
  }
}

/// Raise, change or read a Bill of Entry. Pops the saved [BillOfEntry]; stays
/// open with the server's message when refused. Nothing is prefilled: a blank
/// currency and rate take the linked bill's, and a blank amount is worked out.
class BillOfEntryDialog extends StatefulWidget {
  const BillOfEntryDialog({
    super.key,
    required this.api,
    this.existing,
    this.mayManage = true,
    this.mayApprove = false,
  });

  final ApiClient api;
  final BillOfEntry? existing;
  final bool mayManage;
  final bool mayApprove;

  @override
  State<BillOfEntryDialog> createState() => _BillOfEntryDialogState();
}

class _BillOfEntryDialogState extends State<BillOfEntryDialog>
    with SaveInDialog<BillOfEntryDialog> {
  List<Vendor> _vendors = const [];
  String _vendorId = '';
  late String _boeDate;
  bool _loading = true;
  String? _problem;
  final TextEditingController _boeNumber = TextEditingController();
  final TextEditingController _port = TextEditingController();
  final TextEditingController _currency = TextEditingController();
  final TextEditingController _rate = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  final List<_LineEdit> _lines = [];

  List<Json> _bills = const [];
  List<GoodsReceiptRecord> _receipts = const [];
  final Set<String> _billIds = {};
  final Set<String> _receiptIds = {};

  BillOfEntry? get _record => widget.existing;
  bool get _editable =>
      widget.mayManage && (_record == null || _record!.isDraft) && !saving;

  @override
  void initState() {
    super.initState();
    final BillOfEntry? b = _record;
    _boeDate = b != null && b.boeDate.isNotEmpty ? b.boeDate : _today();
    if (b != null) {
      _vendorId = b.vendorId;
      _boeNumber.text = b.boeNumber;
      _port.text = b.portCode;
      _currency.text = b.currencyCode;
      _rate.text = b.exchangeRate.contains('.')
          ? b.exchangeRate.replaceFirst(RegExp(r'\.?0+$'), '')
          : b.exchangeRate;
      _remarks.text = b.remarks;
      for (final BoeLine line in b.lines) {
        _lines.add(_LineEdit(line));
      }
      _billIds.addAll(b.invoices.map((e) => e.id));
      _receiptIds.addAll(
          b.receipts.where((e) => !e.viaInvoice).map((e) => e.id));
    } else {
      _lines.add(_LineEdit());
    }
    unawaited(_loadVendors());
  }

  @override
  void dispose() {
    _boeNumber.dispose();
    _port.dispose();
    _currency.dispose();
    _rate.dispose();
    _remarks.dispose();
    for (final _LineEdit line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  Future<void> _loadVendors() async {
    try {
      final List<Vendor> vendors =
          await fetchAllPages((page) => widget.api.vendors(page: page));
      if (!mounted) return;
      setState(() {
        _vendors = vendors;
        _loading = false;
      });
      if (_vendorId.isNotEmpty) unawaited(_loadLinks());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        saveError = error.message;
        _loading = false;
      });
    }
  }

  /// That supplier's bills and receipts, to tick the ones the goods came on.
  Future<void> _loadLinks() async {
    final String vendorId = _vendorId;
    if (vendorId.isEmpty) return;
    try {
      final Json bills = await widget.api.documentPage(
        'purchase-invoices',
        pageSize: 100,
        additionalQuery: {'vendor_id': vendorId},
      );
      final PagedResult<GoodsReceiptRecord> receipts = await widget.api
          .goodsReceipts(pageSize: 100, filters: {'vendor_id': vendorId});
      if (!mounted || vendorId != _vendorId) return;
      final Object? data = bills['data'];
      setState(() {
        _bills = [
          for (final Object? row in data is List
              ? data
              : data is Map
                  ? data['items'] as List? ?? const []
                  : const [])
            if (row is Map) Map<String, dynamic>.from(row),
        ];
        _receipts = receipts.items;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => saveError = error.message);
    }
  }

  void _chooseVendor(String id) {
    setState(() {
      _vendorId = id;
      _bills = const [];
      _receipts = const [];
      _billIds.clear();
      _receiptIds.clear();
    });
    unawaited(_loadLinks());
  }

  String? _check() {
    if (_boeNumber.text.trim().isEmpty) return 'Enter the Bill of Entry number.';
    if (_port.text.trim().isEmpty) return 'Enter the port code.';
    if (_vendorId.isEmpty) return 'Choose the supplier.';
    final String code = _currency.text.trim();
    if (code.isNotEmpty && !RegExp(r'^[A-Za-z]{3}$').hasMatch(code)) {
      return 'The currency is a three-letter code, such as USD.';
    }
    final String rate = _rate.text.trim();
    if (rate.isNotEmpty && (double.tryParse(rate) ?? 0) <= 0) {
      return 'The exchange rate must be a number above 0, or blank.';
    }
    if (_lines.isEmpty) return 'Add at least one item.';
    for (int i = 0; i < _lines.length; i++) {
      final _LineEdit line = _lines[i];
      final String n = 'Item ${i + 1}';
      if (line.productId.isEmpty) return '$n: choose the product.';
      if ((double.tryParse(line.quantity.text.trim()) ?? 0) <= 0) {
        return '$n: the quantity must be above 0.';
      }
      final double? value = double.tryParse(line.assessable.text.trim());
      if (value == null || value < 0) {
        return '$n: enter the assessable value.';
      }
      for (final TextEditingController c in [
        line.bcdRate,
        line.bcdAmount,
        line.swsRate,
        line.swsAmount,
        line.igstRate,
        line.igstAmount,
        line.cessAmount,
      ]) {
        if (_LineEdit.optional(c)?.isNaN ?? false) {
          return '$n: the duty boxes take a number of 0 or more, or stay blank.';
        }
      }
    }
    return null;
  }

  /// Every declared field. On a change a blank currency, rate or remark is an
  /// explicit null, which clears it; a new document leaves them out.
  Json _body({required bool creating}) {
    final String code = _currency.text.trim().toUpperCase();
    final String rate = _rate.text.trim();
    final String remarks = _remarks.text.trim();
    return <String, dynamic>{
      'boe_number': _boeNumber.text.trim(),
      'boe_date': _boeDate,
      'port_code': _port.text.trim().toUpperCase(),
      'vendor_id': _vendorId,
      if (!creating || code.isNotEmpty) 'currency_code': code.isEmpty ? null : code,
      if (!creating || rate.isNotEmpty) 'exchange_rate': rate.isEmpty ? null : rate,
      'purchase_invoice_ids': _billIds.toList(),
      'goods_receipt_ids': _receiptIds.toList(),
      if (!creating || remarks.isNotEmpty)
        'remarks': remarks.isEmpty ? null : remarks,
      'lines': [for (final _LineEdit line in _lines) line.toJson()],
    };
  }

  void _save() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    final BillOfEntry? existing = _record;
    unawaited(saveAndClose<BillOfEntry>(() => existing == null
        ? widget.api.createBillOfEntry(_body(creating: true))
        : widget.api.updateBillOfEntry(existing.id, _body(creating: false),
            expectedVersion: existing.version)));
  }

  void _post() {
    final BillOfEntry? existing = _record;
    if (existing == null) return;
    unawaited(
        saveAndClose<BillOfEntry>(() => widget.api.postBillOfEntry(existing.id)));
  }

  Future<void> _cancel() async {
    final BillOfEntry? existing = _record;
    if (existing == null) return;
    final String? reason = await askForReason(
      context,
      title: 'Cancel Bill of Entry ${existing.label}',
      explanation: 'The journal is reversed and the duty comes off the '
          'stock cost. The reason is kept with the document.',
      confirmLabel: 'Cancel the Bill of Entry',
    );
    if (reason == null || !mounted) return;
    unawaited(saveAndClose<BillOfEntry>(
        () => widget.api.cancelBillOfEntry(existing.id, reason)));
  }

  Future<String?> _pick(String current) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse(current) ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    return picked?.toIso8601String().split('T').first;
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final Size size = MediaQuery.sizeOf(context);
    final BillOfEntry? record = _record;
    return Dialog(
      insetPadding: const EdgeInsets.all(AppSpacing.lg),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: (size.width - 48).clamp(360.0, 980.0),
          maxHeight: (size.height - 48).clamp(300.0, 760.0),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.sm),
              child: Row(children: [
                Expanded(
                  child: Text(
                    record == null
                        ? 'New Bill of Entry'
                        : 'Bill of Entry ${record.label}',
                    style: theme.textTheme.titleLarge,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (record != null)
                  StatusBadge(label: record.status),
              ]),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.lg),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          saveErrorBanner(),
                          if (_problem != null)
                            Padding(
                              padding:
                                  const EdgeInsets.only(bottom: AppSpacing.sm),
                              child: Text(_problem!,
                                  key: const ValueKey('boe-problem'),
                                  style:
                                      TextStyle(color: theme.colorScheme.error)),
                            ),
                          if (record != null && record.isCancelled)
                            Padding(
                              padding:
                                  const EdgeInsets.only(bottom: AppSpacing.sm),
                              child: Text(
                                'Cancelled: ${record.cancelReason}',
                                key: const ValueKey('boe-cancel-reason'),
                              ),
                            ),
                          _header(),
                          const SizedBox(height: AppSpacing.md),
                          _links(),
                          const SizedBox(height: AppSpacing.md),
                          _itemsSection(),
                        ],
                      ),
                    ),
            ),
            const Divider(height: 1),
            _totals(),
            _actions(),
          ],
        ),
      ),
    );
  }

  Widget _dateBox(String label, String value, VoidCallback? onTap, Key key) =>
      InkWell(
        key: key,
        onTap: onTap,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            suffixIcon: const Icon(Icons.event, size: 16),
          ),
          child: Text(value.isEmpty ? '—' : value),
        ),
      );

  Widget _box(String label, TextEditingController controller, Key key,
          {double width = 180,
          bool number = false,
          String? helper,
          int? maxLength}) =>
      SizedBox(
        width: width,
        child: TextField(
          key: key,
          controller: controller,
          enabled: _editable,
          maxLength: maxLength,
          keyboardType: number
              ? const TextInputType.numberWithOptions(decimal: true)
              : null,
          textCapitalization:
              maxLength != null ? TextCapitalization.characters : TextCapitalization.none,
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            helperText: helper,
            helperMaxLines: 2,
            counterText: '',
          ),
          onChanged: (_) => setState(() {}),
        ),
      );

  Widget _header() => Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.md,
        children: [
          _box('Bill of Entry number', _boeNumber, const ValueKey('boe-number')),
          SizedBox(
            width: 170,
            child: _dateBox(
              'BoE date',
              _boeDate,
              !_editable
                  ? null
                  : () async {
                      final String? v = await _pick(_boeDate);
                      if (v != null) setState(() => _boeDate = v);
                    },
              const ValueKey('boe-date'),
            ),
          ),
          _box('Port code', _port, const ValueKey('boe-port'),
              width: 120, maxLength: 10),
          SizedBox(
            width: 300,
            child: DropdownButtonFormField<String>(
              key: const ValueKey('boe-vendor'),
              initialValue: _vendorId.isEmpty ? null : _vendorId,
              isExpanded: true,
              decoration:
                  const InputDecoration(labelText: 'Supplier', isDense: true),
              items: [
                for (final Vendor v in _vendors)
                  DropdownMenuItem(
                    value: v.id,
                    child:
                        Text(_vendorName(v), overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: _editable && _record == null
                  ? (v) => _chooseVendor(v ?? '')
                  : null,
            ),
          ),
          _box('Currency', _currency, const ValueKey('boe-currency'),
              width: 120,
              maxLength: 3,
              helper: 'Blank takes the linked bill\'s'),
          _box('Exchange rate', _rate, const ValueKey('boe-rate'),
              width: 150, number: true, helper: 'Blank takes the bill\'s'),
          _box('Remarks', _remarks, const ValueKey('boe-remarks'), width: 300),
        ],
      );

  Widget _links() {
    final ThemeData theme = Theme.of(context);
    if (_vendorId.isEmpty) {
      return Text('Choose the supplier to tick the bills and receipts the '
          'goods came on.',
          style: theme.textTheme.bodySmall);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Supplier bills the goods came on',
            style: theme.textTheme.titleSmall),
        if (_bills.isEmpty)
          Text('This supplier has no bills.', style: theme.textTheme.bodySmall)
        else
          for (final Json bill in _bills)
            CheckboxListTile(
              key: ValueKey('boe-bill-${bill['id']}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              value: _billIds.contains('${bill['id']}'),
              onChanged: _editable
                  ? (v) => setState(() => v == true
                      ? _billIds.add('${bill['id']}')
                      : _billIds.remove('${bill['id']}'))
                  : null,
              title: Text(
                '${bill['invoice_number'] ?? ''} · '
                "${bill['supplier_invoice_number'] ?? ''} · "
                '${bill['invoice_date'] ?? ''} · '
                '${(bill['currency_code'] ?? '') == '' ? '' : '${bill['currency_code']} '}'
                '${bill['grand_total'] ?? ''}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
        const SizedBox(height: AppSpacing.sm),
        Text('Goods receipts', style: theme.textTheme.titleSmall),
        if (_receipts.isEmpty)
          Text('This supplier has no receipts.',
              style: theme.textTheme.bodySmall)
        else
          for (final GoodsReceiptRecord receipt in _receipts)
            CheckboxListTile(
              key: ValueKey('boe-receipt-${receipt.id}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              controlAffinity: ListTileControlAffinity.leading,
              value: _receiptIds.contains(receipt.id),
              onChanged: _editable
                  ? (v) => setState(() => v == true
                      ? _receiptIds.add(receipt.id)
                      : _receiptIds.remove(receipt.id))
                  : null,
              title: Text('${receipt.grnNumber} · ${receipt.receiptDate}',
                  overflow: TextOverflow.ellipsis),
            ),
      ],
    );
  }

  Widget _itemsSection() {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(child: Text('Items', style: theme.textTheme.titleSmall)),
          if (_editable)
            TextButton.icon(
              key: const ValueKey('boe-add-line'),
              onPressed: () => setState(() => _lines.add(_LineEdit())),
              icon: const Icon(Icons.add, size: 16),
              label: const Text('Add item'),
            ),
        ]),
        Text(
          'Type a rate or an amount. Leave an amount blank and the server '
          'works it out: SWS is 10% of the basic duty when no rate is typed, '
          'and IGST is charged on the value plus the duty. A typed amount '
          'wins over its rate.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        for (int i = 0; i < _lines.length; i++) _lineCard(i),
      ],
    );
  }

  Widget _lineCard(int index) {
    final ThemeData theme = Theme.of(context);
    final _LineEdit line = _lines[index];
    final BoeLine? c = line.computed;
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Text('${index + 1}', style: theme.textTheme.labelLarge),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: ProductSearchBox(
                  fieldKey: ValueKey('boe-product-$index'),
                  api: widget.api,
                  controller: line.product,
                  enabled: _editable,
                  onPicked: (Product p) => line.productId = p.id,
                  onCleared: () => line.productId = '',
                ),
              ),
              if (_editable && _lines.length > 1)
                IconButton(
                  key: ValueKey('boe-remove-$index'),
                  tooltip: 'Remove item',
                  icon: const Icon(Icons.close, size: 16),
                  onPressed: () => setState(() {
                    _lines.removeAt(index).dispose();
                  }),
                ),
            ]),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                _box('Quantity', line.quantity, ValueKey('boe-qty-$index'),
                    width: 110, number: true),
                _box('Assessable value', line.assessable,
                    ValueKey('boe-value-$index'),
                    width: 140, number: true),
                _box('BCD %', line.bcdRate, ValueKey('boe-bcd-rate-$index'),
                    width: 90, number: true),
                _box('BCD amount', line.bcdAmount,
                    ValueKey('boe-bcd-amount-$index'),
                    width: 120, number: true),
                _box('SWS %', line.swsRate, ValueKey('boe-sws-rate-$index'),
                    width: 90, number: true),
                _box('SWS amount', line.swsAmount,
                    ValueKey('boe-sws-amount-$index'),
                    width: 120, number: true),
                _box('IGST %', line.igstRate, ValueKey('boe-igst-rate-$index'),
                    width: 90, number: true),
                _box('IGST amount', line.igstAmount,
                    ValueKey('boe-igst-amount-$index'),
                    width: 120, number: true),
                _box('Cess amount', line.cessAmount,
                    ValueKey('boe-cess-$index'),
                    width: 120, number: true),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            // Read only: the server's working, shown once it has been saved.
            Text(
              c == null
                  ? 'Worked out when saved.'
                  : 'BCD ${_money(c.bcdAmount)} · SWS ${_money(c.swsAmount)} · '
                      'IGST base ${_money(c.igstBase)} · '
                      'IGST ${_money(c.igstAmount)} · '
                      'total duty ${_money(c.totalDuty)} · '
                      'stock ${_money(c.inventoryAmount)} · '
                      'COGS ${_money(c.cogsAmount)} · '
                      'expense ${_money(c.expenseAmount)}',
              key: ValueKey('boe-computed-$index'),
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  /// Where the duty went, as the server worked it out.
  Widget _totals() {
    final BillOfEntry? r = _record;
    final ThemeData theme = Theme.of(context);
    Widget stat(String label, String? value, Key key) => Padding(
          padding: const EdgeInsets.only(right: AppSpacing.lg),
          child: Text.rich(
            TextSpan(children: [
              TextSpan(text: '$label  ', style: theme.textTheme.bodySmall),
              TextSpan(
                text: value == null ? '—' : _money(value),
                style: theme.textTheme.titleSmall,
              ),
            ]),
            key: key,
          ),
        );
    return Padding(
      key: const ValueKey('boe-totals'),
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Wrap(
        runSpacing: AppSpacing.xs,
        children: [
          stat('Customs duty', r?.customsDuty, const ValueKey('boe-t-customs')),
          stat('IGST', r?.igstAmount, const ValueKey('boe-t-igst')),
          stat('Cess', r?.cessAmount, const ValueKey('boe-t-cess')),
          stat('Total duty', r?.totalDuty, const ValueKey('boe-t-total')),
          stat('To stock', r?.inventoryAmount, const ValueKey('boe-t-stock')),
          stat('To COGS', r?.cogsAmount, const ValueKey('boe-t-cogs')),
          stat('To expense', r?.expenseAmount, const ValueKey('boe-t-expense')),
        ],
      ),
    );
  }

  Widget _actions() {
    final BillOfEntry? r = _record;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.md),
      child: Wrap(
        alignment: WrapAlignment.end,
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          TextButton(
            onPressed: cancelHandler,
            child: Text(_editable ? 'Cancel' : 'Close'),
          ),
          if (r != null && r.isPosted && widget.mayApprove)
            OutlinedButton(
              key: const ValueKey('boe-cancel-document'),
              onPressed: saving ? null : () => unawaited(_cancel()),
              child: const Text('Cancel document'),
            ),
          if (r != null && r.isDraft && widget.mayApprove)
            OutlinedButton(
              key: const ValueKey('boe-post'),
              onPressed: saving ? null : _post,
              child: const Text('Post'),
            ),
          if (_editable || (saving && (r == null || r.isDraft)))
            FilledButton(
              key: const ValueKey('boe-save'),
              onPressed: saving ? null : _save,
              child: const Text('Save'),
            ),
        ],
      ),
    );
  }
}
