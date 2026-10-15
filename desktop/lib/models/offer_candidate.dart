/// The offers and standing arrangements a sales line could take, as a priced
/// preview lists them, and what a person chose (L7 step 8).
///
/// `docs/design/OFFERS_ON_THE_BILL_LINE_DESIGN.md` sections 3.3 and 4. The
/// server builds the candidates afresh on every preview and works out every
/// figure itself; the screen sends **keys, never amounts**, and holds no rule
/// about what combines with what.
library;

/// What one candidate gives, in figures and in the server's own sentence.
class OfferGives {
  const OfferGives({
    required this.kind,
    required this.sentence,
    this.percent,
    this.amount,
    this.buyQuantity,
    this.freeQuantity,
  });

  final String kind;
  final String sentence;
  final String? percent;
  final String? amount;
  final String? buyQuantity;
  final String? freeQuantity;

  /// Whether it takes something off the line's price, not only free goods.
  bool get discounts => percent != null || amount != null;

  factory OfferGives.fromJson(Map<String, dynamic> json) => OfferGives(
        kind: '${json['kind'] ?? ''}',
        sentence: '${json['sentence'] ?? ''}',
        percent: _text(json['percent']),
        amount: _text(json['amount']),
        buyQuantity: _text(json['buy_quantity']),
        freeQuantity: _text(json['free_quantity']),
      );
}

/// The quantity typed, split as a part share of a "buy N get M free" offer.
class OfferPartShare {
  const OfferPartShare({
    required this.chargedQuantity,
    required this.freeQuantity,
  });

  final String chargedQuantity;
  final String freeQuantity;

  factory OfferPartShare.fromJson(Map<String, dynamic> json) => OfferPartShare(
        chargedQuantity: '${json['charged_quantity'] ?? '0'}',
        freeQuantity: '${json['free_quantity'] ?? '0'}',
      );
}

/// One offer or standing arrangement a line, or the bill, could take.
class OfferCandidate {
  const OfferCandidate({
    required this.key,
    required this.source,
    required this.code,
    required this.name,
    required this.gives,
    this.worth = '0',
    this.applied = false,
    this.chosen = false,
    this.combines = false,
    this.available = true,
    this.reason,
    this.needsMore,
    this.thenGives,
    this.partShare,
    this.fundedBy,
  });

  /// Minted by the server: an offer's lasting identity, a price list's id,
  /// `CUSTOMER` or `CUSTOMER_GROUP`.
  final String key;

  /// `promotion`, `price_list`, `customer` or `customer_group`.
  final String source;
  final String code;
  final String name;
  final OfferGives gives;

  /// What it takes off this line alone; for reading, never for the books.
  final String worth;
  final bool applied;
  final bool chosen;
  final bool combines;
  final bool available;
  final String? reason;
  final String? needsMore;
  final String? thenGives;
  final OfferPartShare? partShare;
  final String? fundedBy;

  /// An offer, rather than one of the customer's standing arrangements.
  bool get isOffer => source == 'promotion';

  /// What the line would earn with a little more: "13 more to get 3 free".
  String get hint => needsMore == null || thenGives == null
      ? ''
      : '${plainOfferQuantity(needsMore!)} more to get $thenGives';

  /// The same, short enough for under a quantity box: "2 more: 1 free".
  String get shortHint => needsMore == null || thenGives == null
      ? ''
      : '${plainOfferQuantity(needsMore!)} more: $thenGives';

  /// The row's label: "TEA-5, 5% off", "Price list CITY, 4%".
  String get label {
    final String sentence = gives.sentence;
    final String head = switch (source) {
      'price_list' => 'Price list ${code.isEmpty ? name : code}',
      'customer' => 'Standing rate',
      'customer_group' => 'Group rate',
      _ => code.isEmpty ? name : code,
    };
    return sentence.isEmpty ? head : '$head, $sentence';
  }

  factory OfferCandidate.fromJson(Map<String, dynamic> json) => OfferCandidate(
        key: '${json['key'] ?? ''}',
        source: '${json['source'] ?? ''}',
        code: '${json['code'] ?? ''}',
        name: '${json['name'] ?? ''}',
        gives: OfferGives.fromJson(
          Map<String, dynamic>.from(json['gives'] as Map? ?? const {}),
        ),
        worth: '${json['worth'] ?? '0'}',
        applied: json['applied'] == true,
        chosen: json['chosen'] == true,
        combines: json['combines'] == true,
        available: json['available'] != false,
        reason: _text(json['reason']),
        needsMore: _text(json['needs_more']),
        thenGives: _text(json['then_gives']),
        partShare: json['part_share'] is Map
            ? OfferPartShare.fromJson(
                Map<String, dynamic>.from(json['part_share'] as Map),
              )
            : null,
        fundedBy: _text(json['funded_by']),
      );
}

/// Every candidate in [raw], a preview's `candidates` or `bill_candidates`.
List<OfferCandidate> offerCandidatesFrom(dynamic raw) => <OfferCandidate>[
      for (final dynamic item in raw as List? ?? const [])
        if (item is Map) OfferCandidate.fromJson(Map<String, dynamic>.from(item)),
    ];

