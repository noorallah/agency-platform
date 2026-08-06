import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../workspace/workspace_components.dart';
import '../workspace/workspace_dialog.dart';
import '../workspace/workspace_interactions.dart';

class CustomerController extends ChangeNotifier {
  CustomerController(this._api);

  final ApiClient _api;
  List<Customer> items = const [];
  Customer? selected;
  int total = 0;
  int page = 1;
  String search = '';
  String sortBy = 'created_at';
  bool descending = true;
  CustomerQuery filters = const CustomerQuery();
  bool loading = false;
  String? error;
  bool _disposed = false;

  Future<void> load({int? requestedPage}) async {
    if (_disposed) return;
    loading = true;
    error = null;
    page = requestedPage ?? page;
    notifyListeners();
    try {
      final PagedResult<Customer> result = await _api.customers(
        page: page,
        search: search,
        sortBy: sortBy,
        descending: descending,
        filters: filters,
      );
      items = result.items;
      total = result.total;
      final String? selectedId = selected?.id;
      selected = selectedId == null
          ? null
          : items.cast<Customer?>().firstWhere(
                (customer) => customer?.id == selectedId,
                orElse: () => null,
              );
    } on ApiException catch (exception) {
      error = exception.message;
      items = const [];
      total = 0;
    } finally {
      if (!_disposed) {
        loading = false;
        notifyListeners();
      }
    }
  }

  void select(Customer customer) {
    selected = customer;
    notifyListeners();
  }

  void clearSelection() {
    selected = null;
    notifyListeners();
  }

  Future<Customer> save(Customer? customer, Json payload) async =>
      customer == null
          ? _api.createCustomer(payload)
          : _api.updateCustomer(customer.id, payload);

  Future<void> delete(Customer customer) => _api.deleteCustomer(customer.id);

  Future<void> restore(Customer customer) async {
    await _api.restoreCustomer(customer.id);
  }

  Future<String> export() => _api.exportCustomers(search: search);

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

class CustomerManagementPage extends StatefulWidget {
  const CustomerManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CustomerManagementPage> createState() => _CustomerManagementPageState();
}

class _CustomerManagementPageState extends State<CustomerManagementPage> {
  static const int _rowsPerPage = 20;
  late final CustomerController _controller = CustomerController(widget.api)
    ..addListener(_changed);
  final TextEditingController _search = TextEditingController();
  final TextEditingController _city = TextEditingController();
  final TextEditingController _state = TextEditingController();
  final TextEditingController _createdFrom = TextEditingController();
  final TextEditingController _createdTo = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  String? _status;
  String? _type;
  bool _includeDeleted = false;

