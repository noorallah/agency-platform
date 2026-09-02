import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/commission.dart';
import '../../models/firm_member.dart';
import '../../models/entities.dart';
import '../../models/finance.dart';
import '../../models/product.dart';
import '../workspace/desktop_framework.dart';
import 'payout_dialogs.dart';

/// What each salesman earns, and what a period of collections earned them.
///
/// Two things about this module surprise everybody who reads it for the first
/// time, so both are said on screen rather than left in the documentation:
///
/// * a rule with **no salesman** is the firm-wide default — the rate anybody
///   with no rule of their own earns; and
/// * commission is earned on money **actually collected** in the period, not
///   on what was invoiced. An invoice raised in March and paid in May earns
///   its commission in May, and a payment later taken back stops earning it.
///
/// Reading needs `COMMISSION_VIEW`, which is all the report needs. Recording
/// or changing a rate needs `COMMISSION_MANAGE`; without it the screen is
/// read-only and carries no add control at all.
class CommissionPage extends StatefulWidget {
  const CommissionPage({
    super.key,
    required this.api,
    required this.permissions,
    required this.hasActiveFirm,
  });

  final ApiClient api;
  final PermissionService permissions;
  final bool hasActiveFirm;

  @override
  State<CommissionPage> createState() => _CommissionPageState();
}

/// Which part of the screen is showing.
enum _CommissionView { rules, report, payouts }

class _CommissionPageState extends State<CommissionPage> {
  late final TextEditingController _from =
      TextEditingController(text: isoDate(_firstOfThisMonth()));
  late final TextEditingController _to =
      TextEditingController(text: isoDate(DateTime.now()));

  _CommissionView _view = _CommissionView.rules;

  List<CommissionRuleRecord> _rules = const [];
  CommissionReport? _report;
  String? _selectedId;
  String? _rulesError;
  String? _reportError;
  bool _loadingRules = true;
  bool _loadingReport = false;

  /// The firm's people, so a rate can be agreed with somebody who has never
  /// had one. Without this list the picker could only offer names lifted off
  /// existing rules, which makes every rate but the first impossible to add.
  List<FirmMember> _people = const <FirmMember>[];

  /// What a rule can be scoped to. Loaded with the rules so the editor has
  /// them the moment it opens -- a picker that fetches on open shows an empty
  /// list for as long as the request takes, and somebody saves through it.
  List<Product> _goods = const <Product>[];
  List<ProductCategoryRecord> _goodsCategories = const <ProductCategoryRecord>[];

  List<CommissionPayoutRecord> _payouts = const [];
  List<LedgerAccount> _moneyAccounts = const [];
  String? _payoutsError;
  bool _loadingPayouts = false;

  bool get _mayView => widget.permissions.hasPermission('COMMISSION_VIEW');
  bool get _mayManage => widget.permissions.hasPermission('COMMISSION_MANAGE');

  /// Money leaving the firm is a separate authority from agreeing what is
  /// owed, so the Pay action is gated on its own code. The screen hides the
  /// button rather than letting the server refuse after the dialog.
  bool get _mayPay => widget.permissions.hasPermission('COMMISSION_PAY');

  static DateTime _firstOfThisMonth() {
    final DateTime now = DateTime.now();
    return DateTime(now.year, now.month);
  }

  @override
  void initState() {
    super.initState();
    if (widget.hasActiveFirm && _mayView) _loadRules();
  }

  @override
  void dispose() {
    _from.dispose();
    _to.dispose();
    super.dispose();
  }

  Future<void> _loadRules() async {
    setState(() {
      _loadingRules = true;
      _rulesError = null;
    });
    try {
      // Paged through rather than asked for in one oversized page: anything
      // above `MAX_PAGE_SIZE` is refused rather than clamped.
      final List<CommissionRuleRecord> rows =
          await fetchAllPages<CommissionRuleRecord>(
        (page) => widget.api.commissionRules(page: page),
      );
      final List<FirmMember> people = await widget.api.firmMembers();
      final List<Product> goods = await fetchAllPages<Product>(
        (page) => widget.api.products(page: page, pageSize: 100),
      );
      final List<ProductCategoryRecord> categories =
          await widget.api.productCategories();
      if (!mounted) return;
      setState(() {
        _rules = rows;
        _people = people;
        _goods = goods;
        _goodsCategories = categories;
        _loadingRules = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _rulesError = error.message;
        _loadingRules = false;
      });
    }
  }

  Future<void> _loadReport() async {
    final DateTime? from = parseIsoDate(_from.text);
    final DateTime? to = parseIsoDate(_to.text);
    if (from == null || to == null) {
      setState(() => _reportError =
          'Both dates must be written as YYYY-MM-DD, for example '
          '${isoDate(_firstOfThisMonth())}.');
      return;
    }
    if (to.isBefore(from)) {
      setState(() => _reportError = 'The period cannot end before it starts.');
      return;
    }
    setState(() {
      _loadingReport = true;
      _reportError = null;
      // Cleared before the read: a failed load must not leave one period's
      // figures on screen under a different period's dates.
      _report = null;
    });
    try {
      final CommissionReport report = await widget.api.commissionReport(
        fromDate: isoDate(from),
        toDate: isoDate(to),
      );
      if (!mounted) return;
      setState(() {
        _report = report;
        _loadingReport = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _reportError = error.message;
        _loadingReport = false;
      });
    }
  }


