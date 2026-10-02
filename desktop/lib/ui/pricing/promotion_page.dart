import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/entities.dart';
import '../../models/pricing.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../workspace/desktop_framework.dart';
import 'coupon_batch_dialog.dart';
import 'coupon_dialog.dart';
import 'promotion_copy_dialog.dart';
import 'promotion_dialog.dart';
import 'promotion_try_dialog.dart';

/// The offers a firm is running, in the order they apply.
///
/// A price list is a standing arrangement; a promotion is an offer, and unlike
/// a price list **several apply at once**. They run in priority order, lowest
/// number first, and each says whether it lets the ones behind it apply too.
///
/// Two things this screen has to say plainly, because both surprise people.
/// Percentages **compound on what is left**, so two ten percent offers take
/// nineteen percent rather than twenty. And a discount somebody types on a
/// line beats every promotion on it — a person deciding beats a rule.
class PromotionPage extends StatefulWidget {
  const PromotionPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
    this.saveBytesOverride,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  /// Tests inject one, because a widget test cannot open a save panel.
  final SaveBytesOverride? saveBytesOverride;

  @override
  State<PromotionPage> createState() => _PromotionPageState();
}

class _PromotionPageState extends State<PromotionPage> {
  final TextEditingController _search = TextEditingController();

  /// Which half of the screen is showing. Offers and the codes that reach
  /// them are two lists about one thing, so they share a screen rather than
  /// competing for a place in the sales module's tab bar.
  bool _showingCoupons = false;

  List<PromotionRecord> _rows = const [];
  List<PromotionCouponRecord> _coupons = const [];
  PromotionRecord? _selected;
  PromotionCouponRecord? _selectedCoupon;
  int _total = 0;
  int _page = 1;
  bool _loading = true;
  String? _error;

