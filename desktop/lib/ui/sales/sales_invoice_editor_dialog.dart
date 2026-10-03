import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_client.dart';
import '../../core/api/concurrency.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/batch_sale_settings.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';
import '../../models/customer.dart';
import '../../models/product.dart';
import '../../models/sales_invoice.dart';
import '../../models/document_preview.dart';
import '../../models/line_tax_rule.dart';
import '../../phase2/document_page.dart';
import '../../phase2/indian_format.dart';
import '../../phase2/source_tick_dialog.dart';
import '../workspace/batch_picker_panel.dart';
import '../workspace/custom_fields_section.dart';
import '../workspace/desktop_framework.dart';
import '../workspace/printed_document.dart';
import 'ship_to_field.dart';

part 'sales_invoice_editor_phase2.dart';

/// Billing a delivery note.
///
/// Until this existed a firm using only the desktop could quote, order and
/// dispatch — and then had no way to raise the invoice. `POST /sales-invoices`
/// had worked all along and `SALES_INVOICE_CREATE` was seeded with no screen
/// checking it, so the authority was modelled and the capability was not
/// reachable. It also meant the invoice print feature had nothing to print.
///
/// The picker offers only documents with something left to bill, which the
/// server works out: a client cannot know how much of a delivery line earlier
/// invoices already took, and one that guessed would offer paperwork the save
/// then refuses.
class SalesInvoiceEditorDialog extends StatefulWidget {
  const SalesInvoiceEditorDialog({
    super.key,
    required this.api,
    required this.today,
    this.invoiceId,
    this.mayApprove = false,
    this.printer,
  });

  final ApiClient api;

  /// Passed in rather than read here, so the dialog is testable.
  final DateTime today;

  /// The draft being corrected, or null to raise a new one.
  ///
  /// A draft could only be cancelled and re-raised before this: `PUT
  /// /api/v1/sales-invoices/{id}` existed and nothing in the desktop called
  /// it, so a mistyped quantity cost the document.
  final String? invoiceId;

  /// Whether the signed-in user holds SALES_APPROVE: F9 at the counter
  /// approves the bill it saved only when they do (SEL-12).
  final bool mayApprove;

  /// Hands a rendered receipt to the printer; null uses the system print
  /// dialog. Passed in so the counter flow is testable.
  final Future<void> Function(
    BuildContext context,
    List<int> bytes,
    String documentName,
  )? printer;

  @override
  State<SalesInvoiceEditorDialog> createState() =>
      _SalesInvoiceEditorDialogState();
}

class _SalesInvoiceEditorDialogState extends State<SalesInvoiceEditorDialog> {
  final GlobalKey<FormState> _form = GlobalKey<FormState>();
  final TextEditingController _reference = TextEditingController();

  /// The firm's own fields on a sales invoice (MST-6), sent only once the
  /// definitions arrived.
  late final CustomFieldsController _customFields = CustomFieldsController(
    load: () => widget.api.applicableAttributeDefinitions('SALES_INVOICE'),
  );

  /// The `attributes` key, or nothing while the definitions are unread:
  /// absent leaves the stored values alone, an empty list clears them.
  Map<String, dynamic> _attributeFields() => _customFields.hasFields
      ? <String, dynamic>{'attributes': _customFields.payload()}
      : const <String, dynamic>{};

  /// A coupon the customer presents, on a bill that names products. Only a
  /// new direct bill takes one: the server refuses a coupon on a bill whose
  /// lines name documents, because those were priced when they were raised.
  final TextEditingController _coupon = TextEditingController();
  final TextEditingController _billDiscount = TextEditingController();
  final TextEditingController _freight = TextEditingController();

  /// Money taken at the counter as the bill is made (phase 2). Recorded as a
  /// receipt by the server when the bill is approved.
  final TextEditingController _receivedNow = TextEditingController();
  final TextEditingController _receivedRef = TextEditingController();
  String _receivedMethod = 'CASH';

  /// SEL-12: the counter payment split by how it was paid. Used only once
  /// the person opens the split; otherwise the single amount above is sent
  /// exactly as before.
  bool _splitTender = false;

  /// Whether the draft being edited already carries tenders, so that turning
  /// the split off sends an empty list to clear them.
  bool _hadTenders = false;
  final List<_TenderRow> _tenders = <_TenderRow>[];

  /// SEL-12: the scan field above a counter bill's lines.
  final TextEditingController _scan = TextEditingController();
  final FocusNode _scanFocus = FocusNode();
  String? _scanMessage;

  /// Set once a counter bill has been created by F9 and a later step was
  /// refused: the screen then carries on with that saved draft rather than
  /// creating a second one.
  String? _draftId;

  /// Phase 2, backlog 64 row 4: whether the rates typed on this bill include
  /// GST. A new bill starts from the firm's setting; a draft keeps its own.
  bool _rateIncludesTax = false;

  /// Backlog 79 row 7: the firm takes a counter line's rate from its batch's
  /// selling price. Read once on opening; unreadable means off.
  bool _priceFromBatch = false;

  /// The rate as typed, GST included, of each line of a draft that was
  /// typed so, by source line: what the Rate column shows back.
  final Map<String, String> _enteredRates = <String, String>{};
  final Map<String, TextEditingController> _quantities =
      <String, TextEditingController>{};

  List<BillableDocument> _billable = const [];
  BillableDocument? _document;

  /// Further delivery notes of the same customer and branch billed on this
  /// one invoice (D-SELL-39). [_document] stays the primary one; phase 1
  /// only ever uses that.
  final List<BillableDocument> _extraDocuments = <BillableDocument>[];

  /// Phase 2: the customer chosen before any note is ticked (SEL-1).
  String? _billCustomerId;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  /// Phase 2: the bill as the server priced it last, and the line the side
  /// panel follows.
  SalesInvoicePreviewRecord? _preview;
  int _current = 0;
  Timer? _previewTimer;
  int _previewSerial = 0;
  bool _phase2 = false;

  /// Set while building a payload only to price it: the form is not asked to
  /// show its errors for a bill still being typed.
  bool _drafting = false;