  Future<void> _loadPayouts() async {
    setState(() {
      _loadingPayouts = true;
      _payoutsError = null;
    });
    try {
      final List<CommissionPayoutRecord> rows =
          await fetchAllPages<CommissionPayoutRecord>(
        (page) => widget.api.commissionPayouts(page: page),
      );
      // Only the accounts money can actually leave from. Offering the whole
      // chart would invite a payment posted against revenue.
      final List<LedgerAccount> accounts = _mayPay
          ? (await widget.api.ledgerAccounts(isActive: true))
              .items
              .where((account) => account.accountType == 'ASSET')
              .toList()
          : const <LedgerAccount>[];
      if (!mounted) return;
      setState(() {
        _payouts = rows;
        _moneyAccounts = accounts;
        _loadingPayouts = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _payoutsError = error.message;
        _loadingPayouts = false;
      });
    }
  }

  Future<void> _accrue() async {
    final bool? ran = await showDialog<bool>(
      context: context,
      builder: (context) => CommissionAccrualDialog(api: widget.api),
    );
    if (ran == true) await _loadPayouts();
  }

  /// Run one payout action and say what happened either way.
  Future<void> _payoutAction(
    CommissionPayoutRecord payout,
    Future<CommissionPayoutRecord> Function() action,
    String done,
  ) async {
    try {
      await action();
      if (!mounted) return;
      NotificationService.show(
        context,
        '${payout.salesmanName} — $done',
        kind: AppNotificationKind.success,
      );
      await _loadPayouts();
    } on ApiException catch (error) {
      if (!mounted) return;
      NotificationService.show(
        context,
        error.message,
        kind: AppNotificationKind.error,
      );
    }
  }

  Future<void> _pay(CommissionPayoutRecord payout) async {
    final Json? details = await showDialog<Json>(
      context: context,
      builder: (context) => CommissionPaymentDialog(
        payout: payout,
        accounts: _moneyAccounts,
      ),
    );
    if (details == null) return;
    await _payoutAction(
      payout,
      () => widget.api.payCommissionPayout(
        payout.id,
        details,
        expectedVersion: payout.version,
      ),
      'paid.',
    );
  }