  bool get _canCreate =>
      widget.hasActiveFirm &&
      widget.permissions.hasPermission('CUSTOMER_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('CUSTOMER_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('CUSTOMER_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('CUSTOMER_RESTORE');
  bool get _canExport => widget.permissions.hasPermission('CUSTOMER_EXPORT');

  @override
  void initState() {
    super.initState();
    _searchFocus.addListener(_changed);
    _controller.load();
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_changed)
      ..dispose();
    _search.dispose();
    _city.dispose();
    _state.dispose();
    _createdFrom.dispose();
    _createdTo.dispose();
    _searchFocus
      ..removeListener(_changed)
      ..dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _open(CustomerDialogMode mode, [Customer? customer]) async {
    if (mode == CustomerDialogMode.create && !_canCreate) return;
    if (mode == CustomerDialogMode.edit &&
        (!_canEdit || customer == null || customer.isDeleted)) {
      return;
    }
    final Customer? saved = await showDialog<Customer>(
      context: context,
      barrierDismissible: false,
      builder: (context) => CustomerWorkspaceDialog(
        mode: mode,
        customer: customer,
        onSave: (payload) => _controller.save(customer, payload),
      ),
    );
    if (saved == null || !mounted) return;
    NotificationService.show(
      context,
      'Customer ${customer == null ? 'created' : 'updated'}.',
      kind: AppNotificationKind.success,
    );
    await _controller.load();
  }

  Future<void> _delete(Customer customer) async {
    if (!_canDelete || customer.isDeleted) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete ${customer.displayName}?',
      message:
          'The customer will be hidden from normal searches and can be restored.',
      confirmLabel: 'Delete customer',
      type: ConfirmationType.delete,
    );
    if (!accepted) return;
    try {
      await _controller.delete(customer);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Customer deleted.',
        kind: AppNotificationKind.success,
      );
      await _controller.load();
    } on ApiException catch (exception) {
      if (mounted) {
        NotificationService.show(
          context,
          exception.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _restore(Customer customer) async {
    if (!_canRestore || !customer.isDeleted) return;
    final bool accepted = await showWorkspaceConfirmDialog(
      context,
      title: 'Restore ${customer.displayName}?',
      message: 'The customer will become available to normal workflows again.',
      confirmLabel: 'Restore customer',
    );
    if (!accepted) return;
    try {
      await _controller.restore(customer);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Customer restored.',
        kind: AppNotificationKind.success,
      );
      await _controller.load();
    } on ApiException catch (exception) {
      if (mounted) {
        NotificationService.show(
          context,
          exception.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _export() async {
    try {
      final String csv = await _controller.export();
      await copyTextToClipboard(csv);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Customer CSV copied to the clipboard.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (mounted) {
        NotificationService.show(
          context,
          exception.message,
          kind: AppNotificationKind.error,
        );
      }
    }
  }

  Future<void> _copy(Customer customer) async {
    await copyTextToClipboard(
      [
        customer.code,
        customer.name,
        customer.gstNumber,
        customer.phone,
        customer.city,
        customer.status,
        _money(customer.creditLimit),
        customer.createdAt,
      ].join('\t'),
    );
    if (mounted) {
      NotificationService.show(context, 'Customer row copied.');
    }
  }

  void _applyFilters() {
    _controller.filters = CustomerQuery(
      status: _status,
      customerType: _type,
      city: _city.text.trim(),
      state: _state.text.trim(),
      createdFrom: _createdFrom.text.trim(),
      createdTo: _createdTo.text.trim(),
      includeDeleted: _includeDeleted,
    );
    _controller.load(requestedPage: 1);
  }

  void _clearFilters() {
    setState(() {
      _status = null;
      _type = null;
      _city.clear();
      _state.clear();
      _createdFrom.clear();
      _createdTo.clear();
      _includeDeleted = false;
    });
    _applyFilters();
  }

  int get _activeFilterCount => [
        _status != null,
        _type != null,
        _city.text.trim().isNotEmpty,
        _state.text.trim().isNotEmpty,
        _createdFrom.text.trim().isNotEmpty,
        _createdTo.text.trim().isNotEmpty,
        _includeDeleted,
      ].where((active) => active).length;

  void _contextAction(WorkspaceContextAction action, Customer customer) {
    switch (action) {
      case WorkspaceContextAction.view:
        _open(CustomerDialogMode.view, customer);
        break;
      case WorkspaceContextAction.edit:
        _open(CustomerDialogMode.edit, customer);
        break;
      case WorkspaceContextAction.delete:
        _delete(customer);
        break;
      case WorkspaceContextAction.restore:
        _restore(customer);
        break;
      case WorkspaceContextAction.copy:
        _copy(customer);
        break;
      case WorkspaceContextAction.refresh:
        _controller.load();
        break;
      case WorkspaceContextAction.export:
        _export();
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final Customer? selected = _controller.selected;
    final Widget toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
        ToolbarAction.view,
        ToolbarAction.edit,
        ToolbarAction.delete,
        ToolbarAction.refresh,
        ToolbarAction.export,
      ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete,
        ToolbarAction.export => _canExport,
        _ => true,
      },
      isEnabled: (action) =>
          !_controller.loading &&
          switch (action) {
            ToolbarAction.newItem => _canCreate,
            ToolbarAction.view => selected != null,
            ToolbarAction.edit => selected != null && !selected.isDeleted,
            ToolbarAction.delete => selected != null && !selected.isDeleted,
            ToolbarAction.refresh => true,
            ToolbarAction.export => _controller.items.isNotEmpty,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _open(CustomerDialogMode.create);
            break;
          case ToolbarAction.view:
            if (selected != null) _open(CustomerDialogMode.view, selected);
            break;
          case ToolbarAction.edit:
            if (selected != null) _open(CustomerDialogMode.edit, selected);
            break;
          case ToolbarAction.delete:
            if (selected != null) _delete(selected);
            break;
          case ToolbarAction.refresh:
            _controller.load();
            break;
          case ToolbarAction.export:
            _export();
            break;
          case ToolbarAction.import:
          case ToolbarAction.print:
          case ToolbarAction.settings:
            break;
        }
      },
    );
    final Widget searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search code, name, GST, PAN, email, phone, city, status',
      onSearch: (value) {
        _controller.search = value.trim();
        _controller.load(requestedPage: 1);
      },
    );
    final Widget filterPanel = FilterPanel(
      activeFilterCount: _activeFilterCount,
      onApply: _applyFilters,
      onClear: _clearFilters,
      children: [
        _filterDropdown(
          label: 'Status',
          value: _status,
          values: const ['ACTIVE', 'INACTIVE', 'ON_HOLD'],
          onChanged: (value) => setState(() => _status = value),
        ),
        _filterDropdown(
          label: 'Customer type',
          value: _type,
          values: const ['INDIVIDUAL', 'BUSINESS'],
          onChanged: (value) => setState(() => _type = value),
        ),
        SizedBox(
          width: 220,
          child: TextField(
            controller: _city,
            decoration: const InputDecoration(labelText: 'City'),
          ),
        ),
        SizedBox(
          width: 220,
          child: TextField(
            controller: _state,
            decoration: const InputDecoration(labelText: 'State'),
          ),
        ),
        SizedBox(
          width: 220,
          child: TextField(
            controller: _createdFrom,
            decoration: const InputDecoration(
              labelText: 'Created from',
              hintText: 'YYYY-MM-DD',
            ),
          ),
        ),
        SizedBox(
          width: 220,
          child: TextField(
            controller: _createdTo,
            decoration: const InputDecoration(
              labelText: 'Created to',
              hintText: 'YYYY-MM-DD',
            ),
          ),
        ),
        FilterChip(
          label: const Text('Include deleted'),
          selected: _includeDeleted,
          onSelected: (value) => setState(() => _includeDeleted = value),
        ),
      ],
    );
    final Widget primaryContent;
    if (_controller.error != null) {
      primaryContent = WorkspaceErrorState(
        message: _controller.error!,
        onRetry: _controller.load,
      );
    } else if (_controller.loading && _controller.items.isEmpty) {
      primaryContent = const TableLoadingSkeleton();
    } else if (_controller.items.isEmpty) {
      primaryContent = StandardEmptyState(
        type: _controller.search.isEmpty && _activeFilterCount == 0
            ? EmptyStateType.noRecords
            : EmptyStateType.noSearchResults,
        action: _canCreate
            ? FilledButton.icon(
                onPressed: () => _open(CustomerDialogMode.create),
                icon: const Icon(Icons.add),
                label: const Text('New customer'),
              )
            : null,
      );
    } else {
      primaryContent = LoadingOverlay(
        loading: _controller.loading,
        child: EnterpriseDataGrid<Customer>(
          items: _controller.items,
          total: _controller.total,
          pageOffset: (_controller.page - 1) * _rowsPerPage,
          rowsPerPage: _rowsPerPage,
          columns: [
            _column('Code', 'code'),
            _column('Name', 'name'),
            const GridColumn(key: 'gst', label: 'GST'),
            const GridColumn(key: 'phone', label: 'Phone'),
            const GridColumn(key: 'city', label: 'City'),
            _column('Status', 'status'),
            _column('Credit limit', 'credit_limit'),
            _column('Created', 'created_at'),
          ],
          id: (customer) => customer.id,
          cells: (customer) => [
            customer.code,
            customer.name,
            customer.gstNumber,
            customer.phone,
            customer.city,
            customer.isDeleted ? 'DELETED' : customer.status,
            _money(customer.creditLimit),
            _dateOnly(customer.createdAt),
          ],
          selectedId: selected?.id,
          onSelect: _controller.select,
          onOpen: (customer) => _open(CustomerDialogMode.view, customer),
          contextActionsFor: (customer) => [
            WorkspaceContextAction.view,
            if (_canEdit && !customer.isDeleted) WorkspaceContextAction.edit,
            if (_canDelete && !customer.isDeleted)
              WorkspaceContextAction.delete,
            if (_canRestore && customer.isDeleted)
              WorkspaceContextAction.restore,
            WorkspaceContextAction.copy,
            WorkspaceContextAction.refresh,
            if (_canExport) WorkspaceContextAction.export,
          ],
          onContextAction: _contextAction,
          onPageChanged: (offset) =>
              _controller.load(requestedPage: offset ~/ _rowsPerPage + 1),
        ),
      );
    }
    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreate ? () => _open(CustomerDialogMode.create) : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _controller.load,
        copy: selected == null || _searchFocus.hasFocus
            ? null
            : () => _copy(selected),
        cancel: selected == null ? null : _controller.clearSelection,
        delete: selected != null && !selected.isDeleted && _canDelete
            ? () => _delete(selected)
            : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: searchPanel,
        filterPanel: filterPanel,
        primaryContent: primaryContent,
        detailsPanel: selected == null ? null : _summary(selected),
        statusBar: WorkspaceStatusBar(
          total: _controller.total,
          selected: selected != null,
          message: _controller.loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }

  GridColumn _column(String label, String sortField) => GridColumn(
        key: sortField,
        label: label,
        onSort: (ascending) {
          _controller
            ..sortBy = sortField
            ..descending = !ascending
            ..load(requestedPage: 1);
        },
      );

  Widget _summary(Customer? customer) => QuickSummaryPanel(
        title: customer == null ? 'No customer selected' : customer.displayName,
        lines: customer == null
            ? const []
            : [
                DetailLine('Code', customer.code),
                DetailLine('Type', customer.customerType),
                DetailLine(
                    'Status', customer.isDeleted ? 'DELETED' : customer.status),
                DetailLine('GST', customer.gstNumber),
                DetailLine('Phone', customer.phone),
                DetailLine('City', customer.city),
              ],
        onView: customer == null
            ? null
            : () => _open(CustomerDialogMode.view, customer),
        onEdit: customer != null && _canEdit && !customer.isDeleted
            ? () => _open(CustomerDialogMode.edit, customer)
            : null,
      );

  Widget _filterDropdown({
    required String label,
    required String? value,
    required List<String> values,
    required ValueChanged<String?> onChanged,
  }) =>
      SizedBox(
        width: 220,
        child: DropdownButtonFormField<String>(
          initialValue: value,
          decoration: InputDecoration(labelText: label),
          items: values
              .map((item) =>
                  DropdownMenuItem(value: item, child: Text(_label(item))))
              .toList(),
          onChanged: onChanged,
        ),
      );
}

enum CustomerDialogMode { create, view, edit }

class CustomerWorkspaceDialog extends StatefulWidget {
  const CustomerWorkspaceDialog({
    super.key,
    required this.mode,
    required this.customer,
    required this.onSave,
  });

  final CustomerDialogMode mode;
  final Customer? customer;
  final Future<Customer> Function(Json payload) onSave;

  @override
  State<CustomerWorkspaceDialog> createState() =>
      _CustomerWorkspaceDialogState();
}

class _CustomerWorkspaceDialogState extends State<CustomerWorkspaceDialog> {
  final List<GlobalKey<FormState>> _forms =
      List.generate(4, (_) => GlobalKey<FormState>());
  late final Map<String, TextEditingController> _fields = {
    'code': _controller(widget.customer?.code),
    'name': _controller(widget.customer?.name),
    'display_name': _controller(widget.customer?.displayName),
    'gst_number': _controller(widget.customer?.gstNumber),
    'pan_number': _controller(widget.customer?.panNumber),
    'email': _controller(widget.customer?.email),
    'phone': _controller(widget.customer?.phone),
    'alternate_phone': _controller(widget.customer?.alternatePhone),
    'website': _controller(widget.customer?.website),
    'notes': _controller(widget.customer?.notes),
    'credit_limit': _controller(widget.customer?.creditLimit ?? '0.00'),
    'opening_balance': _controller(widget.customer?.openingBalance ?? '0.00'),
    'payment_terms_days':
        _controller(widget.customer?.paymentTermsDays.toString() ?? '0'),
    'currency_code': _controller(widget.customer?.currencyCode ?? 'INR'),
  };
  late final List<_AddressDraft> _addresses =
      (widget.customer?.addresses ?? const [])
          .map(_AddressDraft.fromAddress)
          .toList();
  late final List<_ContactDraft> _contacts =
      (widget.customer?.contacts ?? const [])
          .map(_ContactDraft.fromContact)
          .toList();
  late String _customerType = widget.customer?.customerType ?? 'BUSINESS';
  late String _status = widget.customer?.status ?? 'ACTIVE';
  int _tab = 0;
  bool _saving = false;
  bool _dirty = false;
  String? _error;

  bool get _readOnly =>
      widget.mode == CustomerDialogMode.view ||
      widget.customer?.isDeleted == true;

  TextEditingController _controller(String? value) =>
      TextEditingController(text: value ?? '');

  @override
  void initState() {
    super.initState();
    for (final TextEditingController controller in _fields.values) {
      controller.addListener(_markDirty);
    }
    for (final _AddressDraft address in _addresses) {
      _watchAddress(address);
    }
    for (final _ContactDraft contact in _contacts) {
      _watchContact(contact);
    }
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _fields.values) {
      controller
        ..removeListener(_markDirty)
        ..dispose();
    }
    for (final _AddressDraft address in _addresses) {
      address.dispose();
    }
    for (final _ContactDraft contact in _contacts) {
      contact.dispose();
    }
    super.dispose();
  }

  void _markDirty() {
    _dirty = true;
  }

  void _watchAddress(_AddressDraft address) {
    for (final TextEditingController controller in address.controllers) {
      controller.addListener(_markDirty);
    }
  }

  void _watchContact(_ContactDraft contact) {
    for (final TextEditingController controller in contact.controllers) {
      controller.addListener(_markDirty);
    }
  }

  Future<void> _close() async {
    if (_saving) return;
    if (!_readOnly && _dirty) {
      final bool discard = await showWorkspaceConfirmDialog(
        context,
        title: 'Discard customer changes?',
        message: 'Unsaved customer information will be lost.',
        confirmLabel: 'Discard changes',
        type: ConfirmationType.discardChanges,
      );
      if (!discard || !mounted) return;
    }
    if (mounted) Navigator.pop(context);
  }

  Future<void> _save() async {
    if (_readOnly || _saving) return;
    bool valid = true;
    for (final GlobalKey<FormState> form in _forms) {
      valid = (form.currentState?.validate() ?? true) && valid;
    }
    if (!valid) {
      setState(() => _error = 'Correct the highlighted fields before saving.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final Customer saved = await widget.onSave(_payload());
      if (mounted) Navigator.pop(context, saved);
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          _error = exception.message;
          _saving = false;
        });
      }
    }
  }

  Json _payload() => {
        'code': _fields['code']!.text.trim().toUpperCase(),
        'customer_type': _customerType,
        'name': _fields['name']!.text.trim(),
        'display_name': _fields['display_name']!.text.trim(),
        'gst_number': _nullable('gst_number'),
        'pan_number': _nullable('pan_number'),
        'email': _nullable('email'),
        'phone': _nullable('phone'),
        'alternate_phone': _nullable('alternate_phone'),
        'website': _nullable('website'),
        'credit_limit': _fields['credit_limit']!.text.trim(),
        'opening_balance': _fields['opening_balance']!.text.trim(),
        'payment_terms_days':
            int.tryParse(_fields['payment_terms_days']!.text.trim()) ?? 0,
        'currency_code': _fields['currency_code']!.text.trim().toUpperCase(),
        'status': _status,
        'notes': _nullable('notes'),
        'addresses': _addresses.map((address) => address.toJson()).toList(),
        'contacts': _contacts.map((contact) => contact.toJson()).toList(),
      };

  String? _nullable(String key) {
    final String value = _fields[key]!.text.trim();
    return value.isEmpty ? null : value;
  }

  @override
  Widget build(BuildContext context) => WorkspaceDialog(
        title: widget.mode == CustomerDialogMode.create
            ? 'New customer'
            : widget.customer!.displayName,
        subtitle: switch (widget.mode) {
          CustomerDialogMode.create => 'Create customer',
          CustomerDialogMode.view => 'View customer',
          CustomerDialogMode.edit => 'Edit customer',
        },
        icon: Icons.people_outline,
        body: const SizedBox.shrink(),
        selectedTab: _tab,
        onTabChanged: (value) => setState(() => _tab = value),
        loading: _saving,
        onClose: _close,
        onSave: _readOnly ? null : _save,
        tabs: [
          WorkspaceDialogTab(label: 'General', child: _generalTab()),
          WorkspaceDialogTab(label: 'Address', child: _addressTab()),
          WorkspaceDialogTab(label: 'Contacts', child: _contactTab()),
          WorkspaceDialogTab(label: 'Financial', child: _financialTab()),
          WorkspaceDialogTab(label: 'Audit', child: _auditTab()),
        ],
        footer: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(mainAxisAlignment: MainAxisAlignment.end, children: [
            OutlinedButton(
              onPressed: _saving ? null : _close,
              child: Text(_readOnly ? 'Close' : 'Cancel'),
            ),
            if (!_readOnly) ...[
              const SizedBox(width: 12),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save_outlined),
                label: Text(_saving ? 'Saving...' : 'Save'),
              ),
            ],
          ]),
        ),
      );

