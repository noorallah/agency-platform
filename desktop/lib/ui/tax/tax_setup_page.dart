import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';

// ─── Data Models ──────────────────────────────────────────────────────────────

class ComponentDraft {
  String? id;
  final TextEditingController code;
  final TextEditingController name;
  final TextEditingController label;
  final TextEditingController percentage;
  final TextEditingController calculationOrder;
  bool recoverable;
  bool includedInPrice;
  String status;

  ComponentDraft({
    this.id,
    String? code,
    String? name,
    String? label,
    String? percentage,
    String? calculationOrder,
    this.recoverable = false,
    this.includedInPrice = false,
    this.status = 'ACTIVE',
  })  : code = TextEditingController(text: code ?? ''),
        name = TextEditingController(text: name ?? ''),
        label = TextEditingController(text: label ?? ''),
        percentage = TextEditingController(text: percentage ?? '0'),
        calculationOrder = TextEditingController(text: calculationOrder ?? '0');

  void dispose() {
    code.dispose();
    name.dispose();
    label.dispose();
    percentage.dispose();
    calculationOrder.dispose();
  }

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'code': code.text.trim().toUpperCase(),
        'name': name.text.trim(),
        'label': label.text.trim().isEmpty ? null : label.text.trim(),
        'percentage': double.tryParse(percentage.text) ?? 0.0,
        'calculation_order': int.tryParse(calculationOrder.text) ?? 0,
        'recoverable': recoverable,
        'included_in_price': includedInPrice,
        'status': status,
      };
}

class ProfileComponentDraft {
  String componentCode;
  final TextEditingController percentage;
  final TextEditingController calculationOrder;
  bool recoverable;
  bool includedInPrice;

  ProfileComponentDraft({
    required this.componentCode,
    String? percentage,
    String? calculationOrder,
    this.recoverable = false,
    this.includedInPrice = false,
  })  : percentage = TextEditingController(text: percentage ?? '0'),
        calculationOrder = TextEditingController(text: calculationOrder ?? '0');

  void dispose() {
    percentage.dispose();
    calculationOrder.dispose();
  }

  Map<String, dynamic> toJson() => {
        'component_code': componentCode,
        'percentage': double.tryParse(percentage.text) ?? 0.0,
        'calculation_order': int.tryParse(calculationOrder.text) ?? 0,
        'recoverable': recoverable,
        'included_in_price': includedInPrice,
      };
}

class ProfileDraft {
  String? id;
  final TextEditingController code;
  final TextEditingController name;
  final TextEditingController label;
  final TextEditingController description;
  String status;
  int displayOrder;
  bool isExpanded;
  List<ProfileComponentDraft> components;

  ProfileDraft({
    this.id,
    String? code,
    String? name,
    String? label,
    String? description,
    this.status = 'ACTIVE',
    this.displayOrder = 0,
    this.isExpanded = false,
    List<ProfileComponentDraft>? components,
  })  : code = TextEditingController(text: code ?? ''),
        name = TextEditingController(text: name ?? ''),
        label = TextEditingController(text: label ?? ''),
        description = TextEditingController(text: description ?? ''),
        components = components ?? [];

  void dispose() {
    code.dispose();
    name.dispose();
    label.dispose();
    description.dispose();
    for (final c in components) {
      c.dispose();
    }
  }

  double get totalRate =>
      components.fold(0.0, (sum, c) => sum + (double.tryParse(c.percentage.text) ?? 0.0));

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'code': code.text.trim().toUpperCase(),
        'name': name.text.trim(),
        'label': label.text.trim().isEmpty ? null : label.text.trim(),
        'description': description.text.trim().isEmpty ? null : description.text.trim(),
        'status': status,
        'display_order': displayOrder,
        'components': components.map((c) => c.toJson()).toList(),
      };
}

// ─── Main Page ────────────────────────────────────────────────────────────────

class TaxSetupPage extends StatefulWidget {
  final ApiClient api;
  final String? systemId; // null = create mode, UUID = edit mode

  const TaxSetupPage({super.key, required this.api, this.systemId});

  @override
  State<TaxSetupPage> createState() => _TaxSetupPageState();
}

class _TaxSetupPageState extends State<TaxSetupPage> {
  final _formKey = GlobalKey<FormState>();
  final _scrollController = ScrollController();

  // System fields
  final _codeCtrl = TextEditingController();
  final _nameCtrl = TextEditingController();
  final _displayNameCtrl = TextEditingController();
  final _descriptionCtrl = TextEditingController();
  String _status = 'ACTIVE';
  int _displayOrder = 1;

