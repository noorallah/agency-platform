import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/geography.dart';
import '../workspace/desktop_framework.dart';

/// The shared geography ladder: country > state > district > city > postal
/// code > locality.
///
/// Six masters that every firm's addresses, branches, warehouses and route
/// profiles hang off, and which had no screen at all — the API could list them
/// and create them and nothing else, so the only places that existed were the
/// ones a seeder made.
///
/// One drill-down rather than six tabs: the levels only make sense in their
/// chain (a district belongs to a state, which belongs to a country), and a
/// flat tab per level would ask the user to pick a parent from a dropdown of
/// every district in the country.
///
/// Reference data shared by every firm, so **writing** it is platform-admin
/// only. A firm user gets the browser and no buttons, which is the honest
/// shape: they need to see what exists in order to pick a city for a route.
class GeographyMasterPage extends StatefulWidget {
  const GeographyMasterPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<GeographyMasterPage> createState() => _GeographyMasterPageState();
}

class _GeographyMasterPageState extends State<GeographyMasterPage> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  GeoLevel _level = GeoLevel.country;

  /// The row picked at each level above the current one, so the breadcrumb can
  /// name the chain and a create knows its parent.
  final List<GeoPlaceRecord> _trail = <GeoPlaceRecord>[];

  List<GeoPlaceRecord> _rows = const <GeoPlaceRecord>[];
  GeoPlaceRecord? _selected;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');
  bool get _canWrite => widget.permissions.isPlatformAdmin;

  String get _parentId => _trail.isEmpty ? '' : _trail.last.id;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!_canView) {
      setState(() => _error = 'You do not have permission to view geography.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<GeoPlaceRecord> rows =
          await widget.api.geoPlaces(_level, parentId: _parentId);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _selected = null;
        _loading = false;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  List<GeoPlaceRecord> get _visible {
    final String term = _search.text.trim().toLowerCase();
    if (term.isEmpty) return _rows;
    return _rows
        .where((row) =>
            row.name.toLowerCase().contains(term) ||
            row.code.toLowerCase().contains(term))
        .toList();
  }

  /// Step into the level below the given row.
  void _drillInto(GeoPlaceRecord row) {
    final GeoLevel? child = row.level.child;
    if (child == null) return;
    setState(() {
      _trail.add(row);
      _level = child;
      _search.clear();
    });
    _load();
  }

  /// Step back to a level already in the trail. `depth` 0 is Countries.
  void _jumpTo(int depth) {
    setState(() {
      _trail.removeRange(depth, _trail.length);
      _level = GeoLevel.values[depth];
      _search.clear();
    });
    _load();
  }

  Future<void> _openEditor({GeoPlaceRecord? current}) async {
    if (!_canWrite) return;
    final GeoPlaceRecord? saved = await showDialog<GeoPlaceRecord>(
      context: context,
      builder: (context) => _GeoEditorDialog(level: _level, current: current),
    );
    if (saved == null || !mounted) return;
    try {
      if (current == null) {
        await widget.api
            .createGeoPlace(_level, saved.toJson(parentId: _parentId));
      } else {
        await widget.api.updateGeoPlace(
          _level,
          current.id,
          saved.toJson(parentId: _parentId),
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${_level.label} saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'place', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _delete(GeoPlaceRecord row) async {
    if (!_canWrite) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${row.name}?',
      message: 'Anything still using this ${_level.label.toLowerCase()} will '
          'stop it being deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!accepted || !mounted) return;
    try {
      await widget.api.deleteGeoPlace(_level, row.id);
      await _load();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${row.name} deleted.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      // The server names how many records still point at it, which is the
      // thing the user needs in order to act.
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final Widget toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
      ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem ||
        ToolbarAction.edit ||
        ToolbarAction.delete =>
          _canWrite,
        _ => true,
      },
      isEnabled: (action) => switch (action) {
        ToolbarAction.newItem => _canWrite,
        ToolbarAction.edit => _canWrite && _selected != null,
        ToolbarAction.delete => _canWrite && _selected != null,
        ToolbarAction.refresh => true,
        _ => false,
      },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _openEditor();
          case ToolbarAction.edit:
            if (_selected != null) _openEditor(current: _selected);
          case ToolbarAction.delete:
            if (_selected != null) _delete(_selected!);
          case ToolbarAction.refresh:
            _load();
          default:
            break;
        }
      },
    );

    final Widget searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search ${_level.plural.toLowerCase()}',
      // Filtered here rather than sent: these endpoints answer with a plain
      // list scoped to one parent, and would ignore a search parameter.
      onSearch: (_) => setState(() {}),
      onChanged: (_) => setState(() {}),
      onClear: () => setState(() {}),
    );

    final Widget breadcrumb = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
        spacing: 4,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (int depth = 0; depth < _trail.length; depth++) ...[
            TextButton(
              onPressed: () => _jumpTo(depth),
              child: Text(_trail[depth].name),
            ),
            const Icon(Icons.chevron_right, size: 16),
          ],
          Chip(label: Text(_level.plural)),
          if (_level.child != null && _rows.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: Text(
                'Double-click a row to open its ${_level.child!.plural.toLowerCase()}.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
        ],
      ),
    );

    final Widget content = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: _load)
        : _loading && _rows.isEmpty
            ? const TableLoadingSkeleton()
            : _visible.isEmpty
                ? StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No ${_level.plural.toLowerCase()} here yet',
                    message: _canWrite
                        ? 'Add one with New.'
                        : 'Geography is shared reference data. A platform '
                            'administrator maintains it.',
                  )
                : LoadingOverlay(
                    loading: _loading,
                    child: EnterpriseDataGrid<GeoPlaceRecord>(
                      items: _visible,
                      total: _visible.length,
                      pageOffset: 0,
                      rowsPerPage: _visible.length,
                      columns: [
                        if (_level.hasCode)
                          const GridColumn(key: 'code', label: 'Code'),
                        GridColumn(key: 'name', label: _level.label),
                        if (_level.hasIsoFields)
                          const GridColumn(key: 'iso', label: 'ISO'),
                        if (_level.hasIsoFields)
                          const GridColumn(key: 'phone', label: 'Phone code'),
                        const GridColumn(key: 'status', label: 'Status'),
                      ],
                      id: (row) => row.id,
                      cells: (row) => [
                        if (_level.hasCode) row.code,
                        row.name,
                        if (_level.hasIsoFields) '${row.iso2} / ${row.iso3}',
                        if (_level.hasIsoFields) row.phoneCode,
                        row.isActive ? 'Active' : 'Inactive',
                      ],
                      selectedId: _selected?.id,
                      onSelect: (row) => setState(() => _selected = row),
                      onOpen: _drillInto,
                      // One request returns every row at this level under this
                      // parent, so the grid holds the whole page.
                      onPageChanged: (_) {},
                    ),
                  );

    return ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: searchPanel,
      filterPanel: breadcrumb,
      primaryContent: content,
      statusBar: WorkspaceStatusBar(
        total: _visible.length,
        selected: _selected != null,
        message: _loading
            ? 'Refreshing ${_level.plural.toLowerCase()}...'
            : _canWrite
                ? 'Ready'
                : 'Read-only — geography is maintained by a platform '
                    'administrator.',
      ),
    );
  }
}