/// What a person chose for one line, as the line write models take it.
class OfferChoice {
  const OfferChoice({this.discountFrom, this.offers, this.partShare});

  /// `offers`, or the key of the one standing arrangement the discount
  /// comes from; null follows the ranking.
  final String? discountFrom;

  /// The keys of the offers the line takes; null takes the server's.
  final List<String>? offers;

  /// The key of the offer taken as a part share; the quantity sent is then
  /// what is charged.
  final String? partShare;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'discount_from': discountFrom,
        'offers': offers,
        'part_share': partShare,
      };
}

/// One line's choice while it is typed: nothing is sent until the person
/// ticked something, and then the keys they ticked, never a figure.
class LineOfferChoice {
  /// Whether somebody ticked, unticked or took a part share on this line.
  bool touched = false;
  OfferChoice? choice;

  /// Why the server did not take the last choice, kept until the next tick.
  String refused = '';

  /// "0.5 free from TEA-11", once a part share was taken.
  String partShareNote = '';

  /// The line's fields for a write or a preview: nothing on an untouched
  /// line, so the server decides -- and an edit keeps the stored choice.
  Map<String, dynamic> get payload => touched
      ? <String, dynamic>{'offer_choice': choice?.toJson()}
      : const <String, dynamic>{};

  /// Whether [candidate] shows ticked: what the person chose where they
  /// chose, else what the server applied.
  bool isTicked(OfferCandidate candidate) {
    final OfferChoice? chosen = choice;
    if (chosen == null) return candidate.applied;
    if (candidate.isOffer) {
      if (chosen.partShare == candidate.key) return true;
      return chosen.offers?.contains(candidate.key) ?? candidate.applied;
    }
    final String? from = chosen.discountFrom;
    if (from == null) return candidate.applied;
    return from == candidate.key;
  }

  /// Tick or untick [candidate], building the choice from what shows ticked
  /// in [candidates]. Keys only; which of them combine is the server's to
  /// answer on the next preview.
  void toggle(List<OfferCandidate> candidates, OfferCandidate candidate) {
    final bool tickedNow = isTicked(candidate);
    final List<String> offers = <String>[
      for (final OfferCandidate item in candidates)
        if (item.isOffer && item.key != candidate.key && isTicked(item))
          item.key,
    ];
    String? discountFrom = choice?.discountFrom;
    String? partShare = choice?.partShare;
    if (candidate.isOffer) {
      if (!tickedNow) {
        offers.add(candidate.key);
        // An offer that takes money off is ticked to give the discount.
        if (candidate.gives.discounts) discountFrom = 'offers';
      } else if (partShare == candidate.key) {
        partShare = null;
      }
    } else {
      discountFrom = tickedNow ? 'offers' : candidate.key;
    }
    choice = OfferChoice(
      discountFrom: discountFrom,
      offers: offers,
      partShare: partShare,
    );
    touched = true;
    refused = '';
  }

  /// Take [candidate] as a part share: the quantity becomes what is
  /// charged, which the caller sets, and the offer gives the rest free.
  void takePartShare(List<OfferCandidate> candidates, OfferCandidate candidate) {
    final OfferPartShare? share = candidate.partShare;
    if (share == null) return;
    choice = OfferChoice(
      discountFrom: choice?.discountFrom,
      offers: <String>[
        for (final OfferCandidate item in candidates)
          if (item.isOffer && isTicked(item)) item.key,
        if (!isTicked(candidate)) candidate.key,
      ],
      partShare: candidate.key,
    );
    touched = true;
    refused = '';
    partShareNote = '${plainOfferQuantity(share.freeQuantity)} free from '
        '${candidate.code.isEmpty ? candidate.name : candidate.code}';
  }

  /// The quantity was typed again: it is no longer a charged share.
  void quantityTyped() {
    final OfferChoice? chosen = choice;
    if (chosen == null || chosen.partShare == null) return;
    choice = OfferChoice(
      discountFrom: chosen.discountFrom,
      offers: chosen.offers,
    );
    partShareNote = '';
  }

  /// A preview said the choice sent could not stand: keep its words and drop
  /// the choice, so the save does not send it again. An edit sends null, so
  /// a stored choice is cleared as well.
  void refusedWith(String? message) {
    if (message == null || message.isEmpty || !touched) return;
    refused = message;
    choice = null;
    partShareNote = '';
  }
}

/// A quantity without its trailing zeros: 13.0000 reads 13, 0.5000 reads 0.5.
String plainOfferQuantity(String value) {
  final double? parsed = double.tryParse(value.trim());
  if (parsed == null) return value.trim();
  if (parsed == parsed.roundToDouble()) return parsed.toInt().toString();
  String text = parsed.toStringAsFixed(4);
  while (text.endsWith('0')) {
    text = text.substring(0, text.length - 1);
  }
  return text;
}

String? _text(dynamic value) => value == null ? null : '$value';
