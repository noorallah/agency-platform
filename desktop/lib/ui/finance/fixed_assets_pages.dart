// Fixed assets (PG-13), under Accounts: the asset register, the asset classes,
// the depreciation runs and the Income-tax block schedule. Phase 2 only.

import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../../models/fixed_asset.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/reason_prompt.dart';

String _money(String value) {
  final double? parsed = double.tryParse(value);
  return parsed == null ? '—' : parsed.toStringAsFixed(2);
}

String _plain(String value) {
  if (!value.contains('.')) return value;
  return value.replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '');
}

String _today() => DateTime.now().toIso8601String().split('T').first;

String _iso(DateTime date) => date.toIso8601String().split('T').first;

Future<String?> _pickDate(BuildContext context, String current) async {
  final DateTime? picked = await showDatePicker(
    context: context,
    initialDate: DateTime.tryParse(current) ?? DateTime.now(),
    firstDate: DateTime(2000),
    lastDate: DateTime(2100),
  );
  return picked == null ? null : _iso(picked);
}

void _say(BuildContext context, String message, {bool error = false}) {
  if (!context.mounted) return;
  NotificationService.show(
    context,
    message,
    kind: error ? AppNotificationKind.error : AppNotificationKind.success,
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

Widget _box(
  String label,
  TextEditingController controller,
  Key key, {
  double width = 180,
  bool number = false,
  bool enabled = true,
  String? helper,
}) =>
    SizedBox(
      width: width,
      child: TextField(
        key: key,
        controller: controller,
        enabled: enabled,
        keyboardType: number
            ? const TextInputType.numberWithOptions(decimal: true)
            : null,
        decoration: InputDecoration(
          labelText: label,
          isDense: true,
          helperText: helper,
          helperMaxLines: 2,
        ),
      ),
    );

/// A dialog frame that stays inside the window from 800x600 up: a title, a
/// scrolling body and a row of actions.
class _Frame extends StatelessWidget {
  const _Frame({
    required this.title,
    required this.body,
    required this.actions,
    this.badge,
    this.maxWidth = 760,
  });

  final String title;
  final Widget body;
  final List<Widget> actions;
  final Widget? badge;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    final Size size = MediaQuery.sizeOf(context);
    return Dialog(
      insetPadding: const EdgeInsets.all(AppSpacing.lg),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: (size.width - 48).clamp(320.0, maxWidth),
          maxHeight: (size.height - 48).clamp(300.0, 700.0),
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
                    title,
                    style: Theme.of(context).textTheme.titleLarge,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (badge != null) badge!,
              ]),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding:
                    const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                child: body,
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Wrap(
                alignment: WrapAlignment.end,
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: actions,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _problemText(BuildContext context, String? problem, Key key) =>
    problem == null
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(problem,
                key: key,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          );

Widget _noFirm(String what) => WorkspaceEmptyState(
      title: 'Choose a firm',
      message: '$what belong to one firm.',
    );

Widget _noView(String what) => WorkspaceEmptyState(
      icon: Icons.lock_outline,
      title: 'You cannot see $what',
      message: 'Reading them needs the view fixed assets permission.',
    );

// ===========================================================================
// Asset register
// ===========================================================================

/// The register: every asset with its cost, depreciation to date and net
/// book value. Add by hand, change, see the schedule, dispose.
class AssetRegisterPage extends StatefulWidget {
  const AssetRegisterPage({
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
  State<AssetRegisterPage> createState() => _AssetRegisterPageState();
}

class _AssetRegisterPageState extends State<AssetRegisterPage> {
  List<FixedAsset> _rows = const [];
  List<AssetClass> _classes = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String _status = '';
  String _classId = '';
  String _asOf = '';
  final TextEditingController _search = TextEditingController();

  void _tell(String message, {bool error = false}) {
    if (!mounted) return;
    _say(context, message, error: error);
  }

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('FIXED_ASSET_VIEW');
  bool get _mayManage => _may('FIXED_ASSET_MANAGE');
  bool get _mayPost => _may('JOURNAL_POST');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) {
      unawaited(_loadClasses());
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadClasses() async {
    try {
      final PagedResult<AssetClass> page =
          await widget.api.assetClasses(pageSize: 100);
      if (!mounted) return;
      setState(() => _classes = page.items);
    } on ApiException {
      // The filter simply offers no classes; the register still loads.
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<FixedAsset> page = await widget.api.fixedAssets(
        search: _search.text.trim(),
        status: _status,
        assetClassId: _classId,
        asOf: _asOf,
        pageSize: 100,
      );
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

  FixedAsset? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  Future<void> _open(FixedAsset? row) async {
    FixedAsset? full = row;
    if (row != null) {
      try {
        full = await widget.api.fixedAsset(row.id);
      } on ApiException catch (error) {
        _tell(error.message, error: true);
        return;
      }
    }
    if (!mounted) return;
    final FixedAsset? saved = await showDialog<FixedAsset>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AssetDialog(
        api: widget.api,
        existing: full,
        classes: _classes,
        mayManage: _mayManage,
      ),
    );
    if (saved == null || !mounted) return;
    _tell('Asset ${saved.assetNumber} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _schedule(FixedAsset row) async {
    try {
      final AssetSchedule schedule =
          await widget.api.fixedAssetSchedule(row.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => AssetScheduleDialog(asset: row, schedule: schedule),
      );
    } on ApiException catch (error) {
      _tell(error.message, error: true);
    }
  }

  Future<void> _dispose(FixedAsset row) async {
    final FixedAsset? done = await showDialog<FixedAsset>(
      context: context,
      barrierDismissible: false,
      builder: (_) => DisposeAssetDialog(api: widget.api, asset: row),
    );
    if (done == null || !mounted) return;
    _tell('Asset ${done.assetNumber} disposed.');
    await _load();
  }

  Future<void> _delete(FixedAsset row) async {
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete ${row.assetNumber}'),
        content: const Text(
            'Only an asset that no depreciation has been charged on can be '
            'deleted.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          FilledButton(
            key: const ValueKey('asset-delete-confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await widget.api.deleteFixedAsset(row.id);
      if (!mounted) return;
      _tell('Asset ${row.assetNumber} deleted.');
      _selectedId = null;
      await _load();
    } on ApiException catch (error) {
      _tell(error.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) return _noFirm('Fixed assets');
    if (!_mayView) return _noView('fixed assets');
    final FixedAsset? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'Every asset the firm holds, at cost less the depreciation '
          'charged. A capital-goods bill line raises its asset when the bill '
          'is approved; one bought earlier is added here by hand.',
      toolbar: _toolbar(picked),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.assetNumber,
              party: picked.name,
              status: picked.status,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Fixed assets',
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
        _filters(),
        const SizedBox(height: AppSpacing.sm),
        Expanded(child: _grid()),
      ],
    );
  }

  /// The filters sit above the grid rather than in the toolbar, which has no
  /// room for four of them at 800 pixels wide.
  Widget _filters() => Padding(
        padding: const EdgeInsets.only(top: AppSpacing.sm),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 180,
              child: TextField(
                key: const ValueKey('asset-search'),
                controller: _search,
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'Search',
                  prefixIcon: Icon(Icons.search, size: 16),
                ),
                onSubmitted: (_) => unawaited(_load()),
              ),
            ),
            Phase2MenuChip<String>(
              key: const ValueKey('asset-status-filter'),
              label: 'Show: ${switch (_status) {
                'ACTIVE' => 'In use',
                'DISPOSED' => 'Disposed',
                _ => 'All',
              }}',
              itemBuilder: (_) => const [
                PopupMenuItem<String>(value: '', child: Text('All')),
                PopupMenuItem<String>(value: 'ACTIVE', child: Text('In use')),
                PopupMenuItem<String>(
                    value: 'DISPOSED', child: Text('Disposed')),
              ],
              onSelected: (value) {
                setState(() {
                  _status = value;
                  _selectedId = null;
                });
                unawaited(_load());
              },
            ),
            Phase2MenuChip<String>(
              key: const ValueKey('asset-class-filter'),
              label: 'Class: ${_classes.where((c) => c.id == _classId).map((c) => c.code).firstOrNull ?? 'All'}',
              itemBuilder: (_) => [
                const PopupMenuItem<String>(value: '', child: Text('All')),
                for (final AssetClass c in _classes)
                  PopupMenuItem<String>(
                      value: c.id, child: Text('${c.code} · ${c.name}')),
              ],
              onSelected: (value) {
                setState(() {
                  _classId = value;
                  _selectedId = null;
                });
                unawaited(_load());
              },
            ),
            Phase2MenuChip<String>(
              key: const ValueKey('asset-asof-filter'),
              label: _asOf.isEmpty ? 'As of: today' : 'As of: $_asOf',
              itemBuilder: (_) => const [
                PopupMenuItem<String>(value: 'today', child: Text('Today')),
                PopupMenuItem<String>(value: 'pick', child: Text('Pick a date')),
              ],
              onSelected: (value) async {
                if (value == 'today') {
                  setState(() => _asOf = '');
                } else {
                  final String? date = await _pickDate(context, _asOf);
                  if (date == null) return;
                  setState(() => _asOf = date);
                }
                unawaited(_load());
              },
            ),
          ],
        ),
      );

  WorkspaceToolbar _toolbar(FixedAsset? row) => WorkspaceToolbar(
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
          ToolbarCommand(
            id: 'schedule',
            label: 'Schedule',
            icon: Icons.table_chart_outlined,
            onPressed: row != null ? () => unawaited(_schedule(row)) : null,
          ),
          if (_mayManage && _mayPost)
            ToolbarCommand(
              id: 'dispose',
              label: 'Dispose',
              icon: Icons.sell_outlined,
              onPressed: row != null && row.isActive
                  ? () => unawaited(_dispose(row))
                  : null,
            ),
          if (_mayManage)
            ToolbarCommand(
              id: 'delete',
              label: 'Delete',
              icon: Icons.delete_outline,
              onPressed: row != null && row.isActive
                  ? () => unawaited(_delete(row))
                  : null,
            ),
        ],
      );

  late final ColumnChoice<FixedAsset> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'fixed-assets.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Asset'),
        cell: (item) => item.assetNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'name', label: 'Name'),
        cell: (item) => item.name,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'class', label: 'Class'),
        cell: (item) => item.assetClassCode,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'acquired', label: 'Acquired'),
        cell: (item) => item.acquisitionDate,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'cost', label: 'Cost'),
        cell: (item) => _money(item.cost),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'dep', label: 'Depreciation'),
        cell: (item) => _money(item.accumulatedDepreciation),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'nbv', label: 'Net book value'),
        cell: (item) => _money(item.netBookValue),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'to', label: 'Depreciated to'),
        cell: (item) => item.depreciatedTo,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'bill', label: 'Bill'),
        cell: (item) => item.purchaseInvoiceNumber,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'disposed', label: 'Disposed on'),
        cell: (item) => item.disposedOn,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'sale', label: 'Sale amount'),
        cell: (item) =>
            item.saleAmount.isEmpty ? '' : _money(item.saleAmount),
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'gain', label: 'Gain / loss'),
        cell: (item) =>
            item.disposalGainLoss.isEmpty ? '' : _money(item.disposalGainLoss),
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
        title: 'No fixed assets',
        message: 'Mark a bill line as capital goods, or add an asset by hand.',
      );
    }
    return EnterpriseDataGrid<FixedAsset>(
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

/// Add an asset by hand, or change one. Only what changed is sent on a change,
/// because the server fixes the figures depreciation is worked from once a run
/// has charged the asset.
class AssetDialog extends StatefulWidget {
  const AssetDialog({
    super.key,
    required this.api,
    required this.classes,
    this.existing,
    this.mayManage = true,
  });

  final ApiClient api;
  final List<AssetClass> classes;
  final FixedAsset? existing;
  final bool mayManage;

  @override
  State<AssetDialog> createState() => _AssetDialogState();
}

class _AssetDialogState extends State<AssetDialog>
    with SaveInDialog<AssetDialog> {
  final TextEditingController _name = TextEditingController();
  final TextEditingController _quantity = TextEditingController(text: '1');
  final TextEditingController _cost = TextEditingController();
  final TextEditingController _residual = TextEditingController();
  final TextEditingController _openingDep = TextEditingController();
  final TextEditingController _openingWdv = TextEditingController();
  final TextEditingController _location = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  String _classId = '';
  String _acquired = _today();
  String _putToUse = '';
  String _openingAsOf = '';
  String? _problem;

  FixedAsset? get _record => widget.existing;
  bool get _editable => widget.mayManage && !saving && !(_record?.isDisposed ?? false);

  @override
  void initState() {
    super.initState();
    final FixedAsset? a = _record;
    if (a == null) return;
    _name.text = a.name;
    _classId = a.assetClassId;
    _acquired = a.acquisitionDate;
    _putToUse = a.putToUseDate;
    _quantity.text = _plain(a.quantity);
    _cost.text = _plain(a.cost);
    _residual.text = _plain(a.residualValue);
    _openingDep.text = _plain(a.openingAccumulatedDepreciation);
    _openingAsOf = a.openingAsOf;
    _openingWdv.text = _plain(a.openingItWdv);
    _location.text = a.location;
    _remarks.text = a.remarks;
  }

  @override
  void dispose() {
    for (final TextEditingController c in [
      _name,
      _quantity,
      _cost,
      _residual,
      _openingDep,
      _openingWdv,
      _location,
      _remarks,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _check() {
    if (_name.text.trim().isEmpty) return 'Enter the asset name.';
    if (_classId.isEmpty) return 'Choose the asset class.';
    if ((double.tryParse(_cost.text.trim()) ?? 0) <= 0) {
      return 'The cost must be above 0.';
    }
    if (_record == null && (double.tryParse(_quantity.text.trim()) ?? 0) <= 0) {
      return 'The quantity must be above 0.';
    }
    for (final TextEditingController c in [_residual, _openingDep, _openingWdv]) {
      final String v = c.text.trim();
      if (v.isNotEmpty && (double.tryParse(v) ?? -1) < 0) {
        return 'The residual and opening figures take a number of 0 or '
            'more, or stay blank.';
      }
    }
    final bool opening = _openingDep.text.trim().isNotEmpty &&
        (double.tryParse(_openingDep.text.trim()) ?? 0) > 0;
    if (opening && _openingAsOf.isEmpty) {
      return 'Say the date the opening depreciation is up to.';
    }
    return null;
  }

  bool _same(String typed, String stored) {
    final double? a = double.tryParse(typed.trim());
    final double? b = double.tryParse(stored.trim());
    if (a != null && b != null) return a == b;
    return typed.trim() == stored.trim();
  }

  Json _createBody() => <String, dynamic>{
        'name': _name.text.trim(),
        'asset_class_id': _classId,
        'acquisition_date': _acquired,
        if (_putToUse.isNotEmpty) 'put_to_use_date': _putToUse,
        'quantity': _quantity.text.trim(),
        'cost': _cost.text.trim(),
        if (_residual.text.trim().isNotEmpty)
          'residual_value': _residual.text.trim(),
        if (_openingDep.text.trim().isNotEmpty)
          'opening_accumulated_depreciation': _openingDep.text.trim(),
        if (_openingAsOf.isNotEmpty) 'opening_as_of': _openingAsOf,
        if (_openingWdv.text.trim().isNotEmpty)
          'opening_it_wdv': _openingWdv.text.trim(),
        if (_location.text.trim().isNotEmpty) 'location': _location.text.trim(),
        if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      };

  /// Only the boxes that differ from what the server holds.
  Json _changes(FixedAsset a) => <String, dynamic>{
        if (_name.text.trim() != a.name) 'name': _name.text.trim(),
        if (_classId != a.assetClassId) 'asset_class_id': _classId,
        if (_acquired != a.acquisitionDate) 'acquisition_date': _acquired,
        if (_putToUse.isNotEmpty && _putToUse != a.putToUseDate)
          'put_to_use_date': _putToUse,
        if (!_same(_cost.text, a.cost)) 'cost': _cost.text.trim(),
        if (_residual.text.trim().isNotEmpty &&
            !_same(_residual.text, a.residualValue))
          'residual_value': _residual.text.trim(),
        if (_openingDep.text.trim().isNotEmpty &&
            !_same(_openingDep.text, a.openingAccumulatedDepreciation))
          'opening_accumulated_depreciation': _openingDep.text.trim(),
        if (_openingAsOf.isNotEmpty && _openingAsOf != a.openingAsOf)
          'opening_as_of': _openingAsOf,
        if (_openingWdv.text.trim().isNotEmpty &&
            !_same(_openingWdv.text, a.openingItWdv))
          'opening_it_wdv': _openingWdv.text.trim(),
        if (_location.text.trim() != a.location)
          'location': _location.text.trim().isEmpty ? null : _location.text.trim(),
        if (_remarks.text.trim() != a.remarks)
          'remarks': _remarks.text.trim().isEmpty ? null : _remarks.text.trim(),
      };

  void _save() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    final FixedAsset? existing = _record;
    unawaited(saveAndClose<FixedAsset>(() => existing == null
        ? widget.api.createFixedAsset(_createBody())
        : widget.api.updateFixedAsset(existing.id, _changes(existing),
            expectedVersion: existing.version)));
  }

  @override
  Widget build(BuildContext context) {
    final FixedAsset? a = _record;
    return _Frame(
      title: a == null ? 'New fixed asset' : 'Asset ${a.assetNumber}',
      badge: a == null ? null : StatusBadge(label: a.status),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          saveErrorBanner(),
          _problemText(context, _problem, const ValueKey('asset-problem')),
          if (a != null && a.purchaseInvoiceNumber.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Text('Raised by bill ${a.purchaseInvoiceNumber}.'),
            ),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: [
              _box('Name', _name, const ValueKey('asset-name'),
                  width: 300, enabled: _editable),
              SizedBox(
                width: 260,
                child: DropdownButtonFormField<String>(
                  key: const ValueKey('asset-class'),
                  initialValue: _classId.isEmpty ? null : _classId,
                  isExpanded: true,
                  decoration: const InputDecoration(
                      labelText: 'Asset class', isDense: true),
                  items: [
                    for (final AssetClass c in widget.classes)
                      DropdownMenuItem(
                        value: c.id,
                        child: Text('${c.code} · ${c.name}',
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged:
                      _editable ? (v) => setState(() => _classId = v ?? '') : null,
                ),
              ),
              SizedBox(
                width: 170,
                child: _dateBox(
                  'Acquired on',
                  _acquired,
                  !_editable
                      ? null
                      : () async {
                          final String? v = await _pickDate(context, _acquired);
                          if (v != null) setState(() => _acquired = v);
                        },
                  const ValueKey('asset-acquired'),
                ),
              ),
              SizedBox(
                width: 170,
                child: _dateBox(
                  'Put to use on',
                  _putToUse.isEmpty ? 'same day' : _putToUse,
                  !_editable
                      ? null
                      : () async {
                          final String? v = await _pickDate(
                              context, _putToUse.isEmpty ? _acquired : _putToUse);
                          if (v != null) setState(() => _putToUse = v);
                        },
                  const ValueKey('asset-put-to-use'),
                ),
              ),
              if (a == null)
                _box('Quantity', _quantity, const ValueKey('asset-quantity'),
                    width: 110, number: true),
              _box('Cost', _cost, const ValueKey('asset-cost'),
                  width: 140, number: true, enabled: _editable),
              _box('Residual value', _residual, const ValueKey('asset-residual'),
                  width: 150,
                  number: true,
                  enabled: _editable,
                  helper: 'blank takes the class share'),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Text('Bought earlier? Opening figures',
              style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: [
              _box('Depreciation so far', _openingDep,
                  const ValueKey('asset-opening-dep'),
                  width: 170, number: true, enabled: _editable),
              SizedBox(
                width: 170,
                child: _dateBox(
                  'Up to',
                  _openingAsOf,
                  !_editable
                      ? null
                      : () async {
                          final String? v = await _pickDate(
                              context, _openingAsOf.isEmpty ? _today() : _openingAsOf);
                          if (v != null) setState(() => _openingAsOf = v);
                        },
                  const ValueKey('asset-opening-as-of'),
                ),
              ),
              _box('Income-tax WDV then', _openingWdv,
                  const ValueKey('asset-opening-wdv'),
                  width: 170, number: true, enabled: _editable),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: [
              _box('Location', _location, const ValueKey('asset-location'),
                  width: 300, enabled: _editable),
              _box('Remarks', _remarks, const ValueKey('asset-remarks'),
                  width: 300, enabled: _editable),
            ],
          ),
          if (a != null && a.isDisposed) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              'Disposed on ${a.disposedOn} for ${_money(a.saleAmount)}: '
              '${a.disposalReason}',
              key: const ValueKey('asset-disposal-note'),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          key: const ValueKey('asset-close'),
          onPressed: cancelHandler,
          child: Text(_editable ? 'Cancel' : 'Close'),
        ),
        if (_editable)
          FilledButton(
            key: const ValueKey('asset-save'),
            onPressed: saving ? null : _save,
            child: Text(saving ? 'Saving…' : 'Save'),
          ),
      ],
    );
  }
}

/// Sell or scrap an asset: the date, what it fetched, how the money came and
/// why. The server charges depreciation up to the date first.
class DisposeAssetDialog extends StatefulWidget {
  const DisposeAssetDialog({super.key, required this.api, required this.asset});

  final ApiClient api;
  final FixedAsset asset;

  @override
  State<DisposeAssetDialog> createState() => _DisposeAssetDialogState();
}

class _DisposeAssetDialogState extends State<DisposeAssetDialog>
    with SaveInDialog<DisposeAssetDialog> {
  String _date = _today();
  String _method = 'BANK';
  final TextEditingController _sale = TextEditingController(text: '0');
  final TextEditingController _reason = TextEditingController();
  String? _problem;

  @override
  void dispose() {
    _sale.dispose();
    _reason.dispose();
    super.dispose();
  }

  void _save() {
    final double? sale = double.tryParse(_sale.text.trim());
    String? problem;
    if (sale == null || sale < 0) {
      problem = 'The sale amount is a number of 0 or more; 0 is a scrapping.';
    } else if (_reason.text.trim().isEmpty) {
      problem = 'Say why the asset is being disposed of.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<FixedAsset>(() => widget.api.disposeFixedAsset(
          widget.asset.id,
          {
            'disposal_date': _date,
            'sale_amount': _sale.text.trim(),
            'method': _method,
            'reason': _reason.text.trim(),
          },
        )));
  }

  @override
  Widget build(BuildContext context) => _Frame(
        title: 'Dispose of ${widget.asset.assetNumber}',
        maxWidth: 560,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            _problemText(context, _problem, const ValueKey('dispose-problem')),
            Text('${widget.asset.name} stands at a net book value of '
                '${_money(widget.asset.netBookValue)}. Depreciation is '
                'charged up to the date first.'),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.md,
              children: [
                SizedBox(
                  width: 170,
                  child: _dateBox(
                    'Disposed on',
                    _date,
                    saving
                        ? null
                        : () async {
                            final String? v = await _pickDate(context, _date);
                            if (v != null) setState(() => _date = v);
                          },
                    const ValueKey('dispose-date'),
                  ),
                ),
                _box('Sale amount', _sale, const ValueKey('dispose-sale'),
                    width: 150, number: true, enabled: !saving),
                SizedBox(
                  width: 150,
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('dispose-method'),
                    isExpanded: true,
                    initialValue: _method,
                    decoration: const InputDecoration(
                        labelText: 'Money came by', isDense: true),
                    items: const [
                      DropdownMenuItem(value: 'BANK', child: Text('Bank')),
                      DropdownMenuItem(value: 'CASH', child: Text('Cash')),
                    ],
                    onChanged: saving
                        ? null
                        : (v) => setState(() => _method = v ?? 'BANK'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('dispose-reason'),
              controller: _reason,
              enabled: !saving,
              maxLines: 2,
              decoration: const InputDecoration(
                  labelText: 'Reason', isDense: true),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey('dispose-confirm'),
            onPressed: saving ? null : _save,
            child: Text(saving ? 'Disposing…' : 'Dispose'),
          ),
        ],
      );
}

/// What has been charged on an asset, year by year, and what is still to come.
class AssetScheduleDialog extends StatelessWidget {
  const AssetScheduleDialog(
      {super.key, required this.asset, required this.schedule});

  final FixedAsset asset;
  final AssetSchedule schedule;

  DataRow _row(AssetScheduleEntry e) => DataRow(cells: [
        DataCell(Text('${e.fromDate} to ${e.toDate}')),
        DataCell(Text('${e.days}')),
        DataCell(Text(_money(e.openingBookValue))),
        DataCell(Text(_money(e.amount))),
        DataCell(Text(_money(e.closingBookValue))),
        DataCell(Text(e.projected ? 'Projected' : e.runNumber)),
      ]);

  @override
  Widget build(BuildContext context) => _Frame(
        title: 'Schedule of ${asset.assetNumber}',
        maxWidth: 860,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${schedule.depreciationMethod} · cost '
                '${_money(schedule.cost)} · residual '
                '${_money(schedule.residualValue)}'),
            const SizedBox(height: AppSpacing.sm),
            if (schedule.charged.isEmpty && schedule.projected.isEmpty)
              const Text('Nothing charged yet.',
                  key: ValueKey('schedule-empty'))
            else
              SingleChildScrollView(
                key: const ValueKey('schedule-table'),
                scrollDirection: Axis.horizontal,
                child: DataTable(
                  columns: const [
                    DataColumn(label: Text('Period')),
                    DataColumn(label: Text('Days')),
                    DataColumn(label: Text('Opening')),
                    DataColumn(label: Text('Depreciation')),
                    DataColumn(label: Text('Closing')),
                    DataColumn(label: Text('Run')),
                  ],
                  rows: [
                    for (final AssetScheduleEntry e in schedule.charged)
                      _row(e),
                    for (final AssetScheduleEntry e in schedule.projected)
                      _row(e),
                  ],
                ),
              ),
          ],
        ),
        actions: [
          TextButton(
            key: const ValueKey('schedule-close'),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      );
}

// ===========================================================================
// Asset classes
// ===========================================================================

/// The kinds of asset and how each is depreciated.
class AssetClassesPage extends StatefulWidget {
  const AssetClassesPage({
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
  State<AssetClassesPage> createState() => _AssetClassesPageState();
}

class _AssetClassesPageState extends State<AssetClassesPage> {
  List<AssetClass> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;

  void _tell(String message, {bool error = false}) {
    if (!mounted) return;
    _say(context, message, error: error);
  }

  bool get _mayView => widget.permissions.hasPermission('FIXED_ASSET_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('FIXED_ASSET_MANAGE');

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
      final PagedResult<AssetClass> page =
          await widget.api.assetClasses(pageSize: 100);
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

  AssetClass? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  Future<void> _open(AssetClass? row) async {
    AssetClass? full = row;
    if (row != null) {
      try {
        full = await widget.api.assetClass(row.id);
      } on ApiException catch (error) {
        _tell(error.message, error: true);
        return;
      }
    }
    if (!mounted) return;
    final AssetClass? saved = await showDialog<AssetClass>(
      context: context,
      barrierDismissible: false,
      builder: (_) => AssetClassDialog(
        api: widget.api,
        existing: full,
        mayManage: _mayManage,
      ),
    );
    if (saved == null || !mounted) return;
    _tell('Asset class ${saved.code} saved.');
    _selectedId = saved.id;
    await _load();
  }

  Future<void> _delete(AssetClass row) async {
    final bool? sure = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete ${row.code}'),
        content: const Text('A class that holds assets cannot be deleted.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          FilledButton(
            key: const ValueKey('class-delete-confirm'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await widget.api.deleteAssetClass(row.id);
      if (!mounted) return;
      _tell('Asset class ${row.code} deleted.');
      _selectedId = null;
      await _load();
    } on ApiException catch (error) {
      _tell(error.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) return _noFirm('Asset classes');
    if (!_mayView) return _noView('asset classes');
    final AssetClass? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'How each kind of asset is depreciated. A change applies to '
          'depreciation charged from now on; what was charged stands.',
      toolbar: WorkspaceToolbar(
        actions: [
          if (_mayManage) ToolbarAction.newItem,
          ToolbarAction.view,
          ToolbarAction.refresh,
        ],
        isEnabled: (action) => action != ToolbarAction.view || picked != null,
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_open(null));
            case ToolbarAction.view:
              if (picked != null) unawaited(_open(picked));
            default:
              unawaited(_load());
          }
        },
        commands: [
          if (_mayManage)
            ToolbarCommand(
              id: 'delete',
              label: 'Delete',
              icon: Icons.delete_outline,
              onPressed:
                  picked != null ? () => unawaited(_delete(picked)) : null,
            ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.code,
              party: picked.name,
              status: picked.isActive ? 'ACTIVE' : 'INACTIVE',
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Asset classes',
      ),
    );
  }

  late final ColumnChoice<AssetClass> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'asset-classes.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'code', label: 'Code'),
        cell: (item) => item.code,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'name', label: 'Name'),
        cell: (item) => item.name,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'method', label: 'Method'),
        cell: (item) => item.depreciationMethod,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'rate', label: 'Rate %'),
        cell: (item) => _plain(item.ratePercent),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'life', label: 'Life (years)'),
        cell: (item) => _plain(item.usefulLifeYears),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'residual', label: 'Residual %'),
        cell: (item) => _plain(item.residualPercent),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'it', label: 'Income-tax rate %'),
        cell: (item) => _plain(item.itBlockRatePercent),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'active', label: 'Active'),
        cell: (item) => item.isActive ? 'Yes' : 'No',
        shownByDefault: true,
      ),
    ],
  );

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
        Expanded(
          child: _rows.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'No asset classes',
                  message: 'Add a class before raising assets.',
                )
              : EnterpriseDataGrid<AssetClass>(
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
                ),
        ),
      ],
    );
  }
}

