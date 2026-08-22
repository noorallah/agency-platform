import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/uom_packaging.dart';
import '../workspace/desktop_framework.dart';

enum UomManagementSection {
  uoms,
  uomGroups,
  packagingTypes,
  conversionRules,
  industryTemplates,
}

class UomManagementPage extends StatefulWidget {
  const UomManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.section,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final UomManagementSection section;

  @override
  State<UomManagementPage> createState() => _UomManagementPageState();
}

class _UomManagementPageState extends State<UomManagementPage> {
  static const int _rowsPerPage = 20;

  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  String? _selectedId;
  final TextEditingController _search = TextEditingController();

  List<UomRecord> _uoms = const [];
  List<UomGroupRecord> _groups = const [];
  List<PackagingTypeRecord> _packaging = const [];
  List<ConversionRuleRecord> _conversions = const [];
  List<IndustryTemplateRecord> _templates = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant UomManagementPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // All five sub-tabs build this same class in the same slot with no key, so
    // Flutter reuses the Element and keeps this State: `initState` does not run
    // again and the new section is never fetched. The grid then shows the new
    // section's still-empty list as "no records", which reads as data failing
    // to load — and clicking Refresh appeared to fix it because `_load` reads
    // the section that has, by then, already changed.
    if (widget.section == oldWidget.section) return;
    _resetForSection();
    _load();
  }

  /// Drop what belonged to the tab being left.
  ///
  /// Lookups and permissions are tab-agnostic and deliberately survive —
  /// re-fetching those on every sub-tab click is what keying the whole page
  /// would have cost. A search typed for Units means nothing on Packaging
  /// Types, so it goes.
  void _resetForSection() {
    _search.clear();
    _page = 1;
    _total = 0;
    _selectedId = null;
    _error = null;
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  bool get _canManageUom => widget.permissions.hasPermission('UOM_MANAGE');
  bool get _canManagePackaging =>
      widget.permissions.hasPermission('PACKAGING_MANAGE');
  bool get _canManageConversion =>
      widget.permissions.hasPermission('CONVERSION_RULE_MANAGE');

  Future<void> _load({int? requestedPage}) async {
    if (!widget.hasActiveFirm) return;
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      switch (widget.section) {
        case UomManagementSection.uoms:
          _uoms = await widget.api.uoms(includeInactive: true);
          _total = _uoms.length;
          break;
        case UomManagementSection.uomGroups:
          _groups = await widget.api.uomGroups();
          _total = _groups.length;
          break;
        case UomManagementSection.packagingTypes:
          _packaging = await widget.api.packagingTypes();
          _total = _packaging.length;
          break;
        case UomManagementSection.conversionRules:
          final PagedResult<ConversionRuleRecord> result = await widget.api
              .conversionRules(page: _page, pageSize: _rowsPerPage);
          _conversions = result.items;
          _total = result.total;
          break;
        case UomManagementSection.industryTemplates:
          _templates =
              await widget.api.industryTemplates(includeInactive: true);
          _total = _templates.length;
          break;
      }
    } on ApiException catch (exception) {
      _error = exception.message;
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: 8,
        children: [
          if (_canCreateCurrent)
            FilledButton.icon(
              onPressed: _openCreateDialog,
              icon: const Icon(Icons.add),
              label: const Text('Add'),
            ),
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: _subtitle,
        onSearch: (_) => _load(requestedPage: 1),
      ),
      primaryContent: _buildContent(),
      detailsPanel: _selectedId == null ? null : _detailsPanel(),
      statusBar:
          WorkspaceStatusBar(total: _total, selected: _selectedId != null),
    );
  }

  bool get _canCreateCurrent => switch (widget.section) {
        UomManagementSection.uoms => _canManageUom,
        UomManagementSection.uomGroups => _canManageUom,
        UomManagementSection.packagingTypes => _canManagePackaging,
        UomManagementSection.conversionRules => _canManageConversion,
        UomManagementSection.industryTemplates => _canManageUom,
      };

  String get _subtitle => switch (widget.section) {
        UomManagementSection.uoms => 'Manage units of measure.',
        UomManagementSection.uomGroups => 'Manage unit groups.',
        UomManagementSection.packagingTypes => 'Manage packaging types.',
        UomManagementSection.conversionRules => 'Manage conversion rules.',
        UomManagementSection.industryTemplates => 'Manage industry templates.',
      };

  Widget _buildContent() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
          title: 'Unable to load data', message: _error!);
    }
    return switch (widget.section) {
      UomManagementSection.uoms => _buildUomGrid(),
      UomManagementSection.uomGroups => _buildGroupGrid(),
      UomManagementSection.packagingTypes => _buildPackagingGrid(),
      UomManagementSection.conversionRules => _buildConversionGrid(),
      UomManagementSection.industryTemplates => _buildTemplateGrid(),
    };
  }

  Widget _buildUomGrid() {
    if (_uoms.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<UomRecord>(
      items: _uoms,
      total: _uoms.length,
      pageOffset: 0,
      rowsPerPage: _uoms.length > 50 ? 50 : _uoms.length,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'symbol', label: 'Symbol'),
        GridColumn(key: 'dimension', label: 'Dimension'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) =>
          [row.code, row.name, row.symbol, row.dimension, row.status],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete
      ],
      onContextAction: (action, row) {
        if (action == WorkspaceContextAction.edit) {
          _openUomDialog(existing: row);
        }
        if (action == WorkspaceContextAction.delete) _deleteUom(row);
      },
    );
  }

  Widget _buildGroupGrid() {
    if (_groups.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<UomGroupRecord>(
      items: _groups,
      total: _groups.length,
      pageOffset: 0,
      rowsPerPage: _groups.length > 50 ? 50 : _groups.length,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [row.code, row.name, row.status],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete
      ],
      onContextAction: (action, row) {
        if (action == WorkspaceContextAction.edit) {
          _openGroupDialog(existing: row);
        }
        if (action == WorkspaceContextAction.delete) _deleteGroup(row);
      },
    );
  }

  Widget _buildPackagingGrid() {
    if (_packaging.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<PackagingTypeRecord>(
      items: _packaging,
      total: _packaging.length,
      pageOffset: 0,
      rowsPerPage: _packaging.length > 50 ? 50 : _packaging.length,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [row.code, row.name, row.status],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete
      ],
      onContextAction: (action, row) {
        if (action == WorkspaceContextAction.edit) {
          _openPackagingDialog(existing: row);
        }
        if (action == WorkspaceContextAction.delete) _deletePackaging(row);
      },
    );
  }

  Widget _buildConversionGrid() {
    if (_conversions.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<ConversionRuleRecord>(
      items: _conversions,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'from_uom_id', label: 'From UOM'),
        GridColumn(key: 'to_uom_id', label: 'To UOM'),
        GridColumn(key: 'factor', label: 'Factor'),
        GridColumn(key: 'version', label: 'Version'),
        GridColumn(key: 'effective', label: 'Effective From'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.fromUomId,
        row.toUomId,
        row.conversionFactor,
        row.version.toString(),
        row.effectiveFrom,
        row.status
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (offset) =>
          _load(requestedPage: (offset ~/ _rowsPerPage) + 1),
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete
      ],
      onContextAction: (action, row) {
        if (action == WorkspaceContextAction.edit) {
          _openConversionDialog(existing: row);
        }
        if (action == WorkspaceContextAction.delete) _deleteConversion(row);
      },
    );
  }

  Widget _buildTemplateGrid() {
    if (_templates.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<IndustryTemplateRecord>(
      items: _templates,
      total: _templates.length,
      pageOffset: 0,
      rowsPerPage: _templates.length > 50 ? 50 : _templates.length,
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'industry_type', label: 'Industry'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [row.code, row.name, row.industryType, row.status],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete
      ],
      onContextAction: (action, row) {
        if (action == WorkspaceContextAction.edit) {
          _openTemplateDialog(existing: row);
        }
        if (action == WorkspaceContextAction.delete) _deleteTemplate(row);
      },
    );
  }

  Future<void> _openCreateDialog() async {
    switch (widget.section) {
      case UomManagementSection.uoms:
        await _openUomDialog();
        break;
      case UomManagementSection.uomGroups:
        await _openGroupDialog();
        break;
      case UomManagementSection.packagingTypes:
        await _openPackagingDialog();
        break;
      case UomManagementSection.conversionRules:
        await _openConversionDialog();
        break;
      case UomManagementSection.industryTemplates:
        await _openTemplateDialog();
        break;
    }
  }

  Future<void> _openUomDialog({UomRecord? existing}) async {
    final Json? payload = await _simpleDialog(
      title: existing == null ? 'Create UOM' : 'Edit UOM',
      fields: [
        _FieldSpec('code', 'Code', existing?.code ?? ''),
        _FieldSpec('name', 'Name', existing?.name ?? ''),
        _FieldSpec('symbol', 'Symbol', existing?.symbol ?? ''),
        _FieldSpec('dimension', 'Dimension', existing?.dimension ?? 'COUNT'),
        _FieldSpec('status', 'Status', existing?.status ?? 'ACTIVE'),
      ],
    );
    if (payload == null) return;
    try {
      if (existing == null) {
        await widget.api.createUom(payload);
      } else {
        await widget.api.updateUom(
          existing.id,
          payload,
          expectedVersion: preconditionFor(existing.version),
        );
      }
      if (mounted) {
        NotificationService.show(
          context,
          'UOM saved.',
          kind: AppNotificationKind.success,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          saveFailureMessage(e, 'UOM', changesKept: false),
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _openGroupDialog({UomGroupRecord? existing}) async {
    final Json? payload = await _simpleDialog(
      title: existing == null ? 'Create UOM Group' : 'Edit UOM Group',
      fields: [
        _FieldSpec('code', 'Code', existing?.code ?? ''),
        _FieldSpec('name', 'Name', existing?.name ?? ''),
        _FieldSpec('description', 'Description', existing?.description ?? ''),
        _FieldSpec('status', 'Status', existing?.status ?? 'ACTIVE'),
      ],
    );
    if (payload == null) return;
    try {
      if (existing == null) {
        await widget.api.createUomGroup(payload);
      } else {
        await widget.api.updateUomGroup(
          existing.id,
          payload,
          expectedVersion: preconditionFor(existing.version),
        );
      }
      if (mounted) {
        NotificationService.show(
          context,
          'UOM group saved.',
          kind: AppNotificationKind.success,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          saveFailureMessage(e, 'UOM group', changesKept: false),
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _openPackagingDialog({PackagingTypeRecord? existing}) async {
    final Json? payload = await _simpleDialog(
      title: existing == null ? 'Create Packaging Type' : 'Edit Packaging Type',
      fields: [
        _FieldSpec('code', 'Code', existing?.code ?? ''),
        _FieldSpec('name', 'Name', existing?.name ?? ''),
        _FieldSpec('description', 'Description', existing?.description ?? ''),
        _FieldSpec('status', 'Status', existing?.status ?? 'ACTIVE'),
      ],
    );
    if (payload == null) return;
    try {
      if (existing == null) {
        await widget.api.createPackagingType(payload);
      } else {
        await widget.api.updatePackagingType(
          existing.id,
          payload,
          expectedVersion: preconditionFor(existing.version),
        );
      }
      if (mounted) {
        NotificationService.show(
          context,
          'Packaging type saved.',
          kind: AppNotificationKind.success,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          saveFailureMessage(e, 'packaging type', changesKept: false),
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _openConversionDialog({ConversionRuleRecord? existing}) async {
    final Json? payload = await _simpleDialog(
      title:
          existing == null ? 'Create Conversion Rule' : 'Edit Conversion Rule',
      fields: [
        _FieldSpec('from_uom_id', 'From UOM ID', existing?.fromUomId ?? ''),
        _FieldSpec('to_uom_id', 'To UOM ID', existing?.toUomId ?? ''),
        _FieldSpec(
            'conversion_factor', 'Factor', existing?.conversionFactor ?? '1'),
        _FieldSpec('version', 'Version', existing?.version.toString() ?? '1'),
        _FieldSpec(
            'effective_from',
            'Effective From (YYYY-MM-DD)',
            existing?.effectiveFrom ??
                DateTime.now().toIso8601String().substring(0, 10)),
        _FieldSpec('status', 'Status', existing?.status ?? 'ACTIVE'),
      ],
    );
    if (payload == null) return;
    try {
      if (existing == null) {
        await widget.api.createConversionRule(payload);
      } else {
        await widget.api.updateConversionRule(
          existing.id,
          payload,
          expectedVersion: preconditionFor(existing.version),
        );
      }
      if (mounted) {
        NotificationService.show(
          context,
          'Conversion rule saved.',
          kind: AppNotificationKind.success,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          saveFailureMessage(e, 'conversion rule', changesKept: false),
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _openTemplateDialog({IndustryTemplateRecord? existing}) async {
    final Json? payload = await _simpleDialog(
      title: existing == null
          ? 'Create Industry Template'
          : 'Edit Industry Template',
      fields: [
        _FieldSpec('code', 'Code', existing?.code ?? ''),
        _FieldSpec('name', 'Name', existing?.name ?? ''),
        _FieldSpec('industry_type', 'Industry Type',
            existing?.industryType ?? 'GENERIC'),
        _FieldSpec('status', 'Status', existing?.status ?? 'ACTIVE'),
      ],
      extra: {'template_payload': const <String, dynamic>{}},
    );
    if (payload == null) return;
    try {
      if (existing == null) {
        await widget.api.createIndustryTemplate(payload);
      } else {
        await widget.api.updateIndustryTemplate(existing.id, payload);
      }
      if (mounted) {
        NotificationService.show(
          context,
          'Industry template saved.',
          kind: AppNotificationKind.success,
        );
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _deleteUom(UomRecord row) async {
    try {
      await widget.api.deleteUom(row.id);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _deleteGroup(UomGroupRecord row) async {
    try {
      await widget.api.deleteUomGroup(row.id);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _deletePackaging(PackagingTypeRecord row) async {
    try {
      await widget.api.deletePackagingType(row.id);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _deleteConversion(ConversionRuleRecord row) async {
    try {
      await widget.api.deleteConversionRule(row.id);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _deleteTemplate(IndustryTemplateRecord row) async {
    try {
      await widget.api.deleteIndustryTemplate(row.id);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        NotificationService.show(
          context,
          e.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Widget _detailsPanel() {
    final List<DetailLine> lines = switch (widget.section) {
      UomManagementSection.uoms => _uoms
          .where((row) => row.id == _selectedId)
          .map((row) => [
                DetailLine('Code', row.code),
                DetailLine('Name', row.name),
                DetailLine('Symbol', row.symbol),
                DetailLine('Dimension', row.dimension),
                DetailLine('Status', row.status),
              ])
          .cast<List<DetailLine>>()
          .firstWhere((_) => true, orElse: () => const []),
      UomManagementSection.uomGroups => _groups
          .where((row) => row.id == _selectedId)
          .map((row) => [
                DetailLine('Code', row.code),
                DetailLine('Name', row.name),
                DetailLine('Status', row.status),
              ])
          .cast<List<DetailLine>>()
          .firstWhere((_) => true, orElse: () => const []),
      UomManagementSection.packagingTypes => _packaging
          .where((row) => row.id == _selectedId)
          .map((row) => [
                DetailLine('Code', row.code),
                DetailLine('Name', row.name),
                DetailLine('Status', row.status),
              ])
          .cast<List<DetailLine>>()
          .firstWhere((_) => true, orElse: () => const []),
      UomManagementSection.conversionRules => _conversions
          .where((row) => row.id == _selectedId)
          .map((row) => [
                DetailLine('From UOM', row.fromUomId),
                DetailLine('To UOM', row.toUomId),
                DetailLine('Factor', row.conversionFactor),
                DetailLine('Version', row.version.toString()),
                DetailLine('Status', row.status),
              ])
          .cast<List<DetailLine>>()
          .firstWhere((_) => true, orElse: () => const []),
      UomManagementSection.industryTemplates => _templates
          .where((row) => row.id == _selectedId)
          .map((row) => [
                DetailLine('Code', row.code),
                DetailLine('Name', row.name),
                DetailLine('Industry', row.industryType),
                DetailLine('Status', row.status),
              ])
          .cast<List<DetailLine>>()
          .firstWhere((_) => true, orElse: () => const []),
    };
    return DetailsPanel(title: 'Details', lines: lines);
  }

  Future<Json?> _simpleDialog({
    required String title,
    required List<_FieldSpec> fields,
    Json extra = const {},
  }) async {
    final List<TextEditingController> controllers = [
      for (final _FieldSpec field in fields)
        TextEditingController(text: field.initialValue),
    ];
    final Json? result = await showDialog<Json>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              children: [
                for (int i = 0; i < fields.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: TextField(
                      controller: controllers[i],
                      decoration: InputDecoration(labelText: fields[i].label),
                    ),
                  ),
              ],
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
              final Json payload = {...extra};
              for (int i = 0; i < fields.length; i++) {
                final String raw = controllers[i].text.trim();
                if (raw.isEmpty) continue;
                payload[fields[i].key] = _coerce(raw);
              }
              Navigator.pop(context, payload);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    for (final TextEditingController c in controllers) {
      c.dispose();
    }
    return result;
  }

  dynamic _coerce(String value) {
    if (value == 'true' || value == 'false') return value == 'true';
    final int? asInt = int.tryParse(value);
    if (asInt != null) return asInt;
    final double? asDouble = double.tryParse(value);
    if (asDouble != null) return asDouble;
    return value;
  }
}

class _FieldSpec {
  const _FieldSpec(this.key, this.label, this.initialValue);

  final String key;
  final String label;
  final String initialValue;
}
