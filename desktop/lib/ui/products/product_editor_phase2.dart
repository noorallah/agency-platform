part of 'product_management_page.dart';

/// The product record in the phase 2 app: a full-page tab titled with the
/// product's name, as the customer record the owner approved (2026-09-26).
/// Every section the firm uses is one scroll -- General, UOM & size,
/// Pricing, Tax, Attributes, Images, Attachments -- reached from a strip of
/// links, with a side panel of what selling and buying need at a glance:
/// the three prices, the margin they leave, and stock on hand. The dialog's
/// fields, validation, payload and three saves are reused unchanged.
extension _Phase2ProductForm on _ProductWorkspaceDialogState {
  /// The sections the record shows; audit and history are in the panel.
  List<String> get _pageSections => [
        for (final String tab in _visibleTabs)
          if (tab != 'audit' && tab != 'history') tab,
      ];

  Widget _phase2Page(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final String name = _name.text.trim();
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            unawaited(_close()),
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () =>
            unawaited(_saveAndClose()),
      },
      child: Focus(
        autofocus: true,
        child: Material(
          color: scheme.surface,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DocumentPageBand(
                title: widget.mode == ProductDialogMode.create
                    ? (name.isEmpty ? 'New product' : name)
                    : (name.isEmpty ? widget.product!.name : name),
                chips: [
                  if (_code.text.trim().isNotEmpty) _code.text.trim(),
                  _status == 'ACTIVE'
                      ? 'Active'
                      : _status.isEmpty
                          ? ''
                          : _status[0] + _status.substring(1).toLowerCase(),
                ].where((chip) => chip.isNotEmpty).toList(),
                hint: _readOnly ? '' : 'Ctrl+S save  ·  Esc close',
                actions: [
                  TextButton(
                    onPressed: _saving ? null : () => unawaited(_close()),
                    child: Text(_readOnly ? 'Close' : 'Cancel'),
                  ),
                  if (!_readOnly) ...[
                    OutlinedButton(
                      key: const ValueKey('product-save-new'),
                      onPressed:
                          _saving ? null : () => unawaited(_saveAndNew()),
                      child: const Text('Save & new'),
                    ),
                    FilledButton(
                      key: const ValueKey('product-save'),
                      onPressed:
                          _saving ? null : () => unawaited(_saveAndClose()),
                      child: Text(_saving ? 'Saving…' : 'Save product'),
                    ),
                  ],
                ],
              ),
              if (_validationSummary.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                  child: MaterialBanner(
                    contentTextStyle: theme.textTheme.bodyMedium,
                    content: Text(_validationSummary.join('  ·  ')),
                    actions: [
                      TextButton(
                        onPressed: () =>
                            _setState(() => _validationSummary = const []),
                        child: const Text('Dismiss'),
                      ),
                    ],
                  ),
                ),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, constraints) => Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            _sectionStrip(context),
                            Expanded(
                              child: AbsorbPointer(
                                absorbing: _saving,
                                child: _body(context),
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (constraints.maxWidth >= DocumentSidePanel.showFrom)
                        // Redrawn as the prices are typed, so the margin
                        // follows them.
                        ListenableBuilder(
                          listenable: Listenable.merge(
                            [_purchasePrice, _sellingPrice, _mrp],
                          ),
                          builder: (context, _) => _sidePanel(),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionStrip(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(children: [
            for (final String section in _pageSections)
              TextButton(
                key: ValueKey<String>('product-section-$section'),
                onPressed: () {
                  final BuildContext? target =
                      _sectionKey(section).currentContext;
                  if (target != null) {
                    unawaited(Scrollable.ensureVisible(
                      target,
                      duration: const Duration(milliseconds: 200),
                    ));
                  }
                },
                child: Text(_label(section)),
              ),
          ]),
        ),
      ),
    );
  }

  GlobalKey _sectionKey(String section) =>
      _sectionKeys.putIfAbsent(section, GlobalKey.new);

  Widget _heading(BuildContext context, String section) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      key: _sectionKey(section),
      padding: const EdgeInsets.fromLTRB(0, 20, 0, 10),
      child: Text(
        _label(section).toUpperCase(),
        style: theme.textTheme.labelMedium?.copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: .6,
          color: theme.colorScheme.onSurfaceVariant,
        ),
      ),
    );
  }

  Widget _section(String key) => switch (key) {
        'general' => _generalSection(),
        'packaging' => _packagingSection(),
        'pricing' => _pricingSection(),
        'tax' => _taxSection(),
        'business_attributes' => _attributesSection(),
        'images' => _mediaSection(_imageRows, imageMode: true),
        'attachments' => _mediaSection(_attachmentRows, imageMode: false),
        _ => const SizedBox.shrink(),
      };

  /// The dialog's own sections, drawn dense, one after another.
  Widget _body(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Theme(
      data: theme.copyWith(
        inputDecorationTheme: theme.inputDecorationTheme.copyWith(
          isDense: true,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        ),
      ),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final String section in _pageSections) ...[
              _heading(context, section),
              _section(section),
            ],
          ],
        ),
      ),
    );
  }

  Widget _sidePanel() {
    final Product? product = widget.product;
    final double buy = double.tryParse(_purchasePrice.text.trim()) ?? 0;
    final double sell = double.tryParse(_sellingPrice.text.trim()) ?? 0;
    final double mrp = double.tryParse(_mrp.text.trim()) ?? 0;
    String money(double value) =>
        value == 0 ? '—' : indianAmount(value, full: true);
    return DocumentSidePanel(children: [
      const DocumentSideHeading('Prices'),
      DocumentSidePair('Buys at', money(buy)),
      DocumentSidePair('Sells at', money(sell), bold: true),
      DocumentSidePair('MRP', money(mrp)),
      if (buy > 0 && sell > 0) ...[
        DocumentSidePair(
          'Margin',
          '${indianAmount(sell - buy, full: true)} · '
              '${((sell - buy) / sell * 100).toStringAsFixed(1)}%',
          tone: sell < buy ? Theme.of(context).colorScheme.error : null,
        ),
        const DocumentSideNote('on the selling price, before tax'),
      ],
      if (mrp > 0 && sell > mrp)
        DocumentSideNote(
          'the selling price is above MRP, which cannot be charged',
        ),
      if (product != null) ...[
        const DocumentSideHeading('Stock'),
        DocumentSidePair(
          'On hand',
          product.stockOnHand.isEmpty
              ? '—'
              : '${documentQuantity(product.stockOnHand)} ${product.unit}'
                  .trim(),
          tone: product.lowStock ? Theme.of(context).colorScheme.error : null,
        ),
        if (product.lowStock) const DocumentSideNote('below its reorder level'),
        const DocumentSideHeading('Record'),
        DocumentSidePair('Created', _day(product.createdAt)),
        DocumentSidePair('Last changed', _day(product.updatedAt)),
      ] else
        const DocumentSideNote(
          'a code and a name are all it needs to be saved; units, prices and '
          'tax can be added now or later',
        ),
    ]);
  }

  String _day(String value) {
    final DateTime? day = DateTime.tryParse(value)?.toLocal();
    return day == null ? (value.isEmpty ? '—' : value) : documentDate(day);
  }
}