/// Add or change an asset class. A change sends only the boxes that moved.
class AssetClassDialog extends StatefulWidget {
  const AssetClassDialog({
    super.key,
    required this.api,
    this.existing,
    this.mayManage = true,
  });

  final ApiClient api;
  final AssetClass? existing;
  final bool mayManage;

  @override
  State<AssetClassDialog> createState() => _AssetClassDialogState();
}

class _AssetClassDialogState extends State<AssetClassDialog>
    with SaveInDialog<AssetClassDialog> {
  final TextEditingController _code = TextEditingController();
  final TextEditingController _name = TextEditingController();
  final TextEditingController _rate = TextEditingController();
  final TextEditingController _life = TextEditingController();
  final TextEditingController _residual = TextEditingController(text: '5');
  final TextEditingController _itRate = TextEditingController(text: '0');
  final TextEditingController _description = TextEditingController();
  String _method = 'SLM';
  bool _active = true;
  String? _problem;

  AssetClass? get _record => widget.existing;
  bool get _editable => widget.mayManage && !saving;

  @override
  void initState() {
    super.initState();
    final AssetClass? c = _record;
    if (c == null) return;
    _code.text = c.code;
    _name.text = c.name;
    _method = c.depreciationMethod;
    _rate.text = _plain(c.ratePercent);
    _life.text = _plain(c.usefulLifeYears);
    _residual.text = _plain(c.residualPercent);
    _itRate.text = _plain(c.itBlockRatePercent);
    _description.text = c.description;
    _active = c.isActive;
  }

  @override
  void dispose() {
    for (final TextEditingController c in [
      _code,
      _name,
      _rate,
      _life,
      _residual,
      _itRate,
      _description,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _check() {
    if (_code.text.trim().isEmpty) return 'Enter the class code.';
    if (_name.text.trim().isEmpty) return 'Enter the class name.';
    final bool hasRate = _rate.text.trim().isNotEmpty;
    final bool hasLife = _life.text.trim().isNotEmpty;
    if (_method == 'SLM' && !hasRate && !hasLife) {
      return 'Straight line needs a useful life or a rate.';
    }
    if (_method == 'WDV' && !hasRate && !hasLife) {
      return 'Written down value needs a rate, or a life to work one from.';
    }
    for (final (String name, TextEditingController c, double max) in [
      ('rate', _rate, 100),
      ('residual', _residual, 100),
      ('Income-tax rate', _itRate, 100),
    ]) {
      final String v = c.text.trim();
      if (v.isEmpty) continue;
      final double? n = double.tryParse(v);
      if (n == null || n < 0 || n > max) {
        return 'The $name is a percentage from 0 to 100.';
      }
    }
    if (hasLife && (double.tryParse(_life.text.trim()) ?? 0) <= 0) {
      return 'The useful life must be above 0 years.';
    }
    return null;
  }

  bool _same(String typed, String stored) {
    final double? a = double.tryParse(typed.trim());
    final double? b = double.tryParse(stored.trim());
    if (a != null && b != null) return a == b;
    return typed.trim() == stored.trim();
  }

  Json _createBody() => <String, dynamic>{
        'code': _code.text.trim(),
        'name': _name.text.trim(),
        'depreciation_method': _method,
        if (_rate.text.trim().isNotEmpty) 'rate_percent': _rate.text.trim(),
        if (_life.text.trim().isNotEmpty)
          'useful_life_years': _life.text.trim(),
        if (_residual.text.trim().isNotEmpty)
          'residual_percent': _residual.text.trim(),
        if (_itRate.text.trim().isNotEmpty)
          'it_block_rate_percent': _itRate.text.trim(),
        'is_active': _active,
        if (_description.text.trim().isNotEmpty)
          'description': _description.text.trim(),
      };

  Json _changes(AssetClass c) => <String, dynamic>{
        if (_code.text.trim() != c.code) 'code': _code.text.trim(),
        if (_name.text.trim() != c.name) 'name': _name.text.trim(),
        if (_method != c.depreciationMethod) 'depreciation_method': _method,
        if (_rate.text.trim().isNotEmpty && !_same(_rate.text, c.ratePercent))
          'rate_percent': _rate.text.trim(),
        if (_life.text.trim().isNotEmpty &&
            !_same(_life.text, c.usefulLifeYears))
          'useful_life_years': _life.text.trim(),
        if (_residual.text.trim().isNotEmpty &&
            !_same(_residual.text, c.residualPercent))
          'residual_percent': _residual.text.trim(),
        if (_itRate.text.trim().isNotEmpty &&
            !_same(_itRate.text, c.itBlockRatePercent))
          'it_block_rate_percent': _itRate.text.trim(),
        if (_active != c.isActive) 'is_active': _active,
        if (_description.text.trim() != c.description)
          'description':
              _description.text.trim().isEmpty ? null : _description.text.trim(),
      };

  void _save() {
    final String? problem = _check();
    setState(() => _problem = problem);
    if (problem != null) return;
    final AssetClass? existing = _record;
    unawaited(saveAndClose<AssetClass>(() => existing == null
        ? widget.api.createAssetClass(_createBody())
        : widget.api.updateAssetClass(existing.id, _changes(existing),
            expectedVersion: existing.version)));
  }

  @override
  Widget build(BuildContext context) => _Frame(
        title: _record == null ? 'New asset class' : 'Asset class ${_record!.code}',
        maxWidth: 680,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            _problemText(context, _problem, const ValueKey('class-problem')),
            Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.md,
              children: [
                _box('Code', _code, const ValueKey('class-code'),
                    width: 130, enabled: _editable),
                _box('Name', _name, const ValueKey('class-name'),
                    width: 300, enabled: _editable),
                SizedBox(
                  width: 190,
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('class-method'),
                    isExpanded: true,
                    initialValue: _method,
                    decoration: const InputDecoration(
                        labelText: 'Method', isDense: true),
                    items: const [
                      DropdownMenuItem(
                          value: 'SLM', child: Text('Straight line')),
                      DropdownMenuItem(
                          value: 'WDV', child: Text('Written down value')),
                    ],
                    onChanged: _editable
                        ? (v) => setState(() => _method = v ?? 'SLM')
                        : null,
                  ),
                ),
                _box('Rate %', _rate, const ValueKey('class-rate'),
                    width: 110, number: true, enabled: _editable),
                _box('Useful life (years)', _life, const ValueKey('class-life'),
                    width: 150, number: true, enabled: _editable),
                _box('Residual %', _residual, const ValueKey('class-residual'),
                    width: 110, number: true, enabled: _editable),
                _box('Income-tax rate %', _itRate, const ValueKey('class-it-rate'),
                    width: 150, number: true, enabled: _editable),
                _box('Description', _description,
                    const ValueKey('class-description'),
                    width: 300, enabled: _editable),
              ],
            ),
            SwitchListTile(
              key: const ValueKey('class-active'),
              contentPadding: EdgeInsets.zero,
              title: const Text('Active'),
              value: _active,
              onChanged: _editable ? (v) => setState(() => _active = v) : null,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: cancelHandler,
            child: Text(widget.mayManage ? 'Cancel' : 'Close'),
          ),
          if (widget.mayManage)
            FilledButton(
              key: const ValueKey('class-save'),
              onPressed: saving ? null : _save,
              child: Text(saving ? 'Saving…' : 'Save'),
            ),
        ],
      );
}

