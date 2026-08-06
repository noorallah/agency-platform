import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/preferences/desktop_preferences_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/uom_packaging.dart';
import '../workspace/workspace_components.dart';
import '../workspace/workspace_interactions.dart';

class ProductController extends ChangeNotifier {
  ProductController(this._api);

  final ApiClient _api;
  List<Product> items = const [];
  Product? selected;
  int total = 0;
  int page = 1;
  String search = '';
  String sortBy = 'created_at';
  bool descending = true;
  ProductQuery filters = const ProductQuery();
  bool loading = false;
  String? error;
  bool _disposed = false;

  List<ProductCategoryRecord> categories = const [];
  List<UomRecord> uoms = const [];
  List<AttributeDefinitionRecord> attributeDefinitions = const [];
  ProductMetadataRecord metadata = const ProductMetadataRecord(
    profileCode: '',
    features: [],
    categories: [],
    taxProfiles: [],
    requiredAttributeDefinitionIds: [],
    optionalAttributeDefinitionIds: [],
  );

  Future<void> bootstrap() async {
    try {
      categories = await _api.productCategories();
    } on ApiException {
      categories = const [];
    }
    try {
      metadata = await _api.productMetadata();
      if (categories.isEmpty && metadata.categories.isNotEmpty) {
        categories = metadata.categories;
      }
    } on ApiException {
      metadata = const ProductMetadataRecord(
        profileCode: '',
        features: [],
        categories: [],
        taxProfiles: [],
        requiredAttributeDefinitionIds: [],
        optionalAttributeDefinitionIds: [],
      );
    }
    try {
      final PagedResult<AttributeDefinitionRecord> result =
          await _api.attributeDefinitions(pageSize: 500);
      attributeDefinitions = result.items;
    } on ApiException catch (exception) {
      if (!exception.isForbidden) {
        rethrow;
      }
      attributeDefinitions = const [];
    }
    try {
      uoms = await _api.uoms();
    } on ApiException {
      uoms = const [];
    }
    notifyListeners();
  }

  Future<ProductMetadataRecord> metadataForCategory(String categoryId) async {
    metadata = await _api.productMetadata(categoryId: categoryId);
    notifyListeners();
    return metadata;
  }

  Future<void> load({int? requestedPage}) async {
    if (_disposed) return;
    loading = true;
    error = null;
    page = requestedPage ?? page;
    notifyListeners();
    try {
      final PagedResult<Product> result = await _api.products(
        page: page,
        search: search,
        sortBy: sortBy,
        descending: descending,
        filters: filters,
      );
      items = result.items;
      total = result.total;
      final String? selectedId = selected?.id;
      selected = selectedId == null
          ? null
          : items.cast<Product?>().firstWhere(
                (item) => item?.id == selectedId,
                orElse: () => null,
              );
    } on ApiException catch (exception) {
      error = exception.message;
      items = const [];
      total = 0;
    } finally {
      if (!_disposed) {
        loading = false;
        notifyListeners();
      }
    }
  }

  Future<Product> save(Product? product, Json payload) async => product == null
      ? _api.createProduct(payload)
      : _api.updateProduct(product.id, payload);

  Future<void> delete(Product product) => _api.deleteProduct(product.id);
  Future<void> restore(Product product) => _api.restoreProduct(product.id);
  Future<Product> duplicate(Product product) =>
      _api.duplicateProduct(product.id);
  Future<String> export({required String format}) =>
      _api.exportProducts(search: search, format: format);

  Future<int> bulkDelete(List<String> ids) => _api.bulkDeleteProducts(ids);
  Future<int> bulkRestore(List<String> ids) => _api.bulkRestoreProducts(ids);

  void select(Product product) {
    selected = product;
    notifyListeners();
  }

  Product? itemById(String id) => items.cast<Product?>().firstWhere(
        (item) => item?.id == id,
        orElse: () => null,
      );

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

class _ProductColumn {
  const _ProductColumn({
    required this.key,
    required this.label,
    this.visible = true,
    this.width = 180,
    this.sortField,
  });

  final String key;
  final String label;
  final bool visible;
  final double width;
  final String? sortField;

  _ProductColumn copyWith({
    bool? visible,
    double? width,
    String? sortField,
  }) =>
      _ProductColumn(
        key: key,
        label: label,
        visible: visible ?? this.visible,
        width: width ?? this.width,
        sortField: sortField ?? this.sortField,
      );

  Map<String, dynamic> toJson() => {
        'key': key,
        'visible': visible,
        'width': width,
        if (sortField != null) 'sort_field': sortField,
      };
}

class _SavedFilter {
  const _SavedFilter({
    required this.name,
    required this.query,
    required this.status,
    required this.productType,
    required this.categoryId,
    required this.brand,
    required this.hsnSac,
    required this.attributeQuery,
    required this.includeDeleted,
  });

  final String name;
  final String query;
  final String? status;
  final String? productType;
  final String? categoryId;
  final String brand;
  final String hsnSac;
  final String attributeQuery;
  final bool includeDeleted;

  Map<String, dynamic> toJson() => {
        'name': name,
        'query': query,
        'status': status,
        'product_type': productType,
        'category_id': categoryId,
        'brand': brand,
        'hsn_sac': hsnSac,
        'attribute_query': attributeQuery,
        'include_deleted': includeDeleted,
      };

  factory _SavedFilter.fromJson(Map<String, dynamic> json) => _SavedFilter(
        name: stringValue(json['name']),
        query: stringValue(json['query']),
        status: stringValue(json['status']).isEmpty
            ? null
            : stringValue(json['status']),
        productType: stringValue(json['product_type']).isEmpty
            ? null
            : stringValue(json['product_type']),
        categoryId: stringValue(json['category_id']).isEmpty
            ? null
            : stringValue(json['category_id']),
        brand: stringValue(json['brand']),
        hsnSac: stringValue(json['hsn_sac']),
        attributeQuery: stringValue(json['attribute_query']),
        includeDeleted: boolValue(json['include_deleted']),
      );
}

class ProductManagementPage extends StatefulWidget {
  const ProductManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.preferences,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final DesktopPreferencesService preferences;
  final bool hasActiveFirm;

  @override
  State<ProductManagementPage> createState() => _ProductManagementPageState();
}

class _ProductManagementPageState extends State<ProductManagementPage> {
  static const int _rowsPerPage = 20;
  static const String _preferencesKey = 'product_grid_v2';
  late final ProductController _controller = ProductController(widget.api)
    ..addListener(_changed);
  final TextEditingController _search = TextEditingController();
  final TextEditingController _brand = TextEditingController();
  final TextEditingController _hsnSac = TextEditingController();
  final TextEditingController _attributeSearch = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  final Set<String> _selectedIds = <String>{};
  final List<String> _recentSearches = <String>[];
  final List<_SavedFilter> _savedFilters = <_SavedFilter>[];
  List<_ProductColumn> _columns = const [
    _ProductColumn(key: 'code', label: 'Code', width: 150, sortField: 'code'),
    _ProductColumn(key: 'name', label: 'Name', width: 220, sortField: 'name'),
    _ProductColumn(key: 'type', label: 'Type', width: 150),
    _ProductColumn(key: 'brand', label: 'Brand', width: 150),
    _ProductColumn(key: 'category', label: 'Category', width: 170),
    _ProductColumn(
        key: 'status', label: 'Status', width: 130, sortField: 'status'),
    _ProductColumn(
        key: 'selling',
        label: 'Selling',
        width: 130,
        sortField: 'selling_price'),
    _ProductColumn(
        key: 'created', label: 'Created', width: 130, sortField: 'created_at'),
  ];
  String? _status;
  String? _productType;
  String? _categoryId;
  bool _includeDeleted = false;
  bool _filtersExpanded = false;
  bool _loadingPreferences = true;
  String _dialogTab = 'general';
  String _gridDensity = 'comfortable';