  Widget _generalTab() => Form(
        key: _forms[0],
        child: _tabPage([
          if (_error != null) _errorBanner(),
          _responsiveFields([
            _text('code', 'Customer code', required: true),
            _text('name', 'Customer name', required: true),
            _text('display_name', 'Display name'),
            _dropdown(
              'Customer type',
              _customerType,
              const ['INDIVIDUAL', 'BUSINESS'],
              (value) => setState(() {
                _customerType = value!;
                _dirty = true;
              }),
            ),
            _dropdown(
              'Status',
              _status,
              const ['ACTIVE', 'INACTIVE', 'ON_HOLD'],
              (value) => setState(() {
                _status = value!;
                _dirty = true;
              }),
            ),
            _text('gst_number', 'GST number'),
            _text('pan_number', 'PAN number'),
            _text('email', 'Email'),
            _text('phone', 'Phone', hint: '+919876543210'),
            _text('alternate_phone', 'Alternate phone'),
            _text('website', 'Website'),
          ]),
          _text('notes', 'Notes', lines: 4, fullWidth: true),
        ]),
      );

  Widget _addressTab() => Form(
        key: _forms[1],
        child: _tabPage([
          SectionHeader(
            title: 'Addresses',
            description: 'Maintain billing, shipping, and contact locations.',
            trailing: _readOnly
                ? null
                : FilledButton.tonalIcon(
                    onPressed: () => setState(() {
                      final _AddressDraft address = _AddressDraft.empty();
                      _watchAddress(address);
                      _addresses.add(address);
                      _dirty = true;
                    }),
                    icon: const Icon(Icons.add),
                    label: const Text('Add address'),
                  ),
          ),
          const SizedBox(height: 12),
          if (_addresses.isEmpty)
            const StandardEmptyState(
              type: EmptyStateType.noRecords,
              message: 'No addresses have been added.',
            ),
          for (int index = 0; index < _addresses.length; index++)
            _addressCard(index),
        ]),
      );

