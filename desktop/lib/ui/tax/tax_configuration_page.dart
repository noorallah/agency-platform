// Tax Configuration page — two tabs: Tax Systems | Tax Profiles
// Each tab uses master-detail split layout (left list + right edit panel)

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../core/api/api_client.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/tax_framework.dart';

// ─── Helper: Component Draft (Tax System tab) ─────────────────────────────────

class _ComponentDraft {
  String? id;
  bool deleted = false;
  final TextEditingController code;
  final TextEditingController name;
  final TextEditingController percentage;
  final TextEditingController calculationOrder;
  bool recoverable;
  String status;

  _ComponentDraft({
    this.id,
    String? code,
    String? name,
    String? percentage,
    String? calculationOrder,
    this.recoverable = false,
    this.status = 'ACTIVE',
  })  : code = TextEditingController(text: code ?? ''),
        name = TextEditingController(text: name ?? ''),
        percentage = TextEditingController(text: percentage ?? '0'),
        calculationOrder = TextEditingController(text: calculationOrder ?? '0');

  void dispose() {
    code.dispose();
    name.dispose();
    percentage.dispose();
    calculationOrder.dispose();
  }

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'code': code.text.trim().toUpperCase(),
        'name': name.text.trim(),
        'percentage': double.tryParse(percentage.text) ?? 0.0,
        'calculation_order': int.tryParse(calculationOrder.text) ?? 0,
        'recoverable': recoverable,
        'status': status,
      };
}

// ─── Helper: Component Assignment (Tax Profile tab) ──────────────────────────

class _ComponentAssignment {
  final TaxComponentRecord component;
  bool selected;
  final TextEditingController rateCtrl;
  bool recoverable;

  _ComponentAssignment({
    required this.component,
    this.selected = false,
    String? initialRate,
    this.recoverable = false,
  }) : rateCtrl = TextEditingController(
            text: initialRate ?? component.percentage);

  double get rate => double.tryParse(rateCtrl.text) ?? 0.0;

  void dispose() => rateCtrl.dispose();
}

// ─── Main Page ────────────────────────────────────────────────────────────────

class TaxConfigurationPage extends StatefulWidget {
  const TaxConfigurationPage({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TaxConfigurationPage> createState() => _TaxConfigurationPageState();
}

class _TaxConfigurationPageState extends State<TaxConfigurationPage>
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
                  icon: Icon(Icons.account_balance_outlined, size: 18),
                  text: 'Tax Systems'),
              Tab(
                  icon: Icon(Icons.receipt_long_outlined, size: 18),
                  text: 'Tax Profiles'),
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
              TaxSystemsTab(api: widget.api, permissions: widget.permissions),
              TaxProfilesTab(api: widget.api, permissions: widget.permissions),
            ],
          ),
        ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1: Tax Systems
// ═══════════════════════════════════════════════════════════════════════════════