  bool get _canCreate =>
      widget.hasActiveFirm &&
      widget.permissions.hasPermission('PRODUCT_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('PRODUCT_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('PRODUCT_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('PRODUCT_RESTORE');
  bool get _canExport => widget.permissions.hasPermission('PRODUCT_EXPORT');
  bool get _canImport => widget.permissions.hasPermission('PRODUCT_IMPORT');

  @override
  void initState() {
    super.initState();
    _searchFocus.addListener(_changed);
    _loadPreferences();
    _controller.bootstrap().then((_) => _controller.load());
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_changed)
      ..dispose();
    _search.dispose();
    _brand.dispose();
    _hsnSac.dispose();
    _attributeSearch.dispose();
    _searchFocus
      ..removeListener(_changed)
      ..dispose();
    super.dispose();
  }

  Future<void> _loadPreferences() async {
    final Map<String, dynamic> raw =
        widget.preferences.current.serverPreferences[_preferencesKey] is Map
            ? Map<String, dynamic>.from(
                widget.preferences.current.serverPreferences[_preferencesKey]
                    as Map,
              )
            : const {};
    if (raw.isNotEmpty) {
      final List<dynamic> columns =
          raw['columns'] as List<dynamic>? ?? const [];
      final Map<String, _ProductColumn> defaults = {
        for (final _ProductColumn column in _columns) column.key: column,
      };
      final List<_ProductColumn> hydrated = columns
          .whereType<Map>()
          .map((entry) => Map<String, dynamic>.from(entry))
          .map(
            (entry) {
              final _ProductColumn? base = defaults[stringValue(entry['key'])];
              if (base == null) return null;
              return base.copyWith(
                visible: boolValue(entry['visible'], fallback: base.visible),
                width: (entry['width'] as num?)?.toDouble() ?? base.width,
              );
            },
          )
          .whereType<_ProductColumn>()
          .toList();
      if (hydrated.length == _columns.length) {
        _columns = hydrated;
      }
      _controller.sortBy = stringValue(raw['sort_by']).isEmpty
          ? _controller.sortBy
          : stringValue(raw['sort_by']);
      _controller.descending = boolValue(raw['descending'], fallback: true);
      _status = stringValue(raw['status']).isEmpty
          ? null
          : stringValue(raw['status']);
      _productType = stringValue(raw['product_type']).isEmpty
          ? null
          : stringValue(raw['product_type']);
      _categoryId = stringValue(raw['category_id']).isEmpty
          ? null
          : stringValue(raw['category_id']);
      _brand.text = stringValue(raw['brand']);
      _hsnSac.text = stringValue(raw['hsn_sac']);
      _attributeSearch.text = stringValue(raw['attribute_query']);
      _includeDeleted = boolValue(raw['include_deleted']);
      _filtersExpanded = boolValue(raw['filters_expanded']);
      _gridDensity = stringValue(raw['grid_density']).isEmpty
          ? 'comfortable'
          : stringValue(raw['grid_density']);
      _dialogTab = stringValue(raw['dialog_tab']).isEmpty
          ? 'general'
          : stringValue(raw['dialog_tab']);
      _recentSearches.addAll(
        stringList(raw['recent_searches']).where((entry) => entry.isNotEmpty),
      );
      _savedFilters.addAll(
        (raw['saved_filters'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((entry) =>
                _SavedFilter.fromJson(Map<String, dynamic>.from(entry))),
      );
    }
    if (mounted) {
      setState(() => _loadingPreferences = false);
    }
  }

  Future<void> _persistPreferences() =>
      widget.preferences.cacheServerPreferences({
        ...widget.preferences.current.serverPreferences,
        _preferencesKey: {
          'columns': _columns.map((column) => column.toJson()).toList(),
          'sort_by': _controller.sortBy,
          'descending': _controller.descending,
          'status': _status,
          'product_type': _productType,
          'category_id': _categoryId,
          'brand': _brand.text.trim(),
          'hsn_sac': _hsnSac.text.trim(),
          'attribute_query': _attributeSearch.text.trim(),
          'include_deleted': _includeDeleted,
          'filters_expanded': _filtersExpanded,
          'dialog_tab': _dialogTab,
          'grid_density': _gridDensity,
          'recent_searches': _recentSearches.take(10).toList(),
          'saved_filters':
              _savedFilters.map((entry) => entry.toJson()).toList(),
        },
      });

  int get _rowsPerPageForDensity => switch (_gridDensity) {
        'compact' => 24,
        'spacious' => 16,
        _ => _rowsPerPage,
      };

  int get _activeFilterCount => [
        _status != null,
        _productType != null,
        _categoryId != null,
        _brand.text.trim().isNotEmpty,
        _hsnSac.text.trim().isNotEmpty,
        _attributeSearch.text.trim().isNotEmpty,
        _includeDeleted,
      ].where((active) => active).length;

  void _changed() {
    if (mounted) setState(() {});
  }

  String _categoryLabel(String id) {
    final ProductCategoryRecord? match =
        _controller.categories.cast<ProductCategoryRecord?>().firstWhere(
              (item) => item?.id == id,
              orElse: () => null,
            );
    return match?.name ?? '';
  }

  ProductQuery _currentQuery() => ProductQuery(
        status: _status,
        productType: _productType,
        categoryId: _categoryId,
        brand: _brand.text.trim().isEmpty ? null : _brand.text.trim(),
        hsnSac: _hsnSac.text.trim().isEmpty ? null : _hsnSac.text.trim(),
        attributeQuery: _attributeSearch.text.trim().isEmpty
            ? null
            : _attributeSearch.text.trim(),
        includeDeleted: _includeDeleted,
      );

  Future<void> _applyFilters() async {
    _controller.filters = _currentQuery();
    await _persistPreferences();
    await _controller.load(requestedPage: 1);
  }

  Future<void> _clearFilters() async {
    setState(() {
      _status = null;
      _productType = null;
      _categoryId = null;
      _brand.clear();
      _hsnSac.clear();
      _attributeSearch.clear();
      _includeDeleted = false;
    });
    await _applyFilters();
  }

  Future<void> _open(ProductDialogMode mode, [Product? product]) async {
    if (mode == ProductDialogMode.create && !_canCreate) return;
    if (mode == ProductDialogMode.edit &&
        (!_canEdit || product == null || product.isDeleted)) {
      return;
    }
    final Product? saved = await showDialog<Product>(
      context: context,
      barrierDismissible: false,
      builder: (context) => ProductWorkspaceDialog(
        mode: mode,
        product: product,
        categories: _controller.categories,
        uoms: _controller.uoms,
        definitions: _controller.attributeDefinitions,
        metadata: _controller.metadata,
        initialTab: _dialogTab,
        onMetadataForCategory: _controller.metadataForCategory,
        onSave: (payload) => _controller.save(product, payload),
        onTabChanged: (tab) {
          _dialogTab = tab;
          _persistPreferences();
        },
      ),
    );
    if (saved == null || !mounted) return;
    NotificationService.show(
      context,
      'Product ${product == null ? 'created' : 'updated'}.',
      kind: AppNotificationKind.success,
    );
    await _controller.load();
  }

  Future<void> _delete(Product product) async {
    if (!_canDelete || product.isDeleted) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${product.name}?',
      message: 'The product will be hidden and can be restored later.',
      confirmLabel: 'Delete product',
      type: ConfirmationType.delete,
    );
    if (!accepted) return;
    await _controller.delete(product);
    if (!mounted) return;
    NotificationService.show(context, 'Product deleted.');
    await _controller.load();
  }

  Future<void> _restore(Product product) async {
    if (!_canRestore || !product.isDeleted) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Restore ${product.name}?',
      message: 'The product will return to active search results.',
      confirmLabel: 'Restore product',
    );
    if (!accepted) return;
    await _controller.restore(product);
    if (!mounted) return;
    NotificationService.show(context, 'Product restored.');
    await _controller.load();
  }

  Future<void> _copy(Product product) async {
    await copyTextToClipboard(
      [
        product.code,
        product.name,
        product.productType,
        _categoryLabel(product.categoryId),
        product.status,
        product.sellingPrice,
      ].join('\t'),
    );
    if (mounted) {
      NotificationService.show(context, 'Product row copied.');
    }
  }

  Future<void> _copySelection() async {
    if (_selectedIds.isEmpty) return;
    final List<String> rows = _selectedIds
        .map(_controller.itemById)
        .whereType<Product>()
        .map(
          (product) => [
            product.code,
            product.name,
            product.productType,
            _categoryLabel(product.categoryId),
            product.status,
            product.sellingPrice,
          ].join('\t'),
        )
        .toList();
    if (rows.isEmpty) return;
    await copyTextToClipboard(rows.join('\n'));
    if (mounted) {
      NotificationService.show(context, 'Selected product rows copied.');
    }
  }

  Future<void> _runBulkOperation() async {
    if (_selectedIds.isEmpty) {
      NotificationService.show(
        context,
        'Select at least one product.',
        kind: AppNotificationKind.warning,
      );
      return;
    }
    final _BulkOperationResult? operation =
        await showDialog<_BulkOperationResult>(
      context: context,
      builder: (context) => _BulkOperationDialog(
        categories: _controller.categories,
        selectedCount: _selectedIds.length,
      ),
    );
    if (operation == null) return;
    int affected = 0;
    final List<Product> targets =
        _selectedIds.map(_controller.itemById).whereType<Product>().toList();
    switch (operation.kind) {
      case _BulkOperationKind.delete:
        affected = await _controller.bulkDelete(_selectedIds.toList());
      case _BulkOperationKind.restore:
        affected = await _controller.bulkRestore(_selectedIds.toList());
      case _BulkOperationKind.export:
        final String text = await _controller.export(format: operation.format);
        await copyTextToClipboard(text);
        affected = targets.length;
      case _BulkOperationKind.statusChange:
        for (final Product product in targets) {
          await _controller.save(product, {
            'code': product.code,
            'name': product.name,
            'product_type': product.productType,
            'status': operation.status,
            'category_id':
                product.categoryId.isEmpty ? null : product.categoryId,
            'tax_profile_id':
                product.taxProfileId.isEmpty ? null : product.taxProfileId,
            'attributes': product.attributes
                .map(
                  (entry) => {
                    'attribute_definition_id': entry.attributeDefinitionId,
                    'value': entry.valueText.isNotEmpty
                        ? entry.valueText
                        : entry.valueDate,
                  },
                )
                .toList(),
            'media': product.media
                .map(
                  (entry) => {
                    'media_kind': entry.mediaKind,
                    'file_name': entry.fileName,
                    'mime_type': entry.mimeType,
                    'storage_path': entry.storagePath,
                    'is_primary': entry.isPrimary,
                  },
                )
                .toList(),
          });
        }
        affected = targets.length;
      case _BulkOperationKind.categoryChange:
        for (final Product product in targets) {
          await _controller.save(product, {
            'code': product.code,
            'name': product.name,
            'product_type': product.productType,
            'status': product.status,
            'category_id':
                operation.categoryId.isEmpty ? null : operation.categoryId,
            'tax_profile_id':
                product.taxProfileId.isEmpty ? null : product.taxProfileId,
            'attributes': const [],
            'media': const [],
          });
        }
        affected = targets.length;
      case _BulkOperationKind.priceUpdate:
        final num delta = num.tryParse(operation.value) ?? 0;
        for (final Product product in targets) {
          final num current = num.tryParse(product.sellingPrice) ?? 0;
          await _controller.save(product, {
            'code': product.code,
            'name': product.name,
            'product_type': product.productType,
            'status': product.status,
            'category_id':
                product.categoryId.isEmpty ? null : product.categoryId,
            'tax_profile_id':
                product.taxProfileId.isEmpty ? null : product.taxProfileId,
            'selling_price': (current + delta).toStringAsFixed(2),
            'attributes': const [],
            'media': const [],
          });
        }
        affected = targets.length;
    }
    if (!mounted) return;
    NotificationService.show(
        context, 'Bulk operation completed: $affected updated.');
    _selectedIds.clear();
    await _controller.load();
  }

  Future<void> _openColumnChooser() async {
    final List<_ProductColumn>? updated =
        await showDialog<List<_ProductColumn>>(
      context: context,
      builder: (context) => _ColumnChooserDialog(columns: _columns),
    );
    if (updated == null) return;
    setState(() => _columns = updated);
    await _persistPreferences();
  }

  Future<void> _saveCurrentFilter() async {
    final TextEditingController nameController = TextEditingController();
    final String? name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Save filter'),
        content: TextField(
          controller: nameController,
          decoration: const InputDecoration(labelText: 'Filter name'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.of(context).pop(nameController.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;
    _savedFilters.removeWhere((entry) => entry.name == name);
    _savedFilters.insert(
      0,
      _SavedFilter(
        name: name,
        query: _search.text.trim(),
        status: _status,
        productType: _productType,
        categoryId: _categoryId,
        brand: _brand.text.trim(),
        hsnSac: _hsnSac.text.trim(),
        attributeQuery: _attributeSearch.text.trim(),
        includeDeleted: _includeDeleted,
      ),
    );
    await _persistPreferences();
    if (mounted) {
      NotificationService.show(context, 'Filter "$name" saved.');
    }
  }

  Future<void> _applySavedFilter(_SavedFilter filter) async {
    setState(() {
      _search.text = filter.query;
      _status = filter.status;
      _productType = filter.productType;
      _categoryId = filter.categoryId;
      _brand.text = filter.brand;
      _hsnSac.text = filter.hsnSac;
      _attributeSearch.text = filter.attributeQuery;
      _includeDeleted = filter.includeDeleted;
    });
    _controller.search = filter.query;
    await _applyFilters();
  }

  Future<void> _runImportWizard() async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (context) => _ProductImportWizard(
        onImport: (records) async {
          for (final Json record in records) {
            await widget.api.createProduct(record);
          }
        },
      ),
    );
    if (!mounted) return;
    await _controller.load();
  }

  Future<void> _export(String format) async {
    final _ExportScope? scope = await showDialog<_ExportScope>(
      context: context,
      builder: (context) => const _ExportScopeDialog(),
    );
    if (scope == null) return;
    String text;
    if (scope == _ExportScope.selected && _selectedIds.isNotEmpty) {
      final List<Product> selected =
          _selectedIds.map(_controller.itemById).whereType<Product>().toList();
      text = [
        'Code,Name,Type,Category,Status,SellingPrice',
        ...selected.map(
          (item) =>
              '${item.code},${item.name},${item.productType},${_categoryLabel(item.categoryId)},${item.status},${item.sellingPrice}',
        ),
      ].join('\n');
    } else {
      text = await _controller.export(format: format);
    }
    await copyTextToClipboard(text);
    if (mounted) {
      NotificationService.show(context, 'Export copied to clipboard.');
    }
  }

  Future<void> _runSearch(String query) async {
    final String value = query.trim();
    _controller.search = value;
    if (value.isNotEmpty) {
      _recentSearches.remove(value);
      _recentSearches.insert(0, value);
    }
    await _persistPreferences();
    await _controller.load(requestedPage: 1);
  }

  @override
  Widget build(BuildContext context) {
    if (_loadingPreferences) {
      return const Center(child: CircularProgressIndicator());
    }
    final Product? selected = _controller.selected;
    final List<_ProductColumn> visibleColumns =
        _columns.where((column) => column.visible).toList();
    final List<GridColumn> gridColumns = _columns
        .map(
          (column) => GridColumn(
            key: column.key,
            label: column.label,
            tooltip: column.label,
            visible: column.visible,
            onSort: column.sortField == null
                ? null
                : (ascending) {
                    _controller
                      ..sortBy = column.sortField!
                      ..descending = !ascending;
                    _persistPreferences();
                    _controller.load(requestedPage: 1);
                  },
          ),
        )
        .toList();
    final Widget toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.view,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.import,
        ToolbarAction.export,
        ToolbarAction.refresh,
        ToolbarAction.settings,
      ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete,
        ToolbarAction.import => _canImport,
        ToolbarAction.export => _canExport,
        _ => true,
      },
      isEnabled: (action) =>
          !_controller.loading &&
          switch (action) {
            ToolbarAction.newItem => _canCreate,
            ToolbarAction.view => selected != null,
            ToolbarAction.edit => selected != null && !selected.isDeleted,
            ToolbarAction.delete => _selectedIds.isNotEmpty ||
                (selected != null && !selected.isDeleted),
            ToolbarAction.import => _canImport,
            ToolbarAction.export =>
              _controller.items.isNotEmpty || _selectedIds.isNotEmpty,
            ToolbarAction.refresh => true,
            ToolbarAction.settings => true,
            ToolbarAction.print => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _open(ProductDialogMode.create);
            break;
          case ToolbarAction.view:
            if (selected != null) _open(ProductDialogMode.view, selected);
            break;
          case ToolbarAction.edit:
            if (selected != null) _open(ProductDialogMode.edit, selected);
            break;
          case ToolbarAction.delete:
            _runBulkOperation();
            break;
          case ToolbarAction.import:
            _runImportWizard();
            break;
          case ToolbarAction.export:
            _export('csv');
            break;
          case ToolbarAction.refresh:
            _controller.load();
            break;
          case ToolbarAction.settings:
            _openColumnChooser();
            break;
          case ToolbarAction.print:
            break;
        }
      },
    );
    final Widget searchPanel = Row(
      children: [
        Expanded(
          child: SearchFilterPanel(
            controller: _search,
            focusNode: _searchFocus,
            hintText: 'Search code, barcode, QR, name, brand, HSN, attributes',
            onSearch: _runSearch,
            filters: [
              if (_recentSearches.isNotEmpty)
                PopupMenuButton<String>(
                  tooltip: 'Recent searches',
                  onSelected: (value) {
                    _search.text = value;
                    _runSearch(value);
                  },
                  itemBuilder: (context) => _recentSearches
                      .take(8)
                      .map((entry) => PopupMenuItem(
                            value: entry,
                            child: Text(entry),
                          ))
                      .toList(),
                  child: const Icon(Icons.history),
                ),
              PopupMenuButton<_SavedFilter>(
                tooltip: 'Saved filters',
                onSelected: _applySavedFilter,
                itemBuilder: (context) => _savedFilters.isEmpty
                    ? const [
                        PopupMenuItem(
                          enabled: false,
                          child: Text('No saved filters'),
                        )
                      ]
                    : _savedFilters
                        .map((entry) => PopupMenuItem(
                            value: entry, child: Text(entry.name)))
                        .toList(),
                child: const Icon(Icons.bookmark_outline),
              ),
              IconButton(
                tooltip: 'Save current filter',
                onPressed: _saveCurrentFilter,
                icon: const Icon(Icons.bookmark_add_outlined),
              ),
              IconButton(
                tooltip: 'Advanced filters',
                onPressed: () => setState(() => _filtersExpanded = true),
                icon: const Icon(Icons.filter_alt_outlined),
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        DropdownButton<String>(
          value: _gridDensity,
          items: const [
            DropdownMenuItem(value: 'compact', child: Text('Compact')),
            DropdownMenuItem(value: 'comfortable', child: Text('Comfortable')),
            DropdownMenuItem(value: 'spacious', child: Text('Spacious')),
          ],
          onChanged: (value) {
            if (value == null) return;
            setState(() => _gridDensity = value);
            _persistPreferences();
          },
        ),
      ],
    );
    final Widget filterPanel = FilterPanel(
      expanded: _filtersExpanded,
      onExpandedChanged: (value) {
        _filtersExpanded = value;
        _persistPreferences();
      },
      activeFilterCount: _activeFilterCount,
      onApply: _applyFilters,
      onClear: _clearFilters,
      children: [
        _dropdown(
          label: 'Status',
          value: _status,
          values: const ['ACTIVE', 'INACTIVE', 'DRAFT', 'ARCHIVED'],
          onChanged: (value) => setState(() => _status = value),
        ),
        _dropdown(
          label: 'Product Type',
          value: _productType,
          values: const [
            'STOCK_ITEM',
            'SERVICE',
            'RAW_MATERIAL',
            'FINISHED_GOODS',
            'SEMI_FINISHED',
            'ASSET',
            'CONSUMABLE',
            'BUNDLE',
            'DIGITAL_PRODUCT',
          ],
          onChanged: (value) => setState(() => _productType = value),
        ),
        SizedBox(
          width: 220,
          child: DropdownButtonFormField<String?>(
            initialValue: _categoryId,
            decoration: const InputDecoration(labelText: 'Category'),
            items: [
              const DropdownMenuItem(value: null, child: Text('Any')),
              ..._controller.categories.map(
                (category) => DropdownMenuItem(
                  value: category.id,
                  child: Text(category.name),
                ),
              )
            ],
            onChanged: (value) => setState(() => _categoryId = value),
          ),
        ),
        _textFilter(_brand, 'Brand'),
        _textFilter(_hsnSac, 'HSN / SAC'),
        _textFilter(_attributeSearch, 'Attribute contains'),
        FilterChip(
          label: const Text('Include deleted'),
          selected: _includeDeleted,
          onSelected: (value) => setState(() => _includeDeleted = value),
        ),
      ],
    );
    final List<Widget> filterChips = [
      if (_status != null)
        InputChip(
          label: Text('Status: $_status'),
          onDeleted: () => setState(() => _status = null),
        ),
      if (_productType != null)
        InputChip(
          label: Text('Type: $_productType'),
          onDeleted: () => setState(() => _productType = null),
        ),
      if (_categoryId != null)
        InputChip(
          label: Text('Category: ${_categoryLabel(_categoryId!)}'),
          onDeleted: () => setState(() => _categoryId = null),
        ),
      if (_brand.text.trim().isNotEmpty)
        InputChip(
          label: Text('Brand: ${_brand.text.trim()}'),
          onDeleted: () => setState(_brand.clear),
        ),
      if (_hsnSac.text.trim().isNotEmpty)
        InputChip(
          label: Text('HSN: ${_hsnSac.text.trim()}'),
          onDeleted: () => setState(_hsnSac.clear),
        ),
      if (_attributeSearch.text.trim().isNotEmpty)
        InputChip(
          label: Text('Attr: ${_attributeSearch.text.trim()}'),
          onDeleted: () => setState(_attributeSearch.clear),
        ),
      if (_includeDeleted)
        InputChip(
          label: const Text('Including deleted'),
          onDeleted: () => setState(() => _includeDeleted = false),
        ),
    ];
    final Widget primaryContent;
    if (_controller.error != null) {
      primaryContent = WorkspaceErrorState(
        message: _controller.error!,
        onRetry: _controller.load,
      );
    } else if (_controller.loading && _controller.items.isEmpty) {
      primaryContent = const TableLoadingSkeleton();
    } else if (_controller.items.isEmpty) {
      primaryContent = const StandardEmptyState(type: EmptyStateType.noRecords);
    } else {
      primaryContent = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (filterChips.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
              child: Wrap(spacing: 8, runSpacing: 8, children: filterChips),
            ),
          Expanded(
            child: EnterpriseDataGrid<Product>(
              items: _controller.items,
              total: _controller.total,
              pageOffset: (_controller.page - 1) * _rowsPerPageForDensity,
              rowsPerPage: _rowsPerPageForDensity,
              showRowNumbers: true,
              selectedIds: _selectedIds,
              onSelectionChanged: (ids) => setState(() {
                _selectedIds
                  ..clear()
                  ..addAll(ids);
              }),
              columns: gridColumns,
              id: (product) => product.id,
              cells: (product) => [
                product.code,
                product.name,
                product.productType,
                product.brand,
                _categoryLabel(product.categoryId),
                product.isDeleted ? 'DELETED' : product.status,
                product.sellingPrice,
                _dateOnly(product.createdAt),
              ],
              cellBuilder: (columnIndex, value, product) {
                final _ProductColumn column = visibleColumns[columnIndex];
                if (column.key == 'status') {
                  final ColorScheme colors = Theme.of(context).colorScheme;
                  final bool deleted = product.isDeleted;
                  final Color bg = deleted
                      ? colors.errorContainer
                      : value == 'ACTIVE'
                          ? colors.primaryContainer
                          : colors.surfaceContainerHighest;
                  return SizedBox(
                    width: column.width,
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: bg,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(value),
                      ),
                    ),
                  );
                }
                return SizedBox(
                  width: column.width,
                  child: Text(
                    value,
                    overflow: TextOverflow.ellipsis,
                  ),
                );
              },
              selectedId: selected?.id,
              onSelect: _controller.select,
              onOpen: (product) => _open(ProductDialogMode.view, product),
              contextActionsFor: (product) => [
                WorkspaceContextAction.view,
                if (_canEdit && !product.isDeleted) WorkspaceContextAction.edit,
                if (_canDelete && !product.isDeleted)
                  WorkspaceContextAction.delete,
                if (_canRestore && product.isDeleted)
                  WorkspaceContextAction.restore,
                WorkspaceContextAction.copy,
                WorkspaceContextAction.refresh,
                WorkspaceContextAction.export,
              ],
              onContextAction: (action, product) async {
                switch (action) {
                  case WorkspaceContextAction.view:
                    await _open(ProductDialogMode.view, product);
                    break;
                  case WorkspaceContextAction.edit:
                    await _open(ProductDialogMode.edit, product);
                    break;
                  case WorkspaceContextAction.delete:
                    await _delete(product);
                    break;
                  case WorkspaceContextAction.restore:
                    await _restore(product);
                    break;
                  case WorkspaceContextAction.copy:
                    await _copy(product);
                    break;
                  case WorkspaceContextAction.refresh:
                    await _controller.load();
                    break;
                  case WorkspaceContextAction.export:
                    await _export('csv');
                    break;
                }
              },
              onPageChanged: (offset) => _controller.load(
                  requestedPage: offset ~/ _rowsPerPageForDensity + 1),
            ),
          ),
        ],
      );
    }
    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreate ? () => _open(ProductDialogMode.create) : null,
        save: selected != null && _canEdit
            ? () => _open(ProductDialogMode.edit, selected)
            : null,
        focusSearch: _searchFocus.requestFocus,
        advancedSearch: () => setState(() => _filtersExpanded = true),
        export: _canExport ? () => _export('csv') : null,
        edit: selected != null && _canEdit
            ? () => _open(ProductDialogMode.edit, selected)
            : null,
        refresh: _controller.load,
        copy: selected == null ? null : () => _copy(selected),
        copyRow: _selectedIds.isEmpty ? null : _copySelection,
        cancel: selected == null
            ? null
            : () => setState(() {
                  _selectedIds.clear();
                  _controller.selected = null;
                }),
        delete: (_selectedIds.isNotEmpty || selected != null) && _canDelete
            ? _runBulkOperation
            : null,
        globalSearch: _canExport ? _runBulkOperation : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: searchPanel,
        filterPanel: filterPanel,
        primaryContent: primaryContent,
        detailsPanel: selected == null
            ? null
            : QuickSummaryPanel(
                title: selected.name,
                lines: [
                  DetailLine('Code', selected.code),
                  DetailLine('Type', selected.productType),
                  DetailLine(
                    'Status',
                    selected.isDeleted ? 'DELETED' : selected.status,
                  ),
                  DetailLine('Category', _categoryLabel(selected.categoryId)),
                  DetailLine('Selling', selected.sellingPrice),
                  DetailLine('Created', _dateOnly(selected.createdAt)),
                ],
                onView: () => _open(ProductDialogMode.view, selected),
                onEdit: _canEdit && !selected.isDeleted
                    ? () => _open(ProductDialogMode.edit, selected)
                    : null,
              ),
        statusBar: WorkspaceStatusBar(
          total: _controller.total,
          selected: _selectedIds.isNotEmpty || selected != null,
          selectedCount: _selectedIds.isNotEmpty ? _selectedIds.length : null,
          message: _controller.loading
              ? 'Refreshing...'
              : '${visibleColumns.length} visible columns',
        ),
      ),
    );
  }

  Widget _textFilter(TextEditingController controller, String label) =>
      SizedBox(
        width: 220,
        child: TextField(
          controller: controller,
          decoration: InputDecoration(labelText: label),
        ),
      );

  Widget _dropdown({
    required String label,
    required String? value,
    required List<String> values,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 220,
        child: DropdownButtonFormField<String?>(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          items: [
            const DropdownMenuItem(value: null, child: Text('Any')),
            ...values.map(
                (item) => DropdownMenuItem(value: item, child: Text(item))),
          ],
          onChanged: onChanged,
        ),
      );
}

