import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../models/entities.dart';

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
  });
  final String key, label;
  final bool required, requiredOnCreate, multiline, boolean;
  final String? optionsResource;
  final bool singleSelection, readOnlyWhenEditing, createOnly, editOnly;
  final String? helperText;
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
  });

  final String title, resource;
  final List<String> headers;
  final List<String> Function(T) cells;
  final String Function(T) id;
  final Future<PagedResult<T>> Function({int page, String search}) load;
  final List<FieldSpec> fields;
  final Map<String, dynamic> Function(T? item) initialValues;
  final Json Function(Map<String, dynamic> values, bool isCreating) payload;
  final bool partialUpdate;
  final Future<Map<String, dynamic>> Function(String id)? loadAssignments;
  final Future<void> Function(String id, Map<String, dynamic> values)?
      saveAssignments;
  final bool Function(T item)? canEdit;
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
  bool _loading = true;
  String? _error;

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
      );
      if (!mounted) return;
      setState(() {
        _items = result.items;
        _total = result.total;
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

  Future<void> _edit([T? item]) async {
    final Map<String, dynamic> initialValues = widget.definition.initialValues(item);
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
    final Map<String, dynamic>? values = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => _EntityEditor(
        title: '${item == null ? 'Create' : 'Edit'} ${widget.definition.title}',
        fields: widget.definition.fields,
        values: initialValues,
        api: widget.api,
        isCreating: item == null,
      ),
    );
    if (values == null) return;
    try {
      late final String savedId;
      if (item == null) {
        final Json response = await widget.api.create(
          widget.definition.resource,
          widget.definition.payload(values, true),
        );
        final dynamic data = response['data'] ?? response;
        savedId = data is Map<String, dynamic> ? stringValue(data['id']) : '';
      } else {
        await widget.api.update(
          widget.definition.resource,
          widget.definition.id(item),
          widget.definition.payload(values, false),
          partial: widget.definition.partialUpdate,
        );
        savedId = widget.definition.id(item);
      }
      if (widget.definition.saveAssignments != null) {
        if (savedId.isEmpty) {
          throw const ApiException('The API did not return an identifier for the saved item.');
        }
        await widget.definition.saveAssignments!(savedId, values);
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${widget.definition.title} saved.')),
      );
      await _load();
    } on ApiException catch (exception) {
      if (mounted) _showError(exception);
    }
  }

  Future<void> _delete(T item) async {
    final bool? accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${widget.definition.title}?'),
        content: const Text('This action cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton.tonal(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (accepted != true) return;
    try {
      await widget.api.delete(widget.definition.resource, widget.definition.id(item));
      if (!mounted) return;
      await _load();
    } on ApiException catch (exception) {
      if (mounted) _showError(exception);
    }
  }

  void _showError(ApiException exception) => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(exception.isForbidden
              ? 'You are not authorized to perform this action.'
              : exception.message),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final _ResourceDataSource<T> source = _ResourceDataSource<T>(
      _items,
      widget.definition.cells,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      onEdit: _edit,
      onDelete: _delete,
      canEdit: widget.definition.canEdit,
    );
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(widget.definition.title, style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        Text('Create, update, and remove ${widget.definition.title.toLowerCase()}.'),
        const SizedBox(height: 20),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _search,
              onSubmitted: (_) => _load(page: 1),
              decoration: InputDecoration(
                hintText: 'Search ${widget.definition.title.toLowerCase()}',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                  tooltip: 'Refresh',
                  onPressed: _loading ? null : _load,
                  icon: const Icon(Icons.refresh),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          FilledButton.icon(
            onPressed: _loading ? null : () => _edit(),
            icon: const Icon(Icons.add),
            label: Text('New ${widget.definition.title}'),
          ),
        ]),
        const SizedBox(height: 16),
        if (_error != null)
          Expanded(child: _ErrorState(message: _error!, onRetry: _load))
        else if (_loading && _items.isEmpty)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else
          Expanded(
            child: Card(
              clipBehavior: Clip.antiAlias,
              child: LayoutBuilder(
                builder: (context, constraints) => SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SizedBox(
                    width: constraints.maxWidth < 720 ? 720 : constraints.maxWidth,
                    child: PaginatedDataTable(
                      header: Text(widget.definition.title),
                      rowsPerPage: _rowsPerPage,
                      initialFirstRowIndex: (_page - 1) * _rowsPerPage,
                      showFirstLastButtons: true,
                      availableRowsPerPage: const [_rowsPerPage],
                      onPageChanged: (rowIndex) =>
                          _load(page: rowIndex ~/ _rowsPerPage + 1),
                      columns: [
                        ...widget.definition.headers
                            .map((header) => DataColumn(label: Text(header))),
                        const DataColumn(label: Text('Actions')),
                      ],
                      source: source,
                    ),
                  ),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

class _ResourceDataSource<T> extends DataTableSource {
  _ResourceDataSource(
    this.items,
    this.cells, {
    required this.total,
    required this.pageOffset,
    required this.onEdit,
    required this.onDelete,
    this.canEdit,
  });
  final List<T> items;
  final List<String> Function(T) cells;
  final int total, pageOffset;
  final void Function(T) onEdit, onDelete;
  final bool Function(T)? canEdit;

  @override
  DataRow? getRow(int index) {
    final int localIndex = index - pageOffset;
    if (localIndex < 0 || localIndex >= items.length) return null;
    final T item = items[localIndex];
    final bool editable = canEdit?.call(item) ?? true;
    return DataRow.byIndex(
      index: index,
      cells: [
        ...cells(item).map((value) => DataCell(
              Tooltip(message: value, child: Text(value, overflow: TextOverflow.ellipsis)),
            )),
        DataCell(Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            tooltip: editable ? 'Edit' : 'This system item cannot be edited',
            onPressed: editable ? () => onEdit(item) : null,
            icon: const Icon(Icons.edit_outlined),
          ),
          IconButton(
            tooltip: editable ? 'Delete' : 'This system item cannot be deleted',
            onPressed: editable ? () => onDelete(item) : null,
            icon: const Icon(Icons.delete_outline),
          ),
        ])),
      ],
    );
  }

  @override
  bool get isRowCountApproximate => false;
  @override
  int get rowCount => total;
  @override
  int get selectedRowCount => 0;
}

class _EntityEditor extends StatefulWidget {
  const _EntityEditor({
    required this.title,
    required this.fields,
    required this.values,
    required this.api,
    required this.isCreating,
  });
  final String title;
  final List<FieldSpec> fields;
  final Map<String, dynamic> values;
  final ApiClient api;
  final bool isCreating;
  @override
  State<_EntityEditor> createState() => _EntityEditorState();
}

class _EntityEditorState extends State<_EntityEditor> {
  final _formKey = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _controllers = {
    for (final FieldSpec field
        in widget.fields.where((field) => !field.boolean && field.optionsResource == null))
      field.key: TextEditingController(text: widget.values[field.key]?.toString() ?? ''),
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
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: SizedBox(
          width: 560,
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: widget.fields.map(_field).toList(),
              ),
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: _save, child: const Text('Save')),
        ],
      );

  Widget _field(FieldSpec field) {
    if ((field.createOnly && !widget.isCreating) ||
        (field.editOnly && widget.isCreating)) {
      return const SizedBox.shrink();
    }
    if (field.boolean) {
      return SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(field.label),
        value: _booleans[field.key]!,
        onChanged: (value) => setState(() => _booleans[field.key] = value),
      );
    }
    if (field.optionsResource != null) {
      final List<AssignmentOption> options = _options[field.key] ?? const [];
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Align(
          alignment: Alignment.centerLeft,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(field.label, style: Theme.of(context).textTheme.titleSmall),
            if (field.helperText != null)
              Text(field.helperText!, style: Theme.of(context).textTheme.bodySmall),
            if (_loadingOptions)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator()),
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
                          onSelected: (selected) => setState(() {
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
          ]),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        controller: _controllers[field.key],
        readOnly: field.readOnlyWhenEditing && !widget.isCreating,
        maxLines: field.multiline ? 3 : 1,
        decoration: InputDecoration(labelText: field.label, helperText: field.helperText),
        validator: (value) =>
                (field.required || (field.requiredOnCreate && widget.isCreating)) &&
                    (value == null || value.trim().isEmpty)
            ? '${field.label} is required.'
            : null,
      ),
    );
  }

  void _save() {
    if (!_formKey.currentState!.validate()) return;
    Navigator.pop(context, <String, dynamic>{
      for (final MapEntry<String, TextEditingController> entry in _controllers.entries)
        entry.key: entry.value.text.trim(),
      for (final MapEntry<String, Set<String>> entry in _selections.entries)
        entry.key: entry.value.join(','),
      ..._booleans,
    });
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function({int? page}) onRetry;
  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.error_outline,
                size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () => onRetry(),
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ]),
        ),
      );
}