/// Create or rename one place.
class _GeoEditorDialog extends StatefulWidget {
  const _GeoEditorDialog({required this.level, this.current});

  final GeoLevel level;
  final GeoPlaceRecord? current;

  @override
  State<_GeoEditorDialog> createState() => _GeoEditorDialogState();
}

class _GeoEditorDialogState extends State<_GeoEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  late final TextEditingController _code =
      TextEditingController(text: widget.current?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.current?.name ?? '');
  late final TextEditingController _iso2 =
      TextEditingController(text: widget.current?.iso2 ?? '');
  late final TextEditingController _iso3 =
      TextEditingController(text: widget.current?.iso3 ?? '');
  late final TextEditingController _phone =
      TextEditingController(text: widget.current?.phoneCode ?? '');
  late bool _isActive = widget.current?.isActive ?? true;

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _iso2.dispose();
    _iso3.dispose();
    _phone.dispose();
    super.dispose();
  }

  String? _required(String? value) =>
      (value == null || value.trim().isEmpty) ? 'Required' : null;

  @override
  Widget build(BuildContext context) {
    final GeoLevel level = widget.level;
    return AlertDialog(
      title: Text(
        '${widget.current == null ? 'New' : 'Edit'} ${level.label.toLowerCase()}',
      ),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _form,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (level == GeoLevel.postalCode)
                  TextFormField(
                    controller: _code,
                    decoration:
                        const InputDecoration(labelText: 'Postal code'),
                    validator: _required,
                  )
                else ...[
                  if (level.hasCode)
                    TextFormField(
                      controller: _code,
                      decoration: const InputDecoration(
                        labelText: 'Code',
                        helperText: 'Stored in upper case.',
                      ),
                      validator: _required,
                    ),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _name,
                    decoration: const InputDecoration(labelText: 'Name'),
                    validator: _required,
                  ),
                ],
                if (level.hasIsoFields) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: _iso2,
                          maxLength: 2,
                          decoration: const InputDecoration(
                            labelText: 'ISO 2',
                            counterText: '',
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextFormField(
                          controller: _iso3,
                          maxLength: 3,
                          decoration: const InputDecoration(
                            labelText: 'ISO 3',
                            counterText: '',
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextFormField(
                          controller: _phone,
                          decoration:
                              const InputDecoration(labelText: 'Phone code'),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 8),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _isActive,
                  title: const Text('Active'),
                  subtitle: const Text(
                    'An inactive place stays on the records already using it.',
                  ),
                  onChanged: (value) => setState(() => _isActive = value),
                ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (!(_form.currentState?.validate() ?? false)) return;
            final String name = level == GeoLevel.postalCode
                ? _code.text.trim()
                : _name.text.trim();
            Navigator.pop(
              context,
              GeoPlaceRecord(
                level: level,
                id: widget.current?.id ?? '',
                code: _code.text.trim().toUpperCase(),
                name: name,
                parentId: widget.current?.parentId ?? '',
                isActive: _isActive,
                iso2: _iso2.text.trim().toUpperCase(),
                iso3: _iso3.text.trim().toUpperCase(),
                phoneCode: _phone.text.trim(),
              ),
            );
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