enum ProductDialogMode { create, view, edit }

class ProductWorkspaceDialog extends StatefulWidget {
  const ProductWorkspaceDialog({
    super.key,
    required this.mode,
    required this.product,
    required this.categories,
    required this.uoms,
    required this.definitions,
    required this.metadata,
    required this.initialTab,
    required this.onMetadataForCategory,
    required this.onSave,
    required this.onTabChanged,
  });

  final ProductDialogMode mode;
  final Product? product;
  final List<ProductCategoryRecord> categories;
  final List<UomRecord> uoms;
  final List<AttributeDefinitionRecord> definitions;
  final ProductMetadataRecord metadata;
  final String initialTab;
  final Future<ProductMetadataRecord> Function(String categoryId)
      onMetadataForCategory;
  final Future<Product> Function(Json payload) onSave;
  final ValueChanged<String> onTabChanged;

  @override
  State<ProductWorkspaceDialog> createState() => _ProductWorkspaceDialogState();
}

class _ProductWorkspaceDialogState extends State<ProductWorkspaceDialog> {
  static const List<String> _tabs = [
    'general',
    'packaging',
    'pricing',
    'tax',
    'business_attributes',
    'images',
    'attachments',
    'audit',
    'history',
    'notes',
    'future_inventory',
  ];
  late final TextEditingController _code;
  late final TextEditingController _name;
  late final TextEditingController _shortName;
  late final TextEditingController _description;
  late final TextEditingController _barcode;
  late final TextEditingController _qrCode;
  late final TextEditingController _brand;
  late final TextEditingController _model;
  late final TextEditingController _unit;
  late final TextEditingController _hsn;
  late final TextEditingController _weight;
  late final TextEditingController _volume;
  late final TextEditingController _length;
  late final TextEditingController _width;
  late final TextEditingController _height;
  late final TextEditingController _purchasePrice;
  late final TextEditingController _sellingPrice;
  late final TextEditingController _mrp;
  late final TextEditingController _remarks;
  late final TextEditingController _notes;
  late String _productType;
  late String _status;
  late String _categoryId;
  late String _taxProfileId;
  late String _baseUomId;
  late String _inventoryUomId;
  late String _purchaseUomId;
  late String _salesUomId;
  late String _defaultReceivingUomId;
  late String _defaultDispatchUomId;
  late String _minimumSalesUomId;
  late bool _allowFraction;
  late bool _allowDecimal;
  late ProductMetadataRecord _metadata;
  late String _tab;
  final Map<String, TextEditingController> _attributeControllers = {};
  final List<Map<String, String>> _imageRows = [];
  final List<Map<String, String>> _attachmentRows = [];
  bool _saving = false;
  bool _dirty = false;
  List<String> _validationSummary = const [];

