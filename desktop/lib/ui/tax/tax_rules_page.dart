// Tax Rules page — two tabs: Rules (master-detail) | Priority Manager

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/tax_framework.dart';

// ─── Helper: Condition Draft ──────────────────────────────────────────────────

class _ConditionDraft {
  String? id;
  final TextEditingController fieldKey;
  String operator;
  final TextEditingController value;
  int sequence;

  _ConditionDraft({
    this.id,
    String? fieldKey,
    this.operator = 'EQUALS',
    String? value,
    this.sequence = 1,
  })  : fieldKey = TextEditingController(text: fieldKey ?? 'customer_type'),
        value = TextEditingController(text: value ?? '');

  void dispose() {
    fieldKey.dispose();
    value.dispose();
  }
}

// ─── Helper: Action Draft ─────────────────────────────────────────────────────

class _ActionDraft {
  String? id;
  String actionType;
  final TextEditingController targetProfileId;
  final TextEditingController targetComponentId;
  final TextEditingController percentageOverride;
  int sequence;

  _ActionDraft({
    this.id,
    this.actionType = 'EXEMPT_TAX',
    String? targetProfileId,
    String? targetComponentId,
    String? percentageOverride,
    this.sequence = 1,
  })  : targetProfileId =
            TextEditingController(text: targetProfileId ?? ''),
        targetComponentId =
            TextEditingController(text: targetComponentId ?? ''),
        percentageOverride =
            TextEditingController(text: percentageOverride ?? '');

  void dispose() {
    targetProfileId.dispose();
    targetComponentId.dispose();
    percentageOverride.dispose();
  }
}

// ─── Constants ────────────────────────────────────────────────────────────────

const _kFieldKeys = [
  'customer_type',
  'vendor_type',
  'product_type',
  'product_category',
  'transaction_type',
  'country',
  'state',
  'district',
  'city',
  'invoice_value',
  'quantity',
  'currency_code',
  'origin',
  'destination',
  'customer_category',
  'vendor_category',
];

const _kOperators = [
  'EQUALS',
  'NOT_EQUALS',
  'IN',
  'NOT_IN',
  'GREATER_THAN',
  'GREATER_OR_EQUAL',
  'LESS_THAN',
  'LESS_OR_EQUAL',
  'BETWEEN',
  'EXISTS',
  'NOT_EXISTS',
];

const _kActionTypes = [
  'APPLY_TAX_PROFILE',
  'APPLY_TAX_COMPONENT',
  'EXEMPT_TAX',
  'ZERO_RATED',
  'REVERSE_CHARGE',
  'INPUT_CREDIT_ALLOWED',
  'INPUT_CREDIT_BLOCKED',
  'OVERRIDE_COMPONENT_PERCENTAGE',
];

const _kNoValueOperators = {'EXISTS', 'NOT_EXISTS'};
const _kNumericFieldKeys = {'invoice_value', 'quantity'};

// ─── Main Page ────────────────────────────────────────────────────────────────

class TaxRulesPage extends StatefulWidget {
  const TaxRulesPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TaxRulesPage> createState() => _TaxRulesPageState();
}

