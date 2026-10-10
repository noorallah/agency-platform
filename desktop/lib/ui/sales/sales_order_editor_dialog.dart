import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../models/batch_sale_settings.dart';
import '../../models/batch_serial.dart';
import '../../models/branch_warehouse.dart';
import '../../models/customer.dart';
import '../../models/entities.dart';
import '../../models/firm_member.dart';
import '../../models/pricing.dart';
import '../../models/product.dart';
import '../../models/uom_packaging.dart';
import '../../models/document_preview.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../document_framework/document_steps.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/desktop_framework.dart';
import 'ship_to_field.dart';

part 'sales_order_editor_phase2.dart';

/// One line of the order, while it is being typed.
///
/// The controllers belong to the draft rather than to the state, because a
/// line removed from the middle of the list has to take its own text with it
/// -- parallel lists of controllers are how a deleted row leaves the quantity
/// of the row below it behind.

class _LineDraft {
  _LineDraft({
    required this.productId,
    String quantity = '1',
    String unitPrice = '0',
    String free = '',
    String discountPercent = '',
    String discountAmount = '',
    this.lastRate = '',
    this.lastSource = '',
    this.freePromotionId,
    this.offerFree = '',
  })  : quantity = TextEditingController(text: quantity),
        unitPrice = TextEditingController(text: unitPrice),
        free = TextEditingController(text: free),
        discountPercent = TextEditingController(text: discountPercent),
        discountAmount = TextEditingController(text: discountAmount);

  String? productId;
  final TextEditingController quantity;
  final TextEditingController unitPrice;

  /// Goods thrown in with this line. Charged for at nothing, so it never
  /// enters the line's value -- but stock moves for it, and the order says so.
  final TextEditingController free;

  /// The offer that gave this saved line its free goods, and how many it
  /// gave; null where somebody typed them (`free_promotion_id`). The box
  /// stays blank for an offer's goods: sending the figure back would make
  /// them typed, which escapes the offer's free-unit budget and is claimed
  /// from the principal in full. Typing a figure in the box still replaces
  /// the offer's, and 0 refuses it.
  final String? freePromotionId;
  final String offerFree;

  /// Whether the free goods shown are an offer's, not typed.
  bool get freeFromOffer =>
      freePromotionId != null && free.text.trim().isEmpty;

  /// The rate the stored line was priced at, and where it came from, when
  /// it was resolved rather than typed: said under the blank box.
  final String lastRate;
  final String lastSource;

  /// Left blank on a new line **on purpose**. Blank is omitted from the
  /// payload, and absent is what lets the server apply the more specific
  /// arrangement it knows about: the firm's price list for this customer and
  /// product first, the customer's blanket rate after it. A typed zero is an
  /// instruction -- "not this time" -- and is sent as zero.
  final TextEditingController discountPercent;

  /// A flat figure off this line, which beats the percentage when both are
  /// given. Same rule: blank says nothing, zero refuses.
  final TextEditingController discountAmount;

  /// True once somebody typed a price.
  ///
  /// A line nobody has priced follows whichever product is chosen; one that
  /// has been typed into does not, because refilling it would overwrite a
  /// price the salesman had just agreed.
  bool priceEdited = false;

  /// Where the server says this line's price came from ("Price list",
  /// "Dealer level", "Product price"), or empty before it has been asked.
  /// Cleared the moment somebody types a price.
  String priceSource = '';

  /// Fill the price from the product's own, unless it was typed into.
  /// The batch the customer asked for (backlog 79 row 4), or null for
  /// earliest expiry. Kept even when the batch is no longer listed.
  String? pinnedBatchId;

  /// The product's batches with stock, read for [batchKey]; null until read.
  List<BatchAvailabilityRecord>? batches;
  String batchKey = '';

  void followProduct(String price) {
    if (priceEdited) return;
    unitPrice.text = price;
    priceSource = '';
  }

  double get _quantity => double.tryParse(quantity.text.trim()) ?? 0;
  double get _price => double.tryParse(unitPrice.text.trim()) ?? 0;

  /// What this line is worth before any discount. Free goods are outside it
  /// everywhere on this platform, so they are never discounted either.
  double get gross => _quantity * _price;

  /// What this line adds to the order, before tax and before any discount on
  /// the whole document. An amount beats a percentage, as it does on the
  /// server.
  double get netOfDiscount {
    final double amount = double.tryParse(discountAmount.text.trim()) ?? -1;
    if (amount >= 0) return gross - amount;
    final double percent = double.tryParse(discountPercent.text.trim()) ?? 0;
    return gross * (1 - percent / 100);
  }

  void dispose() {
    quantity.dispose();
    unitPrice.dispose();
    free.dispose();
    discountPercent.dispose();
    discountAmount.dispose();
  }
}

/// Taking an order.
///
/// A sales order could only appear here by converting a quotation, so a phone
/// order had to be typed as an offer and accepted in the same breath -- two
/// documents, and an acceptance the customer never gave. `POST
/// /api/v1/sales-orders` had worked all along with nothing on the desktop
/// calling it.
///
/// It loads its own pickers rather than being handed them, so the management
/// page needs to know nothing but the id of the order to open.
class SalesOrderEditorDialog extends StatefulWidget {
  const SalesOrderEditorDialog({
    super.key,
    required this.api,
    required this.today,
    this.orderId,
    this.steps = const [],
  });

  final ApiClient api;

  /// The order's next steps, as the list toolbar offers them (D-BUY-22):
  /// *Save & approve* where the user may approve, and the rest of a saved
  /// order's steps. Empty offers none.
  final List<DocumentStep<Json>> steps;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  /// The draft being corrected, or null to take a new order.
  ///
  /// Only a draft can be corrected -- the server refuses anything else,
  /// because an approved order has committed credit and a delivered one has
  /// moved stock.
  final String? orderId;

  @override
  State<SalesOrderEditorDialog> createState() => _SalesOrderEditorDialogState();
}