// ===========================================================================
// Depreciation runs
// ===========================================================================

/// Depreciation runs: one journal for a period's charges. Run for a period,
/// read a run with its lines, cancel one with a reason.
class DepreciationRunsPage extends StatefulWidget {
  const DepreciationRunsPage({
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
  State<DepreciationRunsPage> createState() => _DepreciationRunsPageState();
}

class _DepreciationRunsPageState extends State<DepreciationRunsPage> {
  List<DepreciationRun> _rows = const [];
  String? _error;
  String? _selectedId;
  bool _loading = true;
  String _status = '';
  String _runType = '';

  void _tell(String message, {bool error = false}) {
    if (!mounted) return;
    _say(context, message, error: error);
  }

  bool _may(String code) => widget.permissions.hasPermission(code);
  bool get _mayView => _may('FIXED_ASSET_VIEW');
  bool get _mayRun => _may('FIXED_ASSET_MANAGE') && _may('JOURNAL_POST');

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
      final PagedResult<DepreciationRun> page = await widget.api
          .depreciationRuns(status: _status, runType: _runType, pageSize: 100);
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

  DepreciationRun? get _selected =>
      _rows.where((row) => row.id == _selectedId).firstOrNull;

  Future<void> _run() async {
    final DepreciationRun? done = await showDialog<DepreciationRun>(
      context: context,
      barrierDismissible: false,
      builder: (_) => RunDepreciationDialog(api: widget.api),
    );
    if (done == null || !mounted) return;
    _tell('Depreciation run ${done.runNumber} posted.');
    _selectedId = done.id;
    await _load();
  }

  Future<void> _view(DepreciationRun row) async {
    try {
      final DepreciationRun full = await widget.api.depreciationRun(row.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => DepreciationRunDialog(run: full),
      );
    } on ApiException catch (error) {
      _tell(error.message, error: true);
    }
  }

  Future<void> _cancel(DepreciationRun row) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel run ${row.runNumber}',
      explanation: 'The journal is reversed and the depreciation comes off '
          'the assets. The reason is kept with the run.',
      confirmLabel: 'Cancel the run',
    );
    if (reason == null) return;
    try {
      final DepreciationRun done =
          await widget.api.cancelDepreciationRun(row.id, reason);
      if (!mounted) return;
      _tell('Run ${done.runNumber} cancelled.');
      await _load();
    } on ApiException catch (error) {
      _tell(error.message, error: true);
    }
  }

