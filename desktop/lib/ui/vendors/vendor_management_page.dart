import 'dart:async';

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

  /// The four collections this dialog used to show a sentence about.
  ///
  /// Every one of them round-trips through the API and could only be filled
  /// by import or by calling it directly: the tabs said "bank details are
  /// supported with primary flag" and offered no field to type one into.
  late final List<_EditableContact> _contacts = <_EditableContact>[
    for (final VendorContact row in widget.vendor?.contacts ?? const [])
      _EditableContact.from(row),
  ];
  late final List<_EditableBank> _banks = <_EditableBank>[
    for (final VendorBankAccount row in widget.vendor?.bankAccounts ?? const [])
      _EditableBank.from(row),
  ];
  late final List<_EditableTax> _taxes = <_EditableTax>[
    for (final VendorTaxDetail row in widget.vendor?.taxDetails ?? const [])
      _EditableTax.from(row),
  ];
  late final List<_EditableNote> _notes = <_EditableNote>[
    for (final VendorNote row in widget.vendor?.notes ?? const [])
      _EditableNote.from(row),
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

  /// The two masters a vendor points at, loaded once when the dialog opens.
  ///
  /// Empty until they arrive, and **empty is not the same as none**: while
  /// they are loading, or if the request failed, `_payload` omits both keys
  /// rather than sending null. The API replaces what it is given, so sending
  /// null for a field this dialog could not populate would clear a category
  /// somebody had set -- the shape that cost a vendor its addresses once.
  List<AssignmentOption> _categories = const [];
  List<AssignmentOption> _types = const [];
  bool _classificationsLoaded = false;
  String? _categoryId;
  String? _typeId;

  @override
  void initState() {
    super.initState();
    _status = widget.vendor?.status.isNotEmpty == true
        ? widget.vendor!.status
        : 'ACTIVE';
    _gstRegistration = widget.vendor?.gstRegistration ?? false;
    _categoryId = widget.vendor?.categoryId.isNotEmpty == true
        ? widget.vendor!.categoryId
        : null;
    _typeId =
        widget.vendor?.typeId.isNotEmpty == true ? widget.vendor!.typeId : null;
    unawaited(_loadClassifications());
  }

  Future<void> _loadClassifications() async {
    try {
      final List<List<AssignmentOption>> loaded = await Future.wait([
        widget.api.options('vendors/categories'),
        widget.api.options('vendors/types'),
      ]);
      if (!mounted) return;
      setState(() {
        _categories = loaded[0];
        _types = loaded[1];
        _classificationsLoaded = true;
      });
    } on ApiException {
      // The rest of the form still works, and the two keys stay out of the
      // payload, so nothing is lost by the list not arriving.
      if (mounted) setState(() => _classificationsLoaded = false);
    }
  }

  /// A picker for one master, with the stored id kept selectable.
  ///
  /// An id that is not in the loaded list -- a category since deactivated, or
  /// a list that has not arrived -- must stay as an item of its own, or
  /// `DropdownButtonFormField` asserts and the form renders blank. Same trap
  /// `GeoAreaPicker` documents.
  Widget _classificationPicker({
    required String label,
    required List<AssignmentOption> options,
    required String? value,
    required ValueChanged<String?> onChanged,
  }) {
    final bool missing =
        value != null && !options.any((option) => option.id == value);
    return DropdownButtonFormField<String?>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: label,
        helperText: _classificationsLoaded ? null : 'Loading...',
      ),
      items: [
        const DropdownMenuItem<String?>(value: null, child: Text('Not set')),
        if (missing)
          DropdownMenuItem<String?>(value: value, child: const Text('(current)')),
        for (final AssignmentOption option in options)
          DropdownMenuItem<String?>(value: option.id, child: Text(option.label)),
      ],
      onChanged: onChanged,
    );
  }

  @override
  void dispose() {
    for (final row in _contacts) {
      row.dispose();
    }
    for (final row in _banks) {
      row.dispose();
    }
    for (final row in _taxes) {
      row.dispose();
    }
    for (final row in _notes) {
      row.dispose();
    }
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
                    _contactsTab(),
                    _addressTab(),
                    _bankTab(),
                    _taxTab(),
                    _notesTab(),
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
          Row(
            children: [
              Expanded(
                child: _classificationPicker(
                  label: 'Category',
                  options: _categories,
                  value: _categoryId,
                  onChanged: (value) => setState(() => _categoryId = value),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _classificationPicker(
                  label: 'Type',
                  options: _types,
                  value: _typeId,
                  onChanged: (value) => setState(() => _typeId = value),
                ),
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

  /// A card list with an Add button, shared by the four collection tabs.
  ///
  /// Same shape as the address tab above it: the count, an Add, and one card
  /// per row that can be removed. Written once because four near-identical
  /// hand-rolled copies is how the "Primary" rule ends up meaning something
  /// different on each tab.
  Widget _collectionTab({
    required String noun,
    required int count,
    required String emptyMessage,
    required VoidCallback onAdd,
    required Widget Function(int index) card,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(count == 0 ? 'No $noun yet' : '$count $noun'),
                ),
                OutlinedButton.icon(
                  onPressed: () => setState(onAdd),
                  icon: const Icon(Icons.add),
                  label: Text('Add $noun'),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: count == 0
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(emptyMessage, textAlign: TextAlign.center),
                    ),
                  )
                : ListView.builder(
                    itemCount: count,
                    itemBuilder: (context, index) => Card(
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: card(index),
                      ),
                    ),
                  ),
          ),
        ],
      );

  /// One "Primary" checkbox that demotes the rest.
  ///
  /// The API keeps one primary per collection, so the choice is made here
  /// rather than letting the save be refused for a rule the form knows.
  Widget _primaryBox({
    required bool value,
    required VoidCallback demoteOthers,
    required ValueChanged<bool> onChanged,
  }) =>
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        value: value,
        title: const Text('Primary'),
        onChanged: (next) => setState(() {
          demoteOthers();
          onChanged(next ?? false);
        }),
      );

  Widget _removeButton(String tooltip, VoidCallback onRemove) => IconButton(
        tooltip: tooltip,
        onPressed: () => setState(onRemove),
        icon: const Icon(Icons.delete_outline),
      );

  Widget _contactsTab() => _collectionTab(
        noun: 'contact(s)',
        count: _contacts.length,
        emptyMessage: 'Who to call at this vendor. One contact can be marked '
            'primary; the rest stay on the record.',
        onAdd: () => _contacts.add(_EditableContact.empty()),
        card: (index) {
          final _EditableContact row = _contacts[index];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                Expanded(child: _field(row.name, 'Name')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.designation, 'Designation')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.department, 'Department')),
                _removeButton(
                  'Remove contact',
                  () => _contacts.removeAt(index),
                ),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                  child: _field(row.phone, 'Phone', helper: phoneHelperText),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _field(row.mobile, 'Mobile', helper: phoneHelperText),
                ),
                const SizedBox(width: 12),
                Expanded(child: _field(row.email, 'Email')),
              ]),
              _primaryBox(
                value: row.isPrimary,
                demoteOthers: () {
                  for (final other in _contacts) {
                    other.isPrimary = false;
                  }
                },
                onChanged: (next) => row.isPrimary = next,
              ),
            ],
          );
        },
      );

  Widget _bankTab() => _collectionTab(
        noun: 'account(s)',
        count: _banks.length,
        emptyMessage: 'Where this vendor is paid. The primary account is what '
            'a payment defaults to.',
        onAdd: () => _banks.add(_EditableBank.empty()),
        card: (index) {
          final _EditableBank row = _banks[index];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                Expanded(child: _field(row.bankName, 'Bank')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.accountName, 'Account name')),
                _removeButton('Remove account', () => _banks.removeAt(index)),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _field(row.accountNumber, 'Account number')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.ifsc, 'IFSC')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.branch, 'Branch')),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _field(row.upiId, 'UPI id')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.swiftCode, 'SWIFT')),
              ]),
              _primaryBox(
                value: row.isPrimary,
                demoteOthers: () {
                  for (final other in _banks) {
                    other.isPrimary = false;
                  }
                },
                onChanged: (next) => row.isPrimary = next,
              ),
            ],
          );
        },
      );

  Widget _taxTab() => _collectionTab(
        noun: 'registration(s)',
        count: _taxes.length,
        emptyMessage: 'The registrations this vendor trades under. One selling '
            'from two states has two GSTINs, and only one of them is primary.',
        onAdd: () => _taxes.add(_EditableTax.empty()),
        card: (index) {
          final _EditableTax row = _taxes[index];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                Expanded(child: _field(row.gstin, 'GSTIN')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.pan, 'PAN')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.tan, 'TAN')),
                _removeButton(
                  'Remove registration',
                  () => _taxes.removeAt(index),
                ),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _field(row.fssai, 'FSSAI')),
                const SizedBox(width: 12),
                Expanded(child: _field(row.drugLicense, 'Drug licence')),
                const SizedBox(width: 12),
                Expanded(
                  child: _field(row.importExportCode, 'Import/export code'),
                ),
              ]),
              _primaryBox(
                value: row.isPrimary,
                demoteOthers: () {
                  for (final other in _taxes) {
                    other.isPrimary = false;
                  }
                },
                onChanged: (next) => row.isPrimary = next,
              ),
            ],
          );
        },
      );

  Widget _notesTab() => _collectionTab(
        noun: 'note(s)',
        count: _notes.length,
        emptyMessage: 'What somebody needs to know before dealing with this '
            'vendor. Notes sit on the record; the audit trail is separate.',
        onAdd: () => _notes.add(_EditableNote.empty()),
        card: (index) {
          final _EditableNote row = _notes[index];
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                SizedBox(
                  width: 200,
                  child: DropdownButtonFormField<String>(
                    initialValue: row.noteType,
                    decoration: const InputDecoration(labelText: 'Type'),
                    items: const [
                      DropdownMenuItem(
                          value: 'GENERAL', child: Text('General')),
                      DropdownMenuItem(
                          value: 'PAYMENT', child: Text('Payment')),
                      DropdownMenuItem(
                          value: 'QUALITY', child: Text('Quality')),
                      DropdownMenuItem(
                          value: 'DELIVERY', child: Text('Delivery')),
                    ],
                    onChanged: (value) => setState(
                      () => row.noteType = value ?? 'GENERAL',
                    ),
                  ),
                ),
                const Spacer(),
                _removeButton('Remove note', () => _notes.removeAt(index)),
              ]),
              const SizedBox(height: 8),
              _field(row.note, 'Note', maxLines: 3),
            ],
          );
        },
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
                                loadPlaces: widget.api.geoPlaces,
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
        // Absent while the lists are still loading or failed to load: see
        // `_loadClassifications`. An explicit null clears the column, which is
        // right when somebody chooses "Not set" and wrong when the dialog
        // simply never knew.
        if (_classificationsLoaded) 'category_id': _categoryId,
        if (_classificationsLoaded) 'type_id': _typeId,
        'gst_registration': _gstRegistration,
        'gstin': _gstin.text.trim().toUpperCase(),
        'pan': _pan.text.trim().toUpperCase(),
        'email': _email.text.trim(),
        'phone': _phone.text.trim(),
        'mobile': _mobile.text.trim(),
        'remarks': _remarks.text.trim(),
        'business_attributes': const <String, dynamic>{},
        // Five of the six collections are edited here, so they are sent --
        // the API replaces rather than merges, and what is on screen is the
        // record. `attachments` stays **absent**, not empty: nothing in this
        // client uploads a file, and sending `[]` for a collection the dialog
        // cannot edit is what destroyed a vendor's addresses, contacts, bank
        // accounts, tax details and notes every time somebody corrected a
        // phone number. Absent means leave them alone.
        'addresses': [for (final row in _addresses) row.toJson()],
        'contacts': [for (final row in _contacts) row.toJson()],
        // The write schema names these `banking` and `tax`; the response
        // calls the same collections `bank_accounts` and `tax_details`. The
        // schema forbids extra fields, so sending the response's names is a
        // 422 rather than a silent no-op -- which is the better failure, and
        // still one worth not shipping.
        'banking': [for (final row in _banks) row.toJson()],
        'tax': [for (final row in _taxes) row.toJson()],
        'notes': [for (final row in _notes) row.toJson()],
      };
}