  void _setState(VoidCallback change) => setState(change);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _phase2 = Phase2Scope.of(context);
  }

  /// Price the bill again once the typing pauses; only the latest answer
  /// lands.
  void _schedulePreview() {
    if (!_phase2) return;
    _previewTimer?.cancel();
    _previewTimer = Timer(const Duration(milliseconds: 350), () async {
      Json? draft;
      _drafting = true;
      try {
        draft = _payload();
      } finally {
        _drafting = false;
      }
      if (draft == null || !mounted) return;
      final int serial = ++_previewSerial;
      try {
        final SalesInvoicePreviewRecord priced =
            await widget.api.previewSalesInvoice(draft);
        if (!mounted || serial != _previewSerial) return;
        setState(() => _preview = priced);
      } on ApiException {
        // A bill the server refuses as it stands -- serials not yet picked,
        // a quantity past what is left -- keeps the last figures.
      }
    });
  }

  /// The draft as it was read, when correcting one.
  Json? _existing;

  /// How much of each source line this draft already bills. In edit mode the
  /// ceiling is that plus whatever is still unbilled elsewhere, because the
  /// draft's own quantity is counted against the source line and would
  /// otherwise be subtracted from the number the user is allowed to keep.
  final Map<String, double> _ownQuantities = <String, double>{};

  String? get _invoiceId => _draftId ?? widget.invoiceId;

  bool get _editing => _invoiceId != null;

  /// Which stages this firm types. A firm that types neither the order nor the
  /// delivery note has nothing to pick from, so it names products instead and
  /// the server raises the documents behind the bill.
  SalesWorkflowSettings _stages = SalesWorkflowSettings.wholeChain;
  bool get _direct => _stages.billsDirectly && !_editing;

  List<Customer> _customers = const [];
  List<Product> _products = const [];
  String? _customerId;

  /// Where the bill says the goods went (backlog 67 row 3). Null is "as
  /// delivered": the server takes it from the notes billed, else from the
  /// order a counter bill raises, else the customer's default.
  String? _shipToId;

  /// The addresses of the customers a bill of documents is for, read on
  /// their own because that mode loads no customer list.
  final Map<String, List<CustomerAddress>> _addressesOf =
      <String, List<CustomerAddress>>{};

  /// The addresses the Ship to box offers, for the bill's customer.
  List<CustomerAddress> get _shipToAddresses {
    final String? id = _direct ? _customerId : _document?.customerId;
    if (id == null) return const <CustomerAddress>[];
    for (final Customer item in _customers) {
      if (item.id == id) return item.addresses;
    }
    return _addressesOf[id] ?? const <CustomerAddress>[];
  }

  /// Read one customer's addresses for the picker. A courtesy: without them
  /// the box is left out and the server decides, as it always did.
  Future<void> _loadAddresses(String customerId) async {
    if (customerId.isEmpty || _addressesOf.containsKey(customerId)) return;
    try {
      final Customer customer = await widget.api.customer(customerId);
      if (!mounted) return;
      setState(() => _addressesOf[customerId] = customer.addresses);
    } on Object {
      // No picker; the server inherits the address.
    }
  }
  final List<_DirectLine> _directLines = <_DirectLine>[_DirectLine()];

  /// The serials picked for a document line, keyed by its source line id.
  /// Direct lines carry their own on [_DirectLine.serialIds].
  final Map<String, List<String>> _pickedSerials = <String, List<String>>{};

  /// The batches chosen for a document line, by its source line id (backlog
  /// 79 row 2): only where the bill dispatches its own goods. Absent means
  /// nobody chose, and nothing is sent.
  final Map<String, Map<String, double>> _batchPicks =
      <String, Map<String, double>>{};

  /// AVAILABLE serials of each serial-tracked product, keyed by product and
  /// warehouse: what the bill picks from when it ships its own goods.
  final Map<String, List<SerialRecord>> _serialsOnShelf =
      <String, List<SerialRecord>>{};

  @override
  void initState() {
    super.initState();
    _load();
    _readBatchRules();
  }

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
    _reference.dispose();
    _coupon.dispose();
    _billDiscount.dispose();
    _freight.dispose();
    _receivedNow.dispose();
    _receivedRef.dispose();
    _scan.dispose();
    _scanFocus.dispose();
    for (final _TenderRow row in _tenders) {
      row.dispose();
    }
    for (final TextEditingController controller in _quantities.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      // Fail open to the whole chain: an unreadable setting must leave the
      // dialog working the way it always has, not strand the user in a mode
      // their firm does not use.
      SalesWorkflowSettings stages = SalesWorkflowSettings.wholeChain;
      try {
        stages = await widget.api.salesWorkflowSettings();
      } on ApiException {
        stages = SalesWorkflowSettings.wholeChain;
      }
      final bool direct = stages.billsDirectly && _invoiceId == null;
      final List<BillableDocument> rows =
          direct ? const [] : await widget.api.billableDocuments();
      // Every customer and product, not the first hundred by name: a counter
      // sale to a customer past it could not be billed (D-SELL-18).
      final List<Customer> customers = direct
          ? await fetchAllPages<Customer>(
              (int page) => widget.api.customers(
                page: page,
                pageSize: maxApiPageSize,
                sortBy: 'name',
                descending: false,
              ),
            )
          : const [];
      // An edit of a counter bill reads them too: which lines are
      // batch-tracked decides whether its picker is offered.
      final bool wantProducts =
          direct || (_invoiceId != null && stages.billsDirectly);
      List<Product> products = const [];
      if (wantProducts) {
        try {
          products = await fetchAllPages<Product>(
            (int page) => widget.api.products(
              page: page,
              pageSize: maxApiPageSize,
              sortBy: 'name',
              descending: false,
            ),
          );
        } on Object {
          // A bill of products cannot be raised without them; an edit just
          // goes without the batch picker.
          if (direct) rethrow;
        }
      }
      final String? id = _invoiceId;
      final Json? existing =
          id == null ? null : _unwrap(await widget.api.salesInvoice(id));
      if (!mounted) return;
      setState(() {
        _stages = stages;
        if (existing == null) _rateIncludesTax = stages.rateIncludesTax;
        _customers = customers;
        _products = products;
        _billable = rows;
        _existing = existing;
        _loading = false;
        if (existing != null) {
          _adoptExisting(existing);
        } else if (rows.length == 1) {
          _choose(rows.first);
        }
      });
      // After the invoice, so a correction opens with its stored values.
      unawaited(_customFields.start());
      _schedulePreview();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  Json _unwrap(Json response) {
    final dynamic data = response['data'];
    return data is Map ? Map<String, dynamic>.from(data) : response;
  }

  /// Build the form from a draft that already exists.
  ///
  /// Its lines are the truth about what it bills; the billable list only
  /// contributes how much *more* of each source line is available, so a
  /// correction can go up as well as down.
  void _adoptExisting(Json invoice) {
    _customFields.seed(attributeValuesFrom(invoice['attributes']));
    final List<dynamic> lines =
        invoice['lines'] is List ? invoice['lines'] as List : const [];
    if (lines.isEmpty) return;
    // A bill can carry lines of several notes (D-SELL-39): group them by the
    // document they continue. The first group is the primary document, the
    // rest are the ones billed beside it.
    final Map<String, List<Json>> groups = <String, List<Json>>{};
    for (final dynamic raw in lines) {
      final Json line = Map<String, dynamic>.from(raw as Map);
      groups
          .putIfAbsent('${line['source_document_id'] ?? ''}', () => <Json>[])
          .add(line);
    }
    final List<BillableDocument> rebuilt = <BillableDocument>[
      for (final MapEntry<String, List<Json>> group in groups.entries)
        _rebuildDocument(invoice, group.key, group.value),
    ];
    _document = rebuilt.first;
    _shipToId = _blankToNull('${invoice['shipping_address_id'] ?? ''}');
    unawaited(_loadAddresses(rebuilt.first.customerId));
    _extraDocuments
      ..clear()
      ..addAll(rebuilt.skip(1));
    for (final BillableDocument document in rebuilt) {
      for (final BillableLine line in document.lines) {
        _quantities[line.sourceDocumentLineId] = TextEditingController(
          text: '${_ownQuantities[line.sourceDocumentLineId] ?? 0}',
        );
        if (line.trackSerial) _loadSerials(line.productId, line.warehouseId);
      }
    }
    final double bill =
        double.tryParse('${invoice['bill_discount_percent'] ?? 0}') ?? 0;
    if (bill > 0) _billDiscount.text = '${invoice['bill_discount_percent']}';
    _reference.text = '${invoice['reference_number'] ?? ''}';
    final double received =
        double.tryParse('${invoice['received_now_amount'] ?? 0}') ?? 0;
    if (received > 0) _receivedNow.text = '${invoice['received_now_amount']}';
    _receivedMethod = '${invoice['received_now_method']}' == 'BANK'
        ? 'BANK'
        : 'CASH';
    _receivedRef.text = '${invoice['received_now_reference'] ?? ''}';
    for (final _TenderRow row in _tenders) {
      row.dispose();
    }
    _tenders.clear();
    for (final dynamic item
        in (invoice['received_now_tenders'] as List?) ?? const []) {
      if (item is! Map) continue;
      _tenders.add(_TenderRow(
        mode: '${item['mode']}',
        amount: '${item['amount']}',
        reference: '${item['reference'] ?? ''}',
      ));
    }
    _hadTenders = _tenders.isNotEmpty;
    _splitTender = _hadTenders;
    _rateIncludesTax = invoice['rate_includes_tax'] == true;
  }

  /// What the counter took, sent on every save from the phase 2 bill: an
  /// omitted field is left alone by an update, so a cleared box must say 0.
  Map<String, dynamic> _receivedFields() {
    if (!_phase2) return const <String, dynamic>{};
    if (_splitTender) {
      return <String, dynamic>{'received_now_tenders': _tendersPayload()};
    }
    final String typed = _receivedNow.text.trim();
    final double amount = double.tryParse(typed) ?? 0;
    if (typed.isNotEmpty && double.tryParse(typed) == null) {
      return const <String, dynamic>{};
    }
    if (amount < 0) return const <String, dynamic>{};
    return <String, dynamic>{
      // A draft that held tenders and has been put back to one amount must
      // say so: an absent list leaves the tenders alone.
      if (_hadTenders) 'received_now_tenders': const <Json>[],
      'received_now_amount': amount > 0 ? typed : '0',
      if (amount > 0) 'received_now_method': _receivedMethod,
      if (amount > 0 &&
          _receivedMethod == 'BANK' &&
          _receivedRef.text.trim().isNotEmpty)
        'received_now_reference': _receivedRef.text.trim(),
    };
  }

  /// The tenders as the server takes them. Cash is sent as what the bill
  /// still needs after the other modes -- never more than the bill, because
  /// change is handed back and is not a receipt.
  List<Json> _tendersPayload() {
    final double total = _billTotal;
    double nonCash = 0;
    for (final _TenderRow row in _tenders) {
      if (row.mode != 'CASH') nonCash += row.value;
    }
    double room = total > 0 ? (total - nonCash) : double.infinity;
    if (room < 0) room = 0;
    final List<Json> sent = <Json>[];
    for (final _TenderRow row in _tenders) {
      double amount = row.value;
      if (amount <= 0) continue;
      String text = row.amount.text.trim();
      if (row.mode == 'CASH') {
        if (amount > room) amount = room;
        room -= amount;
        if (amount <= 0) continue;
        if (amount != row.value) text = amount.toStringAsFixed(2);
      }
      final String reference = row.reference.text.trim();
      sent.add(<String, dynamic>{
        'mode': row.mode,
        'amount': text,
        if (reference.isNotEmpty) 'reference': reference,
      });
    }
    return sent;
  }

  /// Cash handed over beyond what the bill needed: the change to give back.
  double get _changeToGive {
    if (_billTotal <= 0) return 0;
    double typedCash = 0;
    double sentCash = 0;
    for (final _TenderRow row in _tenders) {
      if (row.mode == 'CASH') typedCash += row.value;
    }
    for (final Json tender in _tendersPayload()) {
      if (tender['mode'] == 'CASH') {
        sentCash += double.tryParse('${tender['amount']}') ?? 0;
      }
    }
    final double change = typedCash - sentCash;
    return change > 0.004 ? change : 0;
  }

  /// One source document of a draft, rebuilt from the draft's own lines.
  BillableDocument _rebuildDocument(
    Json invoice,
    String sourceId,
    List<Json> lines,
  ) {
    final Json first = lines.first;
    final Iterable<BillableDocument> matching =
        _billable.where((item) => item.sourceDocumentId == sourceId);
    final List<BillableLine> extra =
        matching.isEmpty ? const [] : matching.first.lines;

    final List<BillableLine> rebuilt = <BillableLine>[];
    for (final Json line in lines) {
      final String lineId = '${line['source_document_line_id'] ?? ''}';
      final String entered = stringValue(line['entered_rate']);
      if (entered.isNotEmpty) _enteredRates[lineId] = entered;
      final double own =
          double.tryParse('${line['current_invoice_quantity'] ?? 0}') ?? 0;
      _ownQuantities[lineId] = own;
      final Iterable<BillableLine> still =
          extra.where((item) => item.sourceDocumentLineId == lineId);
      final double elsewhere = still.isEmpty
          ? 0
          : (double.tryParse(still.first.remainingQuantity) ?? 0);
      // A serial-tracked line billing the note this bill raised for itself:
      // the bill names its units, so the picker comes back with the units
      // the note will ship already ticked (D-SELL-33).
      final bool picks = line['picks_serials'] == true;
      if (picks) {
        _pickedSerials[lineId] = <String>[
          for (final dynamic raw in (line['serials'] as List?) ?? const [])
            if (raw is Map) '${raw['serial_id'] ?? ''}',
        ];
      }
      // The batches the note line takes, chosen or shipped (backlog 79).
      final Map<String, double> taken = <String, double>{
        for (final dynamic raw in (line['batches'] as List?) ?? const [])
          if (raw is Map)
            '${raw['batch_id'] ?? ''}':
                double.tryParse('${raw['quantity'] ?? 0}') ?? 0,
      };
      if (taken.isNotEmpty) _batchPicks[lineId] = taken;
      rebuilt.add(BillableLine(
        sourceDocumentLineId: lineId,
        lineNumber: (line['line_number'] as num?)?.toInt() ?? 0,
        productId: '${line['product_id'] ?? ''}',
        warehouseId: '${line['warehouse_id'] ?? ''}',
        trackSerial: picks,
        description: '${line['description'] ?? ''}',
        sourceQuantity: '${line['delivered_quantity'] ?? own}',
        alreadyInvoicedQuantity: '0',
        // What this draft may keep, plus anything still unbilled.
        remainingQuantity: '${own + elsewhere}',
        unitPrice: '${line['unit_price'] ?? '0'}',
        discountPercent: '${line['discount_percent'] ?? '0'}',
      ));
    }

    return BillableDocument(
      sourceDocumentType: '${first['source_document_type'] ?? 'DELIVERY_NOTE'}',
      sourceDocumentId: sourceId,
      sourceDocumentNumber: '${first['source_document_number'] ?? ''}',
      documentDate: '${invoice['invoice_date'] ?? ''}',
      customerId: '${invoice['customer_id'] ?? ''}',
      customerName: '${invoice['customer_name'] ?? ''}',
      branchId: '${invoice['branch_id'] ?? ''}',
      lines: rebuilt,
    );
  }

  /// Take a document and give each of its lines a quantity box.
  ///
  /// Defaulted to what is left rather than to what was dispatched: billing the
  /// remainder is the ordinary act, and the number is one the save accepts.
  void _choose(BillableDocument document) {
    for (final TextEditingController controller in _quantities.values) {
      controller.dispose();
    }
    _quantities.clear();
    _pickedSerials.clear();
    // A different primary note is a different bill: the notes added beside
    // the last one do not follow it.
    _extraDocuments.clear();
    for (final BillableLine line in document.lines) {
      _quantities[line.sourceDocumentLineId] =
          TextEditingController(text: line.remainingQuantity);
      if (_picksSerials(document, line)) {
        _loadSerials(line.productId, line.warehouseId);
      }
    }
    _document = document;
    // A different note may be for a different customer, so the chosen
    // address goes back to "as delivered".
    _shipToId = null;
    unawaited(_loadAddresses(document.customerId));
  }

  String? _blankToNull(String value) => value.isEmpty ? null : value;

  /// Every document on the bill: the primary one, then those added.
  List<BillableDocument> get _documents => [
        if (_document != null) _document!,
        ..._extraDocuments,
      ];

  /// The customers with something waiting to be billed, in the order their
  /// newest note arrives (SEL-1: the customer is chosen first).
  List<BillableDocument> get _billableCustomers {
    final Map<String, BillableDocument> byCustomer =
        <String, BillableDocument>{};
    for (final BillableDocument item in _billable) {
      byCustomer.putIfAbsent(item.customerId, () => item);
    }
    final List<BillableDocument> rows = byCustomer.values.toList()
      ..sort((a, b) => a.customerName.compareTo(b.customerName));
    return rows;
  }

  /// The customer whose notes the tick list offers: the one chosen, or the
  /// one the bill's notes belong to.
  String? get _tickCustomerId => _document?.customerId ?? _billCustomerId;

  /// That customer's notes with something left to bill, plus any already on
  /// the bill (a draft's own notes may be billed in full elsewhere in it).
  List<BillableDocument> get _customerNotes {
    final String? customer = _tickCustomerId;
    if (customer == null) return const [];
    final Map<String, BillableDocument> byId = <String, BillableDocument>{
      for (final BillableDocument item in _documents)
        item.sourceDocumentId: item,
    };
    for (final BillableDocument item in _billable) {
      if (item.customerId == customer) {
        byId.putIfAbsent(item.sourceDocumentId, () => item);
      }
    }
    return byId.values.toList();
  }

  /// Why [candidate] cannot share a bill with [ticked], naming the field and
  /// the note it clashes with, or null where it can (SEL-1, backlog 58 item
  /// 4). The server's rule, asked before the save: one branch, and at most
  /// one salesman, territory and route among the notes that name one.
  String? _noteClash(BillableDocument candidate, List<BillableDocument> ticked) {
    for (final BillableDocument other in ticked) {
      final String number = other.sourceDocumentNumber;
      if (candidate.branchId != other.branchId) {
        return 'Another branch: ${_named(candidate.branchName, 'this one')}'
            ' here, ${_named(other.branchName, 'another')} on $number';
      }
      if (candidate.salesmanId.isNotEmpty &&
          other.salesmanId.isNotEmpty &&
          candidate.salesmanId != other.salesmanId) {
        return 'Another salesman: ${_named(candidate.salesmanName, 'one')}'
            ' here, ${_named(other.salesmanName, 'another')} on $number';
      }
      if (candidate.territoryId.isNotEmpty &&
          other.territoryId.isNotEmpty &&
          candidate.territoryId != other.territoryId) {
        return 'Another territory: ${_named(candidate.territoryName, 'one')}'
            ' here, ${_named(other.territoryName, 'another')} on $number';
      }
      if (candidate.routeId.isNotEmpty &&
          other.routeId.isNotEmpty &&
          candidate.routeId != other.routeId) {
        return 'Another route: ${_named(candidate.routeName, 'one')}'
            ' here, ${_named(other.routeName, 'another')} on $number';
      }
    }
    return null;
  }

  String _named(String name, String fallback) =>
      name.isEmpty ? fallback : name;

  /// Put exactly [picked] on the bill, in that order: the first is the
  /// primary note. Quantities already typed on a note that stays are kept;
  /// a note coming on starts at what is left of each line.
  void _setDocuments(List<BillableDocument> picked) {
    final Set<String> keep = {
      for (final BillableDocument item in picked) item.sourceDocumentId,
    };
    for (final BillableDocument document in _documents) {
      if (keep.contains(document.sourceDocumentId)) continue;
      for (final BillableLine line in document.lines) {
        _quantities.remove(line.sourceDocumentLineId)?.dispose();
        _pickedSerials.remove(line.sourceDocumentLineId);
      }
    }
    final Set<String> had = {
      for (final BillableDocument item in _documents) item.sourceDocumentId,
    };
    for (final BillableDocument document in picked) {
      if (had.contains(document.sourceDocumentId)) continue;
      for (final BillableLine line in document.lines) {
        _quantities[line.sourceDocumentLineId]?.dispose();
        _quantities[line.sourceDocumentLineId] =
            TextEditingController(text: line.remainingQuantity);
        if (_picksSerials(document, line)) {
          _loadSerials(line.productId, line.warehouseId);
        }
      }
    }
    final String? before = _document?.customerId;
    _document = picked.isEmpty ? null : picked.first;
    _extraDocuments
      ..clear()
      ..addAll(picked.skip(1));
    _current = 0;
    final String? after = _document?.customerId;
    if (after != null && after != before) {
      _shipToId = null;
      unawaited(_loadAddresses(after));
    }
  }

  double _quantityOf(BillableLine line) =>
      double.tryParse(_quantities[line.sourceDocumentLineId]?.text.trim() ?? '') ??
      0;

  /// What the invoice comes to before tax, after both discounts.
  double get _beforeTax {
    double lines = 0;
    for (final BillableDocument document in _documents) {
      for (final BillableLine line in document.lines) {
        final double gross =
            _quantityOf(line) * (double.tryParse(line.unitPrice) ?? 0);
        final double rate = double.tryParse(line.discountPercent) ?? 0;
        lines += gross * (1 - rate / 100);
      }
    }
    final double bill = double.tryParse(_billDiscount.text.trim()) ?? 0;
    return bill <= 0 ? lines : lines * (1 - bill / 100);
  }

  /// The documents the picker may offer, one entry per source document.
  ///
  /// A fully billed source is absent from the billable list, so editing its
  /// draft needs it added back — and deduped by id rather than by object,
  /// because the chosen document and its billable twin are different
  /// instances of the same thing and `DropdownButtonFormField` asserts when
  /// two items carry one value.
  List<BillableDocument> get _pickable {
    final Map<String, BillableDocument> byId = <String, BillableDocument>{
      for (final BillableDocument item in _billable) item.sourceDocumentId: item,
    };
    final BillableDocument? chosen = _document;
    if (chosen != null) byId.putIfAbsent(chosen.sourceDocumentId, () => chosen);
    return byId.values.toList();
  }

  String _iso(DateTime value) => value.toIso8601String().split('T').first;

  Json? _payload() {
    if (_direct) return _directPayload();
    final BillableDocument? document = _document;
    if (document == null) return null;
    if (!_drafting && !(_form.currentState?.validate() ?? false)) return null;
    final List<Json> lines = <Json>[];
    // Every note on the bill, numbered 1..n across all of them: the server
    // takes each line's own source and refuses sources that disagree.
    for (final BillableDocument source in _documents) {
      for (final BillableLine line in source.lines) {
        final String typed =
            _quantities[line.sourceDocumentLineId]?.text.trim() ?? '';
        // A line billed at nothing is left off entirely rather than sent as a
        // zero: the server would price and store it, and an invoice carrying
        // a line for nothing is one the customer queries.
        if (typed.isEmpty || (double.tryParse(typed) ?? 0) <= 0) continue;
        lines.add(<String, dynamic>{
          'source_document_type': source.sourceDocumentType,
          'source_document_id': source.sourceDocumentId,
          'source_document_line_id': line.sourceDocumentLineId,
          'line_number': lines.length + 1,
          'current_invoice_quantity': typed,
          'unit_price': line.unitPrice,
          if (_picksSerials(source, line))
            'serial_ids': [...?_pickedSerials[line.sourceDocumentLineId]],
          if (!_drafting &&
              _picksBatches(source, line) &&
              _batchPicks[line.sourceDocumentLineId] != null)
            'batches': _batchesPayload(_batchPicks[line.sourceDocumentLineId]!),
        });
      }
    }
    if (lines.isEmpty) return null;
    return <String, dynamic>{
      'customer_id': document.customerId,
      if (document.branchId.isNotEmpty) 'branch_id': document.branchId,
      'invoice_date': _iso(widget.today),
      // Null is "as delivered"; the key is sent in phase 2, which has the box.
      if (_phase2) 'shipping_address_id': _shipToId,
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      // Omitted when blank: absent is what tells the server there is no
      // discount on the bill, and an empty string is a schema error.
      if (_billDiscount.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscount.text.trim(),
      if (_freight.text.trim().isNotEmpty)
        'freight_amount': _freight.text.trim(),
      ..._receivedFields(),
      ..._attributeFields(),
      'lines': lines,
    };
  }

  /// A bill that names products rather than the paperwork behind them.
  ///
  /// The server raises the order and the delivery note as it saves, so what
  /// leaves the warehouse is still recorded on a delivery note and cost of
  /// goods sold still belongs to it.
  Json? _directPayload() {
    final String? customerId = _customerId;
    if (customerId == null) return null;
    if (!_drafting && !(_form.currentState?.validate() ?? false)) return null;
    final List<Json> lines = <Json>[];
    for (final _DirectLine line in _directLines) {
      final String product = line.productId ?? '';
      final String quantity = line.quantity.text.trim();
      if (product.isEmpty) continue;
      // A line billed at nothing is left off rather than sent as a zero, the
      // same rule the document path follows.
      if (quantity.isEmpty || (double.tryParse(quantity) ?? 0) <= 0) continue;
      final String price = line.price.text.trim();
      lines.add(<String, dynamic>{
        'product_id': product,
        'line_number': lines.length + 1,
        'current_invoice_quantity': quantity,
        // With GST included, blank is the product's own price -- before tax,
        // as the server resolves it -- rather than a typed shelf price.
        if (!(_rateIncludesTax && price.isEmpty))
          'unit_price': price.isEmpty ? '0' : price,
        // Omitted when blank on purpose. Saying nothing takes whatever
        // arrangement the customer already has; sending a zero refuses it.
        if (line.discount.text.trim().isNotEmpty)
          'discount_percent': line.discount.text.trim(),
        if (_isSerialised(product)) 'serial_ids': [...line.serialIds],
        // Only when the person chose or reset: absent leaves the note's own
        // earliest-expiry-first choice (backlog 79 row 2).
        if (!_drafting && _isBatched(product) && line.batchPicks != null)
          'batches': _batchesPayload(line.batchPicks!),
      });
    }
    if (lines.isEmpty) return null;
    return <String, dynamic>{
      'customer_id': customerId,
      'invoice_date': _iso(widget.today),
      // Sent on every bill of products: the phase 1 screen types rates
      // before tax, whatever the firm's default.
      'rate_includes_tax': _phase2 && _rateIncludesTax,
      if (_phase2) 'shipping_address_id': _shipToId,
      if (_reference.text.trim().isNotEmpty)
        'reference_number': _reference.text.trim(),
      // Omitted when blank: an empty string is a code that matches nothing,
      // not the absence of one. Never sent from the document path above.
      if (_coupon.text.trim().isNotEmpty) 'coupon_code': _coupon.text.trim(),
      if (_billDiscount.text.trim().isNotEmpty)
        'bill_discount_percent': _billDiscount.text.trim(),
      if (_freight.text.trim().isNotEmpty)
        'freight_amount': _freight.text.trim(),
      ..._receivedFields(),
      ..._attributeFields(),
      'lines': lines,
    };
  }

  /// Save the bill; with [print], hand the saved bill to the printer before
  /// the screen closes -- what a counter does with every bill.
  Future<void> _save({bool print = false}) async {
    final String? customField = _customFields.validate();
    if (customField != null) {
      setState(() => _error = customField);
      return;
    }
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = 'Bill at least one line.');
      return;
    }
    final String? short = _serialShortfall();
    if (short != null) {
      setState(() => _error = short);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final String? id = _invoiceId;
      final Json response;
      if (id == null) {
        response = await widget.api.createSalesInvoice(payload);
      } else {
        response = await widget.api.updateSalesInvoice(
          id,
          payload,
          expectedVersion: (_existing?['version'] as num?)?.toInt(),
        );
      }
      if (!mounted) return;
      if (print) {
        final dynamic saved = response['data'];
        final String savedId =
            saved is Map ? stringValue(saved['id']) : (id ?? '');
        final String number =
            saved is Map ? stringValue(saved['invoice_number']) : 'invoice';
        if (savedId.isNotEmpty) {
          try {
            final List<int>? pdf = await fetchPrintablePdf(
              context,
              ({bool referenceCopy = false}) => widget.api
                  .salesInvoicePdf(savedId, referenceCopy: referenceCopy),
            );
            if (pdf == null || !mounted) return;
            await printDocument(context, bytes: pdf, documentName: number);
          } on ApiException catch (error) {
            // Saved either way: the bill is there to print from the list.
            if (mounted) {
              NotificationService.show(
                context,
                'Saved, but it could not be printed: ${error.message}',
                kind: AppNotificationKind.warning,
              );
            }
          }
          if (!mounted) return;
        }
      }
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      // The server's sentence names what is wrong -- an over-billed line, a
      // closed period, a credit limit -- and is more use than anything this
      // dialog could invent.
      setState(() {
        _error =
            saveFailureMessage(error, 'invoice', changesKept: true);
        _saving = false;
      });
    }
  }

  // ── Counter billing (SEL-12) ───────────────────────────────────────────

  /// Give a direct line its product: the product's own price where nobody
  /// typed one, and its serials where it is serial-tracked.
  void _pickProduct(int index, String? value) {
    final _DirectLine line = _directLines[index];
    _setState(() {
      line.productId = value;
      // Units of the last product are not units of this one.
      line.serialIds.clear();
      line.batchPicks = null;
      // The product's selling price, where nobody typed one -- not on a bill
      // whose rates include GST: that price is before tax, and blank takes
      // it as such.
      if (line.price.text.trim().isEmpty && !_rateIncludesTax) {
        final Product? chosen = _product(value);
        final double price = double.tryParse(chosen?.sellingPrice ?? '') ?? 0;
        if (price > 0) {
          line.price.text = chosen!.sellingPrice;
          line.autoPrice = chosen.sellingPrice;
        }
      }
      _current = index;
    });
    if (value != null && _isSerialised(value)) {
      _loadSerials(value, _directWarehouse);
    }
    _schedulePreview();
  }

  /// Take what the scanner typed: a barcode, ending in Enter. A product
  /// already on the bill gains one; a new one gets a line of quantity 1.
  void _scanned(String raw) {
    final String code = raw.trim();
    _scan.clear();
    if (code.isEmpty) {
      _refocusScan();
      return;
    }
    final String wanted = code.toLowerCase();
    Product? found;
    for (final Product item in _products) {
      if (item.barcode.isNotEmpty && item.barcode.toLowerCase() == wanted) {
        found = item;
        break;
      }
    }
    if (found == null) {
      for (final Product item in _products) {
        if (item.code.toLowerCase() == wanted) {
          found = item;
          break;
        }
      }
    }
    if (found == null) {
      _setState(() => _scanMessage = 'No product has the barcode "$code".');
      _refocusScan();
      return;
    }
    final Product product = found;
    int index = _directLines.indexWhere((l) => l.productId == product.id);
    if (index >= 0) {
      final _DirectLine line = _directLines[index];
      final double next =
          (double.tryParse(line.quantity.text.trim()) ?? 0) + 1;
      _setState(() {
        line.quantity.text =
            next == next.roundToDouble() ? next.toStringAsFixed(0) : '$next';
        _current = index;
        _scanMessage = null;
      });
      _schedulePreview();
    } else {
      index = _directLines.indexWhere((l) => l.productId == null);
      _setState(() {
        if (index < 0) {
          _directLines.add(_DirectLine());
          index = _directLines.length - 1;
        }
        final _DirectLine line = _directLines[index];
        line.refresh++;
        line.quantity.text = '1';
        _scanMessage = null;
      });
      _pickProduct(index, product.id);
    }
    _refocusScan();
  }

  void _refocusScan() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _scanFocus.requestFocus();
    });
  }

  /// A fresh bill for the same counter: the customer stays, everything the
  /// last sale typed goes.
  void _newCounterBill() {
    _previewTimer?.cancel();
    _previewSerial++;
    _setState(() {
      _directLines
        ..clear()
        ..add(_DirectLine());
      _current = 0;
      _preview = null;
      _error = null;
      _scanMessage = null;
      _reference.clear();
      _coupon.clear();
      _billDiscount.clear();
      _freight.clear();
      _receivedNow.clear();
      _receivedRef.clear();
      _receivedMethod = 'CASH';
      _splitTender = false;
      _hadTenders = false;
      for (final _TenderRow row in _tenders) {
        row.dispose();
      }
      _tenders.clear();
      _saving = false;
    });
    _refocusScan();
  }

  /// F9: save, approve where the user may, print the receipt and open the
  /// next bill. A step the server refuses stops the run, shows its message
  /// and leaves the bill on screen.
  Future<void> _saveApprovePrint() async {
    final String? customField = _customFields.validate();
    if (customField != null) {
      setState(() => _error = customField);
      return;
    }
    final Json? payload = _payload();
    if (payload == null) {
      setState(() => _error = 'Bill at least one line.');
      return;
    }
    final String? short = _serialShortfall();
    if (short != null) {
      setState(() => _error = short);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final bool freshCounterBill = _direct && _invoiceId == null;
    String? savedId = _invoiceId;
    try {
      final Json response;
      if (savedId == null) {
        response = await widget.api.createSalesInvoice(payload);
      } else {
        response = await widget.api.updateSalesInvoice(
          savedId,
          payload,
          expectedVersion: (_existing?['version'] as num?)?.toInt(),
        );
      }
      final dynamic saved = response['data'];
      if (saved is Map && stringValue(saved['id']).isNotEmpty) {
        savedId = stringValue(saved['id']);
      }
      final String number =
          saved is Map ? stringValue(saved['invoice_number']) : 'invoice';
      final String status = saved is Map ? '${saved['status'] ?? ''}' : '';
      final String billId = savedId ?? '';
      if (billId.isEmpty) {
        throw const ApiException('The server did not return the saved bill.');
      }
      if (widget.mayApprove && status != 'APPROVED') {
        await widget.api.documentAction('sales-invoices', billId, '/approve');
      }
      if (!mounted) return;
      final List<int>? pdf = await fetchPrintablePdf(
        context,
        ({bool referenceCopy = false}) =>
            widget.api.salesInvoicePdf(billId, referenceCopy: referenceCopy),
      );
      if (!mounted) return;
      if (pdf != null) {
        final printer = widget.printer;
        if (printer != null) {
          await printer(context, pdf, number);
        } else {
          await printDocument(context, bytes: pdf, documentName: number);
        }
      }
      if (!mounted) return;
      if (freshCounterBill) {
        _newCounterBill();
      } else {
        Navigator.of(context).pop(true);
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      final String message =
          saveFailureMessage(error, 'invoice', changesKept: true);
      if (savedId != null && savedId != _invoiceId) {
        // The bill was saved before the refusal: carry on with that draft so
        // another F9 mends it rather than raising a second bill.
        setState(() {
          _draftId = savedId;
          _loading = true;
          _saving = false;
        });
        await _load();
        if (mounted) setState(() => _error = message);
      } else {
        setState(() {
          _error = message;
          _saving = false;
        });
      }
    }
  }

  // ── Serial numbers (D-STK-15) ──────────────────────────────────────────
  // A bill that dispatches its own goods -- the firm types no delivery note --
  // is the document that issues the stock, so it names the units going out,
  // one per unit, the way the delivery note editor does (D-STK-4). The server
  // refuses such a line without them. A bill of a note already dispatched
  // names none: the note picked them.

  bool _isSerialised(String productId) {
    for (final Product product in _products) {
      if (product.id == productId) return product.trackSerial;
    }
    return false;
  }

  /// Whether a document line is one this bill must name serials for.
  ///
  /// A new bill of an order names them; so does an edit of a draft whose line
  /// bills the note that draft raised, which the server marks by setting
  /// `picks_serials` -- the only way such a line gets [BillableLine.trackSerial]
  /// when editing (D-SELL-33).
  bool _picksSerials(BillableDocument document, BillableLine line) =>
      line.trackSerial &&
      (document.sourceDocumentType == 'SALES_ORDER' || _editing);

  /// Whether the product is tracked by batch and not by unit: the lines the
  /// batch picker is offered for.
  bool _isBatched(String productId) {
    for (final Product product in _products) {
      if (product.id == productId) {
        return product.trackBatch && !product.trackSerial;
      }
    }
    return false;
  }

  /// Whether a document line is one this bill may name batches for: only a
  /// draft counter bill editing the note it raised -- the server refuses
  /// batches on a note somebody else dispatched (backlog 79 row 2).
  bool _picksBatches(BillableDocument document, BillableLine line) =>
      _phase2 &&
      _editing &&
      _stages.billsDirectly &&
      document.sourceDocumentType == 'DELIVERY_NOTE' &&
      _isBatched(line.productId);

  /// The split as the server takes it: stock units, nothing for a batch
  /// given none, and an empty list for "back to earliest expiry".
  List<Json> _batchesPayload(Map<String, double> picks) => <Json>[
        for (final MapEntry<String, double> pick in picks.entries)
          if (pick.value > 0)
            <String, dynamic>{
              'batch_id': pick.key,
              'quantity': pick.value == pick.value.roundToDouble()
                  ? pick.value.toStringAsFixed(0)
                  : '${pick.value}',
            },
      ];

  /// Where a direct bill's goods leave from, when the firm has said.
  String get _directWarehouse => _stages.defaultWarehouseId ?? '';

  static String _shelfKey(String productId, String warehouseId) =>
      '$productId@$warehouseId';

  /// Read the AVAILABLE units of one product, once per product and shelf.
  ///
  /// With no warehouse named -- a direct bill whose firm set no default --
  /// every shelf's units are offered and the server refuses one that is not
  /// on the shelf the goods leave from, by name.
  Future<void> _loadSerials(String productId, String warehouseId) async {
    final String key = _shelfKey(productId, warehouseId);
    if (productId.isEmpty || _serialsOnShelf.containsKey(key)) return;
    try {
      _serialsOnShelf[key] = await fetchAllPages<SerialRecord>(
        (int page) => widget.api.serials(
          page: page,
          pageSize: maxApiPageSize,
          sortBy: 'serial_number',
          descending: false,
          filters: SerialQuery(
            productId: productId,
            warehouseId: warehouseId.isEmpty ? null : warehouseId,
            status: 'AVAILABLE',
          ),
        ),
      );
    } on ApiException catch (exception) {
      _serialsOnShelf[key] = const [];
      _error = 'Could not read the serial numbers on the shelf: '
          '${exception.message}';
    }
    if (mounted) setState(() {});
  }

  /// How many units a quantity is, or null when it is not a whole number.
  static int? _units(String quantity) {
    final double value = double.tryParse(quantity.trim()) ?? 0;
    return value == value.roundToDouble() ? value.toInt() : null;
  }

  /// Say which line is short of serials, before the round trip.
  String? _serialShortfall() {
    if (_direct) {
      for (int index = 0; index < _directLines.length; index++) {
        final _DirectLine line = _directLines[index];
        if (!_isSerialised(line.productId ?? '')) continue;
        final int? needed = _units(line.quantity.text);
        if (needed != null && needed > 0 && line.serialIds.length != needed) {
          return 'Line ${index + 1}: pick one serial number per unit going '
              'out -- $needed needed, ${line.serialIds.length} picked.';
        }
      }
      return null;
    }
    for (final BillableDocument document in _documents) {
      for (final BillableLine line in document.lines) {
        if (!_picksSerials(document, line)) continue;
        final int? needed =
            _units(_quantities[line.sourceDocumentLineId]?.text ?? '');
        final int picked =
            _pickedSerials[line.sourceDocumentLineId]?.length ?? 0;
        if (needed != null && needed > 0 && picked != needed) {
          return '${line.label}: pick one serial number per unit going out '
              '-- $needed needed, $picked picked.';
        }
      }
    }
    return null;
  }

  /// Let whoever bills say which units are going out.
  Widget _serialPicker({
    required Key key,
    required String productId,
    required String warehouseId,
    required List<String> picked,
    required int? needed,
  }) {
    final ThemeData theme = Theme.of(context);
    final List<SerialRecord> onShelf =
        _serialsOnShelf[_shelfKey(productId, warehouseId)] ?? const [];
    final bool short = needed != null && picked.length != needed;
    return Padding(
      key: key,
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            needed == null
                ? 'Serial numbers going out — ${picked.length} picked'
                : 'Serial numbers going out — pick $needed, '
                    '${picked.length} picked',
            style: theme.textTheme.labelMedium?.copyWith(
              color: short ? theme.colorScheme.error : null,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          if (onShelf.isEmpty)
            Text(
              'No serial numbers of this product are AVAILABLE. Number the '
              'units under Inventory → Batch & Serial first.',
              style: theme.textTheme.bodySmall,
            )
          else
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                for (final SerialRecord serial in onShelf)
                  FilterChip(
                    key: ValueKey<String>('serial-pick-${serial.id}'),
                    label: Text(serial.serialNumber),
                    selected: picked.contains(serial.id),
                    onSelected: (bool on) => setState(() {
                      if (on) {
                        picked.add(serial.id);
                      } else {
                        picked.remove(serial.id);
                      }
                    }),
                  ),
              ],
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Phase 2: the one-screen bill (the quotation's approved layout).
    if (Phase2Scope.of(context)) return _phase2Page(context);
    final ThemeData theme = Theme.of(context);
    final String title = _editing ? 'Edit draft invoice' : 'New Invoice';
    final Widget content = _loading
        ? const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: CircularProgressIndicator(),
            ),
          )
        : _direct
            ? _directForm(theme)
            : _billable.isEmpty && !_editing
                ? const WorkspaceEmptyState(
                    title: 'Nothing is waiting to be billed',
                    message: 'Dispatch a delivery note and it appears '
                        'here. A note that has already been invoiced in '
                        'full does not.',
                  )
                : _form_(theme);
    final List<Widget> actions = [
      TextButton(
        onPressed: _saving ? null : () => Navigator.of(context).pop(false),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: _saving || (!_direct && _billable.isEmpty && !_editing)
            ? null
            : _save,
        child: Text(
          _saving ? 'Saving…' : (_editing ? 'Save' : 'Create draft'),
        ),
      ),
    ];
    // Phase 2 (4.8): a bill open in a tab is the page, its buttons fixed
    // along the bottom; phase 1 keeps the dialog it always was.
    if (DocumentTabScope.of(context)) {
      return WorkspaceDialog(
        title: title,
        icon: Icons.receipt_outlined,
        onClose: _saving ? null : () => Navigator.of(context).pop(false),
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Align(
            alignment: Alignment.topLeft,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 960),
              child: content,
            ),
          ),
        ),
        footer: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(children: [
            const Spacer(),
            actions[0],
            const SizedBox(width: AppSpacing.md),
            actions[1],
          ]),
        ),
      );
    }
    return AlertDialog(
      title: Text(title),
      content: SizedBox(width: 720, child: content),
      actions: actions,
    );
  }

  /// One screen: who is buying, what they are taking, and what it costs.
  Widget _directForm(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'This firm bills directly. Saving raises the order and the '
                'delivery note behind this bill, so the goods leave the '
                'warehouse and the cost is recorded with them.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _customerId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Customer'),
                items: [
                  for (final Customer item in _customers)
                    DropdownMenuItem(
                      value: item.id,
                      child: Text(item.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a customer.' : null,
                onChanged: (value) => setState(() => _customerId = value),
              ),
              const SizedBox(height: AppSpacing.md),
              for (int index = 0; index < _directLines.length; index++) ...[
                _directLineRow(index, theme),
                if (_isSerialised(_directLines[index].productId ?? ''))
                  _serialPicker(
                    key: ValueKey<String>('serials-direct-$index'),
                    productId: _directLines[index].productId ?? '',
                    warehouseId: _directWarehouse,
                    picked: _directLines[index].serialIds,
                    needed: _units(_directLines[index].quantity.text),
                  ),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () =>
                      setState(() => _directLines.add(_DirectLine())),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('Add line'),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _billDiscount,
                decoration: const InputDecoration(
                  labelText: 'Discount on the whole bill %',
                  helperText: 'Comes off what the lines discounted to, and '
                      'the tax falls with it.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                validator: _percentage,
                onChanged: (_) => setState(() {}),
              ),
              TextFormField(
                controller: _freight,
                decoration: const InputDecoration(
                  labelText: 'Delivery charge',
                  // The opposite of the field above it, and the difference
                  // decides the tax -- so it is said rather than assumed.
                  helperText: 'Split across the lines and taxed with them.',
                  helperMaxLines: 2,
                ),
                keyboardType: TextInputType.number,
                onChanged: (_) => setState(() {}),
              ),
              TextFormField(
                controller: _reference,
                decoration:
                    const InputDecoration(labelText: "Customer's reference"),
              ),
              if (_error != null) ...[
                const SizedBox(height: AppSpacing.md),
                Text(
                  _error!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ],
            ],
          ),
        ),
      );

  Widget _directLineRow(int index, ThemeData theme) {
    final _DirectLine line = _directLines[index];
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: DropdownButtonFormField<String>(
              initialValue: line.productId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Product'),
              items: [
                for (final Product item in _products)
                  DropdownMenuItem(
                    value: item.id,
                    child: Text(item.name, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: (value) {
                setState(() {
                  line.productId = value;
                  // Units of the last product are not units of this one.
                  line.serialIds.clear();
                });
                if (value != null && _isSerialised(value)) {
                  _loadSerials(value, _directWarehouse);
                }
              },
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.quantity,
              decoration: const InputDecoration(labelText: 'Qty'),
              keyboardType: TextInputType.number,
              onChanged: (_) => setState(() {}),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.price,
              decoration: const InputDecoration(labelText: 'Price'),
              keyboardType: TextInputType.number,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextFormField(
              controller: line.discount,
              decoration: const InputDecoration(
                labelText: 'Disc %',
                // Never prefilled. A literal 0 reads as a refusal of every
                // standing arrangement, so blank is what takes the
                // customer's own rate.
                helperText: 'Blank takes theirs',
                helperMaxLines: 2,
              ),
              keyboardType: TextInputType.number,
              validator: _percentage,
            ),
          ),
          IconButton(
            tooltip: 'Remove line',
            onPressed: _directLines.length == 1
                ? null
                : () => setState(() => _directLines.removeAt(index)),
            icon: const Icon(Icons.close, size: 18),
          ),
        ],
      ),
    );
  }

  Widget _form_(ThemeData theme) => Form(
        key: _form,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                initialValue: _document?.sourceDocumentId,
                // Without this the button's row is `mainAxisSize: min` and
                // never constrains the label, so `ellipsis` has nothing to
                // ellipsise against and a long document name overflows.
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Bill this delivery note',
                  helperText: 'Only notes with something left to bill.',
                  helperMaxLines: 2,
                ),
                items: [
                  for (final BillableDocument item in _pickable)
                    DropdownMenuItem(
                      value: item.sourceDocumentId,
                      child: Text(item.label, overflow: TextOverflow.ellipsis),
                    ),
                ],
                validator: (value) =>
                    value == null ? 'Choose a delivery note.' : null,
                // Fixed while editing: changing which document a draft bills
                // is raising a different invoice, not correcting this one.
                onChanged: _editing
                    ? null
                    : (value) => setState(() {
                          final Iterable<BillableDocument> found = _billable
                              .where((item) => item.sourceDocumentId == value);
                          if (found.isNotEmpty) _choose(found.first);
                        }),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_document != null) ...[
                for (final BillableLine line in _document!.lines) ...[
                  _lineRow(line, theme),
                  if (_picksSerials(_document!, line))
                    _serialPicker(
                      key: ValueKey<String>(
                          'serials-${line.sourceDocumentLineId}'),
                      productId: line.productId,
                      warehouseId: line.warehouseId,
                      picked: _pickedSerials.putIfAbsent(
                          line.sourceDocumentLineId, () => <String>[]),
                      needed: _units(
                          _quantities[line.sourceDocumentLineId]?.text ?? ''),
                    ),
                ],
                const SizedBox(height: AppSpacing.md),
                TextFormField(
                  controller: _billDiscount,
                  decoration: const InputDecoration(
                    labelText: 'Discount on the whole bill %',
                    helperText: 'Comes off what the lines discounted to, and '
                        'the tax falls with it.',
                    helperMaxLines: 2,
                  ),
                  keyboardType: TextInputType.number,
                  validator: _percentage,
                  onChanged: (_) => setState(() {}),
                ),
                TextFormField(
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: "Customer's reference",
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Billed before tax: ${_beforeTax.toStringAsFixed(2)}. Tax is '
                  'worked out by the server at the rate in force.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.md),
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
            ],
          ),
        ),
      );

  Widget _lineRow(BillableLine line, ThemeData theme) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(line.label),
                  Text(
                    'dispatched ${line.sourceQuantity}'
                    '${line.alreadyInvoicedQuantity == '0' || line.alreadyInvoicedQuantity.isEmpty ? '' : ', already billed ${line.alreadyInvoicedQuantity}'}'
                    ' · at ${line.unitPrice}'
                    '${(double.tryParse(line.discountPercent) ?? 0) > 0 ? ' less ${line.discountPercent}%' : ''}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: TextFormField(
                controller: _quantities[line.sourceDocumentLineId],
                decoration: const InputDecoration(
                  labelText: 'Bill',
                  isDense: true,
                ),
                keyboardType: TextInputType.number,
                validator: (value) => _billableQuantity(value, line),
                onChanged: (_) => setState(() {}),
              ),
            ),
          ],
        ),
      );

  /// A quantity the server would refuse, caught before the round trip.
  String? _billableQuantity(String? value, BillableLine line) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a quantity.';
    if (parsed < 0) return 'Cannot be negative.';
    final double remaining = double.tryParse(line.remainingQuantity) ?? 0;
    // The goods left on somebody else's document; billing more than went out
    // is a bill the warehouse cannot reconcile.
    if (parsed > remaining) return 'Only $remaining left to bill.';
    return null;
  }

  String? _percentage(String? value) {
    final String text = (value ?? '').trim();
    if (text.isEmpty) return null;
    final double? parsed = double.tryParse(text);
    if (parsed == null) return 'Enter a percentage.';
    if (parsed < 0 || parsed > 100) return 'Between 0 and 100.';
    return null;
  }
}


