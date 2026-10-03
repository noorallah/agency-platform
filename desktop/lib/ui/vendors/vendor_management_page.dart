import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/geography.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/vendor_rating.dart';
import '../../models/file_import.dart';
import '../../models/tds.dart';
import '../../models/trade_licence.dart';
import '../../models/vendor.dart';
import '../../models/vendor_opening_bill.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/opening_bill_import_dialog.dart';
import '../workspace/party_merge.dart';
import '../workspace/reason_prompt.dart';
import '../workspace/trade_licence_quick_add.dart';
import 'supplier_catalogue_section.dart';
import 'vendor_ratings_section.dart';
import '../../phase2/document_page.dart';

part 'vendor_editor_phase2.dart';

class VendorManagementPage extends StatefulWidget {
  const VendorManagementPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveExportOverride,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Injected by tests, which cannot open a native save dialog.
  final SaveExportOverride? saveExportOverride;

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
  bool get _canImport => widget.permissions.hasPermission('VENDOR_IMPORT');

  @override
  void initState() {
    super.initState();
    _load();
    unawaited(_loadSummary());
  }

  /// How many vendors stand in each status, for the phase 2 counters.
  Map<String, dynamic> _summary = const {};

  Future<void> _loadSummary() async {
    try {
      final Map<String, dynamic> response =
          await widget.api.documentSummary('vendors');
      final dynamic data = response['data'];
      if (!mounted) return;
      setState(() =>
          _summary = data is Map<String, dynamic> ? data : response);
    } on ApiException {
      // The counters are a convenience; the list stands without them.
    }
  }

  /// Phase 2 (as Customers): one counter per status, and clicking one
  /// filters the list to it -- again for all.
  List<Widget> _statusCounters() => [
        for (final (String label, String status, String key) in const [
          ('Active', 'ACTIVE', 'active'),
          ('Inactive', 'INACTIVE', 'inactive'),
          ('Draft', 'DRAFT', 'draft'),
        ])
          SummaryCount(
            key: ValueKey('vendor-counter-$key'),
            label: label,
            value: '${_summary[key] ?? '-'}',
            selected: _status == status,
            onTap: () {
              setState(() => _status = _status == status ? null : status);
              _load(requestedPage: 1);
            },
          ),
      ];

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
    // Phase 2 opens the record as a full-page tab titled with the vendor's
    // name (owner, 2026-09-26); phase 1 keeps its dialog.
    final bool phase2 = Phase2Scope.of(context);
    // Phase 2 saves inside the page, so a refusal keeps what was typed (D-DLG-1).
    Future<void> saveIt(Json data) async {
      if (creating) {
        await saveUnlessDuplicate<Vendor>(
          context,
          noun: 'supplier',
          check: () => widget.api.vendorDuplicates(
            name: '${data['name'] ?? ''}',
            phone: '${data['phone'] ?? ''}',
            gstin: '${data['gstin'] ?? ''}',
          ),
          save: () => widget.api.createVendor(data),
        );
      } else {
        await widget.api.updateVendor(
          vendor.id,
          data,
          expectedVersion: preconditionFor(vendor.version),
        );
      }
    }