  // Children
  final List<ComponentDraft> _components = [];
  final List<ProfileDraft> _profiles = [];

  // track saved system id so edit mode activates after first create
  String? _savedSystemId;
  bool _saveSuccess = false;

  bool _isLoading = false;
  bool _isSaving = false;
  String? _errorMessage;

  bool get _isEditMode => widget.systemId != null || _savedSystemId != null;
  String? get _activeSystemId => widget.systemId ?? _savedSystemId;

  @override
  void initState() {
    super.initState();
    if (_isEditMode) {
      _loadExisting();
    } else {
      _components.add(ComponentDraft());
      _profiles.add(ProfileDraft());
    }
  }

  void _resetForm() {
    for (final c in _components) {
      c.dispose();
    }
    for (final p in _profiles) {
      p.dispose();
    }
    setState(() {
      _codeCtrl.clear();
      _nameCtrl.clear();
      _displayNameCtrl.clear();
      _descriptionCtrl.clear();
      _status = 'ACTIVE';
      _displayOrder = 1;
      _components.clear();
      _components.add(ComponentDraft());
      _profiles.clear();
      _profiles.add(ProfileDraft());
      _savedSystemId = null;
      _saveSuccess = false;
      _errorMessage = null;
    });
  }

  @override
  void dispose() {
    _codeCtrl.dispose();
    _nameCtrl.dispose();
    _displayNameCtrl.dispose();
    _descriptionCtrl.dispose();
    _scrollController.dispose();
    for (final c in _components) {
      c.dispose();
    }
    for (final p in _profiles) {
      p.dispose();
    }
    super.dispose();
  }

