import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/physical_count.dart';
import '../workspace/desktop_framework.dart';

/// The firm's cycle-count plans (STK-6): which stock is counted, how often,
/// and whether the counter is told what the system expects.
///
/// Closes with the [PhysicalCountSheet] when a plan draws one, so the screen
/// behind it can open the sheet for counting.
class CountPlansDialog extends StatefulWidget {
  const CountPlansDialog({
    super.key,
    required this.api,
    required this.canManage,
  });

  final ApiClient api;
  final bool canManage;

  @override
  State<CountPlansDialog> createState() => _CountPlansDialogState();
}

class _CountPlansDialogState extends State<CountPlansDialog> {
  List<CountPlan> _plans = const [];
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final List<CountPlan> plans = await widget.api.countPlans();
      final PagedResult<BranchRecord> branches =
          await widget.api.branches(page: 1, pageSize: 100);
      final PagedResult<WarehouseRecord> warehouses =
          await widget.api.warehouses(page: 1, pageSize: 100);
      if (!mounted) return;
      setState(() {
        _plans = plans;
        _branches = branches.items;
        _warehouses = warehouses.items;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _warehouseName(String id) {
    final WarehouseRecord? match =
        _warehouses.where((w) => w.id == id).firstOrNull;
    return match == null ? id : match.name;
  }

  /// What the plan covers: its class, or the bin it is limited to.
  String _scope(CountPlan plan) {
    if (plan.storageNodeId.isNotEmpty) return 'One bin';
    if (plan.abcClass.isNotEmpty) return 'Class ${plan.abcClass}';
    return 'All stock';
  }

  Future<void> _edit([CountPlan? plan]) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => CountPlanEditDialog(
        api: widget.api,
        plan: plan,
        branches: _branches,
        warehouses: _warehouses,
      ),
    );
    if (saved == true) await _load();
  }

