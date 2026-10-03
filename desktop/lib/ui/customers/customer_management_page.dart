import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/customer.dart';
import '../../models/pricing.dart';
import '../../models/customer_opening_bill.dart';
import '../../models/customer_records.dart';
import '../../models/entities.dart';
import '../../models/file_import.dart';
import '../../models/firm_member.dart';
import '../../models/geography.dart';
import '../../models/product.dart';
import '../../models/sales_territory.dart';
import '../../models/trade_licence.dart';
import '../../models/vendor.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/opening_bill_import_dialog.dart';
import '../workspace/reason_prompt.dart';
import '../workspace/trade_licence_quick_add.dart';
import 'credit_settings_dialog.dart';
import 'customer_group_dialog.dart';
import 'customer_records_sections.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';

part 'customer_editor_phase2.dart';

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

  /// Create or replace a customer.
  ///
  /// An update carries the version of the record the user opened, so a save
  /// aimed at a customer somebody else has changed since is refused rather
  /// than overwriting their work. `version` of zero means the server did not
  /// publish one — an older backend — and the save then goes without a
  /// precondition, exactly as it did before.
  Future<Customer> save(Customer? customer, Json payload) async =>
      customer == null
          ? _api.createCustomer(payload)
          : _api.updateCustomer(
              customer.id,
              payload,
              expectedVersion: customer.version > 0 ? customer.version : null,
            );

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
  bool get _canImport => widget.permissions.hasPermission('CUSTOMER_IMPORT');

  /// The segments this firm sells to, and what each is normally given.
  ///
  /// Beside the credit policy rather than behind a menu: a group decides a
  /// price, so somebody raising a document needs to reach it from the screen
  /// they are already on.
  Future<void> _openCustomerGroups() => showDialog<bool>(
        context: context,
        builder: (_) => CustomerGroupDialog(
          api: widget.api,
          permissions: widget.permissions,
        ),
      ).then((_) => _controller.load());

  /// Show the firm's credit policy, and let the right role change it.
  Future<void> _openCreditSettings() => showDialog<bool>(
        context: context,
        builder: (_) => CreditSettingsDialog(
          api: widget.api,
          permissions: widget.permissions,
        ),
      );

  @override
  void initState() {
    super.initState();
    _searchFocus.addListener(_changed);
    _controller.load();
    unawaited(_loadSummary());
  }

  /// How many customers stand in each status, for the phase 2 counters.
  Map<String, dynamic> _summary = const {};

  Future<void> _loadSummary() async {
    try {
      final Map<String, dynamic> response =
          await widget.api.documentSummary('customers');
      final dynamic data = response['data'];
      if (!mounted) return;
      setState(() => _summary = data is Map<String, dynamic> ? data : response);
    } on ApiException {
      // The counters are a convenience; the list stands without them.
    }
  }

  /// Phase 2 (the wireframe's "Active 15  On hold 2"): one counter per
  /// status, and clicking one filters the list to it -- again for all.
  List<Widget> _statusCounters() => [
        for (final (String label, String status, String key) in const [
          ('Active', 'ACTIVE', 'active'),
          ('On hold', 'ON_HOLD', 'on_hold'),
          ('Inactive', 'INACTIVE', 'inactive'),
        ])
          SummaryCount(
            key: ValueKey('customer-counter-$key'),
            label: label,
            value: '${_summary[key] ?? '-'}',
            selected: _status == status,
            onTap: () {
              setState(() => _status = _status == status ? null : status);
              _applyFilters();
            },
          ),
      ];

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
    // Phase 2 opens the record as a full-page tab; phase 1 keeps its dialog.
    final bool phase2 = Phase2Scope.of(context);
    Widget form(BuildContext context) => CustomerWorkspaceDialog(
          mode: mode,
          customer: customer,
          onSave: (payload) => _controller.save(customer, payload),
          // Passed as loaders rather than the client itself, matching `onSave`:
          // the dialog stays a form and does not grow an API dependency.
          loadPlaces: widget.api.geoPlaces,
          // Advisory: names who else holds the GSTIN or PAN (decision A7).
          checkIdentity: (gst, pan) => widget.api.customerIdentityCheck(
            gstNumber: gst,
            panNumber: pan,
            excludingId: customer?.id,
          ),
          loadRoutes: customer == null
              ? null
              : () => widget.api.customerRoutes(customer.id),
          loadAttributes: () =>
              widget.api.applicableAttributeDefinitions('CUSTOMER'),
          // The firm's segments, so the customer can be put in one. Passed as
          // a loader like the others; the dialog stays a form.
          loadGroups: () => widget.api
              .customerGroups(pageSize: 100)
              .then((page) => page.items),
          // The account manager picker (backlog 67 row 2), phase 2 only.
          loadMembers: phase2 ? widget.api.firmMembers : null,
          // "Also a supplier" (ACC-11), phase 2 only, for somebody who may
          // read suppliers at all.
          loadVendors: phase2 && widget.permissions.hasPermission('VENDOR_VIEW')
              ? () => fetchAllPages<Vendor>(
                    (page) => widget.api.vendors(page: page),
                  )
              : null,
          // The price level picker, phase 2 only, for somebody who may read
          // price lists at all.
          loadPriceLevels:
              phase2 && widget.permissions.hasPermission('PRICE_LIST_VIEW')
                  ? () => widget.api
                      .priceLevels()
                      .then((levels) => [
                            for (final PriceLevelRecord level in levels)
                              if (level.isActive) level,
                          ])
                  : null,
          // The server refuses a moved limit without it; the form says so first.
          mayChangeCreditLimit:
              widget.permissions.hasPermission('CUSTOMER_MANAGE_SETTINGS'),
          mayChangeStandingDiscount:
              widget.permissions.hasPermission('CUSTOMER_MANAGE_SETTINGS'),
          // Licences (backlog 54): only for a record that already exists, and
          // only for somebody who may see them at all.
          loadLicences: customer != null &&
                  widget.permissions.hasPermission('TRADE_LICENCE_VIEW')
              ? () => widget.api.tradeLicences(customerId: customer.id)
              : null,
          canManageLicences:
              widget.permissions.hasPermission('TRADE_LICENCE_MANAGE'),
          onAddLicence: customer == null
              ? null
              : () => addTradeLicenceFor(
                    context,
                    api: widget.api,
                    holderType: 'CUSTOMER',
                    customerId: customer.id,
                    holderLabel: customer.displayName.isEmpty
                        ? customer.name
                        : customer.displayName,
                  ),
          // Opening bills (backlog 36): what the customer owed on the firm's
          // first day here, bill by bill. Only for a record that exists.
          loadOpeningBills: customer != null &&
                  widget.permissions.hasPermission('CUSTOMER_VIEW')
              ? () => widget.api.customerOpeningBills(customer.id)
              : null,
          onCreateOpeningBill: customer == null
              ? null
              : (payload) =>
                  widget.api.createCustomerOpeningBill(customer.id, payload),
          onCancelOpeningBill: widget.api.cancelCustomerOpeningBill,
          canManageOpeningBills:
              widget.permissions.hasPermission('CUSTOMER_UPDATE'),
          // Bank accounts and files (MST-4), phase 2 only, existing records
          // only. The number arrives masked without the bank-details code.
          loadBankAccounts: phase2 &&
                  customer != null &&
                  widget.permissions.hasPermission('CUSTOMER_VIEW')
              ? () => widget.api.customerBankAccounts(customer.id)
              : null,
          onSaveBankAccounts: phase2 &&
                  customer != null &&
                  widget.permissions
                      .hasPermission('CUSTOMER_MANAGE_BANK_DETAILS')
              ? (accounts) async {
                  await widget.api
                      .saveCustomerBankAccounts(customer.id, accounts);
                }
              : null,
          loadFiles: phase2 &&
                  customer != null &&
                  widget.permissions.hasPermission('CUSTOMER_VIEW')
              ? () => widget.api.customerAttachments(customer.id)
              : null,
          onAddFiles: phase2 &&
                  customer != null &&
                  widget.permissions.hasPermission('CUSTOMER_UPDATE')
              ? (files) async {
                  await widget.api.addCustomerAttachments(customer.id, files);
                }
              : null,
          onRemoveFile: phase2 &&
                  customer != null &&
                  widget.permissions.hasPermission('CUSTOMER_UPDATE')
              ? (id) => widget.api.removeCustomerAttachment(customer.id, id)
              : null,
        );
    final Customer? saved = phase2
        ? await showDocument<Customer>(
            context,
            // The name, as people say it; the code is on the page itself.
            title: customer == null
                ? 'New customer'
                : customer.displayName.isEmpty
                    ? customer.name
                    : customer.displayName,
            builder: form,
          )
        : await showDialog<Customer>(
            context: context,
            barrierDismissible: false,
            builder: form,
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

  Future<void> _runImport() async {
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      barrierDismissible: false,
      builder: (context) => MasterImportDialog(
        noun: 'customers',
        fileStem: 'customer',
        downloadTemplate: (format) =>
            widget.api.customerImportTemplate(format: format),
        mappingApi: widget.api,
        mappingKind: 'customers',
        checkFile: widget.api.checkCustomerImportFile,
        canUpdate: _canEdit,
      ),
    );
    if (!mounted || report == null) return;
    await _controller.load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Imported ${report.toCreate} new, updated ${report.toUpdate} customers.',
      kind: AppNotificationKind.success,
    );
  }

  /// Bring the customers' opening bills in from one file, posted on the
  /// cutover day, all or none (D-GOLIVE-1).
  Future<void> _runOpeningBillImport() async {
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      barrierDismissible: false,
      builder: (context) =>
          OpeningBillImportDialog(api: widget.api, side: 'customers'),
    );
    if (!mounted || report == null) return;
    await _controller.load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Posted ${report.toCreate} opening bills.',
      kind: AppNotificationKind.success,
    );
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
        _money(customer.currentOutstanding),
        _money(customer.unappliedAdvanceBalance),
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
    unawaited(_loadSummary());
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
        ToolbarAction.import,
        ToolbarAction.export,
        ToolbarAction.settings,
      ],
      // Phase 2 keeps the groups under Masters > Parties > Customer Groups;
      // phase 1 keeps its button here.
      // D-GOLIVE-1. Phase 2 draws commands; phase 1 does not.
      commands: [
        if (_canImport)
          ToolbarCommand(
            id: 'import-opening-bills',
            label: 'Import opening bills',
            icon: Icons.upload_file_outlined,
            tooltip: 'Bring the opening bills in from a file',
            onPressed: widget.hasActiveFirm ? _runOpeningBillImport : null,
            // Done once, at cutover: behind "...", never a button on the line.
            menuOnly: true,
          ),
      ],
      trailing: Phase2Scope.of(context)
          ? const []
          : [
              Padding(
                padding: const EdgeInsets.only(left: 8),
                child: OutlinedButton.icon(
                  onPressed: widget.hasActiveFirm ? _openCustomerGroups : null,
                  icon: const Icon(Icons.groups_outlined, size: 18),
                  label: const Text('Groups'),
                ),
              ),
            ],
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete,
        ToolbarAction.import => _canImport,
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
            ToolbarAction.import => _canImport,
            ToolbarAction.export => _controller.items.isNotEmpty,
            // Reading the policy needs only CUSTOMER_VIEW: someone the policy
            // warns should be able to see the rule behind the warning.
            ToolbarAction.settings => true,
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
          case ToolbarAction.settings:
            _openCreditSettings();
            break;
          case ToolbarAction.import:
            _runImport();
            break;
          case ToolbarAction.print:
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
            _column('Credit limit', 'credit_limit', numeric: true),
            _column('Outstanding', 'current_outstanding', numeric: true),
            const GridColumn(key: 'advance', label: 'Advance', numeric: true),
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
            _money(customer.currentOutstanding),
            _money(customer.unappliedAdvanceBalance),
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
        // Option C (owner, 2026-09-27): the customer's actions on a bar that
        // names them, above the grid, as on the document lists.
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.record(
                name: selected.name,
                facts: [selected.code, selected.city],
                status: selected.isDeleted ? 'DELETED' : selected.status,
                onClear: _controller.clearSelection,
              ),
        searchPanel: searchPanel,
        filterPanel: filterPanel,
        // Phase 2's counters are handed to the page line by SummaryCards,
        // which draws nothing here; phase 1 is as it was.
        primaryContent: Phase2Scope.of(context)
            ? Column(children: [
                SummaryCards(children: _statusCounters()),
                Expanded(child: primaryContent),
              ])
            : primaryContent,
        // No summary panel. Selecting a row should select it, not open a
        // second reading of it beside the table; opening a record is what
        // double-click and the row's eye icon are for. Passing null also hands
        // the table back the ~300px the panel was holding. The same decision
        // as ResourceManagementPage and the other master workspaces.
        detailsPanel: null,
        statusBar: WorkspaceStatusBar(
          total: _controller.total,
          selected: selected != null,
          message: _controller.loading ? 'Refreshing...' : 'Ready',
        ),
      ),
    );
  }

  GridColumn _column(
    String label,
    String sortField, {
    bool numeric = false,
  }) =>
      GridColumn(
        key: sortField,
        label: label,
        numeric: numeric,
        onSort: (ascending) {
          _controller
            ..sortBy = sortField
            ..descending = !ascending
            ..load(requestedPage: 1);
        },
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
          isExpanded: true,
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
    required this.loadPlaces,
    this.checkIdentity,
    this.loadRoutes,
    this.loadAttributes,
    this.loadGroups,
    this.loadMembers,
    this.loadVendors,
    this.loadPriceLevels,
    this.mayChangeCreditLimit = true,
    this.mayChangeStandingDiscount = true,
    this.loadLicences,
    this.canManageLicences = false,
    this.onAddLicence,
    this.loadOpeningBills,
    this.onCreateOpeningBill,
    this.onCancelOpeningBill,
    this.canManageOpeningBills = false,
    this.loadBankAccounts,
    this.onSaveBankAccounts,
    this.loadFiles,
    this.onAddFiles,
    this.onRemoveFile,
    this.pickFiles,
  });

  final CustomerDialogMode mode;
  final Customer? customer;
  final Future<Customer> Function(Json payload) onSave;

  /// One rung of the geography ladder behind an address. A loader rather than
  /// the client itself, matching `onSave` and `loadRoutes`: the dialog stays a
  /// form and does not grow an API dependency.
  final GeoPlaceLoader loadPlaces;

  /// Names the other customers holding a GSTIN or PAN, or null when none does
  /// (decision A7). Null here skips the check. A failure of the call is
  /// swallowed by the form: the check is advisory and never blocks a save.
  final Future<String?> Function(String gst, String pan)? checkIdentity;

  /// The rounds that call this shop. Null while creating, since a customer
  /// that does not exist yet is on nothing.
  final Future<List<CustomerRouteRecord>> Function()? loadRoutes;

  /// The custom fields a customer carries in this firm. Null means the
  /// caller supplies none, and the dialog offers no Custom fields tab.
  final Future<ApplicableAttributesRecord> Function()? loadAttributes;

  /// The firm's customer groups, for the Group dropdown. Null means the
  /// caller supplies none and the dropdown is omitted.
  final Future<List<CustomerGroup>> Function()? loadGroups;

  /// The firm's people, for the account manager picker (backlog 67 row 2).
  /// Null omits the picker; the stored manager is still sent back unchanged.
  final Future<List<FirmMember>> Function()? loadMembers;

  /// The firm's suppliers, for the "Also a supplier" picker (ACC-11). Null
  /// omits the picker, and then `linked_vendor_id` is not sent at all, so a
  /// save cannot clear a link the form never showed.
  final Future<List<Vendor>> Function()? loadVendors;

  /// The firm's active price levels, for the "Price level" picker; null for a
  /// user without PRICE_LIST_VIEW, which hides the picker.
  final Future<List<PriceLevelRecord>> Function()? loadPriceLevels;

  /// Whether the user holds `CUSTOMER_MANAGE_SETTINGS`. A credit limit is a
  /// credit control, so moving an existing customer's limit takes the code
  /// that writes the credit policy (D-CFG-17); without it the field is shown
  /// and not editable. A new customer's limit stays editable: it can only
  /// tighten one that otherwise starts with none.
  final bool mayChangeCreditLimit;

  /// Whether the user holds `CUSTOMER_MANAGE_SETTINGS`. A standing discount
  /// is a price decision -- a segment's rate already takes this code -- so
  /// whoever sells on it must not be the one who sets it (D-MST-2). Without
  /// it the rate is shown and not editable, on a new customer as well: the
  /// server refuses a new customer that starts with one just the same.
  final bool mayChangeStandingDiscount;

  /// The trade licences this customer holds (backlog 54). Null hides the
  /// Licences tab entirely -- while the customer is still being created, or
  /// for a user without `TRADE_LICENCE_VIEW`.
  final Future<List<TradeLicenceRecord>> Function()? loadLicences;

  /// Whether the user holds `TRADE_LICENCE_MANAGE`, so "Add licence" shows.
  final bool canManageLicences;

  /// Opens the licence form pre-set to this customer. Returns whether one
  /// was saved, so the tab knows to re-read the list.
  final Future<bool> Function()? onAddLicence;

  /// What this customer owed on the firm's first day here, bill by bill.
  /// Null hides the Opening bills section entirely -- while the customer is
  /// still being created, or for a user without `CUSTOMER_VIEW`.
  final Future<List<CustomerOpeningBill>> Function()? loadOpeningBills;

  /// Records one opening bill for this customer, and posts it.
  final Future<CustomerOpeningBill> Function(Json payload)? onCreateOpeningBill;

  /// Takes back one opening bill, with the reason given.
  final Future<CustomerOpeningBill> Function(String billId, String reason)?
      onCancelOpeningBill;

  /// Whether the user holds `CUSTOMER_UPDATE`, so "Add opening bill" and
  /// "Cancel" show.
  final bool canManageOpeningBills;

  /// The customer's bank accounts (MST-4, phase 2 only). Null hides the
  /// section for an existing record; a new one is told to save first.
  final Future<List<CustomerBankAccount>> Function()? loadBankAccounts;

  /// Replaces the whole list of bank accounts. Null (no
  /// `CUSTOMER_MANAGE_BANK_DETAILS`) hides the Edit button.
  final Future<void> Function(List<Json> accounts)? onSaveBankAccounts;

  /// The files kept with the customer (MST-4, phase 2 only).
  final Future<List<CustomerAttachment>> Function()? loadFiles;

  /// Keeps files with the customer; null hides Add files.
  final Future<void> Function(List<Json> files)? onAddFiles;

  /// Takes one file off the customer; null hides Remove.
  final Future<void> Function(String attachmentId)? onRemoveFile;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  @override
  State<CustomerWorkspaceDialog> createState() =>
      _CustomerWorkspaceDialogState();
}

