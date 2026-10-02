import 'entities.dart';

/// The five things a person scores a supplier on, in the order shown.
const List<(String, String)> vendorRatingCriteria = <(String, String)>[
  ('quality', 'Quality'),
  ('delivery', 'Delivery'),
  ('price', 'Price'),
  ('communication', 'Communication'),
  ('paperwork', 'Paperwork'),
];

/// One person's opinion of a supplier (BUY-15).
class VendorRating {
  const VendorRating({
    required this.id,
    required this.ratedBy,
    required this.ratedOn,
    required this.scores,
    required this.remark,
  });

  final String id;
  final String ratedBy;
  final String ratedOn;

  /// Criterion key (`quality`...) to a score from 1 to 5.
  final Map<String, int> scores;
  final String remark;

  factory VendorRating.fromJson(Json json) => VendorRating(
        id: stringValue(json['id']),
        ratedBy: stringValue(json['rated_by']),
        ratedOn: stringValue(json['rated_on']),
        scores: <String, int>{
          for (final (String key, String _) in vendorRatingCriteria)
            key: (json[key] as num?)?.toInt() ?? 0,
        },
        remark: stringValue(json['remark']),
      );
}

/// Everything `GET /vendors/{id}/ratings` answers: the averages, the list and
/// the caller's own rating.
class VendorRatings {
  const VendorRatings({
    required this.count,
    required this.averages,
    required this.overall,
    required this.ratings,
    required this.mine,
  });

  final int count;

  /// Criterion key to its average as the server printed it; null when unrated.
  final Map<String, String?> averages;
  final String? overall;
  final List<VendorRating> ratings;
  final VendorRating? mine;

  factory VendorRatings.fromJson(Json json) {
    final Object? rawAverages = json['averages'];
    final Json averages = rawAverages is Map
        ? Map<String, dynamic>.from(rawAverages)
        : <String, dynamic>{};
    final Object? rawMine = json['mine'];
    return VendorRatings(
      count: (json['count'] as num?)?.toInt() ?? 0,
      averages: <String, String?>{
        for (final (String key, String _) in vendorRatingCriteria)
          key: averages[key]?.toString(),
      },
      overall: json['overall']?.toString(),
      ratings: <VendorRating>[
        for (final Object? row in (json['ratings'] as List<dynamic>? ?? []))
          if (row is Map)
            VendorRating.fromJson(Map<String, dynamic>.from(row)),
      ],
      mine: rawMine is Map
          ? VendorRating.fromJson(Map<String, dynamic>.from(rawMine))
          : null,
    );
  }
}