  bool get _readOnly => widget.mode == ProductDialogMode.view;
  bool get _barcodeEnabled => _metadata.featureEnabled('BARCODE');
  bool get _qrEnabled => _metadata.featureEnabled('QR_CODE');

  @override
  void initState() {
    super.initState();
    final Product? product = widget.product;
    _code = TextEditingController(text: product?.code ?? '');
    _name = TextEditingController(text: product?.name ?? '');
    _shortName = TextEditingController(text: product?.shortName ?? '');
    _description = TextEditingController(text: product?.description ?? '');
    _barcode = TextEditingController(text: product?.barcode ?? '');
    _qrCode = TextEditingController(text: product?.qrCode ?? '');
    _brand = TextEditingController(text: product?.brand ?? '');
    _model = TextEditingController(text: product?.model ?? '');
    _unit = TextEditingController(text: product?.unit ?? '');
    _hsn = TextEditingController(text: product?.hsnSac ?? '');
    _weight = TextEditingController(text: product?.weight ?? '');
    _volume = TextEditingController(text: product?.volume ?? '');
    _length = TextEditingController(text: product?.length ?? '');
    _width = TextEditingController(text: product?.width ?? '');
    _height = TextEditingController(text: product?.height ?? '');
    _purchasePrice = TextEditingController(text: product?.purchasePrice ?? '');
    _sellingPrice = TextEditingController(text: product?.sellingPrice ?? '');
    _mrp = TextEditingController(text: product?.mrp ?? '');
    _remarks = TextEditingController(text: product?.remarks ?? '');
    _notes = TextEditingController(text: '');
    _productType = product?.productType.isNotEmpty == true
        ? product!.productType
        : 'STOCK_ITEM';
    _status = product?.status.isNotEmpty == true ? product!.status : 'ACTIVE';
    _categoryId = product?.categoryId ?? '';
    _taxProfileId = product?.taxProfileId ?? '';
    _baseUomId = product?.baseUomId ?? '';
    _inventoryUomId = product?.inventoryUomId ?? '';
    _purchaseUomId = product?.purchaseUomId ?? '';
    _salesUomId = product?.salesUomId ?? '';
    _defaultReceivingUomId = product?.defaultReceivingUomId ?? '';
    _defaultDispatchUomId = product?.defaultDispatchUomId ?? '';
    _minimumSalesUomId = product?.minimumSalesUomId ?? '';
    _allowFraction = product?.allowFraction ?? false;
    _allowDecimal = product?.allowDecimal ?? true;
    _metadata = widget.metadata;
    _tab = _tabs.contains(widget.initialTab) ? widget.initialTab : 'general';
    _syncAttributeControllers();
    for (final ProductMediaRecord media in product?.media ?? const []) {
      _imageRows.add({
        'kind': media.mediaKind,
        'file': media.fileName,
        'mime': media.mimeType,
        'path': media.storagePath,
        'primary': media.isPrimary ? 'true' : 'false',
      });
    }
    for (final TextEditingController controller in _allControllers) {
      controller.addListener(() => _dirty = true);
    }
  }

