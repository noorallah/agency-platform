part of 'sales_invoice_editor_dialog.dart';

/// Holding a counter bill and the cashier's shift (backlog 87 #7, SG-7).
///
/// Hold saves the bill the way Save draft does, parks it on the server and
/// opens a fresh bill; Recall takes one back. The shift strip reads the
/// caller's open shift once as the screen opens and again only when a bill is
/// approved or a shift is opened or closed. A shift is optional: with none
/// open the counter works as it always did.
extension _CounterHoldAndShift on _SalesInvoiceEditorDialogState {
  /// Whether this is the counter: phase 2, a firm that bills products, and a
  /// screen opened for billing rather than to correct a draft from the list.
  bool get _counterMode =>
      _phase2 && _stages.billsDirectly && widget.invoiceId == null;

  /// Whether the bill has a line worth holding.
  bool get _hasBillableLine {
    if (_editing) return true;
    for (final _DirectLine line in _directLines) {
      if (line.productId == null) continue;
      if ((double.tryParse(line.quantity.text.trim()) ?? 0) > 0) return true;
    }
    return false;
  }

  /// Read the shift and the count of held bills, once, as the counter opens.
  Future<void> _readCounterState() async {
    if (_shiftKnown || !_counterMode) return;
    _shiftKnown = true;
    await Future.wait<void>(<Future<void>>[_refreshShift(), _refreshHeld()]);
  }

  Future<void> _refreshShift() async {
    try {
      final Json? shift = await widget.api.currentCounterShift();
      if (mounted) _setState(() => _shift = shift);
    } on ApiException {
      // No strip data; the counter works without a shift.
      if (mounted) _setState(() => _shift = null);
    }
  }

  Future<void> _refreshHeld() async {
    try {
      final Json response =
          await widget.api.heldSalesInvoices(page: 1, pageSize: 1);
      final int count = pagedTotal(
        response,
        fallback: (response['data'] as List? ?? const []).length,
      );
      if (mounted) _setState(() => _heldCount = count);
    } on ApiException {
      // The count is a courtesy; Recall still lists them.
    }
  }

  Future<void> _openShift() async {
    final Json? opened = await showDialog<Json>(
      context: context,
      builder: (_) => OpenShiftDialog(api: widget.api),
    );
    if (opened == null || !mounted) return;
    await _refreshShift();
  }

  Future<void> _closeShift() async {
    final String? id = _shift == null ? null : stringValue(_shift!['id']);
    if (id == null || id.isEmpty) return;
    await showDialog<Json>(
      context: context,
      builder: (_) => CloseShiftDialog(api: widget.api, shiftId: id),
    );
    if (!mounted) return;
    await _refreshShift();
  }

  /// A fresh bill after one is parked or finished. A bill that was a saved
  /// draft (a recalled one) is let go of first, so the next is a new bill.
  Future<void> _startAnotherBill() async {
    if (_draftId != null) {
      _setState(() {
        _draftId = null;
        _existing = null;
        _document = null;
        _extraDocuments.clear();
        _loading = true;
      });
      await _load();
      if (!mounted) return;
    }
    _newCounterBill();
  }

  /// F8: save the bill, park it, open the next one.
  Future<void> _holdBill() async {
    if (_saving || !_hasBillableLine) return;
    final String? note = await askHoldNote(context);
    if (note == null || !mounted) return;
    final Json? saved = await _persist();
    if (saved == null || !mounted) return;
    final String id = stringValue(saved['id']);
    try {
      await widget.api.holdSalesInvoice(id, note: note);
    } on ApiException catch (error) {
      if (!mounted) return;
      await _holdSaved(
        saved,
        'Saved as draft ${stringValue(saved['invoice_number'])}, but not '
        'held: ${error.message}',
      );
      return;
    }
    if (!mounted) return;
    NotificationService.show(
      context,
      '${stringValue(saved['invoice_number'])} is held. Recall it from the '
      'Recall button.',
      kind: AppNotificationKind.success,
    );
    await _startAnotherBill();
    if (mounted) await _refreshHeld();
  }

  /// Pick a held bill and carry on with it as the draft it is.
  Future<void> _recallBill() async {
    if (_saving) return;
    if (_hasBillableLine) {
      _setState(() => _error =
          'Hold this bill, or finish it, before recalling another.');
      return;
    }
    final Json? row = await showDialog<Json>(
      context: context,
      builder: (_) => HeldBillsDialog(api: widget.api),
    );
    if (row == null || !mounted) return;
    final String id = stringValue(row['id']);
    _setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.recallSalesInvoice(id);
    } on ApiException catch (error) {
      if (!mounted) return;
      _setState(() {
        _saving = false;
        _error = error.message;
      });
      return;
    }
    if (!mounted) return;
    _setState(() {
      _draftId = id;
      _stayAtCounter = true;
      _loading = true;
      _saving = false;
    });
    await _load();
    if (mounted) await _refreshHeld();
  }

  /// The Hold and Recall buttons, for the page band.
  List<Widget> _holdActions() {
    if (!_counterMode) return const <Widget>[];
    return <Widget>[
      OutlinedButton(
        key: const ValueKey('sales-invoice-hold'),
        onPressed: _saving || !_hasBillableLine
            ? null
            : () => unawaited(_holdBill()),
        child: const Text('Hold (F8)'),
      ),
      OutlinedButton(
        key: const ValueKey('sales-invoice-recall'),
        onPressed: _saving ? null : () => unawaited(_recallBill()),
        child: Text(_heldCount > 0 ? 'Recall ($_heldCount)' : 'Recall'),
      ),
    ];
  }

  /// The shift strip, above the scan field.
  Widget _shiftStrip() => CounterShiftStrip(
        shift: _shift,
        busy: _saving,
        onOpen: () => unawaited(_openShift()),
        onClose: () => unawaited(_closeShift()),
      );
}
