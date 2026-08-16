import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/geography.dart';
import '../../models/entities.dart';
import '../../models/vendor.dart';
import '../workspace/desktop_framework.dart';

class VendorManagementPage extends StatefulWidget {
  const VendorManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<VendorManagementPage> createState() => _VendorManagementPageState();
}

class _VendorManagementPageState extends State<VendorManagementPage> {
  static const int _rowsPerPage = 20;
  final TextEditingController _search = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  List<Vendor> _items = const [];
  Vendor? _selected;
  bool _loading = false;
  String? _error;
  int _page = 1;
  int _total = 0;
  String _sortBy = 'created_at';
  bool _descending = true;
  bool _includeDeleted = false;
  String? _status;

  bool get _canCreate =>
      widget.hasActiveFirm && widget.permissions.hasPermission('VENDOR_CREATE');
  bool get _canEdit => widget.permissions.hasPermission('VENDOR_UPDATE');
  bool get _canDelete => widget.permissions.hasPermission('VENDOR_DELETE');
  bool get _canRestore => widget.permissions.hasPermission('VENDOR_RESTORE');
  bool get _canExport => widget.permissions.hasPermission('VENDOR_EXPORT');

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    setState(() {
      _loading = true;
      _error = null;
      _page = requestedPage ?? _page;
    });
    try {
      final result = await widget.api.vendors(
        page: _page,
        search: _search.text.trim(),
        sortBy: _sortBy,
        descending: _descending,
        filters: VendorQuery(
          status: _status,
          includeDeleted: _includeDeleted,
        ),
      );
      if (!mounted) return;
      setState(() {
        _items = result.items;
        _total = result.total;
        final selectedId = _selected?.id;
        _selected = selectedId == null
            ? null
            : _items.where((item) => item.id == selectedId).isEmpty
                ? null
                : _items.firstWhere((item) => item.id == selectedId);
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open([Vendor? vendor]) async {
    final bool creating = vendor == null;
    if (creating && !_canCreate) return;
    if (!creating && !_canEdit) return;
    final Json? payload = await showDialog<Json>(
      context: context,
      builder: (context) =>
          _VendorEditorDialog(api: widget.api, vendor: vendor),
    );
    if (payload == null || !mounted) return;
    try {
      if (creating) {
        await widget.api.createVendor(payload);
      } else {
        await widget.api.updateVendor(
          vendor.id,
          payload,
          expectedVersion: preconditionFor(vendor.version),
        );
      }
      await _load();
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        saveFailureMessage(exception, 'vendor', changesKept: false),
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _delete(Vendor vendor) async {
    if (!_canDelete || vendor.isDeleted) return;
    final confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Delete vendor?',
      message: 'This vendor will be soft deleted.',
      confirmLabel: 'Delete',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deleteVendor(vendor.id);
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

  Future<void> _restore(Vendor vendor) async {
    if (!_canRestore || !vendor.isDeleted) return;
    try {
      await widget.api.restoreVendor(vendor.id);
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

  Future<void> _export() async {
    if (!_canExport) return;
    try {
      final csv = await widget.api.exportVendors(search: _search.text.trim());
      if (!mounted) return;
      final rows = csv.split('\n');
      NotificationService.show(
        context,
        'Export ready (${rows.length > 1 ? rows.length - 1 : 0} rows).',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(
        context,
        exception.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    final toolbar = WorkspaceToolbar(
      actions: const [
        ToolbarAction.newItem,
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
          !_loading &&
          switch (action) {
            ToolbarAction.newItem => _canCreate,
            ToolbarAction.edit => selected != null && !selected.isDeleted,
            ToolbarAction.delete => selected != null && !selected.isDeleted,
            ToolbarAction.refresh => true,
            ToolbarAction.export => _items.isNotEmpty,
            _ => false,
          },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.newItem:
            _open();
            break;
          case ToolbarAction.edit:
            if (selected != null) _open(selected);
            break;
          case ToolbarAction.delete:
            if (selected != null) _delete(selected);
            break;
          case ToolbarAction.refresh:
            _load();
            break;
          case ToolbarAction.export:
            _export();
            break;
          default:
            break;
        }
      },
    );
    final searchPanel = SearchFilterPanel(
      controller: _search,
      focusNode: _searchFocus,
      hintText: 'Search vendor code, name, GSTIN, PAN, email, phone',
      onSearch: (_) => _load(requestedPage: 1),
    );
    final filterPanel = FilterPanel(
      activeFilterCount: (_status == null ? 0 : 1) + (_includeDeleted ? 1 : 0),
      onApply: () => _load(requestedPage: 1),
      onClear: () {
        setState(() {
          _status = null;
          _includeDeleted = false;
        });
        _load(requestedPage: 1);
      },
      children: [
        SizedBox(
          width: 220,
          child: DropdownButtonFormField<String>(
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED']
                .map((item) => DropdownMenuItem(value: item, child: Text(item)))
                .toList(),
            onChanged: (value) => setState(() => _status = value),
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
    if (_error != null) {
      primaryContent = WorkspaceErrorState(message: _error!, onRetry: _load);
    } else if (_loading && _items.isEmpty) {
      primaryContent = const TableLoadingSkeleton();
    } else if (_items.isEmpty) {
      primaryContent = StandardEmptyState(
        type: EmptyStateType.noRecords,
        action: _canCreate
            ? FilledButton.icon(
                onPressed: _open,
                icon: const Icon(Icons.add),
                label: const Text('New vendor'),
              )
            : null,
      );
    } else {
      primaryContent = LoadingOverlay(
        loading: _loading,
        child: EnterpriseDataGrid<Vendor>(
          items: _items,
          total: _total,
          pageOffset: (_page - 1) * _rowsPerPage,
          rowsPerPage: _rowsPerPage,
          columns: [
            _column('Code', 'code'),
            _column('Name', 'name'),
            const GridColumn(key: 'gstin', label: 'GSTIN'),
            const GridColumn(key: 'phone', label: 'Phone'),
            _column('Status', 'status'),
            _column('Created', 'created_at'),
          ],
          id: (item) => item.id,
          cells: (item) => [
            item.code,
            item.displayName,
            item.gstin,
            item.mobile.isNotEmpty ? item.mobile : item.phone,
            item.isDeleted ? 'DELETED' : item.status,
            item.createdAt.split('T').first,
          ],
          selectedId: selected?.id,
          onSelect: (item) => setState(() => _selected = item),
          onOpen: (item) => _open(item),
          contextActionsFor: (item) => [
            if (_canEdit && !item.isDeleted) WorkspaceContextAction.edit,
            if (_canDelete && !item.isDeleted) WorkspaceContextAction.delete,
            if (_canRestore && item.isDeleted) WorkspaceContextAction.restore,
            WorkspaceContextAction.refresh,
          ],
          onContextAction: (action, item) {
            switch (action) {
              case WorkspaceContextAction.edit:
                _open(item);
                break;
              case WorkspaceContextAction.delete:
                _delete(item);
                break;
              case WorkspaceContextAction.restore:
                _restore(item);
                break;
              case WorkspaceContextAction.refresh:
                _load();
                break;
              default:
                break;
            }
          },
          onPageChanged: (offset) =>
              _load(requestedPage: offset ~/ _rowsPerPage + 1),
        ),
      );
    }

    return WorkspaceShortcuts(
      bindings: WorkspaceShortcutBindings(
        create: _canCreate ? _open : null,
        focusSearch: _searchFocus.requestFocus,
        refresh: _load,
        cancel:
            selected == null ? null : () => setState(() => _selected = null),
        delete: selected != null && !selected.isDeleted && _canDelete
            ? () => _delete(selected)
            : null,
      ),
      child: ManagementWorkspaceLayout(
        toolbar: toolbar,
        searchPanel: searchPanel,
        filterPanel: filterPanel,
        primaryContent: primaryContent,
        // No summary panel. Selecting a row should select it, not open a
        // second reading of it beside the table; opening a record is what
        // double-click and the row's eye icon are for. Passing null also hands
        // the table back the ~300px the panel was holding. The same decision
        // as ResourceManagementPage and the other master workspaces.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _total,
          selected: selected != null,
          message: _loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }

  GridColumn _column(String label, String sortField) => GridColumn(
        key: sortField,
        label: label,
        onSort: (ascending) {
          setState(() {
            _sortBy = sortField;
            _descending = !ascending;
          });
          _load(requestedPage: 1);
        },
      );
}

class _VendorEditorDialog extends StatefulWidget {
  const _VendorEditorDialog({required this.api, this.vendor});

  /// Needed for the geography ladder behind an address.
  final ApiClient api;
  final Vendor? vendor;

  @override
  State<_VendorEditorDialog> createState() => _VendorEditorDialogState();
}

class _VendorEditorDialogState extends State<_VendorEditorDialog>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 6, vsync: this);

  /// The vendor's addresses, edited in place.
  ///
  /// `vendor_addresses` has no text city, state or postal code at all — the
  /// geography masters are the only way to say where a vendor is, and no
  /// screen ever set those ids, so every seeded vendor address is two lines
  /// and nothing else.
  late final List<_EditableAddress> _addresses = <_EditableAddress>[
    for (final VendorAddress row in widget.vendor?.addresses ?? const [])
      _EditableAddress.from(row),
  ];
  late final TextEditingController _code =
      TextEditingController(text: widget.vendor?.code ?? '');
  late final TextEditingController _name =
      TextEditingController(text: widget.vendor?.name ?? '');
  late final TextEditingController _legalName =
      TextEditingController(text: widget.vendor?.legalName ?? '');
  late final TextEditingController _displayName =
      TextEditingController(text: widget.vendor?.displayName ?? '');
  late final TextEditingController _gstin =
      TextEditingController(text: widget.vendor?.gstin ?? '');
  late final TextEditingController _pan =
      TextEditingController(text: widget.vendor?.pan ?? '');
  late final TextEditingController _email =
      TextEditingController(text: widget.vendor?.email ?? '');
  late final TextEditingController _phone =
      TextEditingController(text: widget.vendor?.phone ?? '');
  late final TextEditingController _mobile =
      TextEditingController(text: widget.vendor?.mobile ?? '');
  late final TextEditingController _remarks =
      TextEditingController(text: widget.vendor?.remarks ?? '');
  String _status = 'ACTIVE';
  bool _gstRegistration = false;

  @override
  void initState() {
    super.initState();
    _status = widget.vendor?.status.isNotEmpty == true
        ? widget.vendor!.status
        : 'ACTIVE';
    _gstRegistration = widget.vendor?.gstRegistration ?? false;
  }

  @override
  void dispose() {
    _tabs.dispose();
    _code.dispose();
    _name.dispose();
    _legalName.dispose();
    _displayName.dispose();
    _gstin.dispose();
    _pan.dispose();
    _email.dispose();
    _phone.dispose();
    _mobile.dispose();
    _remarks.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.vendor == null ? 'Create vendor' : 'Edit vendor'),
        content: SizedBox(
          width: 900,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TabBar(
                controller: _tabs,
                isScrollable: true,
                tabs: const [
                  Tab(text: 'General'),
                  Tab(text: 'Contacts'),
                  Tab(text: 'Addresses'),
                  Tab(text: 'Banking'),
                  Tab(text: 'Tax'),
                  Tab(text: 'Notes'),
                ],
              ),
              const SizedBox(height: 12),
              SizedBox(
                height: 360,
                child: TabBarView(
                  controller: _tabs,
                  children: [
                    _generalTab(),
                    const _PlaceholderTab(
                        label: 'Contacts are managed in API payload.'),
                    _addressTab(),
                    const _PlaceholderTab(
                        label: 'Bank details are supported with primary flag.'),
                    const _PlaceholderTab(
                        label:
                            'Tax details support GST, PAN, TAN, FSSAI and profile fields.'),
                    const _PlaceholderTab(
                        label:
                            'Notes and history are persisted as vendor notes.'),
                  ],
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, _payload()),
            child: const Text('Save'),
          ),
        ],
      );

  Widget _generalTab() => ListView(
        children: [
          Row(
            children: [
              Expanded(child: _field(_code, 'Vendor Code')),
              const SizedBox(width: 12),
              Expanded(child: _field(_name, 'Vendor Name')),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: _field(_legalName, 'Legal Name')),
              const SizedBox(width: 12),
              Expanded(child: _field(_displayName, 'Display Name')),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: _field(_gstin, 'GSTIN')),
              const SizedBox(width: 12),
              Expanded(child: _field(_pan, 'PAN')),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: _field(_email, 'Email')),
              const SizedBox(width: 12),
              // Both run through the same E.164 validator as the firm and
              // customer numbers.
              Expanded(
                child: _field(_phone, 'Phone', helper: phoneHelperText),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _field(_mobile, 'Mobile', helper: phoneHelperText),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED']
                .map((item) => DropdownMenuItem(value: item, child: Text(item)))
                .toList(),
            onChanged: (value) => setState(() => _status = value ?? 'ACTIVE'),
          ),
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('GST Registration'),
            value: _gstRegistration,
            onChanged: (value) => setState(() => _gstRegistration = value),
          ),
          const SizedBox(height: 12),
          _field(_remarks, 'Remarks', maxLines: 3),
        ],
      );

  Widget _field(TextEditingController controller, String label,
          {int maxLines = 1, String? helper}) =>
      TextField(
        controller: controller,
        maxLines: maxLines,
        decoration: InputDecoration(labelText: label, helperText: helper),
      );

  /// Where the vendor is. The one form that fills the geography keys.
  Widget _addressTab() => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _addresses.isEmpty
                        ? 'No addresses yet'
                        : '${_addresses.length} address(es)',
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: () => setState(
                    () => _addresses.add(_EditableAddress.empty()),
                  ),
                  icon: const Icon(Icons.add),
                  label: const Text('Add address'),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _addresses.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: Text(
                        'A vendor address records the street lines and the '
                        'place they sit in, chosen from Sales \u2192 Places.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : ListView.builder(
                    itemCount: _addresses.length,
                    itemBuilder: (context, index) {
                      final _EditableAddress row = _addresses[index];
                      return Card(
                        margin: const EdgeInsets.symmetric(vertical: 6),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                children: [
                                  SizedBox(
                                    width: 180,
                                    child: DropdownButtonFormField<String>(
                                      initialValue: row.addressType,
                                      decoration: const InputDecoration(
                                        labelText: 'Type',
                                      ),
                                      items: const [
                                        DropdownMenuItem(
                                            value: 'BILLING',
                                            child: Text('Billing')),
                                        DropdownMenuItem(
                                            value: 'SHIPPING',
                                            child: Text('Shipping')),
                                        DropdownMenuItem(
                                            value: 'OFFICE',
                                            child: Text('Office')),
                                        DropdownMenuItem(
                                            value: 'WAREHOUSE',
                                            child: Text('Warehouse')),
                                      ],
                                      onChanged: (value) => setState(
                                        () => row.addressType =
                                            value ?? 'BILLING',
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: CheckboxListTile(
                                      contentPadding: EdgeInsets.zero,
                                      value: row.isPrimary,
                                      title: const Text('Primary'),
                                      // The API allows one primary address, so
                                      // choosing one here demotes the rest
                                      // rather than letting the save be
                                      // refused for a rule the form knows.
                                      onChanged: (value) => setState(() {
                                        for (final other in _addresses) {
                                          other.isPrimary = false;
                                        }
                                        row.isPrimary = value ?? false;
                                      }),
                                    ),
                                  ),
                                  IconButton(
                                    tooltip: 'Remove address',
                                    icon: const Icon(Icons.close),
                                    onPressed: () => setState(
                                      () => _addresses.removeAt(index),
                                    ),
                                  ),
                                ],
                              ),
                              TextField(
                                controller: row.line1,
                                decoration: const InputDecoration(
                                  labelText: 'Address line 1',
                                ),
                              ),
                              TextField(
                                controller: row.line2,
                                decoration: const InputDecoration(
                                  labelText: 'Address line 2',
                                ),
                              ),
                              const SizedBox(height: 12),
                              GeoAreaPicker(
                                api: widget.api,
                                value: row.place,
                                onChanged: (value) =>
                                    setState(() => row.place = value),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      );

  Json _payload() => {
        'code': _code.text.trim().toUpperCase(),
        'name': _name.text.trim(),
        'legal_name': _legalName.text.trim(),
        'display_name': _displayName.text.trim().isEmpty
            ? _name.text.trim()
            : _displayName.text.trim(),
        'status': _status,
        'gst_registration': _gstRegistration,
        'gstin': _gstin.text.trim().toUpperCase(),
        'pan': _pan.text.trim().toUpperCase(),
        'email': _email.text.trim(),
        'phone': _phone.text.trim(),
        'mobile': _mobile.text.trim(),
        'remarks': _remarks.text.trim(),
        'business_attributes': const <String, dynamic>{},
        // Addresses are edited here, so they are sent. The other five
        // collections are deliberately **absent**, not empty: this dialog does
        // not edit them, the API replaces rather than merges, and sending `[]`
        // destroyed a vendor's contacts, bank accounts, tax details,
        // attachments and notes every time somebody corrected a phone number.
        // Omitting them means "leave them alone".
        'addresses': [for (final row in _addresses) row.toJson()],
      };
}

class _PlaceholderTab extends StatelessWidget {
  const _PlaceholderTab({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) => Center(
        child: Text(
          label,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
}

/// One vendor address while it is being edited.
class _EditableAddress {
  _EditableAddress({
    required this.id,
    required this.addressType,
    required this.line1,
    required this.line2,
    required this.place,
    required this.isPrimary,
  });

  factory _EditableAddress.from(VendorAddress row) => _EditableAddress(
        id: row.id,
        addressType: row.addressType.isEmpty ? 'BILLING' : row.addressType,
        line1: TextEditingController(text: row.addressLine1),
        line2: TextEditingController(text: row.addressLine2),
        place: <GeoLevel, String>{
          if (row.countryId.isNotEmpty) GeoLevel.country: row.countryId,
          if (row.stateId.isNotEmpty) GeoLevel.state: row.stateId,
          if (row.districtId.isNotEmpty) GeoLevel.district: row.districtId,
          if (row.cityId.isNotEmpty) GeoLevel.city: row.cityId,
          if (row.postalCodeId.isNotEmpty)
            GeoLevel.postalCode: row.postalCodeId,
          if (row.localityId.isNotEmpty) GeoLevel.locality: row.localityId,
        },
        isPrimary: row.isPrimary,
      );

  factory _EditableAddress.empty() => _EditableAddress(
        id: '',
        addressType: 'BILLING',
        line1: TextEditingController(),
        line2: TextEditingController(),
        place: <GeoLevel, String>{},
        isPrimary: false,
      );

  /// Empty while the address is new. Sent back so the server reconciles the
  /// row rather than replacing it, which would lose its history.
  final String id;
  String addressType;
  final TextEditingController line1;
  final TextEditingController line2;
  Map<GeoLevel, String> place;
  bool isPrimary;

  String? _at(GeoLevel level) {
    final String value = place[level] ?? '';
    return value.isEmpty ? null : value;
  }

  Json toJson() => <String, dynamic>{
        if (id.isNotEmpty) 'id': id,
        'address_type': addressType,
        'address_line1': line1.text.trim(),
        'address_line2':
            line2.text.trim().isEmpty ? null : line2.text.trim(),
        'country_id': _at(GeoLevel.country),
        'state_id': _at(GeoLevel.state),
        'district_id': _at(GeoLevel.district),
        'city_id': _at(GeoLevel.city),
        'postal_code_id': _at(GeoLevel.postalCode),
        'locality_id': _at(GeoLevel.locality),
        'is_primary': isPrimary,
      };
}
