import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart' show Json;
import '../../models/kit.dart';
import '../../models/product.dart';
import '../inventory/repack_dialog.dart' show RepackOption;
import '../workspace/save_in_dialog.dart';

/// What the kit screens call (STK-15): read and replace a kit's components,
/// list the products a component may be, and make kits up or break them back.
class KitActions {
  const KitActions({
    required this.load,
    required this.replace,
    required this.products,
    required this.assemble,
    required this.disassemble,
  });

  factory KitActions.of(ApiClient api) => KitActions(
        load: api.kitComponents,
        replace: api.replaceKitComponents,
        products: () => fetchAllProducts(api),
        assemble: api.assembleKits,
        disassemble: api.disassembleKits,
      );

  final Future<List<KitComponent>> Function(String productId) load;
  final Future<List<KitComponent>> Function(String productId, Json body)
      replace;

  /// Every product, for the component picker.
  final Future<List<Product>> Function() products;
  final Future<dynamic> Function(String productId, Json body) assemble;
  final Future<dynamic> Function(String productId, Json body) disassemble;
}

/// All of the firm's products, a page at a time.
Future<List<Product>> fetchAllProducts(ApiClient api) async {
  final List<Product> all = <Product>[];
  for (int page = 1; page <= 50; page++) {
    final result = await api.products(page: page, pageSize: 100);
    all.addAll(result.items);
    if (result.items.isEmpty || all.length >= result.total) break;
  }
  return all;
}

class _ComponentDraft {
  _ComponentDraft({this.productId, String quantity = ''})
      : quantity = TextEditingController(text: quantity);

  String? productId;
  final TextEditingController quantity;
}

/// The "Components" section of a kit's product record: a table of component
/// product and quantity per kit, with add, remove and Save. Saving replaces
/// the whole list, and the server's refusal stays on the section.
class KitComponentsSection extends StatefulWidget {
  const KitComponentsSection({
    super.key,
    required this.productId,
    required this.actions,
    required this.canManage,
  });

  final String productId;
  final KitActions actions;
  final bool canManage;

  @override
  State<KitComponentsSection> createState() => _KitComponentsSectionState();
}