  /// The filters sit above the grid, not in a toolbar too narrow at 800.
  Widget _filters() => Padding(
        padding: const EdgeInsets.only(top: AppSpacing.sm),
        child: Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Phase2MenuChip<String>(
              key: const ValueKey('run-status-filter'),
              label: 'Show: ${switch (_status) {
                'POSTED' => 'Posted',
                'CANCELLED' => 'Cancelled',
                _ => 'All',
              }}',
              itemBuilder: (_) => const [
                PopupMenuItem<String>(value: '', child: Text('All')),
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
            Phase2MenuChip<String>(
              key: const ValueKey('run-type-filter'),
              label: 'Type: ${switch (_runType) {
                'PERIODIC' => 'Periodic',
                'DISPOSAL' => 'Disposal',
                _ => 'All',
              }}',
              itemBuilder: (_) => const [
                PopupMenuItem<String>(value: '', child: Text('All')),
                PopupMenuItem<String>(
                    value: 'PERIODIC', child: Text('Periodic')),
                PopupMenuItem<String>(
                    value: 'DISPOSAL', child: Text('Disposal')),
              ],
              onSelected: (value) {
                setState(() {
                  _runType = value;
                  _selectedId = null;
                });
                unawaited(_load());
              },
            ),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) return _noFirm('Depreciation runs');
    if (!_mayView) return _noView('depreciation runs');
    final DepreciationRun? picked = _selected;
    return ManagementWorkspaceLayout(
      notice: 'A run charges every asset its depreciation for a period and '
          'posts one journal. A disposal raises its own run.',
      toolbar: WorkspaceToolbar(
        actions: [
          if (_mayRun) ToolbarAction.newItem,
          ToolbarAction.view,
          ToolbarAction.refresh,
        ],
        newLabel: 'Run depreciation',
        isEnabled: (action) => action != ToolbarAction.view || picked != null,
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              unawaited(_run());
            case ToolbarAction.view:
              if (picked != null) unawaited(_view(picked));
            default:
              unawaited(_load());
          }
        },
        commands: [
          if (_mayRun)
            ToolbarCommand(
              id: 'cancel',
              label: 'Cancel',
              icon: Icons.cancel_outlined,
              onPressed: picked != null &&
                      picked.isPosted &&
                      picked.runType == 'PERIODIC'
                  ? () => unawaited(_cancel(picked))
                  : null,
            ),
        ],
      ),
      searchPanel: const SizedBox.shrink(),
      selectionBar: true,
      selection: picked == null
          ? null
          : SelectionSummary.document(
              number: picked.runNumber,
              party: '${picked.periodFrom} to ${picked.periodTo}',
              status: picked.status,
              onClear: () => setState(() => _selectedId = null),
            ),
      primaryContent: _content(),
      statusBar: WorkspaceStatusBar(
        total: _rows.length,
        selected: _selectedId != null,
        message: 'Depreciation runs',
      ),
    );
  }

  late final ColumnChoice<DepreciationRun> _columns = ColumnChoice(
    preferences: widget.preferences,
    stateKey: 'depreciation-runs.grid',
    columns: [
      ChoosableColumn(
        column: const GridColumn(key: 'number', label: 'Run'),
        cell: (item) => item.runNumber,
        required: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'type', label: 'Type'),
        cell: (item) => item.runType,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'from', label: 'From'),
        cell: (item) => item.periodFrom,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'to', label: 'To'),
        cell: (item) => item.periodTo,
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'total', label: 'Depreciation'),
        cell: (item) => _money(item.totalAmount),
        shownByDefault: true,
      ),
      ChoosableColumn(
        column: const GridColumn(key: 'status', label: 'Status'),
        cell: (item) => item.status,
        shownByDefault: true,
      ),
    ],
  );

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
        _filters(),
        const SizedBox(height: AppSpacing.sm),
        Expanded(
          child: _rows.isEmpty
              ? const WorkspaceEmptyState(
                  title: 'No depreciation runs',
                  message: 'Run depreciation for a period to charge the '
                      'assets.',
                )
              : EnterpriseDataGrid<DepreciationRun>(
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
                    unawaited(_view(row));
                  },
                  onPageChanged: (_) {},
                ),
        ),
      ],
    );
  }
}

