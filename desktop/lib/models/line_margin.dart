import 'entities.dart';

/// What one saved sales order or bill line cost and what it made (L3 step
/// 4, LOT_MARGINS_DESIGN 3.7).
///
/// The server sends these only to a holder of `PRODUCT_VIEW_COST_PRICE`; for
/// anybody else every field is null and [LineMargin.maybeFrom] gives null, so
/// a screen that draws the columns only when it has one never shows cost to
/// somebody not allowed to see it. Screen only: nothing printed reads them.
class LineMargin {
  const LineMargin({
    this.cost,
    this.costIsEstimate = false,
    this.margin,
    this.marginPercent,
  });

  /// The cost of the line's lots: recorded once dispatched, worked out
  /// before that ([costIsEstimate]).
  final double? cost;
  final bool costIsEstimate;

  /// Taxable value less cost, and that as a percentage of cost.
  final double? margin;
  final double? marginPercent;

  /// The line's figures, or null where the server sent none.
  static LineMargin? maybeFrom(Json json) {
    final double? cost = _number(json['cost_amount']);
    final double? margin = _number(json['margin_amount']);
    if (cost == null && margin == null) return null;
    return LineMargin(
      cost: cost,
      costIsEstimate: json['cost_is_estimate'] == true,
      margin: margin,
      marginPercent: _number(json['margin_percent']),
    );
  }
}

/// A saved order's or bill's cost and margin in total, or nothing.
class DocumentMargin {
  const DocumentMargin({this.cost, this.margin});

  final double? cost;
  final double? margin;

  /// The margin as a percentage of cost, where there is a cost.
  double? get percent {
    final double? base = cost;
    final double? made = margin;
    if (base == null || made == null || base == 0) return null;
    return made / base * 100;
  }

  /// The document's totals, or null where the server sent none.
  static DocumentMargin? maybeFrom(Json json) {
    final double? cost = _number(json['cost_total']);
    final double? margin = _number(json['margin_total']);
    if (cost == null && margin == null) return null;
    return DocumentMargin(cost: cost, margin: margin);
  }
}

double? _number(dynamic value) =>
    value == null ? null : double.tryParse(stringValue(value));
