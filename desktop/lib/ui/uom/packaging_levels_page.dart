import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/product.dart';
import '../../models/uom_packaging.dart';
import '../workspace/desktop_framework.dart';

/// A product's physical packaging hierarchy, and what a scanned code is.
///
/// The four endpoints behind this screen have existed since the UOM module was
/// written and nothing called them, so no firm could record a packaging level
/// at all — and the barcodes those levels carry are the reason the table
/// exists. Until `GET /barcode-lookup` there was also nothing that read them,
/// which is why the scan box is on this screen rather than somewhere else: it
/// is the proof that what was typed here is worth typing.
///
/// Levels are per product, so the screen opens on a product picker rather than
/// a list of every level in the firm — a firm with four thousand products has
/// no use for one grid of all their cartons.
class PackagingLevelsPage extends StatefulWidget {
  const PackagingLevelsPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PackagingLevelsPage> createState() => _PackagingLevelsPageState();
}

class _PackagingLevelsPageState extends State<PackagingLevelsPage> {
  final TextEditingController _scan = TextEditingController();

  List<Product> _products = const [];
  List<UomRecord> _uoms = const [];
  List<PackagingLevelRecord> _levels = const [];
  Product? _product;
  BarcodeLookup? _scanned;
  String? _scanError;
  String? _error;
  bool _loading = true;
  bool _loadingLevels = false;
  String? _selectedId;