/// Charge depreciation for a period.
class RunDepreciationDialog extends StatefulWidget {
  const RunDepreciationDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<RunDepreciationDialog> createState() => _RunDepreciationDialogState();
}

class _RunDepreciationDialogState extends State<RunDepreciationDialog>
    with SaveInDialog<RunDepreciationDialog> {
  late String _from;
  late String _to;
  final TextEditingController _remarks = TextEditingController();
  String? _problem;

  @override
  void initState() {
    super.initState();
    final DateTime now = DateTime.now();
    // Last month, whole: the usual run.
    _from = _iso(DateTime(now.year, now.month - 1, 1));
    _to = _iso(DateTime(now.year, now.month, 0));
  }

  @override
  void dispose() {
    _remarks.dispose();
    super.dispose();
  }

  void _save() {
    String? problem;
    if (_to.compareTo(_from) < 0) {
      problem = 'The period cannot end before it starts.';
    }
    setState(() => _problem = problem);
    if (problem != null) return;
    unawaited(saveAndClose<DepreciationRun>(
        () => widget.api.createDepreciationRun({
              'period_from': _from,
              'period_to': _to,
              'book': 'COMPANIES_ACT',
              if (_remarks.text.trim().isNotEmpty)
                'remarks': _remarks.text.trim(),
            })));
  }

  @override
  Widget build(BuildContext context) => _Frame(
        title: 'Run depreciation',
        maxWidth: 520,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            _problemText(context, _problem, const ValueKey('run-problem')),
            const Text('Every asset in use is charged for the days of the '
                'period not already charged, and one journal is posted.'),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.md,
              children: [
                SizedBox(
                  width: 170,
                  child: _dateBox(
                    'From',
                    _from,
                    saving
                        ? null
                        : () async {
                            final String? v = await _pickDate(context, _from);
                            if (v != null) setState(() => _from = v);
                          },
                    const ValueKey('run-from'),
                  ),
                ),
                SizedBox(
                  width: 170,
                  child: _dateBox(
                    'To',
                    _to,
                    saving
                        ? null
                        : () async {
                            final String? v = await _pickDate(context, _to);
                            if (v != null) setState(() => _to = v);
                          },
                    const ValueKey('run-to'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            TextField(
              key: const ValueKey('run-remarks'),
              controller: _remarks,
              enabled: !saving,
              decoration: const InputDecoration(
                  labelText: 'Remarks (optional)', isDense: true),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: cancelHandler, child: const Text('Cancel')),
          FilledButton(
            key: const ValueKey('run-confirm'),
            onPressed: saving ? null : _save,
            child: Text(saving ? 'Running…' : 'Run depreciation'),
          ),
        ],
      );
}

/// A run with the charge it made on each asset.
class DepreciationRunDialog extends StatelessWidget {
  const DepreciationRunDialog({super.key, required this.run});

  final DepreciationRun run;

  @override
  Widget build(BuildContext context) => _Frame(
        title: 'Run ${run.runNumber}',
        badge: StatusBadge(label: run.status),
        maxWidth: 860,
        body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${run.periodFrom} to ${run.periodTo} · '
                '${run.runType == 'DISPOSAL' ? 'disposal' : 'periodic'} · '
                'total ${_money(run.totalAmount)}'),
            if (run.isCancelled)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.sm),
                child: Text('Cancelled: ${run.cancelReason}',
                    key: const ValueKey('run-cancel-reason')),
              ),
            const SizedBox(height: AppSpacing.sm),
            SingleChildScrollView(
              key: const ValueKey('run-lines'),
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columns: const [
                  DataColumn(label: Text('Asset')),
                  DataColumn(label: Text('Name')),
                  DataColumn(label: Text('Period')),
                  DataColumn(label: Text('Days')),
                  DataColumn(label: Text('Opening')),
                  DataColumn(label: Text('Depreciation')),
                ],
                rows: [
                  for (final DepreciationRunLine l in run.lines)
                    DataRow(cells: [
                      DataCell(Text(l.assetNumber)),
                      DataCell(Text(l.assetName)),
                      DataCell(Text('${l.fromDate} to ${l.toDate}')),
                      DataCell(Text('${l.days}')),
                      DataCell(Text(_money(l.openingBookValue))),
                      DataCell(Text(_money(l.amount))),
                    ]),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            key: const ValueKey('run-close'),
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      );
}

// ===========================================================================
// Income-tax block schedule
// ===========================================================================

/// The Income-tax block schedule for a financial year: it needs a year chosen,
/// which the generic report grid cannot ask for, so this is its own screen.
class ItBlockSchedulePage extends StatefulWidget {
  const ItBlockSchedulePage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<ItBlockSchedulePage> createState() => _ItBlockSchedulePageState();
}

class _ItBlockSchedulePageState extends State<ItBlockSchedulePage> {
  List<FinancialYear> _years = const [];
  List<ItBlockRow> _rows = const [];
  String _yearId = '';
  String? _error;
  bool _loading = true;
  bool _ran = false;

  bool get _mayView => widget.permissions.hasPermission('FIXED_ASSET_VIEW');

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) unawaited(_loadYears());
  }

  Future<void> _loadYears() async {
    try {
      final List<FinancialYear> years = await widget.api.financialYears();
      if (!mounted) return;
      final FinancialYear? current =
          years.where((y) => y.isActive).firstOrNull ?? years.firstOrNull;
      setState(() {
        _years = years;
        _yearId = current?.id ?? '';
        _loading = false;
      });
      if (_yearId.isNotEmpty) unawaited(_run());
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Future<void> _run() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<ItBlockRow> rows = await widget.api.itBlockSchedule(_yearId);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _ran = true;
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

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) return _noFirm('Fixed assets');
    if (!_mayView) return _noView('the block schedule');
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Opening written down value, additions at the full and half rate, '
            'disposals, depreciation and closing value for each Income-tax '
            'block.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.md),
          Align(
            alignment: Alignment.centerLeft,
            child: SizedBox(
              width: 300,
              child: DropdownButtonFormField<String>(
                key: const ValueKey('it-block-year'),
                initialValue: _yearId.isEmpty ? null : _yearId,
                isExpanded: true,
                decoration: const InputDecoration(
                    labelText: 'Financial year', isDense: true),
                items: [
                  for (final FinancialYear y in _years)
                    DropdownMenuItem(
                      value: y.id,
                      child: Text('${y.name.isEmpty ? y.code : y.name} · ${y.span}',
                          overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (value) {
                  setState(() => _yearId = value ?? '');
                  if (_yearId.isNotEmpty) unawaited(_run());
                },
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_error != null)
            Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (!_ran || _rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No blocks',
        message: 'No asset has an Income-tax rate in this year.',
      );
    }
    return SingleChildScrollView(
      child: SingleChildScrollView(
        key: const ValueKey('it-block-table'),
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Rate %')),
            DataColumn(label: Text('Classes')),
            DataColumn(label: Text('Opening WDV')),
            DataColumn(label: Text('Additions (full)')),
            DataColumn(label: Text('Additions (half)')),
            DataColumn(label: Text('Disposals')),
            DataColumn(label: Text('Depreciation')),
            DataColumn(label: Text('Closing WDV')),
            DataColumn(label: Text('Short-term gain')),
          ],
          rows: [
            for (final ItBlockRow r in _rows)
              DataRow(cells: [
                DataCell(Text(_plain(r.blockRate))),
                DataCell(Text(r.classNames.join(', '))),
                DataCell(Text(_money(r.openingWdv))),
                DataCell(Text(_money(r.additionsFullRate))),
                DataCell(Text(_money(r.additionsHalfRate))),
                DataCell(Text(_money(r.disposals))),
                DataCell(Text(_money(r.depreciation))),
                DataCell(Text(_money(r.closingWdv))),
                DataCell(Text(_money(r.shortTermCapitalGain))),
              ]),
          ],
        ),
      ),
    );
  }
}