  Widget _contactTab() => Form(
        key: _forms[2],
        child: _tabPage([
          SectionHeader(
            title: 'Contact persons',
            description: 'Maintain people associated with this customer.',
            trailing: _readOnly
                ? null
                : FilledButton.tonalIcon(
                    onPressed: () => setState(() {
                      final _ContactDraft contact = _ContactDraft.empty();
                      _watchContact(contact);
                      _contacts.add(contact);
                      _dirty = true;
                    }),
                    icon: const Icon(Icons.add),
                    label: const Text('Add contact'),
                  ),
          ),
          const SizedBox(height: 12),
          if (_contacts.isEmpty)
            const StandardEmptyState(
              type: EmptyStateType.noRecords,
              message: 'No contact persons have been added.',
            ),
          for (int index = 0; index < _contacts.length; index++)
            _contactCard(index),
        ]),
      );

  Widget _financialTab() => Form(
        key: _forms[3],
        child: _tabPage([
          if (_error != null) _errorBanner(),
          _responsiveFields([
            _number('credit_limit', 'Credit limit', nonNegative: true),
            _number('opening_balance', 'Opening balance'),
            _number(
              'payment_terms_days',
              'Payment terms (days)',
              integer: true,
              nonNegative: true,
            ),
            _text('currency_code', 'Currency', required: true),
          ]),
        ]),
      );

