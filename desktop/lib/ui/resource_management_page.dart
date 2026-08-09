import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/api/api_client.dart';
import '../core/dialogs/app_dialogs.dart';
import '../core/notifications/notification_service.dart';
import '../models/entities.dart';
import 'workspace/enterprise_form_kit.dart';
import 'workspace/desktop_framework.dart';

/// Field "kind" for composite/specialized enterprise widgets that go beyond
/// a plain text/boolean/options control. Plain fields (the historical
/// default) keep using [FieldSpec.boolean]/[FieldSpec.optionsResource].
enum FieldKind { text, date, addressList, documentList }

class FieldSpec {
  const FieldSpec({
    required this.key,
    required this.label,
    this.required = false,
    this.requiredOnCreate = false,
    this.multiline = false,
    this.boolean = false,
    this.optionsResource,
    this.singleSelection = false,
    this.readOnlyWhenEditing = false,
    this.createOnly = false,
    this.editOnly = false,
    this.helperText,
    this.section = 'General',
    this.sectionIcon,
    this.kind = FieldKind.text,
    this.alwaysReadOnly = false,
  });
  final String key, label;
  final bool required, requiredOnCreate, multiline, boolean;
  final String? optionsResource;
  final bool singleSelection, readOnlyWhenEditing, createOnly, editOnly;
  final String? helperText;
  final String section;

  /// Optional icon shown next to [section] in the enterprise form.
  final IconData? sectionIcon;

  /// Selects a specialized enterprise widget for this field instead of a
  /// plain text box (e.g. a date picker or a composite address/document
  /// list editor).
  final FieldKind kind;

  /// Marks a field as always read-only (e.g. audit trail data), regardless
  /// of the dialog's create/edit/view mode.
  final bool alwaysReadOnly;
}

enum CrudDialogMode { create, view, edit }

class CrudCreateCheckpoint {
  String? _persistedId;

  String? get persistedId => _persistedId;

  Future<String> persist(Future<String> Function() create) async {
    final String? existing = _persistedId;
    if (existing != null) return existing;
    final String createdId = await create();
    _persistedId = createdId;
    return createdId;
  }
}

class ResourceDefinition<T> {
  const ResourceDefinition({
    required this.title,
    required this.resource,
    required this.headers,
    required this.cells,
    required this.id,
    required this.load,
    required this.fields,
    required this.initialValues,
    required this.payload,
    this.partialUpdate = false,
    this.loadAssignments,
    this.saveAssignments,
    this.canEdit,
    this.canCreate = true,
    this.canDelete = true,
    this.updateEntity = true,
    this.description,
    this.breadcrumbs = const [],
    this.showFrame = true,
    this.details,
    this.canUseAction,
    this.sortFields = const [],
    this.export,
  });

  final String title, resource;
  final List<String> headers;
  final List<String> Function(T) cells;
  final String Function(T) id;
  final Future<PagedResult<T>> Function({
    int page,
    String search,
    String sortBy,
    bool descending,
  }) load;
  final List<FieldSpec> fields;
  final Map<String, dynamic> Function(T? item) initialValues;
  final Json Function(Map<String, dynamic> values, bool isCreating) payload;
  final bool partialUpdate;
  final Future<Map<String, dynamic>> Function(String id)? loadAssignments;
  final Future<void> Function(String id, Map<String, dynamic> values)?
      saveAssignments;
  final bool Function(T item)? canEdit;
  final bool canCreate, canDelete, updateEntity, showFrame;
  final String? description;
  final List<String> breadcrumbs;
  final List<DetailLine> Function(T item)? details;
  final bool Function(ToolbarAction action, T? selected)? canUseAction;
  final List<String?> sortFields;
  final Future<void> Function(List<T> items)? export;
}

class ResourceManagementPage<T> extends StatefulWidget {
  const ResourceManagementPage({
    super.key,
    required this.api,
    required this.definition,
  });
  final ApiClient api;
  final ResourceDefinition<T> definition;

  @override
  State<ResourceManagementPage<T>> createState() =>
      _ResourceManagementPageState<T>();
}

