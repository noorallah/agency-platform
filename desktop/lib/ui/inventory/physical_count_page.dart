import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/physical_count.dart';
import '../workspace/desktop_framework.dart';
import 'count_plans_dialog.dart';
import 'physical_count_sheet_dialog.dart';

/// Counting a warehouse.
///
/// A sheet is drawn up from what the system holds, walked over hours by people
/// with a clipboard, and posted once at the end. The screen is built around
/// that: opening a sheet and posting it are separate actions, and what has been
/// counted so far is saved rather than held in the form.
class PhysicalCountPage extends StatefulWidget {
  const PhysicalCountPage({
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
  State<PhysicalCountPage> createState() => _PhysicalCountPageState();
}

class _PhysicalCountPageState extends State<PhysicalCountPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<PhysicalCountSheet> _sheets = const [];
  PhysicalCountSheet? _selected;

  /// The count dates the list is narrowed to (owner, 2026-09-27).
  DatePeriod _period = const DatePeriod.all();
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('INVENTORY_VIEW');
  bool get _canCount => widget.permissions.hasPermission('INVENTORY_ADJUST');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<PhysicalCountSheet> result =
          await widget.api.physicalCounts(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        countFrom: _period.from == null ? null : DatePeriod.iso(_period.from!),
        countTo: _period.to == null ? null : DatePeriod.iso(_period.to!),
      );
      if (!mounted) return;
      setState(() {
        _sheets = result.items;
        _total = result.total;
        // Keep the picked sheet across a reload, unless it fell off the page.
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : result.items.where((item) => item.id == selectedId).firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _sheets = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openSheet() async {
    setState(() => _loading = true);
    List<BranchRecord> branches = const [];
    List<WarehouseRecord> warehouses = const [];
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.branches(page: 1, pageSize: 100),
        widget.api.warehouses(page: 1, pageSize: 100),
      ]);
      branches = (results[0] as PagedResult<BranchRecord>).items;
      warehouses = (results[1] as PagedResult<WarehouseRecord>).items;
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted) return;
    if (warehouses.isEmpty) {
      setState(() => _error = 'There is no warehouse to count yet.');
      return;
    }
    final Json? draft = await showDialog<Json>(
      context: context,
      builder: (_) =>
          OpenCountDialog(branches: branches, warehouses: warehouses),
    );
    if (draft == null) return;
    try {
      final PhysicalCountSheet sheet =
          await widget.api.openPhysicalCount(draft);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${sheet.countNumber} opened over ${sheet.lines.length} lines.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: 1);
      if (!mounted) return;
      await _editSheet(sheet);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  /// Count plans (STK-6). A plan that draws a sheet closes the dialog with it,
  /// and the sheet opens for counting straight away.
  Future<void> _plans() async {
    final PhysicalCountSheet? drawn = await showDialog<PhysicalCountSheet>(
      context: context,
      builder: (_) => CountPlansDialog(api: widget.api, canManage: _canCount),
    );
    if (drawn == null || !mounted) return;
    NotificationService.show(
      context,
      '${drawn.countNumber} drawn over ${drawn.lines.length} lines.',
      kind: AppNotificationKind.success,
    );
    await _load(requestedPage: 1);
    if (!mounted) return;
    await _editSheet(drawn);
  }

  Future<void> _editSheet(PhysicalCountSheet sheet) async {
    // Re-read it: the list carries what was loaded minutes ago, and somebody
    // else may have been counting the same sheet in the meantime.
    PhysicalCountSheet current = sheet;
    try {
      current = await widget.api.physicalCount(sheet.id);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    if (!mounted) return;
    final bool? changed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PhysicalCountSheetDialog(
        api: widget.api,
        sheet: current,
        canCount: _canCount,
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Physical count',
        message: 'You do not have permission to view stock.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Physical count',
        message: 'Choose a firm to count its warehouses.',
      );
    }
    if (Phase2Scope.of(context)) return _grid(context);
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _search,
                  decoration: const InputDecoration(
                    labelText: 'Search by count number',
                    prefixIcon: Icon(Icons.search),
                    hintText: 'PC-…',
                  ),
                  onSubmitted: (_) => _load(requestedPage: 1),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              OutlinedButton.icon(
                key: const ValueKey<String>('count-plans-open'),
                onPressed: () => unawaited(_plans()),
                icon: const Icon(Icons.event_repeat_outlined),
                label: const Text('Count plans'),
              ),
              const SizedBox(width: AppSpacing.md),
              if (_canCount)
                FilledButton.icon(
                  onPressed: () => unawaited(_openSheet()),
                  icon: const Icon(Icons.add),
                  label: const Text('Open Count'),
                ),
            ]),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
            child: MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ),
        Expanded(
          child: _sheets.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No counts yet',
                  message: 'Opening a count draws up a sheet from what the '
                      'warehouse currently holds. Posting it turns every '
                      'difference into a stock adjustment.',
                )
              : ListView.separated(
                  itemCount: _sheets.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) =>
                      _tile(context, _sheets[index]),
                ),
        ),
        WorkspacePager(
          page: _page,
          pageSize: _rowsPerPage,
          total: _total,
          onPageChanged: (next) => unawaited(_load(requestedPage: next)),
        ),
      ]),
    );
  }

  /// How far a sheet has been walked, in words.
  static String _progress(PhysicalCountSheet sheet) => sheet.isPosted
      ? '${sheet.lines.length} lines · posted'
      : '${sheet.countedLines} of ${sheet.lines.length} lines counted';

  /// Phase 2 (owner, 2026-09-27): a full-width grid, as every list -- the
  /// Period after the search, Columns, option C's bar naming the picked
  /// sheet, and a double-click (or Open) to count it or post it.
  Widget _grid(BuildContext context) {
    final PhysicalCountSheet? selected = _selected;
    return LoadingOverlay(
      loading: _loading,
      child: ManagementWorkspaceLayout(
        toolbar: WorkspaceToolbar(
          actions: const [
            ToolbarAction.view,
            ToolbarAction.refresh,
            ToolbarAction.newItem,
          ],
          newLabel: '+ New count',
          isVisible: (action) => action != ToolbarAction.newItem || _canCount,
          isEnabled: (action) =>
              !_loading &&
              switch (action) {
                ToolbarAction.view => selected != null,
                ToolbarAction.refresh => true,
                ToolbarAction.newItem => _canCount,
                _ => false,
              },
          onAction: (action) {
            switch (action) {
              case ToolbarAction.view:
                if (selected != null) unawaited(_editSheet(selected));
              case ToolbarAction.refresh:
                unawaited(_load());
              case ToolbarAction.newItem:
                unawaited(_openSheet());
              default:
                break;
            }
          },
          // Period right after the search, then Columns (owner).
          trailing: [
            OutlinedButton.icon(
              key: const ValueKey<String>('count-plans-open'),
              onPressed: () => unawaited(_plans()),
              icon: const Icon(Icons.event_repeat_outlined, size: 18),
              label: const Text('Count plans'),
            ),
            DateRangeFilter(
              value: _period,
              onChanged: (period) {
                setState(() => _period = period);
                unawaited(_load(requestedPage: 1));
              },
            ),
            ColumnsButton(
              onPressed: () async {
                if (await _columns.choose(context) && mounted) {
                  setState(() {});
                }
              },
            ),
          ],
        ),
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.document(
                number: selected.countNumber,
                party: selected.warehouseName,
                status: selected.status,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: SearchFilterPanel(
          controller: _search,
          hintText: 'Search count number or warehouse',
          onSearch: (_) => unawaited(_load(requestedPage: 1)),
        ),
        primaryContent: Column(children: [
          if (_error != null)
            MaterialBanner(
              content: Text(_error!),
              actions: [
                TextButton(
                  onPressed: () => setState(() => _error = null),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          Expanded(
            // Nothing yet while the first read is out: the thin bar says it is
            // loading, and "nothing here" would be a claim not yet known.
            child: _loading && _sheets.isEmpty
                ? const SizedBox.shrink()
                : _sheets.isEmpty
                ? (_search.text.trim().isEmpty && _period.from == null
                    ? const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'No counts yet',
                        message: 'Opening a count draws up a sheet from what '
                            'the warehouse currently holds. Posting it turns '
                            'every difference into a stock adjustment.',
                      )
                    : const StandardEmptyState(
                        type: EmptyStateType.noSearchResults,
                      ))
                : EnterpriseDataGrid<PhysicalCountSheet>(
                    columns: _columns.gridColumns,
                    items: _sheets,
                    id: (item) => item.id,
                    selectedId: selected?.id,
                    cells: _columns.cells,
                    onSelect: (item) => setState(() => _selected = item),
                    onOpen: (item) => unawaited(_editSheet(item)),
                    total: _total,
                    pageOffset: (_page - 1) * _rowsPerPage,
                    rowsPerPage: _rowsPerPage,
                    onPageChanged: (offset) {
                      final int next = offset ~/ _rowsPerPage + 1;
                      if (next != _page) unawaited(_load(requestedPage: next));
                    },
                  ),
          ),
        ]),
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: selected != null,
          message: _loading ? 'Loading...' : null,
        ),
      ),
    );
  }

  /// Every column the grid can show; Columns picks among them, remembered
  /// per screen on this PC (owner, 2026-09-27).
  late final ColumnChoice<PhysicalCountSheet> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'physical-counts.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Count Number'),
        cell: (item) => item.countNumber,
        required: true,
      ),
      // Which warehouse was walked; kept at any width.
      ChoosableColumn(
        column:
            const GridColumn(key: 'warehouse', label: 'Warehouse', priority: 1),
        cell: (item) => item.warehouseName,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'date', label: 'Count Date'),
        cell: (item) => item.countDate,
        shownByDefault: true,
      ),
      // How much has been walked is what somebody managing a count wants.
      ChoosableColumn(
        column: const GridColumn(key: 'progress', label: 'Progress'),
        cell: _progress,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.isBlind ? '${item.status} (blind)' : item.status,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'posted', label: 'Posted At'),
        cell: (item) => createdStamp(item.postedAt),
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'remarks', label: 'Remarks'),
        cell: (item) => item.remarks,
      ),
    ],
  );

  Widget _tile(BuildContext context, PhysicalCountSheet sheet) => ListTile(
        title: Text('${sheet.countNumber}  ·  ${sheet.countDate}'),
        // How much of it has been walked is what somebody managing a count
        // wants from a list of them.
        subtitle: Text(
          sheet.isPosted
              ? '${sheet.lines.length} lines · posted'
              : '${sheet.countedLines} of ${sheet.lines.length} lines counted',
        ),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          StatusBadge(label: sheet.status),
          const SizedBox(width: AppSpacing.md),
          const Icon(Icons.chevron_right),
        ]),
        onTap: () => unawaited(_editSheet(sheet)),
      );
}