  Widget _auditTab() {
    final Customer? customer = widget.customer;
    return _tabPage([
      if (customer == null)
        const WorkspaceEmptyState(
          title: 'Audit available after save',
          message: 'Creation metadata is recorded when the customer is saved.',
          icon: Icons.history,
        )
      else
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                _auditLine('Created by', customer.createdBy),
                _auditLine('Created date', customer.createdAt),
                _auditLine('Updated by', customer.updatedBy),
                _auditLine('Updated date', customer.updatedAt),
                _auditLine('Deleted', customer.isDeleted ? 'Yes' : 'No'),
              ],
            ),
          ),
        ),
    ]);
  }

  Widget _addressCard(int index) {
    final _AddressDraft address = _addresses[index];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(
              child: Text(
                'Address ${index + 1}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            if (!_readOnly)
              IconButton(
                tooltip: 'Delete address',
                onPressed: () => setState(() {
                  _addresses.removeAt(index).dispose();
                  _dirty = true;
                }),
                icon: const Icon(Icons.delete_outline),
              ),
          ]),
          _responsiveFields([
            _draftDropdown(
              'Address type',
              address.addressType,
              const ['BILLING', 'SHIPPING', 'OFFICE', 'HOME', 'OTHER'],
              (value) => setState(() {
                address.addressType = value!;
                _dirty = true;
              }),
            ),
            _draftText(address.line1, 'Address line 1', required: true),
            _draftText(address.line2, 'Address line 2'),
            _draftText(address.area, 'Area'),
            _draftText(address.city, 'City', required: true),
            _draftText(address.district, 'District'),
            _draftText(address.state, 'State', required: true),
            _draftText(address.country, 'Country', required: true),
            _draftText(address.postalCode, 'Postal code', required: true),
          ]),
          Wrap(spacing: 12, children: [
            FilterChip(
              label: const Text('Default billing'),
              selected: address.defaultBilling,
              onSelected: _readOnly
                  ? null
                  : (selected) => setState(() {
                        for (final _AddressDraft item in _addresses) {
                          item.defaultBilling = false;
                        }
                        address.defaultBilling = selected;
                        _dirty = true;
                      }),
            ),
            FilterChip(
              label: const Text('Default shipping'),
              selected: address.defaultShipping,
              onSelected: _readOnly
                  ? null
                  : (selected) => setState(() {
                        for (final _AddressDraft item in _addresses) {
                          item.defaultShipping = false;
                        }
                        address.defaultShipping = selected;
                        _dirty = true;
                      }),
            ),
          ]),
        ]),
      ),
    );
  }

  Widget _contactCard(int index) {
    final _ContactDraft contact = _contacts[index];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(
              child: Text(
                'Contact ${index + 1}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            if (!_readOnly)
              IconButton(
                tooltip: 'Delete contact',
                onPressed: () => setState(() {
                  _contacts.removeAt(index).dispose();
                  _dirty = true;
                }),
                icon: const Icon(Icons.delete_outline),
              ),
          ]),
          _responsiveFields([
            _draftText(contact.name, 'Name', required: true),
            _draftText(contact.designation, 'Designation'),
            _draftText(contact.mobile, 'Mobile'),
            _draftText(contact.email, 'Email'),
            _draftText(contact.department, 'Department'),
          ]),
          Align(
            alignment: Alignment.centerLeft,
            child: FilterChip(
              label: const Text('Primary contact'),
              selected: contact.primary,
              onSelected: _readOnly
                  ? null
                  : (selected) => setState(() {
                        for (final _ContactDraft item in _contacts) {
                          item.primary = false;
                        }
                        contact.primary = selected;
                        _dirty = true;
                      }),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _tabPage(List<Widget> children) => SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1100),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ),
      );

  Widget _responsiveFields(List<Widget> children) => LayoutBuilder(
        builder: (context, constraints) {
          final double width =
              constraints.maxWidth < 700 ? constraints.maxWidth : 520;
          return Wrap(
            spacing: 16,
            runSpacing: 12,
            children: [
              for (final Widget child in children)
                SizedBox(width: width, child: child),
            ],
          );
        },
      );

  Widget _text(
    String key,
    String label, {
    bool required = false,
    int lines = 1,
    bool fullWidth = false,
    String? hint,
  }) =>
      TextFormField(
        controller: _fields[key],
        readOnly: _readOnly,
        maxLines: lines,
        decoration: InputDecoration(labelText: label, hintText: hint),
        validator: required
            ? (value) =>
                value?.trim().isEmpty == true ? '$label is required.' : null
            : null,
      );

  Widget _number(
    String key,
    String label, {
    bool integer = false,
    bool nonNegative = false,
  }) =>
      TextFormField(
        controller: _fields[key],
        readOnly: _readOnly,
        decoration: InputDecoration(labelText: label),
        validator: (value) {
          final num? parsed = integer
              ? int.tryParse(value ?? '')
              : double.tryParse(value ?? '');
          if (parsed == null) return '$label must be a number.';
          if (nonNegative && parsed < 0) return '$label cannot be negative.';
          return null;
        },
      );

  Widget _dropdown(
    String label,
    String value,
    List<String> values,
    ValueChanged<String?> onChanged,
  ) =>
      DropdownButtonFormField<String>(
        initialValue: value,
        decoration: InputDecoration(labelText: label),
        items: values
            .map((item) =>
                DropdownMenuItem(value: item, child: Text(_label(item))))
            .toList(),
        onChanged: _readOnly ? null : onChanged,
      );

  Widget _draftText(
    TextEditingController controller,
    String label, {
    bool required = false,
  }) =>
      TextFormField(
        controller: controller,
        readOnly: _readOnly,
        decoration: InputDecoration(labelText: label),
        validator: required
            ? (value) =>
                value?.trim().isEmpty == true ? '$label is required.' : null
            : null,
      );

  Widget _draftDropdown(
    String label,
    String value,
    List<String> values,
    ValueChanged<String?> onChanged,
  ) =>
      DropdownButtonFormField<String>(
        initialValue: value,
        decoration: InputDecoration(labelText: label),
        items: values
            .map((item) =>
                DropdownMenuItem(value: item, child: Text(_label(item))))
            .toList(),
        onChanged: _readOnly ? null : onChanged,
      );

  Widget _auditLine(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 140,
            child: Text(label, style: Theme.of(context).textTheme.labelLarge),
          ),
          Expanded(child: SelectableText(value.isEmpty ? '—' : value)),
        ]),
      );

  Widget _errorBanner() => Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          _error!,
          style: TextStyle(
            color: Theme.of(context).colorScheme.onErrorContainer,
          ),
        ),
      );
}