class _ResourceManagementPageState<T> extends State<ResourceManagementPage<T>> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  List<T> _items = const [];
  int _total = 0;
  int _page = 1;
  String _sortBy = 'created_at';
  bool _descending = true;
  bool _loading = true;
  String? _error;
  T? _selected;

  @override
  void initState() {
    super.initState();
    _searchFocus.addListener(_searchFocusChanged);
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.removeListener(_searchFocusChanged);
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _load({int? page}) async {
    setState(() {
      _loading = true;
      _error = null;
      _page = page ?? _page;
    });
    try {
      final PagedResult<T> result = await widget.definition.load(
        page: _page,
        search: _search.text.trim(),
        sortBy: _sortBy,
        descending: _descending,
      );
      if (!mounted) return;
      setState(() {
        _items = result.items;
        _total = result.total;
        final T? previouslySelected = _selected;
        if (previouslySelected != null &&
            !result.items
                .map(widget.definition.id)
                .contains(widget.definition.id(previouslySelected))) {
          _selected = null;
        }
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.isForbidden
            ? 'You are not authorized to view ${widget.definition.title.toLowerCase()}.'
            : exception.message;
        _items = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openDialog(CrudDialogMode mode, [T? item]) async {
    final ToolbarAction action = switch (mode) {
      CrudDialogMode.create => ToolbarAction.newItem,
      CrudDialogMode.view => ToolbarAction.view,
      CrudDialogMode.edit => ToolbarAction.edit,
    };
    if (!_hasCapability(action, item) ||
        (mode == CrudDialogMode.create && !widget.definition.canCreate) ||
        (mode == CrudDialogMode.edit &&
            item != null &&
            !(widget.definition.canEdit?.call(item) ?? true))) {
      return;
    }
    final Map<String, dynamic> initialValues =
        widget.definition.initialValues(item);
    if (item != null && widget.definition.loadAssignments != null) {
      try {
        initialValues.addAll(
          await widget.definition.loadAssignments!(widget.definition.id(item)),
        );
      } on ApiException catch (exception) {
        if (mounted) _showError(exception);
        return;
      }
    }
    if (!mounted) return;
    final CrudCreateCheckpoint createCheckpoint = CrudCreateCheckpoint();
    final Map<String, dynamic>? values = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CrudWorkspaceDialog(
        title: widget.definition.title,
        fields: widget.definition.fields,
        values: initialValues,
        api: widget.api,
        mode: mode,
        onSave: mode == CrudDialogMode.view
            ? null
            : (values) => _saveEntity(item, values, createCheckpoint),
      ),
    );
    if (values == null) return;
    if (!mounted) return;
    NotificationService.show(
      context,
      '${widget.definition.title} saved.',
      kind: AppNotificationKind.success,
    );
    await _load();
  }

  Future<void> _saveEntity(
    T? item,
    Map<String, dynamic> values,
    CrudCreateCheckpoint createCheckpoint,
  ) async {
    late final String savedId;
    if (item == null) {
      savedId = await createCheckpoint.persist(() async {
        final Json response = await widget.api.create(
          widget.definition.resource,
          widget.definition.payload(values, true),
        );
        final dynamic data = response['data'] ?? response;
        final String createdId =
            data is Map<String, dynamic> ? stringValue(data['id']) : '';
        if (createdId.isEmpty) {
          throw const ApiException(
            'The API did not return an identifier for the saved item.',
          );
        }
        return createdId;
      });
    } else {
      savedId = widget.definition.id(item);
      if (widget.definition.updateEntity) {
        await widget.api.update(
          widget.definition.resource,
          savedId,
          widget.definition.payload(values, false),
          partial: widget.definition.partialUpdate,
        );
      }
    }
    if (widget.definition.saveAssignments != null) {
      await widget.definition.saveAssignments!(savedId, values);
    }
  }

  Future<void> _delete(T item) async {
    if (!_hasCapability(ToolbarAction.delete, item) ||
        !widget.definition.canDelete ||
        !(widget.definition.canEdit?.call(item) ?? true)) {
      return;
    }
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${widget.definition.title}?',
      message: 'This action cannot be undone.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!accepted) return;
    try {
      await widget.api
          .delete(widget.definition.resource, widget.definition.id(item));
      if (!mounted) return;
      await _load();
    } on ApiException catch (exception) {
      if (mounted) _showError(exception);
    }
  }

  void _showError(ApiException exception) => NotificationService.show(
        context,
        exception.isForbidden
            ? 'You are not authorized to perform this action.'
            : exception.message,
        kind: AppNotificationKind.error,
      );

  bool _hasCapability(ToolbarAction action, T? selected) =>
      widget.definition.canUseAction?.call(action, selected) ?? true;

  void _searchFocusChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _copy(T item) async {
    final String row = widget.definition.cells(item).join('\t');
    await copyTextToClipboard(row);
    if (!mounted) return;
    NotificationService.show(
      context,
      '${widget.definition.title} row copied.',
      kind: AppNotificationKind.information,
    );
  }

  Future<void> _export() async {
    final Future<void> Function(List<T>)? export = widget.definition.export;
    if (export == null || _loading) return;
    try {
      await export(List.unmodifiable(_items));
      if (!mounted) return;
      NotificationService.show(
        context,
        '${widget.definition.title} exported.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (mounted) _showError(exception);
    }
  }

  void _contextAction(WorkspaceContextAction action, T item) {
    switch (action) {
      case WorkspaceContextAction.view:
        _openDialog(CrudDialogMode.view, item);
        break;
      case WorkspaceContextAction.edit:
        _openDialog(CrudDialogMode.edit, item);
        break;
      case WorkspaceContextAction.delete:
        _delete(item);
        break;
      case WorkspaceContextAction.restore:
        break;
      case WorkspaceContextAction.copy:
        _copy(item);
        break;
      case WorkspaceContextAction.refresh:
        _load();
        break;
      case WorkspaceContextAction.export:
        _export();
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final Set<int> statusColumnIndexes = widget.definition.headers
        .asMap()
        .entries
        .where(
          (entry) => entry.value.toLowerCase().replaceAll(' ', '').contains(
                'status',
              ),
        )
        .map((entry) => entry.key)
        .toSet();
    final T? selected = _selected;
    final bool canEditSelected =
        selected != null && (widget.definition.canEdit?.call(selected) ?? true);
    final Widget search = SearchFilterPanel(
      controller: _search,
      hintText: 'Search ${widget.definition.title.toLowerCase()}',
      onSearch: (_) => _load(page: 1),
      focusNode: _searchFocus,
    );
    final Widget toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.view,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
        ToolbarAction.import,
        ToolbarAction.export,
        ToolbarAction.print,
        ToolbarAction.settings,
      ],
      isVisible: (action) =>
          _hasCapability(action, null) &&
          switch (action) {
            ToolbarAction.newItem => widget.definition.canCreate,
            ToolbarAction.view ||
            ToolbarAction.edit ||
            ToolbarAction.delete ||
            ToolbarAction.refresh =>
              true,
            ToolbarAction.export => widget.definition.export != null,
            _ => false,
          },
      isEnabled: (action) =>
          !_loading &&
          _hasCapability(action, selected) &&
          switch (action) {
            ToolbarAction.newItem => widget.definition.canCreate,
            ToolbarAction.view => selected != null,
            ToolbarAction.edit => canEditSelected,
            ToolbarAction.delete =>
              canEditSelected && widget.definition.canDelete,
            ToolbarAction.refresh => true,
            ToolbarAction.export => widget.definition.export != null,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _openDialog(CrudDialogMode.create);
            break;
          case ToolbarAction.edit:
            if (selected != null) {
              _openDialog(CrudDialogMode.edit, selected);
            }
            break;
          case ToolbarAction.delete:
            if (selected != null) _delete(selected);
            break;
          case ToolbarAction.view:
            if (selected != null) {
              _openDialog(CrudDialogMode.view, selected);
            }
            break;
          case ToolbarAction.refresh:
            _load();
            break;
          case ToolbarAction.export:
            _export();
            break;
          case ToolbarAction.import:
          case ToolbarAction.print:
          case ToolbarAction.settings:
            break;
        }
      },
    );
    final List<DetailLine> lines = selected == null
        ? const []
        : (widget.definition.details?.call(selected) ??
                List.generate(
                  widget.definition.headers.length,
                  (index) => DetailLine(
                    widget.definition.headers[index],
                    widget.definition.cells(selected)[index],
                  ),
                ))
            .take(6)
            .toList();
    final Widget primaryContent;
    if (_error != null) {
      primaryContent =
          WorkspaceErrorState(message: _error!, onRetry: () => _load());
    } else if (_loading && _items.isEmpty) {
      primaryContent = const WorkspaceLoadingState();
    } else if (_items.isEmpty) {
      primaryContent = WorkspaceEmptyState(
        title: 'No ${widget.definition.title.toLowerCase()} found',
        message: 'Try a different search or create a new record.',
      );
    } else {
      primaryContent = EnterpriseDataGrid<T>(
        items: _items,
        total: _total,
        pageOffset: (_page - 1) * _rowsPerPage,
        columns: widget.definition.headers
            .asMap()
            .entries
            .map(
              (entry) => GridColumn(
                key: widget.definition.sortFields.length > entry.key &&
                        widget.definition.sortFields[entry.key] != null
                    ? widget.definition.sortFields[entry.key]!
                    : entry.value.toLowerCase().replaceAll(' ', '_'),
                label: entry.value,
                onSort: entry.key < widget.definition.sortFields.length &&
                        widget.definition.sortFields[entry.key] != null
                    ? (ascending) {
                        setState(() {
                          _sortBy = widget.definition.sortFields[entry.key]!;
                          _descending = !ascending;
                        });
                        _load(page: 1);
                      }
                    : null,
              ),
            )
            .toList(),
        id: widget.definition.id,
        cells: widget.definition.cells,
        cellBuilder: (columnIndex, value, _) {
          if (statusColumnIndexes.contains(columnIndex) &&
              value.trim().isNotEmpty) {
            return Align(
              alignment: Alignment.centerLeft,
              child: StatusBadge.fromStatus(value),
            );
          }
          return Tooltip(
            message: value,
            child: SizedBox(
              width: double.infinity,
              child: Text(value, overflow: TextOverflow.ellipsis),
            ),
          );
        },
        selectedId: selected == null ? null : widget.definition.id(selected),
        onSelect: (item) => setState(() => _selected = item),
        onOpen: (item) => _openDialog(CrudDialogMode.view, item),
        contextActions: [
          if (_hasCapability(ToolbarAction.view, selected))
            WorkspaceContextAction.view,
          if (_hasCapability(ToolbarAction.edit, selected))
            WorkspaceContextAction.edit,
          if (widget.definition.canDelete &&
              _hasCapability(ToolbarAction.delete, selected))
            WorkspaceContextAction.delete,
          WorkspaceContextAction.copy,
          WorkspaceContextAction.refresh,
          if (widget.definition.export != null) WorkspaceContextAction.export,
        ],
        onContextAction: _contextAction,
        onPageChanged: (rowIndex) => _load(page: rowIndex ~/ _rowsPerPage + 1),
      );
    }
    final Widget layout = ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: search,
      primaryContent: primaryContent,
      detailsPanel: selected == null
          ? null
          : QuickSummaryPanel(
              title: 'Selected ${widget.definition.title}',
              lines: lines,
              onView: _hasCapability(ToolbarAction.view, selected)
                  ? () => _openDialog(CrudDialogMode.view, selected)
                  : null,
              onEdit: canEditSelected &&
                      _hasCapability(ToolbarAction.edit, selected)
                  ? () => _openDialog(CrudDialogMode.edit, selected)
                  : null,
            ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: selected != null,
        message: _loading ? 'Refreshing...' : null,
      ),
    );
    final Widget shortcutLayout = WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: widget.definition.canCreate &&
                _hasCapability(ToolbarAction.newItem, null)
            ? () => _openDialog(CrudDialogMode.create)
            : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _load,
        copy: selected == null || _searchFocus.hasFocus
            ? null
            : () => _copy(selected),
        cancel:
            selected == null ? null : () => setState(() => _selected = null),
        delete: canEditSelected &&
                widget.definition.canDelete &&
                _hasCapability(ToolbarAction.delete, selected)
            ? () => _delete(selected)
            : null,
      ),
      child: layout,
    );
    return widget.definition.showFrame
        ? ModuleWorkspaceFrame(
            title: widget.definition.title,
            description: widget.definition.description ??
                'Create, review, and manage ${widget.definition.title.toLowerCase()}.',
            breadcrumbs: widget.definition.breadcrumbs,
            child: shortcutLayout,
          )
        : shortcutLayout;
  }
}