class _CustomerWorkspaceDialogState extends State<CustomerWorkspaceDialog> {
  /// Null until the rounds have been read; empty means read and none.
  List<CustomerRouteRecord>? _routes;
  bool _routesRequested = false;

  /// Null until the licences have been read; empty means read and none.
  List<TradeLicenceRecord>? _licences;
  bool _licencesRequested = false;

  /// Null until the opening bills have been read; empty means read and none.
  List<CustomerOpeningBill>? _openingBills;
  bool _openingBillsRequested = false;

  final List<GlobalKey<FormState>> _forms =
      List.generate(4, (_) => GlobalKey<FormState>());
  late final Map<String, TextEditingController> _fields = {
    'code': _controller(widget.customer?.code),
    'name': _controller(widget.customer?.name),
    'display_name': _controller(widget.customer?.displayName),
    'gst_number': _controller(widget.customer?.gstNumber),
    'pan_number': _controller(widget.customer?.panNumber),
    'tan_number': _controller(widget.customer?.tanNumber),
    'email': _controller(widget.customer?.email),
    'phone': _controller(widget.customer?.phone),
    'alternate_phone': _controller(widget.customer?.alternatePhone),
    'website': _controller(widget.customer?.website),
    'notes': _controller(widget.customer?.notes),
    'credit_limit': _controller(widget.customer?.creditLimit ?? '0.00'),
    'default_discount_percent':
        _controller(widget.customer?.defaultDiscountPercent ?? '0'),
    'opening_balance': _controller(widget.customer?.openingBalance ?? '0.00'),
    'payment_terms_days':
        _controller(widget.customer?.paymentTermsDays.toString() ?? '0'),
    'currency_code': _controller(widget.customer?.currencyCode ?? 'INR'),
    'minimum_shelf_life_days': _controller(
        widget.customer?.minimumShelfLifeDays?.toString() ?? ''),
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
  late String _gstType = widget.customer?.gstRegistrationType ?? '';
  late String _status = widget.customer?.status ?? 'ACTIVE';
  late bool _noReminders = widget.customer?.noReminders ?? false;
  late bool _whatsappOptIn = widget.customer?.whatsappOptIn ?? false;
  // Empty string is "no preference", sent as null.
  late String _preferredChannel = widget.customer?.preferredChannel ?? '';
  // Empty string is "no group", which the dropdown shows and the payload
  // sends as null.
  late String _customerGroupId = widget.customer?.customerGroupId ?? '';
  List<CustomerGroup> _groups = const [];
  bool _groupsRequested = false;
  // Empty string is "nobody", sent as null.
  late String _salesmanId = widget.customer?.salesmanId ?? '';
  List<FirmMember> _members = const [];
  // Empty string is "not a supplier", sent as null. Sent only once the
  // supplier list arrived (`_vendorsLoaded`): absent leaves the link alone.
  late String _linkedVendorId = widget.customer?.linkedVendorId ?? '';
  List<Vendor> _vendors = const [];
  bool _vendorsLoaded = false;
  // Empty string is "no level", sent as null. Sent only once the levels
  // arrived (`_priceLevelsLoaded`): absent leaves the level alone.
  late String _priceLevelId = widget.customer?.priceLevelId ?? '';
  List<PriceLevelRecord> _priceLevels = const [];
  bool _priceLevelsLoaded = false;
  late final CustomFieldsController? _customFields =
      widget.loadAttributes == null
          ? null
          : CustomFieldsController(
              load: widget.loadAttributes!,
              stored: widget.customer?.attributes ?? const [],
            );
  int _tab = 0;
  bool _saving = false;
  bool _dirty = false;
  String? _error;

  /// Phase 2: the sections are one scroll rather than tabs, each reached
  /// from the strip at the top.
  bool _flat = false;
  final Map<String, GlobalKey> _sectionKeys = {
    for (final String section in const [
      'General',
      'Money',
      'Addresses',
      'Contacts',
      'Custom fields',
      'Rounds',
      'Licences',
      'Opening bills',
      'Bank accounts',
      'Files',
    ])
      section: GlobalKey(),
  };

  void _setState(VoidCallback change) => setState(change);

  bool get _readOnly =>
      widget.mode == CustomerDialogMode.view ||
      widget.customer?.isDeleted == true;

  TextEditingController _controller(String? value) =>
      TextEditingController(text: value ?? '');

  @override
  void initState() {
    super.initState();
    _customFields?.start();
    _loadGroups();
    _loadMembers();
    _loadVendors();
    _loadPriceLevels();
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
    _customFields?.dispose();
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

  Future<void> _loadGroups() async {
    if (widget.loadGroups == null || _groupsRequested) return;
    _groupsRequested = true;
    try {
      final List<CustomerGroup> groups = await widget.loadGroups!();
      if (mounted) setState(() => _groups = groups);
    } on Object {
      // A group list that cannot be read leaves the field with just its
      // current value; it must not break the rest of the form.
      if (mounted) setState(() => _groups = const []);
    }
  }

  Future<void> _loadMembers() async {
    if (widget.loadMembers == null) return;
    try {
      final List<FirmMember> members = await widget.loadMembers!();
      if (mounted) setState(() => _members = members);
    } on Object {
      // Unreadable leaves the picker with just the stored manager.
      if (mounted) setState(() => _members = const []);
    }
  }

  Future<void> _loadPriceLevels() async {
    if (widget.loadPriceLevels == null) return;
    try {
      final List<PriceLevelRecord> levels = await widget.loadPriceLevels!();
      if (mounted) {
        setState(() {
          _priceLevels = levels;
          _priceLevelsLoaded = true;
        });
      }
    } on Object {
      // Unreadable: no picker, and nothing about the level is sent.
      if (mounted) setState(() => _priceLevelsLoaded = false);
    }
  }

  /// The Price level picker. Values are level ids; '' is "no level". A stored
  /// level that is no longer active stays selectable as its own item so a
  /// save does not clear it.
  Widget _priceLevelDropdown() {
    final List<DropdownMenuItem<String>> items = [
      const DropdownMenuItem(value: '', child: Text('No level')),
      for (final PriceLevelRecord level in _priceLevels)
        DropdownMenuItem(
          value: level.id,
          child: Text(level.label, overflow: TextOverflow.ellipsis),
        ),
    ];
    if (_priceLevelId.isNotEmpty &&
        !_priceLevels.any((level) => level.id == _priceLevelId)) {
      items.add(DropdownMenuItem(
        value: _priceLevelId,
        child: const Text('Current level'),
      ));
    }
    return DropdownButtonFormField<String>(
      key: const ValueKey('customer-price-level'),
      isExpanded: true,
      initialValue: _priceLevelId,
      decoration: const InputDecoration(
        labelText: 'Price level',
        helperText: "Blank: the group's level, else the product's price",
      ),
      items: items,
      onChanged: _readOnly
          ? null
          : (value) => setState(() {
                _priceLevelId = value ?? '';
                _dirty = true;
              }),
    );
  }

  Future<void> _loadVendors() async {
    if (widget.loadVendors == null) return;
    try {
      final List<Vendor> vendors = await widget.loadVendors!();
      if (mounted) {
        setState(() {
          _vendors = vendors;
          _vendorsLoaded = true;
        });
      }
    } on Object {
      // Unreadable: no picker, and nothing about the link is sent.
      if (mounted) setState(() => _vendorsLoaded = false);
    }
  }

  /// The "Also a supplier" picker (ACC-11). Values are vendor ids; '' is
  /// "not a supplier". A stored link that is not in the loaded list stays
  /// selectable as its own item so a save does not clear it.
  Widget _linkedVendorDropdown() {
    String label(Vendor vendor) =>
        vendor.displayName.isNotEmpty ? vendor.displayName : vendor.name;
    final List<DropdownMenuItem<String>> items = [
      const DropdownMenuItem(value: '', child: Text('Not a supplier')),
      for (final Vendor vendor in _vendors)
        DropdownMenuItem(
          value: vendor.id,
          child: Text(
            '${vendor.code}  ${label(vendor)}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
    ];
    if (_linkedVendorId.isNotEmpty &&
        !_vendors.any((vendor) => vendor.id == _linkedVendorId)) {
      items.add(DropdownMenuItem(
        value: _linkedVendorId,
        child: const Text('Linked supplier'),
      ));
    }
    return DropdownButtonFormField<String>(
      key: const ValueKey('customer-linked-vendor'),
      isExpanded: true,
      initialValue: _linkedVendorId,
      decoration: const InputDecoration(
        labelText: 'Also a supplier',
        helperText: 'The supplier record of the same business; the two '
            'accounts can then be read and set off together',
      ),
      items: items,
      onChanged: _readOnly
          ? null
          : (value) => setState(() {
                _linkedVendorId = value ?? '';
                _dirty = true;
              }),
    );
  }

  /// The account manager picker (backlog 67 row 2). Values are user ids;
  /// '' is nobody. A stored manager who has since left the firm is not in
  /// the list and stays selectable as its own item, so a save does not
  /// silently clear them.
  Widget _managerDropdown() {
    final List<DropdownMenuItem<String>> items = [
      const DropdownMenuItem(value: '', child: Text('Nobody in particular')),
      for (final FirmMember member in _members)
        DropdownMenuItem(value: member.userId, child: Text(member.label)),
    ];
    if (_salesmanId.isNotEmpty &&
        !_members.any((member) => member.userId == _salesmanId)) {
      items.add(DropdownMenuItem(
        value: _salesmanId,
        child: const Text('Current manager (no longer a member)'),
      ));
    }
    return DropdownButtonFormField<String>(
      key: const ValueKey('customer-account-manager'),
      isExpanded: true,
      initialValue: _salesmanId,
      decoration: const InputDecoration(
        labelText: 'Account manager',
        helperText: 'New sales documents for them default to this salesman',
      ),
      items: items,
      onChanged: _readOnly
          ? null
          : (value) => setState(() {
                _salesmanId = value ?? '';
                _dirty = true;
              }),
    );
  }

  /// The Group dropdown. Values are group ids; '' is "No group". A stored id
  /// that is not in the loaded list stays selectable as its own item, or
  /// DropdownButtonFormField asserts and the form would save it away as blank
  /// -- the trap the geography picker had.
  Widget _groupDropdown() {
    final List<DropdownMenuItem<String>> items = [
      const DropdownMenuItem(value: '', child: Text('No group')),
      for (final CustomerGroup group in _groups)
        DropdownMenuItem(value: group.id, child: Text(group.name)),
    ];
    final bool missing = _customerGroupId.isNotEmpty &&
        !_groups.any((group) => group.id == _customerGroupId);
    if (missing) {
      items.add(DropdownMenuItem(
        value: _customerGroupId,
        child: const Text('Current group'),
      ));
    }
    return DropdownButtonFormField<String>(
      isExpanded: true,
      initialValue: _customerGroupId,
      decoration: const InputDecoration(labelText: 'Customer group'),
      items: items,
      onChanged: _readOnly
          ? null
          : (value) => setState(() {
                _customerGroupId = value ?? '';
                _dirty = true;
              }),
    );
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
    final String? customField = _customFields?.validate();
    if (customField != null) {
      setState(() => _error = customField);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final bool carryOn = await _confirmRepeatedIdentity();
    if (!carryOn) {
      if (mounted) setState(() => _saving = false);
      return;
    }
    try {
      final Customer saved = await widget.onSave(_payload());
      if (mounted) Navigator.pop(context, saved);
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          // A conflict needs more than the server's sentence. The user is
          // holding a form full of their own typing and is being told to
          // reload, so say plainly that closing this loses it — otherwise the
          // safe-looking action is the one that throws their work away.
          _error = exception.isConflict
              ? 'Somebody else saved this customer while you were editing it. '
                  'Your changes are still here and have not been sent. Copy '
                  'anything you need, then close and reopen to see theirs.'
              : exception.message;
          _saving = false;
        });
      }
    }
  }

  /// Ask before saving a GSTIN or PAN another customer already holds (A7).
  ///
  /// One company has several accounts, so a repeat is allowed; the person is
  /// told and decides. Only a value that is new -- on a create, or changed
  /// from what was loaded -- is asked about. The check is advisory, so a
  /// failure of the call saves as before.
  Future<bool> _confirmRepeatedIdentity() async {
    final check = widget.checkIdentity;
    if (check == null) return true;
    final String gst = (_nullable('gst_number') ?? '').toUpperCase();
    final String pan = (_nullable('pan_number') ?? '').toUpperCase();
    final Customer? loaded = widget.customer;
    final bool gstNew = gst.isNotEmpty &&
        (loaded == null || gst != loaded.gstNumber.trim().toUpperCase());
    final bool panNew = pan.isNotEmpty &&
        (loaded == null || pan != loaded.panNumber.trim().toUpperCase());
    if (!gstNew && !panNew) return true;
    String? message;
    try {
      message = await check(gstNew ? gst : '', panNew ? pan : '');
    } on Object {
      return true;
    }
    if (message == null || !mounted) return true;
    return AppDialogs.confirm(
      context,
      title: 'Same GSTIN or PAN on another customer',
      message: '$message\n\nOne company may have several accounts. '
          'Save anyway?',
      confirmLabel: 'Save anyway',
    );
  }

  Json _payload() => {
        // Blank on a new customer: the server issues the next code.
        if (widget.mode != CustomerDialogMode.create ||
            _fields['code']!.text.trim().isNotEmpty)
          'code': _fields['code']!.text.trim().toUpperCase(),
        'customer_type': _customerType,
        'name': _fields['name']!.text.trim(),
        'display_name': _fields['display_name']!.text.trim(),
        'gst_number': _nullable('gst_number'),
        'pan_number': _nullable('pan_number'),
        'tan_number': _nullable('tan_number'),
        'gst_registration_type': _gstType.isEmpty ? null : _gstType,
        'email': _nullable('email'),
        'phone': _nullable('phone'),
        'alternate_phone': _nullable('alternate_phone'),
        'website': _nullable('website'),
        // Empty means "no group", sent as null so it clears any prior one.
        'customer_group_id': _customerGroupId.isEmpty ? null : _customerGroupId,
        'salesman_id': _salesmanId.isEmpty ? null : _salesmanId,
        // Only once the supplier list arrived: absent means "leave the link
        // alone" and null clears it.
        if (widget.loadVendors != null && _vendorsLoaded)
          'linked_vendor_id': _linkedVendorId.isEmpty ? null : _linkedVendorId,
        // Only once the levels arrived: absent means "leave the level alone"
        // and null clears it.
        if (widget.loadPriceLevels != null && _priceLevelsLoaded)
          'price_level_id': _priceLevelId.isEmpty ? null : _priceLevelId,
        'credit_limit': _fields['credit_limit']!.text.trim(),
        'default_discount_percent':
            _fields['default_discount_percent']!.text.trim().isEmpty
                ? '0'
                : _fields['default_discount_percent']!.text.trim(),
        'opening_balance': _fields['opening_balance']!.text.trim(),
        'payment_terms_days':
            int.tryParse(_fields['payment_terms_days']!.text.trim()) ?? 0,
        'currency_code': _fields['currency_code']!.text.trim().toUpperCase(),
        // Blank means no minimum, sent as null so it clears a prior one.
        'minimum_shelf_life_days':
            int.tryParse(_fields['minimum_shelf_life_days']!.text.trim()),
        'status': _status,
        'no_reminders': _noReminders,
        'preferred_channel':
            _preferredChannel.isEmpty ? null : _preferredChannel,
        'whatsapp_opt_in': _whatsappOptIn,
        'notes': _nullable('notes'),
        'addresses': _addresses.map((address) => address.toJson()).toList(),
        'contacts': _contacts.map((contact) => contact.toJson()).toList(),
        // Only once the definitions arrived: absent means "leave them alone"
        // and an empty list means "clear them", so a form that could not
        // read the fields must not send the empty one.
        if (_customFields?.canSend ?? false)
          'attributes': _customFields!.payload(),
      };

  String? _nullable(String key) {
    final String value = _fields[key]!.text.trim();
    return value.isEmpty ? null : value;
  }

  @override
  Widget build(BuildContext context) {
    _flat = Phase2Scope.of(context);
    // Phase 2: the record as a full-page tab (design section 9, item 1).
    if (_flat) return _phase2Page(context);
    return _dialog(context);
  }

  Widget _dialog(BuildContext context) => WorkspaceDialog(
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
          if (_customFields != null)
            WorkspaceDialogTab(
              label: 'Custom fields',
              child: _tabPage([
                CustomFieldsSection(
                  controller: _customFields,
                  noun: 'customers',
                  readOnly: _readOnly,
                  onChanged: () => setState(() => _dirty = true),
                ),
              ]),
            ),
          WorkspaceDialogTab(label: 'Routes', child: _routesTab()),
          if (widget.loadLicences != null)
            WorkspaceDialogTab(label: 'Licences', child: _licencesTab()),
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
          if (_error != null && !_flat) _errorBanner(),
          _responsiveFields([
            _text(
              'code',
              'Customer code',
              required: widget.mode != CustomerDialogMode.create,
              helper: widget.mode == CustomerDialogMode.create
                  ? 'Blank: issued on save'
                  : null,
            ),
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
            if (widget.loadMembers != null) _managerDropdown(),
            if (widget.loadVendors != null && _vendorsLoaded)
              _linkedVendorDropdown(),
            _text('gst_number', 'GST number'),
            _gstTypePicker(),
            _text('pan_number', 'PAN number'),
            _text(
              'tan_number',
              'TAN',
              helper: 'Only if they deduct TDS from what they pay you',
            ),
            _text('email', 'Email'),
            // Both are validated as E.164 server-side, and the refusal names
            // the standard rather than showing the shape it wants.
            _text('phone', 'Phone', helper: phoneHelperText),
            _text('alternate_phone', 'Alternate phone',
                helper: phoneHelperText),
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
          if (_error != null && !_flat) _errorBanner(),
          _responsiveFields([
            _groupDropdown(),
            if (widget.loadPriceLevels != null && _priceLevelsLoaded)
              _priceLevelDropdown(),
            _number(
              'credit_limit',
              'Credit limit',
              nonNegative: true,
              locked: widget.mode == CustomerDialogMode.edit &&
                  !widget.mayChangeCreditLimit,
              lockedHelper: 'Changing a credit limit needs the manage '
                  'customer settings permission.',
            ),
            _number(
              'default_discount_percent',
              'Default discount %',
              nonNegative: true,
              maximum: 100,
              blankIsZero: true,
              locked: !widget.mayChangeStandingDiscount,
              lockedHelper: 'Setting a standing discount needs the manage '
                  'customer settings permission.',
            ),
            _number('opening_balance', 'Opening balance'),
            _number(
              'payment_terms_days',
              'Payment terms (days)',
              integer: true,
              nonNegative: true,
            ),
            _text('currency_code', 'Currency', required: true),
            _number(
              'minimum_shelf_life_days',
              'Minimum shelf life (days)',
              integer: true,
              blankIsNone: true,
              minimum: 1,
              maximum: 3650,
              helper: 'Blank = none. Batches with less left are refused '
                  'or flagged at dispatch.',
            ),
          ]),
          _messagingGroup(),
        ]),
      );

  /// How messages reach this customer (backlog 51). Whether any are sent at
  /// all is the firm's choice, under Settings > Messaging.
  Widget _messagingGroup() {
    final ThemeData theme = Theme.of(context);
    final String optedInAt = widget.customer?.whatsappOptInAt ?? '';
    return Column(
      key: const ValueKey('customer-messaging-group'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Text('Messaging', style: theme.textTheme.titleSmall),
        CheckboxListTile(
          key: const ValueKey('customer-no-reminders'),
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          title: const Text('No payment reminders'),
          value: _noReminders,
          onChanged: _readOnly
              ? null
              : (value) => setState(() {
                    _noReminders = value ?? false;
                    _dirty = true;
                  }),
        ),
        SizedBox(
          width: 320,
          child: DropdownButtonFormField<String>(
            key: const ValueKey('customer-preferred-channel'),
            isExpanded: true,
            initialValue: _preferredChannel,
            decoration: const InputDecoration(labelText: 'Preferred channel'),
            items: const [
              DropdownMenuItem(value: '', child: Text('No preference')),
              DropdownMenuItem(value: 'EMAIL', child: Text('Email')),
              DropdownMenuItem(value: 'WHATSAPP', child: Text('WhatsApp')),
              DropdownMenuItem(value: 'SMS', child: Text('SMS')),
            ],
            onChanged: _readOnly
                ? null
                : (value) => setState(() {
                      _preferredChannel = value ?? '';
                      _dirty = true;
                    }),
          ),
        ),
        CheckboxListTile(
          key: const ValueKey('customer-whatsapp-opt-in'),
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          title: const Text('Agreed to WhatsApp messages'),
          subtitle: optedInAt.isEmpty
              ? null
              : Text('Agreed on ${optedInAt.split('T').first}'),
          value: _whatsappOptIn,
          onChanged: _readOnly
              ? null
              : (value) => setState(() {
                    _whatsappOptIn = value ?? false;
                    _dirty = true;
                  }),
        ),
      ],
    );
  }

  /// Which rounds call this shop, and where in each.
  ///
  /// The relationship was one-directional everywhere: from a territory you
  /// could list its customers, and from a customer you could see nothing at
  /// all — so nobody could answer "is this shop on a beat?" without opening
  /// every route in turn.
  Widget _routesTab() {
    if (widget.loadRoutes == null) {
      return _tabPage([
        const WorkspaceEmptyState(
          title: 'Routes appear after save',
          message: 'A customer is put on a round from the Sales workspace.',
          icon: Icons.alt_route,
        ),
      ]);
    }
    if (!_routesRequested) {
      _routesRequested = true;
      widget.loadRoutes!().then((rows) {
        if (mounted) setState(() => _routes = rows);
      }).catchError((Object _) {
        // A round list that cannot be read costs this tab, not the dialog.
        if (mounted) setState(() => _routes = const <CustomerRouteRecord>[]);
      });
    }
    final List<CustomerRouteRecord>? rows = _routes;
    if (rows == null) {
      return _tabPage([const Center(child: CircularProgressIndicator())]);
    }
    if (rows.isEmpty) {
      return _tabPage([
        const WorkspaceEmptyState(
          title: 'On no round yet',
          message:
              'Put this customer on a route from Sales \u2192 Route Builder, '
              'or from the territory itself.',
          icon: Icons.alt_route,
        ),
      ]);
    }
    return _tabPage([
      Card(
        child: Column(
          children: [
            for (final CustomerRouteRecord row in rows)
              ListTile(
                leading: Icon(
                  row.isRoute ? Icons.alt_route : Icons.account_tree_outlined,
                ),
                title: Text('${row.code} \u2014 ${row.name}'),
                subtitle: Text(row.path),
                trailing: Wrap(
                  spacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    if (row.visitSequence != null)
                      Text('Stop ${row.visitSequence}'),
                    // The round a sale for this shop is filed under, which is
                    // what makes the by-territory reports say what they say.
                    if (row.isPrimary)
                      const StatusBadge(
                        label: 'Primary',
                        tone: StatusBadgeTone.success,
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    ]);
  }

  /// The trade licences this customer holds (backlog 54) -- read-only here;
  /// "Add licence" opens the licence form itself, pre-set to this customer.
  Widget _licencesTab() {
    if (widget.loadLicences == null) {
      return _tabPage([
        const WorkspaceEmptyState(
          title: 'Licences appear after save',
          message: 'A licence is recorded once the customer has been created.',
          icon: Icons.badge_outlined,
        ),
      ]);
    }
    if (!_licencesRequested) {
      _licencesRequested = true;
      unawaited(_reloadLicences());
    }
    final List<TradeLicenceRecord>? rows = _licences;
    final Widget header = SectionHeader(
      title: 'Trade licences',
      description: 'Licences this customer holds and when each runs out.',
      trailing: !widget.canManageLicences || widget.onAddLicence == null
          ? null
          : FilledButton.tonalIcon(
              onPressed: _addLicence,
              icon: const Icon(Icons.add),
              label: const Text('Add licence'),
            ),
    );
    if (rows == null) {
      return _tabPage(
          [header, const Center(child: CircularProgressIndicator())]);
    }
    if (rows.isEmpty) {
      return _tabPage([
        header,
        const SizedBox(height: 12),
        const StandardEmptyState(
          type: EmptyStateType.noRecords,
          message: 'No licences have been recorded for this customer.',
        ),
      ]);
    }
    return _tabPage([
      header,
      const SizedBox(height: 12),
      Card(
        child: Column(
          children: [
            for (final TradeLicenceRecord row in rows)
              ListTile(
                leading: const Icon(Icons.badge_outlined),
                title: Text(
                  '${row.licenceTypeName.isEmpty ? row.licenceTypeCode : row.licenceTypeName}'
                  ' — ${row.licenceNumber}',
                ),
                subtitle: Text(
                  row.validTo.isEmpty
                      ? 'No expiry recorded'
                      : 'Valid to ${row.validTo}',
                ),
                trailing: StatusBadge.fromStatus(row.standing),
              ),
          ],
        ),
      ),
    ]);
  }

  Future<void> _reloadLicences() async {
    try {
      final List<TradeLicenceRecord> rows = await widget.loadLicences!();
      if (mounted) setState(() => _licences = rows);
    } on Object {
      // A licence list that cannot be read costs this tab, not the dialog.
      if (mounted) setState(() => _licences = const <TradeLicenceRecord>[]);
    }
  }

  Future<void> _addLicence() async {
    final Future<bool> Function()? onAddLicence = widget.onAddLicence;
    if (onAddLicence == null) return;
    final bool saved = await onAddLicence();
    if (!saved) return;
    _licencesRequested = false;
    if (mounted) setState(() {});
  }

  /// What this customer owed on the firm's first day here (customer opening
  /// bills) -- entered once at cutover, so receipts can be set against the
  /// old bills and the ageing is right. Read-only besides "Add opening bill"
  /// and, per row, "Cancel".
  Widget _openingBillsTab() {
    if (widget.loadOpeningBills == null) {
      return const SizedBox.shrink();
    }
    if (!_openingBillsRequested) {
      _openingBillsRequested = true;
      unawaited(_reloadOpeningBills());
    }
    final List<CustomerOpeningBill>? rows = _openingBills;
    final bool canAdd =
        widget.canManageOpeningBills && widget.onCreateOpeningBill != null;
    final Widget addButton = Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(children: [
        Expanded(
          child: Text(rows == null || rows.isEmpty
              ? 'No opening bills yet'
              : '${rows.length} opening bill(s)'),
        ),
        if (canAdd)
          OutlinedButton.icon(
            onPressed: _addOpeningBill,
            icon: const Icon(Icons.add),
            label: const Text('Add opening bill'),
          ),
      ]),
    );
    if (rows == null) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        addButton,
        const Divider(height: 1),
        const Center(child: CircularProgressIndicator()),
      ]);
    }
    if (rows.isEmpty) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        addButton,
        const Divider(height: 1),
        const StandardEmptyState(
          type: EmptyStateType.noRecords,
          message: 'What this customer owed on the firm\'s first day here, '
              'bill by bill. Nothing recorded yet. Use this or the opening '
              'balance under Money, not both.',
        ),
      ]);
    }
    final bool canCancel =
        widget.canManageOpeningBills && widget.onCancelOpeningBill != null;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      addButton,
      const Divider(height: 1),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Bill no.')),
            DataColumn(label: Text('Old bill ref')),
            DataColumn(label: Text('Bill date')),
            DataColumn(label: Text('Due')),
            DataColumn(label: Text('Amount'), numeric: true),
            DataColumn(label: Text('Received'), numeric: true),
            DataColumn(label: Text('Owed'), numeric: true),
            DataColumn(label: Text('Status')),
            DataColumn(label: Text('')),
          ],
          rows: [
            for (final CustomerOpeningBill bill in rows)
              DataRow(cells: [
                DataCell(Text(bill.billNumber)),
                DataCell(Text(bill.referenceNumber)),
                DataCell(Text(bill.billDate)),
                DataCell(Text(bill.dueDate)),
                DataCell(Text(bill.amount)),
                DataCell(Text(bill.receivedAmount)),
                DataCell(Text(bill.outstandingAmount)),
                DataCell(StatusBadge.fromStatus(bill.status)),
                DataCell(
                  canCancel && bill.canCancel
                      ? TextButton(
                          key: ValueKey<String>(
                              'customer-opening-bill-cancel-${bill.id}'),
                          onPressed: () => unawaited(_cancelOpeningBill(bill)),
                          child: const Text('Cancel'),
                        )
                      : const SizedBox.shrink(),
                ),
              ]),
          ],
        ),
      ),
    ]);
  }

  Future<void> _reloadOpeningBills() async {
    try {
      final List<CustomerOpeningBill> rows = await widget.loadOpeningBills!();
      if (mounted) setState(() => _openingBills = rows);
    } on Object {
      // A list that cannot be read costs this section, not the form.
      if (mounted) {
        setState(() => _openingBills = const <CustomerOpeningBill>[]);
      }
    }
  }

  Future<void> _addOpeningBill() async {
    final Future<CustomerOpeningBill> Function(Json payload)? create =
        widget.onCreateOpeningBill;
    if (create == null) return;
    final Json? payload = await showDialog<Json>(
      context: context,
      builder: (context) => const _AddCustomerOpeningBillDialog(),
    );
    if (payload == null || !mounted) return;
    try {
      await create(payload);
      _openingBillsRequested = false;
      if (mounted) setState(() {});
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _cancelOpeningBill(CustomerOpeningBill bill) async {
    final Future<CustomerOpeningBill> Function(String, String)? cancel =
        widget.onCancelOpeningBill;
    if (cancel == null) return;
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${bill.billNumber}',
      explanation: 'This takes back what the bill added to the customer\'s '
          'balance. Refused once any receipt has been applied to it.',
      confirmLabel: 'Cancel bill',
    );
    if (reason == null || !mounted) return;
    try {
      await cancel(bill.id, reason);
      _openingBillsRequested = false;
      if (mounted) setState(() {});
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

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

  /// Show the text the chosen place will save.
  ///
  /// The server derives these columns from the keys anyway, so this is not the
  /// authority — it is the form refusing to display something different from
  /// what it is about to send. A rung the picker could not name is left as the
  /// user typed it rather than blanked.
  void _mirrorPlace(_AddressDraft address, Map<GeoLevel, String> names) {
    const Map<GeoLevel, String> fields = <GeoLevel, String>{
      GeoLevel.state: 'state',
      GeoLevel.district: 'district',
      GeoLevel.city: 'city',
      GeoLevel.postalCode: 'postalCode',
      GeoLevel.locality: 'area',
    };
    for (final MapEntry<GeoLevel, String> entry in fields.entries) {
      final String? name = names[entry.key];
      if (name == null || name.isEmpty) continue;
      switch (entry.key) {
        case GeoLevel.state:
          address.state.text = name;
        case GeoLevel.district:
          address.district.text = name;
        case GeoLevel.city:
          address.city.text = name;
        case GeoLevel.postalCode:
          address.postalCode.text = name;
        case GeoLevel.locality:
          address.area.text = name;
        case GeoLevel.country:
          break;
      }
    }
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
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Place',
              style: Theme.of(context).textTheme.labelLarge,
            ),
          ),
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Choosing a place fills the fields above from the shared '
              'masters, so two shops on the same street group together.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          const SizedBox(height: 8),
          GeoAreaPicker(
            loadPlaces: widget.loadPlaces,
            value: address.place,
            enabled: !_readOnly,
            onChanged: (value) => setState(() {
              address.place = value;
              _dirty = true;
            }),
            onNames: (names) => setState(() => _mirrorPlace(address, names)),
          ),
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

  Widget _tabPage(List<Widget> children) => _flat
      // Phase 2 lays the sections out in one scroll, so each is a column.
      ? Column(
          crossAxisAlignment: CrossAxisAlignment.stretch, children: children)
      : SingleChildScrollView(
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
          // Phase 2 fits three to a row on a wide page, two on a narrower one.
          final double width = _flat
              ? constraints.maxWidth >= 900
                  ? (constraints.maxWidth - 32) / 3
                  : constraints.maxWidth >= 560
                      ? (constraints.maxWidth - 16) / 2
                      : constraints.maxWidth
              : constraints.maxWidth < 700
                  ? constraints.maxWidth
                  : 520;
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
    String? helper,
  }) =>
      TextFormField(
        controller: _fields[key],
        readOnly: _readOnly,
        maxLines: lines,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          helperText: helper,
        ),
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
    num? maximum,
    bool blankIsZero = false,
    bool blankIsNone = false,
    num? minimum,
    bool locked = false,
    String? lockedHelper,
    String? helper,
  }) =>
      TextFormField(
        controller: _fields[key],
        readOnly: _readOnly || locked,
        decoration: InputDecoration(
          labelText: label,
          helperText: locked && !_readOnly ? lockedHelper : helper,
          helperMaxLines: 2,
        ),
        validator: (value) {
          // An emptied discount box reads as "none" and nothing else, so it
          // is accepted and sent as zero. A blank credit limit is genuinely
          // ambiguous -- unlimited, or none? -- and still has to be typed.
          if ((blankIsZero || blankIsNone) && (value ?? '').trim().isEmpty) {
            return null;
          }
          final num? parsed = integer
              ? int.tryParse(value ?? '')
              : double.tryParse(value ?? '');
          if (parsed == null) return '$label must be a number.';
          if (nonNegative && parsed < 0) return '$label cannot be negative.';
          if (minimum != null && parsed < minimum) {
            return '$label cannot be less than $minimum.';
          }
          // Caught here as well as on the server, which answers a schema
          // error naming a limit the form never mentioned.
          if (maximum != null && parsed > maximum) {
            return '$label cannot be more than $maximum.';
          }
          return null;
        },
      );

  /// The buyer's GST standing. Blank leaves it to the GSTIN: Regular with
  /// one, Unregistered without. SEZ and export change the tax and the return.
  Widget _gstTypePicker() => DropdownButtonFormField<String>(
        isExpanded: true,
        initialValue: _gstTypes.containsKey(_gstType) ? _gstType : '',
        decoration: const InputDecoration(
          labelText: 'GST registration',
          helperText: 'SEZ is always IGST; exports go in the export table',
        ),
        items: [
          for (final MapEntry<String, String> entry in _gstTypes.entries)
            DropdownMenuItem(value: entry.key, child: Text(entry.value)),
        ],
        onChanged: _readOnly
            ? null
            : (value) => setState(() {
                  _gstType = value ?? '';
                  _dirty = true;
                }),
      );

  Widget _dropdown(
    String label,
    String value,
    List<String> values,
    ValueChanged<String?> onChanged,
  ) =>
      DropdownButtonFormField<String>(
        isExpanded: true,
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
        isExpanded: true,
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
    this.place = const <GeoLevel, String>{},
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

  /// Where the address is, chosen from the shared geography masters. The text
  /// fields above stay: they are required, and a firm whose Places are empty
  /// still has to be able to record an address. Where a rung is chosen the
  /// server derives the matching text from it, and the form mirrors that so
  /// the user sees what will be saved.
  Map<GeoLevel, String> place;

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
        place: <GeoLevel, String>{
          if (address.countryId.isNotEmpty) GeoLevel.country: address.countryId,
          if (address.stateId.isNotEmpty) GeoLevel.state: address.stateId,
          if (address.districtId.isNotEmpty)
            GeoLevel.district: address.districtId,
          if (address.cityId.isNotEmpty) GeoLevel.city: address.cityId,
          if (address.postalCodeId.isNotEmpty)
            GeoLevel.postalCode: address.postalCodeId,
          if (address.localityId.isNotEmpty)
            GeoLevel.locality: address.localityId,
        },
      );

  String? _at(GeoLevel level) {
    final String value = place[level] ?? '';
    return value.isEmpty ? null : value;
  }

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
        'country_id': _at(GeoLevel.country),
        'state_id': _at(GeoLevel.state),
        'district_id': _at(GeoLevel.district),
        'city_id': _at(GeoLevel.city),
        'postal_code_id': _at(GeoLevel.postalCode),
        'locality_id': _at(GeoLevel.locality),
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