  Future<void> _edit({CommissionRuleRecord? rule}) async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (context) => CommissionRuleDialog(
        api: widget.api,
        rule: rule,
        // The firm's people, plus anybody a rule names who has since left.
        known: _knownSalesmen(),
        goods: _goods,
        goodsCategories: _goodsCategories,
      ),
    );
    if (saved == true) await _loadRules();
  }

  /// The people this screen can name.
  ///
  /// The firm's own members, read from `/commission/salesmen`, **plus**
  /// anybody a rule already names who is no longer among them -- somebody who
  /// has left still explains the payouts their rule made, and dropping them
  /// would make `DropdownButtonFormField` assert on a stored id that is not in
  /// its list and save the rule as firm-wide.
  List<FirmMember> _knownSalesmen() {
    final Map<String, FirmMember> byId = {
      for (final FirmMember person in _people) person.userId: person,
    };
    for (final CommissionRuleRecord rule in _rules) {
      if (rule.salesmanId.isEmpty || byId.containsKey(rule.salesmanId)) {
        continue;
      }
      byId[rule.salesmanId] = FirmMember(
        userId: rule.salesmanId,
        fullName: rule.salesmanName.isEmpty ? rule.salesmanId : rule.salesmanName,
      );
    }
    return byId.values.toList()..sort((a, b) => a.fullName.compareTo(b.fullName));
  }

  Future<void> _delete(CommissionRuleRecord rule) async {
    try {
      await widget.api.deleteCommissionRule(rule.id);
      if (!mounted) return;
      NotificationService.show(
        context,
        '${rule.whoLabel} — rule removed. It still explains the payouts it '
        'made while it was in force.',
        kind: AppNotificationKind.success,
      );
      await _loadRules();
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
      return const WorkspaceEmptyState(
        title: 'Choose a firm',
        message: 'Commission rates and collections are recorded per firm.',
      );
    }
    if (!_mayView) {
      return const WorkspaceEmptyState(
        icon: Icons.lock_outline,
        title: 'You cannot see commission',
        message: 'Reading commission rates and the collections report needs '
            'the view commission permission.',
      );
    }
    final bool onRules = _view == _CommissionView.rules;
    final bool onPayouts = _view == _CommissionView.payouts;
    return ManagementWorkspaceLayout(
      toolbar: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: [
          if (onRules && _mayManage)
            FilledButton.icon(
              onPressed: () => _edit(),
              icon: const Icon(Icons.add),
              label: const Text('Add rule'),
            ),
          if (onPayouts && _mayManage)
            FilledButton.icon(
              onPressed: _accrue,
              icon: const Icon(Icons.playlist_add_check),
              label: const Text('Accrue period'),
            ),
          OutlinedButton.icon(
            onPressed: onPayouts
                ? _loadPayouts
                : (onRules ? _loadRules : _loadReport),
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ],
      ),
      searchPanel: _view == _CommissionView.report
          ? _periodPanel()
          : const SizedBox.shrink(),
      viewBar: SegmentedButton<_CommissionView>(
        segments: const [
          ButtonSegment(
            value: _CommissionView.rules,
            label: Text('Rates'),
            icon: Icon(Icons.percent),
          ),
          ButtonSegment(
            value: _CommissionView.report,
            label: Text('Collected'),
            icon: Icon(Icons.payments_outlined),
          ),
          ButtonSegment(
            value: _CommissionView.payouts,
            label: Text('Payouts'),
            icon: Icon(Icons.account_balance_wallet_outlined),
          ),
        ],
        selected: {_view},
        showSelectedIcon: false,
        onSelectionChanged: (selection) {
          setState(() => _view = selection.first);
          if (_view == _CommissionView.report &&
              _report == null &&
              !_loadingReport) {
            _loadReport();
          }
          if (_view == _CommissionView.payouts &&
              _payouts.isEmpty &&
              !_loadingPayouts) {
            _loadPayouts();
          }
        },
      ),
      primaryContent: onPayouts
          ? _payoutsContent()
          : (onRules ? _rulesContent() : _reportContent()),
      statusBar: WorkspaceStatusBar(
        total: switch (_view) {
          _CommissionView.rules => _rules.length,
          _CommissionView.report => _report?.rows.length ?? 0,
          _CommissionView.payouts => _payouts.length,
        },
        selected: onRules && _selectedId != null,
        message: switch (_view) {
          _CommissionView.rules =>
            'A rate with no salesman applies to everybody without one of '
                'their own.',
          _CommissionView.report =>
            'What each rule paid, on the basis that rule declares.',
          _CommissionView.payouts =>
            'Approving posts the cost and the debt; paying clears it.',
        },
      ),
    );
  }


  // ------------------------------------------------------------------
  // Payouts
  // ------------------------------------------------------------------

  Widget _payoutsContent() {
    if (_loadingPayouts) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CommissionNotice(
          icon: Icons.receipt_long_outlined,
          text: 'A payout holds what the report said when it was accrued. '
              'Nothing re-reads it, so approving in April and asking again in '
              'September give the same number.',
        ),
        if (_payoutsError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _ErrorLine(message: _payoutsError!),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _payoutsGrid()),
      ],
    );
  }

  Widget _payoutsGrid() {
    if (_payouts.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No payouts yet',
        message: _mayManage
            ? 'Accrue a period to turn what it earned into draft payouts.'
            : 'Accruing a period needs the manage commission permission.',
      );
    }
    return EnterpriseDataGrid<CommissionPayoutRecord>(
      items: _payouts,
      total: _payouts.length,
      pageOffset: 0,
      rowsPerPage: _payouts.length,
      availableRowsPerPage: [_payouts.length],
      columns: const [
        GridColumn(key: 'salesman', label: 'Salesman'),
        GridColumn(key: 'period', label: 'Period'),
        GridColumn(key: 'earned', label: 'Earned'),
        GridColumn(key: 'payable', label: 'Payable'),
        GridColumn(key: 'status', label: 'Status'),
        GridColumn(key: 'actions', label: ''),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.salesmanName,
        row.periodLabel,
        row.earnedAmount,
        // The adjustment is folded in here rather than given a column of its
        // own, and the basis into the status. Every column costs about 220
        // pixels, and at 1366 an eighth one put the actions past the right
        // edge -- an Approve nobody can reach without scrolling sideways is
        // one nobody finds. Both notes appear only where there is something
        // to say.
        row.adjustmentAmount == '0.00'
            ? row.payableAmount
            : '${row.payableAmount}  (adj ${row.adjustmentAmount})',
        row.basis.isEmpty
            ? row.status
            : '${row.status} · ${basisLabel(row.basis).toLowerCase()}',
        '',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
      cellBuilder: (columnIndex, value, row) =>
          columnIndex == 5 ? _payoutActions(row) : Text(value),
    );
  }

  /// Only what this row can actually do next.
  ///
  /// An action the server is going to refuse is worse than none: it reads as
  /// a working action until the moment somebody needs it. Paying is gated on
  /// its own code, because whoever states a debt should not be the one who
  /// moves the cash.
  Widget _payoutActions(CommissionPayoutRecord row) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (row.isDraft && _mayManage)
          TextButton(
            onPressed: () => _payoutAction(
              row,
              () => widget.api.approveCommissionPayout(
                row.id,
                expectedVersion: row.version,
              ),
              'approved. The cost and the debt are on the ledger.',
            ),
            child: const Text('Approve'),
          ),
        if (row.isApproved && _mayPay)
          TextButton(
            onPressed: () => _pay(row),
            child: const Text('Pay'),
          ),
        if ((row.isDraft || row.isApproved) && _mayManage)
          TextButton(
            onPressed: () => _payoutAction(
              row,
              () => widget.api.cancelCommissionPayout(
                row.id,
                expectedVersion: row.version,
              ),
              'cancelled. The period is free to accrue again.',
            ),
            child: const Text('Cancel'),
          ),
      ],
    );
  }

  // ------------------------------------------------------------------
  // The rates
  // ------------------------------------------------------------------

  Widget _rulesContent() {
    if (_loadingRules) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CommissionNotice(
          icon: Icons.groups_outlined,
          text: 'A rule with no salesman is the firm-wide default: the rate '
              'anybody with no rule of their own earns.',
        ),
        if (_rulesError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _ErrorLine(message: _rulesError!),
        ],
        const SizedBox(height: AppSpacing.md),
        Expanded(child: _rulesGrid()),
      ],
    );
  }

  Widget _rulesGrid() {
    if (_rules.isEmpty) {
      return WorkspaceEmptyState(
        title: 'No commission rates yet',
        message: _mayManage
            ? 'Add one for the whole firm, or one for a particular salesman.'
            : 'Recording a rate needs the manage commission permission.',
      );
    }
    return EnterpriseDataGrid<CommissionRuleRecord>(
      items: _rules,
      total: _rules.length,
      pageOffset: 0,
      rowsPerPage: _rules.length,
      availableRowsPerPage: [_rules.length],
      selectedId: _selectedId,
      columns: const [
        GridColumn(key: 'who', label: 'Applies to'),
        GridColumn(key: 'goods', label: 'On'),
        GridColumn(key: 'rate', label: 'Rate'),
        GridColumn(key: 'basis', label: 'Paid on'),
        GridColumn(key: 'window', label: 'In force'),
        GridColumn(key: 'status', label: 'Status'),
      ],
      id: (row) => row.id,
      cells: (row) => [
        row.whoLabel,
        row.scopeLabel,
        // Neither a ladder nor a per-unit rate has a single percentage, so
        // the column says what shape the arrangement is rather than printing
        // a field the rule does not use -- which would be the number somebody
        // read as the deal.
        row.slabs.isEmpty && row.rateType == 'PERCENT'
            ? '${trimDecimal(row.percentage)}%'
            : row.rateLabel,
        row.basis == 'INVOICED' ? 'Invoiced value' : 'Money collected',
        row.windowLabel,
        row.status,
      ],
      onSelect: (row) => setState(() => _selectedId = row.id),
      onPageChanged: (_) {},
      onOpen: _mayManage ? (row) => _edit(rule: row) : null,
      contextActions: _mayManage
          ? const [
              WorkspaceContextAction.edit,
              WorkspaceContextAction.delete,
            ]
          : const [],
      onContextAction: (action, row) {
        if (!_mayManage) return;
        if (action == WorkspaceContextAction.edit) _edit(rule: row);
        if (action == WorkspaceContextAction.delete) _delete(row);
      },
    );
  }

  // ------------------------------------------------------------------
  // The report
  // ------------------------------------------------------------------

  Widget _periodPanel() => Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.sm,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 190,
                child: CommissionDateField(
                  controller: _from,
                  label: 'Collected from',
                ),
              ),
              SizedBox(
                width: 190,
                child: CommissionDateField(
                  controller: _to,
                  label: 'Collected to',
                ),
              ),
              FilledButton.tonalIcon(
                onPressed: _loadingReport ? null : _loadReport,
                icon: const Icon(Icons.calculate_outlined, size: 18),
                label: const Text('Show'),
              ),
            ],
          ),
        ),
      );

  Widget _reportContent() {
    final CommissionReport? report = _report;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const CommissionNotice(
          icon: Icons.info_outline,
          text: 'Commission is earned on money actually collected in this '
              'period, not on what was invoiced. An invoice raised earlier '
              'and paid now earns it now, and a payment taken back stops '
              'earning it.',
        ),
        if (_reportError != null) ...[
          const SizedBox(height: AppSpacing.sm),
          _ErrorLine(message: _reportError!),
        ],
        const SizedBox(height: AppSpacing.md),
        if (_loadingReport)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (report == null)
          const Expanded(
            child: WorkspaceEmptyState(
              icon: Icons.date_range_outlined,
              title: 'Choose a period',
              message: 'Pick the dates money was collected between, then '
                  'press Show.',
            ),
          )
        else ...[
          _totals(report),
          const SizedBox(height: AppSpacing.md),
          Expanded(child: _reportGrid(report)),
          const SizedBox(height: AppSpacing.sm),
          const CommissionNotice(
            icon: Icons.help_outline,
            text: 'Unassigned is money collected against invoices that '
                'carried no salesman. It belongs to nobody, and it is counted '
                'in the totals so they reconcile against the cash book.',
          ),
        ],
      ],
    );
  }

  Widget _totals(CommissionReport report) => Wrap(
        spacing: AppSpacing.md,
        runSpacing: AppSpacing.sm,
        children: [
          _TotalCard(
            label: 'Collected ${report.fromDate} to ${report.toDate}',
            value: report.totalCollectedAmount,
          ),
          _TotalCard(
            label: 'Invoiced in the same period',
            value: report.totalInvoicedAmount,
          ),
          _TotalCard(
            label: 'Commission earned',
            value: report.totalCommissionAmount,
          ),
        ],
      );

  Widget _reportGrid(CommissionReport report) {
    if (report.rows.isEmpty) {
      return const WorkspaceEmptyState(
        title: 'Nothing was collected in this period',
        message: 'No settlement was allocated to an invoice between these '
            'dates, so no commission was earned.',
      );
    }
    return EnterpriseDataGrid<CommissionRow>(
      items: report.rows,
      total: report.rows.length,
      pageOffset: 0,
      rowsPerPage: report.rows.length,
      availableRowsPerPage: [report.rows.length],
      columns: const [
        GridColumn(key: 'salesman', label: 'Salesman'),
        GridColumn(key: 'collected', label: 'Collected'),
        GridColumn(key: 'invoiced', label: 'Invoiced'),
        GridColumn(key: 'basis', label: 'Paid on'),
        GridColumn(key: 'commission', label: 'Commission'),
        GridColumn(key: 'invoices', label: 'Invoices'),
      ],
      id: (row) => row.salesmanId.isEmpty ? 'unassigned' : row.salesmanId,
      cells: (row) => [
        row.salesmanId.isEmpty
            ? 'Unassigned (no salesman on the invoice)'
            : row.salesmanName,
        row.collectedAmount,
        row.invoicedAmount,
        // Both figures are shown whatever the arrangement, so this column is
        // what says which of the two the payout beside it was worked out on.
        basisLabel(row.basis),
        row.commissionAmount,
        '${row.invoiceCount}',
      ],
      onSelect: (_) {},
      onPageChanged: (_) {},
    );
  }
}