class _KitComponentsSectionState extends State<KitComponentsSection> {
  final List<_ComponentDraft> _rows = [];
  final Map<String, String> _labels = {};
  bool _loaded = false;
  bool _saving = false;
  String? _error;
  String? _notice;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    for (final _ComponentDraft row in _rows) {
      row.quantity.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final List<KitComponent> saved =
          await widget.actions.load(widget.productId);
      List<Product> products = const [];
      try {
        products = await widget.actions.products();
      } on ApiException {
        // The picker keeps the saved components; adding needs the list.
      }
      if (!mounted) return;
      setState(() {
        for (final Product product in products) {
          if (product.productType != 'BUNDLE' &&
              product.id != widget.productId) {
            _labels[product.id] = '${product.code} - ${product.name}';
          }
        }
        for (final KitComponent component in saved) {
          _labels.putIfAbsent(component.componentProductId, () => component.label);
          _rows.add(_ComponentDraft(
            productId: component.componentProductId,
            quantity: component.quantity,
          ));
        }
        _loaded = true;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  Future<void> _save() async {
    for (final _ComponentDraft row in _rows) {
      final double? quantity = double.tryParse(row.quantity.text.trim());
      if (row.productId == null || quantity == null || quantity <= 0) {
        setState(() {
          _notice = null;
          _error = 'Choose a product and a quantity above zero on every row.';
        });
        return;
      }
    }
    setState(() {
      _saving = true;
      _error = null;
      _notice = null;
    });
    try {
      await widget.actions.replace(widget.productId, <String, dynamic>{
        'components': [
          for (final _ComponentDraft row in _rows)
            <String, dynamic>{
              'component_product_id': row.productId,
              'quantity': row.quantity.text.trim(),
            },
        ],
      });
      if (!mounted) return;
      setState(() {
        _saving = false;
        _notice = 'Components saved.';
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = exception.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    if (!_loaded && _error == null) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: LinearProgressIndicator(),
      );
    }
    return Column(
      key: const ValueKey('kit-components'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'What goes into one kit. A dispatch makes up any shortfall of kits '
          'from these automatically.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        for (int index = 0; index < _rows.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('kit-component-product-$index'),
                    isExpanded: true,
                    initialValue: _rows[index].productId,
                    decoration:
                        const InputDecoration(labelText: 'Component product'),
                    items: [
                      for (final MapEntry<String, String> option
                          in _labels.entries)
                        DropdownMenuItem(
                          value: option.key,
                          child:
                              Text(option.value, overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: widget.canManage && !_saving
                        ? (value) =>
                            setState(() => _rows[index].productId = value)
                        : null,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                SizedBox(
                  width: 140,
                  child: TextField(
                    key: ValueKey('kit-component-quantity-$index'),
                    controller: _rows[index].quantity,
                    enabled: widget.canManage && !_saving,
                    decoration:
                        const InputDecoration(labelText: 'Quantity per kit'),
                    keyboardType: TextInputType.number,
                  ),
                ),
                if (widget.canManage)
                  IconButton(
                    key: ValueKey('kit-component-remove-$index'),
                    tooltip: 'Remove component',
                    onPressed: _saving
                        ? null
                        : () => setState(
                              () => _rows.removeAt(index).quantity.dispose(),
                            ),
                    icon: const Icon(Icons.close),
                  ),
              ],
            ),
          ),
        if (_rows.isEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(
              'No components yet.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(_error!, style: TextStyle(color: colors.error)),
          ),
        if (_notice != null)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(_notice!),
          ),
        if (widget.canManage)
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              OutlinedButton.icon(
                key: const ValueKey('kit-component-add'),
                onPressed: _saving || !_loaded
                    ? null
                    : () => setState(() => _rows.add(_ComponentDraft())),
                icon: const Icon(Icons.add),
                label: const Text('Add component'),
              ),
              FilledButton(
                key: const ValueKey('kit-components-save'),
                onPressed: _saving || !_loaded ? null : _save,
                child: Text(_saving ? 'Saving…' : 'Save components'),
              ),
            ],
          ),
      ],
    );
  }
}

/// Make kits up from their components, or break them back (STK-15). One
/// dialog for both; [onSave] runs the call and a refusal, which names the
/// component that is short, stays on the dialog (D-DLG-1).
///
/// A kit kept in batches is assembled into a batch, and a part kept in
/// batches goes back into one when a kit is broken. The server asks for
/// both by name, so the dialog has a box for each (D-UI-85): without them
/// the refusal asked for something the screen could not give.
class KitStockDialog extends StatefulWidget {
  const KitStockDialog({
    super.key,
    required this.kitName,
    required this.assemble,
    required this.branches,
    required this.warehouses,
    required this.onSave,
    this.kitTracksBatch = false,
    this.kitTracksExpiry = false,
    this.batchParts = const [],
  });

  final String kitName;

  /// The kit itself is kept in batches (and its batches are dated).
  final bool kitTracksBatch;
  final bool kitTracksExpiry;

  /// The components kept in batches, each offered a batch box on a break.
  final List<KitComponent> batchParts;

  /// True to assemble, false to disassemble.
  final bool assemble;
  final List<RepackOption> branches;
  final List<RepackOption> warehouses;
  final Future<dynamic> Function(Json body) onSave;

  @override
  State<KitStockDialog> createState() => _KitStockDialogState();
}

class _KitStockDialogState extends State<KitStockDialog> with SaveInDialog {
  final TextEditingController _quantity = TextEditingController();
  final TextEditingController _remarks = TextEditingController();
  final TextEditingController _batch = TextEditingController();
  final TextEditingController _expiry = TextEditingController();
  late final List<TextEditingController> _partBatches = [
    for (int i = 0; i < widget.batchParts.length; i++) TextEditingController(),
  ];
  DateTime _when = DateTime.now();
  String? _branchId;
  String? _warehouseId;
  String? _problem;

  @override
  void initState() {
    super.initState();
    if (widget.branches.length == 1) _branchId = widget.branches.first.id;
    _keepWarehouseInBranch();
  }

  @override
  void dispose() {
    _quantity.dispose();
    _remarks.dispose();
    _batch.dispose();
    _expiry.dispose();
    for (final TextEditingController box in _partBatches) {
      box.dispose();
    }
    super.dispose();
  }

  List<RepackOption> get _warehousesHere => [
        for (final RepackOption warehouse in widget.warehouses)
          if (_branchId == null ||
              warehouse.parentId == null ||
              warehouse.parentId == _branchId)
            warehouse,
      ];

  void _keepWarehouseInBranch() {
    final List<RepackOption> here = _warehousesHere;
    if (!here.any((warehouse) => warehouse.id == _warehouseId)) {
      _warehouseId = here.length == 1 ? here.first.id : null;
    }
  }

  bool get _kitBatch => widget.assemble && widget.kitTracksBatch;

  Future<void> _save() async {
    final double? quantity = double.tryParse(_quantity.text.trim());
    final String expiry = _expiry.text.trim();
    final String? problem = _branchId == null
        ? 'Choose the branch.'
        : _warehouseId == null
            ? 'Choose the warehouse.'
            : quantity == null || quantity <= 0
                ? 'Enter a quantity above zero.'
                : _kitBatch &&
                        expiry.isNotEmpty &&
                        (expiry.length != 10 ||
                            DateTime.tryParse(expiry) == null)
                    ? 'Enter the expiry date as YYYY-MM-DD.'
                    : null;
    setState(() {
      _problem = problem;
      saveError = null;
    });
    if (problem != null) return;
    final Json body = <String, dynamic>{
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'quantity': _quantity.text.trim(),
      'on': _when.toIso8601String().substring(0, 10),
      'remarks': _remarks.text.trim().isEmpty ? null : _remarks.text.trim(),
      if (_kitBatch && _batch.text.trim().isNotEmpty)
        'batch_number': _batch.text.trim(),
      if (_kitBatch && expiry.isNotEmpty) 'expiry_date': expiry,
      // A blank box leaves the part to the batch the last assembly took
      // it from, which the server works out.
      if (!widget.assemble &&
          _partBatches.any((box) => box.text.trim().isNotEmpty))
        'part_batches': <Json>[
          for (int i = 0; i < _partBatches.length; i++)
            if (_partBatches[i].text.trim().isNotEmpty)
              <String, dynamic>{
                'product_id': widget.batchParts[i].componentProductId,
                'batch_number': _partBatches[i].text.trim(),
              },
        ],
    };
    // Closes with the repack the server posted, so the page can name it.
    await saveAndClose<dynamic>(() => widget.onSave(body));
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final String verb = widget.assemble ? 'Assemble' : 'Disassemble';
    return AlertDialog(
      title: Text('$verb kits - ${widget.kitName}'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_problem != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(_problem!, style: TextStyle(color: colors.error)),
                ),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: const ValueKey('kit-branch'),
                    isExpanded: true,
                    initialValue: _branchId,
                    decoration: const InputDecoration(labelText: 'Branch'),
                    items: [
                      for (final RepackOption branch in widget.branches)
                        DropdownMenuItem(
                          value: branch.id,
                          child: Text(branch.label,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() {
                              _branchId = value;
                              _keepWarehouseInBranch();
                            }),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('kit-warehouse-$_branchId'),
                    isExpanded: true,
                    initialValue: _warehouseId,
                    decoration: const InputDecoration(labelText: 'Warehouse'),
                    items: [
                      for (final RepackOption warehouse in _warehousesHere)
                        DropdownMenuItem(
                          value: warehouse.id,
                          child: Text(warehouse.label,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() => _warehouseId = value),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const ValueKey('kit-quantity'),
                    controller: _quantity,
                    enabled: !saving,
                    decoration: const InputDecoration(
                      labelText: 'Number of kits',
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: InkWell(
                    onTap: saving
                        ? null
                        : () async {
                            final DateTime? picked = await showDatePicker(
                              context: context,
                              initialDate: _when,
                              firstDate: DateTime(2000),
                              lastDate: DateTime(2100),
                            );
                            if (picked != null) setState(() => _when = picked);
                          },
                    child: InputDecorator(
                      decoration: const InputDecoration(
                        labelText: 'Date',
                        suffixIcon: Icon(Icons.calendar_today, size: 18),
                      ),
                      child: Text(_when.toIso8601String().substring(0, 10)),
                    ),
                  ),
                ),
              ]),
              if (_kitBatch) ...[
                const SizedBox(height: AppSpacing.md),
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    child: TextField(
                      key: const ValueKey('kit-batch'),
                      controller: _batch,
                      enabled: !saving,
                      decoration: const InputDecoration(
                        labelText: 'Batch number',
                        helperText: 'The batch the kits go into',
                      ),
                    ),
                  ),
                  if (widget.kitTracksExpiry) ...[
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: TextField(
                        key: const ValueKey('kit-expiry'),
                        controller: _expiry,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'Expiry date',
                          helperText: 'YYYY-MM-DD, for a new batch',
                        ),
                      ),
                    ),
                  ],
                ]),
              ],
              if (!widget.assemble)
                for (int i = 0; i < widget.batchParts.length; i++) ...[
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    key: ValueKey('kit-part-batch-$i'),
                    controller: _partBatches[i],
                    enabled: !saving,
                    decoration: InputDecoration(
                      labelText: 'Batch for ${widget.batchParts[i].label}',
                      helperText: 'Blank: the batch the last assembly here '
                          'took it from',
                    ),
                  ),
                ],
              const SizedBox(height: AppSpacing.md),
              TextField(
                key: const ValueKey('kit-remarks'),
                controller: _remarks,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Remarks'),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('kit-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Posting...' : verb),
        ),
      ],
    );
  }
}
