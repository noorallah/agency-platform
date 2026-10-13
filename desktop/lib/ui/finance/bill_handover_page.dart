// Bills with Collectors (backlog 122): the office hands unpaid bills to a
// collector in the morning and takes them back later. It is a note beside the
// bill; it changes no balance and no report. Phase 2 only.
//
// M6 (backlog 124) adds the Day sheet: the collectors' end-of-day lines, what
// they state, what is in a receipt, and whether the two agree.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/bill_handover.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../phase2/display_dates.dart';
import '../../phase2/indian_format.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';
import 'collection_return_dialog.dart';

const int _pageSize = 50;

String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? value : parsed.toStringAsFixed(2);
}

/// A stored day as the person's own date format writes it; blank stays blank.
String _shown(String? value) {
  if (value == null || value.length < 10) return value ?? '';
  final DateTime? parsed = DateTime.tryParse(value.substring(0, 10));
  return parsed == null ? value : DisplayDates.write(parsed);
}

String _bills(int count) => count == 1 ? '1 bill' : '$count bills';

/// One member picker. Values are user ids; the empty string is [anyLabel].
Widget _picker({
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

/// Which unpaid bills are in the office and which are with a collector, and
/// the buttons that hand them out and take them back.
class BillHandoverPage extends StatefulWidget {
  const BillHandoverPage({
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
  State<BillHandoverPage> createState() => _BillHandoverPageState();
}

class _BillHandoverPageState extends State<BillHandoverPage> {
  static const List<GridColumn> _billColumns = [
    GridColumn(key: 'tick', label: '', priority: 1),
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'bill-date', label: 'Date', priority: 2),
    GridColumn(key: 'due', label: 'Due', priority: 2),
    GridColumn(key: 'overdue', label: 'Days overdue', numeric: true),
    GridColumn(key: 'outstanding', label: 'Outstanding', numeric: true),
    GridColumn(key: 'with', label: 'With'),
    GridColumn(key: 'handed-on', label: 'Handed on', priority: 2),
  ];

  static const GridColumn _lineColumn =
      GridColumn(key: 'line', label: 'Day’s line');

  static const List<GridColumn> _daySheetColumns = [
    GridColumn(key: 'collector', label: 'Collector'),
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'outcome', label: 'Outcome'),
    GridColumn(key: 'stated', label: 'Stated', numeric: true),
    GridColumn(key: 'how-paid', label: 'How paid', priority: 2),
    GridColumn(key: 'receipt', label: 'Receipt'),
    GridColumn(key: 'receipt-amount', label: 'In receipt', numeric: true),
    GridColumn(key: 'promised-on', label: 'Promised for', priority: 2),
    GridColumn(key: 'note', label: 'Note', priority: 3),
    GridColumn(key: 'by', label: 'Recorded by', priority: 3),
    GridColumn(key: 'actions', label: ''),
  ];

  static const List<GridColumn> _historyColumns = [
    GridColumn(key: 'tick', label: '', priority: 1),
    GridColumn(key: 'customer', label: 'Customer'),
    GridColumn(key: 'bill', label: 'Bill'),
    GridColumn(key: 'collector', label: 'Collector'),
    GridColumn(key: 'handed-on', label: 'Handed on', priority: 2),
    GridColumn(key: 'by', label: 'By', priority: 3),
    GridColumn(key: 'owed-then', label: 'Owed when handed', numeric: true),
    GridColumn(key: 'owes-now', label: 'Owes now', numeric: true),
    GridColumn(key: 'taken-back', label: 'Taken back', priority: 2),
  ];

  final TextEditingController _area = TextEditingController();
  final TextEditingController _numberFrom = TextEditingController();
  final TextEditingController _numberTo = TextEditingController();

  List<FirmMember> _members = const [];
  List<HandoverBill> _billRows = const [];
  List<BillHandover> _historyRows = const [];
  final Set<String> _ticked = <String>{};

  CollectionDaySheet? _sheet;
  DateTime _sheetDay = DateTime.now();
  String _viewName = 'bills';
  String _handed = 'ALL';
  String _historyState = '';
  String _filterCollector = '';
  String _giveTo = '';
  DateTime? _dateFrom;
  DateTime? _dateTo;
  int _page = 1;
  int _total = 0;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  bool get _mayView => widget.permissions.hasPermission('RECEIPT_VIEW');
  bool get _mayAssign => widget.permissions.hasPermission('COLLECTION_ASSIGN');
  bool get _mayReceipt => widget.permissions.hasPermission('RECEIPT_CREATE');
  bool get _historyView => _viewName == 'history';
  bool get _dayView => _viewName == 'day';

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) {
      unawaited(_loadMembers());
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _area.dispose();
    _numberFrom.dispose();
    _numberTo.dispose();
    super.dispose();
  }

  Future<void> _loadMembers() async {
    try {
      final List<FirmMember> members = await widget.api.firmMembers();
      if (mounted) setState(() => _members = members);
    } on ApiException {
      // The pickers just stay at nobody.
    }
  }

  String? _text(TextEditingController controller) {
    final String value = controller.text.trim();
    return value.isEmpty ? null : value;
  }

  /// Clears the rows and the ticks first: the screen must have read the list
  /// before anything can be done to it.
  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      _billRows = const [];
      _historyRows = const [];
      _sheet = null;
      _ticked.clear();
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final String? collector =
          _filterCollector.isEmpty ? null : _filterCollector;
      if (_dayView) {
        final Json answer = await widget.api.collectionDaySheet(
          day: _iso(_sheetDay),
          collectorId: collector,
        );
        if (!mounted) return;
        setState(() {
          _sheet = CollectionDaySheet.fromJson(answer);
          _total = _sheet!.rows.length;
          _loading = false;
        });
      } else if (_historyView) {
        final Json response = await widget.api.billHandovers(
          page: _page,
          pageSize: _pageSize,
          collectorId: collector,
          state: _historyState.isEmpty ? null : _historyState,
        );
        final List<BillHandover> rows = [
          for (final dynamic item in (response['data'] as List? ?? const []))
            if (item is Map)
              BillHandover.fromJson(Map<String, dynamic>.from(item)),
        ];
        if (!mounted) return;
        setState(() {
          _historyRows = rows;
          _total = pagedTotal(response, fallback: rows.length);
          _loading = false;
        });
      } else {
        final Json response = await widget.api.handoverBills(
          page: _page,
          pageSize: _pageSize,
          handed: _handed == 'ALL' ? null : _handed,
          collectorId: collector,
          dateFrom: _dateFrom == null ? null : _iso(_dateFrom!),
          dateTo: _dateTo == null ? null : _iso(_dateTo!),
          area: _text(_area),
          numberFrom: _text(_numberFrom),
          numberTo: _text(_numberTo),
        );
        final List<HandoverBill> rows = [
          for (final dynamic item in (response['data'] as List? ?? const []))
            if (item is Map)
              HandoverBill.fromJson(Map<String, dynamic>.from(item)),
        ];
        if (!mounted) return;
        setState(() {
          _billRows = rows;
          _total = pagedTotal(response, fallback: rows.length);
          _loading = false;
        });
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _total = 0;
        _loading = false;
      });
    }
  }

  void _tell(String message, AppNotificationKind kind) =>
      NotificationService.show(context, message, kind: kind);

  String _collectorName(String id) {
    for (final FirmMember member in _members) {
      if (member.userId == id) return member.label;
    }
    return 'the collector';
  }

  /// Runs one change, shows its answer, then reads the list again.
  Future<void> _act(Future<String> Function() change) async {
    setState(() => _busy = true);
    try {
      final String message = await change();
      if (!mounted) return;
      _tell(message, AppNotificationKind.success);
      setState(() => _busy = false);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _busy = false);
      _tell(error.message, AppNotificationKind.error);
    }
  }

  String _gaveMessage(Json answer, String collector) {
    final int bills = (answer['bills'] as num?)?.toInt() ?? 0;
    final int already = (answer['already_out'] as num?)?.toInt() ?? 0;
    final double amount = double.tryParse('${answer['amount']}') ?? 0;
    final String left = already == 0
        ? ''
        : ' ${already == 1 ? '1 was' : '$already were'} already out and '
            '${already == 1 ? 'was' : 'were'} left.';
    return '${_bills(bills)} handed to $collector, '
        '${indianAmount(amount, full: true)} in all.$left';
  }

  String _tookMessage(Json answer) {
    final int bills = (answer['bills'] as num?)?.toInt() ?? 0;
    return '${_bills(bills)} taken back.';
  }

  List<HandoverBill> get _tickedBills =>
      _billRows.where((row) => _ticked.contains(row.invoiceId)).toList();

  List<BillHandover> get _tickedHistory =>
      _historyRows.where((row) => _ticked.contains(row.id)).toList();

  List<String> get _handoverIdsToTakeBack => _historyView
      ? [for (final BillHandover row in _tickedHistory) if (row.isOut) row.id]
      : [
          for (final HandoverBill row in _tickedBills)
            if (row.handoverId != null) row.handoverId!,
        ];

  List<String> get _invoiceIdsToGive => [
        for (final HandoverBill row in _tickedBills)
          if (!row.isOut) row.invoiceId,
      ];

  /// The filters "Hand over all matching" will send: only the ones set.
  Map<String, String> get _matching => <String, String>{
        if (_dateFrom != null) 'date_from': _iso(_dateFrom!),
        if (_dateTo != null) 'date_to': _iso(_dateTo!),
        if (_text(_area) != null) 'area': _text(_area)!,
        if (_text(_numberFrom) != null) 'number_from': _text(_numberFrom)!,
        if (_text(_numberTo) != null) 'number_to': _text(_numberTo)!,
      };

  Future<void> _giveTicked() {
    final String collector = _collectorName(_giveTo);
    final String to = _giveTo;
    final List<String> ids = _invoiceIdsToGive;
    return _act(() async => _gaveMessage(
          await widget.api.handBillsOut(collectorId: to, invoiceIds: ids),
          collector,
        ));
  }

  Future<void> _giveMatching() async {
    final Map<String, String> matching = _matching;
    final String collector = _collectorName(_giveTo);
    final String to = _giveTo;
    const Map<String, String> names = {
      'date_from': 'From',
      'date_to': 'To',
      'area': 'Area or city',
      'number_from': 'Bill no. from',
      'number_to': 'Bill no. to',
    };
    final bool? yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hand over all matching bills?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Every unpaid bill that is still in the office and fits '
                'these will go to $collector:'),
            const SizedBox(height: AppSpacing.sm),
            for (final MapEntry<String, String> entry in matching.entries)
              Text('${names[entry.key]}: ${entry.value}'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('handover-confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Hand over'),
          ),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    await _act(() async => _gaveMessage(
          await widget.api.handBillsOut(collectorId: to, matching: matching),
          collector,
        ));
  }

  Future<void> _takeBack() {
    final List<String> ids = _handoverIdsToTakeBack;
    return _act(() async =>
        _tookMessage(await widget.api.takeBillsBack(handoverIds: ids)));
  }

  Future<void> _recordLine({
    required String handoverId,
    required String billNumber,
    required String customer,
    required double owes,
  }) async {
    final bool saved = await showCollectionReturnDialog(
      context,
      billNumber: billNumber,
      customerName: customer,
      owes: owes,
      handoverId: handoverId,
      office: true,
      collectorRecordsReceipt: true,
      onSave: (body) async {
        await widget.api.recordCollectionReturn(body);
      },
    );
    if (saved && mounted) await _load();
  }

  Future<void> _receiptFor(CollectionReturnLine row) => _act(() async {
        await widget.api.recordReturnReceipt(row.id);
        return 'Receipt recorded for ${row.invoiceNumber}.';
      });

  Future<void> _withdrawLine(CollectionReturnLine row) async {
    final String? reason = await askForReason(
      context,
      title: 'Withdraw this line?',
      explanation: 'The line on ${row.invoiceNumber} is withdrawn. A receipt '
          'recorded from it has to be reversed first.',
      confirmLabel: 'Withdraw',
    );
    if (reason == null || !mounted) return;
    await _act(() async {
      await widget.api.withdrawCollectionReturn(row.id, reason);
      return 'Line on ${row.invoiceNumber} withdrawn.';
    });
  }

  Future<void> _pickSheetDay() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _sheetDay,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    setState(() => _sheetDay = picked);
    unawaited(_load());
  }

  Future<void> _pickDate({required bool from}) async {
    final DateTime? current = from ? _dateFrom : _dateTo;
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: current ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    setState(() => from ? _dateFrom = picked : _dateTo = picked);
  }

  Widget _dateBox({
    required Key key,
    required String label,
    required DateTime? value,
    required bool from,
  }) {
    return SizedBox(
      width: 150,
      child: InkWell(
        key: key,
        onTap: () => unawaited(_pickDate(from: from)),
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            suffixIcon: value == null
                ? const Icon(Icons.event_outlined, size: 16)
                : IconButton(
                    icon: const Icon(Icons.close, size: 16),
                    tooltip: 'Clear',
                    onPressed: () =>
                        setState(() => from ? _dateFrom = null : _dateTo = null),
                  ),
          ),
          child: Text(value == null ? '' : _iso(value)),
        ),
      ),
    );
  }

  Widget _textBox(Key key, String label, TextEditingController controller,
      double width) {
    return SizedBox(
      width: width,
      child: TextField(
        key: key,
        controller: controller,
        decoration: InputDecoration(labelText: label, isDense: true),
        onChanged: (_) => setState(() {}),
        onSubmitted: (_) => unawaited(_load(requestedPage: 1)),
      ),
    );
  }

  Widget _daySheetFilters() {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 190,
          child: _picker(
            key: const ValueKey('day-sheet-collector'),
            label: 'Collector',
            anyLabel: 'All collectors',
            members: _members,
            value: _filterCollector,
            onChanged: (value) {
              setState(() => _filterCollector = value);
              unawaited(_load());
            },
          ),
        ),
        SizedBox(
          width: 170,
          child: InkWell(
            key: const ValueKey('day-sheet-day'),
            onTap: () => unawaited(_pickSheetDay()),
            child: InputDecorator(
              decoration: const InputDecoration(
                labelText: 'Day',
                isDense: true,
                suffixIcon: Icon(Icons.event_outlined, size: 16),
              ),
              child: Text(DisplayDates.write(_sheetDay)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _filters() {
    if (_dayView) return _daySheetFilters();
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (!_historyView)
          SizedBox(
            width: 190,
            child: DropdownButtonFormField<String>(
              key: const ValueKey('handover-show'),
              isExpanded: true,
              initialValue: _handed,
              decoration:
                  const InputDecoration(labelText: 'Show', isDense: true),
              items: const [
                DropdownMenuItem(value: 'ALL', child: Text('All unpaid bills')),
                DropdownMenuItem(
                    value: 'NOT_OUT', child: Text('In the office')),
                DropdownMenuItem(value: 'OUT', child: Text('With a collector')),
              ],
              onChanged: (value) => setState(() => _handed = value ?? 'ALL'),
            ),
          ),
        if (_historyView)
          SizedBox(
            width: 170,
            child: DropdownButtonFormField<String>(
              key: const ValueKey('handover-state'),
              isExpanded: true,
              initialValue: _historyState,
              decoration:
                  const InputDecoration(labelText: 'Show', isDense: true),
              items: const [
                DropdownMenuItem(value: '', child: Text('All')),
                DropdownMenuItem(value: 'OUT', child: Text('Out')),
                DropdownMenuItem(value: 'RETURNED', child: Text('Taken back')),
              ],
              onChanged: (value) =>
                  setState(() => _historyState = value ?? ''),
            ),
          ),
        SizedBox(
          width: 190,
          child: _picker(
            key: const ValueKey('handover-filter-collector'),
            label: 'Collector',
            anyLabel: 'Everybody',
            members: _members,
            value: _filterCollector,
            onChanged: (value) => setState(() => _filterCollector = value),
          ),
        ),
        if (!_historyView) ...[
          _dateBox(
              key: const ValueKey('handover-date-from'),
              label: 'From',
              value: _dateFrom,
              from: true),
          _dateBox(
              key: const ValueKey('handover-date-to'),
              label: 'To',
              value: _dateTo,
              from: false),
          _textBox(const ValueKey('handover-area'), 'Area or city', _area, 160),
          _textBox(const ValueKey('handover-number-from'), 'Bill no. from',
              _numberFrom, 130),
          _textBox(const ValueKey('handover-number-to'), 'Bill no. to',
              _numberTo, 130),
        ],
        FilledButton(
          key: const ValueKey('handover-apply'),
          onPressed: _loading ? null : () => unawaited(_load(requestedPage: 1)),
          child: const Text('Show'),
        ),
      ],
    );
  }

  Widget _actions() {
    final bool canGive =
        !_busy && !_loading && _giveTo.isNotEmpty && _invoiceIdsToGive.isNotEmpty;
    final bool canGiveMatching =
        !_busy && !_loading && _giveTo.isNotEmpty && _matching.isNotEmpty;
    final bool canTakeBack =
        !_busy && !_loading && _handoverIdsToTakeBack.isNotEmpty;
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.sm,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (!_historyView) ...[
          SizedBox(
            width: 190,
            child: _picker(
              key: const ValueKey('handover-collector'),
              label: 'Hand to',
              anyLabel: 'Choose a collector',
              members: _members,
              value: _giveTo,
              onChanged: _busy ? null : (value) => setState(() => _giveTo = value),
            ),
          ),
          FilledButton(
            key: const ValueKey('handover-give'),
            onPressed: canGive ? () => unawaited(_giveTicked()) : null,
            child: const Text('Hand over ticked'),
          ),
          OutlinedButton(
            key: const ValueKey('handover-give-matching'),
            onPressed: canGiveMatching ? () => unawaited(_giveMatching()) : null,
            child: const Text('Hand over all matching'),
          ),
        ],
        OutlinedButton(
          key: const ValueKey('handover-take-back'),
          onPressed: canTakeBack ? () => unawaited(_takeBack()) : null,
          child: const Text('Take back ticked'),
        ),
      ],
    );
  }

  Widget _view() {
    return SegmentedButton<String>(
      showSelectedIcon: false,
      segments: const [
        ButtonSegment(
          value: 'bills',
          label: Text('Bills', key: ValueKey('handover-view-bills')),
        ),
        ButtonSegment(
          value: 'history',
          label: Text('History', key: ValueKey('handover-view-history')),
        ),
        ButtonSegment(
          value: 'day',
          label: Text('Day sheet', key: ValueKey('handover-view-day-sheet')),
        ),
      ],
      selected: {_viewName},
      onSelectionChanged: (picked) {
        setState(() {
          _viewName = picked.first;
          _page = 1;
        });
        unawaited(_load(requestedPage: 1));
      },
    );
  }

  Widget _tickBox(String id) => Checkbox(
        key: ValueKey('handover-tick-$id'),
        value: _ticked.contains(id),
        onChanged: _busy
            ? null
            : (on) => setState(() {
                  if (on == true) {
                    _ticked.add(id);
                  } else {
                    _ticked.remove(id);
                  }
                }),
      );

  Widget _tickAll(List<String> ids) {
    final bool all = ids.isNotEmpty && ids.every(_ticked.contains);
    return Align(
      alignment: Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Checkbox(
            key: const ValueKey('handover-tick-all'),
            value: all,
            onChanged: _busy || ids.isEmpty
                ? null
                : (on) => setState(() {
                      if (on == true) {
                        _ticked.addAll(ids);
                      } else {
                        _ticked.removeAll(ids);
                      }
                    }),
          ),
          Text(_ticked.isEmpty
              ? 'Tick every bill shown'
              : '${_ticked.length} ticked'),
        ],
      ),
    );
  }

  Widget _plainCell(String value) => Tooltip(
        message: value,
        child: SizedBox(
          width: double.infinity,
          child: Text(value, overflow: TextOverflow.ellipsis),
        ),
      );

  void _onPage(int offset) {
    final int next = offset ~/ _pageSize + 1;
    if (next != _page) unawaited(_load(requestedPage: next));
  }

  Widget _billGrid() {
    return EnterpriseDataGrid<HandoverBill>(
      items: _billRows,
      total: _total,
      pageOffset: (_page - 1) * _pageSize,
      rowsPerPage: _pageSize,
      availableRowsPerPage: const [_pageSize],
      columns: [..._billColumns, if (_mayReceipt) _lineColumn],
      id: (row) => row.invoiceId,
      cells: (row) => [
        '',
        row.customerLabel,
        row.invoiceNumber,
        row.invoiceDate,
        row.dueDate,
        '${row.daysOverdue}',
        _money(row.outstanding),
        row.collectorName,
        row.handedOn,
        if (_mayReceipt) '',
      ],
      onSelect: (_) {},
      onPageChanged: _onPage,
      cellBuilder: (columnIndex, value, item) {
        if (columnIndex == 0) return _tickBox(item.invoiceId);
        if (columnIndex == _billColumns.length) {
          if (!item.isOut) return const SizedBox.shrink();
          return Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: ValueKey('handover-line-${item.handoverId}'),
              onPressed: _busy
                  ? null
                  : () => unawaited(_recordLine(
                        handoverId: item.handoverId!,
                        billNumber: item.invoiceNumber,
                        customer: item.customerLabel,
                        owes: double.tryParse(item.outstanding) ?? 0,
                      )),
              child: const Text('Day’s line'),
            ),
          );
        }
        return _plainCell(value);
      },
    );
  }

  Widget _historyGrid() {
    return EnterpriseDataGrid<BillHandover>(
      items: _historyRows,
      total: _total,
      pageOffset: (_page - 1) * _pageSize,
      rowsPerPage: _pageSize,
      availableRowsPerPage: const [_pageSize],
      columns: [..._historyColumns, if (_mayReceipt) _lineColumn],
      id: (row) => row.id,
      cells: (row) => [
        '',
        row.customerLabel,
        row.invoiceNumber,
        row.collectorName,
        row.handedOn,
        row.handedByName,
        _money(row.outstandingAtHandover),
        _money(row.outstanding),
        row.returnedAt.length >= 10
            ? row.returnedAt.substring(0, 10)
            : row.returnedAt,
        if (_mayReceipt) '',
      ],
      onSelect: (_) {},
      onPageChanged: _onPage,
      cellBuilder: (columnIndex, value, item) {
        if (columnIndex == 0) return _tickBox(item.id);
        if (columnIndex == _historyColumns.length) {
          if (!item.isOut) return const SizedBox.shrink();
          return Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              key: ValueKey('handover-line-${item.id}'),
              onPressed: _busy
                  ? null
                  : () => unawaited(_recordLine(
                        handoverId: item.id,
                        billNumber: item.invoiceNumber,
                        customer: item.customerLabel,
                        owes: double.tryParse(item.outstanding) ?? 0,
                      )),
              child: const Text('Day’s line'),
            ),
          );
        }
        return _plainCell(value);
      },
    );
  }

  String _receiptText(CollectionReturnLine row) {
    if (row.receiptReversed) return 'Receipt reversed';
    if (row.settlementId != null) return row.settlementNumber ?? 'Receipt';
    return row.stated > 0 ? 'No receipt yet' : '';
  }

  Widget _daySheetActions(CollectionReturnLine row) {
    if (!_mayReceipt) return const SizedBox.shrink();
    return FittedBox(
      fit: BoxFit.scaleDown,
      alignment: Alignment.centerLeft,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (row.needsReceipt)
            TextButton(
              key: ValueKey('day-sheet-receipt-${row.id}'),
              onPressed: _busy ? null : () => unawaited(_receiptFor(row)),
              child: const Text('Record receipt'),
            ),
          TextButton(
            key: ValueKey('day-sheet-withdraw-${row.id}'),
            onPressed: _busy ? null : () => unawaited(_withdrawLine(row)),
            child: const Text('Withdraw'),
          ),
        ],
      ),
    );
  }

  Widget _daySheetGrid(CollectionDaySheet sheet) {
    return EnterpriseDataGrid<CollectionReturnLine>(
      items: sheet.rows,
      total: sheet.rows.length,
      pageOffset: 0,
      rowsPerPage: sheet.rows.length,
      availableRowsPerPage: [sheet.rows.length],
      columns: _daySheetColumns,
      id: (row) => row.id,
      cells: (row) => [
        row.collectorName,
        row.customerName,
        row.invoiceNumber,
        returnOutcomeWords(row.outcome),
        row.stated > 0 ? _money(row.amountCollected) : '',
        collectionModeWords(row.stated > 0 ? row.paymentMode : null),
        _receiptText(row),
        (double.tryParse(row.receiptAmount) ?? 0) > 0
            ? _money(row.receiptAmount)
            : '',
        _shown(row.promisedOn),
        row.note ?? '',
        row.recordedByName,
        '',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
      cellBuilder: (columnIndex, value, item) => columnIndex == 11
          ? _daySheetActions(item)
          : _plainCell(value),
    );
  }

  /// Stated, in receipts, the difference, and whether the sheet adds up.
  Widget _daySheetTotals(CollectionDaySheet sheet) {
    final ThemeData theme = Theme.of(context);
    final int out = sheet.billsWithoutALine;
    final String none = out == 0
        ? ''
        : ' ${_bills(out)} out ${out == 1 ? 'has' : 'have'} no line.';
    final String difference = indianAmount(sheet.notReceipted, full: true);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Stated ${indianAmount(sheet.stated, full: true)}. '
          'In receipts ${indianAmount(sheet.receipted, full: true)}. '
          'Difference $difference.$none',
          key: const ValueKey('day-sheet-totals'),
          style: theme.textTheme.titleSmall,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          sheet.addsUp
              ? 'The sheet adds up.'
              : 'The sheet does not add up: $difference stated is not in a '
                  'receipt.',
          key: const ValueKey('day-sheet-adds-up'),
          style: theme.textTheme.bodyMedium?.copyWith(
            color: sheet.addsUp
                ? theme.colorScheme.primary
                : theme.colorScheme.error,
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
        message: 'Bills with collectors belong to one firm’s books.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see the bills with collectors',
        message: 'Reading them needs the view receipts permission.',
      );
    }
    final bool empty = _dayView
        ? (_sheet?.rows.isEmpty ?? true)
        : _historyView
            ? _historyRows.isEmpty
            : _billRows.isEmpty;
    final List<String> shownIds = _historyView
        ? [for (final BillHandover row in _historyRows) row.id]
        : [for (final HandoverBill row in _billRows) row.invoiceId];
    return ManagementWorkspaceLayout(
      toolbar: WorkspaceToolbar(
        actions: const [ToolbarAction.refresh],
        isEnabled: (action) => !_busy,
        onAction: (action) => unawaited(_load()),
      ),
      searchPanel: const SizedBox.shrink(),
      primaryContent: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Handing a bill out changes no balance and no report. '
            'It only records who carries the bill.',
            key: const ValueKey('handover-note'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.sm),
          Align(alignment: Alignment.centerLeft, child: _view()),
          const SizedBox(height: AppSpacing.sm),
          _filters(),
          if (_mayAssign && !_dayView) ...[
            const SizedBox(height: AppSpacing.sm),
            _actions(),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_error!,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (!_loading && !empty && !_dayView) _tickAll(shownIds),
          if (!_loading && _sheet != null) ...[
            const SizedBox(height: AppSpacing.sm),
            _daySheetTotals(_sheet!),
          ],
          const SizedBox(height: AppSpacing.sm),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : empty
                    ? WorkspaceEmptyState(
                        title: _dayView
                            ? 'No lines for this day'
                            : _historyView
                                ? 'Nothing handed out yet'
                                : 'No bills',
                        message: _dayView
                            ? 'No collector has stated a line for this day.'
                            : _historyView
                                ? 'No hand-over matches these filters.'
                                : 'No unpaid bill matches these filters.',
                      )
                    : _dayView
                        ? _daySheetGrid(_sheet!)
                        : (_historyView ? _historyGrid() : _billGrid()),
          ),
        ],
      ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: false,
        message: 'Bills with collectors',
      ),
    );
  }
}