  Future<void> _loadExisting() async {
    final String? systemId = widget.systemId;
    if (systemId == null) {
      return;
    }
    setState(() => _isLoading = true);
    try {
      final response = await widget.api.taxSetup(systemId);
      final data = response['data'] as Map<String, dynamic>;
      final system = data['system'] as Map<String, dynamic>;
      final rawComponents = (data['components'] as List).cast<Map<String, dynamic>>();
      final rawProfiles = (data['profiles'] as List).cast<Map<String, dynamic>>();

      setState(() {
        _codeCtrl.text = system['code'] ?? '';
        _nameCtrl.text = system['name'] ?? '';
        _displayNameCtrl.text = system['display_name'] ?? '';
        _descriptionCtrl.text = system['description'] ?? '';
        _status = system['status'] ?? 'ACTIVE';
        _displayOrder = (system['display_order'] as num?)?.toInt() ?? 1;

        _components.clear();
        for (final c in rawComponents) {
          _components.add(ComponentDraft(
            id: c['id'] as String?,
            code: c['code'] as String?,
            name: c['name'] as String?,
            label: c['label'] as String?,
            percentage: (c['percentage'] ?? 0).toString(),
            calculationOrder: (c['calculation_order'] ?? 0).toString(),
            recoverable: c['recoverable'] as bool? ?? false,
            includedInPrice: c['included_in_price'] as bool? ?? false,
            status: c['status'] as String? ?? 'ACTIVE',
          ));
        }

        _profiles.clear();
        for (final p in rawProfiles) {
          final profileComponents = (p['components'] as List? ?? [])
              .cast<Map<String, dynamic>>()
              .map((pc) {
            // Resolve component code either directly or via tax_component_id
            String compCode = pc['component_code'] as String? ?? '';
            if (compCode.isEmpty) {
              final compId = pc['tax_component_id'];
              final comp = rawComponents.firstWhere(
                (c) => c['id'] == compId,
                orElse: () => <String, dynamic>{'code': ''},
              );
              compCode = comp['code'] as String? ?? '';
            }
            return ProfileComponentDraft(
              componentCode: compCode,
              percentage: (pc['percentage'] ?? 0).toString(),
              calculationOrder: (pc['calculation_order'] ?? 0).toString(),
              recoverable: pc['recoverable'] as bool? ?? false,
              includedInPrice: pc['included_in_price'] as bool? ?? false,
            );
          }).toList();

          _profiles.add(ProfileDraft(
            id: p['id'] as String?,
            code: p['code'] as String?,
            name: p['name'] as String?,
            label: p['label'] as String?,
            description: p['description'] as String?,
            status: p['status'] as String? ?? 'ACTIVE',
            displayOrder: (p['display_order'] as num?)?.toInt() ?? 0,
            components: profileComponents,
          ));
        }
      });
    } catch (e) {
      setState(() => _errorMessage = 'Failed to load tax setup: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _isSaving = true;
      _errorMessage = null;
    });

    final payload = {
      'code': _codeCtrl.text.trim().toUpperCase(),
      'name': _nameCtrl.text.trim(),
      'display_name': _displayNameCtrl.text.trim().isEmpty ? null : _displayNameCtrl.text.trim(),
      'description': _descriptionCtrl.text.trim().isEmpty ? null : _descriptionCtrl.text.trim(),
      'status': _status,
      'display_order': _displayOrder,
      'components': _components.map((c) => c.toJson()).toList(),
      'profiles': _profiles.map((p) => p.toJson()).toList(),
    };

    try {
      if (_isEditMode) {
        await widget.api.updateTaxSetup(_activeSystemId!, payload);
        if (mounted) {
          setState(() => _saveSuccess = true);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Tax setup updated successfully.'),
              backgroundColor: Colors.green.shade700,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      } else {
        final response = await widget.api.createTaxSetup(payload);
        // Extract the created system id so subsequent saves use PUT
        final systemId = (response['data']?['system']?['id'] as String?);
        if (mounted) {
          setState(() {
            _savedSystemId = systemId;
            _saveSuccess = true;
          });
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Tax setup created successfully.'),
              backgroundColor: Colors.green.shade700,
              duration: const Duration(seconds: 3),
              action: SnackBarAction(
                label: 'New Setup',
                textColor: Colors.white,
                onPressed: _resetForm,
              ),
            ),
          );
        }
      }
    } catch (e) {
      setState(() => _errorMessage = 'Save failed: $e');
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  // ─── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    if (_isLoading) {
      return Scaffold(
        appBar: _buildAppBar(theme, colorScheme),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: _buildAppBar(theme, colorScheme),
      body: Form(
        key: _formKey,
        child: Scrollbar(
          controller: _scrollController,
          child: SingleChildScrollView(
            controller: _scrollController,
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1200),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_errorMessage != null) _buildErrorBanner(),
                  if (_saveSuccess) _buildSuccessBanner(),
                  _buildSystemInfoCard(theme, colorScheme),
                  const SizedBox(height: 20),
                  _buildComponentsCard(theme, colorScheme),
                  const SizedBox(height: 20),
                  _buildProfilesCard(theme, colorScheme),
                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(ThemeData theme, ColorScheme colorScheme) {
    return AppBar(
      backgroundColor: colorScheme.surface,
      elevation: 0,
      surfaceTintColor: Colors.transparent,
      leading: Navigator.of(context).canPop()
          ? IconButton(
              icon: const Icon(Icons.arrow_back),
              onPressed: () => Navigator.of(context).pop(),
              tooltip: 'Back',
            )
          : null,
      title: Text(
        _isEditMode ? 'Edit Tax Setup' : 'Create Tax Setup',
        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
      actions: [
        if (_isSaving)
          const Padding(
            padding: EdgeInsets.all(16),
            child: SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          )
        else
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: FilledButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.save_outlined, size: 18),
              label: Text(_isEditMode ? 'Update' : 'Create'),
            ),
          ),
      ],
    );
  }

  Widget _buildErrorBanner() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        border: Border.all(color: Colors.red.shade200),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _errorMessage!,
              style: TextStyle(color: Colors.red.shade700, fontSize: 13),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            onPressed: () => setState(() => _errorMessage = null),
            color: Colors.red.shade700,
          ),
        ],
      ),
    );
  }

  // ─── System Info Card ──────────────────────────────────────────────────────

  Widget _buildSuccessBanner() {
    final isEdit = widget.systemId != null || (_savedSystemId != null);
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.green.shade50,
        border: Border.all(color: Colors.green.shade300),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(Icons.check_circle_outline, color: Colors.green.shade700, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isEdit
                  ? 'Tax setup saved successfully. You can continue editing.'
                  : 'Tax setup created successfully. You can edit it below or create another.',
              style: TextStyle(color: Colors.green.shade800, fontSize: 13),
            ),
          ),
          if (!isEdit)
            TextButton.icon(
              onPressed: _resetForm,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('New Setup'),
              style: TextButton.styleFrom(foregroundColor: Colors.green.shade700),
            ),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            onPressed: () => setState(() => _saveSuccess = false),
            color: Colors.green.shade700,
          ),
        ],
      ),
    );
  }

  Widget _buildSystemInfoCard(ThemeData theme, ColorScheme colorScheme) {
    return _SectionCard(
      title: 'Tax System',
      icon: Icons.account_balance_outlined,
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 2,
                child: _buildTextField(
                  controller: _codeCtrl,
                  label: 'Code *',
                  hint: 'GST-IN',
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Code is required' : null,
                  textCapitalization: TextCapitalization.characters,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 4,
                child: _buildTextField(
                  controller: _nameCtrl,
                  label: 'Name *',
                  hint: 'GST India',
                  validator: (v) =>
                      (v == null || v.trim().isEmpty) ? 'Name is required' : null,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 4,
                child: _buildTextField(
                  controller: _displayNameCtrl,
                  label: 'Display Name',
                  hint: 'Goods & Services Tax',
                ),
              ),
              const SizedBox(width: 16),
              SizedBox(
                width: 140,
                child: _buildStatusDropdown(),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildTextField(
            controller: _descriptionCtrl,
            label: 'Description',
            hint: 'Optional description of this tax system',
            maxLines: 2,
          ),
        ],
      ),
    );
  }

  // ─── Components Card ───────────────────────────────────────────────────────

  Widget _buildComponentsCard(ThemeData theme, ColorScheme colorScheme) {
    return _SectionCard(
      title: 'Tax Components',
      icon: Icons.layers_outlined,
      subtitle: 'Define individual tax heads (CGST, SGST, IGST, etc.)',
      headerAction: FilledButton.tonalIcon(
        onPressed: () => setState(() => _components.add(ComponentDraft())),
        icon: const Icon(Icons.add, size: 16),
        label: const Text('Add Component'),
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          textStyle: const TextStyle(fontSize: 13),
        ),
      ),
      child: _components.isEmpty
          ? _buildEmptyState(
              'No components yet. Add at least one.',
              Icons.layers_outlined,
            )
          : Column(
              children: [
                _buildComponentsHeader(),
                const Divider(height: 1),
                ...List.generate(_components.length, _buildComponentRow),
              ],
            ),
    );
  }

  Widget _buildComponentsHeader() {
    const style = TextStyle(
      fontWeight: FontWeight.w600,
      fontSize: 12,
      color: Colors.grey,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      child: Row(
        children: const [
          SizedBox(width: 32),
          Expanded(flex: 2, child: Text('Code', style: style)),
          SizedBox(width: 8),
          Expanded(flex: 3, child: Text('Name', style: style)),
          SizedBox(width: 8),
          Expanded(flex: 2, child: Text('Label', style: style)),
          SizedBox(width: 8),
          SizedBox(width: 96, child: Text('Rate %', style: style)),
          SizedBox(width: 8),
          SizedBox(width: 96, child: Text('Calc Order', style: style)),
          SizedBox(width: 8),
          SizedBox(width: 96, child: Text('Recoverable', style: style)),
          SizedBox(width: 8),
          SizedBox(width: 80, child: Text('Status', style: style)),
          SizedBox(width: 40),
        ],
      ),
    );
  }

  Widget _buildComponentRow(int i) {
    final comp = _components[i];
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
      decoration: BoxDecoration(
        color: i.isEven ? Colors.transparent : Colors.grey.withValues(alpha: 0.03),
        border: const Border(bottom: BorderSide(color: Color(0xFFEEEEEE))),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 32,
            child: Text(
              '${i + 1}',
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
          Expanded(
            flex: 2,
            child: _compactField(
              controller: comp.code,
              hint: 'CGST',
              textCapitalization: TextCapitalization.characters,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 3,
            child: _compactField(controller: comp.name, hint: 'Central GST'),
          ),
          const SizedBox(width: 8),
          Expanded(
            flex: 2,
            child: _compactField(controller: comp.label, hint: 'Central GST'),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 96,
            child: _compactField(
              controller: comp.percentage,
              hint: '9.00',
              keyboardType: TextInputType.number,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 96,
            child: _compactField(
              controller: comp.calculationOrder,
              hint: '1',
              keyboardType: TextInputType.number,
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 96,
            child: Checkbox(
              value: comp.recoverable,
              onChanged: (v) => setState(() => comp.recoverable = v ?? false),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 80,
            child: _miniStatusDropdown(
              value: comp.status,
              onChanged: (v) => setState(() => comp.status = v ?? 'ACTIVE'),
            ),
          ),
          SizedBox(
            width: 40,
            child: IconButton(
              icon: const Icon(Icons.delete_outline, size: 18, color: Colors.red),
              onPressed: () => setState(() {
                final code = comp.code.text;
                comp.dispose();
                _components.removeAt(i);
                // Remove orphaned profile component assignments
                for (final p in _profiles) {
                  p.components.removeWhere((pc) => pc.componentCode == code);
                }
              }),
              tooltip: 'Remove component',
              padding: EdgeInsets.zero,
            ),
          ),
        ],
      ),
    );
  }

  // ─── Profiles Card ─────────────────────────────────────────────────────────

  Widget _buildProfilesCard(ThemeData theme, ColorScheme colorScheme) {
    return _SectionCard(
      title: 'Tax Profiles (Slabs)',
      icon: Icons.receipt_long_outlined,
      subtitle: 'Define tax slabs to assign to products (e.g. GST 18%, GST 5%)',
      headerAction: FilledButton.tonalIcon(
        onPressed: () => setState(() => _profiles.add(ProfileDraft())),
        icon: const Icon(Icons.add, size: 16),
        label: const Text('Add Profile'),
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          textStyle: const TextStyle(fontSize: 13),
        ),
      ),
      child: _profiles.isEmpty
          ? _buildEmptyState(
              'No profiles yet. Add tax slabs.',
              Icons.receipt_long_outlined,
            )
          : Column(
              children: List.generate(
                _profiles.length,
                (i) => _buildProfileRow(i, theme, colorScheme),
              ),
            ),
    );
  }

  Widget _buildProfileRow(int i, ThemeData theme, ColorScheme colorScheme) {
    final prof = _profiles[i];
    final totalRate = prof.totalRate;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Column(
        children: [
          // ── Profile header row ──────────────────────────────────────────
          InkWell(
            onTap: () => setState(() => prof.isExpanded = !prof.isExpanded),
            borderRadius: BorderRadius.vertical(
              top: const Radius.circular(8),
              bottom: prof.isExpanded ? Radius.zero : const Radius.circular(8),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  Icon(
                    prof.isExpanded ? Icons.expand_less : Icons.expand_more,
                    size: 20,
                    color: Colors.grey,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    flex: 2,
                    child: _compactField(
                      controller: prof.code,
                      hint: 'GST18-LOCAL',
                      textCapitalization: TextCapitalization.characters,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    flex: 3,
                    child: _compactField(
                      controller: prof.name,
                      hint: 'GST 18% Local',
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    flex: 2,
                    child: _compactField(
                      controller: prof.label,
                      hint: 'GST @18%',
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Total rate badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: colorScheme.primaryContainer,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      '${totalRate.toStringAsFixed(1)}%',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                        color: colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _miniStatusDropdown(
                    value: prof.status,
                    onChanged: (v) => setState(() => prof.status = v ?? 'ACTIVE'),
                  ),
                  const SizedBox(width: 4),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 18, color: Colors.red),
                    onPressed: () => setState(() {
                      prof.dispose();
                      _profiles.removeAt(i);
                    }),
                    tooltip: 'Remove profile',
                    padding: EdgeInsets.zero,
                  ),
                ],
              ),
            ),
          ),

          // ── Expanded: component assignments ─────────────────────────────
          if (prof.isExpanded) ...[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        'Component Assignments',
                        style: theme.textTheme.labelMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: colorScheme.primary,
                        ),
                      ),
                      const Spacer(),
                      _buildAddComponentMenu(prof),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (prof.components.isEmpty)
                    Padding(
                      padding: const EdgeInsets.all(8),
                      child: Text(
                        'No components assigned. Click "Add Component" to assign.',
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                      ),
                    )
                  else
                    ...List.generate(
                      prof.components.length,
                      (j) => _buildProfileComponentRow(prof, j, colorScheme),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAddComponentMenu(ProfileDraft prof) {
    final available = _components
        .where((c) =>
            c.code.text.isNotEmpty &&
            !prof.components.any((pc) => pc.componentCode == c.code.text))
        .toList();

    if (available.isEmpty) {
      return FilledButton.tonalIcon(
        onPressed: null,
        icon: const Icon(Icons.add, size: 14),
        label: const Text('Add Component'),
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          textStyle: const TextStyle(fontSize: 12),
        ),
      );
    }

    return PopupMenuButton<String>(
      tooltip: 'Add component assignment',
      onSelected: (code) {
        if (prof.components.any((c) => c.componentCode == code)) return;
        setState(() => prof.components.add(
              ProfileComponentDraft(componentCode: code),
            ));
      },
      itemBuilder: (_) => available
          .map((c) => PopupMenuItem(
                value: c.code.text,
                child: Text('${c.code.text} — ${c.name.text}'),
              ))
          .toList(),
      child: FilledButton.tonalIcon(
        onPressed: null, // handled by PopupMenuButton
        icon: const Icon(Icons.add, size: 14),
        label: const Text('Add Component'),
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          textStyle: const TextStyle(fontSize: 12),
        ),
      ),
    );
  }

  Widget _buildProfileComponentRow(
      ProfileDraft prof, int j, ColorScheme colorScheme) {
    final pc = prof.components[j];
    final compDraft = _components.firstWhere(
      (c) => c.code.text == pc.componentCode,
      orElse: () => ComponentDraft(code: pc.componentCode),
    );

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              pc.componentCode,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 12,
                color: colorScheme.onPrimaryContainer,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              compDraft.name.text,
              style: const TextStyle(fontSize: 13),
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 100,
            child: TextFormField(
              controller: pc.percentage,
              decoration: const InputDecoration(
                labelText: 'Rate %',
                isDense: true,
                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.number,
              style: const TextStyle(fontSize: 13),
              onChanged: (_) => setState(() {}),
            ),
          ),
          const SizedBox(width: 12),
          Row(
            children: [
              const Text('Recoverable', style: TextStyle(fontSize: 12)),
              Checkbox(
                value: pc.recoverable,
                onChanged: (v) => setState(() => pc.recoverable = v ?? false),
              ),
            ],
          ),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline, size: 18, color: Colors.red),
            tooltip: 'Remove assignment',
            onPressed: () => setState(() {
              pc.dispose();
              prof.components.removeAt(j);
            }),
          ),
        ],
      ),
    );
  }

  // ─── Shared Helpers ────────────────────────────────────────────────────────

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    String? hint,
    String? Function(String?)? validator,
    int maxLines = 1,
    TextCapitalization textCapitalization = TextCapitalization.none,
  }) {
    return TextFormField(
      controller: controller,
      validator: validator,
      maxLines: maxLines,
      textCapitalization: textCapitalization,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        border: const OutlineInputBorder(),
        isDense: true,
      ),
    );
  }

  Widget _compactField({
    required TextEditingController controller,
    String? hint,
    TextInputType? keyboardType,
    TextCapitalization textCapitalization = TextCapitalization.none,
  }) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      textCapitalization: textCapitalization,
      style: const TextStyle(fontSize: 13),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        border: const OutlineInputBorder(),
      ),
      onChanged: (_) => setState(() {}),
    );
  }

  Widget _buildStatusDropdown() {
    return DropdownButtonFormField<String>(
      initialValue: _status,
      decoration: const InputDecoration(
        labelText: 'Status',
        border: OutlineInputBorder(),
        isDense: true,
      ),
      items: const ['ACTIVE', 'DRAFT', 'INACTIVE', 'ARCHIVED']
          .map((s) => DropdownMenuItem(value: s, child: Text(s)))
          .toList(),
      onChanged: (v) => setState(() => _status = v ?? 'ACTIVE'),
    );
  }

  Widget _miniStatusDropdown({
    required String value,
    required ValueChanged<String?> onChanged,
  }) {
    return DropdownButton<String>(
      value: value,
      isDense: true,
      underline: const SizedBox(),
      items: const ['ACTIVE', 'DRAFT', 'INACTIVE']
          .map((s) => DropdownMenuItem(
                value: s,
                child: Text(s, style: const TextStyle(fontSize: 12)),
              ))
          .toList(),
      onChanged: onChanged,
    );
  }

  Widget _buildEmptyState(String message, IconData icon) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [
          Icon(icon, size: 40, color: Colors.grey.shade300),
          const SizedBox(height: 8),
          Text(
            message,
            style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

// ─── Reusable Section Card ────────────────────────────────────────────────────

class _SectionCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final String? subtitle;
  final Widget child;
  final Widget? headerAction;

  const _SectionCard({
    required this.title,
    required this.icon,
    required this.child,
    this.subtitle,
    this.headerAction,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Card header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: colorScheme.surfaceContainerLow,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            child: Row(
              children: [
                Icon(icon, size: 20, color: colorScheme.primary),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    if (subtitle != null)
                      Text(
                        subtitle!,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                      ),
                  ],
                ),
                if (headerAction != null) ...[
                  const Spacer(),
                  headerAction!,
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          // Card body
          Padding(
            padding: const EdgeInsets.all(16),
            child: child,
          ),
        ],
      ),
    );
  }
}