  bool get _mayManage => widget.permissions.hasPermission('PACKAGING_MANAGE');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _scan.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!widget.hasActiveFirm) {
      setState(() => _loading = false);
      return;
    }
    try {
      // Every product, because the picker has to offer all of them. Paged
      // through rather than asked for in one over-cap page, which two screens
      // shipped doing and every real backend refused with a 500.
      final List<Product> products = await fetchAllPages<Product>(
        (page) => widget.api.products(page: page),
      );
      // `uoms` is not paginated -- the unit list is small and the API returns
      // it whole.
      final List<UomRecord> uoms = await widget.api.uoms();
      if (!mounted) return;
      setState(() {
        _products = products;
        _uoms = uoms;
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

  Future<void> _chooseProduct(Product? product) async {
    setState(() {
      _product = product;
      // Cleared before the read, and the grid stays empty until it succeeds:
      // a failed load must not leave the previous product's levels on screen
      // beside a different product's name.
      _levels = const [];
      _selectedId = null;
      _loadingLevels = product != null;
      _error = null;
    });
    if (product == null) return;
    await _reloadLevels();
  }

  Future<void> _reloadLevels() async {
    final Product? product = _product;
    if (product == null) return;
    try {
      final List<PackagingLevelRecord> rows =
          await widget.api.packagingLevels(product.id);
      if (!mounted) return;
      setState(() {
        _levels = rows;
        _loadingLevels = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loadingLevels = false;
      });
    }
  }

  Future<void> _lookup() async {
    final String code = _scan.text.trim();
    if (code.isEmpty) return;
    setState(() {
      _scanned = null;
      _scanError = null;
    });
    try {
      final BarcodeLookup found = await widget.api.lookupBarcode(code);
      if (!mounted) return;
      setState(() => _scanned = found);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server's sentence is the useful one — it names the code, or says
      // how many things carry it — so it is shown rather than replaced.
      setState(() => _scanError = error.message);
    }
  }

  Future<void> _edit({PackagingLevelRecord? level}) async {
    final Product? product = _product;
    if (product == null) return;
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => _PackagingLevelDialog(
        api: widget.api,
        product: product,
        uoms: _uoms,
        levels: _levels,
        level: level,
      ),
    );
    if (saved == true) await _reloadLevels();
  }

  Future<void> _delete(PackagingLevelRecord level) async {
    final Product? product = _product;
    if (product == null) return;
    try {
      await widget.api.deletePackagingLevel(product.id, level.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${level.levelName} removed. Any code printed on it stops resolving.',
        kind: AppNotificationKind.success,
      );
      await _reloadLevels();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  String _uomLabel(String id) {
    for (final UomRecord unit in _uoms) {
      if (unit.id == id) return unit.code;
    }
    return '';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Packaging is recorded per firm, per product.',
      );
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: 8,
        children: [
          if (_mayManage)
            FilledButton.icon(
              onPressed: _product == null ? null : () => _edit(),
              icon: const Icon(Icons.add),
              label: const Text('Add level'),
            ),
          OutlinedButton.icon(
            onPressed: _product == null ? null : _reloadLevels,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: _scanBox(),
      primaryContent: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _picker(),
                const SizedBox(height: AppSpacing.md),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: Text(
                      _error!,
                      style:
                          TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ),
                Expanded(child: _grid()),
              ],
            ),
      statusBar: WorkspaceStatusBar(
        total: _levels.length,
        selected: _selectedId != null,
      ),
    );
  }

  Widget _picker() => DropdownButtonFormField<String>(
        initialValue: _product?.id,
        decoration: const InputDecoration(
          labelText: 'Product',
          helperText: 'Packaging is recorded per product.',
        ),
        items: [
          for (final Product item in _products)
            DropdownMenuItem(
              value: item.id,
              child: Text('${item.code} — ${item.name}',
                  overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: (value) => _chooseProduct(
          _products.where((item) => item.id == value).firstOrNull,
        ),
      );

  Widget _scanBox() => Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _scan,
                    decoration: const InputDecoration(
                      labelText: 'Scan or type a code',
                      helperText:
                          'Any level of any product in this firm, or a '
                          "product's own barcode.",
                      isDense: true,
                    ),
                    onSubmitted: (_) => _lookup(),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                FilledButton.tonalIcon(
                  onPressed: _lookup,
                  icon: const Icon(Icons.qr_code_scanner, size: 18),
                  label: const Text('Look up'),
                ),
              ]),
              if (_scanned != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(
                    '${_scanned!.code} is '
                    '${_scanned!.productCode} ${_scanned!.productName}'
                    '${_scanned!.levelName.isEmpty ? '' : ' (${_scanned!.levelName})'}'
                    ' — one scan is ${_scanned!.baseQuantity} base units.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              if (_scanError != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(
                    _scanError!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
            ],
          ),
        ),
      );

  Widget _grid() {
    if (_product == null) {
      return const WorkspaceEmptyState(
        title: 'Choose a product',
        message: 'Its packaging levels and their codes appear here.',
      );
    }
    if (_loadingLevels) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_levels.isEmpty) {
      return WorkspaceEmptyState(
        title: '${_product!.code} has no packaging levels',
        message: 'Add one to record what it ships in and the code printed '
            'on it.',
      );
    }
    return EnterpriseDataGrid<PackagingLevelRecord>(
      items: _levels,
      total: _levels.length,
      pageOffset: 0,
      rowsPerPage: _levels.length,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'level', label: 'Level'),
        GridColumn(key: 'factor', label: 'Base units'),
        GridColumn(key: 'uom', label: 'Unit'),
        GridColumn(key: 'barcode', label: 'Barcode'),
        GridColumn(key: 'codes', label: 'GTIN / EAN / UPC'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.levelName,
        row.conversionToBaseFactor,
        _uomLabel(row.uomId),
        row.barcode,
        [row.gtin, row.ean, row.upc]
            .where((value) => value.isNotEmpty)
            .join(' / '),
        row.status,
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete,
      ],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) _edit(level: row);
        if (action == WorkspaceContextAction.delete) _delete(row);
      },
    );
  }
}

/// Add or change one rung of the hierarchy.
class _PackagingLevelDialog extends StatefulWidget {
  const _PackagingLevelDialog({
    required this.api,
    required this.product,
    required this.uoms,
    required this.levels,
    this.level,
  });

  final ApiClient api;
  final Product product;
  final List<UomRecord> uoms;
  final List<PackagingLevelRecord> levels;
  final PackagingLevelRecord? level;

  @override
  State<_PackagingLevelDialog> createState() => _PackagingLevelDialogState();
}

