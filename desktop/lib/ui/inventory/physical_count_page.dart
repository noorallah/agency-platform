import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/branch_warehouse.dart';
import '../../models/entities.dart';
import '../../models/physical_count.dart';
import '../workspace/desktop_framework.dart';
import 'physical_count_sheet_dialog.dart';

/// Counting a warehouse.
///
/// A sheet is drawn up from what the system holds, walked over hours by people
/// with a clipboard, and posted once at the end. The screen is built around
/// that: opening a sheet and posting it are separate actions, and what has been
/// counted so far is saved rather than held in the form.
class PhysicalCountPage extends StatefulWidget {
  const PhysicalCountPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<PhysicalCountPage> createState() => _PhysicalCountPageState();
}

class _PhysicalCountPageState extends State<PhysicalCountPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  List<PhysicalCountSheet> _sheets = const [];
  int _page = 1;
  int _total = 0;
  bool _loading = false;
  String? _error;

  bool get _canView => widget.permissions.hasPermission('INVENTORY_VIEW');
  bool get _canCount => widget.permissions.hasPermission('INVENTORY_ADJUST');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm || !_canView) return;
    setState(() {
      _loading = true;
      _error = null;
      if (requestedPage != null) _page = requestedPage;
    });
    try {
      final PagedResult<PhysicalCountSheet> result =
          await widget.api.physicalCounts(
        page: _page,
        pageSize: _rowsPerPage,
        search: _search.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _sheets = result.items;
        _total = result.total;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _error = exception.message;
        _sheets = const [];
        _total = 0;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openSheet() async {
    setState(() => _loading = true);
    List<BranchRecord> branches = const [];
    List<WarehouseRecord> warehouses = const [];
    try {
      final List<dynamic> results = await Future.wait<dynamic>([
        widget.api.branches(page: 1, pageSize: 100),
        widget.api.warehouses(page: 1, pageSize: 100),
      ]);
      branches = (results[0] as PagedResult<BranchRecord>).items;
      warehouses = (results[1] as PagedResult<WarehouseRecord>).items;
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
    if (!mounted) return;
    if (warehouses.isEmpty) {
      setState(() => _error = 'There is no warehouse to count yet.');
      return;
    }
    final Json? draft = await showDialog<Json>(
      context: context,
      builder: (_) => OpenCountDialog(branches: branches, warehouses: warehouses),
    );
    if (draft == null) return;
    try {
      final PhysicalCountSheet sheet = await widget.api.openPhysicalCount(draft);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${sheet.countNumber} opened over ${sheet.lines.length} lines.',
        kind: AppNotificationKind.success,
      );
      await _load(requestedPage: 1);
      if (!mounted) return;
      await _editSheet(sheet);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  Future<void> _editSheet(PhysicalCountSheet sheet) async {
    // Re-read it: the list carries what was loaded minutes ago, and somebody
    // else may have been counting the same sheet in the meantime.
    PhysicalCountSheet current = sheet;
    try {
      current = await widget.api.physicalCount(sheet.id);
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
      return;
    }
    if (!mounted) return;
    final bool? changed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PhysicalCountSheetDialog(
        api: widget.api,
        sheet: current,
        canCount: _canCount,
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!_canView) {
      return const StandardEmptyState(
        type: EmptyStateType.noPermissions,
        title: 'Physical count',
        message: 'You do not have permission to view stock.',
      );
    }
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(
        type: EmptyStateType.noFirmSelected,
        title: 'Physical count',
        message: 'Choose a firm to count its warehouses.',
      );
    }
    return LoadingOverlay(
      loading: _loading,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(children: [
            Expanded(
              child: TextField(
                controller: _search,
                decoration: const InputDecoration(
                  labelText: 'Search by count number',
                  prefixIcon: Icon(Icons.search),
                  hintText: 'PC-…',
                ),
                onSubmitted: (_) => _load(requestedPage: 1),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            if (_canCount)
              FilledButton.icon(
                onPressed: () => unawaited(_openSheet()),
                icon: const Icon(Icons.add),
                label: const Text('Open Count'),
              ),
          ]),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
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
        Expanded(
          child: _sheets.isEmpty
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'No counts yet',
                  message: 'Opening a count draws up a sheet from what the '
                      'warehouse currently holds. Posting it turns every '
                      'difference into a stock adjustment.',
                )
              : ListView.separated(
                  itemCount: _sheets.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) =>
                      _tile(context, _sheets[index]),
                ),
        ),
        WorkspacePager(
          page: _page,
          pageSize: _rowsPerPage,
          total: _total,
          onPageChanged: (next) => unawaited(_load(requestedPage: next)),
        ),
      ]),
    );
  }

  Widget _tile(BuildContext context, PhysicalCountSheet sheet) => ListTile(
        title: Text('${sheet.countNumber}  ·  ${sheet.countDate}'),
        // How much of it has been walked is what somebody managing a count
        // wants from a list of them.
        subtitle: Text(
          sheet.isPosted
              ? '${sheet.lines.length} lines · posted'
              : '${sheet.countedLines} of ${sheet.lines.length} lines counted',
        ),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          StatusBadge(label: sheet.status),
          const SizedBox(width: AppSpacing.md),
          const Icon(Icons.chevron_right),
        ]),
        onTap: () => unawaited(_editSheet(sheet)),
      );
}