class _AddressDraft {
  _AddressDraft({
    required this.id,
    required this.addressType,
    required this.line1,
    required this.line2,
    required this.area,
    required this.city,
    required this.district,
    required this.state,
    required this.country,
    required this.postalCode,
    required this.defaultBilling,
    required this.defaultShipping,
  });

  final String id;
  String addressType;
  final TextEditingController line1;
  final TextEditingController line2;
  final TextEditingController area;
  final TextEditingController city;
  final TextEditingController district;
  final TextEditingController state;
  final TextEditingController country;
  final TextEditingController postalCode;
  bool defaultBilling;
  bool defaultShipping;

  List<TextEditingController> get controllers => [
        line1,
        line2,
        area,
        city,
        district,
        state,
        country,
        postalCode,
      ];

  factory _AddressDraft.empty() => _AddressDraft(
        id: '',
        addressType: 'BILLING',
        line1: TextEditingController(),
        line2: TextEditingController(),
        area: TextEditingController(),
        city: TextEditingController(),
        district: TextEditingController(),
        state: TextEditingController(),
        country: TextEditingController(text: 'IN'),
        postalCode: TextEditingController(),
        defaultBilling: false,
        defaultShipping: false,
      );

  factory _AddressDraft.fromAddress(CustomerAddress address) => _AddressDraft(
        id: address.id,
        addressType: address.addressType,
        line1: TextEditingController(text: address.addressLine1),
        line2: TextEditingController(text: address.addressLine2),
        area: TextEditingController(text: address.area),
        city: TextEditingController(text: address.city),
        district: TextEditingController(text: address.district),
        state: TextEditingController(text: address.state),
        country: TextEditingController(text: address.country),
        postalCode: TextEditingController(text: address.postalCode),
        defaultBilling: address.isDefaultBilling,
        defaultShipping: address.isDefaultShipping,
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'address_type': addressType,
        'address_line1': line1.text.trim(),
        'address_line2': _nullIfEmpty(line2.text),
        'area': _nullIfEmpty(area.text),
        'city': city.text.trim(),
        'district': _nullIfEmpty(district.text),
        'state': state.text.trim(),
        'country': country.text.trim().toUpperCase(),
        'postal_code': postalCode.text.trim(),
        'is_default_billing': defaultBilling,
        'is_default_shipping': defaultShipping,
      };