/// One vendor contact while it is being edited.
class _EditableContact {
  _EditableContact({
    required this.id,
    required this.name,
    required this.department,
    required this.designation,
    required this.phone,
    required this.mobile,
    required this.email,
    required this.isPrimary,
    required this.status,
  });

  factory _EditableContact.from(VendorContact row) => _EditableContact(
        id: row.id,
        name: TextEditingController(text: row.name),
        department: TextEditingController(text: row.department),
        designation: TextEditingController(text: row.designation),
        phone: TextEditingController(text: row.phone),
        mobile: TextEditingController(text: row.mobile),
        email: TextEditingController(text: row.email),
        isPrimary: row.isPrimary,
        status: row.status.isEmpty ? 'ACTIVE' : row.status,
      );

  factory _EditableContact.empty() => _EditableContact(
        id: '',
        name: TextEditingController(),
        department: TextEditingController(),
        designation: TextEditingController(),
        phone: TextEditingController(),
        mobile: TextEditingController(),
        email: TextEditingController(),
        isPrimary: false,
        status: 'ACTIVE',
      );

  /// Empty while the row is new. Sent back so the server reconciles the row
  /// rather than replacing it, which would lose what it is referenced by.
  final String id;
  final TextEditingController name;
  final TextEditingController department;
  final TextEditingController designation;
  final TextEditingController phone;
  final TextEditingController mobile;
  final TextEditingController email;
  bool isPrimary;
  String status;