class CrudWorkspaceDialog extends StatefulWidget {
  const CrudWorkspaceDialog({
    required this.title,
    required this.fields,
    required this.values,
    required this.api,
    required this.mode,
    required this.onSave,
    super.key,
  });
  final String title;
  final List<FieldSpec> fields;
  final Map<String, dynamic> values;
  final ApiClient api;
  final CrudDialogMode mode;
  final Future<void> Function(Map<String, dynamic> values)? onSave;

  bool get isCreating => mode == CrudDialogMode.create;
  bool get isReadOnly => mode == CrudDialogMode.view;

  @override
  State<CrudWorkspaceDialog> createState() => _CrudWorkspaceDialogState();
}

class _CrudWorkspaceDialogState extends State<CrudWorkspaceDialog> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _controllers = {
    for (final FieldSpec field in widget.fields.where((field) =>
        !field.boolean &&
        field.optionsResource == null &&
        field.kind != FieldKind.addressList &&
        field.kind != FieldKind.documentList))
      field.key: TextEditingController(
          text: widget.values[field.key]?.toString() ?? ''),
  };
  late final Map<String, bool> _booleans = {
    for (final FieldSpec field in widget.fields.where((field) => field.boolean))
      field.key: widget.values[field.key] as bool? ?? false,
  };
  final Map<String, List<AssignmentOption>> _options = {};
  late final Map<String, Set<String>> _selections = {
    for (final FieldSpec field
        in widget.fields.where((field) => field.optionsResource != null))
      field.key: (widget.values[field.key]?.toString() ?? '')
          .split(',')
          .map((id) => id.trim())
          .where((id) => id.isNotEmpty)
          .toSet(),
  };
  late final Map<String, List<AddressRecord>> _addressLists = {
    for (final FieldSpec field
        in widget.fields.where((field) => field.kind == FieldKind.addressList))
      field.key:
          _decodeRecords(widget.values[field.key], AddressRecord.fromJson),
  };
  late final Map<String, List<DocumentRecord>> _documentLists = {
    for (final FieldSpec field
        in widget.fields.where((field) => field.kind == FieldKind.documentList))
      field.key:
          _decodeRecords(widget.values[field.key], DocumentRecord.fromJson),
  };
  bool _loadingOptions = true;
  String? _optionsError;
  bool _saving = false;
  bool _dirty = false;
  String? _submitError;
  Map<String, String> _fieldErrors = const {};

  static List<R> _decodeRecords<R>(
    Object? raw,
    R Function(Map<String, dynamic>) fromJson,
  ) {
    if (raw is! List) return [];
    return [
      for (final Object? item in raw)
        if (item is Map) fromJson(Map<String, dynamic>.from(item)),
    ];
  }

  void _markDirty() {
    if (!_dirty) setState(() => _dirty = true);
  }

  List<String> get _sections => widget.fields
      .where(_isVisible)
      .map((field) => field.section)
      .toSet()
      .toList();

  @override
  void initState() {
    super.initState();
    for (final TextEditingController controller in _controllers.values) {
      controller.addListener(_markDirty);
    }
    _loadOptions();
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadOptions() async {
    final List<FieldSpec> fields =
        widget.fields.where((field) => field.optionsResource != null).toList();
    if (fields.isEmpty) {
      setState(() => _loadingOptions = false);
      return;
    }
    try {
      final List<List<AssignmentOption>> results = await Future.wait(
        fields.map((field) => widget.api.options(field.optionsResource!)),
      );
      if (!mounted) return;
      setState(() {
        for (int index = 0; index < fields.length; index++) {
          _options[fields[index].key] = results[index];
        }
        _loadingOptions = false;
      });
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          _optionsError = exception.message;
          _loadingOptions = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final Size window = MediaQuery.sizeOf(context);
    final List<String> sections = _sections;
    return Dialog(
      insetPadding: const EdgeInsets.all(24),
      constraints: const BoxConstraints(),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        key: const ValueKey('crud-workspace-dialog-surface'),
        width: window.width * .88,
        height: window.height * .88,
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.escape): _close,
            const SingleActivator(
              LogicalKeyboardKey.keyS,
              control: true,
            ): _save,
          },
          child: Focus(
            autofocus: true,
            child: Column(children: [
              CrudWorkspaceHeader(
                title: widget.title,
                mode: widget.mode,
                onClose: _saving ? null : _close,
              ),
              Expanded(
                child: AbsorbPointer(
                  absorbing: _saving,
                  child: Form(
                    key: _formKey,
                    child: CrudFormPage(
                      children: [
                        EnterpriseValidationSummary(
                          message: _submitError,
                          fieldErrors: _fieldErrors,
                        ),
                        for (final String section in sections)
                          EnterpriseSection(
                            title: section,
                            icon: widget.fields
                                .firstWhere(
                                  (field) =>
                                      field.section == section &&
                                      field.sectionIcon != null,
                                  orElse: () => widget.fields.firstWhere(
                                      (field) => field.section == section),
                                )
                                .sectionIcon,
                            errorCount: widget.fields
                                .where((field) =>
                                    _isVisible(field) &&
                                    field.section == section &&
                                    _fieldErrors[field.key] != null)
                                .length,
                            readOnly: widget.fields
                                .where((field) => field.section == section)
                                .every((field) => field.alwaysReadOnly),
                            children: widget.fields
                                .where((field) =>
                                    _isVisible(field) &&
                                    field.section == section)
                                .map(_field)
                                .toList(),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              EnterpriseActionBar(
                saving: _saving,
                readOnly: widget.isReadOnly,
                onCancel: _saving ? null : _close,
                onSaveAndClose: widget.isReadOnly || _saving ? null : _save,
                onSaveAndNew:
                    widget.isCreating && !widget.isReadOnly && !_saving
                        ? () => _save(andNew: true)
                        : null,
              ),
            ]),
          ),
        ),
      ),
    );
  }

  bool _isVisible(FieldSpec field) =>
      !((field.createOnly && !widget.isCreating) ||
          (field.editOnly && widget.isCreating));

  /// Groups options by inferring a category from the code prefix before the
  /// first underscore (e.g. "USER_CREATE" -> "User"). Falls back to a single
  /// "General" group when there is nothing to usefully group by.
  Map<String, List<AssignmentOption>> _groupOptions(
      List<AssignmentOption> options) {
    if (options.length <= 8) {
      return {'': options};
    }
    final Map<String, List<AssignmentOption>> grouped = {};
    for (final option in options) {
      final int underscoreIndex = option.label.indexOf('_');
      final String rawKey = underscoreIndex > 0
          ? option.label.substring(0, underscoreIndex)
          : 'General';
      final String key = rawKey
          .split('_')
          .map((w) => w.isEmpty
              ? w
              : '${w[0].toUpperCase()}${w.substring(1).toLowerCase()}')
          .join(' ');
      grouped.putIfAbsent(key, () => []).add(option);
    }
    return grouped;
  }

  Widget _permissionChip(FieldSpec field, AssignmentOption option) {
    final bool selected = _selections[field.key]!.contains(option.id);
    return FilterChip(
      label: Text(option.label),
      labelStyle: Theme.of(context).textTheme.bodySmall,
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      labelPadding: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 0),
      selected: selected,
      onSelected: widget.isReadOnly
          ? null
          : (bool value) {
              _markDirty();
              setState(() {
                if (value) {
                  if (field.singleSelection) {
                    _selections[field.key]!.clear();
                  }
                  _selections[field.key]!.add(option.id);
                } else {
                  _selections[field.key]!.remove(option.id);
                }
              });
            },
    );
  }

  Widget _field(FieldSpec field) {
    if (field.alwaysReadOnly) {
      final String value = widget.values[field.key]?.toString() ?? '';
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(field.label,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 2),
            Text(value.trim().isNotEmpty ? value : '—'),
          ],
        ),
      );
    }
    if (field.kind == FieldKind.addressList) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: EnterpriseAddressEditor(
          addresses: _addressLists[field.key] ?? const [],
          readOnly: widget.isReadOnly,
          onChanged: (addresses) {
            _markDirty();
            setState(() => _addressLists[field.key] = addresses);
          },
        ),
      );
    }
    if (field.kind == FieldKind.documentList) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: EnterpriseDocumentSection(
          documents: _documentLists[field.key] ?? const [],
          readOnly: widget.isReadOnly,
          onChanged: (documents) {
            _markDirty();
            setState(() => _documentLists[field.key] = documents);
          },
        ),
      );
    }
    if (field.boolean) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(field.label),
              value: _booleans[field.key]!,
              onChanged: widget.isReadOnly
                  ? null
                  : (value) {
                      _markDirty();
                      setState(() => _booleans[field.key] = value);
                    },
            ),
            if (_fieldErrors[field.key] != null)
              Text(
                _fieldErrors[field.key]!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
          ],
        ),
      );
    }
    if (field.optionsResource != null) {
      final List<AssignmentOption> options = _options[field.key] ?? const [];
      final Map<String, List<AssignmentOption>> grouped =
          _groupOptions(options);
      final List<String> groupKeys = grouped.keys.toList()..sort();
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Align(
          alignment: Alignment.centerLeft,
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(field.label, style: Theme.of(context).textTheme.titleSmall),
            if (_loadingOptions)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: SizedBox(
                    width: 20, height: 20, child: CircularProgressIndicator()),
              )
            else if (_optionsError != null)
              Text(
                'Assignments could not be loaded: $_optionsError',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              )
            else
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final String groupKey in groupKeys) ...[
                      if (groupKeys.length > 1)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 4, top: 8),
                          child: Text(
                            groupKey,
                            style: Theme.of(context)
                                .textTheme
                                .labelSmall
                                ?.copyWith(
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurfaceVariant,
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.4,
                                ),
                          ),
                        ),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: grouped[groupKey]!
                            .map((option) => _permissionChip(field, option))
                            .toList(),
                      ),
                    ],
                  ],
                ),
              ),
            if (_fieldErrors[field.key] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _fieldErrors[field.key]!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ]),
        ),
      );
    }
    if (field.kind == FieldKind.date) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextFormField(
          controller: _controllers[field.key],
          readOnly: true,
          decoration: InputDecoration(
            labelText: field.label,
            helperText: field.helperText,
            suffixIcon: widget.isReadOnly
                ? null
                : IconButton(
                    icon: const Icon(Icons.calendar_today_outlined, size: 18),
                    onPressed: () async {
                      final DateTime now = DateTime.now();
                      final DateTime initial = DateTime.tryParse(
                            _controllers[field.key]!.text,
                          ) ??
                          now;
                      final DateTime? picked = await showDatePicker(
                        context: context,
                        initialDate: initial,
                        firstDate: DateTime(now.year - 80),
                        lastDate: DateTime(now.year + 20),
                      );
                      if (picked != null) {
                        _controllers[field.key]!.text =
                            picked.toIso8601String().split('T').first;
                      }
                    },
                  ),
          ),
          validator: (value) =>
              _fieldErrors[field.key] ??
              ((field.required ||
                          (field.requiredOnCreate && widget.isCreating)) &&
                      (value == null || value.trim().isEmpty)
                  ? '${field.label} is required.'
                  : null),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        controller: _controllers[field.key],
        readOnly: widget.isReadOnly ||
            (field.readOnlyWhenEditing && !widget.isCreating),
        maxLines: field.multiline ? 3 : 1,
        decoration: InputDecoration(
            labelText: field.label, helperText: field.helperText),
        validator: (value) =>
            _fieldErrors[field.key] ??
            ((field.required ||
                        (field.requiredOnCreate && widget.isCreating)) &&
                    (value == null || value.trim().isEmpty)
                ? '${field.label} is required.'
                : null),
      ),
    );
  }

  Future<void> _save({bool andNew = false}) async {
    if (widget.isReadOnly || _saving || widget.onSave == null) return;
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _submitError = null;
      _fieldErrors = const {};
    });
    final Map<String, dynamic> values = {
      for (final MapEntry<String, TextEditingController> entry
          in _controllers.entries)
        entry.key: entry.value.text.trim(),
      for (final MapEntry<String, Set<String>> entry in _selections.entries)
        entry.key: entry.value.join(','),
      for (final MapEntry<String, List<AddressRecord>> entry
          in _addressLists.entries)
        entry.key: entry.value.map((address) => address.toJson()).toList(),
      for (final MapEntry<String, List<DocumentRecord>> entry
          in _documentLists.entries)
        entry.key: entry.value.map((document) => document.toJson()).toList(),
      ..._booleans,
    };
    try {
      await widget.onSave!(values);
      if (!mounted) return;
      if (andNew) {
        setState(() {
          _saving = false;
          _dirty = false;
        });
        for (final TextEditingController controller in _controllers.values) {
          controller.text = '';
        }
        for (final String key in _booleans.keys) {
          _booleans[key] = false;
        }
        for (final Set<String> selection in _selections.values) {
          selection.clear();
        }
        for (final String key in _addressLists.keys) {
          _addressLists[key] = [];
        }
        for (final String key in _documentLists.keys) {
          _documentLists[key] = [];
        }
        NotificationService.show(
          context,
          '${widget.title} saved. Ready for a new entry.',
          kind: AppNotificationKind.success,
        );
      } else {
        Navigator.pop(context, values);
      }
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _submitError = exception.message;
        _fieldErrors = _validationErrors(exception.details);
        _saving = false;
      });
      _formKey.currentState!.validate();
    }
  }

  void _close() {
    if (_saving) return;
    unawaited(_confirmAndClose());
  }

  Future<void> _confirmAndClose() async {
    if (_dirty && !widget.isReadOnly) {
      final bool discard =
          await EnterpriseConfirmationDialog.confirmDiscard(context);
      if (!discard || !mounted) return;
    }
    if (mounted) Navigator.pop(context);
  }

  Map<String, String> _validationErrors(Object? details) {
    if (details is! List) return const {};
    final Map<String, String> errors = {};
    for (final Object? item in details) {
      if (item is! Map) continue;
      final String field = item['field']?.toString() ?? '';
      final String message = item['message']?.toString() ?? '';
      if (field.isEmpty || message.isEmpty) continue;
      final String key = field.split('.').last;
      errors[key] = message;
    }
    return errors;
  }
}

class CrudWorkspaceHeader extends StatelessWidget {
  const CrudWorkspaceHeader({
    super.key,
    required this.title,
    required this.mode,
    required this.onClose,
  });

  final String title;
  final CrudDialogMode mode;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Row(children: [
            Icon(
              switch (mode) {
                CrudDialogMode.create => Icons.add_circle_outline,
                CrudDialogMode.view => Icons.visibility_outlined,
                CrudDialogMode.edit => Icons.edit_outlined,
              },
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.headlineSmall),
                  Text(
                    switch (mode) {
                      CrudDialogMode.create => 'Create new record',
                      CrudDialogMode.view => 'View record details',
                      CrudDialogMode.edit => 'Edit existing record',
                    },
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Close',
              onPressed: onClose,
              icon: const Icon(Icons.close),
            ),
          ]),
        ),
      );
}

class CrudFormPage extends StatelessWidget {
  const CrudFormPage({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1100),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ),
      );
}