/// One line of a bill raised without any paperwork behind it.
class _DirectLine {
  String? productId;

  /// Bumped when a scan fills the line, so its product box is rebuilt to
  /// show the product (a box otherwise takes its selection only once).
  int refresh = 0;

  /// The units picked for a serial-tracked product, by serial id.
  final List<String> serialIds = <String>[];
  final TextEditingController quantity = TextEditingController();
  final TextEditingController price = TextEditingController();
  final TextEditingController discount = TextEditingController();

  /// The batches chosen for the product (backlog 79 row 2): null while
  /// nobody has, an empty map once the choice is handed back to the server.
  Map<String, double>? batchPicks;

  /// The rate this line was last given without the person typing it -- the
  /// product's own price, or its batch's selling price. A rate still equal to
  /// it may be replaced; anything else was typed and is left alone.
  String? autoPrice;

  /// Whether the rate box holds nothing the person typed.
  bool get priceUntyped {
    final String text = price.text.trim();
    return text.isEmpty ||
        (double.tryParse(text) ?? 0) == 0 ||
        text == autoPrice;
  }
}

/// One way of paying on a counter bill (SEL-12): mode, amount, reference.
class _TenderRow {
  _TenderRow({this.mode = 'CASH', String amount = '', String reference = ''})
      : amount = TextEditingController(text: amount),
        reference = TextEditingController(text: reference);

  String mode;
  final TextEditingController amount;
  final TextEditingController reference;

  double get value => double.tryParse(amount.text.trim()) ?? 0;

  void dispose() {
    amount.dispose();
    reference.dispose();
  }
}