  void dispose() {
    name.dispose();
    department.dispose();
    designation.dispose();
    phone.dispose();
    mobile.dispose();
    email.dispose();
  }

  Json toJson() => <String, dynamic>{
        if (id.isNotEmpty) 'id': id,
        'name': name.text.trim(),
        'department': _orNull(department),
        'designation': _orNull(designation),
        'phone': _orNull(phone),
        'mobile': _orNull(mobile),
        'email': _orNull(email),
        'is_primary': isPrimary,
        'status': status,
      };
}

/// One vendor bank account while it is being edited.
class _EditableBank {
  _EditableBank({
    required this.id,
    required this.bankName,
    required this.accountName,
    required this.accountNumber,
    required this.ifsc,
    required this.branch,
    required this.upiId,
    required this.swiftCode,
    required this.isPrimary,
  });

  factory _EditableBank.from(VendorBankAccount row) => _EditableBank(
        id: row.id,
        bankName: TextEditingController(text: row.bankName),
        accountName: TextEditingController(text: row.accountName),
        accountNumber: TextEditingController(text: row.accountNumber),
        ifsc: TextEditingController(text: row.ifsc),
        branch: TextEditingController(text: row.branch),
        upiId: TextEditingController(text: row.upiId),
        swiftCode: TextEditingController(text: row.swiftCode),
        isPrimary: row.isPrimary,
      );