    final Json? payload = phase2
        ? await showDocument<Json>(
            context,
            title: creating
                ? 'New vendor'
                : vendor.displayName.isEmpty
                    ? vendor.name
                    : vendor.displayName,
            builder: (context) => _VendorEditorDialog(
              api: widget.api,
              vendor: vendor,
              onSave: saveIt,
              loadLicences: vendor != null &&
                      widget.permissions.hasPermission('TRADE_LICENCE_VIEW')
                  ? () => widget.api.tradeLicences(vendorId: vendor.id)
                  : null,
              canManageLicences:
                  widget.permissions.hasPermission('TRADE_LICENCE_MANAGE'),
              onAddLicence: vendor == null
                  ? null
                  : () => addTradeLicenceFor(
                        context,
                        api: widget.api,
                        holderType: 'VENDOR',
                        vendorId: vendor.id,
                        holderLabel: vendor.displayName.isEmpty
                            ? vendor.name
                            : vendor.displayName,
                      ),
              loadOpeningBills: vendor != null &&
                      widget.permissions.hasPermission('VENDOR_VIEW')
                  ? () => widget.api.vendorOpeningBills(vendor.id)
                  : null,
              canManageOpeningBills:
                  widget.permissions.hasPermission('VENDOR_UPDATE'),
              showCatalogue: vendor != null &&
                  widget.permissions.hasPermission('VENDOR_VIEW'),
              canManageCatalogue:
                  widget.permissions.hasPermission('VENDOR_UPDATE'),
              canImportCatalogue:
                  widget.permissions.hasPermission('VENDOR_IMPORT'),
              loadRatings: vendor != null &&
                      (widget.permissions.hasPermission('VENDOR_VIEW') ||
                          widget.permissions.hasPermission('PURCHASE_VIEW'))
                  ? () => widget.api.vendorRatings(vendor.id)
                  : null,
              onRate: vendor == null
                  ? null
                  : (Json body) async {
                      await widget.api.saveMyVendorRating(vendor.id, body);
                    },
              onWithdrawRating: vendor == null
                  ? null
                  : () => widget.api.withdrawMyVendorRating(vendor.id),
              loadMembers: widget.api.firmMembers,
              // "Also a customer" (ACC-11): read-only, for somebody who may
              // read customers.
              loadLinkedCustomer: vendor != null &&
                      widget.permissions.hasPermission('CUSTOMER_VIEW')
                  ? () => widget.api.linkedCustomerOfVendor(vendor.id)
                  : null,
            ),
          )
        : await showDialog<Json>(
            context: context,
            builder: (context) =>
                _VendorEditorDialog(api: widget.api, vendor: vendor),
          );
    if (payload == null || !mounted) return;
    try {
      if (phase2) {
        await _load();
        return;
      }
      await saveIt(payload);
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

  /// Fold a duplicate into [survivor] (MST-3).
  Future<void> _merge(Vendor survivor) async {
    if (!_canDelete || survivor.isDeleted) return;
    final Json? result = await showPartyMergeDialog(
      context,
      noun: 'supplier',
      survivorId: survivor.id,
      survivorLabel:
          survivor.displayName.isEmpty ? survivor.name : survivor.displayName,
      likely: () => widget.api.vendorDuplicates(
        name: survivor.name,
        phone: survivor.phone,
        gstin: survivor.gstin,
        excluding: survivor.id,
      ),
      search: (text) => widget.api.vendors(search: text).then((page) => [
            for (final Vendor row in page.items)
              <String, dynamic>{
                'id': row.id,
                'code': row.code,
                'name': row.displayName.isEmpty ? row.name : row.displayName,
              },
          ]),
      merge: (body) => widget.api.mergeVendor(survivor.id, body),
    );
    if (result == null || !mounted) return;
    NotificationService.show(
      context,
      mergeSummary(result),
      kind: AppNotificationKind.success,
    );
    await _load();
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

  Future<void> _runImport() async {
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      barrierDismissible: false,
      builder: (context) => MasterImportDialog(
        noun: 'suppliers',
        fileStem: 'supplier',
        downloadTemplate: (format) =>
            widget.api.vendorImportTemplate(format: format),
        mappingApi: widget.api,
        mappingKind: 'vendors',
        checkFile: widget.api.checkVendorImportFile,
        canUpdate: _canEdit,
      ),
    );
    if (!mounted || report == null) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Imported ${report.toCreate} new, updated ${report.toUpdate} suppliers.',
      kind: AppNotificationKind.success,
    );
  }