/// Record or change one commission rate.
///
/// Both of the server's own rules are restated here so a mistake is caught
/// while the numbers are still on screen: a rate outside 0–100, and a window
/// that closes before it opens. When the server refuses for any other reason
/// its sentence is shown as it stands — it knows things this form does not,
/// such as a rate already covering the same days for the same person.
class CommissionRuleDialog extends StatefulWidget {
  const CommissionRuleDialog({
    super.key,
    required this.api,
    required this.known,
    this.goods = const <Product>[],
    this.goodsCategories = const <ProductCategoryRecord>[],
    this.rule,
  });

  final ApiClient api;

  /// The people who can be named, besides the firm as a whole.
  final List<FirmMember> known;

  /// What a rule can be scoped to. A rule naming neither is about the whole
  /// document, which is what every rule was before scoping existed.
  final List<Product> goods;
  final List<ProductCategoryRecord> goodsCategories;

  /// The rule being changed, or null to record a new one.
  final CommissionRuleRecord? rule;

  @override
  State<CommissionRuleDialog> createState() => _CommissionRuleDialogState();
}

class _CommissionRuleDialogState extends State<CommissionRuleDialog> {
  late final TextEditingController _percentage =
      TextEditingController(text: trimDecimal(widget.rule?.percentage ?? ''));
  late final TextEditingController _from = TextEditingController(
      text: widget.rule?.effectiveFrom ?? isoDate(DateTime.now()));
  late final TextEditingController _to =
      TextEditingController(text: widget.rule?.effectiveTo ?? '');