  bool get _mayManage => widget.permissions.hasPermission('PROMOTION_MANAGE');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({int? requestedPage}) async {
    final int page = requestedPage ?? _page;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_showingCoupons) {
        final PagedResult<PromotionCouponRecord> coupons =
            await widget.api.promotionCoupons(page: page, search: _search.text);
        if (!mounted) return;
        setState(() {
          _coupons = coupons.items;
          _total = coupons.total;
          _page = page;
          _loading = false;
          _selectedCoupon = _coupons
              .where((row) => row.id == _selectedCoupon?.id)
              .firstOrNull;
        });
        return;
      }
      final PagedResult<PromotionRecord> result = await widget.api.promotions(
        page: page,
        search: _search.text,
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        _page = page;
        _loading = false;
        _selected = _rows.where((row) => row.id == _selected?.id).firstOrNull;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Mint a coupon, or change the limits on one.
  ///
  /// The offers are read first: a coupon points at one, and a picker with
  /// nothing in it would let somebody fill the form in and then be refused.
  Future<void> _editCoupon({PromotionCouponRecord? existing}) async {
    late final List<PromotionRecord> offers;
    try {
      offers = await fetchAllPages<PromotionRecord>(
        (page) => widget.api.promotions(page: page),
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
      return;
    }
    if (!mounted) return;
    if (offers.isEmpty) {
      NotificationService.show(
        context,
        'Create an offer first. A coupon is a way of reaching one, not an '
        'offer in itself.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => CouponDialog(
        api: widget.api,
        promotions: offers,
        existing: existing,
      ),
    );
    if (saved ?? false) unawaited(_load());
  }

  Future<List<PromotionRecord>?> _readOffers() async {
    try {
      return await fetchAllPages<PromotionRecord>(
        (page) => widget.api.promotions(page: page),
      );
    } on ApiException catch (error) {
      if (!mounted) return null;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
      return null;
    }
  }

  /// Mint a batch of single-use codes for an offer (SEL-5).
  Future<void> _generateCodes() async {
    final List<PromotionRecord>? offers = await _readOffers();
    if (offers == null || !mounted) return;
    if (offers.isEmpty) {
      NotificationService.show(
        context,
        'Create an offer first. A coupon is a way of reaching one, not an '
        'offer in itself.',
        kind: AppNotificationKind.information,
      );
      return;
    }
    final bool? generated = await showDialog<bool>(
      context: context,
      builder: (_) => CouponBatchDialog(
        api: widget.api,
        promotions: offers,
        initialPromotionId: _selectedCoupon?.promotionId ?? _selected?.id,
        saveBytesOverride: widget.saveBytesOverride,
      ),
    );
    if (generated ?? false) {
      setState(() {
        _showingCoupons = true;
        _page = 1;
      });
      unawaited(_load(requestedPage: 1));
    }
  }

  /// Copy the picked offer as a draft with new dates (SEL-8).
  Future<void> _copyOffer(PromotionRecord offer) async {
    final List<PromotionRecord>? copies =
        await showDialog<List<PromotionRecord>>(
      context: context,
      builder: (_) => PromotionCopyDialog(
        api: widget.api,
        promotions: [offer],
      ),
    );
    if (copies == null || !mounted) return;
    NotificationService.show(
      context,
      '${copies.length} offer(s) copied as drafts.',
      kind: AppNotificationKind.success,
    );
    unawaited(_load(requestedPage: 1));
  }

  /// Save an offer's codes as a CSV: the selected coupon's or offer's, or one
  /// the user picks.
  Future<void> _exportCodes() async {
    final List<PromotionRecord>? offers = await _readOffers();
    if (offers == null || !mounted) return;
    final String? wanted = _selectedCoupon?.promotionId ?? _selected?.id;
    PromotionRecord? offer =
        offers.where((row) => row.id == wanted).firstOrNull;
    offer ??= await showDialog<PromotionRecord>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: const Text('Export the codes of which offer?'),
        children: [
          for (final PromotionRecord row in offers)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(dialogContext, row),
              child: Text('${row.code} — ${row.name}'),
            ),
        ],
      ),
    );
    if (offer == null || !mounted) return;
    await saveCouponCodesCsv(
      context,
      widget.api,
      offer,
      saveBytesOverride: widget.saveBytesOverride,
    );
  }

  /// Retire a coupon without forgetting what it already gave away.
  Future<void> _deleteCoupon(PromotionCouponRecord row) async {
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Retire ${row.code}?',
      message: 'It stops being claimable. What it has already given away is '
          'kept, so the claims against it still reconcile.',
      confirmLabel: 'Retire',
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deletePromotionCoupon(row.id);
      if (!mounted) return;
      NotificationService.show(context, '${row.code} retired.',
          kind: AppNotificationKind.success);
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(context, error.message,
          kind: AppNotificationKind.error);
    }
  }

  Future<void> _edit({PromotionRecord? existing}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => PromotionDialog(api: widget.api, existing: existing),
    );
    if (!(saved ?? false)) return;
    if (!mounted) return;
    // An active offer is superseded rather than changed, and nothing on
    // screen said so: the only sign was a second row after Refresh.
    NotificationService.show(
      context,
      existing == null
          ? 'Promotion created.'
          : existing.status == 'DRAFT'
              ? 'Promotion ${existing.code} saved.'
              : 'Promotion ${existing.code} saved as a new revision; the one '
                  'you opened is now inactive.',
      kind: AppNotificationKind.success,
    );
    unawaited(_load());
  }

  Future<void> _delete(PromotionRecord row) async {
    final bool confirmed = await showWorkspaceConfirmDialog(
      context,
      title: 'Retire ${row.code}?',
      message: 'It stops applying to new documents. Documents already priced '
          'under it are unchanged.',
      confirmLabel: 'Retire',
      type: ConfirmationType.delete,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.api.deletePromotion(row.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Promotion ${row.code} retired.',
        kind: AppNotificationKind.success,
      );
      unawaited(_load());
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.hasActiveFirm) {
      return const StandardEmptyState(type: EmptyStateType.noFirmSelected);
    }
    final bool phase2 = Phase2Scope.of(context);
    return ManagementWorkspaceLayout(
      toolbar: phase2
          ? _phase2Toolbar()
          : Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Offers')),
              ButtonSegment(value: true, label: Text('Coupons')),
            ],
            selected: {_showingCoupons},
            onSelectionChanged: (choice) {
              setState(() {
                _showingCoupons = choice.first;
                _page = 1;
              });
              unawaited(_load(requestedPage: 1));
            },
          ),
          if (_mayManage && !_showingCoupons)
            FilledButton.icon(
              onPressed: () => unawaited(_edit()),
              icon: const Icon(Icons.add),
              label: const Text('New promotion'),
            ),
          // The coupon tab hid the promotion button and never gained one of
          // its own, so coupons were list-only: none could be created from
          // the desktop at all, and the code is how a customer reaches an
          // offer that requires one.
          if (_mayManage && _showingCoupons)
            FilledButton.icon(
              onPressed: () => unawaited(_editCoupon()),
              icon: const Icon(Icons.add),
              label: const Text('New coupon'),
            ),
          Phase2Refresh(
            onPressed: () => unawaited(_load()),
            child: OutlinedButton.icon(
              onPressed: () => unawaited(_load()),
              icon: const Icon(Icons.refresh),
              label: const Text('Refresh'),
            ),
          ),
        ],
      ),
      searchPanel: SearchFilterPanel(
        controller: _search,
        hintText: 'Search by name...',
        onSearch: (_) => unawaited(_load(requestedPage: 1)),
      ),
      // Phase 2 (option C, owner 2026-09-27): the picked offer or coupon
      // named on a bar above the grid with its actions; an offer's detail
      // opens in a window rather than a side pane.
      selectionBar: true,
      selection: _selectionSummary(),
      primaryContent: _showingCoupons ? _couponContent() : _content(),
      detailsPanel: phase2 || _showingCoupons
          ? null
          : (_selected == null ? null : _details(_selected!)),
      statusBar: WorkspaceStatusBar(
        total: _total,
        selected: _showingCoupons ? _selectedCoupon != null : _selected != null,
        message: _loading ? 'Loading...' : null,
      ),
    );
  }

  /// Offers or coupons, on the line beside the search.
  Widget _switch() => SegmentedButton<bool>(
        segments: const [
          ButtonSegment(value: false, label: Text('Offers')),
          ButtonSegment(value: true, label: Text('Coupons')),
        ],
        selected: {_showingCoupons},
        onSelectionChanged: (choice) {
          setState(() {
            _showingCoupons = choice.first;
            _page = 1;
          });
          unawaited(_load(requestedPage: 1));
        },
      );

  WorkspaceToolbar _phase2Toolbar() {
    final PromotionRecord? offer = _showingCoupons ? null : _selected;
    final PromotionCouponRecord? coupon =
        _showingCoupons ? _selectedCoupon : null;
    final bool picked = offer != null || coupon != null;
    return WorkspaceToolbar(
      trailing: [_switch()],
      commands: [
        // Not about the picked row: it tries the whole set of live offers on
        // a made-up document.
        ToolbarCommand(
          id: 'try-offers',
          label: 'Try offers',
          icon: Icons.science_outlined,
          tooltip: 'See what a document would earn, and why',
          // About the whole set of offers, not the picked one: with a
          // selection bar the list line keeps only what is menu-only.
          menuOnly: true,
          onPressed: () => unawaited(showDialog<void>(
            context: context,
            builder: (_) => PromotionTryDialog(api: widget.api),
          )),
        ),
        // Bulk single-use codes (SEL-5): about an offer, not the picked row.
        if (_mayManage)
          ToolbarCommand(
            id: 'generate-codes',
            label: 'Generate codes',
            icon: Icons.confirmation_number_outlined,
            tooltip: 'Mint many single-use codes for an offer',
            menuOnly: true,
            onPressed: () => unawaited(_generateCodes()),
          ),
        // Last season's offer again with new dates (SEL-8): about the picked
        // offer, so it waits for one.
        if (_mayManage && !_showingCoupons)
          ToolbarCommand(
            id: 'copy-offers',
            label: 'Copy with new dates...',
            icon: Icons.copy_all_outlined,
            tooltip: 'Copy the picked offer as a draft with a new window',
            menuOnly: true,
            onPressed:
                offer == null ? null : () => unawaited(_copyOffer(offer)),
          ),
        ToolbarCommand(
          id: 'export-codes',
          label: 'Export codes',
          icon: Icons.download_outlined,
          tooltip: 'Save the codes of an offer as a CSV file',
          menuOnly: true,
          onPressed: () => unawaited(_exportCodes()),
        ),
      ],
      actions: [
        if (!_showingCoupons) ToolbarAction.view,
        if (_mayManage) ToolbarAction.edit,
        if (_mayManage) ToolbarAction.delete,
        ToolbarAction.refresh,
        if (_mayManage) ToolbarAction.newItem,
      ],
      isEnabled: (action) => switch (action) {
        ToolbarAction.view => offer != null,
        ToolbarAction.edit || ToolbarAction.delete => picked,
        _ => !_loading,
      },
      onAction: (action) {
        switch (action) {
          case ToolbarAction.view:
            if (offer != null) unawaited(_read(offer));
          case ToolbarAction.edit:
            if (offer != null) unawaited(_edit(existing: offer));
            if (coupon != null) unawaited(_editCoupon(existing: coupon));
          case ToolbarAction.delete:
            if (offer != null) unawaited(_delete(offer));
            if (coupon != null) unawaited(_deleteCoupon(coupon));
          case ToolbarAction.newItem:
            unawaited(_showingCoupons ? _editCoupon() : _edit());
          default:
            unawaited(_load());
        }
      },
    );
  }

  SelectionSummary? _selectionSummary() {
    if (_showingCoupons) {
      final PromotionCouponRecord? coupon = _selectedCoupon;
      return coupon == null
          ? null
          : SelectionSummary.record(
              name: coupon.code,
              facts: [coupon.promotionCode, coupon.usageLabel],
              status: coupon.status,
              onClear: () => setState(() => _selectedCoupon = null),
            );
    }
    final PromotionRecord? offer = _selected;
    return offer == null
        ? null
        : SelectionSummary.record(
            name: offer.name,
            facts: [offer.code, _benefitLabel(offer)],
            status: offer.status,
            onClear: () => setState(() => _selected = null),
          );
  }

  /// Read one offer: what the side pane held, in a window.
  Future<void> _read(PromotionRecord row) async {
    setState(() => _selected = row);
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        content: SizedBox(width: 520, child: _details(row)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(
        title: 'Promotions unavailable',
        message: _error!,
      );
    }
    if (_rows.isEmpty) {
      return WorkspaceEmptyState(
        title: _search.text.trim().isEmpty
            ? 'No promotions yet'
            : 'Nothing matches that search',
        message: 'A promotion is an offer that applies while a document is '
            'priced — a rate off a line, off the whole bill, or goods given '
            'away. Several can apply to one order.',
      );
    }
    return EnterpriseDataGrid<PromotionRecord>(
      items: _rows,
      total: _total,
      pageOffset: (_page - 1) * 20,
      rowsPerPage: 20,
      selectedId: _selected?.id,
      columns: const [
        GridColumn(key: 'priority', label: 'Order'),
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'name', label: 'Name'),
        GridColumn(key: 'gives', label: 'Gives'),
        GridColumn(key: 'stacks', label: 'Stacks'),
        GridColumn(key: 'window', label: 'In force'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        '${row.priority}',
        row.code,
        row.name,
        _benefitLabel(row),
        row.allowStacking ? 'Yes' : 'Ends here',
        _windowLabel(row),
        row.status,
      ],
      onSelect: (row) => setState(() => _selected = row),
      onPageChanged: (page) => unawaited(_load(requestedPage: page)),
      // Double-click edits, as the coupon grid beside it already did; phase 2
      // reads it, as every list, with Edit on the bar.
      onOpen: Phase2Scope.of(context)
          ? (row) => unawaited(_read(row))
          : _mayManage
              ? (row) => unawaited(_edit(existing: row))
              : null,
      contextActions: const [
        WorkspaceContextAction.edit,
        WorkspaceContextAction.delete,
      ],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) {
          unawaited(_edit(existing: row));
        }
        if (action == WorkspaceContextAction.delete) unawaited(_delete(row));
      },
    );
  }

  Widget _couponContent() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return WorkspaceEmptyState(title: 'Coupons unavailable', message: _error!);
    }
    if (_coupons.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'No coupons yet',
        message: 'A coupon is a code a customer presents to claim an offer. '
            'The benefit lives on the offer; the coupon decides who reaches '
            'it, and how often. Use “New coupon” above.',
      );
    }
    return EnterpriseDataGrid<PromotionCouponRecord>(
      items: _coupons,
      total: _total,
      pageOffset: (_page - 1) * 20,
      rowsPerPage: 20,
      selectedId: _selectedCoupon?.id,
      columns: const [
        GridColumn(key: 'code', label: 'Code'),
        GridColumn(key: 'promotion', label: 'Offer'),
        GridColumn(key: 'used', label: 'Claimed'),
        GridColumn(key: 'per', label: 'Per customer'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.code,
        row.promotionCode,
        row.usageLabel,
        row.maxRedemptionsPerCustomer == null
            ? 'No limit'
            : '${row.maxRedemptionsPerCustomer}',
        row.status,
      ],
      onSelect: (row) => setState(() => _selectedCoupon = row),
      onOpen: _mayManage
          ? (row) => unawaited(_editCoupon(existing: row))
          : null,
      contextActions: _mayManage
          ? const [WorkspaceContextAction.edit, WorkspaceContextAction.delete]
          : const [],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) {
          unawaited(_editCoupon(existing: row));
        }
        if (action == WorkspaceContextAction.delete) {
          unawaited(_deleteCoupon(row));
        }
      },
      onPageChanged: (page) => unawaited(_load(requestedPage: page)),
    );
  }

  static String _benefitLabel(PromotionRecord row) {
    if (row.actions.isEmpty) return '—';
    return row.actions.map(_actionLabel).join(', ');
  }

  static String _actionLabel(PromotionActionRecord action) =>
      switch (action.actionType) {
        'LINE_DISCOUNT_PERCENT' => '${action.percent}% off the line',
        'LINE_DISCOUNT_AMOUNT' => '${action.amount} off the line',
        'BILL_DISCOUNT_PERCENT' => '${action.percent}% off the bill',
        'BILL_DISCOUNT_AMOUNT' => '${action.amount} off the bill',
        'FREE_QUANTITY' =>
          'buy ${action.buyQuantity}, get ${action.freeQuantity} free',
        'FREE_PRODUCT' => action.buyQuantity.isEmpty
            ? '${action.freeQuantity} of another product free'
            : 'buy ${action.buyQuantity}, get ${action.freeQuantity} of '
                'another product free',
        'FREE_SHIPPING' => 'free delivery',
        _ => action.actionType,
      };

  static String _windowLabel(PromotionRecord row) {
    if (row.effectiveFrom.isEmpty && row.effectiveTo.isEmpty) return 'Always';
    if (row.effectiveTo.isEmpty) return 'From ${row.effectiveFrom}';
    if (row.effectiveFrom.isEmpty) return 'Until ${row.effectiveTo}';
    return '${row.effectiveFrom} to ${row.effectiveTo}';
  }

  Widget _details(PromotionRecord row) {
    final ThemeData theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(row.name, style: theme.textTheme.titleMedium),
          Text(
            '${row.code} · revision ${row.versionNumber} · applies '
            '${row.priority == 1 ? 'first' : 'at ${row.priority}'}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text('In force ${_windowLabel(row)}',
              style: theme.textTheme.bodySmall),
          if (row.description.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(row.description, style: theme.textTheme.bodyMedium),
          ],
          const SizedBox(height: AppSpacing.md),
          Text('Gives', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          for (final PromotionActionRecord action in row.actions)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(_actionLabel(action)),
            ),
          const SizedBox(height: AppSpacing.md),
          Text('Applies when', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          if (row.conditions.isEmpty)
            Text(
              'Always — no conditions, so every line qualifies.',
              style: theme.textTheme.bodySmall,
            ),
          for (final PromotionConditionRecord condition in row.conditions)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Text(
                describePromotionCondition(condition),
                style: theme.textTheme.bodySmall,
              ),
            ),
          const SizedBox(height: AppSpacing.md),
          Text(
            row.allowStacking
                ? 'Other promotions may still apply after this one. '
                    'Percentages compound on what is left, so two ten percent '
                    'offers take nineteen percent, not twenty.'
                : 'This promotion ends the stack: nothing after it applies.',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
