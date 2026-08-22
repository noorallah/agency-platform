import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/sales_territory.dart';
import '../workspace/desktop_framework.dart';

/// When a route runs.
///
/// The backend has had complete CRUD for beat plans since the module was
/// written — list, create, read, update, delete — and no screen called any of
/// it. A route could say it ran weekly and never say *which* week, which day,
/// or between which dates.
///
/// Bespoke rather than a `ResourceDefinition`: `plan_type` decides whether the
/// weekday and week-of-month fields mean anything, and a generated flat form
/// would offer all of them all of the time.
class BeatPlanManagementPage extends StatefulWidget {
  const BeatPlanManagementPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<BeatPlanManagementPage> createState() => _BeatPlanManagementPageState();
}

class _BeatPlanManagementPageState extends State<BeatPlanManagementPage> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  List<BeatPlanRecord> _items = const [];
  List<SalesTerritory> _routes = const [];
  BeatPlanRecord? _selected;
  bool _loading = false;
  bool _includeDeleted = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  static const int _rowsPerPage = 25;

  bool get _canView => widget.permissions.hasPermission('TERRITORY_VIEW');
  bool get _canCreate => widget.permissions.hasPermission('TERRITORY_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('TERRITORY_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('TERRITORY_DELETE');

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  /// The routes a plan may target.
  ///
  /// Only nodes that actually carry a route profile: the server refuses a beat
  /// plan on anything else, because the customers a plan calls are the ones
  /// assigned to its territory and assignments live on routes.
  Future<void> _loadRoutes() async {
    final PagedResult<SalesTerritory> page =
        await widget.api.territories(page: 1, pageSize: 100);
    if (!mounted) return;
    setState(() {
      _routes = page.items
          .where((item) => item.routeProfile != null && !item.isDeleted)
          .toList();
    });
  }

  Future<void> _loadAll({int? requestedPage}) async {
    if (!_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      await _loadRoutes();
      final PagedResult<BeatPlanRecord> page = await widget.api.beatPlans(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
        includeDeleted: _includeDeleted,
      );
      if (!mounted) return;
      setState(() {
        _items = page.items;
        _total = page.total;
        final String? selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : _items.where((item) => item.id == selectedId).firstOrNull;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _routeLabel(String territoryId) {
    final SalesTerritory? route =
        _routes.where((item) => item.id == territoryId).firstOrNull;
    if (route == null) return '(route not listed)';
    return '${route.code} — ${route.name}';
  }

  Future<void> _openEditor({BeatPlanRecord? current}) async {
    if (current == null && !_canCreate) return;
    if (current != null && !_canEdit) return;
    if (_routes.isEmpty) {
      NotificationService.show(
        context,
        'No routes yet. Turn on "This is a route" for a territory under '
        'Geography before scheduling a beat plan.',
        kind: AppNotificationKind.warning,
      );
      return;
    }
    final Json? result = await showDialog<Json>(
      context: context,
      builder: (context) => _BeatPlanEditorDialog(
        plan: current,
        routes: _routes,
      ),
    );
    if (!mounted || result == null) return;
    try {
      if (current == null) {
        await widget.api.createBeatPlan(result);
      } else {
        await widget.api.updateBeatPlan(
          current.id,
          result,
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _loadAll();
      if (!mounted) return;
      NotificationService.show(
        context,
        current == null ? 'Beat plan created.' : 'Beat plan updated.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'beat plan', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _delete(BeatPlanRecord plan) async {
    if (!_canDelete) return;
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete beat plan',
      message: 'Delete ${plan.code} — ${plan.name}?',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deleteBeatPlan(plan.id);
      setState(() => _selected = null);
      await _loadAll();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Beat plans are not visible to you',
        message: 'TERRITORY_VIEW is required.',
      );
    }

    final Widget toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
      ],
      isEnabled: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _selected != null && _canEdit,
        ToolbarAction.delete => _selected != null && _canDelete,
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
            _loadAll();
          default:
            break;
        }
      },
    );

    final Widget searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search beat plans by code or name',
      onSearch: (_) => _loadAll(requestedPage: 1),
      onClear: () => _loadAll(requestedPage: 1),
      filters: [
        FilterChip(
          label: const Text('Include deleted'),
          selected: _includeDeleted,
          onSelected: (value) {
            setState(() => _includeDeleted = value);
            _loadAll(requestedPage: 1);
          },
        ),
      ],
    );

    final Widget content = _error != null
        ? WorkspaceErrorState(message: _error!, onRetry: _loadAll)
        : _loading && _items.isEmpty
            ? const TableLoadingSkeleton()
            : _items.isEmpty
                ? const StandardEmptyState(
                    type: EmptyStateType.noRecords,
                    title: 'No beat plans yet',
                    message: 'A beat plan says which days a route runs. '
                        'Create one to schedule a round.',
                  )
                : LoadingOverlay(
                    loading: _loading,
                    child: EnterpriseDataGrid<BeatPlanRecord>(
                      items: _items,
                      total: _total,
                      pageOffset: (_page - 1) * _rowsPerPage,
                      rowsPerPage: _rowsPerPage,
                      columns: const [
                        GridColumn(key: 'code', label: 'Code'),
                        GridColumn(key: 'name', label: 'Name'),
                        GridColumn(key: 'route', label: 'Route'),
                        GridColumn(key: 'type', label: 'Repeats'),
                        GridColumn(key: 'when', label: 'When'),
                        GridColumn(key: 'window', label: 'Runs between'),
                        GridColumn(key: 'status', label: 'Status'),
                      ],
                      id: (item) => item.id,
                      cells: (item) => [
                        item.code,
                        item.name,
                        _routeLabel(item.territoryId),
                        titleCaseCode(item.planType),
                        describeOccurrence(item),
                        _window(item),
                        item.isActive ? 'Active' : 'Inactive',
                      ],
                      selectedId: _selected?.id,
                      onSelect: (item) => setState(() => _selected = item),
                      onOpen: (item) => _openEditor(current: item),
                      onPageChanged: (offset) =>
                          _loadAll(requestedPage: offset ~/ _rowsPerPage + 1),
                    ),
                  );

    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreate ? () => _openEditor() : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _loadAll,
        delete:
            _selected != null && _canDelete ? () => _delete(_selected!) : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: searchPanel,
        primaryContent: content,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _selected != null,
          message: _loading ? 'Refreshing beat plans...' : 'Ready',
        ),
      ),
    );
  }

  static String _window(BeatPlanRecord plan) {
    if (plan.startsOn.isEmpty && plan.endsOn.isEmpty) return 'Always';
    final String from = plan.startsOn.isEmpty ? '...' : plan.startsOn;
    final String to = plan.endsOn.isEmpty ? '...' : plan.endsOn;
    return '$from  to  $to';
  }
}