class _SalesOrderEditorDialogState extends State<SalesOrderEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _customerReference = TextEditingController();
  final TextEditingController _reference = TextEditingController();
  final TextEditingController _coupon = TextEditingController();
  final TextEditingController _remarks = TextEditingController();

  /// The firm's own fields on a sales order (MST-6), sent only once the
  /// definitions arrived.
  late final CustomFieldsController _customFields = CustomFieldsController(
    load: () => widget.api.applicableAttributeDefinitions('SALES_ORDER'),
  );

  /// A deal struck on the whole order. The server takes it off what the lines
  /// discounted to and splits it back across them, so the tax falls with it.
  final TextEditingController _billDiscountPercent = TextEditingController();
  final TextEditingController _billDiscountAmount = TextEditingController();

  /// What a promotion took off the whole order when it was last saved, shown
  /// under the blank box rather than refilled into it: refilled, the next
  /// save sent it as typed, and a typed figure switches the offer off (plan
  /// item 10.7, 2026-09-13). Empty when the figure was typed or nothing gave
  /// one.
  String _billResolvedHelper = '';
  final TextEditingController _freightAmount = TextEditingController();

  /// What was agreed on payment (backlog 67 row 4). Both stay blank unless
  /// somebody types them: blank days takes the customer's, and the order
  /// says so beside the box rather than filling it in.
  final TextEditingController _paymentTerms = TextEditingController();
  final TextEditingController _paymentTermsDays = TextEditingController();

  final List<_LineDraft> _lines = <_LineDraft>[];

  /// Lines the offers' engine added -- nothing sold, goods given, carrying
  /// `free_promotion_id` (D-PRC-39). They are the server's: shown, never
  /// edited, and never sent back, because a line sent back is a line a
  /// person typed, which escapes the offer's free-unit budget. The server
  /// adds them again from the offer on every save.
  final List<Json> _offerFreeLines = <Json>[];

  /// Unit codes by id, read once for the offers' free lines.
  final Map<String, String> _unitCodes = <String, String>{};
  bool _unitsAsked = false;

  List<Customer> _customers = const [];
  List<Product> _products = const [];
  List<BranchRecord> _branches = const [];
  List<WarehouseRecord> _warehouses = const [];

  String? _customerId;

  /// Where the goods go: one of the customer's addresses (backlog 67 row 3).
  /// Preselected with the default shipping address rather than left to the
  /// server's silence once the customer's addresses are in hand.
  String? _shippingAddressId;

  /// Who took the order.
  ///
  /// Optional on the API and optional here, but what a blank costs is worth
  /// saying, so the field carries its own helper. Two things make the honest
  /// sentence longer than it looks: where the customer is on a round, the
  /// server derives that round's salesman for a document that names none
  /// (`_derived_salesman` in `app/sales/services/scope_resolution.py`), so a
  /// blank is not automatically nobody -- and where they are not, the money
  /// this order collects lands in the commission report's Unassigned bucket,
  /// which belongs to nobody and pays nobody.
  ///
  /// The picker offers every member of the firm and does not filter by who
  /// covers the customer's round. The server refuses a salesman who does not,
  /// in a sentence that names the reason; filtering here would need the
  /// customer's assignments on every keystroke and would still have to trust
  /// that refusal.
  String? _salesmanId;
  List<FirmMember> _members = const <FirmMember>[];
  String? _branchId;
  String? _warehouseId;
  late DateTime _orderDate;
  DateTime? _deliveryDate;

  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// The version the order was read at, sent back as `If-Match`. The update
  /// replaces the whole line collection, so a lost race costs every line
  /// somebody entered rather than a single field.
  int _version = 0;

  /// Phase 2: the order as the server priced it last, and the line the side
  /// panel follows.
  SalesOrderPreviewRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;
  bool _phase2 = false;

  /// Phase 2, backlog 64 row 4: whether the rates typed on this order include
  /// GST. A new order starts from the firm's setting; a draft keeps its own,
  /// and the switch can move it.
  bool _rateIncludesTax = false;

  void _setState(VoidCallback change) => setState(change);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _phase2 = Phase2Scope.of(context);
  }

  /// Price the order again once the typing pauses; only the latest answer
  /// lands. Phase 2 only, and never for an order that can no longer change.
  void _schedulePreview() {
    if (!_phase2 || _locked) return;
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      final List<int> rows = _finishedRows();
      final Json? draft = rows.isEmpty ? null : _buildPayload(only: rows);
      if (draft == null || !mounted) return;
      final int serial = ++_previewSerial;
      try {
        final SalesOrderPreviewRecord priced =
            await widget.api.previewSalesOrder(draft);
        if (!mounted || serial != _previewSerial) return;
        setState(() {
          _preview = priced;
          _pricedAs = <int, int>{
            for (int at = 0; at < rows.length; at += 1) rows[at]: at + 1,
          };
        });
        _ensureUnitCodes();
      } on ApiException {
        // A half-typed order the server refuses: keep the last figures.
      }
    });
  }

  /// The rows that can be priced as they stand, without asking the form to
  /// show its errors: a row still being typed is left out, so it no longer
  /// stops the finished ones being priced (D-UI-93). Empty while nothing can
  /// be priced at all.
  List<int> _finishedRows() {
    if (_customerId == null || _branchId == null || _warehouseId == null) {
      return const <int>[];
    }
    return <int>[
      for (int index = 0; index < _lines.length; index += 1)
        if (_finished(_lines[index])) index,
    ];
  }

  bool _finished(_LineDraft line) {
    if (line.productId == null) return false;
    if ((double.tryParse(line.quantity.text.trim()) ?? 0) <= 0) return false;
    if (!_rateIncludesTax &&
        (double.tryParse(line.unitPrice.text.trim()) ?? 0) <= 0) {
      return false;
    }
    return _percentage(line.discountPercent.text) == null;
  }

  /// The line number each row was priced under in [_preview]: rows still
  /// being typed are left out of a pricing, so the numbers can differ.
  Map<int, int> _pricedAs = const <int, int>{};

  /// The order's status as it was read. Only a draft may be rewritten.
  String _status = 'DRAFT';

  /// STK-12: when the order's stock hold lapsed unshipped, if it did.
  String _reservationLapsedAt = '';

  /// The order as the server last answered it -- read to be corrected, or
  /// saved by this window; null for a new order not yet saved.
  Json? _record;

  /// Whether this window has written the order, so closing it tells the list
  /// to read itself again.
  bool _wrote = false;

  String? get _orderId =>
      widget.orderId ?? (_record == null ? null : stringValue(_record!['id']));

  bool get _editing => _orderId != null;

  bool get _locked => _editing && _status != 'DRAFT';

  @override
  void initState() {
    super.initState();
    _orderDate = widget.today;
    _load();
    _readBatchRules();
  }

  /// Backlog 79 row 7: the firm takes a line's rate from the selling price of
  /// the batch pinned on it. Read once on opening; unreadable means off.
  bool _priceFromBatch = false;

  Future<void> _readBatchRules() async {
    try {
      final BatchSaleSettings rules = await widget.api.batchSaleSettings();
      if (mounted) _priceFromBatch = rules.priceFromBatch;
    } on Object {
      // Off: a rate the person types is never second-guessed.
    }
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _customFields.dispose();
    for (final _LineDraft line in _lines) {
      line.dispose();
    }
    _customerReference.dispose();
    _reference.dispose();
    _coupon.dispose();
    _remarks.dispose();
    _billDiscountPercent.dispose();
    _billDiscountAmount.dispose();
    _freightAmount.dispose();
    _paymentTerms.dispose();
    _paymentTermsDays.dispose();
    super.dispose();
  }

  /// Read the pickers and, when correcting one, the order itself.
  ///
  /// Every picker is paged through rather than asked for in one large page:
  /// `MAX_PAGE_SIZE` is 100 and a request above it is refused rather than
  /// clamped, which surfaces as a 500 on some routers.
  Future<void> _load() async {
    try {
      final List<dynamic> loaded = await Future.wait<dynamic>(<Future<dynamic>>[
        fetchAllPages<Customer>(
          (int page) =>
              widget.api.customers(page: page, pageSize: maxApiPageSize),
        ),
        fetchAllPages<Product>(
          (int page) =>
              widget.api.products(page: page, pageSize: maxApiPageSize),
        ),
        fetchAllPages<BranchRecord>(
          (int page) =>
              widget.api.branches(page: page, pageSize: maxApiPageSize),
        ),
        fetchAllPages<WarehouseRecord>(
          (int page) =>
              widget.api.warehouses(page: page, pageSize: maxApiPageSize),
        ),
        // Not paged: one firm's people, and the endpoint answers them all.
        widget.api.firmMembers(),
      ]);
      final String? id = widget.orderId;
      final Json? existing =
          id == null ? null : _unwrap(await widget.api.salesOrder(id));
      // The firm's default for a new order's switch. Unreadable settings
      // leave it off, which is what the order always did.
      bool firmDefault = false;
      if (id == null && _phase2) {
        try {
          firmDefault = (await widget.api.salesWorkflowSettings())
              .rateIncludesTax;
        } on ApiException {
          firmDefault = false;
        }
      }
      if (!mounted) return;
      setState(() {
        if (existing == null) _rateIncludesTax = firmDefault;
        _customers = (loaded[0] as List<dynamic>).cast<Customer>();
        _products = (loaded[1] as List<dynamic>).cast<Product>();
        _branches = (loaded[2] as List<dynamic>).cast<BranchRecord>();
        _warehouses = (loaded[3] as List<dynamic>).cast<WarehouseRecord>();
        _members = (loaded[4] as List<dynamic>).cast<FirmMember>();
        _loading = false;
        if (existing != null) {
          _adoptExisting(existing);
        } else {
          // The branch and the warehouse are nearly always the same ones, and
          // the firm says which. The customer is left unchosen: it is the
          // point of the document, and defaulting it means an order can be
          // raised for the wrong shop by not touching the field.
          //
          // The warehouse is the chosen branch's default, never the first
          // default in a newest-first list: with two branches that could be
          // another branch's, which the server refuses (D-QA-17).
          _branchId = preferredBranchId(_branches);
          _warehouseId = preferredWarehouseId(_warehouses, branchId: _branchId);
        }
        if (_lines.isEmpty) _lines.add(_newLine());
      });
      // After the order, so a correction opens with its stored values.
      unawaited(_customFields.start());
      _ensureUnitCodes();
      // Phase 2 prices what was loaded straight away.
      _schedulePreview();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// The warehouse to show once [branchId] is chosen: the one already chosen
  /// if it belongs there, else that branch's default. An order's warehouse
  /// must belong to its branch, so keeping another branch's is keeping a
  /// refusal.
  String? _warehouseFor(String? branchId) {
    for (final WarehouseRecord item in _warehouses) {
      if (item.id == _warehouseId && item.branchId == branchId) {
        return _warehouseId;
      }
    }
    return preferredWarehouseId(_warehouses, branchId: branchId);
  }

  Json _unwrap(Json response) {
    final dynamic data = response['data'];
    return data is Map ? Map<String, dynamic>.from(data) : response;
  }

  /// Build the form from an order that already exists.
  ///
  /// Everything comes off the document rather than off the masters: an order
  /// records what was agreed on the day it was taken, and re-reading a price
  /// or a discount out of the customer master would rewrite it.
  void _adoptExisting(Json order) {
    _record = order;
    _version = (order['version'] as num?)?.toInt() ?? 0;
    _status = stringValue(order['status']).isEmpty
        ? 'DRAFT'
        : stringValue(order['status']);
    _reservationLapsedAt = stringValue(order['reservation_lapsed_at']);
    _customerId = _blankToNull(stringValue(order['customer_id']));
    // The order's own address; the customer's default only for an order
    // saved before it recorded one.
    _shippingAddressId =
        _blankToNull(stringValue(order['shipping_address_id'])) ??
            defaultShipToId(_customerAddresses);
    _salesmanId = _blankToNull(stringValue(order['salesman_id']));
    _branchId = _blankToNull(stringValue(order['branch_id']));
    _warehouseId = _blankToNull(stringValue(order['warehouse_id']));
    _orderDate =
        DateTime.tryParse(stringValue(order['order_date'])) ?? _orderDate;
    _deliveryDate = DateTime.tryParse(stringValue(order['delivery_date']));
    _customerReference.text = stringValue(order['customer_reference']);
    _reference.text = stringValue(order['reference_number']);
    _coupon.text = stringValue(order['coupon_code']);
    _paymentTerms.text = stringValue(order['payment_terms']);
    _paymentTermsDays.text = stringValue(order['payment_terms_days']);
    _rateIncludesTax = order['rate_includes_tax'] == true;
    _remarks.text = stringValue(order['remarks']);
    _customFields.seed(attributeValuesFrom(order['attributes']));
    // Blank rather than '0' where there was none, so the box reads as empty
    // and the payload omits it.
    // Only what somebody typed comes back into the boxes. An order saved
    // before the source was recorded (null) keeps the old behaviour.
    final String billSource = stringValue(order['bill_discount_source']);
    final String billAmount = _positiveOrBlank(order['bill_discount_amount']);
    if (billSource == 'promotion' || billSource == 'none') {
      _billDiscountPercent.text = '';
      _billDiscountAmount.text = '';
      _billResolvedHelper = billAmount.isEmpty
          ? ''
          : 'Last taken off: ${trimDiscountRate(billAmount)} by a promotion. '
              'Blank prices it afresh.';
    } else {
      _billDiscountPercent.text = _positiveOrBlank(
        order['bill_discount_percent'],
      );
      _billDiscountAmount.text = billAmount;
      _billResolvedHelper = '';
    }
    // The delivery charge that was **asked** for, not what was left of it: a
    // free-shipping offer's share comes off again on save if the offer still
    // applies, and is charged if it no longer does. Sending back the charged
    // figure alone would bake a lapsed offer's waiver into the order, and the
    // charge could never come back (D-SELL-35, the order twin of D-SELL-34).
    _freightAmount.text = _askedFreight(order);

    final List<dynamic> lines =
        order['lines'] is List ? order['lines'] as List : const [];
    _offerFreeLines.clear();
    for (final dynamic raw in lines) {
      final Json line = Map<String, dynamic>.from(raw as Map);
      if (_isOfferFreeLine(line)) {
        _offerFreeLines.add(line);
        continue;
      }
      // Typed with GST in the rate: the boxes read what was typed, which the
      // server derives the stored pre-tax figures from.
      final String enteredRate = stringValue(line['entered_rate']);
      final String enteredDiscount = _rateIncludesTax &&
              stringValue(line['discount_source']) == 'amount'
          ? stringValue(line['entered_discount_amount'])
          : '';
      _lines.add(
        _LineDraft(
          productId: _blankToNull(stringValue(line['product_id'])),
          quantity: stringValue(line['quantity']),
          unitPrice: _rateIncludesTax && enteredRate.isNotEmpty
              ? enteredRate
              : stringValue(line['unit_price']),
          // An offer's free goods are not echoed back as a figure (D-PRC-5).
          free: _blankToNull(stringValue(line['free_promotion_id'])) == null
              ? _positiveOrBlank(line['free_quantity'])
              : '',
          freePromotionId: _blankToNull(stringValue(line['free_promotion_id'])),
          offerFree: _positiveOrBlank(line['free_quantity']),
          // A typed rate is echoed **including a zero**, because the document
          // is the record of what was agreed. A rate the server resolved is
          // priced afresh: re-sending it as typed froze a ladder at its first
          // step (plan item 9.2, 2026-09-13). Only the rate, never the amount
          // beside it: a flat amount wins over a rate and would pin the
          // discount to a figure that no longer matches once the quantity
          // moves.
          discountPercent: enteredDiscount.isEmpty &&
                  discountWasTyped(stringValue(line['discount_source']))
              ? stringValue(line['discount_percent'])
              : '',
          discountAmount: enteredDiscount,
          lastRate: discountWasTyped(stringValue(line['discount_source']))
              ? ''
              : stringValue(line['discount_percent']),
          lastSource: stringValue(line['discount_source']),
        )
          ..priceEdited = true
          ..pinnedBatchId = _blankToNull(stringValue(line['pinned_batch_id'])),
      );
    }
  }

  String? _blankToNull(String value) => value.isEmpty ? null : value;

  /// A line the engine added for an offer: sells nothing and names the
  /// offer that gave it. A line somebody typed has no `free_promotion_id`.
  bool _isOfferFreeLine(Map<dynamic, dynamic> line) =>
      stringValue(line['free_promotion_id']).isNotEmpty &&
      (double.tryParse(stringValue(line['quantity'])) ?? 0) == 0;

  /// The offers' free lines to show: as the last pricing returned them, else
  /// as the order was read.
  List<Json> get _offerFreeShown {
    final Json? order = _preview?.order;
    if (order == null) return _offerFreeLines;
    return <Json>[
      for (final dynamic raw in order['lines'] as List? ?? const <dynamic>[])
        if (raw is Map && _isOfferFreeLine(raw)) Map<String, dynamic>.from(raw),
    ];
  }

  /// "Free with CODE: 2 PIECE" for one of the offers' free lines.
  String _offerFreeWords(Json line) {
    final String named = stringValue(line['description']);
    final String unit = _unitCodes[stringValue(line['sales_uom_id'])] ??
        _product(stringValue(line['product_id']))?.displayUnit ??
        '';
    final String quantity = documentQuantity(stringValue(line['free_quantity']));
    return '${named.isEmpty ? 'Free with the offer' : named}: $quantity'
        '${unit.isEmpty ? '' : ' $unit'}';
  }

  /// Read the unit names once, only when an offer's free line names a unit.
  void _ensureUnitCodes() {
    if (_unitsAsked) return;
    if (!_offerFreeShown
        .any((line) => stringValue(line['sales_uom_id']).isNotEmpty)) {
      return;
    }
    _unitsAsked = true;
    unawaited(() async {
      try {
        final List<UomRecord> units = await widget.api.uoms();
        if (!mounted) return;
        setState(() {
          for (final UomRecord unit in units) {
            _unitCodes[unit.id] = unit.code;
          }
        });
      } on ApiException {
        // The product's own unit is shown instead.
      }
    }());
  }

  /// The chosen customer's addresses, empty until a customer is chosen.
  List<CustomerAddress> get _customerAddresses {
    for (final Customer item in _customers) {
      if (item.id == _customerId) return item.addresses;
    }
    return const <CustomerAddress>[];
  }

  /// A stored figure as the box should read it: blank when it is nothing.
  /// The delivery charge an order asked for, blank where it asked none.
  String _askedFreight(Json order) {
    final double charged =
        double.tryParse(stringValue(order['freight_amount'])) ?? 0;
    final double waived =
        double.tryParse(stringValue(order['freight_waived_amount'])) ?? 0;
    if (waived <= 0) return _positiveOrBlank(order['freight_amount']);
    return (charged + waived).toStringAsFixed(4);
  }

  String _positiveOrBlank(dynamic value) {
    final String text = stringValue(value);
    return (double.tryParse(text) ?? 0) > 0 ? text : '';
  }

  /// What a product sells for, as the price box should read.
  ///
  /// Shown rather than applied silently on the server, because a price is the
  /// central term of a sale -- a document that says nothing about it is
  /// incomplete, not one that means "the usual". The API requires an explicit
  /// price for the same reason.
  String _priceOf(String? productId) {
    // Blank on an order whose rates include GST: the product's price is
    // before tax, and a blank rate takes it as such on the server.
    if (_rateIncludesTax) return '';
    for (final Product item in _products) {
      if (item.id != productId) continue;
      final double price = double.tryParse(item.sellingPrice.trim()) ?? 0;
      return price > 0 ? item.sellingPrice.trim() : '0';
    }
    return '0';
  }

  /// What the product lists at, where that is worth saying.
  ///
  /// Silent once somebody has typed: the number on screen is then theirs, and
  /// repeating the list price beside it reads as a correction.
  String? _priceHelper(_LineDraft line) {
    if (line.priceEdited) return null;
    for (final Product item in _products) {
      if (item.id != line.productId) continue;
      final double mrp = double.tryParse(item.mrp.trim()) ?? 0;
      final double price = double.tryParse(item.sellingPrice.trim()) ?? 0;
      if (price <= 0) return null;
      return mrp > 0 ? 'lists at ${item.sellingPrice}, MRP ${item.mrp}' : null;
    }
    return null;
  }

  /// Move an unpriced line onto the newly chosen product's price.
  void _chooseProduct(_LineDraft line, String? productId) {
    setState(() {
      // A batch belongs to one product: choosing another drops the pin.
      if (line.productId != productId) {
        line.pinnedBatchId = null;
        line.batches = null;
        line.batchKey = '';
      }
      line.productId = productId;
      line.followProduct(_priceOf(productId));
    });
    unawaited(_quotePrices([line]));
  }

  /// Ask the server what this customer is charged for the unpriced [lines]
  /// and show it in the price box, with where it came from.
  ///
  /// Phase 2 only, and a suggestion: a line somebody has typed into is never
  /// touched, the answer is dropped if the product moved while it was on its
  /// way, and the figure still goes out as the typed value it now is -- so
  /// what is saved is what is on screen. A refusal or a missing answer leaves
  /// the product's own price where it was.
  Future<void> _quotePrices(Iterable<_LineDraft> lines) async {
    final String? customerId = _customerId;
    // With GST in the rate a blank box is the server's own pre-tax price, and
    // a quoted pre-tax figure typed into it would be read as shelf price.
    if (!_phase2 || _locked || _rateIncludesTax || customerId == null) return;
    final List<_LineDraft> targets = [
      for (final _LineDraft line in lines)
        if (!line.priceEdited && line.productId != null) line,
    ];
    if (targets.isEmpty) return;
    final Map<_LineDraft, String> asked = {
      for (final _LineDraft line in targets) line: line.productId!,
    };
    try {
      final Map<String, UnitPriceQuote> quotes = await widget.api.unitPrices(
        productIds: asked.values.toSet().toList(),
        on: _iso(_orderDate),
        customerId: customerId,
      );
      if (!mounted || _customerId != customerId) return;
      setState(() {
        asked.forEach((_LineDraft line, String productId) {
          final UnitPriceQuote? quote = quotes[productId];
          if (quote == null ||
              line.priceEdited ||
              line.productId != productId ||
              !_lines.contains(line)) {
            return;
          }
          if ((double.tryParse(quote.unitPrice) ?? 0) <= 0) return;
          line.unitPrice.text = _plainPrice(quote.unitPrice);
          line.priceSource = quote.sourceLabel;
        });
      });
      _schedulePreview();
    } on Object {
      // Only a suggestion: the product's own price stays.
    }
  }

  /// `100.0000` as `100.00`: the server's scale, kept to two places unless
  /// the price really has more.
  static String _plainPrice(String value) {
    final String text = value.trim();
    if (!text.contains('.')) return text;
    String trimmed = text.replaceAll(RegExp(r'0+$'), '');
    final int decimals = trimmed.length - trimmed.indexOf('.') - 1;
    if (decimals < 2) {
      trimmed = trimmed.padRight(trimmed.length + 2 - decimals, '0');
    }
    return trimmed;
  }

  /// A fresh line: no product and no quantity, so Save names what is missing
  /// rather than drafting an order for a product nobody chose (D-UI-22).
  _LineDraft _newLine() =>
      _LineDraft(productId: null, quantity: '', unitPrice: _priceOf(null));

  void _addLine() {
    final _LineDraft line = _newLine();
    setState(() => _lines.add(line));
    unawaited(_quotePrices([line]));
  }

  void _removeLine(int index) {
    // An order with no lines is not an order, and the server refuses one, so
    // the last row cannot be taken away -- the way to abandon it is Cancel.
    if (_lines.length <= 1) return;
    setState(() => _lines.removeAt(index).dispose());
  }

  /// The chosen customer's standing discount, or an empty string where there
  /// is none. Said on screen rather than filled into the boxes: filling it
  /// would turn an inherited rate into an explicit one, and an explicit rate
  /// outranks the firm's price list for this customer and product.
  String get _customerDiscount {
    for (final Customer item in _customers) {
      if (item.id != _customerId) continue;
      final double rate =
          double.tryParse(item.defaultDiscountPercent.trim()) ?? 0;
      return rate > 0 ? item.defaultDiscountPercent.trim() : '';
    }
    return '';
  }

  /// What the order comes to before tax, after both discounts.
  double get _beforeTax {
    final double lines = _lines.fold<double>(
      0,
      (double running, _LineDraft line) => running + line.netOfDiscount,
    );
    final double amount =
        double.tryParse(_billDiscountAmount.text.trim()) ?? -1;
    if (amount >= 0) return lines - amount;
    final double percent =
        double.tryParse(_billDiscountPercent.text.trim()) ?? 0;
    return percent <= 0 ? lines : lines * (1 - percent / 100);
  }

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  /// The rate box: required, except where the order's rates include GST and
  /// a blank takes the product's own (before-tax) price.
  String? _priceBox(String? value) {
    if (_rateIncludesTax && (value ?? '').trim().isEmpty) return null;
    return _positive(value, 'price');
  }

  String? _positive(String? value, String what) {
    final double parsed = double.tryParse((value ?? '').trim()) ?? -1;
    if (parsed <= 0) return 'Enter the $what.';
    return null;
  }

  /// A quantity given away cannot be a negative number of goods.
  String? _quantityOrBlank(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a quantity.';
    if (parsed < 0) return 'Cannot be negative.';
    return null;
  }

  /// A rate the server would refuse, caught before the round trip.
  String? _percentage(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a percentage.';
    if (parsed < 0 || parsed > 100) return 'Between 0 and 100.';
    return null;
  }

  /// A discount above what it comes off is refused by the server, because it
  /// produces a negative taxable value.
  String? _discountAmount(String? value, double ceiling, String subject) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter an amount.';
    if (parsed < 0) return 'Cannot be negative.';
    if (parsed > ceiling) return 'More than $subject comes to.';
    return null;
  }

  Json? _payload() {
    if (!(_form.currentState?.validate() ?? false)) return null;
    return _buildPayload();
  }

  /// What a save with nothing marked on screen is missing, said in words:
  /// the pickers carry no red mark of their own, so "check the fields marked
  /// below" pointed at nothing (D-UI-17).
  String? _missing() {
    if (_customerId == null) return 'Choose the customer.';
    if (_branchId == null || _warehouseId == null) {
      return 'Choose the branch and the warehouse the goods ship from.';
    }
    final int blank = _lines.indexWhere((_LineDraft l) => l.productId == null);
    if (blank >= 0) return 'Choose a product on line ${blank + 1}.';
    return null;
  }

  /// The order as it would be saved. [only] names the rows to send, numbered
  /// from 1 in that order, for pricing an order one of whose lines is still
  /// being typed; a save sends every row and passes nothing.
  Json? _buildPayload({List<int>? only}) {
    if (_customerId == null || _branchId == null || _warehouseId == null) {
      return null;
    }
    if (only == null &&
        _lines.any((_LineDraft line) => line.productId == null)) {
      return null;
    }
    final List<int> rows = only ??
        <int>[for (int index = 0; index < _lines.length; index += 1) index];
    final DateTime? delivery = _deliveryDate;
    return <String, dynamic>{
      'customer_id': _customerId,
      // Sent whenever the customer's addresses are in hand, so an update
      // after the customer changed never leans on "absent keeps the order's
      // own"; left out when the customer has none to choose from, and in
      // phase 1, which has no picker to say anything.
      if (_phase2 && _customerAddresses.isNotEmpty)
        'shipping_address_id': _shippingAddressId,
      // Omitted when nobody was named rather than sent null: absent is what
      // the create schema reads as "no salesman", and this form has no reason
      // to distinguish that from clearing one.
      if (_salesmanId != null) 'salesman_id': _salesmanId,
      'branch_id': _branchId,
      'warehouse_id': _warehouseId,
      'order_date': _iso(_orderDate),
      // Sent on every save: absent is off on a new order and keeps the
      // order's own on an update, and the switch is the user's to say.
      // Phase 1 has no switch, so a new order there is typed before tax.
      'rate_includes_tax': _rateIncludesTax,
      if (delivery != null) 'delivery_date': _iso(delivery),
      if (_customerReference.text.trim().isNotEmpty)
        'customer_reference': _customerReference.text.trim(),
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      // Omitted when blank, like every other optional field: an empty string
      // is a code that matches nothing rather than the absence of one.
      if (_coupon.text.trim().isNotEmpty) 'coupon_code': _coupon.text.trim(),
      if (_remarks.text.trim().isNotEmpty) 'remarks': _remarks.text.trim(),
      // Only once the definitions arrived: absent leaves the stored values
      // alone, and an empty list would clear them.
      if (_customFields.hasFields) 'attributes': _customFields.payload(),
      // Omitted when blank: absent is what tells the server there is no
      // discount on the order, and an empty string is a schema error.
      if (_billDiscountPercent.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscountPercent.text.trim(),
      if (_billDiscountAmount.text.trim().isNotEmpty)
        'bill_discount_amount': _billDiscountAmount.text.trim(),
      if (_freightAmount.text.trim().isNotEmpty)
        'freight_amount': _freightAmount.text.trim(),
      // Both sent on every phase 2 save: absent keeps the order's own on an
      // update, so a cleared box has to say null. Blank days is null, which
      // takes the customer's on a new order.
      if (_phase2) ...<String, dynamic>{
        'payment_terms': _paymentTerms.text.trim().isEmpty
            ? null
            : _paymentTerms.text.trim(),
        'payment_terms_days': int.tryParse(_paymentTermsDays.text.trim()),
      },
      'lines': <Json>[
        for (int at = 0; at < rows.length; at += 1)
          _linePayload(_lines[rows[at]], at + 1),
      ],
    };
  }

  Json _linePayload(_LineDraft line, int number) => <String, dynamic>{
        'line_number': number,
        'product_id': line.productId,
        'quantity': line.quantity.text.trim(),
        // With GST included, blank is the product's own price -- before
        // tax, as the server resolves it -- not a typed shelf price.
        if (!(_rateIncludesTax && line.unitPrice.text.trim().isEmpty))
          'unit_price': line.unitPrice.text.trim(),
        if (line.free.text.trim().isNotEmpty)
          'free_quantity': line.free.text.trim(),
        // Null is "earliest expiry"; sent on every line so a cleared pin
        // clears on update, since absent keeps the line's own.
        'pinned_batch_id': line.pinnedBatchId,
        // Blank is omitted and zero is sent. Absent means the server
        // applies the price list or the customer's standing rate; zero
        // means somebody refused it for this line. Coercing blank to zero
        // would switch every standing arrangement off silently.
        if (line.discountPercent.text.trim().isNotEmpty)
          'discount_percent': line.discountPercent.text.trim(),
        if (line.discountAmount.text.trim().isNotEmpty)
          'discount_amount': line.discountAmount.text.trim(),
      };

  /// Save and close.
  Future<void> _save() async {
    final Json? saved = await _persist();
    if (saved == null || !mounted) return;
    Navigator.of(context).pop(true);
  }

  /// Save, then approve what was saved (D-BUY-22). A refused approval leaves
  /// the window open on the saved draft with the server's sentence, and the
  /// next save corrects that draft rather than raising a second order.
  Future<void> _saveAndStep(DocumentStep<Json> step) => saveThenStep<Json>(
        context,
        save: _persist,
        step: step,
        onStopped: (saved, refusal) => setState(() {
          _record = saved;
          _version = (saved['version'] as num?)?.toInt() ?? _version;
          _saving = false;
          _error = refusal == null
              ? null
              : 'Saved as draft ${stringValue(saved['order_number'])}, but '
                  'not approved: $refusal';
        }),
      );

  /// Write the order, returning it as saved; null when the save was
  /// refused, which [_error] then says.
  Future<Json?> _persist() async {
    final String? customField = _customFields.validate();
    if (customField != null) {
      setState(() => _error = customField);
      return null;
    }
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = _missing() ?? 'Check the fields marked below.');
      return null;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final String? id = _orderId;
      final Json response;
      if (id == null) {
        response = await widget.api.createSalesOrder(payload);
      } else {
        response = await widget.api.updateSalesOrder(
          id,
          payload,
          expectedVersion: preconditionFor(_version),
        );
      }
      _wrote = true;
      final Json saved = _unwrap(response);
      return saved.isEmpty ? {...?_record, 'id': id} : saved;
    } on ApiException catch (error) {
      if (!mounted) return null;
      setState(() {
        // This dialog saves from inside itself, so a refusal leaves every
        // keystroke on screen -- and the message has to say so, because
        // closing the form is what throws them away.
        _error = saveFailureMessage(error, 'sales order', changesKept: true);
        _saving = false;
      });
      return null;
    }
  }

  Future<void> _pickOrderDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _orderDate,
      // An order taken last week is ordinary; one dated next year is a typo.
      firstDate: widget.today.subtract(const Duration(days: 365)),
      lastDate: widget.today.add(const Duration(days: 365)),
      helpText: 'Order taken on',
    );
    if (picked != null) setState(() => _orderDate = picked);
  }

  Future<void> _pickDeliveryDate() async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _deliveryDate ?? _orderDate,
      firstDate: _orderDate,
      lastDate: _orderDate.add(const Duration(days: 730)),
      helpText: 'Wanted by',
    );
    if (picked != null) setState(() => _deliveryDate = picked);
  }

  /// The items for one picker, with the stored id kept even when it is not in
  /// the loaded list.
  ///
  /// A customer who has since been deactivated, or a product beyond the pages
  /// read, would otherwise leave `DropdownButtonFormField` holding a value
  /// that matches no item -- which asserts, and on a form that survives it
  /// saves as blank.
  List<DropdownMenuItem<String>> _items(
    List<({String id, String label})> options,
    String? selected,
  ) {
    final List<DropdownMenuItem<String>> items = <DropdownMenuItem<String>>[
      for (final ({String id, String label}) option in options)
        DropdownMenuItem<String>(
          value: option.id,
          child: Text(option.label, overflow: TextOverflow.ellipsis),
        ),
    ];
    if (selected != null && !options.any((option) => option.id == selected)) {
      items.add(
        DropdownMenuItem<String>(
          value: selected,
          child: const Text(
            'On the order, no longer listed',
            overflow: TextOverflow.ellipsis,
          ),
        ),
      );
    }
    return items;
  }

  /// A picker that may honestly be left blank.
  ///
  /// [_picker] validates its value away from null, which is right for the
  /// customer and the warehouse and wrong for a salesman: an order taken at
  /// the counter was taken by nobody in particular, and refusing to save
  /// without a name would put a wrong one on every such order.
  Widget _optionalPicker({
    required String label,
    required String helperText,
    required String blankLabel,
    required String? value,
    required List<({String id, String label})> options,
    required ValueChanged<String?> onChanged,
    Key? key,
  }) =>
      DropdownButtonFormField<String?>(
        key: key,
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 3,
        ),
        items: <DropdownMenuItem<String?>>[
          DropdownMenuItem<String?>(
            value: null,
            child: Text(blankLabel, overflow: TextOverflow.ellipsis),
          ),
          for (final ({String id, String label}) option in options)
            DropdownMenuItem<String?>(
              value: option.id,
              child: Text(option.label, overflow: TextOverflow.ellipsis),
            ),
          // A stored id nobody in the list carries -- somebody who has left --
          // must stay an item of its own, or the widget asserts and the form
          // saves the order as though no salesman had ever been on it.
          if (value != null && !options.any((option) => option.id == value))
            DropdownMenuItem<String?>(
              value: value,
              child: Text(value, overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: _locked ? null : onChanged,
      );

  Widget _picker({
    required String label,
    String? helperText,
    required String? value,
    required List<({String id, String label})> options,
    required ValueChanged<String?> onChanged,
    required String emptyMessage,
    Key? key,
  }) =>
      DropdownButtonFormField<String>(
        key: key,
        initialValue: value,
        // Without this the button's row is `mainAxisSize: min` and never
        // constrains the label, so `ellipsis` has nothing to ellipsise
        // against and a long name overflows instead of eliding.
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 2,
        ),
        items: _items(options, value),
        validator: (String? chosen) => chosen == null ? emptyMessage : null,
        onChanged: _locked ? null : onChanged,
      );

  /// One line's row of controls.
  ///
  /// Each line carries its own running total, because the order's total alone
  /// does not say which of five lines was mistyped.
  Widget _lineEditor(int index) {
    final _LineDraft line = _lines[index];
    final bool removable = _lines.length > 1 && !_locked;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: _picker(
                  key: ValueKey<String>('sales-order-line-product-$index'),
                  label: 'Product ${index + 1}',
                  value: line.productId,
                  options: <({String id, String label})>[
                    for (final Product item in _products)
                      (id: item.id, label: '${item.code}  ${item.name}'),
                  ],
                  onChanged: (String? value) => _chooseProduct(line, value),
                  emptyMessage: 'Choose a product.',
                ),
              ),
              IconButton(
                onPressed: removable ? () => _removeLine(index) : null,
                icon: const Icon(Icons.close, size: 18),
                tooltip: removable
                    ? 'Remove this line'
                    : 'An order needs at least one line',
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextFormField(
                  controller: line.quantity,
                  enabled: !_locked,
                  decoration: const InputDecoration(labelText: 'Quantity'),
                  keyboardType: TextInputType.number,
                  validator: (String? value) => _positive(value, 'quantity'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextFormField(
                  controller: line.free,
                  enabled: !_locked,
                  decoration: InputDecoration(
                    labelText: 'Free',
                    helperText: line.freeFromOffer
                        ? 'The offer gives ${line.offerFree}. Blank keeps '
                            'it; 0 refuses it.'
                        : 'Blank takes the offer; 0 refuses it.',
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: _quantityOrBlank,
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextFormField(
                  controller: line.unitPrice,
                  enabled: !_locked,
                  decoration: InputDecoration(
                    labelText: 'Unit price',
                    helperText: _priceHelper(line),
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: (String? value) => _positive(value, 'price'),
                  // onChanged fires only for typing, never for the programmatic
                  // fill above, which is what keeps the two distinguishable.
                  onChanged: (_) => setState(() => line.priceEdited = true),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextFormField(
                  controller: line.discountPercent,
                  enabled: !_locked,
                  decoration: InputDecoration(
                    labelText: 'Discount %',
                    helperText: line.lastRate.isNotEmpty
                        ? lastPricedHelper(line.lastRate, line.lastSource)
                        : _customerDiscount.isEmpty
                            ? 'Blank takes the arrangement on file.'
                            : "Blank takes this customer's $_customerDiscount%.",
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: _percentage,
                  onChanged: (_) => setState(() {}),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: TextFormField(
                  controller: line.discountAmount,
                  enabled: !_locked,
                  decoration: const InputDecoration(
                    labelText: 'Discount amount',
                    helperText: 'Beats the percentage.',
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: (String? value) =>
                      _discountAmount(value, line.gross, 'the line'),
                  onChanged: (_) => setState(() {}),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Align(
            alignment: Alignment.centerRight,
            child: Text(
              'Line ${index + 1}: ${line.netOfDiscount.toStringAsFixed(2)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }

  Widget _dateField({
    required String label,
    required String value,
    required String helperText,
    required VoidCallback onPick,
    VoidCallback? onClear,
  }) =>
      InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
          helperMaxLines: 2,
        ),
        child: Row(
          children: [
            Expanded(child: Text(value, overflow: TextOverflow.ellipsis)),
            if (onClear != null)
              TextButton(
                onPressed: _locked ? null : onClear,
                child: const Text('Clear'),
              ),
            TextButton.icon(
              onPressed: _locked ? null : onPick,
              icon: const Icon(Icons.event, size: 18),
              label: const Text('Change'),
            ),
          ],
        ),
      );

  Widget _body(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_locked) ...[
                MaterialBanner(
                  // A notice, not a refusal: the theme colours banners as
                  // errors, and this one is the exception.
                  backgroundColor: Theme.of(
                    context,
                  ).colorScheme.surfaceContainerHighest,
                  contentTextStyle: Theme.of(context).textTheme.bodyMedium,
                  content: Text(
                    'This order is $_status, so it can no longer be rewritten. '
                    'Its lines are what stock and credit were committed '
                    'against.',
                  ),
                  actions: const [SizedBox.shrink()],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              if (_error != null) ...[
                MaterialBanner(
                  content: Text(_error!),
                  actions: [
                    TextButton(
                      onPressed: () => setState(() => _error = null),
                      child: const Text('Dismiss'),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
              ],
              const SectionHeader(
                title: 'Order',
                description: 'Who it is for, which branch takes it, and where '
                    'it will ship from.',
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 2,
                    child: _picker(
                      key: const ValueKey<String>('sales-order-customer'),
                      label: 'Customer',
                      value: _customerId,
                      options: <({String id, String label})>[
                        for (final Customer item in _customers)
                          (
                            id: item.id,
                            label: '${item.code} - ${item.displayName}',
                          ),
                      ],
                      // Fixed while correcting: an order for a different shop is
                      // a different order, and its credit was checked against
                      // this one.
                      onChanged: _editing
                          ? (String? value) {}
                          : (String? value) {
                              setState(() => _customerId = value);
                              unawaited(_quotePrices(_lines));
                            },
                      emptyMessage: 'Choose a customer.',
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    flex: 2,
                    child: _optionalPicker(
                      key: const ValueKey<String>('sales-order-salesman'),
                      label: 'Salesman',
                      blankLabel: 'Nobody',
                      helperText: 'Who took the order. Left blank, the '
                          "customer's round supplies one where they are on a "
                          'round; otherwise what this order collects earns '
                          'nobody commission.',
                      value: _salesmanId,
                      options: <({String id, String label})>[
                        for (final FirmMember item in _members)
                          (id: item.userId, label: item.label),
                      ],
                      onChanged: (String? value) =>
                          setState(() => _salesmanId = value),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _picker(
                      key: const ValueKey<String>('sales-order-branch'),
                      label: 'Branch',
                      value: _branchId,
                      options: <({String id, String label})>[
                        for (final BranchRecord item in _branches)
                          (
                            id: item.id,
                            label: '${item.code} - ${item.displayName}',
                          ),
                      ],
                      onChanged: (String? value) => setState(() {
                        _branchId = value;
                        _warehouseId = _warehouseFor(value);
                      }),
                      emptyMessage: 'Choose a branch.',
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    // Rebuilt when the branch changes, so the field shows the
                    // warehouse the branch change chose rather than its first.
                    child: KeyedSubtree(
                      key: ValueKey<String>(
                        'sales-order-warehouse-of-${_branchId ?? ''}',
                      ),
                      child: _picker(
                        key: const ValueKey<String>('sales-order-warehouse'),
                        label: 'Ships from',
                        helperText: 'Stock is committed here on approval.',
                        value: _warehouseId,
                        options: <({String id, String label})>[
                          for (final WarehouseRecord item in _warehouses)
                            (
                              id: item.id,
                              label: '${item.code} - ${item.displayName}',
                            ),
                        ],
                        onChanged: (String? value) =>
                            setState(() => _warehouseId = value),
                        emptyMessage: 'Choose a warehouse.',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _dateField(
                      label: 'Order taken on',
                      value: _iso(_orderDate),
                      helperText: 'The date the rules and rates are read at.',
                      onPick: _pickOrderDate,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: _dateField(
                      label: 'Wanted by',
                      value: _deliveryDate == null
                          ? 'Not promised'
                          : _iso(_deliveryDate!),
                      helperText: 'Optional. Nothing is scheduled from it.',
                      onPick: _pickDeliveryDate,
                      onClear: _deliveryDate == null
                          ? null
                          : () => setState(() => _deliveryDate = null),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _customerReference,
                      enabled: !_locked,
                      decoration: const InputDecoration(
                        labelText: "Customer's reference",
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      controller: _reference,
                      enabled: !_locked,
                      decoration:
                          const InputDecoration(labelText: 'Our reference'),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      controller: _coupon,
                      enabled: !_locked,
                      decoration: const InputDecoration(
                        labelText: 'Coupon',
                        // A code that matches nothing leaves the order saveable
                        // and simply gives no benefit -- worth saying, so a typo
                        // is not mistaken for a broken offer.
                        helperText: 'Unrecognised codes are ignored',
                        helperMaxLines: 2,
                      ),
                      textCapitalization: TextCapitalization.characters,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              const SectionHeader(
                title: 'What was ordered',
                description: 'A price starts at what the product lists at and '
                    'stays as it is typed.',
              ),
              const SizedBox(height: AppSpacing.md),
              for (int index = 0; index < _lines.length; index += 1)
                _lineEditor(index),
              for (final Json free in _offerFreeShown)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(
                    '${_offerFreeWords(free)}  (given by the offer)',
                    key: const ValueKey('sales-order-offer-free-note'),
                  ),
                ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _locked ? null : _addLine,
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add line'),
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              // Below the lines and above the total, because it is a deal
              // struck on the whole order rather than a property of any line.
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _billDiscountPercent,
                      enabled: !_locked,
                      decoration: const InputDecoration(
                        labelText: 'Discount on the whole order %',
                        helperText:
                            'Comes off what the lines discounted to, and '
                            'the tax falls with it.',
                        helperMaxLines: 2,
                      ),
                      keyboardType: TextInputType.number,
                      validator: _percentage,
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      controller: _billDiscountAmount,
                      enabled: !_locked,
                      decoration: InputDecoration(
                        labelText: 'Discount on the whole order',
                        helperText: _billResolvedHelper.isNotEmpty &&
                                _billDiscountAmount.text.trim().isEmpty
                            ? _billResolvedHelper
                            : 'A flat figure. Beats the percentage.',
                        helperMaxLines: 2,
                      ),
                      keyboardType: TextInputType.number,
                      validator: (String? value) => _discountAmount(
                        value,
                        _lines.fold<double>(
                          0,
                          (double running, _LineDraft line) =>
                              running + line.netOfDiscount,
                        ),
                        'the order',
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: TextFormField(
                      controller: _freightAmount,
                      enabled: !_locked,
                      decoration: const InputDecoration(
                        labelText: 'Delivery charge',
                        // Said plainly, because it is the opposite of what the
                        // field beside it does and the difference decides the
                        // tax.
                        helperText: 'Split across the lines and taxed with '
                            'them.',
                        helperMaxLines: 2,
                      ),
                      keyboardType: TextInputType.number,
                      onChanged: (_) => setState(() {}),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Ordered before tax: ${_beforeTax.toStringAsFixed(2)}. Tax is '
                'worked out by the server at the rate in force.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _remarks,
                enabled: !_locked,
                decoration: const InputDecoration(labelText: 'Remarks'),
                maxLines: 2,
              ),
              AdditionalDetailsSection(
                controller: _customFields,
                noun: 'sales orders',
                readOnly: _locked,
              ),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    // Phase 2: the one-screen order (the quotation's approved layout).
    if (Phase2Scope.of(context)) return _phase2Page(context);
    final ThemeData theme = Theme.of(context);
    final bool nothingToOrder =
        !_loading && (_customers.isEmpty || _products.isEmpty) && !_editing;
    return WorkspaceDialog(
      title: _editing ? 'Edit draft order' : 'New sales order',
      subtitle: _editing
          ? 'Correcting a draft. Only a draft can be rewritten.'
          : 'Taken over the counter or the phone, without a quotation first.',
      icon: Icons.receipt_long_outlined,
      loading: _loading || _saving,
      onClose: () => Navigator.of(context).pop(false),
      saveLabel: _editing ? 'Save order' : 'Create draft',
      onSave: _locked || nothingToOrder ? null : _save,
      // WorkspaceDialog drops its whole footer when there is nothing to save,
      // which would leave a locked order with no way out but Escape.
      footer: _locked || nothingToOrder
          ? Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    child: const Text('Close'),
                  ),
                ],
              ),
            )
          : null,
      body: _loading
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.xxl),
                child: CircularProgressIndicator(),
              ),
            )
          : nothingToOrder
              ? const StandardEmptyState(
                  type: EmptyStateType.noRecords,
                  title: 'Nothing to order yet',
                  message: 'An order needs a customer to take it from and a '
                      'product to sell.',
                )
              : _body(theme),
    );
  }
}