  Future<void> _draw(CountPlan plan) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PhysicalCountSheet sheet = await widget.api.drawCountPlanSheet(
        plan.id,
        countDate: DateTime.now().toIso8601String().substring(0, 10),
      );
      if (!mounted) return;
      Navigator.of(context).pop(sheet);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _loading = false;
      });
    }
  }

  Future<void> _delete(CountPlan plan) async {
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${plan.name}?',
      message: 'The plan is removed. Sheets already drawn from it stay.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    try {
      await widget.api.deleteCountPlan(plan.id);
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return WorkspaceDialog(
      title: 'Count plans',
      subtitle: 'Cycle counting: each plan says what to count and how often.',
      loading: _loading,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
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
          if (widget.canManage)
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                key: const ValueKey<String>('count-plan-add'),
                onPressed: _loading ? null : () => unawaited(_edit()),
                icon: const Icon(Icons.add),
                label: const Text('Add plan'),
              ),
            ),
          const SizedBox(height: AppSpacing.md),
          Expanded(
            child: _plans.isEmpty
                ? (_loading
                    ? const SizedBox.shrink()
                    : const StandardEmptyState(
                        type: EmptyStateType.noRecords,
                        title: 'No count plans',
                        message: 'A plan says which stock is counted and how '
                            'often, and tells you when a count is due.',
                      ))
                : SingleChildScrollView(
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: DataTable(
                        columns: const [
                          DataColumn(label: Text('Name')),
                          DataColumn(label: Text('Warehouse')),
                          DataColumn(label: Text('Covers')),
                          DataColumn(label: Text('Every'), numeric: true),
                          DataColumn(label: Text('Blind')),
                          DataColumn(label: Text('Last counted')),
                          DataColumn(label: Text('Next due')),
                          DataColumn(label: Text('')),
                        ],
                        rows: [
                          for (final CountPlan plan in _plans)
                            DataRow(
                              color: plan.isDue
                                  ? WidgetStatePropertyAll<Color>(
                                      colors.tertiaryContainer)
                                  : null,
                              cells: [
                                DataCell(Text(plan.name)),
                                DataCell(
                                    Text(_warehouseName(plan.warehouseId))),
                                DataCell(Text(_scope(plan))),
                                DataCell(Text('${plan.frequencyDays} days')),
                                DataCell(Text(plan.blind ? 'Yes' : 'No')),
                                DataCell(Text(plan.lastCountedOn.isEmpty
                                    ? 'Never'
                                    : plan.lastCountedOn)),
                                DataCell(Text(
                                  plan.isDue
                                      ? '${plan.nextDueOn} (due)'
                                      : plan.nextDueOn,
                                  style: plan.isDue
                                      ? TextStyle(
                                          fontWeight: FontWeight.w600,
                                          color: colors.onTertiaryContainer)
                                      : null,
                                )),
                                DataCell(Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (widget.canManage) ...[
                                      TextButton(
                                        key: ValueKey<String>(
                                            'count-plan-draw-${plan.id}'),
                                        onPressed: _loading
                                            ? null
                                            : () => unawaited(_draw(plan)),
                                        child: const Text('Draw sheet'),
                                      ),
                                      IconButton(
                                        tooltip: 'Edit',
                                        onPressed: _loading
                                            ? null
                                            : () => unawaited(_edit(plan)),
                                        icon: const Icon(Icons.edit_outlined,
                                            size: 18),
                                      ),
                                      IconButton(
                                        tooltip: 'Delete',
                                        onPressed: _loading
                                            ? null
                                            : () => unawaited(_delete(plan)),
                                        icon: const Icon(Icons.delete_outline,
                                            size: 18),
                                      ),
                                    ],
                                  ],
                                )),
                              ],
                            ),
                        ],
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

/// Add or edit one plan. The save runs here, so a refusal stays on screen
/// beside everything typed (D-DLG-1).
class CountPlanEditDialog extends StatefulWidget {
  const CountPlanEditDialog({
    super.key,
    required this.api,
    required this.branches,
    required this.warehouses,
    this.plan,
  });

  final ApiClient api;
  final CountPlan? plan;
  final List<BranchRecord> branches;
  final List<WarehouseRecord> warehouses;

  @override
  State<CountPlanEditDialog> createState() => _CountPlanEditDialogState();
}

class _CountPlanEditDialogState extends State<CountPlanEditDialog>
    with SaveInDialog<CountPlanEditDialog> {
  late final TextEditingController _name;
  late final TextEditingController _days;
  String _branchId = '';
  String _warehouseId = '';
  String _abcClass = '';
  String _storageNodeId = '';
  bool _blind = false;
  bool _active = true;
  List<StorageNodeRecord> _bins = const [];
  String? _formError;

  @override
  void initState() {
    super.initState();
    final CountPlan? plan = widget.plan;
    _name = TextEditingController(text: plan?.name ?? '');
    _days = TextEditingController(text: '${plan?.frequencyDays ?? 30}');
    _branchId = plan?.branchId ??
        (widget.branches.isEmpty ? '' : widget.branches.first.id);
    _warehouseId = plan?.warehouseId ??
        (widget.warehouses.isEmpty ? '' : widget.warehouses.first.id);
    _abcClass = plan?.abcClass ?? '';
    _storageNodeId = plan?.storageNodeId ?? '';
    _blind = plan?.blind ?? false;
    _active = plan?.isActive ?? true;
    unawaited(_loadBins());
  }

  @override
  void dispose() {
    _name.dispose();
    _days.dispose();
    super.dispose();
  }

  Future<void> _loadBins() async {
    if (_warehouseId.isEmpty) return;
    try {
      final List<StorageNodeRecord> bins =
          await widget.api.storageNodes(_warehouseId);
      if (!mounted) return;
      setState(() {
        _bins = bins.where((b) => b.isActive && !b.isDeleted).toList();
        if (_storageNodeId.isNotEmpty &&
            !_bins.any((b) => b.id == _storageNodeId)) {
          _storageNodeId = '';
        }
      });
    } on ApiException {
      // No bins to offer; the plan can still cover the warehouse by class.
    }
  }

  Future<void> _save() async {
    final String name = _name.text.trim();
    final int? days = int.tryParse(_days.text.trim());
    if (name.isEmpty ||
        _branchId.isEmpty ||
        _warehouseId.isEmpty ||
        days == null ||
        days < 1 ||
        days > 366) {
      setState(() => _formError =
          'Give the plan a name, a branch and warehouse, and a frequency '
          'of 1 to 366 days.');
      return;
    }
    setState(() => _formError = null);
    final Json body = <String, dynamic>{
      'name': name,
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'abc_class': _abcClass.isEmpty ? null : _abcClass,
      'storage_node_id': _storageNodeId.isEmpty ? null : _storageNodeId,
      'frequency_days': days,
      'blind': _blind,
      'is_active': _active,
    };
    final CountPlan? plan = widget.plan;
    await saveAndClose<bool>(() async {
      if (plan == null) {
        await widget.api.createCountPlan(body);
      } else {
        await widget.api.updateCountPlan(plan.id, body);
      }
      return true;
    });
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: widget.plan == null ? 'Add count plan' : 'Edit count plan',
        loading: saving,
        onSave: saving ? null : () => unawaited(_save()),
        body: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              saveErrorBanner(),
              if (_formError != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text(
                    _formError!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              TextField(
                key: const ValueKey<String>('count-plan-name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _branchId.isEmpty ? null : _branchId,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Branch'),
                    items: [
                      for (final BranchRecord branch in widget.branches)
                        DropdownMenuItem<String>(
                          value: branch.id,
                          child: Text('${branch.code} - ${branch.name}',
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (value) =>
                        setState(() => _branchId = value ?? ''),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _warehouseId.isEmpty ? null : _warehouseId,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Warehouse'),
                    items: [
                      for (final WarehouseRecord warehouse in widget.warehouses)
                        DropdownMenuItem<String>(
                          value: warehouse.id,
                          child: Text('${warehouse.code} - ${warehouse.name}',
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (value) {
                      setState(() {
                        _warehouseId = value ?? '';
                        _storageNodeId = '';
                        _bins = const [];
                      });
                      unawaited(_loadBins());
                    },
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _abcClass,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'ABC class'),
                    items: const [
                      DropdownMenuItem(value: '', child: Text('All classes')),
                      DropdownMenuItem(value: 'A', child: Text('A')),
                      DropdownMenuItem(value: 'B', child: Text('B')),
                      DropdownMenuItem(value: 'C', child: Text('C')),
                    ],
                    onChanged: (value) =>
                        setState(() => _abcClass = value ?? ''),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    key: ValueKey<String>('bin-$_warehouseId-${_bins.length}'),
                    initialValue: _storageNodeId,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Bin'),
                    items: [
                      const DropdownMenuItem(
                          value: '', child: Text('Whole warehouse')),
                      for (final StorageNodeRecord bin in _bins)
                        DropdownMenuItem<String>(
                          value: bin.id,
                          child: Text('${bin.code} - ${bin.name}',
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (value) =>
                        setState(() => _storageNodeId = value ?? ''),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              SizedBox(
                width: 220,
                child: TextField(
                  key: const ValueKey<String>('count-plan-days'),
                  controller: _days,
                  keyboardType: TextInputType.number,
                  decoration:
                      const InputDecoration(labelText: 'Count every (days)'),
                ),
              ),
              SwitchListTile(
                key: const ValueKey<String>('count-plan-blind'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Blind count'),
                subtitle: const Text(
                    'Hide the system quantity from the counter until posted.'),
                value: _blind,
                onChanged: (value) => setState(() => _blind = value),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Active'),
                value: _active,
                onChanged: (value) => setState(() => _active = value),
              ),
            ],
          ),
        ),
      );
}
