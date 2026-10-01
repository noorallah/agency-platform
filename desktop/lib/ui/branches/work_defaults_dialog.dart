import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../models/branch_warehouse.dart';
import '../workspace/paged_fetch.dart';
import '../workspace/save_in_dialog.dart';

/// "My Branch and Warehouse": the branch and warehouse a person usually works
/// from, which every new document opens with (backlog 44).
///
/// It only fills a blank -- the document's own value, when it continues one,
/// comes first, and every branch and warehouse stays selectable. Any member of
/// the firm may set their own; nothing here is a permission.
class WorkDefaultsDialog extends StatefulWidget {
  const WorkDefaultsDialog({super.key, required this.api});

  final ApiClient api;

  @override
  State<WorkDefaultsDialog> createState() => _WorkDefaultsDialogState();
}

class _WorkDefaultsDialogState extends State<WorkDefaultsDialog>
    with SaveInDialog<WorkDefaultsDialog> {
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];
  List<String> _ignored = const [];
  String? _branchId;
  String? _warehouseId;
  bool _loading = true;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final List<BranchRecord> branches = await fetchAllPages<BranchRecord>(
        (int page) => widget.api.branches(page: page, pageSize: maxApiPageSize),
      );
      final List<WarehouseRecord> warehouses =
          await fetchAllPages<WarehouseRecord>(
        (int page) =>
            widget.api.warehouses(page: page, pageSize: maxApiPageSize),
      );
      final WorkDefaults mine = await widget.api.myWorkDefaults();
      if (!mounted) return;
      setState(() {
        _branches = branches.where((b) => !b.isDeleted).toList();
        _warehouses = warehouses.where((w) => !w.isDeleted).toList();
        _branchId = mine.branchId;
        _warehouseId = mine.warehouseId;
        _ignored = mine.ignored;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  /// The warehouses on offer: those of the chosen branch, or all of them
  /// while no branch is chosen.
  List<WarehouseRecord> get _offered => _branchId == null
      ? _warehouses
      : _warehouses.where((w) => w.branchId == _branchId).toList();

  Future<void> _save({required bool clear}) =>
      saveAndClose<WorkDefaults>(() async {
        final WorkDefaults saved = await widget.api.setMyWorkDefaults(
          branchId: clear ? null : _branchId,
          warehouseId: clear ? null : _warehouseId,
        );
        UserWorkDefaults.set(saved);
        return saved;
      });

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<WarehouseRecord> offered = _offered;
    final String? warehouseValue =
        offered.any((w) => w.id == _warehouseId) ? _warehouseId : null;
    final String? branchValue =
        _branches.any((b) => b.id == _branchId) ? _branchId : null;
    return AlertDialog(
      icon: const Icon(Icons.warehouse_outlined),
      title: const Text('My branch and warehouse'),
      content: SizedBox(
        width: 460,
        child: _loading
            ? const Padding(
                padding: EdgeInsets.all(AppSpacing.xl),
                child: Center(child: CircularProgressIndicator()),
              )
            : Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  saveErrorBanner(),
                  if (_loadError != null)
                    Text(_loadError!,
                        style: TextStyle(color: theme.colorScheme.error)),
                  Text(
                    'New documents open with these. A document that continues '
                    'another keeps that one\'s branch and warehouse, and you '
                    'can always pick a different one.',
                    style: theme.textTheme.bodySmall,
                  ),
                  for (final String message in _ignored) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.info_outline,
                            size: 16,
                            color: theme.colorScheme.onSurfaceVariant),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: Text(message,
                              style: theme.textTheme.bodySmall),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: AppSpacing.lg),
                  DropdownButtonFormField<String?>(
                    key: const ValueKey<String>('work-defaults-branch'),
                    isExpanded: true,
                    initialValue: branchValue,
                    decoration: const InputDecoration(labelText: 'Branch'),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('No usual branch'),
                      ),
                      for (final BranchRecord branch in _branches)
                        DropdownMenuItem<String?>(
                          value: branch.id,
                          child: Text(
                            branch.displayName.isEmpty
                                ? branch.name
                                : branch.displayName,
                          ),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (String? value) => setState(() {
                              _branchId = value;
                              if (!_offered.any((w) => w.id == _warehouseId)) {
                                _warehouseId = null;
                              }
                            }),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  DropdownButtonFormField<String?>(
                    key: ValueKey<String>('work-defaults-warehouse-$branchValue'),
                    isExpanded: true,
                    initialValue: warehouseValue,
                    decoration: const InputDecoration(labelText: 'Warehouse'),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('No usual warehouse'),
                      ),
                      for (final WarehouseRecord warehouse in offered)
                        DropdownMenuItem<String?>(
                          value: warehouse.id,
                          child: Text(
                            warehouse.displayName.isEmpty
                                ? warehouse.name
                                : warehouse.displayName,
                          ),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (String? value) =>
                            setState(() => _warehouseId = value),
                  ),
                ],
              ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        TextButton(
          key: const ValueKey<String>('work-defaults-clear'),
          onPressed:
              saving || _loading || _loadError != null
                  ? null
                  : () => _save(clear: true),
          child: const Text('Clear'),
        ),
        FilledButton(
          key: const ValueKey<String>('work-defaults-save'),
          onPressed:
              saving || _loading || _loadError != null
                  ? null
                  : () => _save(clear: false),
          child: const Text('Save'),
        ),
      ],
    );
  }
}