  late final TextEditingController _cap = TextEditingController(
      text: trimDecimal(widget.rule?.maxCommissionAmount ?? ''));

  /// The empty string is the firm-wide default, which belongs to nobody.
  late String _salesmanId = widget.rule?.salesmanId ?? '';
  late String _status = widget.rule?.status ?? 'ACTIVE';
  late final TextEditingController _perUnit = TextEditingController(
      text: trimDecimal(widget.rule?.perUnitAmount ?? ''));

  late String _basis = widget.rule?.basis ?? 'COLLECTED';
  late String _slabMode = widget.rule?.slabMode ?? 'MARGINAL';
  late String _rateType = widget.rule?.rateType ?? 'PERCENT';

  /// What the rule is about. Empty is everything; at most one is ever set,
  /// because the server refuses both -- a product is the narrower of the two.
  late String _productId = widget.rule?.productId ?? '';
  late String _categoryId = widget.rule?.productCategoryId ?? '';

  /// The ladder being edited, as typed text so a half-finished rung does not
  /// have to parse. Empty is a flat rate, which is what most rules are.
  late final List<_SlabDraft> _slabs = [
    for (final CommissionSlabRecord slab in widget.rule?.slabs ?? const [])
      _SlabDraft.from(slab),
  ];

  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _percentage.dispose();
    _from.dispose();
    _to.dispose();
    _cap.dispose();
    _perUnit.dispose();
    for (final _SlabDraft slab in _slabs) {
      slab.dispose();
    }
    super.dispose();
  }

  /// Say what is wrong, or nothing.
  String? _validate() {
    if (_rateType == 'PER_UNIT') {
      final double? perUnit = double.tryParse(_perUnit.text.trim());
      if (perUnit == null || perUnit <= 0) {
        return 'Enter what each unit earns, for example 2.50.';
      }
      // Both of the server's own rules about a per-unit rate, restated while
      // the numbers are still on screen.
      if (_basis != 'INVOICED') {
        return 'A per-unit rate can only be paid on invoiced value: money '
            'collected has no units in it.';
      }
      if (_productId.isEmpty && _categoryId.isEmpty) {
        return 'Say which product or category a per-unit rate is for.';
      }
      return _windowProblem();
    }
    final double? percentage = double.tryParse(_percentage.text.trim());
    if (percentage == null) {
      return 'Enter the rate as a number, for example 2.5.';
    }
    if (percentage < 0 || percentage > 100) {
      return 'A commission rate must be between 0 and 100 percent.';
    }
    final String? ladder = _validateLadder();
    if (ladder != null) {
      return ladder;
    }
    return _windowProblem();
  }

  /// Say what is wrong with the effective window, or nothing.
  String? _windowProblem() {
    final DateTime? from = parseIsoDate(_from.text);
    if (from == null) {
      return 'Enter the date the rate starts, written as YYYY-MM-DD.';
    }
    final String to = _to.text.trim();
    if (to.isNotEmpty) {
      final DateTime? until = parseIsoDate(to);
      if (until == null) {
        return 'Enter the date the rate ends as YYYY-MM-DD, or leave it empty '
            'to let it run on.';
      }
      if (until.isBefore(from)) {
        return 'The rate cannot end before it starts.';
      }
    }
    return null;
  }

  /// Restate the server's ladder rules while the numbers are still on screen.
  ///
  /// The server refuses the same three things and its sentence is what the
  /// user sees when anything else is wrong; these are here because a ladder is
  /// typed a rung at a time and a gap is easy to leave by accident.
  String? _validateLadder() {
    if (_slabs.isEmpty) return null;
    final List<double> floors = [];
    for (int index = 0; index < _slabs.length; index++) {
      final _SlabDraft slab = _slabs[index];
      final double? from = double.tryParse(slab.from.text.trim());
      final double? rate = double.tryParse(slab.percentage.text.trim());
      if (from == null) return 'Slab ${index + 1} needs an amount to start at.';
      if (rate == null || rate < 0 || rate > 100) {
        return 'Slab ${index + 1} needs a rate between 0 and 100 percent.';
      }
      floors.add(from);
      final String upper = slab.to.text.trim();
      final bool last = index == _slabs.length - 1;
      if (upper.isEmpty) {
        if (!last) return 'Only the highest slab may be left open-ended.';
        continue;
      }
      final double? to = double.tryParse(upper);
      if (to == null) return 'Slab ${index + 1} needs a number to end at.';
      if (to <= from) return 'Slab ${index + 1} must end above where it starts.';
      if (!last) {
        final double? next = double.tryParse(_slabs[index + 1].from.text.trim());
        if (next != null && next != to) {
          return 'Slabs must meet exactly: slab ${index + 1} ends at '
              '${trimDecimal(upper)} and the next starts at '
              '${trimDecimal(_slabs[index + 1].from.text.trim())}.';
        }
      }
    }
    if (floors.first != 0) {
      return 'The first slab must start at 0. Use a 0% slab if nothing is '
          'earned below a threshold.';
    }
    return null;
  }

  /// What to send.
  ///
  /// On a create the salesman is *omitted* when nobody is named, which is how
  /// the server reads the firm-wide default. On an update it is sent as an
  /// explicit null instead: the update model dumps with `exclude_unset`, so
  /// omitting it would mean leave it alone and a rule could never be moved
  /// back to the firm-wide scope.
  Json _payload({required bool creating}) => <String, dynamic>{
        if (_salesmanId.isNotEmpty)
          'salesman_id': _salesmanId
        else if (!creating)
          'salesman_id': null,
        'percentage': _percentage.text.trim(),
        'effective_from': _from.text.trim(),
        'effective_to': _to.text.trim().isEmpty ? null : _to.text.trim(),
        'status': _status,
        'basis': _basis,
        'slab_mode': _slabMode,
        'rate_type': _rateType,
        'per_unit_amount':
            _perUnit.text.trim().isEmpty ? '0' : _perUnit.text.trim(),
        // Always sent, including as null: this form shows the whole scope, so
        // clearing it here has to clear it on the record.
        'product_id': _productId.isEmpty ? null : _productId,
        'product_category_id': _categoryId.isEmpty ? null : _categoryId,
        'max_commission_amount':
            _cap.text.trim().isEmpty ? null : _cap.text.trim(),
        // Always sent, including as an empty list: this form shows the whole
        // ladder, so what is on screen is the arrangement. Omitting it would
        // mean *leave it alone* and a rung deleted here would stay in force.
        'slabs': [for (final _SlabDraft slab in _slabs) slab.toJson()],
      };

  Future<void> _save() async {
    final String? problem = _validate();
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final CommissionRuleRecord? rule = widget.rule;
      if (rule == null) {
        await widget.api.createCommissionRule(_payload(creating: true));
      } else {
        await widget.api.updateCommissionRule(
          rule.id,
          _payload(creating: false),
          expectedVersion: preconditionFor(rule.version),
        );
      }
      if (!mounted) return;
      NotificationService.show(
        context,
        rule == null ? 'Commission rate recorded.' : 'Commission rate saved.',
        kind: AppNotificationKind.success,
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        // The typing is still on screen, so the conflict message says so.
        _error = saveFailureMessage(
          error,
          'commission rate',
          changesKept: true,
        );
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    // A rule may name somebody the picker has never heard of — an old rule for
    // a former member. Keeping their id as an item of its own stops the
    // dropdown asserting on a value that is not in its list, which silently
    // saves the field as blank.
    final bool namedIsKnown = _salesmanId.isEmpty ||
        widget.known.any((person) => person.userId == _salesmanId);
    return AlertDialog(
      icon: const Icon(Icons.percent),
      title: Text(widget.rule == null
          ? 'Add a commission rate'
          : 'Edit ${widget.rule!.whoLabel}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                // Long names are common here, and the button row of a
                // dropdown never constrains its child: without this a name
                // overflows the dialog rather than eliding.
                isExpanded: true,
                initialValue: _salesmanId,
                decoration: const InputDecoration(
                  labelText: 'Applies to',
                  helperText: 'Leave as everyone for the firm-wide default.',
                ),
                items: [
                  const DropdownMenuItem<String>(
                    value: '',
                    child: Text(
                      'Everyone (default)',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  for (final FirmMember person in widget.known)
                    DropdownMenuItem<String>(
                      value: person.userId,
                      child:
                          Text(person.fullName, overflow: TextOverflow.ellipsis),
                    ),
                  if (!namedIsKnown)
                    DropdownMenuItem<String>(
                      value: _salesmanId,
                      child: Text(
                        widget.rule?.whoLabel ?? _salesmanId,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _salesmanId = value ?? ''),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _percentage,
                enabled: !_saving,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: InputDecoration(
                  labelText: _slabs.isEmpty ? 'Rate' : 'Rate (unused)',
                  helperText: _slabs.isEmpty
                      ? 'Percent of ${basisLabel(_basis).toLowerCase()}.'
                      : 'A ladder is below, and it is what this rule pays.',
                  suffixText: '%',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _basis,
                decoration: const InputDecoration(
                  labelText: 'Paid on',
                  helperText: 'What the rate is a percentage of.',
                ),
                items: const [
                  DropdownMenuItem(
                    value: 'COLLECTED',
                    child: Text('Money collected'),
                  ),
                  DropdownMenuItem(
                    value: 'INVOICED',
                    child: Text('Invoiced value'),
                  ),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _basis = value ?? _basis),
              ),
              const SizedBox(height: AppSpacing.md),
              _ScopePicker(
                productId: _productId,
                categoryId: _categoryId,
                goods: widget.goods,
                categories: widget.goodsCategories,
                enabled: !_saving,
                onChanged: (product, category) => setState(() {
                  _productId = product;
                  _categoryId = category;
                }),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _rateType,
                decoration: const InputDecoration(
                  labelText: 'Rate shape',
                  helperText: 'A share of the money, or a sum for each unit.',
                ),
                items: const [
                  DropdownMenuItem(
                    value: 'PERCENT',
                    child: Text('Percentage of the value'),
                  ),
                  DropdownMenuItem(
                    value: 'PER_UNIT',
                    child: Text('An amount for each unit sold'),
                  ),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _rateType = value ?? _rateType),
              ),
              if (_rateType == 'PER_UNIT') ...[
                const SizedBox(height: AppSpacing.md),
                TextField(
                  controller: _perUnit,
                  enabled: !_saving,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: [
                    FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                  ],
                  decoration: const InputDecoration(
                    labelText: 'Each unit earns',
                    helperText: 'Paid for every unit sold, whatever it sold '
                        'for. Only on invoiced value, and only for named '
                        'goods.',
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              if (_rateType == 'PERCENT') _LadderEditor(
                slabs: _slabs,
                mode: _slabMode,
                enabled: !_saving,
                onModeChanged: (value) => setState(() => _slabMode = value),
                onAdd: () => setState(() => _slabs.add(_SlabDraft.empty(
                      startingAt: _slabs.isEmpty
                          ? '0'
                          : _slabs.last.to.text.trim(),
                    ))),
                onRemove: (index) => setState(() {
                  _slabs.removeAt(index).dispose();
                }),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _cap,
                enabled: !_saving,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Most this pays per period',
                  helperText: 'Leave empty for no ceiling. It caps what was '
                      'earned, not what was sold.',
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: CommissionDateField(
                      controller: _from,
                      label: 'In force from',
                      enabled: !_saving,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.lg),
                  Expanded(
                    child: CommissionDateField(
                      controller: _to,
                      label: 'Until',
                      helper: 'Leave empty to run on.',
                      enabled: !_saving,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: _status,
                decoration: const InputDecoration(labelText: 'Status'),
                items: const [
                  DropdownMenuItem(value: 'ACTIVE', child: Text('Active')),
                  DropdownMenuItem(value: 'INACTIVE', child: Text('Inactive')),
                ],
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _status = value ?? _status),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.lg),
                Text(
                  _error!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}


/// What a commission rule is about: everything, one category, or one product.
///
/// One control rather than two pickers, because the server refuses a rule that
/// names both -- a product is the narrower of the two -- and two independent
/// dropdowns would let somebody build exactly the rule that gets refused.
class _ScopePicker extends StatelessWidget {
  const _ScopePicker({
    required this.productId,
    required this.categoryId,
    required this.goods,
    required this.categories,
    required this.enabled,
    required this.onChanged,
  });

  final String productId;
  final String categoryId;
  final List<Product> goods;
  final List<ProductCategoryRecord> categories;
  final bool enabled;
  final void Function(String productId, String categoryId) onChanged;

  static const String _everything = '';

  @override
  Widget build(BuildContext context) {
    final String selected = productId.isNotEmpty
        ? 'p:$productId'
        : (categoryId.isNotEmpty ? 'c:$categoryId' : _everything);
    final List<DropdownMenuItem<String>> items = [
      const DropdownMenuItem<String>(
        value: _everything,
        child: Text('Everything sold'),
      ),
      for (final ProductCategoryRecord category in categories)
        DropdownMenuItem<String>(
          value: 'c:${category.id}',
          child: Text(
            'Category — ${category.name}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      for (final Product product in goods)
        DropdownMenuItem<String>(
          value: 'p:${product.id}',
          child: Text(
            'Product — ${product.name}',
            overflow: TextOverflow.ellipsis,
          ),
        ),
    ];
    // A stored id that is not in the loaded list must stay as an item of its
    // own, or `DropdownButtonFormField` asserts and the form saves as blank.
    if (selected != _everything &&
        !items.any((item) => item.value == selected)) {
      items.add(DropdownMenuItem<String>(
        value: selected,
        child: const Text('(no longer listed)'),
      ));
    }
    return DropdownButtonFormField<String>(
      isExpanded: true,
      initialValue: selected,
      decoration: const InputDecoration(
        labelText: 'On',
        helperText: 'A rule about named goods beats a broader one for those '
            'lines; the broader one still covers the rest.',
      ),
      items: items,
      onChanged: enabled
          ? (value) {
              final String choice = value ?? _everything;
              if (choice.startsWith('p:')) {
                onChanged(choice.substring(2), '');
              } else if (choice.startsWith('c:')) {
                onChanged('', choice.substring(2));
              } else {
                onChanged('', '');
              }
            }
          : null,
    );
  }
}

/// Name the arrangement a figure was worked out on.
String basisLabel(String basis) => switch (basis) {
      'INVOICED' => 'Invoiced value',
      'COLLECTED' => 'Money collected',
      'MIXED' => 'Both (the rate changed)',
      _ => '—',
    };

/// One rung being typed, held as text so a half-finished band need not parse.
class _SlabDraft {
  _SlabDraft({
    required this.from,
    required this.to,
    required this.percentage,
  });

  factory _SlabDraft.from(CommissionSlabRecord slab) => _SlabDraft(
        from: TextEditingController(text: trimDecimal(slab.fromAmount)),
        to: TextEditingController(text: trimDecimal(slab.toAmount)),
        percentage: TextEditingController(text: trimDecimal(slab.percentage)),
      );

  /// A new rung continues where the one above it stopped, because that is the
  /// only thing the server will accept — the rungs have to meet exactly.
  factory _SlabDraft.empty({String startingAt = ''}) => _SlabDraft(
        from: TextEditingController(text: startingAt),
        to: TextEditingController(),
        percentage: TextEditingController(),
      );

  final TextEditingController from;
  final TextEditingController to;
  final TextEditingController percentage;

  Json toJson() => <String, dynamic>{
        'from_amount': from.text.trim(),
        if (to.text.trim().isNotEmpty) 'to_amount': to.text.trim(),
        'percentage': percentage.text.trim(),
      };

  void dispose() {
    from.dispose();
    to.dispose();
    percentage.dispose();
  }
}

/// The ladder: rungs of value, each with its own rate, and how they read.
///
/// The mode is the firm's to declare rather than something to infer, because
/// the two pay very differently on the same numbers — 120,000 against 2% to
/// 100,000 and 3% above pays 2,600 read one way and 3,600 read the other.
class _LadderEditor extends StatelessWidget {
  const _LadderEditor({
    required this.slabs,
    required this.mode,
    required this.enabled,
    required this.onModeChanged,
    required this.onAdd,
    required this.onRemove,
  });

  final List<_SlabDraft> slabs;
  final String mode;
  final bool enabled;
  final ValueChanged<String> onModeChanged;
  final VoidCallback onAdd;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text('Slabs', style: theme.textTheme.titleSmall),
            ),
            TextButton.icon(
              onPressed: enabled ? onAdd : null,
              icon: const Icon(Icons.add, size: 16),
              label: const Text('Add slab'),
            ),
          ],
        ),
        if (slabs.isEmpty)
          Text(
            'No slabs, so the flat rate above is what this rule pays.',
            style: theme.textTheme.bodySmall,
          )
        else ...[
          DropdownButtonFormField<String>(
            isExpanded: true,
            initialValue: mode,
            decoration: const InputDecoration(labelText: 'How the slabs read'),
            items: const [
              DropdownMenuItem(
                value: 'MARGINAL',
                child: Text('Each band at its own rate'),
              ),
              DropdownMenuItem(
                value: 'WHOLE_AMOUNT',
                child: Text('Everything at the band reached'),
              ),
            ],
            onChanged:
                enabled ? (value) => onModeChanged(value ?? mode) : null,
          ),
          const SizedBox(height: AppSpacing.sm),
          for (int index = 0; index < slabs.length; index++)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextField(
                      controller: slabs[index].from,
                      enabled: enabled,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(labelText: 'From'),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: TextField(
                      controller: slabs[index].to,
                      enabled: enabled,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: InputDecoration(
                        labelText: 'To',
                        helperText: index == slabs.length - 1
                            ? 'Empty runs on'
                            : null,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  SizedBox(
                    width: 96,
                    child: TextField(
                      controller: slabs[index].percentage,
                      enabled: enabled,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9.]')),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'Rate',
                        suffixText: '%',
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Remove this slab',
                    onPressed: enabled ? () => onRemove(index) : null,
                    icon: const Icon(Icons.close, size: 18),
                  ),
                ],
              ),
            ),
        ],
      ],
    );
  }
}

/// A date, typed as `YYYY-MM-DD` or chosen from the calendar.
///
/// Typed as well as picked because a report period is usually a month somebody
/// already knows, and four calendar taps to reach it is three too many.
class CommissionDateField extends StatelessWidget {
  const CommissionDateField({
    super.key,
    required this.controller,
    required this.label,
    this.helper,
    this.enabled = true,
    this.onChanged,
  });

  final TextEditingController controller;
  final String label;
  final String? helper;
  final bool enabled;
  final VoidCallback? onChanged;

  Future<void> _pick(BuildContext context) async {
    final DateTime anchor = parseIsoDate(controller.text) ?? DateTime.now();
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: anchor,
      firstDate: DateTime(anchor.year - 5),
      lastDate: DateTime(anchor.year + 5),
    );
    if (picked == null) return;
    controller.text = isoDate(picked);
    onChanged?.call();
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: controller,
        enabled: enabled,
        decoration: InputDecoration(
          labelText: label,
          helperText: helper ?? 'YYYY-MM-DD',
          isDense: true,
          suffixIcon: IconButton(
            tooltip: 'Pick a date',
            icon: const Icon(Icons.event, size: 18),
            onPressed: enabled ? () => _pick(context) : null,
          ),
        ),
      );
}

/// A quiet line of explanation, in the shape the credit policy dialog uses.
class CommissionNotice extends StatelessWidget {
  const CommissionNotice({super.key, required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            text,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      ],
    );
  }
}

class _TotalCard extends StatelessWidget {
  const _TotalCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(value, style: theme.textTheme.titleLarge),
          ],
        ),
      ),
    );
  }
}

class _ErrorLine extends StatelessWidget {
  const _ErrorLine({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Text(
      message,
      style: theme.textTheme.bodySmall
          ?.copyWith(color: theme.colorScheme.error),
    );
  }
}

/// Render `2.5000` as `2.5` — the server stores a scale nobody types.
String trimDecimal(String value) {
  if (!value.contains('.')) return value;
  final String trimmed =
      value.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
  return trimmed.isEmpty ? '0' : trimmed;
}

/// A date as the API writes it.
String isoDate(DateTime value) => '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

/// Read `YYYY-MM-DD`, or nothing.
///
/// Deliberately stricter than `DateTime.tryParse`, which happily accepts a
/// timestamp and half a dozen other shapes — a report period read out of one
/// of those is a period nobody asked for.
DateTime? parseIsoDate(String text) {
  final String trimmed = text.trim();
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(trimmed)) return null;
  return DateTime.tryParse(trimmed);
}