/// The GST registration types the server takes, with what a person reads.
const Map<String, String> _gstTypes = {
  '': 'From the GSTIN',
  'REGULAR': 'Regular',
  'COMPOSITION': 'Composition',
  'UNREGISTERED': 'Unregistered',
  'SEZ_WITH_PAYMENT': 'SEZ, tax paid',
  'SEZ_WITHOUT_PAYMENT': 'SEZ, under LUT (no tax)',
  'DEEMED_EXPORT': 'Deemed export',
  'OVERSEAS': 'Overseas (export)',
};

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

/// One bill a customer owed at cutover, typed in.
///
/// Returns a payload holding only the keys the write schema declares --
/// `reference_number`, `bill_date`, `due_date`, `posting_date`, `amount`,
/// `narration` -- and only the optional ones that were actually filled in,
/// because the server forbids extra fields and treats an absent key as
/// "leave it to the default" rather than null: no due date means the bill
/// date plus the customer's terms, no posting date means today.
class _AddCustomerOpeningBillDialog extends StatefulWidget {
  const _AddCustomerOpeningBillDialog();

  @override
  State<_AddCustomerOpeningBillDialog> createState() =>
      _AddCustomerOpeningBillDialogState();
}

class _AddCustomerOpeningBillDialogState
    extends State<_AddCustomerOpeningBillDialog> {
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _amount = TextEditingController();
  final TextEditingController _narration = TextEditingController();
  DateTime _billDate = DateTime.now();
  DateTime? _dueDate;
  DateTime? _postingDate;
  String? _error;

  @override
  void dispose() {
    _reference.dispose();
    _amount.dispose();
    _narration.dispose();
    super.dispose();
  }

  String _iso(DateTime date) => date.toIso8601String().substring(0, 10);

  Future<void> _pickDate({
    required DateTime initial,
    required ValueChanged<DateTime> onPicked,
  }) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) onPicked(picked);
  }

  void _submit() {
    final double amount = double.tryParse(_amount.text.trim()) ?? 0;
    if (amount <= 0) {
      setState(() => _error = 'Enter how much was still owed on this bill.');
      return;
    }
    Navigator.of(context).pop(<String, dynamic>{
      'bill_date': _iso(_billDate),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      if (_dueDate != null) 'due_date': _iso(_dueDate!),
      if (_postingDate != null) 'posting_date': _iso(_postingDate!),
      'amount': _amount.text.trim(),
      if (_narration.text.trim().isNotEmpty)
        'narration': _narration.text.trim(),
    });
  }

  Widget _dateBox({
    required String label,
    required DateTime? value,
    required VoidCallback onTap,
    VoidCallback? onClear,
    String? helperText,
  }) =>
      InkWell(
        onTap: onTap,
        child: InputDecorator(
          decoration: InputDecoration(
            labelText: label,
            helperText: helperText,
            helperMaxLines: 2,
            suffixIcon: onClear != null && value != null
                ? IconButton(
                    tooltip: 'Clear',
                    icon: const Icon(Icons.close),
                    onPressed: onClear,
                  )
                : const Icon(Icons.calendar_today, size: 18),
          ),
          child: Text(value == null ? '' : _iso(value)),
        ),
      );

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Add opening bill'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null) ...[
                  Text(
                    _error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                  const SizedBox(height: 8),
                ],
                TextField(
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: 'Old bill number',
                  ),
                ),
                const SizedBox(height: 12),
                _dateBox(
                  label: 'Bill date',
                  value: _billDate,
                  onTap: () => _pickDate(
                    initial: _billDate,
                    onPicked: (picked) => setState(() => _billDate = picked),
                  ),
                ),
                const SizedBox(height: 12),
                _dateBox(
                  label: 'Due date',
                  value: _dueDate,
                  onTap: () => _pickDate(
                    initial: _dueDate ?? _billDate,
                    onPicked: (picked) => setState(() => _dueDate = picked),
                  ),
                  onClear: () => setState(() => _dueDate = null),
                  helperText: 'blank = bill date plus the customer\'s terms',
                ),
                const SizedBox(height: 12),
                _dateBox(
                  label: 'Posting date',
                  value: _postingDate,
                  onTap: () => _pickDate(
                    initial: _postingDate ?? DateTime.now(),
                    onPicked: (picked) => setState(() => _postingDate = picked),
                  ),
                  onClear: () => setState(() => _postingDate = null),
                  helperText: 'blank = today; the day your books here start',
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _amount,
                  decoration: const InputDecoration(labelText: 'Amount owed'),
                  keyboardType: TextInputType.number,
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _narration,
                  decoration: const InputDecoration(labelText: 'Narration'),
                  maxLines: 3,
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: _submit,
            child: const Text('Save'),
          ),
        ],
      );
}