class TaxSystemsTab extends StatefulWidget {
  const TaxSystemsTab({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TaxSystemsTab> createState() => _TaxSystemsTabState();
}

class _TaxSystemsTabState extends State<TaxSystemsTab> {
  // List state
  List<TaxSystemRecord> _systems = [];
  List<TaxSystemRecord> _filtered = [];
  bool _listLoading = false;
  String? _listError;
  final TextEditingController _search = TextEditingController();
  String _statusFilter = 'All';

  // Detail state
  TaxSystemRecord? _selected;
  bool _isNew = false;
  bool _detailLoading = false;
  bool _saving = false;
  String? _detailError;
  String? _detailSuccess;
  bool _showAdvanced = false;

  // Form controllers
  final _codeCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _displayNameCtrl = TextEditingController();
  final _descriptionCtrl = TextEditingController();
  final _effectiveFromCtrl = TextEditingController();
  final _effectiveToCtrl = TextEditingController();
  String _formStatus = 'ACTIVE';
  final List<_ComponentDraft> _components = [];
  final _formKey = GlobalKey<FormState>();
  final _detailScroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _loadSystems();
    _search.addListener(_applyFilter);
  }

  @override
  void dispose() {
    _search.dispose();
    _codeCtrl.dispose();
    _nameCtrl.dispose();
    _displayNameCtrl.dispose();
    _descriptionCtrl.dispose();
    _effectiveFromCtrl.dispose();
    _effectiveToCtrl.dispose();
    _detailScroll.dispose();
    for (final c in _components) {
      c.dispose();
    }
    super.dispose();
  }

  // ─── Data loading ──────────────────────────────────────────────────────────

  Future<void> _loadSystems() async {
    setState(() {
      _listLoading = true;
      _listError = null;
    });
    try {
      final resp = await widget.api.request(
        'GET',
        '/api/v1/tax-framework/systems',
        query: {'page': '1', 'page_size': '100'},
      );
      if (!mounted) return;
      final raw = resp['data'];
      final list = raw is List
          ? raw
              .whereType<Map>()
              .map((e) => TaxSystemRecord.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : <TaxSystemRecord>[];
      setState(() {
        _systems = list;
        _applyFilter();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _listError = e.message);
    } finally {
      if (mounted) setState(() => _listLoading = false);
    }
  }

  Future<void> _loadDetail(TaxSystemRecord system) async {
    setState(() {
      _selected = system;
      _isNew = false;
      _detailLoading = true;
      _detailError = null;
      _detailSuccess = null;
    });
    try {
      final resp = await widget.api.request(
        'GET',
        '/api/v1/tax-framework/setup/${system.id}',
      );
      if (!mounted) return;
      final data = resp['data'] as Map<String, dynamic>? ?? {};
      final sys = data['system'] as Map<String, dynamic>? ?? {};
      final rawComp = (data['components'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();

      for (final c in _components) {
        c.dispose();
      }
      _components.clear();
      for (final c in rawComp) {
        _components.add(_ComponentDraft(
          id: stringValue(c['id']),
          code: stringValue(c['code']),
          name: stringValue(c['name']),
          percentage: (c['percentage'] ?? 0).toString(),
          calculationOrder: (c['calculation_order'] ?? 0).toString(),
          recoverable: c['recoverable'] as bool? ?? false,
          status: stringValue(c['status']).isEmpty
              ? 'ACTIVE'
              : stringValue(c['status']),
        ));
      }

      setState(() {
        _codeCtrl.text = stringValue(sys['code']);
        _nameCtrl.text = stringValue(sys['name']);
        _displayNameCtrl.text = stringValue(sys['display_name']);
        _descriptionCtrl.text = stringValue(sys['description']);
        _effectiveFromCtrl.text = stringValue(sys['effective_from']);
        _effectiveToCtrl.text = stringValue(sys['effective_to']);
        _formStatus =
            stringValue(sys['status']).isEmpty ? 'ACTIVE' : stringValue(sys['status']);
        _showAdvanced = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _detailError = e.message);
    } finally {
      if (mounted) setState(() => _detailLoading = false);
    }
  }

  void _newSystem() {
    for (final c in _components) {
      c.dispose();
    }
    _components.clear();
    _components.add(_ComponentDraft());
    setState(() {
      _selected = null;
      _isNew = true;
      _detailError = null;
      _detailSuccess = null;
      _codeCtrl.clear();
      _nameCtrl.clear();
      _displayNameCtrl.clear();
      _descriptionCtrl.clear();
      _effectiveFromCtrl.clear();
      _effectiveToCtrl.clear();
      _formStatus = 'ACTIVE';
      _showAdvanced = false;
    });
  }

  void _cancel() {
    for (final c in _components) {
      c.dispose();
    }
    _components.clear();
    setState(() {
      _selected = null;
      _isNew = false;
      _detailError = null;
      _detailSuccess = null;
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _detailError = null;
      _detailSuccess = null;
    });
    final payload = <String, dynamic>{
      'code': _codeCtrl.text.trim().toUpperCase(),
      'name': _nameCtrl.text.trim(),
      'display_name': _displayNameCtrl.text.trim().isEmpty
          ? null
          : _displayNameCtrl.text.trim(),
      'description': _descriptionCtrl.text.trim().isEmpty
          ? null
          : _descriptionCtrl.text.trim(),
      'status': _formStatus,
      'display_order': 1,
      if (_effectiveFromCtrl.text.trim().isNotEmpty)
        'effective_from': _effectiveFromCtrl.text.trim(),
      if (_effectiveToCtrl.text.trim().isNotEmpty)
        'effective_to': _effectiveToCtrl.text.trim(),
      'components': _components
          .where((c) => !c.deleted)
          .map((c) => c.toJson())
          .toList(),
      'profiles': const [],
    };
    try {
      if (_isNew) {
        final resp = await widget.api
            .request('POST', '/api/v1/tax-framework/setup', body: payload);
        final sysData = resp['data'] is Map
            ? (resp['data'] as Map<dynamic, dynamic>)['system']
            : null;
        final newId = stringValue(
            sysData is Map ? sysData['id'] : null);
        if (!mounted) return;
        await _loadSystems();
        if (!mounted) return;
        setState(() {
          _isNew = false;
          _detailSuccess = 'Tax system created successfully.';
          if (newId.isNotEmpty) {
            final match =
                _systems.where((s) => s.id == newId).toList();
            if (match.isNotEmpty) _selected = match.first;
          }
        });
      } else {
        final id = _selected!.id;
        await widget.api.request(
          'PUT',
          '/api/v1/tax-framework/setup/$id',
          body: payload,
        );
        if (!mounted) return;
        await _loadSystems();
        if (!mounted) return;
        setState(() {
          _detailSuccess = 'Tax system saved successfully.';
          final match = _systems.where((s) => s.id == id).toList();
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

  Future<void> _deleteSystem(TaxSystemRecord system) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Tax System?'),
        content: Text(
            'This will delete "${system.name}". This action cannot be undone.'),
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
          .request('DELETE', '/api/v1/tax-framework/systems/${system.id}');
      if (!mounted) return;
      _cancel();
      await _loadSystems();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _detailError = e.message);
    }
  }

  // ─── Filter ────────────────────────────────────────────────────────────────

  void _applyFilter() {
    final q = _search.text.trim().toLowerCase();
    setState(() {
      _filtered = _systems.where((s) {
        final matchStatus = _statusFilter == 'All' ||
            s.status.toUpperCase() == _statusFilter.toUpperCase();
        final matchSearch = q.isEmpty ||
            s.code.toLowerCase().contains(q) ||
            s.name.toLowerCase().contains(q);
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
              width: constraints.maxWidth * 0.35,
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
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            controller: _search,
            decoration: InputDecoration(
              hintText: 'Search systems…',
              prefixIcon: const Icon(Icons.search, size: 18),
              isDense: true,
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8)),
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
              onRetry: _loadSystems,
            ),
          ),
        if (_listLoading && _systems.isEmpty)
          const Expanded(
              child: Center(child: CircularProgressIndicator()))
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: _loadSystems,
              child: _filtered.isEmpty
                  ? const Center(
                      child: Text('No tax systems found.',
                          style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      itemCount: _filtered.length,
                      itemBuilder: (_, i) =>
                          _buildSystemCard(_filtered[i]),
                    ),
            ),
          ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.all(12),
          child: SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _newSystem,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('New Tax System'),
              style: OutlinedButton.styleFrom(
                foregroundColor: cs.primary,
                side: BorderSide(color: cs.primary),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStatusChips() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: ['All', 'ACTIVE', 'DRAFT', 'INACTIVE']
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

  Widget _buildSystemCard(TaxSystemRecord system) {
    final cs = Theme.of(context).colorScheme;
    final isSelected = _selected?.id == system.id;
    // We don't have components in list view, so show nothing extra here
    return GestureDetector(
      onTap: () => _loadDetail(system),
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
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text.rich(
                      TextSpan(children: [
                        TextSpan(
                          text: system.code,
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        TextSpan(
                          text: '  ${system.name}',
                          style: TextStyle(
                              color: cs.onSurfaceVariant, fontSize: 13),
                        ),
                      ]),
                    ),
                  ),
                  _StatusChip(status: system.status),
                ],
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
            Icon(Icons.account_balance_outlined,
                size: 48, color: Colors.grey),
            SizedBox(height: 12),
            Text('Select a tax system to view or edit',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }

    if (_detailLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    final cs = Theme.of(context).colorScheme;

    return Form(
      key: _formKey,
      child: Column(
        children: [
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
                    _buildSystemInfoCard(cs),
                    const SizedBox(height: 16),
                    _buildComponentsCard(cs),
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

  Widget _buildSystemInfoCard(ColorScheme cs) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('System Info',
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
                    validator: (v) => (v == null || v.trim().isEmpty)
                        ? 'Required'
                        : null,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _nameCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Name *', isDense: true),
                    validator: (v) => (v == null || v.trim().isEmpty)
                        ? 'Required'
                        : null,
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
                    items: ['ACTIVE', 'DRAFT', 'INACTIVE']
                        .map((s) => DropdownMenuItem(
                            value: s, child: Text(s)))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _formStatus = v);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _displayNameCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Display Name', isDense: true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    controller: _descriptionCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Description (optional)',
                        isDense: true),
                    maxLines: 1,
                  ),
                ),
              ],
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
                          icon:
                              const Icon(Icons.calendar_today, size: 16),
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
                          icon:
                              const Icon(Icons.calendar_today, size: 16),
                          onPressed: () =>
                              _pickDate(_effectiveToCtrl),
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

  Widget _buildComponentsCard(ColorScheme cs) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Tax Components',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: cs.onSurface,
                        fontSize: 14)),
                const Spacer(),
                TextButton.icon(
                  onPressed: () =>
                      setState(() => _components.add(_ComponentDraft())),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Add Component'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // Header row
            Row(
              children: const [
                SizedBox(width: 100, child: Text('Code', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 8),
                Expanded(child: Text('Name', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 8),
                SizedBox(width: 90, child: Text('Rate %', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 8),
                SizedBox(width: 80, child: Text('Order', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 8),
                SizedBox(width: 100, child: Text('Recoverable', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 8),
                SizedBox(width: 110, child: Text('Status', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                SizedBox(width: 40),
              ],
            ),
            const Divider(),
            ..._components.asMap().entries.map((entry) {
              final i = entry.key;
              final comp = entry.value;
              return _buildComponentRow(i, comp, cs);
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildComponentRow(int i, _ComponentDraft comp, ColorScheme cs) {
    final deleted = comp.deleted;
    return Opacity(
      opacity: deleted ? 0.45 : 1.0,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            SizedBox(
              width: 100,
              child: TextFormField(
                controller: comp.code,
                enabled: !deleted,
                decoration: const InputDecoration(
                    isDense: true,
                    hintText: 'CGST',
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
                textCapitalization: TextCapitalization.characters,
                style: deleted
                    ? const TextStyle(
                        decoration: TextDecoration.lineThrough)
                    : null,
                validator: (v) => (!deleted && (v == null || v.trim().isEmpty))
                    ? 'Required'
                    : null,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextFormField(
                controller: comp.name,
                enabled: !deleted,
                decoration: const InputDecoration(
                    isDense: true,
                    hintText: 'Central GST',
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
                style: deleted
                    ? const TextStyle(
                        decoration: TextDecoration.lineThrough)
                    : null,
                validator: (v) => (!deleted && (v == null || v.trim().isEmpty))
                    ? 'Required'
                    : null,
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 90,
              child: TextFormField(
                controller: comp.percentage,
                enabled: !deleted,
                decoration: const InputDecoration(
                    isDense: true,
                    hintText: '9.0',
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 80,
              child: TextFormField(
                controller: comp.calculationOrder,
                enabled: !deleted,
                decoration: const InputDecoration(
                    isDense: true,
                    hintText: '1',
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
                keyboardType: TextInputType.number,
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 100,
              child: Row(
                children: [
                  Checkbox(
                    value: comp.recoverable,
                    onChanged: deleted
                        ? null
                        : (v) => setState(
                            () => comp.recoverable = v ?? false),
                  ),
                  const Text('Yes', style: TextStyle(fontSize: 12)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 110,
              child: DropdownButtonFormField<String>(
                initialValue: comp.status,
                isDense: true,
                decoration: const InputDecoration(
                    isDense: true,
                    contentPadding:
                        EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
                items: ['ACTIVE', 'INACTIVE']
                    .map((s) =>
                        DropdownMenuItem(value: s, child: Text(s, style: const TextStyle(fontSize: 12))))
                    .toList(),
                onChanged: deleted
                    ? null
                    : (v) {
                        if (v != null) {
                          setState(() => comp.status = v);
                        }
                      },
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 40,
              child: deleted
                  ? Tooltip(
                      message: 'Restore',
                      child: IconButton(
                        icon: const Icon(Icons.restore,
                            size: 18, color: Colors.green),
                        onPressed: () =>
                            setState(() => comp.deleted = false),
                      ),
                    )
                  : Tooltip(
                      message: 'Remove',
                      child: IconButton(
                        icon: Icon(Icons.delete_outline,
                            size: 18, color: Colors.red.shade400),
                        onPressed: () => setState(() {
                          if (comp.id != null) {
                            comp.deleted = true;
                          } else {
                            comp.dispose();
                            _components.removeAt(i);
                          }
                        }),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFooter(ColorScheme cs) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outlineVariant)),
      ),
      child: Row(
        children: [
          if (!_isNew && _selected != null)
            OutlinedButton.icon(
              onPressed: () => _deleteSystem(_selected!),
              icon: Icon(Icons.delete_outline,
                  size: 16, color: Colors.red.shade600),
              label: Text('Delete',
                  style: TextStyle(color: Colors.red.shade600)),
              style: OutlinedButton.styleFrom(
                  side: BorderSide(color: Colors.red.shade300)),
            ),
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
// TAB 2: Tax Profiles
// ═══════════════════════════════════════════════════════════════════════════════

class TaxProfilesTab extends StatefulWidget {
  const TaxProfilesTab({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  State<TaxProfilesTab> createState() => _TaxProfilesTabState();
}

class _TaxProfilesTabState extends State<TaxProfilesTab> {
  // List state
  List<TaxProfileRecord> _profiles = [];
  List<TaxProfileRecord> _filtered = [];
  bool _listLoading = false;
  String? _listError;
  final TextEditingController _search = TextEditingController();
  String _statusFilter = 'All';

  // Systems for dropdown
  List<TaxSystemRecord> _systems = [];

  // Detail state
  TaxProfileRecord? _selected;
  bool _isNew = false;
  bool _saving = false;
  String? _detailError;
  String? _detailSuccess;
  bool _showAdvanced = false;

  // Form controllers
  final _codeCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _labelCtrl = TextEditingController();
  final _descriptionCtrl = TextEditingController();
  final _effectiveFromCtrl = TextEditingController();
  final _effectiveToCtrl = TextEditingController();
  String _formStatus = 'ACTIVE';
  String? _selectedSystemId;

  // Component assignments
  List<_ComponentAssignment> _assignments = [];
  bool _compsLoading = false;

  final _formKey = GlobalKey<FormState>();
  final _detailScroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _loadAll();
    _search.addListener(_applyFilter);
  }

  @override
  void dispose() {
    _search.dispose();
    _codeCtrl.dispose();
    _nameCtrl.dispose();
    _labelCtrl.dispose();
    _descriptionCtrl.dispose();
    _effectiveFromCtrl.dispose();
    _effectiveToCtrl.dispose();
    _detailScroll.dispose();
    for (final a in _assignments) {
      a.dispose();
    }
    super.dispose();
  }

  // ─── Data loading ──────────────────────────────────────────────────────────

  Future<void> _loadAll() async {
    await Future.wait([_loadProfiles(), _loadSystems()]);
  }

  Future<void> _loadProfiles() async {
    setState(() {
      _listLoading = true;
      _listError = null;
    });
    try {
      final resp = await widget.api.request(
        'GET',
        '/api/v1/tax-framework/profiles',
        query: {'page': '1', 'page_size': '100'},
      );
      if (!mounted) return;
      final raw = resp['data'];
      final list = raw is List
          ? raw
              .whereType<Map>()
              .map((e) =>
                  TaxProfileRecord.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : <TaxProfileRecord>[];
      setState(() {
        _profiles = list;
        _applyFilter();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _listError = e.message);
    } finally {
      if (mounted) setState(() => _listLoading = false);
    }
  }

  Future<void> _loadSystems() async {
    try {
      final resp = await widget.api.request(
        'GET',
        '/api/v1/tax-framework/systems',
        query: {'page': '1', 'page_size': '100', 'status': 'ACTIVE'},
      );
      if (!mounted) return;
      final raw = resp['data'];
      final list = raw is List
          ? raw
              .whereType<Map>()
              .map((e) =>
                  TaxSystemRecord.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : <TaxSystemRecord>[];
      if (mounted) setState(() => _systems = list);
    } on ApiException catch (_) {
      // silent — list may be empty
    }
  }

  Future<void> _loadComponentsForSystem(String systemId) async {
    setState(() {
      _compsLoading = true;
      for (final a in _assignments) {
        a.dispose();
      }
      _assignments = [];
    });
    try {
      final resp = await widget.api.request(
        'GET',
        '/api/v1/tax-framework/components',
        query: {
          'tax_system_id': systemId,
          'page': '1',
          'page_size': '100',
        },
      );
      if (!mounted) return;
      final raw = resp['data'];
      final comps = raw is List
          ? raw
              .whereType<Map>()
              .map((e) =>
                  TaxComponentRecord.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : <TaxComponentRecord>[];

      // If editing, pre-fill from selected profile's components
      final profileComps = _selected?.components ?? [];
      final assignments = comps.map((comp) {
        final existing = profileComps.where(
            (pc) => pc.taxComponentId == comp.id).toList();
        if (existing.isNotEmpty) {
          return _ComponentAssignment(
            component: comp,
            selected: true,
            initialRate: existing.first.percentage,
            recoverable: false,
          );
        }
        return _ComponentAssignment(
          component: comp,
          selected: false,
          recoverable: false,
        );
      }).toList();

      if (mounted) setState(() => _assignments = assignments);
    } on ApiException catch (_) {
      // silent
    } finally {
      if (mounted) setState(() => _compsLoading = false);
    }
  }

  void _openProfile(TaxProfileRecord profile) {
    setState(() {
      _selected = profile;
      _isNew = false;
      _detailError = null;
      _detailSuccess = null;
      _codeCtrl.text = profile.code;
      _nameCtrl.text = profile.name;
      _labelCtrl.text = profile.label;
      _descriptionCtrl.text = '';
      _effectiveFromCtrl.clear();
      _effectiveToCtrl.clear();
      _formStatus =
          profile.status.isEmpty ? 'ACTIVE' : profile.status;
      _selectedSystemId =
          profile.taxSystemId.isEmpty ? null : profile.taxSystemId;
      _showAdvanced = false;
    });
    if (_selectedSystemId != null) {
      _loadComponentsForSystem(_selectedSystemId!);
    }
  }

  void _newProfile() {
    for (final a in _assignments) {
      a.dispose();
    }
    setState(() {
      _selected = null;
      _isNew = true;
      _detailError = null;
      _detailSuccess = null;
      _codeCtrl.clear();
      _nameCtrl.clear();
      _labelCtrl.clear();
      _descriptionCtrl.clear();
      _effectiveFromCtrl.clear();
      _effectiveToCtrl.clear();
      _formStatus = 'ACTIVE';
      _selectedSystemId = null;
      _assignments = [];
      _showAdvanced = false;
    });
  }

  void _cancel() {
    for (final a in _assignments) {
      a.dispose();
    }
    setState(() {
      _selected = null;
      _isNew = false;
      _detailError = null;
      _detailSuccess = null;
      _assignments = [];
    });
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_selectedSystemId == null) {
      setState(() => _detailError = 'Please select a tax system.');
      return;
    }
    setState(() {
      _saving = true;
      _detailError = null;
      _detailSuccess = null;
    });

    final components = _assignments
        .where((a) => a.selected)
        .toList()
        .asMap()
        .entries
        .map((e) => {
              'tax_component_id': e.value.component.id,
              'percentage': e.value.rate,
              'calculation_order': e.key + 1,
              'recoverable': e.value.recoverable,
              'included_in_price': false,
            })
        .toList();

    final payload = <String, dynamic>{
      'tax_system_id': _selectedSystemId,
      'code': _codeCtrl.text.trim().toUpperCase(),
      'name': _nameCtrl.text.trim(),
      'label': _labelCtrl.text.trim().isEmpty
          ? null
          : _labelCtrl.text.trim(),
      'description': _descriptionCtrl.text.trim().isEmpty
          ? null
          : _descriptionCtrl.text.trim(),
      'status': _formStatus,
      'display_order': 1,
      if (_effectiveFromCtrl.text.trim().isNotEmpty)
        'effective_from': _effectiveFromCtrl.text.trim(),
      if (_effectiveToCtrl.text.trim().isNotEmpty)
        'effective_to': _effectiveToCtrl.text.trim(),
      'components': components,
    };

    try {
      if (_isNew) {
        final resp = await widget.api.request(
          'POST',
          '/api/v1/tax-framework/profiles',
          body: payload,
        );
        final newId = stringValue(
            resp['data'] is Map ? resp['data']['id'] : null);
        if (!mounted) return;
        await _loadProfiles();
        if (!mounted) return;
        setState(() {
          _isNew = false;
          _detailSuccess = 'Tax profile created successfully.';
          if (newId.isNotEmpty) {
            final match =
                _profiles.where((p) => p.id == newId).toList();
            if (match.isNotEmpty) _selected = match.first;
          }
        });
      } else {
        final id = _selected!.id;
        await widget.api.request(
          'PUT',
          '/api/v1/tax-framework/profiles/$id',
          body: payload,
        );
        if (!mounted) return;
        await _loadProfiles();
        if (!mounted) return;
        setState(() {
          _detailSuccess = 'Tax profile saved successfully.';
          final match = _profiles.where((p) => p.id == id).toList();
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

  Future<void> _deleteProfile(TaxProfileRecord profile) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Tax Profile?'),
        content: Text(
            'This will delete "${profile.name}". This action cannot be undone.'),
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
          .request('DELETE', '/api/v1/tax-framework/profiles/${profile.id}');
      if (!mounted) return;
      _cancel();
      await _loadProfiles();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _detailError = e.message);
    }
  }

  void _cloneProfile() {
    if (_selected == null) return;
    final src = _selected!;
    setState(() {
      _isNew = true;
      _selected = null;
      _codeCtrl.text = '${src.code}_COPY';
      _nameCtrl.text = '${src.name} (Copy)';
      _labelCtrl.text = src.label;
      _formStatus = 'DRAFT';
      _detailSuccess = null;
      _detailError = null;
    });
  }

  // ─── Filter ────────────────────────────────────────────────────────────────

  void _applyFilter() {
    final q = _search.text.trim().toLowerCase();
    setState(() {
      _filtered = _profiles.where((p) {
        final matchStatus = _statusFilter == 'All' ||
            p.status.toUpperCase() == _statusFilter.toUpperCase();
        final matchSearch = q.isEmpty ||
            p.code.toLowerCase().contains(q) ||
            p.name.toLowerCase().contains(q);
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
              width: constraints.maxWidth * 0.35,
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
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            controller: _search,
            decoration: InputDecoration(
              hintText: 'Search profiles…',
              prefixIcon: const Icon(Icons.search, size: 18),
              isDense: true,
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8)),
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
              onRetry: _loadProfiles,
            ),
          ),
        if (_listLoading && _profiles.isEmpty)
          const Expanded(
              child: Center(child: CircularProgressIndicator()))
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: _loadProfiles,
              child: _filtered.isEmpty
                  ? const Center(
                      child: Text('No profiles found.',
                          style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      itemCount: _filtered.length,
                      itemBuilder: (_, i) =>
                          _buildProfileCard(_filtered[i]),
                    ),
            ),
          ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.all(12),
          child: SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _newProfile,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('New Tax Profile'),
              style: OutlinedButton.styleFrom(
                foregroundColor: cs.primary,
                side: BorderSide(color: cs.primary),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStatusChips() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: ['All', 'ACTIVE', 'DRAFT', 'INACTIVE']
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

  Widget _buildProfileCard(TaxProfileRecord profile) {
    final cs = Theme.of(context).colorScheme;
    final isSelected = _selected?.id == profile.id;

    final totalRate = profile.components.fold<double>(
        0.0,
        (sum, pc) =>
            sum + (double.tryParse(pc.percentage) ?? 0.0));

    final sysName = _systems
        .where((s) => s.id == profile.taxSystemId)
        .map((s) => s.name)
        .firstOrNull;

    return GestureDetector(
      onTap: () => _openProfile(profile),
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
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text.rich(
                      TextSpan(children: [
                        TextSpan(
                          text: profile.code,
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        TextSpan(
                          text: '  ${profile.name}',
                          style: TextStyle(
                              color: cs.onSurfaceVariant, fontSize: 13),
                        ),
                      ]),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: cs.primary.withAlpha(20),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${totalRate.toStringAsFixed(1)}%',
                      style: TextStyle(
                          color: cs.primary,
                          fontSize: 12,
                          fontWeight: FontWeight.w600),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _StatusChip(status: profile.status),
                ],
              ),
              if (sysName != null) ...[
                const SizedBox(height: 4),
                Text(sysName,
                    style: TextStyle(
                        color: cs.onSurfaceVariant, fontSize: 11)),
              ],
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
            Icon(Icons.receipt_long_outlined,
                size: 48, color: Colors.grey),
            SizedBox(height: 12),
            Text('Select a profile to edit, or create a new one',
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
                    _buildSystemDropdown(cs),
                    const SizedBox(height: 16),
                    _buildProfileInfoCard(cs),
                    const SizedBox(height: 16),
                    _buildComponentAssignmentsCard(cs),
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

  Widget _buildSystemDropdown(ColorScheme cs) {
    return DropdownButtonFormField<String>(
      initialValue: _selectedSystemId,
      decoration: const InputDecoration(
          labelText: 'Tax System *',
          border: OutlineInputBorder(),
          isDense: true),
      hint: const Text('Select a tax system'),
      items: _systems
          .map((s) => DropdownMenuItem(
                value: s.id,
                child: Text('${s.code} — ${s.name}'),
              ))
          .toList(),
      onChanged: (v) {
        setState(() => _selectedSystemId = v);
        if (v != null) _loadComponentsForSystem(v);
      },
      validator: (v) =>
          (v == null || v.isEmpty) ? 'Tax system is required' : null,
    );
  }

  Widget _buildProfileInfoCard(ColorScheme cs) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Profile Info',
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
                    validator: (v) => (v == null || v.trim().isEmpty)
                        ? 'Required'
                        : null,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _nameCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Name *', isDense: true),
                    validator: (v) => (v == null || v.trim().isEmpty)
                        ? 'Required'
                        : null,
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
                    items: ['ACTIVE', 'DRAFT', 'INACTIVE']
                        .map((s) => DropdownMenuItem(
                            value: s, child: Text(s)))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _formStatus = v);
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _labelCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Label (optional)',
                        isDense: true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 2,
                  child: TextFormField(
                    controller: _descriptionCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Description (optional)',
                        isDense: true),
                  ),
                ),
              ],
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
                          icon: const Icon(Icons.calendar_today,
                              size: 16),
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
                          icon: const Icon(Icons.calendar_today,
                              size: 16),
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

  Widget _buildComponentAssignmentsCard(ColorScheme cs) {
    final totalRate = _assignments
        .where((a) => a.selected)
        .fold<double>(0.0, (sum, a) => sum + a.rate);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Component Assignments',
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: cs.onSurface,
                        fontSize: 14)),
                const SizedBox(width: 12),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: cs.primary.withAlpha(20),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Total: ${totalRate.toStringAsFixed(2)}%',
                    style: TextStyle(
                        color: cs.primary,
                        fontSize: 12,
                        fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_compsLoading)
              const Center(child: CircularProgressIndicator())
            else if (_assignments.isEmpty && _selectedSystemId != null)
              const Text('No components found for selected system.',
                  style: TextStyle(color: Colors.grey, fontSize: 13))
            else if (_selectedSystemId == null)
              const Text('Select a tax system above to assign components.',
                  style: TextStyle(color: Colors.grey, fontSize: 13))
            else
              ..._assignments
                  .asMap()
                  .entries
                  .map((e) => _buildAssignmentRow(e.key, e.value, cs)),
          ],
        ),
      ),
    );
  }

  Widget _buildAssignmentRow(
      int i, _ComponentAssignment assign, ColorScheme cs) {
    return Opacity(
      opacity: assign.selected ? 1.0 : 0.5,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Checkbox(
              value: assign.selected,
              onChanged: (v) {
                setState(() => assign.selected = v ?? false);
              },
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${assign.component.code}  ${assign.component.name}',
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 120,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextFormField(
                    controller: assign.rateCtrl,
                    enabled: assign.selected,
                    decoration: const InputDecoration(
                        isDense: true,
                        labelText: 'Rate %',
                        contentPadding: EdgeInsets.symmetric(
                            horizontal: 8, vertical: 8)),
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    onChanged: (_) => setState(() {}),
                  ),
                  Text(
                    'Default: ${assign.component.percentage}%',
                    style: TextStyle(
                        fontSize: 10, color: cs.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Row(
              children: [
                Checkbox(
                  value: assign.recoverable,
                  onChanged: assign.selected
                      ? (v) =>
                          setState(() => assign.recoverable = v ?? false)
                      : null,
                ),
                const Text('Recoverable',
                    style: TextStyle(fontSize: 12)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFooter(ColorScheme cs) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surface,
        border: Border(top: BorderSide(color: cs.outlineVariant)),
      ),
      child: Row(
        children: [
          if (!_isNew && _selected != null) ...[
            OutlinedButton.icon(
              onPressed: () => _deleteProfile(_selected!),
              icon: Icon(Icons.delete_outline,
                  size: 16, color: Colors.red.shade600),
              label: Text('Delete',
                  style: TextStyle(color: Colors.red.shade600)),
              style: OutlinedButton.styleFrom(
                  side: BorderSide(color: Colors.red.shade300)),
            ),
            const SizedBox(width: 8),
            OutlinedButton.icon(
              onPressed: _cloneProfile,
              icon: const Icon(Icons.copy_outlined, size: 16),
              label: const Text('Clone Profile'),
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
            label: Text(_saving ? 'Saving…' : 'Save Profile'),
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
      _ => (Colors.grey.shade200, Colors.grey.shade700),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
          color: bg, borderRadius: BorderRadius.circular(10)),
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
          Icon(Icons.error_outline,
              color: Colors.red.shade700, size: 18),
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