const List<String> beatPlanTypes = <String>[
  'WEEKLY',
  'FORTNIGHTLY',
  'MONTHLY',
  'CUSTOM',
];

/// ISO weekday numbering, which is what the API validates against (1-7).
const List<String> weekdayNames = <String>[
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

String titleCaseCode(String code) => code
    .split('_')
    .map((word) =>
        word.isEmpty ? word : '${word[0]}${word.substring(1).toLowerCase()}')
    .join(' ');

/// The plan's recurrence in a sentence, for the grid.
String describeOccurrence(BeatPlanRecord plan) {
  final String day =
      plan.weekday != null && plan.weekday! >= 1 && plan.weekday! <= 7
          ? weekdayNames[plan.weekday! - 1]
          : '';
  return switch (plan.planType) {
    'WEEKLY' => day.isEmpty ? 'No day set' : 'Every $day',
    'FORTNIGHTLY' => day.isEmpty ? 'No day set' : 'Every other $day',
    'MONTHLY' => plan.weekOfMonth == null || day.isEmpty
        ? 'No day set'
        : '${_ordinal(plan.weekOfMonth!)} $day of the month',
    _ => 'Set by hand',
  };
}

String _ordinal(int value) => switch (value) {
      1 => '1st',
      2 => '2nd',
      3 => '3rd',
      _ => '${value}th',
    };

class _BeatPlanEditorDialog extends StatefulWidget {
  const _BeatPlanEditorDialog({required this.plan, required this.routes});

  final BeatPlanRecord? plan;
  final List<SalesTerritory> routes;

  @override
  State<_BeatPlanEditorDialog> createState() => _BeatPlanEditorDialogState();
}

class _BeatPlanEditorDialogState extends State<_BeatPlanEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  late final TextEditingController _code =
      TextEditingController(text: widget.plan?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.plan?.name ?? '');
  late final TextEditingController _notes =
      TextEditingController(text: widget.plan?.notes ?? '');

  late String? _territoryId = _initialRoute();
  late String _planType = beatPlanTypes.contains(widget.plan?.planType)
      ? widget.plan!.planType
      : 'WEEKLY';
  late int? _weekday = widget.plan?.weekday;
  late int? _weekOfMonth = widget.plan?.weekOfMonth;
  late DateTime? _startsOn = _parseDate(widget.plan?.startsOn);
  late DateTime? _endsOn = _parseDate(widget.plan?.endsOn);
  late bool _isActive = widget.plan?.isActive ?? true;

  /// Only pre-select a route still on the list; a dropdown holding a value with
  /// no matching item asserts.
  String? _initialRoute() {
    final String existing = widget.plan?.territoryId ?? '';
    return widget.routes.any((route) => route.id == existing) ? existing : null;
  }

  static DateTime? _parseDate(String? value) =>
      (value == null || value.isEmpty) ? null : DateTime.tryParse(value);

  static String? _formatDate(DateTime? value) => value == null
      ? null
      : '${value.year.toString().padLeft(4, '0')}-'
          '${value.month.toString().padLeft(2, '0')}-'
          '${value.day.toString().padLeft(2, '0')}';

  bool get _needsWeekday => _planType != 'CUSTOM';
  bool get _needsWeekOfMonth => _planType == 'MONTHLY';

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool isStart}) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: (isStart ? _startsOn : _endsOn) ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _startsOn = picked;
      } else {
        _endsOn = picked;
      }
    });
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(
          widget.plan == null ? 'New beat plan' : 'Edit beat plan',
        ),
        content: SizedBox(
          width: 580,
          height: 520,
          child: Form(
            key: _form,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextFormField(
                    controller: _code,
                    decoration: const InputDecoration(labelText: 'Code'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'Code is required'
                            : null,
                  ),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _name,
                    decoration: const InputDecoration(labelText: 'Name'),
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                            ? 'Name is required'
                            : null,
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: _territoryId,
                    decoration: const InputDecoration(
                      labelText: 'Route',
                      helperText: 'Only territories marked as a route.',
                    ),
                    items: [
                      for (final SalesTerritory route in widget.routes)
                        DropdownMenuItem<String>(
                          value: route.id,
                          child: Text('${route.code} — ${route.name}'),
                        ),
                    ],
                    onChanged: (value) => setState(() => _territoryId = value),
                    validator: (value) => (value == null || value.isEmpty)
                        ? 'Choose the route this plan schedules'
                        : null,
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: _planType,
                    decoration: const InputDecoration(labelText: 'Repeats'),
                    items: [
                      for (final String type in beatPlanTypes)
                        DropdownMenuItem<String>(
                          value: type,
                          child: Text(titleCaseCode(type)),
                        ),
                    ],
                    onChanged: (value) =>
                        setState(() => _planType = value ?? 'WEEKLY'),
                  ),
                  if (_needsWeekday) ...[
                    const SizedBox(height: 8),
                    DropdownButtonFormField<int>(
                      isExpanded: true,
                      initialValue: _weekday,
                      decoration: const InputDecoration(labelText: 'On'),
                      items: [
                        for (int day = 1; day <= 7; day++)
                          DropdownMenuItem<int>(
                            value: day,
                            child: Text(weekdayNames[day - 1]),
                          ),
                      ],
                      onChanged: (value) => setState(() => _weekday = value),
                      validator: (value) =>
                          value == null ? 'A repeating plan needs a day' : null,
                    ),
                  ],
                  if (_needsWeekOfMonth) ...[
                    const SizedBox(height: 8),
                    DropdownButtonFormField<int>(
                      isExpanded: true,
                      initialValue: _weekOfMonth,
                      decoration:
                          const InputDecoration(labelText: 'Week of the month'),
                      items: [
                        for (int week = 1; week <= 5; week++)
                          DropdownMenuItem<int>(
                            value: week,
                            child: Text(_ordinal(week)),
                          ),
                      ],
                      onChanged: (value) =>
                          setState(() => _weekOfMonth = value),
                      validator: (value) =>
                          value == null ? 'A monthly plan needs a week' : null,
                    ),
                  ],
                  if (_planType == 'FORTNIGHTLY') ...[
                    const SizedBox(height: 4),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        'A fortnightly plan counts from its start date, so set '
                        'one below or it can never come round.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _DateField(
                          label: 'Runs from',
                          value: _formatDate(_startsOn),
                          onPick: () => _pickDate(isStart: true),
                          onClear: () => setState(() => _startsOn = null),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _DateField(
                          label: 'Runs until',
                          value: _formatDate(_endsOn),
                          onPick: () => _pickDate(isStart: false),
                          onClear: () => setState(() => _endsOn = null),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _isActive,
                    title: const Text('Active'),
                    onChanged: (value) => setState(() => _isActive = value),
                  ),
                  TextFormField(
                    controller: _notes,
                    maxLines: 3,
                    decoration: const InputDecoration(labelText: 'Notes'),
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
              if (_startsOn != null &&
                  _endsOn != null &&
                  _startsOn!.isAfter(_endsOn!)) {
                NotificationService.show(
                  context,
                  'The start date must not be after the end date.',
                  kind: AppNotificationKind.error,
                );
                return;
              }
              Navigator.pop<Json>(context, <String, dynamic>{
                'code': _code.text.trim().toUpperCase(),
                'name': _name.text.trim(),
                'territory_id': _territoryId,
                'plan_type': _planType,
                // Cleared rather than carried: a plan switched to Custom has no
                // weekday, and sending a stale one would have the server store
                // a day the form is no longer showing.
                'weekday': _needsWeekday ? _weekday : null,
                'week_of_month': _needsWeekOfMonth ? _weekOfMonth : null,
                'starts_on': _formatDate(_startsOn),
                'ends_on': _formatDate(_endsOn),
                'is_active': _isActive,
                'notes': _notes.text.trim().isEmpty ? null : _notes.text.trim(),
              });
            },
            child: const Text('Save'),
          ),
        ],
      );
}

class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.value,
    required this.onPick,
    required this.onClear,
  });

  final String label;
  final String? value;
  final VoidCallback onPick;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) => InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          suffixIcon: value == null
              ? IconButton(
                  icon: const Icon(Icons.calendar_today, size: 18),
                  onPressed: onPick,
                  tooltip: 'Pick a date',
                )
              : IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: onClear,
                  tooltip: 'Clear',
                ),
        ),
        child: InkWell(
          onTap: onPick,
          child: Text(value ?? 'Not set'),
        ),
      );
}
