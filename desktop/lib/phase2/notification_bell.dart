import 'dart:async';

import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import '../models/notification_feed.dart';
import 'app_menu_bar.dart';

/// The bell on the phase 2 bar (PLT-2): what is waiting for the signed-in
/// person in the active firm -- orders to approve, messages that failed, stock
/// at its reorder level -- with a count on it, and a click on a line opening
/// the screen that deals with it.
///
/// It fetches through [load] when a firm is chosen and every [interval]
/// after, and again at once when [firmKey] changes. A poll that fails keeps
/// the last list and says nothing: a bell that raised a dialog every minute
/// while the server was away would be worse than one that went quiet. With no
/// firm ([enabled] false) it draws nothing and asks nothing.
class NotificationBell extends StatefulWidget {
  const NotificationBell({
    super.key,
    required this.enabled,
    required this.firmKey,
    required this.load,
    required this.markRead,
    required this.onOpen,
    this.interval = const Duration(seconds: 60),
  });

  /// Whether there is a firm to ask about.
  final bool enabled;

  /// Identifies the firm: a change refetches at once.
  final Object? firmKey;

  final Future<NotificationFeed> Function() load;
  final Future<void> Function(List<String> keys) markRead;

  /// Called after the item is marked read; opens its screen.
  final ValueChanged<NotificationItem> onOpen;

  final Duration interval;

  @override
  State<NotificationBell> createState() => _NotificationBellState();
}

class _NotificationBellState extends State<NotificationBell> {
  Timer? _timer;
  NotificationFeed _feed = NotificationFeed.empty;

  /// Bumped whenever the firm changes or the bell stops, so an answer that
  /// arrives late is dropped rather than shown against the wrong firm.
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _restart();
  }

  @override
  void didUpdateWidget(NotificationBell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.enabled != widget.enabled ||
        oldWidget.firmKey != widget.firmKey ||
        oldWidget.interval != widget.interval) {
      _feed = NotificationFeed.empty;
      _restart();
    }
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    super.dispose();
  }

  void _restart() {
    _generation++;
    _timer?.cancel();
    _timer = null;
    if (!widget.enabled) return;
    unawaited(_poll());
    _timer = Timer.periodic(widget.interval, (_) => unawaited(_poll()));
  }

  Future<void> _poll() async {
    final int generation = _generation;
    try {
      final NotificationFeed feed = await widget.load();
      if (!mounted || generation != _generation) return;
      setState(() => _feed = feed);
    } on Object {
      // Keep what is shown; the next poll tries again.
    }
  }

  /// Marks [keys] read on screen at once, then on the server; a refusal
  /// brings the server's own answer back.
  Future<void> _markRead(List<String> keys) async {
    if (keys.isEmpty) return;
    final Set<String> marked = keys.toSet();
    final int newlyRead = _feed.items
        .where((item) => !item.read && marked.contains(item.key))
        .length;
    setState(() {
      _feed = NotificationFeed(
        items: [
          for (final NotificationItem item in _feed.items)
            marked.contains(item.key)
                ? NotificationItem(
                    key: item.key,
                    kind: item.kind,
                    title: item.title,
                    detail: item.detail,
                    count: item.count,
                    at: item.at,
                    read: true,
                  )
                : item,
        ],
        unread: (_feed.unread - newlyRead).clamp(0, _feed.unread),
      );
    });
    try {
      // The server takes 50 keys at a time.
      for (int i = 0; i < keys.length; i += 50) {
        await widget.markRead(
          keys.sublist(i, i + 50 > keys.length ? keys.length : i + 50),
        );
      }
    } on Object {
      unawaited(_poll());
    }
  }

  void _open(NotificationItem item) {
    if (!item.read) unawaited(_markRead([item.key]));
    widget.onOpen(item);
  }

  /// "5 min ago", "2 h ago", "3 d ago"; null for a line with no time.
  static String? ago(DateTime? at, DateTime now) {
    if (at == null) return null;
    final Duration age = now.difference(at);
    if (age.inMinutes < 1) return 'just now';
    if (age.inMinutes < 60) return '${age.inMinutes} min ago';
    if (age.inHours < 24) return '${age.inHours} h ago';
    return '${age.inDays} d ago';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return const SizedBox.shrink();
    final AppSemanticColors colors = context.semanticColors;
    final ThemeData theme = Theme.of(context);
    final List<String> unreadKeys = [
      for (final NotificationItem item in _feed.items)
        if (!item.read) item.key,
    ];
    final int unread = _feed.unread;
    return MenuAnchor(
      style: panelStyle(context),
      alignmentOffset: const Offset(-300, 0),
      menuChildren: [
        SizedBox(
          width: 340,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 6, 2),
                child: Row(children: [
                  Expanded(
                    child: Text(
                      'NOTIFICATIONS',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                        letterSpacing: .9,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  TextButton(
                    key: const ValueKey('notification-mark-all'),
                    onPressed: unreadKeys.isEmpty
                        ? null
                        : () => unawaited(_markRead(unreadKeys)),
                    child: const Text('Mark all as read'),
                  ),
                ]),
              ),
              if (_feed.items.isEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
                  child: Text(
                    'Nothing is waiting for you.',
                    key: const ValueKey('notification-empty'),
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                )
              else
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 360),
                  child: SingleChildScrollView(
                    // The menu's own scrollable owns the primary controller.
                    primary: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final NotificationItem item in _feed.items)
                          _line(context, item),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
      builder: (context, controller, _) => Tooltip(
        message: unread == 0 ? 'Notifications' : '$unread unread',
        child: IconButton(
          key: const ValueKey('notification-bell'),
          style: barIconStyle(context),
          onPressed: () =>
              controller.isOpen ? controller.close() : controller.open(),
          icon: Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.center,
            children: [
              Icon(Icons.notifications_none, color: colors.onChrome),
              if (unread > 0)
                Positioned(
                  right: -6,
                  top: -6,
                  child: Container(
                    key: const ValueKey('notification-badge'),
                    constraints:
                        const BoxConstraints(minWidth: 16, minHeight: 16),
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: colors.danger,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      unread > 99 ? '99+' : '$unread',
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onError,
                        fontSize: 10,
                        height: 1,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _line(BuildContext context, NotificationItem item) {
    final ThemeData theme = Theme.of(context);
    final String? when = ago(item.at, DateTime.now());
    return MenuItemButton(
      key: ValueKey('notification-${item.key}'),
      style: const ButtonStyle(
        minimumSize: WidgetStatePropertyAll(Size(340, 48)),
        alignment: Alignment.centerLeft,
      ),
      onPressed: () => _open(item),
      // A menu button gives its child no width, so the row is told one.
      child: SizedBox(
        width: 312,
        child: Row(children: [
        // The dot says unread without relying on the weight of the text.
        SizedBox(
          width: 14,
          child: item.read
              ? null
              : Icon(Icons.circle, size: 8, color: theme.colorScheme.primary),
        ),
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                item.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: item.read ? FontWeight.w400 : FontWeight.w700,
                ),
              ),
              if (item.detail.isNotEmpty || when != null)
                Text(
                  [
                    if (item.detail.isNotEmpty) item.detail,
                    if (when != null) when,
                  ].join(' - '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ),
        ]),
      ),
    );
  }
}