  void dispose() {
    line1.dispose();
    line2.dispose();
    area.dispose();
    city.dispose();
    district.dispose();
    state.dispose();
    country.dispose();
    postalCode.dispose();
  }
}

class _ContactDraft {
  _ContactDraft({
    required this.id,
    required this.name,
    required this.designation,
    required this.mobile,
    required this.email,
    required this.department,
    required this.primary,
  });

  final String id;
  final TextEditingController name;
  final TextEditingController designation;
  final TextEditingController mobile;
  final TextEditingController email;
  final TextEditingController department;
  bool primary;

  List<TextEditingController> get controllers => [
        name,
        designation,
        mobile,
        email,
        department,
      ];

  factory _ContactDraft.empty() => _ContactDraft(
        id: '',
        name: TextEditingController(),
        designation: TextEditingController(),
        mobile: TextEditingController(),
        email: TextEditingController(),
        department: TextEditingController(),
        primary: false,
      );

  factory _ContactDraft.fromContact(CustomerContact contact) => _ContactDraft(
        id: contact.id,
        name: TextEditingController(text: contact.name),
        designation: TextEditingController(text: contact.designation),
        mobile: TextEditingController(text: contact.mobile),
        email: TextEditingController(text: contact.email),
        department: TextEditingController(text: contact.department),
        primary: contact.isPrimary,
      );

  Json toJson() => {
        if (id.isNotEmpty) 'id': id,
        'name': name.text.trim(),
        'designation': _nullIfEmpty(designation.text),
        'mobile': _nullIfEmpty(mobile.text),
        'email': _nullIfEmpty(email.text),
        'department': _nullIfEmpty(department.text),
        'is_primary': primary,
      };

  void dispose() {
    name.dispose();
    designation.dispose();
    mobile.dispose();
    email.dispose();
    department.dispose();
  }
}

String? _nullIfEmpty(String value) {
  final String normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

String _label(String value) => value
    .toLowerCase()
    .split('_')
    .map((word) =>
        word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');

String _dateOnly(String value) =>
    value.length >= 10 ? value.substring(0, 10) : value;

String _money(String value) =>
    double.tryParse(value)?.toStringAsFixed(2) ?? value;