  /// Bring the suppliers' opening bills in from one file, posted on the
  /// cutover day, all or none (D-GOLIVE-1).
  Future<void> _runOpeningBillImport() async {
    final FileImportReport? report = await showDialog<FileImportReport>(
      context: context,
      barrierDismissible: false,
      builder: (context) =>
          OpeningBillImportDialog(api: widget.api, side: 'vendors'),
    );
    if (!mounted || report == null) return;
    await _load();
    if (!mounted) return;
    NotificationService.show(
      context,
      'Posted ${report.toCreate} opening bills.',
      kind: AppNotificationKind.success,
    );
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
      // Used to report the row count and keep the rows.
      final String? path = await saveExportedText(
        suggestedName: 'vendors.csv',
        content: csv,
        override: widget.saveExportOverride,
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        path == null ? exportCancelledMessage : exportSavedMessage(path),
        kind: path == null
            ? AppNotificationKind.information
            : AppNotificationKind.success,
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
        ToolbarAction.import,
        ToolbarAction.export,
      ],
      // D-GOLIVE-1. Phase 2 draws commands; phase 1 does not.
      commands: [
        if (_canDelete && Phase2Scope.of(context))
          ToolbarCommand(
            id: 'merge',
            label: 'Merge into...',
            icon: Icons.merge_type,
            tooltip: 'Fold a duplicate supplier into the selected one',
            onPressed: _loading || selected == null || selected.isDeleted
                ? null
                : () => unawaited(_merge(selected)),
          ),
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
      isVisible: (action) => switch (action) {
        ToolbarAction.newItem => _canCreate,
        ToolbarAction.edit => _canEdit,
        ToolbarAction.delete => _canDelete,
        ToolbarAction.import => _canImport,
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
            ToolbarAction.import => _canImport && widget.hasActiveFirm,
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
          case ToolbarAction.import:
            _runImport();
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
            isExpanded: true,
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED', 'BLOCKED']
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
            const GridColumn(key: 'gst_type', label: 'GST type'),
            const GridColumn(key: 'phone', label: 'Phone'),
            _column('Status', 'status'),
            _column('Created', 'created_at'),
          ],
          id: (item) => item.id,
          cells: (item) => [
            item.code,
            item.displayName,
            item.gstin,
            item.gstTypeShort,
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
        // Option C (owner, 2026-09-27): the supplier's actions on a bar that
        // names them, above the grid, as on the document lists.
        selectionBar: true,
        selection: selected == null
            ? null
            : SelectionSummary.record(
                name: selected.displayName,
                facts: [selected.code, selected.gstin],
                status: selected.isDeleted ? 'DELETED' : selected.status,
                onClear: () => setState(() => _selected = null),
              ),
        searchPanel: searchPanel,
        filterPanel: filterPanel,
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
  const _VendorEditorDialog({
    required this.api,
    this.vendor,
    this.loadLicences,
    this.canManageLicences = false,
    this.onAddLicence,
    this.loadOpeningBills,
    this.canManageOpeningBills = false,
    this.showCatalogue = false,
    this.canManageCatalogue = false,
    this.canImportCatalogue = false,
    this.loadRatings,
    this.onRate,
    this.onWithdrawRating,
    this.loadMembers,
    this.loadLinkedCustomer,
    this.onSave,
  });

  /// Makes the create or update call. When given, the page runs it itself and
  /// stays open with the server's message on a refusal; null pops the payload
  /// for the caller to save (phase 1).
  final Future<void> Function(Json payload)? onSave;

  /// Needed for the geography ladder behind an address.
  final ApiClient api;
  final Vendor? vendor;

  /// The trade licences this vendor holds (backlog 54). Null hides the
  /// Licences section entirely -- while the vendor is still being created,
  /// or for a user without `TRADE_LICENCE_VIEW`. Left null by the phase 1
  /// caller, which keeps its fixed seven-tab layout unchanged.
  final Future<List<TradeLicenceRecord>> Function()? loadLicences;

  /// Whether the user holds `TRADE_LICENCE_MANAGE`, so "Add licence" shows.
  final bool canManageLicences;

  /// Opens the licence form pre-set to this vendor. Returns whether one was
  /// saved, so the section knows to re-read the list.
  final Future<bool> Function()? onAddLicence;

  /// What this supplier was owed on the firm's first day here. Null hides
  /// the Opening bills section entirely -- while the vendor is still being
  /// created, or for a user without `VENDOR_VIEW`.
  final Future<List<VendorOpeningBill>> Function()? loadOpeningBills;

  /// Whether the user holds `VENDOR_UPDATE`, so "Add opening bill" and
  /// "Cancel" show.
  final bool canManageOpeningBills;

  /// The supplier's catalogue (BUY-4), phase 2 only: shown for a saved
  /// supplier to somebody holding `VENDOR_VIEW`; adding and deleting rows
  /// needs `VENDOR_UPDATE` and the file import `VENDOR_IMPORT`.
  final bool showCatalogue;
  final bool canManageCatalogue;
  final bool canImportCatalogue;

  /// What people think of this supplier (BUY-15). Null hides the section for
  /// a user who can read neither `VENDOR_VIEW` nor `PURCHASE_VIEW`; a new
  /// vendor shows "Save the supplier first" instead. Phase 2 only.
  final Future<VendorRatings> Function()? loadRatings;
  final Future<void> Function(Json body)? onRate;
  final Future<void> Function()? onWithdrawRating;
  final Future<List<FirmMember>> Function()? loadMembers;

  /// The customer that is the same business as this supplier (ACC-11), as
  /// `{customer_id, code, name}` or null. Null here hides the line.
  final Future<Json?> Function()? loadLinkedCustomer;

  @override
  State<_VendorEditorDialog> createState() => _VendorEditorDialogState();
}

class _VendorEditorDialogState extends State<_VendorEditorDialog>
    with SingleTickerProviderStateMixin, SaveInDialog {
  /// Made in `initState`, not on first use: the phase 2 page never shows the
  /// tabs, and a controller first made in `dispose` looks up a ticker on a
  /// widget already gone.
  late final TabController _tabs;

  /// The vendor's custom fields, loaded for this firm. Sent only once the
  /// definitions arrived: absent leaves the stored values alone.
  late final CustomFieldsController _customFields = CustomFieldsController(
    load: () => widget.api.applicableAttributeDefinitions('VENDOR'),
    stored: widget.vendor?.attributes ?? const [],
  );

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
  late final TextEditingController _blockedReason =
      TextEditingController(text: widget.vendor?.blockedReason ?? '');
  late final TextEditingController _creditDays = TextEditingController(
      text: '${widget.vendor?.paymentTermsDays ?? 0}');
  late final TextEditingController _standingDiscount = TextEditingController(
      text: '${widget.vendor?.standingDiscountPercent ?? 0}');
  late final TextEditingController _udyam =
      TextEditingController(text: widget.vendor?.udyamNumber ?? '');
  late String _msmeCategory = widget.vendor?.msmeCategory ?? '';
  late String _defaultTdsSection = widget.vendor?.defaultTdsSection ?? '';
  late bool _msmeAgreement = widget.vendor?.msmeWrittenAgreement ?? false;
  late bool _issuesEInvoices = widget.vendor?.issuesEInvoices ?? false;
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

  /// The declared GST type; null is "Not set", which changes no tax.
  String? _gstType;

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

  /// Null until the licences have been read; empty means read and none.
  List<TradeLicenceRecord>? _licences;
  bool _licencesRequested = false;

  /// Null until the opening bills have been read; empty means read and none.
  List<VendorOpeningBill>? _openingBills;
  bool _openingBillsRequested = false;

  /// The customer of the same business, once read; null shows nothing.
  Json? _linkedCustomer;

  /// Phase 2: the sections are one scroll rather than tabs.
  bool _flat = false;
  final Map<String, GlobalKey> _sectionKeys = {
    for (final String section in const [
      'General',
      'Contacts',
      'Addresses',
      'Banking',
      'Tax',
      'Notes',
      'Custom fields',
      'Licences',
      'Opening bills',
      'Catalogue',
      'Ratings',
    ])
      section: GlobalKey(),
  };


  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 7, vsync: this);
    _customFields.start();
    _status = widget.vendor?.status.isNotEmpty == true
        ? widget.vendor!.status
        : 'ACTIVE';
    _gstRegistration = widget.vendor?.gstRegistration ?? false;
    _gstType = widget.vendor?.gstRegistrationType;
    _categoryId = widget.vendor?.categoryId.isNotEmpty == true
        ? widget.vendor!.categoryId
        : null;
    _typeId =
        widget.vendor?.typeId.isNotEmpty == true ? widget.vendor!.typeId : null;
    unawaited(_loadClassifications());
    unawaited(_loadLinkedCustomer());
  }

  Future<void> _loadLinkedCustomer() async {
    if (widget.loadLinkedCustomer == null) return;
    try {
      final Json? linked = await widget.loadLinkedCustomer!();
      if (mounted) setState(() => _linkedCustomer = linked);
    } on Object {
      // Read-only decoration: an unreadable answer shows nothing.
    }
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

  /// The trade licences this vendor holds (backlog 54) -- read-only here;
  /// "Add licence" opens the licence form itself, pre-set to this vendor.
  /// No heading of its own: `_body` already prints one, as it does for every
  /// section here.
  Widget _licencesTab() {
    if (widget.loadLicences == null) {
      return const SizedBox.shrink();
    }
    if (!_licencesRequested) {
      _licencesRequested = true;
      unawaited(_reloadLicences());
    }
    final List<TradeLicenceRecord>? rows = _licences;
    final Widget addButton = Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(children: [
        Expanded(
          child: Text(rows == null || rows.isEmpty
              ? 'No licences yet'
              : '${rows.length} licence(s)'),
        ),
        if (widget.canManageLicences && widget.onAddLicence != null)
          OutlinedButton.icon(
            onPressed: _addLicence,
            icon: const Icon(Icons.add),
            label: const Text('Add licence'),
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
          message: 'No licences have been recorded for this vendor.',
        ),
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      addButton,
      const Divider(height: 1),
      Card(
        child: Column(children: [
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
        ]),
      ),
    ]);
  }

  Future<void> _reloadLicences() async {
    try {
      final List<TradeLicenceRecord> rows = await widget.loadLicences!();
      if (mounted) setState(() => _licences = rows);
    } on Object {
      // A licence list that cannot be read costs this section, not the form.
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

  /// What this supplier was owed on the firm's first day here (vendor
  /// opening bills) -- entered once at cutover, so the balance here matches
  /// the old books without re-keying every historical purchase invoice.
  /// Read-only besides "Add opening bill" and, per row, "Cancel".
  Widget _openingBillsTab() {
    if (widget.loadOpeningBills == null) {
      return const SizedBox.shrink();
    }
    if (!_openingBillsRequested) {
      _openingBillsRequested = true;
      unawaited(_reloadOpeningBills());
    }
    final List<VendorOpeningBill>? rows = _openingBills;
    final Widget addButton = Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(children: [
        Expanded(
          child: Text(rows == null || rows.isEmpty
              ? 'No opening bills yet'
              : '${rows.length} opening bill(s)'),
        ),
        if (widget.canManageOpeningBills)
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
          message: 'What this supplier was owed on the firm\'s first day '
              'here. Nothing recorded yet.',
        ),
      ]);
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      addButton,
      const Divider(height: 1),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: const [
            DataColumn(label: Text('Bill no.')),
            DataColumn(label: Text('Supplier ref')),
            DataColumn(label: Text('Bill date')),
            DataColumn(label: Text('Due')),
            DataColumn(label: Text('Amount'), numeric: true),
            DataColumn(label: Text('Paid'), numeric: true),
            DataColumn(label: Text('Owed'), numeric: true),
            DataColumn(label: Text('Status')),
            DataColumn(label: Text('')),
          ],
          rows: [
            for (final VendorOpeningBill bill in rows)
              DataRow(cells: [
                DataCell(Text(bill.billNumber)),
                DataCell(Text(bill.referenceNumber)),
                DataCell(Text(bill.billDate)),
                DataCell(Text(bill.dueDate)),
                DataCell(Text(bill.amount)),
                DataCell(Text(bill.paidAmount)),
                DataCell(Text(bill.outstandingAmount)),
                DataCell(StatusBadge.fromStatus(bill.status)),
                DataCell(
                  widget.canManageOpeningBills && bill.canCancel
                      ? TextButton(
                          key: ValueKey<String>(
                              'opening-bill-cancel-${bill.id}'),
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
      final List<VendorOpeningBill> rows = await widget.loadOpeningBills!();
      if (mounted) setState(() => _openingBills = rows);
    } on Object {
      // A list that cannot be read costs this section, not the form.
      if (mounted) setState(() => _openingBills = const <VendorOpeningBill>[]);
    }
  }

  Future<void> _addOpeningBill() async {
    final Vendor? vendor = widget.vendor;
    if (vendor == null) return;
    final Json? payload = await showDialog<Json>(
      context: context,
      builder: (context) => const _AddOpeningBillDialog(),
    );
    if (payload == null || !mounted) return;
    try {
      await widget.api.createVendorOpeningBill(vendor.id, payload);
      _openingBillsRequested = false;
      if (mounted) setState(() {});
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _cancelOpeningBill(VendorOpeningBill bill) async {
    final String? reason = await askForReason(
      context,
      title: 'Cancel ${bill.billNumber}',
      explanation: 'This takes back what the bill added to the supplier\'s '
          'balance. Refused once any payment has been applied to it.',
      confirmLabel: 'Cancel bill',
    );
    if (reason == null || !mounted) return;
    try {
      await widget.api.cancelVendorOpeningBill(bill.id, reason);
      _openingBillsRequested = false;
      if (mounted) setState(() {});
    } on ApiException catch (exception) {
      if (!mounted) return;
      NotificationService.show(context, exception.message,
          kind: AppNotificationKind.error);
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
      isExpanded: true,
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
    _customFields.dispose();
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
    _creditDays.dispose();
    _standingDiscount.dispose();
    _blockedReason.dispose();
    _udyam.dispose();
    _email.dispose();
    _phone.dispose();
    _mobile.dispose();
    _remarks.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _flat = Phase2Scope.of(context);
    // Phase 2: the record as a full-page tab, as the customer is.
    if (_flat) return _phase2Page(context);
    return _dialog(context);
  }

  Widget _dialog(BuildContext context) => AlertDialog(
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
                  Tab(text: 'Custom fields'),
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
                    SingleChildScrollView(
                      padding: const EdgeInsets.all(8),
                      child: CustomFieldsSection(
                        controller: _customFields,
                        noun: 'vendors',
                      ),
                    ),
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
            onPressed: () {
              final String? customField = _customFields.validate();
              if (customField != null) {
                NotificationService.show(context, customField,
                    kind: AppNotificationKind.warning);
                return;
              }
              Navigator.pop(context, _payload());
            },
            child: const Text('Save'),
          ),
        ],
      );

  Widget _generalTab() => ListView(
        // Phase 2 lays it out inside the page's own scroll.
        shrinkWrap: _flat,
        physics: _flat ? const NeverScrollableScrollPhysics() : null,
        children: [
          Row(
            children: [
              Expanded(
                child: _field(
                  _code,
                  'Vendor Code',
                  helper: widget.vendor == null ? 'Blank: issued on save' : null,
                ),
              ),
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
              const SizedBox(width: 12),
              // A declaration, not a default: blank changes no tax, and the
              // server refuses a type that disagrees with the GSTIN.
              Expanded(
                child: DropdownButtonFormField<String?>(
                  key: const ValueKey('vendor-gst-type'),
                  isExpanded: true,
                  initialValue: _gstType,
                  decoration: InputDecoration(
                    labelText: 'GST type',
                    helperText: _gstType == null
                        ? vendorGstTypeNotSet
                        : vendorGstTypeLabels[_gstType],
                    helperMaxLines: 2,
                  ),
                  items: [
                    const DropdownMenuItem<String?>(
                      value: null,
                      child: Text('Not set'),
                    ),
                    for (final MapEntry<String, String> option
                        in vendorGstTypeLabels.entries)
                      DropdownMenuItem<String?>(
                        value: option.key,
                        child: Text(vendorGstTypeName(option.key)),
                      ),
                  ],
                  onChanged: (value) => setState(() => _gstType = value),
                ),
              ),
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
            isExpanded: true,
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: const ['DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED', 'BLOCKED']
                .map((item) => DropdownMenuItem(value: item, child: Text(item)))
                .toList(),
            onChanged: (value) => setState(() => _status = value ?? 'ACTIVE'),
          ),
          // A block stops new orders and bills and says why to whoever meets
          // it (backlog 69 row 4); the server refuses one with no reason.
          if (_status == 'BLOCKED') ...[
            const SizedBox(height: 12),
            _field(_blockedReason, 'Why blocked',
                helper: 'Shown to whoever tries to order from or bill them'),
          ],
          const SizedBox(height: 12),
          SwitchListTile(
            title: const Text('GST Registration'),
            value: _gstRegistration,
            onChanged: (value) => setState(() => _gstRegistration = value),
          ),
          SwitchListTile(
            key: const ValueKey('vendor-issues-e-invoices'),
            title: const Text('Supplier e-invoices (bills carry an IRN)'),
            subtitle: const Text(
                'A bill from them with no IRN is warned about when it is '
                'entered (rule 48(4)).'),
            value: _issuesEInvoices,
            onChanged: (value) => setState(() => _issuesEInvoices = value),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _field(_standingDiscount, 'Standing discount %',
                    helper: 'Taken off every purchase line that names no '
                        'discount of its own'),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _field(_creditDays, 'Credit days',
                    helper: "A bill's due date defaults from this"),
              ),
              const SizedBox(width: 12),
              Expanded(child: _field(_udyam, 'Udyam number')),
              const SizedBox(width: 12),
              Expanded(
                child: DropdownButtonFormField<String>(
                  isExpanded: true,
                  initialValue: _msmeCategory,
                  decoration: const InputDecoration(labelText: 'MSME'),
                  items: const [
                    DropdownMenuItem(value: '', child: Text('Not MSME')),
                    DropdownMenuItem(value: 'MICRO', child: Text('Micro')),
                    DropdownMenuItem(value: 'SMALL', child: Text('Small')),
                    DropdownMenuItem(value: 'MEDIUM', child: Text('Medium')),
                  ],
                  onChanged: (value) =>
                      setState(() => _msmeCategory = value ?? ''),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            key: const ValueKey('vendor-default-tds-section'),
            isExpanded: true,
            initialValue: _defaultTdsSection,
            decoration: const InputDecoration(
              labelText: 'Usual TDS section',
              helperText: 'Prefills the section when paying this supplier',
            ),
            items: [
              const DropdownMenuItem(value: '', child: Text('None')),
              for (final MapEntry<String, String> entry in tdsSections.entries)
                DropdownMenuItem(
                  value: entry.key,
                  child: Text(
                    '${entry.key} - ${entry.value}',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: (value) =>
                setState(() => _defaultTdsSection = value ?? ''),
          ),
          if (_msmeCategory == 'MICRO' || _msmeCategory == 'SMALL')
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Written agreement allows up to 45 days'),
              subtitle: const Text(
                  'Without one the law allows 15 days (MSMED Act s.15); an '
                  'unpaid bill past it is disallowed this year (s.43B(h)).'),
              value: _msmeAgreement,
              onChanged: (value) =>
                  setState(() => _msmeAgreement = value ?? false),
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
          _fill(
            count == 0
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(emptyMessage, textAlign: TextAlign.center),
                    ),
                  )
                : ListView.builder(
                    shrinkWrap: _flat,
                    physics:
                        _flat ? const NeverScrollableScrollPhysics() : null,
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
                    isExpanded: true,
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

  /// A tab's list fills the dialog's fixed height; on the phase 2 page it is
  /// as tall as its rows.
  Widget _fill(Widget child) => _flat ? child : Expanded(child: child);

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
          _fill(
            _addresses.isEmpty
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
                    shrinkWrap: _flat,
                    physics:
                        _flat ? const NeverScrollableScrollPhysics() : null,
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
                                      isExpanded: true,
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
        // Blank on a new vendor: the server issues the next code.
        if (widget.vendor != null || _code.text.trim().isNotEmpty)
          'code': _code.text.trim().toUpperCase(),
        'name': _name.text.trim(),
        'legal_name': _legalName.text.trim(),
        'display_name': _displayName.text.trim().isEmpty
            ? _name.text.trim()
            : _displayName.text.trim(),
        'status': _status,
        'blocked_reason': _status == 'BLOCKED' &&
                _blockedReason.text.trim().isNotEmpty
            ? _blockedReason.text.trim()
            : null,
        // Absent while the lists are still loading or failed to load: see
        // `_loadClassifications`. An explicit null clears the column, which is
        // right when somebody chooses "Not set" and wrong when the dialog
        // simply never knew.
        if (_classificationsLoaded) 'category_id': _categoryId,
        if (_classificationsLoaded) 'type_id': _typeId,
        'gst_registration': _gstRegistration,
        // Sent whole like the other optional fields: null is "Not set".
        'gst_registration_type': _gstType,
        'gstin': _gstin.text.trim().toUpperCase(),
        'pan': _pan.text.trim().toUpperCase(),
        'payment_terms_days': int.tryParse(_creditDays.text.trim()) ?? 0,
        'standing_discount_percent':
            double.tryParse(_standingDiscount.text.trim()) ?? 0,
        'udyam_number': _udyam.text.trim().isEmpty
            ? null
            : _udyam.text.trim().toUpperCase(),
        'msme_category': _msmeCategory.isEmpty ? null : _msmeCategory,
        'default_tds_section':
            _defaultTdsSection.isEmpty ? null : _defaultTdsSection,
        'msme_written_agreement': _msmeAgreement,
        'issues_e_invoices': _issuesEInvoices,
        'email': _email.text.trim(),
        'phone': _phone.text.trim(),
        'mobile': _mobile.text.trim(),
        'remarks': _remarks.text.trim(),
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
        // Only once the definitions arrived: absent means "leave them alone".
        if (_customFields.canSend) 'attributes': _customFields.payload(),
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

/// One bill a supplier was owed at cutover, typed in.
///
/// Returns a payload holding only the keys the write schema declares --
/// `reference_number`, `bill_date`, `due_date`, `posting_date`, `amount`,
/// `narration` -- and only the optional ones that were actually filled in,
/// because the server forbids extra fields and treats an absent key as
/// "leave it to the default" rather than null.
class _AddOpeningBillDialog extends StatefulWidget {
  const _AddOpeningBillDialog();

  @override
  State<_AddOpeningBillDialog> createState() => _AddOpeningBillDialogState();
}

class _AddOpeningBillDialogState extends State<_AddOpeningBillDialog> {
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
      setState(() => _error = 'Enter how much was owed on this bill.');
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
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.error),
                  ),
                  const SizedBox(height: 8),
                ],
                TextField(
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: 'Supplier reference',
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
                ),
                const SizedBox(height: 12),
                _dateBox(
                  label: 'Posting date',
                  value: _postingDate,
                  onTap: () => _pickDate(
                    initial: _postingDate ?? DateTime.now(),
                    onPicked: (picked) =>
                        setState(() => _postingDate = picked),
                  ),
                  onClear: () => setState(() => _postingDate = null),
                  helperText:
                      'blank = today; the day your books here start',
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _amount,
                  decoration: const InputDecoration(labelText: 'Amount'),
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