  Iterable<TextEditingController> get _allControllers => [
        _code,
        _name,
        _shortName,
        _description,
        _barcode,
        _qrCode,
        _brand,
        _model,
        _unit,
        _hsn,
        _weight,
        _volume,
        _length,
        _width,
        _height,
        _purchasePrice,
        _sellingPrice,
        _mrp,
        _remarks,
        _notes,
      ];

  List<String> get _allowedAttributeIds => {
        ..._metadata.requiredAttributeDefinitionIds,
        ..._metadata.optionalAttributeDefinitionIds
      }.toList();

  void _syncAttributeControllers() {
    for (final String id in _allowedAttributeIds) {
      _attributeControllers.putIfAbsent(id, () => TextEditingController());
    }
    for (final ProductAttributeValueRecord value
        in widget.product?.attributes ?? const []) {
      final TextEditingController? controller =
          _attributeControllers[value.attributeDefinitionId];
      if (controller != null) {
        controller.text =
            value.valueText.isNotEmpty ? value.valueText : value.valueDate;
      }
    }
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _allControllers) {
      controller.dispose();
    }
    for (final TextEditingController controller
        in _attributeControllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Dialog(
        insetPadding: const EdgeInsets.all(20),
        clipBehavior: Clip.antiAlias,
        child: SizedBox(
          width: MediaQuery.sizeOf(context).width * .9,
          height: MediaQuery.sizeOf(context).height * .88,
          child: Column(
            children: [
              ListTile(
                title: Text(
                  switch (widget.mode) {
                    ProductDialogMode.create => 'Create product',
                    ProductDialogMode.edit => 'Edit product',
                    ProductDialogMode.view => 'Product details',
                  },
                ),
                subtitle: const Text(
                  'General, pricing, tax, dynamic attributes, images, attachments, audit, and history.',
                ),
                trailing: IconButton(
                  tooltip: 'Close',
                  onPressed: _saving ? null : _close,
                  icon: const Icon(Icons.close),
                ),
              ),
              if (_validationSummary.isNotEmpty)
                Material(
                  color: Theme.of(context).colorScheme.errorContainer,
                  child: ListTile(
                    leading: const Icon(Icons.error_outline),
                    title: Text(
                        '${_validationSummary.length} validation issue(s)'),
                    subtitle: Text(_validationSummary.join(' • ')),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SegmentedButton<String>(
                    segments: _tabs
                        .map(
                          (tab) => ButtonSegment(
                            value: tab,
                            label: Text(_label(tab)),
                            enabled: _tabAvailable(tab),
                          ),
                        )
                        .toList(),
                    selected: {_tab},
                    showSelectedIcon: false,
                    onSelectionChanged: (selection) {
                      final String value = selection.first;
                      setState(() => _tab = value);
                      widget.onTabChanged(value);
                    },
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: AbsorbPointer(
                  absorbing: _saving,
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                    child: _tabBody(),
                  ),
                ),
              ),
              const Divider(height: 1),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    TextButton(
                      onPressed: _saving ? null : _close,
                      child: Text(_readOnly ? 'Close' : 'Cancel'),
                    ),
                    const Spacer(),
                    if (!_readOnly) ...[
                      OutlinedButton(
                        onPressed: _saving ? null : _saveAndNew,
                        child: const Text('Save & New'),
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton(
                        onPressed: _saving ? null : _submit,
                        child: const Text('Save'),
                      ),
                      const SizedBox(width: 8),
                      FilledButton(
                        onPressed: _saving ? null : _saveAndClose,
                        child: Text(_saving ? 'Saving...' : 'Save & Close'),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      );

  bool _tabAvailable(String tab) {
    if (tab == 'images') {
      return _metadata.featureEnabled('ATTACHMENTS') ||
          _metadata.featureEnabled('BARCODE') ||
          true;
    }
    if (tab == 'attachments') {
      return _metadata.featureEnabled('ATTACHMENTS') || true;
    }
    return true;
  }

  String _label(String key) => switch (key) {
        'general' => 'General',
        'packaging' => 'Packaging',
        'pricing' => 'Pricing',
        'tax' => 'Tax',
        'business_attributes' => 'Business Attributes',
        'images' => 'Images',
        'attachments' => 'Attachments',
        'audit' => 'Audit',
        'history' => 'History',
        'notes' => 'Notes',
        'future_inventory' => 'Future Inventory',
        _ => key,
      };

  Widget _tabBody() => switch (_tab) {
        'general' => _generalSection(),
        'packaging' => _packagingSection(),
        'pricing' => _pricingSection(),
        'tax' => _taxSection(),
        'business_attributes' => _attributesSection(),
        'images' => _mediaSection(_imageRows, imageMode: true),
        'attachments' => _mediaSection(_attachmentRows, imageMode: false),
        'audit' => _auditSection(),
        'history' => _historySection(),
        'notes' => _notesSection(),
        'future_inventory' => _futureInventorySection(),
        _ => const SizedBox.shrink(),
      };

  Widget _generalSection() => Wrap(
        spacing: 16,
        runSpacing: 12,
        children: [
          _field(_code, 'Product code', required: true),
          _field(_name, 'Product name', required: true, width: 360),
          _field(_shortName, 'Short name'),
          _dropdown(
            label: 'Product type',
            value: _productType,
            values: const [
              'STOCK_ITEM',
              'SERVICE',
              'RAW_MATERIAL',
              'FINISHED_GOODS',
              'SEMI_FINISHED',
              'ASSET',
              'CONSUMABLE',
              'BUNDLE',
              'DIGITAL_PRODUCT',
            ],
            onChanged: (value) =>
                setState(() => _productType = value ?? 'STOCK_ITEM'),
          ),
          _dropdown(
            label: 'Status',
            value: _status,
            values: const ['ACTIVE', 'INACTIVE', 'DRAFT', 'ARCHIVED'],
            onChanged: (value) => setState(() => _status = value ?? 'ACTIVE'),
          ),
          SizedBox(
            width: 260,
            child: DropdownButtonFormField<String>(
              initialValue: _categoryId.isEmpty ? null : _categoryId,
              decoration: const InputDecoration(labelText: 'Category'),
              items: widget.categories
                  .map(
                    (category) => DropdownMenuItem(
                      value: category.id,
                      child: Text(category.name),
                    ),
                  )
                  .toList(),
              onChanged: _readOnly
                  ? null
                  : (value) async {
                      if (value == null) return;
                      final ProductMetadataRecord metadata =
                          await widget.onMetadataForCategory(value);
                      if (!mounted) return;
                      setState(() {
                        _categoryId = value;
                        _metadata = metadata;
                        _syncAttributeControllers();
                      });
                    },
            ),
          ),
          _field(_unit, 'Unit'),
          _field(_brand, 'Brand'),
          _field(_model, 'Model'),
          _field(_remarks, 'Remarks', width: 520),
          _field(_description, 'Description', width: 760, lines: 3),
          _field(
            _barcode,
            'Barcode',
            readOnly: _readOnly || !_barcodeEnabled,
            helper: _barcodeEnabled
                ? null
                : 'Disabled by feature flag for current profile.',
          ),
          _field(
            _qrCode,
            'QR Code',
            readOnly: _readOnly || !_qrEnabled,
            helper: _qrEnabled
                ? null
                : 'Disabled by feature flag for current profile.',
          ),
        ],
      );

  Widget _pricingSection() => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExpansionTile(
            title: const Text('Price setup'),
            initiallyExpanded: true,
            childrenPadding: const EdgeInsets.symmetric(horizontal: 8),
            children: [
              Wrap(
                spacing: 16,
                runSpacing: 12,
                children: [
                  _field(_purchasePrice, 'Purchase price'),
                  _field(_sellingPrice, 'Selling price'),
                  _field(_mrp, 'MRP'),
                ],
              ),
            ],
          ),
          ExpansionTile(
            title: const Text('Price actions'),
            initiallyExpanded: true,
            childrenPadding: const EdgeInsets.symmetric(horizontal: 8),
            children: [
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: _readOnly
                        ? null
                        : () => _copyPriceValue(_purchasePrice, _sellingPrice),
                    icon: const Icon(Icons.copy_outlined),
                    label: const Text('Copy purchase to selling'),
                  ),
                  OutlinedButton.icon(
                    onPressed: _readOnly
                        ? null
                        : () => _copyPriceValue(_sellingPrice, _mrp),
                    icon: const Icon(Icons.copy_outlined),
                    label: const Text('Copy selling to MRP'),
                  ),
                ],
              ),
            ],
          ),
        ],
      );

  Widget _packagingSection() {
    final List<DropdownMenuItem<String>> uomItems = widget.uoms
        .map((item) => DropdownMenuItem<String>(
              value: item.id,
              child: Text('${item.name} (${item.code})'),
            ))
        .toList();
    return Wrap(
      spacing: 16,
      runSpacing: 12,
      children: [
        _uomDropdown(
          label: 'Base UOM',
          value: _baseUomId,
          items: uomItems,
          onChanged: (value) => setState(() => _baseUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Inventory UOM',
          value: _inventoryUomId,
          items: uomItems,
          onChanged: (value) => setState(() => _inventoryUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Purchase UOM',
          value: _purchaseUomId,
          items: uomItems,
          onChanged: (value) => setState(() => _purchaseUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Sales UOM',
          value: _salesUomId,
          items: uomItems,
          onChanged: (value) => setState(() => _salesUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Default Receiving UOM',
          value: _defaultReceivingUomId,
          items: uomItems,
          onChanged: (value) =>
              setState(() => _defaultReceivingUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Default Dispatch UOM',
          value: _defaultDispatchUomId,
          items: uomItems,
          onChanged: (value) =>
              setState(() => _defaultDispatchUomId = value ?? ''),
        ),
        _uomDropdown(
          label: 'Minimum Sales UOM',
          value: _minimumSalesUomId,
          items: uomItems,
          onChanged: (value) =>
              setState(() => _minimumSalesUomId = value ?? ''),
        ),
        _field(_weight, 'Weight'),
        _field(_volume, 'Volume'),
        _field(_length, 'Length'),
        _field(_width, 'Width'),
        _field(_height, 'Height'),
        SizedBox(
          width: 240,
          child: SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: const Text('Allow fraction'),
            value: _allowFraction,
            onChanged: _readOnly
                ? null
                : (value) => setState(() => _allowFraction = value),
          ),
        ),
        SizedBox(
          width: 240,
          child: SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: const Text('Allow decimal'),
            value: _allowDecimal,
            onChanged: _readOnly
                ? null
                : (value) => setState(() => _allowDecimal = value),
          ),
        ),
      ],
    );
  }

  Widget _taxSection() => Wrap(
        spacing: 16,
        runSpacing: 12,
        children: [
          _field(_hsn, 'HSN / SAC'),
          SizedBox(
            width: 320,
            child: DropdownButtonFormField<String>(
              initialValue: _taxProfileId.isEmpty ? null : _taxProfileId,
              decoration: const InputDecoration(labelText: 'Tax profile'),
              items: [
                const DropdownMenuItem<String>(
                  value: '',
                  child: Text('No tax profile'),
                ),
                ..._metadata.taxProfiles.map(
                  (profile) => DropdownMenuItem<String>(
                    value: profile.id,
                    child: Text('${profile.label} (${profile.code})'),
                  ),
                ),
              ],
              onChanged: _readOnly
                  ? null
                  : (value) => setState(() => _taxProfileId = value ?? ''),
            ),
          ),
        ],
      );

  Widget _attributesSection() {
    final List<String> requiredIds = _metadata.requiredAttributeDefinitionIds;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            Chip(
              label: Text(
                  'Profile: ${_metadata.profileCode.isEmpty ? 'N/A' : _metadata.profileCode}'),
            ),
            Chip(label: Text('Required: ${requiredIds.length}')),
            Chip(
                label: Text(
                    'Optional: ${_allowedAttributeIds.length - requiredIds.length}')),
          ],
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 16,
          runSpacing: 12,
          children: _allowedAttributeIds.map((id) {
            final AttributeDefinitionRecord? definition = widget.definitions
                .cast<AttributeDefinitionRecord?>()
                .firstWhere((entry) => entry?.id == id, orElse: () => null);
            final bool required = requiredIds.contains(id);
            return _field(
              _attributeControllers[id]!,
              '${definition?.name ?? id}${required ? ' *' : ''}',
              helper: definition == null
                  ? 'Unknown attribute definition.'
                  : 'Type: ${definition.dataType}',
              width: 280,
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _mediaSection(List<Map<String, String>> rows,
          {required bool imageMode}) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              border: Border.all(color: Theme.of(context).colorScheme.outline),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              imageMode
                  ? 'Drag & drop images here (or add manually below).'
                  : 'Drag & drop attachments here (or add manually below).',
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.tonalIcon(
                onPressed: _readOnly
                    ? null
                    : () => setState(() {
                          rows.add({
                            'kind': imageMode ? 'IMAGE' : 'DOCUMENT',
                            'file': '',
                            'mime': imageMode ? 'image/png' : 'application/pdf',
                            'path': '',
                            'primary': 'false',
                          });
                          _dirty = true;
                        }),
                icon: const Icon(Icons.add),
                label: Text(imageMode ? 'Add image' : 'Add attachment'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...rows.asMap().entries.map((entry) {
            final int index = entry.key;
            final Map<String, String> row = entry.value;
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    Wrap(
                      spacing: 12,
                      runSpacing: 12,
                      children: [
                        _inlineValue(
                          label: 'File',
                          value: row['file'] ?? '',
                          onChanged: (value) => row['file'] = value,
                          readOnly: _readOnly,
                        ),
                        _inlineValue(
                          label: 'MIME',
                          value: row['mime'] ?? '',
                          onChanged: (value) => row['mime'] = value,
                          readOnly: _readOnly,
                        ),
                        _inlineValue(
                          label: 'Path',
                          value: row['path'] ?? '',
                          onChanged: (value) => row['path'] = value,
                          readOnly: _readOnly,
                          width: 360,
                        ),
                      ],
                    ),
                    Row(
                      children: [
                        Switch(
                          value: row['primary'] == 'true',
                          onChanged: _readOnly
                              ? null
                              : (value) => setState(() {
                                    row['primary'] = value ? 'true' : 'false';
                                    _dirty = true;
                                  }),
                        ),
                        const Text('Primary'),
                        const Spacer(),
                        IconButton(
                          tooltip: 'Remove',
                          onPressed: _readOnly
                              ? null
                              : () => setState(() {
                                    rows.removeAt(index);
                                    _dirty = true;
                                  }),
                          icon: const Icon(Icons.delete_outline),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }),
        ],
      );

  Widget _auditSection() {
    final Product? product = widget.product;
    return ListView(
      shrinkWrap: true,
      children: [
        ListTile(
          leading: const Icon(Icons.add_circle_outline),
          title: const Text('Created'),
          subtitle: Text(product?.createdAt ?? 'Not persisted yet'),
        ),
        ListTile(
          leading: const Icon(Icons.edit_outlined),
          title: const Text('Updated'),
          subtitle: Text(product?.updatedAt ?? 'Not persisted yet'),
        ),
        ListTile(
          leading: const Icon(Icons.delete_outline),
          title: const Text('Deleted state'),
          subtitle: Text(product?.isDeleted == true ? 'Deleted' : 'Active'),
        ),
      ],
    );
  }

  Widget _historySection() {
    final Product? product = widget.product;
    return ListView(
      shrinkWrap: true,
      children: [
        ListTile(
          title: const Text('Price changes'),
          subtitle: Text(
            product == null
                ? 'Available after first save.'
                : 'Purchase: ${product.purchasePrice}, Selling: ${product.sellingPrice}, MRP: ${product.mrp}',
          ),
        ),
        ListTile(
          title: const Text('Category changes'),
          subtitle: Text(product == null
              ? 'Available after first save.'
              : _categoryLabel(product.categoryId)),
        ),
        ListTile(
          title: const Text('Attribute changes'),
          subtitle: Text(product == null
              ? 'Available after first save.'
              : '${product.attributes.length} attribute values recorded.'),
        ),
      ],
    );
  }

  Widget _notesSection() =>
      _field(_notes, 'Internal notes', width: 760, lines: 8);

  Widget _futureInventorySection() => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Future Inventory Integration',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text(
                'This product record already exposes profile-driven dynamic attributes, media references, and core pricing/tax fields used by upcoming Inventory, Purchase, Sales, and Manufacturing modules.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      );

  String _categoryLabel(String id) {
    final ProductCategoryRecord? match =
        widget.categories.cast<ProductCategoryRecord?>().firstWhere(
              (item) => item?.id == id,
              orElse: () => null,
            );
    return match?.name ?? '';
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    bool required = false,
    bool readOnly = false,
    String? helper,
    double width = 220,
    int lines = 1,
  }) =>
      SizedBox(
        width: width,
        child: TextField(
          controller: controller,
          readOnly: _readOnly || readOnly,
          maxLines: lines,
          decoration: InputDecoration(
            labelText: required ? '$label *' : label,
            helperText: helper,
          ),
        ),
      );

  Widget _inlineValue({
    required String label,
    required String value,
    required ValueChanged<String> onChanged,
    required bool readOnly,
    double width = 220,
  }) =>
      SizedBox(
        width: width,
        child: TextFormField(
          initialValue: value,
          readOnly: readOnly,
          decoration: InputDecoration(labelText: label),
          onChanged: (next) {
            onChanged(next);
            _dirty = true;
          },
        ),
      );

  Widget _dropdown({
    required String label,
    required String value,
    required List<String> values,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 220,
        child: DropdownButtonFormField<String>(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          items: values
              .map((item) => DropdownMenuItem(value: item, child: Text(item)))
              .toList(),
          onChanged: _readOnly ? null : onChanged,
        ),
      );

  Widget _uomDropdown({
    required String label,
    required String value,
    required List<DropdownMenuItem<String>> items,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 260,
        child: DropdownButtonFormField<String>(
          initialValue: value.isEmpty ? null : value,
          decoration: InputDecoration(labelText: label),
          items: [
            const DropdownMenuItem<String>(
              value: '',
              child: Text('Not set'),
            ),
            ...items,
          ],
          onChanged: _readOnly ? null : onChanged,
        ),
      );

  void _copyPriceValue(
    TextEditingController source,
    TextEditingController target,
  ) {
    target.text = source.text.trim();
    setState(() => _dirty = true);
  }

  List<String> _validate() {
    final List<String> issues = <String>[];
    if (_code.text.trim().isEmpty) {
      issues.add('Product code is required.');
    }
    if (_name.text.trim().isEmpty) {
      issues.add('Product name is required.');
    }
    for (final String id in _metadata.requiredAttributeDefinitionIds) {
      if ((_attributeControllers[id]?.text.trim() ?? '').isEmpty) {
        issues.add('Required business attributes are missing.');
        break;
      }
    }
    if (!_barcodeEnabled && _barcode.text.trim().isNotEmpty) {
      issues.add('Barcode is disabled by the current profile feature flags.');
    }
    if (!_qrEnabled && _qrCode.text.trim().isNotEmpty) {
      issues.add('QR code is disabled by the current profile feature flags.');
    }
    final double? selling = double.tryParse(_sellingPrice.text.trim());
    final double? mrp = double.tryParse(_mrp.text.trim());
    if (selling != null && mrp != null && mrp < selling) {
      issues.add('MRP must be greater than or equal to selling price.');
    }
    return issues;
  }

  Json _payload() {
    final List<Json> attributes = _allowedAttributeIds
        .where(
            (id) => (_attributeControllers[id]?.text.trim() ?? '').isNotEmpty)
        .map(
          (id) => {
            'attribute_definition_id': id,
            'value': _attributeControllers[id]!.text.trim(),
          },
        )
        .toList();
    final List<Json> media = [
      ..._imageRows,
      ..._attachmentRows,
    ]
        .where((row) => stringValue(row['file']).isNotEmpty)
        .map(
          (row) => {
            'media_kind': stringValue(row['kind']),
            'file_name': stringValue(row['file']),
            'mime_type': stringValue(row['mime']),
            'storage_path': stringValue(row['path']),
            'is_primary': row['primary'] == 'true',
          },
        )
        .toList();
    return {
      'code': _code.text.trim(),
      'name': _name.text.trim(),
      'short_name':
          _shortName.text.trim().isEmpty ? null : _shortName.text.trim(),
      'description':
          _description.text.trim().isEmpty ? null : _description.text.trim(),
      'barcode': _barcode.text.trim().isEmpty ? null : _barcode.text.trim(),
      'qr_code': _qrCode.text.trim().isEmpty ? null : _qrCode.text.trim(),
      'product_type': _productType,
      'status': _status,
      'category_id': _categoryId.isEmpty ? null : _categoryId,
      'tax_profile_id': _taxProfileId.isEmpty ? null : _taxProfileId,
      'base_uom_id': _baseUomId.isEmpty ? null : _baseUomId,
      'inventory_uom_id': _inventoryUomId.isEmpty ? null : _inventoryUomId,
      'purchase_uom_id': _purchaseUomId.isEmpty ? null : _purchaseUomId,
      'sales_uom_id': _salesUomId.isEmpty ? null : _salesUomId,
      'default_receiving_uom_id':
          _defaultReceivingUomId.isEmpty ? null : _defaultReceivingUomId,
      'default_dispatch_uom_id':
          _defaultDispatchUomId.isEmpty ? null : _defaultDispatchUomId,
      'minimum_sales_uom_id':
          _minimumSalesUomId.isEmpty ? null : _minimumSalesUomId,
      'weight': _weight.text.trim().isEmpty ? null : _weight.text.trim(),
      'volume': _volume.text.trim().isEmpty ? null : _volume.text.trim(),
      'length': _length.text.trim().isEmpty ? null : _length.text.trim(),
      'width': _width.text.trim().isEmpty ? null : _width.text.trim(),
      'height': _height.text.trim().isEmpty ? null : _height.text.trim(),
      'allow_fraction': _allowFraction,
      'allow_decimal': _allowDecimal,
      'unit': _unit.text.trim().isEmpty ? null : _unit.text.trim(),
      'brand': _brand.text.trim().isEmpty ? null : _brand.text.trim(),
      'model': _model.text.trim().isEmpty ? null : _model.text.trim(),
      'hsn_sac': _hsn.text.trim().isEmpty ? null : _hsn.text.trim(),
      'purchase_price': _purchasePrice.text.trim().isEmpty
          ? null
          : _purchasePrice.text.trim(),
      'selling_price':
          _sellingPrice.text.trim().isEmpty ? null : _sellingPrice.text.trim(),
      'mrp': _mrp.text.trim().isEmpty ? null : _mrp.text.trim(),
      'remarks': _remarks.text.trim().isEmpty ? null : _remarks.text.trim(),
      'attributes': attributes,
      'media': media,
    };
  }

  Future<void> _saveAndNew() async {
    await _submit(closeWhenDone: false);
    if (!mounted) return;
    setState(() {
      _code.clear();
      _name.clear();
      _shortName.clear();
      _description.clear();
      _barcode.clear();
      _qrCode.clear();
      _brand.clear();
      _model.clear();
      _unit.clear();
      _hsn.clear();
      _baseUomId = '';
      _inventoryUomId = '';
      _purchaseUomId = '';
      _salesUomId = '';
      _defaultReceivingUomId = '';
      _defaultDispatchUomId = '';
      _minimumSalesUomId = '';
      _weight.clear();
      _volume.clear();
      _length.clear();
      _width.clear();
      _height.clear();
      _allowFraction = false;
      _allowDecimal = true;
      _taxProfileId = '';
      _purchasePrice.clear();
      _sellingPrice.clear();
      _mrp.clear();
      _remarks.clear();
      for (final TextEditingController controller
          in _attributeControllers.values) {
        controller.clear();
      }
      _imageRows.clear();
      _attachmentRows.clear();
      _dirty = false;
      _validationSummary = const [];
    });
  }

  Future<void> _saveAndClose() => _submit(closeWhenDone: true);

  Future<void> _submit({bool closeWhenDone = true}) async {
    if (_readOnly || _saving) return;
    final List<String> issues = _validate();
    if (issues.isNotEmpty) {
      setState(() => _validationSummary = issues);
      return;
    }
    setState(() {
      _saving = true;
      _validationSummary = const [];
    });
    try {
      final Product saved = await widget.onSave(_payload());
      _dirty = false;
      if (!mounted) return;
      if (closeWhenDone) {
        Navigator.of(context).pop(saved);
      } else {
        NotificationService.show(context, 'Product saved.');
      }
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          _validationSummary = [exception.message];
        });
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  Future<void> _close() async {
    if (_readOnly || !_dirty) {
      Navigator.of(context).pop();
      return;
    }
    final bool discard = await showWorkspaceConfirmDialog(
      context,
      title: 'Discard unsaved changes?',
      message: 'Your product edits are not saved yet.',
      confirmLabel: 'Discard changes',
      type: ConfirmationType.discardChanges,
    );
    if (discard && mounted) {
      Navigator.of(context).pop();
    }
  }
}

enum _BulkOperationKind {
  delete,
  restore,
  export,
  statusChange,
  categoryChange,
  priceUpdate,
}

class _BulkOperationResult {
  const _BulkOperationResult({
    required this.kind,
    this.status = '',
    this.categoryId = '',
    this.value = '',
    this.format = 'csv',
  });

  final _BulkOperationKind kind;
  final String status;
  final String categoryId;
  final String value;
  final String format;
}

class _BulkOperationDialog extends StatefulWidget {
  const _BulkOperationDialog({
    required this.categories,
    required this.selectedCount,
  });

  final List<ProductCategoryRecord> categories;
  final int selectedCount;

  @override
  State<_BulkOperationDialog> createState() => _BulkOperationDialogState();
}

class _BulkOperationDialogState extends State<_BulkOperationDialog> {
  _BulkOperationKind _kind = _BulkOperationKind.delete;
  String _status = 'ACTIVE';
  String _categoryId = '';
  String _priceDelta = '0.00';
  String _format = 'csv';

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Bulk operation (${widget.selectedCount} selected)'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<_BulkOperationKind>(
                initialValue: _kind,
                decoration: const InputDecoration(labelText: 'Operation'),
                items: const [
                  DropdownMenuItem(
                    value: _BulkOperationKind.delete,
                    child: Text('Bulk delete'),
                  ),
                  DropdownMenuItem(
                    value: _BulkOperationKind.restore,
                    child: Text('Bulk restore'),
                  ),
                  DropdownMenuItem(
                    value: _BulkOperationKind.export,
                    child: Text('Bulk export'),
                  ),
                  DropdownMenuItem(
                    value: _BulkOperationKind.statusChange,
                    child: Text('Bulk status change'),
                  ),
                  DropdownMenuItem(
                    value: _BulkOperationKind.categoryChange,
                    child: Text('Bulk category change'),
                  ),
                  DropdownMenuItem(
                    value: _BulkOperationKind.priceUpdate,
                    child: Text('Bulk price update'),
                  ),
                ],
                onChanged: (value) => setState(() => _kind = value ?? _kind),
              ),
              if (_kind == _BulkOperationKind.statusChange)
                DropdownButtonFormField<String>(
                  initialValue: _status,
                  decoration: const InputDecoration(labelText: 'New status'),
                  items: const ['ACTIVE', 'INACTIVE', 'DRAFT', 'ARCHIVED']
                      .map(
                        (value) => DropdownMenuItem(
                          value: value,
                          child: Text(value),
                        ),
                      )
                      .toList(),
                  onChanged: (value) =>
                      setState(() => _status = value ?? _status),
                ),
              if (_kind == _BulkOperationKind.categoryChange)
                DropdownButtonFormField<String>(
                  initialValue: _categoryId.isEmpty ? null : _categoryId,
                  decoration: const InputDecoration(labelText: 'New category'),
                  items: widget.categories
                      .map(
                        (category) => DropdownMenuItem(
                          value: category.id,
                          child: Text(category.name),
                        ),
                      )
                      .toList(),
                  onChanged: (value) =>
                      setState(() => _categoryId = value ?? ''),
                ),
              if (_kind == _BulkOperationKind.priceUpdate)
                TextFormField(
                  initialValue: _priceDelta,
                  decoration: const InputDecoration(
                    labelText: 'Price delta (+/-)',
                    helperText: 'Example: 5.00 or -10.00',
                  ),
                  onChanged: (value) => _priceDelta = value,
                ),
              if (_kind == _BulkOperationKind.export)
                DropdownButtonFormField<String>(
                  initialValue: _format,
                  decoration: const InputDecoration(labelText: 'Format'),
                  items: const [
                    DropdownMenuItem(value: 'csv', child: Text('CSV')),
                    DropdownMenuItem(value: 'xlsx', child: Text('Excel')),
                  ],
                  onChanged: (value) =>
                      setState(() => _format = value ?? _format),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
              _BulkOperationResult(
                kind: _kind,
                status: _status,
                categoryId: _categoryId,
                value: _priceDelta,
                format: _format,
              ),
            ),
            child: const Text('Run'),
          ),
        ],
      );
}

class _ColumnChooserDialog extends StatefulWidget {
  const _ColumnChooserDialog({required this.columns});

  final List<_ProductColumn> columns;

  @override
  State<_ColumnChooserDialog> createState() => _ColumnChooserDialogState();
}

class _ColumnChooserDialogState extends State<_ColumnChooserDialog> {
  late final List<_ProductColumn> _columns =
      widget.columns.map((column) => column.copyWith()).toList();

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Column chooser'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(
              children: _columns.asMap().entries.map((entry) {
                final int index = entry.key;
                final _ProductColumn column = entry.value;
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      children: [
                        CheckboxListTile(
                          title: Text(column.label),
                          value: column.visible,
                          onChanged: (value) => setState(
                            () => _columns[index] = column.copyWith(
                              visible: value ?? true,
                            ),
                          ),
                        ),
                        Row(
                          children: [
                            const Text('Width'),
                            Expanded(
                              child: Slider(
                                value: column.width.clamp(120, 360),
                                min: 120,
                                max: 360,
                                divisions: 12,
                                label: column.width.round().toString(),
                                onChanged: (value) => setState(
                                  () => _columns[index] = column.copyWith(
                                    width: value,
                                  ),
                                ),
                              ),
                            ),
                            Text('${column.width.round()}px'),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_columns),
            child: const Text('Apply'),
          ),
        ],
      );
}

class _ProductImportWizard extends StatefulWidget {
  const _ProductImportWizard({required this.onImport});

  final Future<void> Function(List<Json> records) onImport;

  @override
  State<_ProductImportWizard> createState() => _ProductImportWizardState();
}

class _ProductImportWizardState extends State<_ProductImportWizard> {
  int _step = 0;
  final TextEditingController _payload = TextEditingController();
  List<Json> _preview = const [];
  List<String> _errors = const [];
  bool _loading = false;
  int _imported = 0;

  @override
  void dispose() {
    _payload.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Product import wizard'),
        content: SizedBox(
          width: 800,
          height: 520,
          child: Stepper(
            currentStep: _step,
            controlsBuilder: (context, details) => const SizedBox.shrink(),
            steps: [
              Step(
                title: const Text('Step 1 - Choose file'),
                isActive: _step == 0,
                content: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Paste JSON records (array) generated from CSV/Excel export.',
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _payload,
                      maxLines: 10,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        hintText:
                            '[{"code":"PROD-1","name":"Item","product_type":"STOCK_ITEM","status":"ACTIVE","attributes":[],"media":[]}]',
                      ),
                    ),
                  ],
                ),
              ),
              Step(
                title: const Text('Step 2 - Preview'),
                isActive: _step == 1,
                content: SizedBox(
                  height: 170,
                  child: ListView(
                    children: _preview
                        .take(25)
                        .map((item) => ListTile(
                              dense: true,
                              title: Text(stringValue(item['code'])),
                              subtitle: Text(stringValue(item['name'])),
                            ))
                        .toList(),
                  ),
                ),
              ),
              Step(
                title: const Text('Step 3 - Validation'),
                isActive: _step == 2,
                content: _errors.isEmpty
                    ? const Text('No validation issues.')
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children:
                            _errors.map((entry) => Text('• $entry')).toList(),
                      ),
              ),
              Step(
                title: const Text('Step 4 - Import'),
                isActive: _step == 3,
                content: _loading
                    ? const CircularProgressIndicator()
                    : const Text('Ready to import records.'),
              ),
              Step(
                title: const Text('Step 5 - Summary'),
                isActive: _step == 4,
                content: Text('Imported records: $_imported'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _loading ? null : () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
          if (_step > 0 && _step < 4)
            OutlinedButton(
              onPressed: _loading ? null : () => setState(() => _step--),
              child: const Text('Back'),
            ),
          FilledButton(
            onPressed: _loading ? null : _next,
            child: Text(_step == 4 ? 'Done' : 'Next'),
          ),
        ],
      );

  Future<void> _next() async {
    if (_step == 0) {
      try {
        final dynamic decoded = jsonDecode(_payload.text);
        if (decoded is! List) {
          throw const FormatException('Payload must be an array.');
        }
        _preview = decoded
            .whereType<Map>()
            .map((entry) => Map<String, dynamic>.from(entry))
            .toList();
        if (_preview.isEmpty) {
          throw const FormatException('No records provided.');
        }
        setState(() => _step = 1);
      } on FormatException catch (error) {
        setState(() => _errors = [error.message]);
      }
      return;
    }
    if (_step == 1) {
      final List<String> issues = [];
      final Set<String> seen = {};
      for (int index = 0; index < _preview.length; index++) {
        final Json row = _preview[index];
        final String code = stringValue(row['code']);
        final String name = stringValue(row['name']);
        if (code.isEmpty || name.isEmpty) {
          issues.add('Row ${index + 1}: code and name are required.');
        }
        if (seen.contains(code)) {
          issues.add('Row ${index + 1}: duplicate code "$code".');
        }
        seen.add(code);
      }
      setState(() {
        _errors = issues;
        _step = 2;
      });
      return;
    }
    if (_step == 2) {
      if (_errors.isNotEmpty) return;
      setState(() => _step = 3);
      return;
    }
    if (_step == 3) {
      setState(() => _loading = true);
      try {
        await widget.onImport(_preview);
        if (!mounted) return;
        setState(() {
          _imported = _preview.length;
          _step = 4;
        });
      } finally {
        if (mounted) {
          setState(() => _loading = false);
        }
      }
      return;
    }
    Navigator.of(context).pop();
  }
}

enum _ExportScope { selected, filtered, all }

class _ExportScopeDialog extends StatefulWidget {
  const _ExportScopeDialog();

  @override
  State<_ExportScopeDialog> createState() => _ExportScopeDialogState();
}

class _ExportScopeDialogState extends State<_ExportScopeDialog> {
  _ExportScope _scope = _ExportScope.filtered;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Export scope'),
        content: DropdownButtonFormField<_ExportScope>(
          initialValue: _scope,
          decoration: const InputDecoration(labelText: 'Scope'),
          items: const [
            DropdownMenuItem(
              value: _ExportScope.selected,
              child: Text('Selected rows'),
            ),
            DropdownMenuItem(
              value: _ExportScope.filtered,
              child: Text('Filtered rows'),
            ),
            DropdownMenuItem(
              value: _ExportScope.all,
              child: Text('Entire dataset'),
            ),
          ],
          onChanged: (value) => setState(() => _scope = value ?? _scope),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_scope),
            child: const Text('Export'),
          ),
        ],
      );
}

String _dateOnly(String value) =>
    value.length >= 10 ? value.substring(0, 10) : value;