class _TaxRulesPageState extends State<TaxRulesPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      children: [
        Container(
          color: cs.surface,
          child: TabBar(
            controller: _tabController,
            tabs: const [
              Tab(
                  icon: Icon(Icons.rule_outlined, size: 18),
                  text: 'Rules'),
              Tab(
                  icon: Icon(Icons.sort_outlined, size: 18),
                  text: 'Priority Manager'),
            ],
            labelColor: cs.primary,
            unselectedLabelColor: cs.onSurfaceVariant,
            indicatorColor: cs.primary,
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              _TaxRulesTab(api: widget.api, permissions: widget.permissions),
              _TaxPriorityTab(
                  api: widget.api, permissions: widget.permissions),
            ],
          ),
        ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1: Rules (master-detail)
// ═══════════════════════════════════════════════════════════════════════════════

class _TaxRulesTab extends StatefulWidget {
  const _TaxRulesTab({required this.api, required this.permissions});
  final ApiClient api;
  final PermissionService permissions;

  @override
  State<_TaxRulesTab> createState() => _TaxRulesTabState();
}

class _TaxRulesTabState extends State<_TaxRulesTab> {
  // List state
  List<TaxRuleRecord> _rules = [];
  List<TaxRuleRecord> _filtered = [];
  bool _listLoading = false;
  String? _listError;
  final TextEditingController _search = TextEditingController();
  String _statusFilter = 'All';

  // Reference data
  List<TaxProfileRecord> _profiles = [];
  List<TaxComponentRecord> _components = [];

  // Detail state
  TaxRuleRecord? _selected;
  bool _isNew = false;
  bool _saving = false;
  String? _detailError;
  String? _detailSuccess;
  bool _showAdvanced = false;

  // Form controllers
  final _codeCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _descriptionCtrl = TextEditingController();
  final _priorityCtrl = TextEditingController(text: '100');
  final _effectiveFromCtrl = TextEditingController();
  final _effectiveToCtrl = TextEditingController();
  String _formStatus = 'DRAFT';
  final List<_ConditionDraft> _conditions = [];
  final List<_ActionDraft> _actions = [];
  final _formKey = GlobalKey<FormState>();
  final _detailScroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _search.addListener(_applyFilter);
    _loadRules();
    _loadProfiles();
    _loadComponents();
  }

  @override
  void dispose() {
    _search.dispose();
    _codeCtrl.dispose();
    _nameCtrl.dispose();
    _descriptionCtrl.dispose();
    _priorityCtrl.dispose();
    _effectiveFromCtrl.dispose();
    _effectiveToCtrl.dispose();
    _detailScroll.dispose();
    for (final c in _conditions) {
      c.dispose();
    }
    for (final a in _actions) {
      a.dispose();
    }
    super.dispose();
  }

  // ─── Data loading ──────────────────────────────────────────────────────────

  Future<void> _loadRules() async {
    setState(() {
      _listLoading = true;
      _listError = null;
    });
    try {
      final result = await widget.api.taxRules(page: 1, pageSize: 100);
      if (!mounted) return;
      final list = result.items;
      setState(() {
        _rules = list;
        _applyFilter();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _listError = e.message);
    } finally {
      if (mounted) setState(() => _listLoading = false);
    }
  }

  Future<void> _loadProfiles() async {
    try {
      final result = await widget.api.taxProfiles(page: 1, pageSize: 100);
      if (!mounted) return;
      final list = result.items;
      if (mounted) setState(() => _profiles = list);
    } on ApiException catch (_) {
      // silent
    }
  }

  Future<void> _loadComponents() async {
    try {
      final result = await widget.api.taxComponents(page: 1, pageSize: 100);
      if (!mounted) return;
      final list = result.items;
      if (mounted) setState(() => _components = list);
    } on ApiException catch (_) {
      // silent
    }
  }

  // ─── Rule selection / new ──────────────────────────────────────────────────

  void _openRule(TaxRuleRecord rule) {
    _clearDrafts();
    for (final c in rule.conditions) {
      _conditions.add(_ConditionDraft(
        id: c.id,
        fieldKey: c.fieldKey,
        operator: c.operatorType,
        value: c.valueText.isNotEmpty ? c.valueText : c.valueNumber,
        sequence: c.sequence,
      ));
    }
    for (final a in rule.actions) {
      _actions.add(_ActionDraft(
        id: a.id,
        actionType: a.actionType,
        targetProfileId: a.targetTaxProfileId,
        targetComponentId: a.targetTaxComponentId,
        percentageOverride: a.percentageOverride,
        sequence: a.sequence,
      ));
    }
    setState(() {
      _selected = rule;
      _isNew = false;
      _detailError = null;
      _detailSuccess = null;
      _codeCtrl.text = rule.code;
      _nameCtrl.text = rule.name;
      _descriptionCtrl.text = rule.description;
      _priorityCtrl.text = rule.priority.toString();
      _effectiveFromCtrl.text = rule.effectiveFrom;
      _effectiveToCtrl.text = rule.effectiveTo;
      _formStatus = rule.status.isEmpty ? 'DRAFT' : rule.status;
      _showAdvanced = false;
    });
  }

  void _newRule() {
    _clearDrafts();
    setState(() {
      _selected = null;
      _isNew = true;
      _detailError = null;
      _detailSuccess = null;
      _codeCtrl.clear();
      _nameCtrl.clear();
      _descriptionCtrl.clear();
      _priorityCtrl.text = '100';
      _effectiveFromCtrl.clear();
      _effectiveToCtrl.clear();
      _formStatus = 'DRAFT';
      _showAdvanced = false;
    });
  }

  void _cloneRule() {
    if (_selected == null) return;
    final src = _selected!;
    final newConditions = src.conditions
        .map((c) => _ConditionDraft(
              fieldKey: c.fieldKey,
              operator: c.operatorType,
              value: c.valueText.isNotEmpty ? c.valueText : c.valueNumber,
              sequence: c.sequence,
            ))
        .toList();
    final newActions = src.actions
        .map((a) => _ActionDraft(
              actionType: a.actionType,
              targetProfileId: a.targetTaxProfileId,
              targetComponentId: a.targetTaxComponentId,
              percentageOverride: a.percentageOverride,
              sequence: a.sequence,
            ))
        .toList();
    _clearDrafts();
    _conditions.addAll(newConditions);
    _actions.addAll(newActions);
    setState(() {
      _selected = null;
      _isNew = true;
      _codeCtrl.text = '${src.code}_COPY';
      _nameCtrl.text = '${src.name} (Copy)';
      _descriptionCtrl.text = src.description;
      _priorityCtrl.text = src.priority.toString();
      _effectiveFromCtrl.clear();
      _effectiveToCtrl.clear();
      _formStatus = 'DRAFT';
      _detailSuccess = null;
      _detailError = null;
    });
  }

  void _cancel() {
    _clearDrafts();
    setState(() {
      _selected = null;
      _isNew = false;
      _detailError = null;
      _detailSuccess = null;
    });
  }

  void _clearDrafts() {
    for (final c in _conditions) {
      c.dispose();
    }
    _conditions.clear();
    for (final a in _actions) {
      a.dispose();
    }
    _actions.clear();
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _detailError = null;
      _detailSuccess = null;
    });

    final conditionsJson = _conditions.asMap().entries.map((e) {
      final draft = e.value;
      final isNumeric = _kNumericFieldKeys.contains(draft.fieldKey.text);
      final hasValue = !_kNoValueOperators.contains(draft.operator);
      return <String, dynamic>{
        if (draft.id != null) 'id': draft.id,
        'sequence': draft.sequence,
        'field_key': draft.fieldKey.text,
        'operator': draft.operator,
        if (hasValue && isNumeric)
          'value_number': draft.value.text.trim()
        else if (hasValue)
          'value_text': draft.value.text.trim(),
      };
    }).toList();

    final actionsJson = _actions.asMap().entries.map((e) {
      final draft = e.value;
      return <String, dynamic>{
        if (draft.id != null) 'id': draft.id,
        'sequence': draft.sequence,
        'action_type': draft.actionType,
        if (draft.actionType == 'APPLY_TAX_PROFILE' &&
            draft.targetProfileId.text.trim().isNotEmpty)
          'target_tax_profile_id': draft.targetProfileId.text.trim(),
        if ((draft.actionType == 'APPLY_TAX_COMPONENT' ||
                draft.actionType == 'OVERRIDE_COMPONENT_PERCENTAGE') &&
            draft.targetComponentId.text.trim().isNotEmpty)
          'target_tax_component_id': draft.targetComponentId.text.trim(),
        if (draft.actionType == 'OVERRIDE_COMPONENT_PERCENTAGE' &&
            draft.percentageOverride.text.trim().isNotEmpty)
          'percentage_override': draft.percentageOverride.text.trim(),
      };
    }).toList();

    final payload = <String, dynamic>{
      'code': _codeCtrl.text.trim().toUpperCase(),
      'name': _nameCtrl.text.trim(),
      'description': _descriptionCtrl.text.trim().isEmpty
          ? null
          : _descriptionCtrl.text.trim(),
      'priority': int.tryParse(_priorityCtrl.text.trim()) ?? 100,
      'status': _formStatus,
      if (_effectiveFromCtrl.text.trim().isNotEmpty)
        'effective_from': _effectiveFromCtrl.text.trim()
      else
        'effective_from': null,
      if (_effectiveToCtrl.text.trim().isNotEmpty)
        'effective_to': _effectiveToCtrl.text.trim()
      else
        'effective_to': null,
      'conditions': conditionsJson,
      'actions': actionsJson,
    };

    try {
      if (_isNew) {
        final created = await widget.api.createTaxRule(payload);
        final newId = created.id;
        if (!mounted) return;
        await _loadRules();
        if (!mounted) return;
        setState(() {
          _isNew = false;
          _detailSuccess = 'Tax rule created successfully.';
          if (newId.isNotEmpty) {
            final match = _rules.where((r) => r.id == newId).toList();
            if (match.isNotEmpty) _openRule(match.first);
          }
        });
      } else {
        final id = _selected!.id;
        await widget.api.updateTaxRule(id, payload);
        if (!mounted) return;
        await _loadRules();
        if (!mounted) return;
        setState(() {
          _detailSuccess = 'Tax rule saved successfully.';
          final match = _rules.where((r) => r.id == id).toList();
          if (match.isNotEmpty) _selected = match.first;
        });
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _detailError = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _deleteOrRestore() async {
    if (_selected == null) return;
    final rule = _selected!;
    if (rule.isDeleted) {
      // Restore
      try {
        await widget.api
            .restoreTaxRule(rule.id);
        if (!mounted) return;
        await _loadRules();
        if (!mounted) return;
        final match = _rules.where((r) => r.id == rule.id).toList();
        setState(() {
          _detailSuccess = 'Rule restored.';
          if (match.isNotEmpty) _selected = match.first;
        });
      } on ApiException catch (e) {
        if (!mounted) return;
        setState(() => _detailError = e.message);
      }
    } else {
      // Delete
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Delete Tax Rule?'),
          content: Text(
              'This will delete "${rule.name}". You can restore it later.'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Cancel')),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: FilledButton.styleFrom(
                  backgroundColor: Colors.red.shade700),
              child: const Text('Delete'),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
      try {
        await widget.api
            .deleteTaxRule(rule.id);
        if (!mounted) return;
        await _loadRules();
        if (!mounted) return;
        setState(() {
          // Re-select to show deleted state
          final match = _rules.where((r) => r.id == rule.id).toList();
          if (match.isNotEmpty) {
            _selected = match.first;
            _detailSuccess = 'Rule deleted. You may restore it.';
          } else {
            _cancel();
          }
        });
      } on ApiException catch (e) {
        if (!mounted) return;
        setState(() => _detailError = e.message);
      }
    }
  }

  // ─── Filter ────────────────────────────────────────────────────────────────

  void _applyFilter() {
    final q = _search.text.trim().toLowerCase();
    setState(() {
      _filtered = _rules.where((r) {
        final matchStatus = _statusFilter == 'All' ||
            (_statusFilter == 'DELETED'
                ? r.isDeleted
                : !r.isDeleted &&
                    r.status.toUpperCase() ==
                        _statusFilter.toUpperCase());
        final matchSearch = q.isEmpty ||
            r.code.toLowerCase().contains(q) ||
            r.name.toLowerCase().contains(q);
        return matchStatus && matchSearch;
      }).toList();
    });
  }

  void _setStatusFilter(String v) {
    setState(() => _statusFilter = v);
    _applyFilter();
  }

  // ─── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final wide = constraints.maxWidth >= 800;
      if (wide) {
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 300,
              child: _buildLeftPanel(),
            ),
            const VerticalDivider(width: 1),
            Expanded(child: _buildRightPanel()),
          ],
        );
      } else {
        if (_selected != null || _isNew) return _buildRightPanel();
        return _buildLeftPanel();
      }
    });
  }

  Widget _buildLeftPanel() {
    final cs = Theme.of(context).colorScheme;
    final nonDeletedCount = _rules.where((r) => !r.isDeleted).length;
    return Container(
      color: cs.surfaceContainerHighest.withAlpha(77),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Tax Rules',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                        color: cs.onSurface),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                  decoration: BoxDecoration(
                    color: cs.primary.withAlpha(20),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text('$nonDeletedCount',
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: cs.primary)),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: _newRule,
                  icon: const Icon(Icons.add, size: 14),
                  label: const Text('New Rule',
                      style: TextStyle(fontSize: 12)),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: cs.primary,
                    side: BorderSide(color: cs.primary),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 6),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search rules…',
                prefixIcon: const Icon(Icons.search, size: 18),
                isDense: true,
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
            ),
          ),
          _buildStatusChips(),
          const Divider(height: 1),
          if (_listError != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: _ErrorBanner(
                message: _listError!,
                onClose: () => setState(() => _listError = null),
                onRetry: _loadRules,
              ),
            ),
          if (_listLoading && _rules.isEmpty)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else
            Expanded(
              child: RefreshIndicator(
                onRefresh: _loadRules,
                child: _filtered.isEmpty
                    ? const Center(
                        child: Text('No tax rules found.',
                            style: TextStyle(color: Colors.grey)))
                    : ListView.builder(
                        itemCount: _filtered.length,
                        itemBuilder: (_, i) => _buildRuleCard(_filtered[i]),
                      ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildStatusChips() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: ['All', 'DRAFT', 'ACTIVE', 'INACTIVE', 'DELETED']
            .map((s) => Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: FilterChip(
                    label: Text(s, style: const TextStyle(fontSize: 12)),
                    selected: _statusFilter == s,
                    onSelected: (_) => _setStatusFilter(s),
                  ),
                ))
            .toList(),
      ),
    );
  }

  Widget _buildRuleCard(TaxRuleRecord rule) {
    final cs = Theme.of(context).colorScheme;
    final isSelected = _selected?.id == rule.id;

    return GestureDetector(
      onTap: () => _openRule(rule),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: isSelected ? cs.primaryContainer.withAlpha(80) : null,
          border: Border.all(
            color: isSelected ? cs.primary : cs.outlineVariant,
            width: isSelected ? 2 : 1,
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text.rich(
                      TextSpan(children: [
                        TextSpan(
                          text: rule.code,
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        TextSpan(
                          text: '  ${rule.name}',
                          style: TextStyle(
                              color: cs.onSurfaceVariant, fontSize: 13),
                        ),
                      ]),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  // Priority chip
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 1),
                    decoration: BoxDecoration(
                      color: Colors.indigo.shade50,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      'P${rule.priority}',
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Colors.indigo.shade700),
                    ),
                  ),
                  const SizedBox(width: 6),
                  _StatusChip(
                      status: rule.isDeleted ? 'DELETED' : rule.status),
                  const SizedBox(width: 6),
                  // Version badge
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 5, vertical: 1),
                    decoration: BoxDecoration(
                      color: cs.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'v${rule.versionNumber}',
                      style: TextStyle(
                          fontSize: 10, color: cs.onSurfaceVariant),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                '${rule.conditions.length} condition${rule.conditions.length != 1 ? 's' : ''} → ${rule.actions.length} action${rule.actions.length != 1 ? 's' : ''}',
                style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant),
              ),
              if (rule.effectiveFrom.isNotEmpty || rule.effectiveTo.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    [
                      if (rule.effectiveFrom.isNotEmpty)
                        'From: ${rule.effectiveFrom}',
                      if (rule.effectiveTo.isNotEmpty)
                        'To: ${rule.effectiveTo}',
                    ].join('  '),
                    style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRightPanel() {
    if (!_isNew && _selected == null) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.rule_outlined, size: 48, color: Colors.grey),
            SizedBox(height: 12),
            Text('Select a rule or create new',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }

    final cs = Theme.of(context).colorScheme;

    return Form(
      key: _formKey,
      child: Column(
        children: [
          // Header bar
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: cs.surface,
              border:
                  Border(bottom: BorderSide(color: cs.outlineVariant)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _isNew
                        ? 'New Tax Rule'
                        : '${_selected!.code} — ${_selected!.name}',
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (!_isNew && _selected != null) ...[
                  OutlinedButton.icon(
                    onPressed: _saving ? null : _cloneRule,
                    icon: const Icon(Icons.copy_outlined, size: 14),
                    label: const Text('Clone',
                        style: TextStyle(fontSize: 12)),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 6),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.save_outlined, size: 14),
                  label: Text(_saving ? 'Saving…' : 'Save',
                      style: const TextStyle(fontSize: 12)),
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Scrollbar(
              controller: _detailScroll,
              child: SingleChildScrollView(
                controller: _detailScroll,
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_detailError != null)
                      _ErrorBanner(
                        message: _detailError!,
                        onClose: () =>
                            setState(() => _detailError = null),
                      ),
                    if (_detailSuccess != null)
                      _SuccessBanner(
                        message: _detailSuccess!,
                        onClose: () =>
                            setState(() => _detailSuccess = null),
                      ),
                    _buildBasicInfoCard(cs),
                    const SizedBox(height: 16),
                    _buildConditionsCard(cs),
                    const SizedBox(height: 16),
                    _buildActionsCard(cs),
                    const SizedBox(height: 80),
                  ],
                ),
              ),
            ),
          ),
          _buildFooter(cs),
        ],
      ),
    );
  }

  Widget _buildBasicInfoCard(ColorScheme cs) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Basic Info',
                style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: cs.onSurface,
                    fontSize: 14)),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 140,
                  child: TextFormField(
                    controller: _codeCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Code *', isDense: true),
                    textCapitalization: TextCapitalization.characters,
                    inputFormatters: [
                      FilteringTextInputFormatter.allow(
                          RegExp(r'[A-Z0-9\-_]'))
                    ],
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? 'Required' : null,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _nameCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Name *', isDense: true),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? 'Required' : null,
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 90,
                  child: TextFormField(
                    controller: _priorityCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Priority', isDense: true),
                    keyboardType: TextInputType.number,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly
                    ],
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Required';
                      final n = int.tryParse(v.trim());
                      if (n == null || n < 1 || n > 99999) {
                        return '1–99999';
                      }
                      return null;
                    },
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 140,
                  child: DropdownButtonFormField<String>(
                    initialValue: _formStatus,
                    isDense: true,
                    decoration: const InputDecoration(
                        labelText: 'Status', isDense: true),
                    items: ['DRAFT', 'ACTIVE', 'INACTIVE']
                        .map((s) =>
                            DropdownMenuItem(value: s, child: Text(s)))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _formStatus = v);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _descriptionCtrl,
              decoration: const InputDecoration(
                  labelText: 'Description (optional)', isDense: true),
              maxLines: 2,
              minLines: 1,
            ),
            const SizedBox(height: 8),
            GestureDetector(
              onTap: () =>
                  setState(() => _showAdvanced = !_showAdvanced),
              child: Row(
                children: [
                  Icon(
                    _showAdvanced
                        ? Icons.expand_less
                        : Icons.expand_more,
                    size: 18,
                    color: cs.primary,
                  ),
                  const SizedBox(width: 4),
                  Text('Advanced',
                      style: TextStyle(
                          color: cs.primary, fontSize: 13)),
                ],
              ),
            ),
            if (_showAdvanced) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _effectiveFromCtrl,
                      decoration: InputDecoration(
                        labelText: 'Effective From',
                        isDense: true,
                        suffixIcon: IconButton(
                          icon: const Icon(Icons.calendar_today, size: 16),
                          onPressed: () =>
                              _pickDate(_effectiveFromCtrl),
                        ),
                      ),
                      readOnly: true,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _effectiveToCtrl,
                      decoration: InputDecoration(
                        labelText: 'Effective To',
                        isDense: true,
                        suffixIcon: IconButton(
                          icon: const Icon(Icons.calendar_today, size: 16),
                          onPressed: () => _pickDate(_effectiveToCtrl),
                        ),
                      ),
                      readOnly: true,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _pickDate(TextEditingController ctrl) async {
    final dt = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (dt != null && mounted) {
      ctrl.text =
          '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
    }
  }

  Widget _buildConditionsCard(ColorScheme cs) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('IF — all conditions match',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: cs.onSurface,
                        fontSize: 14)),
                const Spacer(),
                TextButton.icon(
                  onPressed: () => setState(() {
                    _conditions.add(_ConditionDraft(
                        sequence: _conditions.length + 1));
                  }),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Add'),
                ),
              ],
            ),
            if (_conditions.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  'No conditions — rule applies to all transactions',
                  style: TextStyle(
                      color: cs.onSurfaceVariant,
                      fontSize: 13,
                      fontStyle: FontStyle.italic),
                ),
              )
            else ...[
              const SizedBox(height: 8),
              // Header row
              Row(
                children: const [
                  SizedBox(
                      width: 36,
                      child: Text('Seq',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  SizedBox(
                      width: 160,
                      child: Text('Field Key',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  SizedBox(
                      width: 150,
                      child: Text('Operator',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  Expanded(
                      child: Text('Value',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 36),
                ],
              ),
              const Divider(height: 12),
              ..._conditions
                  .asMap()
                  .entries
                  .map((e) => _buildConditionRow(e.key, e.value, cs)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildConditionRow(int i, _ConditionDraft draft, ColorScheme cs) {
    final hideValue = _kNoValueOperators.contains(draft.operator);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 36,
            child: Text(
              '${draft.sequence}',
              style:
                  TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 160,
            child: DropdownButtonFormField<String>(
              initialValue: _kFieldKeys.contains(draft.fieldKey.text)
                  ? draft.fieldKey.text
                  : _kFieldKeys.first,
              isDense: true,
              decoration: const InputDecoration(
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              items: _kFieldKeys
                  .map((k) => DropdownMenuItem(
                      value: k,
                      child: Text(k,
                          style: const TextStyle(fontSize: 12))))
                  .toList(),
              onChanged: (v) {
                if (v != null) {
                  setState(() => draft.fieldKey.text = v);
                }
              },
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 150,
            child: DropdownButtonFormField<String>(
              initialValue: _kOperators.contains(draft.operator)
                  ? draft.operator
                  : _kOperators.first,
              isDense: true,
              decoration: const InputDecoration(
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              items: _kOperators
                  .map((o) => DropdownMenuItem(
                      value: o,
                      child: Text(o,
                          style: const TextStyle(fontSize: 12))))
                  .toList(),
              onChanged: (v) {
                if (v != null) setState(() => draft.operator = v);
              },
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: hideValue
                ? const SizedBox.shrink()
                : TextFormField(
                    controller: draft.value,
                    decoration: const InputDecoration(
                      isDense: true,
                      hintText: 'value',
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    ),
                    style: const TextStyle(fontSize: 13),
                  ),
          ),
          SizedBox(
            width: 36,
            child: IconButton(
              icon: Icon(Icons.remove_circle_outline,
                  size: 18, color: Colors.red.shade400),
              onPressed: () => setState(() {
                draft.dispose();
                _conditions.removeAt(i);
                // Re-sequence
                for (var j = 0; j < _conditions.length; j++) {
                  _conditions[j].sequence = j + 1;
                }
              }),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionsCard(ColorScheme cs) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: cs.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('THEN — apply these actions',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: cs.onSurface,
                        fontSize: 14)),
                const Spacer(),
                TextButton.icon(
                  onPressed: () => setState(() {
                    _actions.add(
                        _ActionDraft(sequence: _actions.length + 1));
                  }),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Add'),
                ),
              ],
            ),
            if (_actions.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  'No actions defined',
                  style: TextStyle(
                      color: cs.onSurfaceVariant,
                      fontSize: 13,
                      fontStyle: FontStyle.italic),
                ),
              )
            else ...[
              const SizedBox(height: 8),
              // Header row
              Row(
                children: const [
                  SizedBox(
                      width: 36,
                      child: Text('Seq',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  SizedBox(
                      width: 200,
                      child: Text('Action Type',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  Expanded(
                      child: Text('Target',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 8),
                  SizedBox(
                      width: 90,
                      child: Text('Rate %',
                          style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600))),
                  SizedBox(width: 36),
                ],
              ),
              const Divider(height: 12),
              ..._actions
                  .asMap()
                  .entries
                  .map((e) => _buildActionRow(e.key, e.value, cs)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildActionRow(int i, _ActionDraft draft, ColorScheme cs) {
    final showProfileField =
        draft.actionType == 'APPLY_TAX_PROFILE';
    final showComponentField = draft.actionType == 'APPLY_TAX_COMPONENT' ||
        draft.actionType == 'OVERRIDE_COMPONENT_PERCENTAGE';
    final showRateField =
        draft.actionType == 'OVERRIDE_COMPONENT_PERCENTAGE';

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 36,
            child: Text(
              '${draft.sequence}',
              style:
                  TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 200,
            child: DropdownButtonFormField<String>(
              initialValue: _kActionTypes.contains(draft.actionType)
                  ? draft.actionType
                  : _kActionTypes.first,
              isDense: true,
              decoration: const InputDecoration(
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              ),
              items: _kActionTypes
                  .map((t) => DropdownMenuItem(
                      value: t,
                      child: Text(t,
                          style: const TextStyle(fontSize: 11))))
                  .toList(),
              onChanged: (v) {
                if (v != null) setState(() => draft.actionType = v);
              },
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: showProfileField
                ? (_profiles.isEmpty
                    ? TextFormField(
                        controller: draft.targetProfileId,
                        decoration: const InputDecoration(
                          isDense: true,
                          hintText: 'Profile group code',
                          contentPadding:
                              EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                        ),
                        style: const TextStyle(fontSize: 13),
                      )
                    : DropdownButtonFormField<String>(
                        initialValue: _profiles.any((p) =>
                                p.id == draft.targetProfileId.text)
                            ? draft.targetProfileId.text
                            : null,
                        isDense: true,
                        decoration: const InputDecoration(
                          isDense: true,
                          hintText: 'Select profile',
                          contentPadding: EdgeInsets.symmetric(
                              horizontal: 8, vertical: 8),
                        ),
                        items: _profiles
                            .map((p) => DropdownMenuItem(
                                  value: p.id,
                                  child: Text('${p.code} — ${p.name}',
                                      style:
                                          const TextStyle(fontSize: 12)),
                                ))
                            .toList(),
                        onChanged: (v) {
                          if (v != null) {
                            setState(() => draft.targetProfileId.text = v);
                          }
                        },
                      ))
                : showComponentField
                    ? (_components.isEmpty
                        ? TextFormField(
                            controller: draft.targetComponentId,
                            decoration: const InputDecoration(
                              isDense: true,
                              hintText: 'Component ID',
                              contentPadding: EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 8),
                            ),
                            style: const TextStyle(fontSize: 13),
                          )
                        : DropdownButtonFormField<String>(
                            initialValue: _components.any((c) =>
                                    c.id ==
                                    draft.targetComponentId.text)
                                ? draft.targetComponentId.text
                                : null,
                            isDense: true,
                            decoration: const InputDecoration(
                              isDense: true,
                              hintText: 'Select component',
                              contentPadding: EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 8),
                            ),
                            items: _components
                                .map((c) => DropdownMenuItem(
                                      value: c.id,
                                      child: Text(
                                          '${c.code} — ${c.name}',
                                          style: const TextStyle(
                                              fontSize: 12)),
                                    ))
                                .toList(),
                            onChanged: (v) {
                              if (v != null) {
                                setState(() =>
                                    draft.targetComponentId.text = v);
                              }
                            },
                          ))
                    : const SizedBox.shrink(),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 90,
            child: showRateField
                ? TextFormField(
                    controller: draft.percentageOverride,
                    decoration: const InputDecoration(
                      isDense: true,
                      hintText: '0.00',
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    ),
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    style: const TextStyle(fontSize: 13),
                  )
                : const SizedBox.shrink(),
          ),
          SizedBox(
            width: 36,
            child: IconButton(
              icon: Icon(Icons.remove_circle_outline,
                  size: 18, color: Colors.red.shade400),
              onPressed: () => setState(() {
                draft.dispose();
                _actions.removeAt(i);
                for (var j = 0; j < _actions.length; j++) {
                  _actions[j].sequence = j + 1;
                }
              }),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFooter(ColorScheme cs) {
    final isDeleted = _selected?.isDeleted ?? false;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outlineVariant)),
      ),
      child: Row(
        children: [
          if (!_isNew && _selected != null) ...[
            if (!isDeleted)
              OutlinedButton.icon(
                onPressed: _saving ? null : _cloneRule,
                icon: const Icon(Icons.copy_outlined, size: 16),
                label: const Text('Clone as Draft'),
              ),
            const SizedBox(width: 8),
            TextButton(
              onPressed: _saving ? null : _deleteOrRestore,
              style: TextButton.styleFrom(
                foregroundColor:
                    isDeleted ? Colors.green.shade700 : Colors.red.shade600,
              ),
              child: Text(isDeleted ? 'Restore' : 'Delete'),
            ),
          ],
          const Spacer(),
          OutlinedButton(
            onPressed: _saving ? null : _cancel,
            child: const Text('Cancel'),
          ),
          const SizedBox(width: 12),
          FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.save_outlined, size: 16),
            label: Text(_saving ? 'Saving…' : 'Save'),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2: Priority Manager
// ═══════════════════════════════════════════════════════════════════════════════

class _TaxPriorityTab extends StatefulWidget {
  const _TaxPriorityTab({required this.api, required this.permissions});
  final ApiClient api;
  final PermissionService permissions;

  @override
  State<_TaxPriorityTab> createState() => _TaxPriorityTabState();
}

class _PriorityEditItem {
  final TaxRulePriorityRecord record;
  final TextEditingController priorityCtrl;
  bool dirty = false;

  _PriorityEditItem(this.record)
      : priorityCtrl =
            TextEditingController(text: record.priority.toString());

  int get currentPriority =>
      int.tryParse(priorityCtrl.text) ?? record.priority;

  void dispose() => priorityCtrl.dispose();
}

class _TaxPriorityTabState extends State<_TaxPriorityTab> {
  List<_PriorityEditItem> _items = [];
  bool _loading = false;
  bool _saving = false;
  String? _error;
  String? _success;

  @override
  void initState() {
    super.initState();
    _loadPriorities();
  }

  @override
  void dispose() {
    for (final item in _items) {
      item.dispose();
    }
    super.dispose();
  }

  Future<void> _loadPriorities() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = List<TaxRulePriorityRecord>.from(
        await widget.api.taxRulePriorities(),
      );
      if (!mounted) return;
      list.sort((a, b) => a.priority.compareTo(b.priority));
      for (final item in _items) {
        item.dispose();
      }
      setState(() {
        _items = list.map(_PriorityEditItem.new).toList();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _swapPriority(int i, int j) {
    if (i < 0 || j < 0 || i >= _items.length || j >= _items.length) return;
    setState(() {
      final pi = _items[i].currentPriority;
      final pj = _items[j].currentPriority;
      _items[i].priorityCtrl.text = pj.toString();
      _items[j].priorityCtrl.text = pi.toString();
      _items[i].dirty = true;
      _items[j].dirty = true;
      // Re-sort by current priority
      _items.sort((a, b) => a.currentPriority.compareTo(b.currentPriority));
    });
  }

  Future<void> _saveOrder() async {
    final dirty = _items.where((item) => item.dirty).toList();
    if (dirty.isEmpty) {
      setState(() => _success = 'No changes to save.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
      _success = null;
    });
    try {
      await Future.wait(dirty.map((item) => widget.api.updateTaxRule(
            item.record.id,
            {
              'code': item.record.code,
              'name': item.record.name,
              'priority': item.currentPriority,
              'status': item.record.status,
            },
          )));
      if (!mounted) return;
      await _loadPriorities();
      if (!mounted) return;
      setState(() => _success = 'Priority order saved successfully.');
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Evaluation Order',
                        style: TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 16,
                            color: cs.onSurface)),
                    const SizedBox(height: 2),
                    Text(
                      'First matching rule wins. Lower priority number = evaluated first.',
                      style: TextStyle(
                          fontSize: 12, color: cs.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.refresh),
                tooltip: 'Reload',
                onPressed: _loading ? null : _loadPriorities,
              ),
            ],
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: _ErrorBanner(
              message: _error!,
              onClose: () => setState(() => _error = null),
              onRetry: _loadPriorities,
            ),
          ),
        if (_success != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: _SuccessBanner(
              message: _success!,
              onClose: () => setState(() => _success = null),
            ),
          ),
        const SizedBox(height: 8),
        // Table header
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Row(
            children: [
              const SizedBox(
                  width: 80,
                  child: Text('Priority',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 8),
              const SizedBox(
                  width: 120,
                  child: Text('Code',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 8),
              const Expanded(
                  child: Text('Name',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 8),
              const SizedBox(
                  width: 80,
                  child: Text('Status',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 8),
              const SizedBox(
                  width: 80,
                  child: Text('Conditions',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 8),
              const SizedBox(
                  width: 60,
                  child: Text('Actions',
                      style: TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w600))),
              const SizedBox(width: 60),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _items.isEmpty
                  ? const Center(
                      child: Text('No rules found.',
                          style: TextStyle(color: Colors.grey)))
                  : ListView.separated(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 4),
                      itemCount: _items.length,
                      separatorBuilder: (_, __) =>
                          const Divider(height: 1),
                      itemBuilder: (_, i) =>
                          _buildPriorityRow(i, _items[i], cs),
                    ),
        ),
        const Divider(height: 1),
        // Footer
        Container(
          padding:
              const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          color: cs.surface,
          child: Row(
            children: [
              Text(
                '${_items.length} rule${_items.length != 1 ? 's' : ''}',
                style:
                    TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
              ),
              const Spacer(),
              FilledButton.icon(
                onPressed: _saving || _loading ? null : _saveOrder,
                icon: _saving
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.save_outlined, size: 16),
                label: Text(_saving ? 'Saving…' : 'Save Order'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildPriorityRow(
      int i, _PriorityEditItem item, ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 80,
            child: TextFormField(
              controller: item.priorityCtrl,
              decoration: const InputDecoration(
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              ),
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              style: const TextStyle(fontSize: 13),
              onChanged: (_) => setState(() => item.dirty = true),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 120,
            child: Text(
              item.record.code,
              style: const TextStyle(
                  fontWeight: FontWeight.w600, fontSize: 13),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              item.record.name,
              style: const TextStyle(fontSize: 13),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 80,
            child: _StatusChip(status: item.record.status),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 80,
            child: Text(
              '${item.record.conditionCount}',
              style: const TextStyle(fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 60,
            child: Text(
              '${item.record.actionCount}',
              style: const TextStyle(fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ),
          SizedBox(
            width: 60,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  icon: const Icon(Icons.keyboard_arrow_up, size: 18),
                  onPressed: i > 0 ? () => _swapPriority(i, i - 1) : null,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: 'Move up',
                ),
                IconButton(
                  icon:
                      const Icon(Icons.keyboard_arrow_down, size: 18),
                  onPressed: i < _items.length - 1
                      ? () => _swapPriority(i, i + 1)
                      : null,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: 'Move down',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Shared Widgets ───────────────────────────────────────────────────────────

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (status.toUpperCase()) {
      'ACTIVE' => (Colors.green.shade100, Colors.green.shade800),
      'DRAFT' => (Colors.orange.shade100, Colors.orange.shade800),
      'INACTIVE' => (Colors.grey.shade200, Colors.grey.shade700),
      'DELETED' => (Colors.red.shade100, Colors.red.shade800),
      _ => (Colors.grey.shade200, Colors.grey.shade700),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
      child: Text(status,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: fg)),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({
    required this.message,
    required this.onClose,
    this.onRetry,
  });
  final String message;
  final VoidCallback onClose;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        border: Border.all(color: Colors.red.shade200),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: Colors.red.shade700, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message,
                style:
                    TextStyle(color: Colors.red.shade800, fontSize: 13)),
          ),
          if (onRetry != null)
            TextButton(
              onPressed: onRetry,
              child: const Text('Retry'),
            ),
          IconButton(
            icon: const Icon(Icons.close, size: 16),
            onPressed: onClose,
            color: Colors.red.shade700,
          ),
        ],
      ),
    );
  }
}

class _SuccessBanner extends StatelessWidget {
  const _SuccessBanner({required this.message, required this.onClose});
  final String message;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.green.shade50,
        border: Border.all(color: Colors.green.shade300),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.check_circle_outline,
              color: Colors.green.shade700, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message,
                style: TextStyle(
                    color: Colors.green.shade800, fontSize: 13)),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 16),
            onPressed: onClose,
            color: Colors.green.shade700,
          ),
        ],
      ),
    );
  }
}