  factory _EditableBank.empty() => _EditableBank(
        id: '',
        bankName: TextEditingController(),
        accountName: TextEditingController(),
        accountNumber: TextEditingController(),
        ifsc: TextEditingController(),
        branch: TextEditingController(),
        upiId: TextEditingController(),
        swiftCode: TextEditingController(),
        isPrimary: false,
      );

  final String id;
  final TextEditingController bankName;
  final TextEditingController accountName;
  final TextEditingController accountNumber;
  final TextEditingController ifsc;
  final TextEditingController branch;
  final TextEditingController upiId;
  final TextEditingController swiftCode;
  bool isPrimary;

  void dispose() {
    bankName.dispose();
    accountName.dispose();
    accountNumber.dispose();
    ifsc.dispose();
    branch.dispose();
    upiId.dispose();
    swiftCode.dispose();
  }

  Json toJson() => <String, dynamic>{
        if (id.isNotEmpty) 'id': id,
        'bank_name': bankName.text.trim(),
        'account_name': accountName.text.trim(),
        'account_number': accountNumber.text.trim(),
        // Upper-cased server-side too; doing it here keeps what was typed and
        // what was stored the same thing on screen.
        'ifsc': _orNull(ifsc, upper: true),
        'branch': _orNull(branch),
        'upi_id': _orNull(upiId),
        'swift_code': _orNull(swiftCode, upper: true),
        'is_primary': isPrimary,
      };
}

