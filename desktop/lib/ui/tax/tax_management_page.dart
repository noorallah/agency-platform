import 'dart:async';

import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/tax_framework.dart';
import '../workspace/desktop_framework.dart';
import 'tax_setup_page.dart';

enum TaxManagementSection {
  systems,
  components,
  profiles,
  countryMapping,
  migrationMapping,
  rules,
  ruleConditions,
  rulePriorities,
  ruleSimulator,
  ruleHistory,
  executionLog,
  effectiveDates,
  settings,
  history,
}

class TaxManagementPage extends StatefulWidget {
  const TaxManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    required this.section,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;
  final TaxManagementSection section;

  @override
  State<TaxManagementPage> createState() => _TaxManagementPageState();
}

class _TaxManagementPageState extends State<TaxManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  List<TaxSystemRecord> _systems = const [];
  List<TaxComponentRecord> _components = const [];
  List<TaxProfileRecord> _profiles = const [];
  List<TaxCountryMappingRecord> _countryMappings = const [];
  List<TaxMigrationMappingRecord> _migrationMappings = const [];
  List<TaxRuleRecord> _rules = const [];
  List<TaxRuleConditionRecord> _ruleConditions = const [];
  List<TaxRulePriorityRecord> _rulePriorities = const [];
  List<TaxRuleRecord> _ruleHistory = const [];
  List<TaxRuleExecutionLogRecord> _executionLogs = const [];
  List<EffectiveDateRecord> _effectiveDates = const [];
  List<TaxHistoryRecord> _history = const [];
  TaxSettingsRecord? _settings;
  TaxRuleSimulationResultRecord? _simulationResult;
  /// Whether retired rows are listed. Off by default, because a list of
  /// live tax systems is what somebody configuring tax wants to see.
  bool _showRetired = false;
  TaxSystemRecord? _selectedSystem;
  TaxComponentRecord? _selectedComponent;
  TaxProfileRecord? _selectedProfile;
  TaxCountryMappingRecord? _selectedCountryMapping;
  TaxMigrationMappingRecord? _selectedMigrationMapping;
  TaxRuleRecord? _selectedRule;

  bool get _canCreate =>
      widget.hasActiveFirm && widget.permissions.hasPermission('TAX_CREATE');
  bool get _canDelete => widget.permissions.hasPermission('TAX_DELETE');

  /// Bringing a retired record back is its own authority server-side, so the
  /// screen asks the same question: offering an action that would answer 403
  /// wastes the user's time twice.
  bool get _canRestore => widget.permissions.hasPermission('TAX_RESTORE');
  bool get _canSettings =>
      widget.permissions.hasPermission('TAX_MANAGE_SETTINGS');
  bool get _canRuleCreate =>
      widget.hasActiveFirm &&
      widget.permissions.hasPermission('TAX_RULE_CREATE');
  bool get _canRuleDelete =>
      widget.permissions.hasPermission('TAX_RULE_DELETE');
  bool get _canSimulate =>
      widget.hasActiveFirm && widget.permissions.hasPermission('TAX_SIMULATE');
  String get _firstSystemId => _systems.isEmpty ? '' : _systems.first.id;
  String get _firstProfileId => _profiles.isEmpty ? '' : _profiles.first.id;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant TaxManagementPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Both tax sub-tabs served by this class build it in the same slot with no
    // key, so Flutter keeps this State and `initState` never runs again.
    if (widget.section == oldWidget.section) return;
    _resetForSection();
    _load();
  }

  /// Drop what belonged to the tab being left.
  ///
  /// The search box matters more here than elsewhere: `_load` sends
  /// `_search.text` to the server, so a term typed on one tab would silently
  /// filter the next one. The selections matter for the same reason —
  /// `ruleConditions` loads with `ruleId: _selectedRule?.id`, which would be a
  /// rule picked on a different tab.
  void _resetForSection() {
    _search.clear();
    _page = 1;
    _total = 0;
    _error = null;
    _selectedSystem = null;
    _selectedComponent = null;
    _selectedProfile = null;
    _selectedCountryMapping = null;
    _selectedMigrationMapping = null;
    _selectedRule = null;
    _simulationResult = null;
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      switch (widget.section) {
        case TaxManagementSection.systems:
          final data = await widget.api.taxSystems(
            includeDeleted: _showRetired,
            page: _page,
            search: _search.text.trim(),
          );
          _systems = data.items;
          _total = data.total;
          break;
        case TaxManagementSection.components:
          if (_systems.isEmpty) {
            _systems = (await widget.api.taxSystems(page: 1)).items;
          }
          final data = await widget.api.taxComponents(
            includeDeleted: _showRetired,
            page: _page,
            search: _search.text.trim(),
          );
          _components = data.items;
          _total = data.total;
          break;
        case TaxManagementSection.profiles:
          if (_systems.isEmpty) {
            _systems = (await widget.api.taxSystems(page: 1)).items;
          }
          final data = await widget.api.taxProfiles(
            includeDeleted: _showRetired,
            page: _page,
            search: _search.text.trim(),
          );
          _profiles = data.items;
          _total = data.total;
          break;
        case TaxManagementSection.countryMapping:
          _countryMappings = await widget.api.taxCountryMappings();
          _total = _countryMappings.length;
          break;
        case TaxManagementSection.migrationMapping:
          _migrationMappings = await widget.api.taxMigrationMappings();
          _total = _migrationMappings.length;
          break;
        case TaxManagementSection.rules:
          final data = await widget.api.taxRules(
            page: _page,
            search: _search.text.trim(),
          );
          _rules = data.items;
          _total = data.total;
          break;
        case TaxManagementSection.ruleConditions:
          _ruleConditions = await widget.api.taxRuleConditions(
            ruleId: _selectedRule?.id,
          );
          _total = _ruleConditions.length;
          break;
        case TaxManagementSection.rulePriorities:
          _rulePriorities = await widget.api.taxRulePriorities();
          _total = _rulePriorities.length;
          break;
        case TaxManagementSection.ruleSimulator:
          if (_profiles.isEmpty) {
            _profiles = (await widget.api.taxProfiles(page: 1)).items;
          }
          _total = _simulationResult == null ? 0 : 1;
          break;
        case TaxManagementSection.ruleHistory:
          _ruleHistory = await widget.api.taxRuleHistory(
            code: _search.text.trim().isEmpty ? null : _search.text.trim(),
          );
          _total = _ruleHistory.length;
          break;
        case TaxManagementSection.executionLog:
          _executionLogs = await widget.api.taxRuleExecutionLogs();
          _total = _executionLogs.length;
          break;
        case TaxManagementSection.effectiveDates:
          _effectiveDates = await widget.api.taxEffectiveDates();
          _total = _effectiveDates.length;
          break;
        case TaxManagementSection.settings:
          _settings = await widget.api.taxSettings();
          _total = 1;
          break;
        case TaxManagementSection.history:
          _history = await widget.api.taxHistory();
          _total = _history.length;
          break;
      }
    } on ApiException catch (exception) {
      _error = exception.message;
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      child: ManagementWorkspaceLayout(
        toolbar: _buildToolbar(),
        searchPanel: SearchFilterPanel(
          controller: _search,
          onSearch: (_) => _load(requestedPage: 1),
          hintText: _subtitle,
        ),
        primaryContent: _buildContent(),
        detailsPanel: _hasSelection ? _summaryPanel() : null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: _hasSelection,
          message: _loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }

  String get _title => switch (widget.section) {
        TaxManagementSection.systems => 'Tax Systems',
        TaxManagementSection.components => 'Tax Components',
        TaxManagementSection.profiles => 'Tax Profiles',
        TaxManagementSection.countryMapping => 'Country Mapping',
        TaxManagementSection.migrationMapping => 'Migration Mapping',
        TaxManagementSection.rules => 'Tax Rules',
        TaxManagementSection.ruleConditions => 'Rule Conditions',
        TaxManagementSection.rulePriorities => 'Rule Priorities',
        TaxManagementSection.ruleSimulator => 'Rule Simulator',
        TaxManagementSection.ruleHistory => 'Rule History',
        TaxManagementSection.executionLog => 'Execution Log',
        TaxManagementSection.effectiveDates => 'Effective Dates',
        TaxManagementSection.settings => 'Tax Settings',
        TaxManagementSection.history => 'Tax History',
      };

  bool get _canCreateCurrent =>
      ({
        TaxManagementSection.systems,
        TaxManagementSection.components,
        TaxManagementSection.profiles,
        TaxManagementSection.countryMapping,
        TaxManagementSection.migrationMapping,
        TaxManagementSection.rules,
      }.contains(widget.section)) &&
      (widget.section == TaxManagementSection.rules
          ? _canRuleCreate
          : _canCreate);

  bool get _canDeleteCurrent =>
      _canDelete &&
      switch (widget.section) {
        TaxManagementSection.systems => _selectedSystem != null,
        TaxManagementSection.components => _selectedComponent != null,
        TaxManagementSection.profiles => _selectedProfile != null,
        TaxManagementSection.countryMapping => _selectedCountryMapping != null,
        TaxManagementSection.migrationMapping =>
          _selectedMigrationMapping != null,
        TaxManagementSection.rules => _selectedRule != null && _canRuleDelete,
        _ => false,
      };

  bool get _hasSelection => switch (widget.section) {
        TaxManagementSection.systems => _selectedSystem != null,
        TaxManagementSection.components => _selectedComponent != null,
        TaxManagementSection.profiles => _selectedProfile != null,
        TaxManagementSection.countryMapping => _selectedCountryMapping != null,
        TaxManagementSection.migrationMapping =>
          _selectedMigrationMapping != null,
        TaxManagementSection.rules => _selectedRule != null,
        _ => false,
      };

  Widget _buildToolbar() => WorkspaceToolbar(
        actions: const [
          ToolbarAction.newItem,
          ToolbarAction.delete,
          ToolbarAction.settings,
          ToolbarAction.refresh,
        ],
        isVisible: (action) => switch (action) {
          ToolbarAction.newItem => _canCreateCurrent,
          ToolbarAction.delete => _canDeleteCurrent,
          ToolbarAction.settings =>
            _canSettings && widget.section == TaxManagementSection.settings,
          ToolbarAction.refresh => true,
          _ => false,
        },
        isEnabled: (action) =>
            !_loading &&
            switch (action) {
              ToolbarAction.newItem => _canCreateCurrent,
              ToolbarAction.delete => _canDeleteCurrent,
              ToolbarAction.settings =>
                _canSettings && widget.section == TaxManagementSection.settings,
              ToolbarAction.refresh => true,
              _ => false,
            },
        trailing: [
          if (_supportsRetired)
            FilterChip(
              label: const Text('Show retired'),
              selected: _showRetired,
              onSelected: _loading
                  ? null
                  : (value) {
                      setState(() => _showRetired = value);
                      _load(requestedPage: 1);
                    },
            ),
        ],
        onAction: (action) {
          switch (action) {
            case ToolbarAction.newItem:
              _openCreate();
              break;
            case ToolbarAction.delete:
              _deleteSelected();
              break;
            case ToolbarAction.settings:
              _saveSettings();
              break;
            case ToolbarAction.refresh:
              _load();
              break;
            default:
              break;
          }
        },
      );

  Widget _buildContent() {
    if (_error != null) {
      return WorkspaceErrorState(message: _error!, onRetry: _load);
    }
    if (_loading && _total == 0) {
      return const TableLoadingSkeleton();
    }
    return switch (widget.section) {
      TaxManagementSection.systems => _systemsGrid(),
      TaxManagementSection.components => _componentsGrid(),
      TaxManagementSection.profiles => _profilesGrid(),
      TaxManagementSection.countryMapping => _countryMappingGrid(),
      TaxManagementSection.migrationMapping => _migrationMappingGrid(),
      TaxManagementSection.rules => _rulesGrid(),
      TaxManagementSection.ruleConditions => _ruleConditionsGrid(),
      TaxManagementSection.rulePriorities => _rulePrioritiesGrid(),
      TaxManagementSection.ruleSimulator => _ruleSimulatorView(),
      TaxManagementSection.ruleHistory => _ruleHistoryGrid(),
      TaxManagementSection.executionLog => _executionLogGrid(),
      TaxManagementSection.effectiveDates => _effectiveDatesGrid(),
      TaxManagementSection.settings => _settingsView(),
      TaxManagementSection.history => _historyGrid(),
    };
  }

  Widget _summaryPanel() => QuickSummaryPanel(
        title: _title,
        lines: [
          DetailLine('Section', _title),
          DetailLine('Total', '$_total'),
        ],
      );

  String get _subtitle => switch (widget.section) {
        TaxManagementSection.systems =>
          'Configure reusable country and profile aware tax systems.',
        TaxManagementSection.components =>
          'Configure calculation components for every tax system.',
        TaxManagementSection.profiles =>
          'Build product-assignable tax profiles from tax components.',
        TaxManagementSection.countryMapping =>
          'Map countries and business profiles to default tax systems.',
        TaxManagementSection.migrationMapping =>
          'Map legacy tax definitions to historical or new profiles.',
        TaxManagementSection.rules =>
          'Configure country-independent rule masters with priority and versioning.',
        TaxManagementSection.ruleConditions =>
          'Review normalized rule conditions used by the tax engine.',
        TaxManagementSection.rulePriorities =>
          'Inspect rule precedence, versions, and action density.',
        TaxManagementSection.ruleSimulator =>
          'Preview matched rules, selected profiles, and calculated components.',
        TaxManagementSection.ruleHistory =>
          'Track immutable rule versions across effective dates.',
        TaxManagementSection.executionLog =>
          'Review stored simulation execution traces and outcomes.',
        TaxManagementSection.effectiveDates =>
          'Review effective date windows across tax systems, components, and profiles.',
        TaxManagementSection.settings =>
          'Manage configurable tax labels for screens and reports.',
        TaxManagementSection.history => 'Track tax framework changes.',
      };

  /// Restore, offered only on a row that is actually retired.
  ///
  /// `contextActionsFor` rather than `contextActions`, so a live row does not
  /// carry an action that would do nothing to it.
  List<WorkspaceContextAction> _rowActions(bool isDeleted) =>
      isDeleted && _canRestore
          ? const [WorkspaceContextAction.restore]
          : const [];

  Widget _systemsGrid() {
    if (_systems.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxSystemRecord>(
      items: _systems,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'effective', label: 'Effective'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.code,
        item.displayName,
        item.isDeleted ? 'DELETED' : item.status,
        '${item.effectiveFrom} - ${item.effectiveTo}',
      ],
      selectedId: _selectedSystem?.id,
      onSelect: (item) => setState(() => _selectedSystem = item),
      onOpen: _openSystemEdit,
      contextActionsFor: (item) => _rowActions(item.isDeleted),
      onContextAction: (action, item) {
        if (action == WorkspaceContextAction.restore) {
          unawaited(_restore(item.id));
        }
      },
      onPageChanged: (offset) =>
          _load(requestedPage: offset ~/ _rowsPerPage + 1),
    );
  }

  Widget _componentsGrid() {
    if (_components.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxComponentRecord>(
      items: _components,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'percentage', label: '%'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.code,
        item.label,
        item.percentage,
        item.isDeleted ? 'DELETED' : item.status,
      ],
      selectedId: _selectedComponent?.id,
      onSelect: (item) => setState(() => _selectedComponent = item),
      onOpen: _openComponentEdit,
      contextActionsFor: (item) => _rowActions(item.isDeleted),
      onContextAction: (action, item) {
        if (action == WorkspaceContextAction.restore) {
          unawaited(_restore(item.id));
        }
      },
      onPageChanged: (offset) =>
          _load(requestedPage: offset ~/ _rowsPerPage + 1),
    );
  }

  Widget _profilesGrid() {
    if (_profiles.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxProfileRecord>(
      items: _profiles,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'components', label: 'Components'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.code,
        item.label,
        '${item.components.length}',
        item.isDeleted ? 'DELETED' : item.status,
      ],
      selectedId: _selectedProfile?.id,
      onSelect: (item) => setState(() => _selectedProfile = item),
      onOpen: _openProfileEdit,
      contextActionsFor: (item) => _rowActions(item.isDeleted),
      onContextAction: (action, item) {
        if (action == WorkspaceContextAction.restore) {
          unawaited(_restore(item.id));
        }
      },
      onPageChanged: (offset) =>
          _load(requestedPage: offset ~/ _rowsPerPage + 1),
    );
  }

  Widget _countryMappingGrid() {
    if (_countryMappings.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxCountryMappingRecord>(
      items: _countryMappings,
      total: _countryMappings.length,
      pageOffset: 0,
      rowsPerPage: _countryMappings.length,
      columns: const [
        GridColumn(key: 'country', label: 'Country'),
        GridColumn(key: 'system', label: 'Tax System'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.countryId,
        item.taxSystemId,
        item.isDeleted ? 'DELETED' : item.status,
      ],
      selectedId: _selectedCountryMapping?.id,
      onSelect: (item) => setState(() => _selectedCountryMapping = item),
      onOpen: _openCountryMappingEdit,
      onPageChanged: (_) {},
    );
  }

  Widget _migrationMappingGrid() {
    if (_migrationMappings.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxMigrationMappingRecord>(
      items: _migrationMappings,
      total: _migrationMappings.length,
      pageOffset: 0,
      rowsPerPage: _migrationMappings.length,
      columns: const [
        GridColumn(key: 'legacy_code', label: 'Legacy Code'),
        GridColumn(key: 'legacy_name', label: 'Legacy Name'),
        GridColumn(key: 'target', label: 'Target Profile'),
        GridColumn(key: 'historical', label: 'Keep Historical'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.legacyTaxCode,
        item.legacyTaxName,
        item.targetTaxProfileId,
        item.keepHistorical ? 'Yes' : 'No',
      ],
      selectedId: _selectedMigrationMapping?.id,
      onSelect: (item) => setState(() => _selectedMigrationMapping = item),
      onOpen: _openMigrationMappingEdit,
      onPageChanged: (_) {},
    );
  }

  Widget _rulesGrid() {
    if (_rules.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxRuleRecord>(
      items: _rules,
      total: _total,
      pageOffset: (_page - 1) * _rowsPerPage,
      rowsPerPage: _rowsPerPage,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'priority', label: 'Priority'),
        GridColumn(key: 'version', label: 'Version'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.code,
        item.name,
        '${item.priority}',
        'v${item.versionNumber}',
        item.isDeleted ? 'DELETED' : item.status,
      ],
      selectedId: _selectedRule?.id,
      onSelect: (item) => setState(() => _selectedRule = item),
      onOpen: _openRuleEdit,
      onPageChanged: (offset) =>
          _load(requestedPage: offset ~/ _rowsPerPage + 1),
    );
  }

  Widget _ruleConditionsGrid() {
    if (_ruleConditions.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxRuleConditionRecord>(
      items: _ruleConditions,
      total: _ruleConditions.length,
      pageOffset: 0,
      rowsPerPage: _ruleConditions.length,
      columns: const [
        GridColumn(key: 'rule', label: 'Rule Id'),
        GridColumn(key: 'sequence', label: 'Seq'),
        GridColumn(key: 'field', label: 'Field'),
        GridColumn(key: 'operator', label: 'Operator'),
        GridColumn(key: 'value', label: 'Value'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.taxRuleId,
        '${item.sequence}',
        item.fieldKey,
        item.operatorType,
        item.valueText.isNotEmpty ? item.valueText : item.valueNumber,
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _rulePrioritiesGrid() {
    if (_rulePriorities.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxRulePriorityRecord>(
      items: _rulePriorities,
      total: _rulePriorities.length,
      pageOffset: 0,
      rowsPerPage: _rulePriorities.length,
      columns: const [
        GridColumn(key: 'priority', label: 'Priority'),
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'version', label: 'Version'),
        GridColumn(key: 'coverage', label: 'Conditions / Actions'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        '${item.priority}',
        item.code,
        'v${item.versionNumber}',
        '${item.conditionCount} / ${item.actionCount}',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _ruleHistoryGrid() {
    if (_ruleHistory.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxRuleRecord>(
      items: _ruleHistory,
      total: _ruleHistory.length,
      pageOffset: 0,
      rowsPerPage: _ruleHistory.length,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'version', label: 'Version'),
        GridColumn(key: 'effective', label: 'Effective'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.code,
        item.name,
        'v${item.versionNumber}',
        '${item.effectiveFrom} - ${item.effectiveTo}',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _executionLogGrid() {
    if (_executionLogs.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxRuleExecutionLogRecord>(
      items: _executionLogs,
      total: _executionLogs.length,
      pageOffset: 0,
      rowsPerPage: _executionLogs.length,
      columns: const [
        GridColumn(key: 'mode', label: 'Mode'),
        GridColumn(key: 'transaction', label: 'Transaction'),
        GridColumn(key: 'rule', label: 'Matched Rule'),
        GridColumn(key: 'profile', label: 'Applied Profile'),
        GridColumn(key: 'created', label: 'Created'),
      ],
      id: (item) => item.id,
      cells: (item) => [
        item.executionMode,
        item.transactionType,
        item.matchedRuleId,
        item.appliedTaxProfileId,
        item.createdAt,
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _ruleSimulatorView() {
    final TextEditingController transactionType =
        TextEditingController(text: 'SALES');
    final TextEditingController invoiceValue =
        TextEditingController(text: '100.00');
    final TextEditingController countryId = TextEditingController();
    final TextEditingController businessProfileId = TextEditingController();
    final TextEditingController taxProfileId =
        TextEditingController(text: _firstProfileId);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                SizedBox(
                  width: 180,
                  child: TextField(
                    controller: transactionType,
                    decoration:
                        const InputDecoration(labelText: 'Transaction type'),
                  ),
                ),
                SizedBox(
                  width: 180,
                  child: TextField(
                    controller: invoiceValue,
                    decoration:
                        const InputDecoration(labelText: 'Invoice value'),
                  ),
                ),
                SizedBox(
                  width: 280,
                  child: TextField(
                    controller: taxProfileId,
                    decoration:
                        const InputDecoration(labelText: 'Tax profile id'),
                  ),
                ),
                SizedBox(
                  width: 280,
                  child: TextField(
                    controller: countryId,
                    decoration: const InputDecoration(labelText: 'Country id'),
                  ),
                ),
                SizedBox(
                  width: 280,
                  child: TextField(
                    controller: businessProfileId,
                    decoration:
                        const InputDecoration(labelText: 'Business profile id'),
                  ),
                ),
                FilledButton.icon(
                  onPressed: !_canSimulate || _loading
                      ? null
                      : () => _runSimulation({
                            'transaction_type': transactionType.text.trim(),
                            'invoice_value': invoiceValue.text.trim(),
                            if (countryId.text.trim().isNotEmpty)
                              'country_id': countryId.text.trim(),
                            if (businessProfileId.text.trim().isNotEmpty)
                              'business_profile_id':
                                  businessProfileId.text.trim(),
                            if (taxProfileId.text.trim().isNotEmpty)
                              'tax_profile_id': taxProfileId.text.trim(),
                          }),
                  icon: const Icon(Icons.science_outlined),
                  label: const Text('Simulate'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            if (_simulationResult == null)
              const Text('Run a simulation to preview the applied rule.')
            else ...[
              Text(
                'Matched rule: ${_simulationResult!.matchedRuleId.isEmpty ? 'None' : _simulationResult!.matchedRuleId}',
              ),
              const SizedBox(height: 8),
              Text('Reason: ${_simulationResult!.matchedRuleReason}'),
              const SizedBox(height: 8),
              Text(
                'Base ${_simulationResult!.baseAmount}  |  Tax ${_simulationResult!.totalTaxAmount}',
              ),
              const SizedBox(height: 12),
              Expanded(
                child: ListView(
                  children: [
                    ..._simulationResult!.appliedComponents.map(
                      (item) => ListTile(
                        dense: true,
                        title: Text('${item.label} (${item.code})'),
                        subtitle: Text(
                          '${item.percentage}% -> ${item.amount}  [${item.source}]',
                        ),
                      ),
                    ),
                    const Divider(),
                    ..._simulationResult!.decisions.map(
                      (item) => ListTile(
                        dense: true,
                        title: Text('${item.code} (priority ${item.priority})'),
                        subtitle: Text(item.reasons.join(' ')),
                        trailing: Icon(
                          item.matched ? Icons.check_circle : Icons.cancel,
                          color: item.matched ? Colors.green : Colors.orange,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _effectiveDatesGrid() {
    if (_effectiveDates.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<EffectiveDateRecord>(
      items: _effectiveDates,
      total: _effectiveDates.length,
      pageOffset: 0,
      rowsPerPage: _effectiveDates.length,
      columns: const [
        GridColumn(key: 'type', label: 'Type'),
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'effective', label: 'Effective'),
      ],
      id: (item) => '${item.entityType}:${item.entityId}',
      cells: (item) => [
        item.entityType,
        item.code,
        item.name,
        '${item.effectiveFrom} - ${item.effectiveTo}',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _historyGrid() {
    if (_history.isEmpty) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    return EnterpriseDataGrid<TaxHistoryRecord>(
      items: _history,
      total: _history.length,
      pageOffset: 0,
      rowsPerPage: _history.length,
      columns: const [
        GridColumn(key: 'action', label: 'Action'),
        GridColumn(key: 'entity', label: 'Entity'),
        GridColumn(key: 'entity_id', label: 'Entity Id'),
        GridColumn(key: 'time', label: 'Timestamp'),
      ],
      id: (item) => item.id,
      cells: (item) =>
          [item.action, item.entityType, item.entityId, item.createdAt],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }

  Widget _settingsView() {
    final settings = _settings;
    if (settings == null) {
      return const StandardEmptyState(type: EmptyStateType.noRecords);
    }
    final TextEditingController primary =
        TextEditingController(text: settings.primaryLabel);
    final TextEditingController component =
        TextEditingController(text: settings.componentLabel);
    final TextEditingController profile =
        TextEditingController(text: settings.profileLabel);
    final TextEditingController report =
        TextEditingController(text: settings.reportLabel);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 16,
          runSpacing: 12,
          children: [
            SizedBox(
              width: 260,
              child: TextField(
                controller: primary,
                decoration: const InputDecoration(labelText: 'Primary label'),
                onChanged: (value) => _settings = TaxSettingsRecord(
                  id: settings.id,
                  primaryLabel: value,
                  componentLabel: component.text.trim(),
                  profileLabel: profile.text.trim(),
                  reportLabel: report.text.trim(),
                  allowMixedHistorical: settings.allowMixedHistorical,
                  additionalSettings: settings.additionalSettings,
                ),
              ),
            ),
            SizedBox(
              width: 260,
              child: TextField(
                controller: component,
                decoration: const InputDecoration(labelText: 'Component label'),
                onChanged: (value) => _settings = TaxSettingsRecord(
                  id: settings.id,
                  primaryLabel: primary.text.trim(),
                  componentLabel: value,
                  profileLabel: profile.text.trim(),
                  reportLabel: report.text.trim(),
                  allowMixedHistorical: settings.allowMixedHistorical,
                  additionalSettings: settings.additionalSettings,
                ),
              ),
            ),
            SizedBox(
              width: 260,
              child: TextField(
                controller: profile,
                decoration: const InputDecoration(labelText: 'Profile label'),
                onChanged: (value) => _settings = TaxSettingsRecord(
                  id: settings.id,
                  primaryLabel: primary.text.trim(),
                  componentLabel: component.text.trim(),
                  profileLabel: value,
                  reportLabel: report.text.trim(),
                  allowMixedHistorical: settings.allowMixedHistorical,
                  additionalSettings: settings.additionalSettings,
                ),
              ),
            ),
            SizedBox(
              width: 260,
              child: TextField(
                controller: report,
                decoration: const InputDecoration(labelText: 'Report label'),
                onChanged: (value) => _settings = TaxSettingsRecord(
                  id: settings.id,
                  primaryLabel: primary.text.trim(),
                  componentLabel: component.text.trim(),
                  profileLabel: profile.text.trim(),
                  reportLabel: value,
                  allowMixedHistorical: settings.allowMixedHistorical,
                  additionalSettings: settings.additionalSettings,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The sections whose rows are soft-deleted and can be brought back.
  ///
  /// A retired tax system, component or profile vanished from every list and
  /// nothing could restore it -- the endpoints existed and no screen reached
  /// them, so from the desktop a soft delete behaved like a permanent one.
  bool get _supportsRetired => const {
        TaxManagementSection.systems,
        TaxManagementSection.components,
        TaxManagementSection.profiles,
      }.contains(widget.section);

  /// Bring a retired row back.
  ///
  /// Offered on the row rather than the toolbar: it applies to one retired
  /// record, and `ToolbarAction` is a framework enum shared by every
  /// workspace in the shell.
  Future<void> _restore(String id) async {
    try {
      switch (widget.section) {
        case TaxManagementSection.systems:
          await widget.api.restoreTaxSystem(id);
          break;
        case TaxManagementSection.components:
          await widget.api.restoreTaxComponent(id);
          break;
        case TaxManagementSection.profiles:
          await widget.api.restoreTaxProfile(id);
          break;
        default:
          return;
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        'Brought back.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _openCreate() async {
    switch (widget.section) {
      case TaxManagementSection.systems:
        await _openSystemEdit(null);
        break;
      case TaxManagementSection.components:
        await _openComponentEdit(null);
        break;
      case TaxManagementSection.profiles:
        await _openProfileEdit(null);
        break;
      case TaxManagementSection.countryMapping:
        await _openCountryMappingEdit(null);
        break;
      case TaxManagementSection.migrationMapping:
        await _openMigrationMappingEdit(null);
        break;
      case TaxManagementSection.rules:
        await _openRuleEdit(null);
        break;
      default:
        break;
    }
  }

  Future<void> _deleteSelected() async {
    try {
      switch (widget.section) {
        case TaxManagementSection.systems:
          if (_selectedSystem != null) {
            await widget.api.deleteTaxSystem(_selectedSystem!.id);
          }
          break;
        case TaxManagementSection.components:
          if (_selectedComponent != null) {
            await widget.api.deleteTaxComponent(_selectedComponent!.id);
          }
          break;
        case TaxManagementSection.profiles:
          if (_selectedProfile != null) {
            await widget.api.deleteTaxProfile(_selectedProfile!.id);
          }
          break;
        case TaxManagementSection.countryMapping:
          if (_selectedCountryMapping != null) {
            await widget.api
                .deleteTaxCountryMapping(_selectedCountryMapping!.id);
          }
          break;
        case TaxManagementSection.migrationMapping:
          if (_selectedMigrationMapping != null) {
            await widget.api
                .deleteTaxMigrationMapping(_selectedMigrationMapping!.id);
          }
          break;
        case TaxManagementSection.rules:
          if (_selectedRule != null) {
            await widget.api.deleteTaxRule(_selectedRule!.id);
          }
          break;
        default:
          break;
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _saveSettings() async {
    if (_settings == null || !_canSettings) return;
    try {
      final saved = await widget.api.updateTaxSettings({
        'primary_label': _settings!.primaryLabel,
        'component_label': _settings!.componentLabel,
        'profile_label': _settings!.profileLabel,
        'report_label': _settings!.reportLabel,
        'allow_mixed_historical': _settings!.allowMixedHistorical,
        'additional_settings': _settings!.additionalSettings,
      });
      _settings = saved;
      if (!mounted) return;
      NotificationService.show(
        context,
        'Tax settings saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openSystemEdit(TaxSystemRecord? current) async {
    final result = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => TaxSetupPage(
          api: widget.api,
          systemId: current?.id,
        ),
      ),
    );
    if (result == true) await _load();
  }

  Future<void> _openComponentEdit(TaxComponentRecord? current) async {
    final payload = await _taxSimpleDialog(
      title: current == null ? 'Create tax component' : 'Edit tax component',
      fields: {
        'tax_system_id': current?.taxSystemId ?? _firstSystemId,
        'code': current?.code ?? '',
        'name': current?.name ?? '',
        'label': current?.label ?? '',
        'percentage': current?.percentage ?? '0',
      },
    );
    if (payload == null) return;
    try {
      if (current == null) {
        await widget.api.createTaxComponent(payload);
      } else {
        await widget.api.updateTaxComponent(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'tax component', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _openProfileEdit(TaxProfileRecord? current) async {
    final payload = await _taxSimpleDialog(
      title: current == null ? 'Create tax profile' : 'Edit tax profile',
      fields: {
        'tax_system_id': current?.taxSystemId ?? _firstSystemId,
        'code': current?.code ?? '',
        'name': current?.name ?? '',
        'label': current?.label ?? '',
        'components': '[]',
      },
      parseJsonFieldKeys: const {'components'},
    );
    if (payload == null) return;
    try {
      if (current == null) {
        await widget.api.createTaxProfile(payload);
      } else {
        await widget.api.updateTaxProfile(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'tax profile', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _openCountryMappingEdit(TaxCountryMappingRecord? current) async {
    final payload = await _taxSimpleDialog(
      title:
          current == null ? 'Create country mapping' : 'Edit country mapping',
      fields: {
        'country_id': current?.countryId ?? '',
        'tax_system_id': current?.taxSystemId ?? '',
        'business_profile_id': current?.businessProfileId ?? '',
        'is_default': (current?.isDefault ?? true).toString(),
      },
      parseBoolFieldKeys: const {'is_default'},
    );
    if (payload == null) return;
    try {
      if (current == null) {
        await widget.api.createTaxCountryMapping(payload);
      } else {
        await widget.api.updateTaxCountryMapping(current.id, payload);
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openMigrationMappingEdit(
      TaxMigrationMappingRecord? current) async {
    final payload = await _taxSimpleDialog(
      title: current == null
          ? 'Create migration mapping'
          : 'Edit migration mapping',
      fields: {
        'legacy_tax_code': current?.legacyTaxCode ?? '',
        'legacy_tax_name': current?.legacyTaxName ?? '',
        'source_system': current?.sourceSystem ?? '',
        'legacy_rate': current?.legacyRate ?? '',
        'target_tax_profile_id': current?.targetTaxProfileId ?? '',
        'keep_historical': (current?.keepHistorical ?? true).toString(),
      },
      parseBoolFieldKeys: const {'keep_historical'},
    );
    if (payload == null) return;
    try {
      if (current == null) {
        await widget.api.createTaxMigrationMapping(payload);
      } else {
        await widget.api.updateTaxMigrationMapping(current.id, payload);
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _openRuleEdit(TaxRuleRecord? current) async {
    final payload = await _taxSimpleDialog(
      title: current == null ? 'Create tax rule' : 'Edit tax rule',
      fields: {
        'code': current?.code ?? '',
        'name': current?.name ?? '',
        'description': current?.description ?? '',
        'priority': '${current?.priority ?? 100}',
        'status': current?.status ?? 'DRAFT',
        'country_id': current?.countryId ?? '',
        'business_profile_id': current?.businessProfileId ?? '',
        'tax_profile_id': current?.taxProfileId ?? _firstProfileId,
        'conditions': current == null
            ? '[]'
            : jsonEncode(current.conditions
                .map((item) => {
                      'sequence': item.sequence,
                      'field_key': item.fieldKey,
                      'operator': item.operatorType,
                      if (item.valueText.isNotEmpty)
                        'value_text': item.valueText,
                      if (item.valueNumber.isNotEmpty)
                        'value_number': item.valueNumber,
                    })
                .toList()),
        'actions': current == null
            ? '[]'
            : jsonEncode(current.actions
                .map((item) => {
                      'sequence': item.sequence,
                      'action_type': item.actionType,
                      if (item.targetTaxProfileId.isNotEmpty)
                        'target_tax_profile_id': item.targetTaxProfileId,
                      if (item.targetTaxComponentId.isNotEmpty)
                        'target_tax_component_id': item.targetTaxComponentId,
                      if (item.percentageOverride.isNotEmpty)
                        'percentage_override': item.percentageOverride,
                    })
                .toList()),
      },
      parseJsonFieldKeys: const {'conditions', 'actions'},
    );
    if (payload == null) return;
    try {
      if (current == null) {
        await widget.api.createTaxRule(payload);
      } else {
        await widget.api.updateTaxRule(
          current.id,
          payload,
          expectedVersion: preconditionFor(current.version),
        );
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'tax rule', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _runSimulation(Json payload) async {
    try {
      final result = await widget.api.simulateTaxRule(payload);
      setState(() {
        _simulationResult = result;
        _total = 1;
      });
      if (!mounted) return;
      NotificationService.show(
        context,
        'Tax simulation completed.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<Json?> _taxSimpleDialog({
    required String title,
    required Map<String, String> fields,
    Set<String> parseBoolFieldKeys = const {},
    Set<String> parseJsonFieldKeys = const {},
  }) async {
    final Map<String, TextEditingController> controllers = {
      for (final entry in fields.entries)
        entry.key: TextEditingController(text: entry.value),
    };
    return showDialog<Json>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 640,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: controllers.entries
                  .map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: TextField(
                        controller: entry.value,
                        decoration: InputDecoration(labelText: entry.key),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final Json payload = {};
              for (final entry in controllers.entries) {
                final raw = entry.value.text.trim();
                if (raw.isEmpty) continue;
                if (parseBoolFieldKeys.contains(entry.key)) {
                  payload[entry.key] = raw.toLowerCase() == 'true';
                  continue;
                }
                if (parseJsonFieldKeys.contains(entry.key)) {
                  payload[entry.key] = decodeJsonOrEmptyArray(raw);
                  continue;
                }
                payload[entry.key] = raw;
              }
              Navigator.of(context).pop(payload);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}

dynamic decodeJsonOrEmptyArray(String value) {
  try {
    return jsonDecode(value);
  } catch (_) {
    return const [];
  }
}