class _PackagingLevelDialogState extends State<_PackagingLevelDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  late final TextEditingController _name =
      TextEditingController(text: widget.level?.levelName ?? '');
  late final TextEditingController _factor = TextEditingController(
      text: widget.level?.conversionToBaseFactor ?? '1');
  late final TextEditingController _barcode =
      TextEditingController(text: widget.level?.barcode ?? '');
  late final TextEditingController _gtin =
      TextEditingController(text: widget.level?.gtin ?? '');
  late final TextEditingController _ean =
      TextEditingController(text: widget.level?.ean ?? '');
  late final TextEditingController _upc =
      TextEditingController(text: widget.level?.upc ?? '');
  late String? _uomId = widget.level?.uomId.isEmpty ?? true
      ? null
      : widget.level!.uomId;
  late String? _parentId = widget.level?.parentLevelId.isEmpty ?? true
      ? null
      : widget.level!.parentLevelId;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    for (final TextEditingController controller in [
      _name,
      _factor,
      _barcode,
      _gtin,
      _ean,
      _upc,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Json _payload() => <String, dynamic>{
        'level_name': _name.text.trim(),
        'conversion_to_base_factor': _factor.text.trim(),
        if (_uomId != null) 'uom_id': _uomId,
        if (_parentId != null) 'parent_level_id': _parentId,
        // Sent as null rather than omitted, so clearing a code clears it.
        'barcode': _barcode.text.trim().isEmpty ? null : _barcode.text.trim(),
        'gtin': _gtin.text.trim().isEmpty ? null : _gtin.text.trim(),
        'ean': _ean.text.trim().isEmpty ? null : _ean.text.trim(),
        'upc': _upc.text.trim().isEmpty ? null : _upc.text.trim(),
      };

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      if (widget.level == null) {
        await widget.api.createPackagingLevel(widget.product.id, _payload());
      } else {
        await widget.api.updatePackagingLevel(
          widget.product.id,
          widget.level!.id,
          _payload(),
          expectedVersion: widget.level!.version,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // A level cannot be its own parent, and the list is the other rungs of
    // this product's hierarchy.
    final List<PackagingLevelRecord> parents = widget.levels
        .where((row) => row.id != widget.level?.id)
        .toList();
    return AlertDialog(
      title: Text(widget.level == null
          ? 'Add a packaging level'
          : 'Edit ${widget.level!.levelName}'),
      content: SizedBox(
        width: 520,
        child: Form(
          key: _form,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _name,
                  decoration: const InputDecoration(
                    labelText: 'Level name',
                    hintText: 'BOX, CARTON, PALLET',
                  ),
                  validator: (value) => (value ?? '').trim().isEmpty
                      ? 'Name the level.'
                      : null,
                ),
                TextFormField(
                  controller: _factor,
                  decoration: const InputDecoration(
                    labelText: 'Base units',
                    helperText: 'How many base units one of these holds.',
                  ),
                  keyboardType: TextInputType.number,
                  validator: (value) {
                    final double? parsed = double.tryParse((value ?? '').trim());
                    if (parsed == null) return 'Enter a number.';
                    // A level holding nothing cannot be scanned into a
                    // quantity, which is the whole purpose of recording it.
                    if (parsed <= 0) return 'Must be more than nothing.';
                    return null;
                  },
                ),
                DropdownButtonFormField<String>(
                  initialValue: _uomId,
                  decoration: const InputDecoration(labelText: 'Unit'),
                  items: [
                    for (final UomRecord unit in widget.uoms)
                      DropdownMenuItem(
                        value: unit.id,
                        child: Text('${unit.code} — ${unit.name}',
                            overflow: TextOverflow.ellipsis),
                      ),
                  ],
                  onChanged: (value) => setState(() => _uomId = value),
                ),
                DropdownButtonFormField<String>(
                  initialValue: _parentId,
                  decoration: const InputDecoration(
                    labelText: 'Sits inside',
                    helperText: 'Leave empty for the outermost level.',
                  ),
                  items: [
                    for (final PackagingLevelRecord row in parents)
                      DropdownMenuItem(
                        value: row.id,
                        child: Text(row.levelName),
                      ),
                  ],
                  onChanged: (value) => setState(() => _parentId = value),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextFormField(
                  controller: _barcode,
                  decoration: const InputDecoration(
                    labelText: 'Barcode',
                    helperText: 'What a scanner reads off this packaging.',
                  ),
                ),
                TextFormField(
                  controller: _gtin,
                  decoration: const InputDecoration(labelText: 'GTIN'),
                ),
                TextFormField(
                  controller: _ean,
                  decoration: const InputDecoration(labelText: 'EAN'),
                ),
                TextFormField(
                  controller: _upc,
                  decoration: const InputDecoration(labelText: 'UPC'),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.md),
                    child: Text(
                      _error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
