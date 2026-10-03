import 'entities.dart';

/// One line in the bell: something waiting for the signed-in person (PLT-2).
///
/// Read from `GET /api/v1/notifications`. [key] names the thing rather than
/// the moment, so a read mark survives the next poll; [kind] says which
/// screen to open.
class NotificationItem {
  const NotificationItem({
    required this.key,
    required this.kind,
    required this.title,
    this.detail = '',
    this.count = 1,
    this.at,
    this.read = false,
  });

  factory NotificationItem.fromJson(Json json) => NotificationItem(
        key: stringValue(json['key']),
        kind: stringValue(json['kind']),
        title: stringValue(json['title']),
        detail: stringValue(json['detail']),
        count: json['count'] is num ? (json['count'] as num).toInt() : 1,
        at: DateTime.tryParse(stringValue(json['at']))?.toLocal(),
        read: boolValue(json['read']),
      );

  final String key;
  final String kind;
  final String title;
  final String detail;
  final int count;
  final DateTime? at;
  final bool read;
}

/// The bell's whole answer: the lines, and how many are unread.
class NotificationFeed {
  const NotificationFeed({this.items = const [], this.unread = 0});

  factory NotificationFeed.fromJson(Json json) {
    final dynamic items = json['items'];
    final List<NotificationItem> rows = items is List
        ? [
            for (final dynamic row in items)
              if (row is Map)
                NotificationItem.fromJson(Map<String, dynamic>.from(row)),
          ]
        : const [];
    return NotificationFeed(
      items: rows,
      unread: json['unread'] is num
          ? (json['unread'] as num).toInt()
          : rows.where((row) => !row.read).length,
    );
  }

  static const NotificationFeed empty = NotificationFeed();

  final List<NotificationItem> items;
  final int unread;
}