/// One vendor tax registration while it is being edited.
class _EditableTax {
  _EditableTax({
    required this.id,
    required this.gstin,
    required this.pan,
    required this.tan,
    required this.fssai,
    required this.drugLicense,
    required this.importExportCode,
    required this.isPrimary,
  });

  factory _EditableTax.from(VendorTaxDetail row) => _EditableTax(
        id: row.id,
        gstin: TextEditingController(text: row.gstin),
        pan: TextEditingController(text: row.pan),
        tan: TextEditingController(text: row.tan),
        fssai: TextEditingController(text: row.fssai),
        drugLicense: TextEditingController(text: row.drugLicense),
        importExportCode: TextEditingController(text: row.importExportCode),
        isPrimary: row.isPrimary,
      );

  factory _EditableTax.empty() => _EditableTax(
        id: '',
        gstin: TextEditingController(),
        pan: TextEditingController(),
        tan: TextEditingController(),
        fssai: TextEditingController(),
        drugLicense: TextEditingController(),
        importExportCode: TextEditingController(),
        isPrimary: false,
      );

  final String id;
  final TextEditingController gstin;
  final TextEditingController pan;
  final TextEditingController tan;
  final TextEditingController fssai;
  final TextEditingController drugLicense;
  final TextEditingController importExportCode;
  bool isPrimary;

  void dispose() {
    gstin.dispose();
    pan.dispose();
    tan.dispose();
    fssai.dispose();
    drugLicense.dispose();
    importExportCode.dispose();
  }

  Json toJson() => <String, dynamic>{
        if (id.isNotEmpty) 'id': id,
        'gstin': _orNull(gstin, upper: true),
        'pan': _orNull(pan, upper: true),
        'tan': _orNull(tan, upper: true),
        'fssai': _orNull(fssai, upper: true),
        'drug_license': _orNull(drugLicense, upper: true),
        'import_export_code': _orNull(importExportCode, upper: true),
        'is_primary': isPrimary,
      };
}

/// One vendor note while it is being edited.
class _EditableNote {
  _EditableNote({
    required this.id,
    required this.note,
    required this.noteType,
  });

  factory _EditableNote.from(VendorNote row) => _EditableNote(
        id: row.id,
        note: TextEditingController(text: row.note),
        noteType: row.noteType.isEmpty ? 'GENERAL' : row.noteType,
      );

  factory _EditableNote.empty() => _EditableNote(
        id: '',
        note: TextEditingController(),
        noteType: 'GENERAL',
      );

  final String id;
  final TextEditingController note;
  String noteType;

  void dispose() => note.dispose();

  Json toJson() => <String, dynamic>{
        if (id.isNotEmpty) 'id': id,
        'note': note.text.trim(),
        'note_type': noteType,
      };
}

/// The trimmed text, or null when the field was left blank.
///
/// The API's optional strings are nullable and length-capped; sending an empty
/// string where it expects null or a real value is how a "required" validator
/// ends up refusing a row nobody filled in.
String? _orNull(TextEditingController controller, {bool upper = false}) {
  final String value = controller.text.trim();
  if (value.isEmpty) return null;
  return upper ? value.toUpperCase() : value;
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
