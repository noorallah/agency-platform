import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/api/api_client.dart';
import '../core/notifications/notification_service.dart';
import '../models/entities.dart';
import 'workspace/workspace_components.dart';

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
  });
  final String key, label;
  final bool required, requiredOnCreate, multiline, boolean;
  final String? optionsResource;
  final bool singleSelection, readOnlyWhenEditing, createOnly, editOnly;
  final String? helperText;
  final String section;
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
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
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

  @override
  Widget build(BuildContext context) {
    final T? selected = _selected;
    final bool canEditSelected =
        selected != null && (widget.definition.canEdit?.call(selected) ?? true);
    final Widget search = SearchFilterPanel(
      controller: _search,
      hintText: 'Search ${widget.definition.title.toLowerCase()}',
      onSearch: (_) => _load(page: 1),
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
          case ToolbarAction.import:
          case ToolbarAction.export:
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
        selectedId: selected == null ? null : widget.definition.id(selected),
        onSelect: (item) => setState(() => _selected = item),
        onPageChanged: (rowIndex) => _load(page: rowIndex ~/ _rowsPerPage + 1),
      );
    }
    final Widget layout = ManagementWorkspaceLayout(
      toolbar: toolbar,
      searchPanel: search,
      primaryContent: primaryContent,
      detailsPanel: QuickSummaryPanel(
        title: selected == null
            ? 'No ${widget.definition.title.toLowerCase()} selected'
            : 'Selected ${widget.definition.title}',
        lines: lines,
        onView: selected != null && _hasCapability(ToolbarAction.view, selected)
            ? () => _openDialog(CrudDialogMode.view, selected)
            : null,
        onEdit: canEditSelected && _hasCapability(ToolbarAction.edit, selected)
            ? () => _openDialog(CrudDialogMode.edit, selected)
            : null,
      ),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: selected != null,
        message: _loading ? 'Refreshing...' : null,
      ),
    );
    return widget.definition.showFrame
        ? ModuleWorkspaceFrame(
            title: widget.definition.title,
            description: widget.definition.description ??
                'Create, review, and manage ${widget.definition.title.toLowerCase()}.',
            breadcrumbs: widget.definition.breadcrumbs,
            child: layout,
          )
        : layout;
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
    for (final FieldSpec field in widget.fields
        .where((field) => !field.boolean && field.optionsResource == null))
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
  bool _loadingOptions = true;
  String? _optionsError;
  bool _saving = false;
  String? _submitError;
  Map<String, String> _fieldErrors = const {};
  int _selectedSection = 0;

  List<String> get _sections => widget.fields
      .where(_isVisible)
      .map((field) => field.section)
      .toSet()
      .toList();

  @override
  void initState() {
    super.initState();
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
              if (sections.length > 1)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: SegmentedButton<int>(
                        segments: [
                          for (var index = 0; index < sections.length; index++)
                            ButtonSegment(
                              value: index,
                              label: Text(sections[index]),
                            ),
                        ],
                        selected: {_selectedSection},
                        showSelectedIcon: false,
                        onSelectionChanged: (selection) =>
                            setState(() => _selectedSection = selection.first),
                      ),
                    ),
                  ),
                ),
              Expanded(
                child: AbsorbPointer(
                  absorbing: _saving,
                  child: Form(
                    key: _formKey,
                    child: IndexedStack(
                      index: _selectedSection,
                      children: [
                        for (final String section in sections)
                          CrudFormPage(
                            children: [
                              if (_submitError != null) ...[
                                _FormErrorBanner(message: _submitError!),
                                const SizedBox(height: 16),
                              ],
                              ...widget.fields
                                  .where(
                                    (field) =>
                                        _isVisible(field) &&
                                        field.section == section,
                                  )
                                  .map(_field),
                            ],
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              CrudWorkspaceFooter(
                mode: widget.mode,
                saving: _saving,
                onCancel: _saving ? null : _close,
                onSave: widget.isReadOnly || _saving ? null : _save,
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

  Widget _field(FieldSpec field) {
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
                  : (value) => setState(() => _booleans[field.key] = value),
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
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Align(
          alignment: Alignment.centerLeft,
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(field.label, style: Theme.of(context).textTheme.titleSmall),
            if (field.helperText != null)
              Text(field.helperText!,
                  style: Theme.of(context).textTheme.bodySmall),
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
              Wrap(
                spacing: 8,
                children: options
                    .map((option) => FilterChip(
                          label: Text(option.label),
                          selected: _selections[field.key]!.contains(option.id),
                          onSelected: widget.isReadOnly
                              ? null
                              : (selected) => setState(() {
                                    if (selected) {
                                      if (field.singleSelection) {
                                        _selections[field.key]!.clear();
                                      }
                                      _selections[field.key]!.add(option.id);
                                    } else {
                                      _selections[field.key]!.remove(option.id);
                                    }
                                  }),
                        ))
                    .toList(),
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

  Future<void> _save() async {
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
      ..._booleans,
    };
    try {
      await widget.onSave!(values);
      if (mounted) Navigator.pop(context, values);
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
    if (!_saving) Navigator.pop(context);
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

class CrudWorkspaceFooter extends StatelessWidget {
  const CrudWorkspaceFooter({
    super.key,
    required this.mode,
    required this.saving,
    required this.onCancel,
    required this.onSave,
  });

  final CrudDialogMode mode;
  final bool saving;
  final VoidCallback? onCancel;
  final VoidCallback? onSave;

  @override
  Widget build(BuildContext context) => Material(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              OutlinedButton(
                onPressed: onCancel,
                child: Text(mode == CrudDialogMode.view ? 'Close' : 'Cancel'),
              ),
              if (mode != CrudDialogMode.view) ...[
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: onSave,
                  icon: saving
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: Text(saving ? 'Saving...' : 'Save'),
                ),
              ],
            ],
          ),
        ),
      );
}

class _FormErrorBanner extends StatelessWidget {
  const _FormErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          message,
          style:
              TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
        ),
      );
}
