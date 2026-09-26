import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import 'menu_layout.dart';

/// The phase 2 menu bar (UI_PHASE_2_DESIGN.md 4.1-4.3): the areas across the
/// top, each dropping a panel of columns rather than expanding a tree.
///
/// Built on Flutter's [MenuBar] for what a Windows menu bar does and a row of
/// buttons does not: moving the pointer along the bar while a panel is open
/// switches to the next area's panel, the arrow keys walk it, and Escape or a
/// click away closes it. Everything it offers has already been cut to what
/// the user may open ([MenuLayout.visible]); this widget only draws it.
class AppMenuBar extends StatelessWidget {
  const AppMenuBar({
    super.key,
    required this.appName,
    required this.areas,
    required this.settings,
    required this.currentPath,
    required this.onOpen,
    required this.trailing,
  });

  final String appName;

  /// The areas to show, already filtered; an area with nothing allowed is not
  /// in this list at all.
  final List<MenuAreaSpec> areas;

  /// The Settings gear's sections, or null when the user may open none.
  final MenuAreaSpec? settings;

  /// The router path on screen, which marks its area on the bar.
  final String currentPath;
  final ValueChanged<MenuItemSpec> onOpen;

  /// Search, the firm switcher and the profile, right-aligned.
  final List<Widget> trailing;

  static const double height = 44;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final String? currentArea = MenuLayout.areaOf(currentPath)?.id;
    return Material(
      color: colors.chrome,
      child: SizedBox(
        height: height,
        child: Row(children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Text(
              appName,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    color: colors.onChrome,
                    fontWeight: FontWeight.w700,
                  ),
            ),
          ),
          // The areas get whatever the controls on the right leave, measured
          // rather than guessed: the right-hand side changes with the firm's
          // name, and a fixed allowance either wasted room or overlapped.
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) =>
                  _areas(context, constraints.maxWidth, currentArea),
            ),
          ),
          ...trailing,
          if (settings != null)
            MenuBar(
              style: MenuStyle(
                backgroundColor: WidgetStatePropertyAll(colors.chrome),
                elevation: const WidgetStatePropertyAll(0),
                padding: const WidgetStatePropertyAll(EdgeInsets.zero),
              ),
              children: [
                SubmenuButton(
                  key: const ValueKey('menu-area-settings'),
                  style: _barButtonStyle(
                      context, currentArea == MenuLayout.settings.id),
                  alignmentOffset: const Offset(-420, 0),
                  menuChildren: [_AreaPanel(area: settings!, onOpen: onOpen)],
                  child: Tooltip(
                    message: 'Settings',
                    child: Icon(Icons.settings_outlined,
                        color: colors.onChrome, size: 20),
                  ),
                ),
              ],
            ),
          const SizedBox(width: 6),
        ]),
      ),
    );
  }

  /// The areas that fit in [room]; the rest fold into More, from the right
  /// (4.11). An area costs about its label plus padding.
  Widget _areas(BuildContext context, double room, String? currentArea) {
    final AppSemanticColors colors = context.semanticColors;
    double cost(MenuAreaSpec area) => area.label.length * 8.5 + 44;
    int fits = 0;
    double used = 0;
    for (final MenuAreaSpec area in areas) {
      if (used + cost(area) > room) break;
      used += cost(area);
      fits++;
    }
    if (fits < areas.length) {
      // Leave space for More itself.
      while (fits > 1 && used + 70 > room) {
        used -= cost(areas[fits - 1]);
        fits--;
      }
    }
    final List<MenuAreaSpec> onBar = areas.take(fits).toList();
    final List<MenuAreaSpec> folded = areas.skip(fits).toList();
    return Align(
      alignment: Alignment.centerLeft,
      child: MenuBar(
        style: MenuStyle(
          backgroundColor: WidgetStatePropertyAll(colors.chrome),
          elevation: const WidgetStatePropertyAll(0),
          // A MenuBar stretches its buttons to its own height; padding it
          // is what leaves them the wireframe's 32 px pills.
          padding: const WidgetStatePropertyAll(
            EdgeInsets.symmetric(vertical: 5),
          ),
          shape: const WidgetStatePropertyAll(RoundedRectangleBorder()),
        ),
        children: [
          for (final MenuAreaSpec area in onBar)
            _areaButton(context, area, area.id == currentArea),
          if (folded.isNotEmpty)
            SubmenuButton(
              key: const ValueKey('menu-area-more'),
              style: _barButtonStyle(context, false),
              menuChildren: [
                for (final MenuAreaSpec area in folded)
                  SubmenuButton(
                    menuChildren: [_AreaPanel(area: area, onOpen: onOpen)],
                    child: Text(area.label),
                  ),
              ],
              child: const Text('More'),
            ),
        ],
      ),
    );
  }

  Widget _areaButton(BuildContext context, MenuAreaSpec area, bool current) {
    // An area of one screen (Home) opens it rather than a panel of one.
    if (area.items.length == 1) {
      final MenuItemSpec only = area.items.first;
      return MenuItemButton(
        key: ValueKey('menu-area-${area.id}'),
        style: _barButtonStyle(context, current),
        onPressed: () => onOpen(only),
        child: Text(area.label),
      );
    }
    return SubmenuButton(
      key: ValueKey('menu-area-${area.id}'),
      style: _barButtonStyle(context, current),
      menuChildren: [_AreaPanel(area: area, onOpen: onOpen)],
      // "Sell ▾": an area that drops a panel says so, as the wireframe does.
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(area.label),
        const SizedBox(width: 2),
        const Icon(Icons.arrow_drop_down, size: 18),
      ]),
    );
  }

  ButtonStyle _barButtonStyle(BuildContext context, bool current) {
    final AppSemanticColors colors = context.semanticColors;
    return ButtonStyle(
      foregroundColor: WidgetStatePropertyAll(colors.onChrome),
      iconColor: WidgetStatePropertyAll(colors.onChrome),
      backgroundColor: WidgetStateProperty.resolveWith((states) =>
          states.contains(WidgetState.hovered) ||
                  states.contains(WidgetState.focused) ||
                  states.contains(WidgetState.pressed)
              ? colors.chromeActive
              : Colors.transparent),
      overlayColor: const WidgetStatePropertyAll(Colors.transparent),
      // The wireframe's pill: padded and rounded, not the bar's full height.
      padding: const WidgetStatePropertyAll(
        EdgeInsets.symmetric(horizontal: 11, vertical: 7),
      ),
      minimumSize: const WidgetStatePropertyAll(Size(0, 34)),
      maximumSize: const WidgetStatePropertyAll(Size(double.infinity, 34)),
      shape: WidgetStatePropertyAll(
        RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
      ),
      // The area you are in: the wireframe's inset shadow (`inset 0 -3px 0`
      // on a 5 px-rounded pill) -- the band between the pill's bottom edge
      // and the same pill lifted 3 px, so it curls up both rounded corners.
      backgroundBuilder: current
          ? (context, states, child) => CustomPaint(
                key: const ValueKey('menu-area-current'),
                foregroundPainter: _InsetBar(colors.chromeIndicator),
                child: child,
              )
          : null,
    );
  }
}

/// One area's drop-down: its groups side by side, every item visible at once
/// with no scrolling and nothing to expand (4.3).
class _AreaPanel extends StatelessWidget {
  const _AreaPanel({required this.area, required this.onOpen});

  final MenuAreaSpec area;
  final ValueChanged<MenuItemSpec> onOpen;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final MenuGroupSpec group in area.groups)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: IntrinsicWidth(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (area.groups.length > 1 || group.label != area.label)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(12, 4, 12, 6),
                        child: Text(
                          group.label.toUpperCase(),
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                            letterSpacing: .6,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    for (final MenuItemSpec item in group.items)
                      MenuItemButton(
                        key: ValueKey('menu-item-${item.path}'),
                        style: ButtonStyle(
                          minimumSize:
                              const WidgetStatePropertyAll(Size(160, 34)),
                          // 4.14: a pointed-at item is outlined in the
                          // accent, not only tinted -- a tint alone is the
                          // faint hover D-QA-1 reported.
                          shape: WidgetStateProperty.resolveWith((states) =>
                              RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(5),
                                side: states.contains(WidgetState.hovered) ||
                                        states.contains(WidgetState.focused)
                                    ? BorderSide(
                                        color: scheme.primary, width: 1.5)
                                    : BorderSide.none,
                              )),
                        ),
                        onPressed: () => onOpen(item),
                        child: Text(item.label),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// The screens somebody has open, as tabs under the menu bar (decision 3).
class OpenScreenTabs extends StatelessWidget {
  const OpenScreenTabs({
    super.key,
    required this.paths,
    required this.activePath,
    required this.labelFor,
    required this.onSelect,
    required this.onClose,
  });

  final List<String> paths;
  final String activePath;
  final String Function(String path) labelFor;
  final ValueChanged<String> onSelect;
  final ValueChanged<String> onClose;

  static const double height = 34;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    // The wireframe's strip: tabs standing on a line, the one on show joined
    // to the page below it.
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      padding: const EdgeInsets.only(left: 8, top: 4),
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          for (final String path in paths)
            _ScreenTab(
              key: ValueKey('open-screen-$path'),
              label: labelFor(path),
              active: path == activePath,
              onSelect: () => onSelect(path),
              onClose: () => onClose(path),
            ),
        ],
      ),
    );
  }
}

class _ScreenTab extends StatelessWidget {
  const _ScreenTab({
    super.key,
    required this.label,
    required this.active,
    required this.onSelect,
    required this.onClose,
  });

  final String label;
  final bool active;
  final VoidCallback onSelect;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextStyle? style = Theme.of(context).textTheme.bodyMedium?.copyWith(
          color: active ? scheme.onSurface : scheme.onSurfaceVariant,
          fontWeight: active ? FontWeight.w600 : FontWeight.w400,
        );
    // As the wireframe draws them: every tab a bordered card with rounded
    // top corners, grey behind; the one on show white and bold, the same
    // ground as the page it opens onto.
    return Padding(
      padding: const EdgeInsets.only(right: 2),
      child: Material(
        color: active
            ? scheme.surfaceContainerLowest
            : scheme.surfaceContainerHigh,
        shape: RoundedRectangleBorder(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
          side: BorderSide(color: scheme.outlineVariant),
        ),
        // Middle-click closes, as it does on a browser tab.
        child: GestureDetector(
          onTertiaryTapUp: (_) => onClose(),
          child: InkWell(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
            onTap: onSelect,
            child: Container(
              padding: const EdgeInsets.only(left: 12, right: 4),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(label, style: style),
                const SizedBox(width: 4),
                IconButton(
                  tooltip: 'Close (Ctrl+W)',
                  visualDensity: VisualDensity.compact,
                  iconSize: 16,
                  onPressed: onClose,
                  icon: Icon(Icons.close, color: scheme.onSurfaceVariant),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// Where the open-screen list goes when [path] is opened: added at the end,
/// or left where it is if already open; capped at [limit] by closing the
/// oldest tab that is not [path] itself. Pure, so the rule is testable
/// without a shell.
List<String> openScreen(List<String> open, String path, {int limit = 10}) {
  if (open.contains(path)) return open;
  final List<String> next = [...open, path];
  while (next.length > limit) {
    next.removeAt(0);
  }
  return next;
}

/// The open-screen list after [path] is closed, and the tab to show next: the
/// one to its right, else to its left, else none.
({List<String> open, String? next}) closeScreen(
  List<String> open,
  String path,
  String activePath,
) {
  final int index = open.indexOf(path);
  if (index < 0) return (open: open, next: null);
  final List<String> remaining = [...open]..removeAt(index);
  if (path != activePath) return (open: remaining, next: null);
  if (remaining.isEmpty) return (open: remaining, next: null);
  return (
    open: remaining,
    next: remaining[index < remaining.length ? index : remaining.length - 1],
  );
}

/// The command box's place on the menu bar (4.4): a box that says what it is
/// and which keys open it, rather than a bare magnifier.
class SearchLauncher extends StatelessWidget {
  const SearchLauncher({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final TextStyle? style = Theme.of(context)
        .textTheme
        .bodyMedium
        ?.copyWith(color: colors.onChromeMuted);
    return Tooltip(
      message: 'Search screens and records (Ctrl+K)',
      child: InkWell(
        key: const ValueKey('menu-search'),
        onTap: onPressed,
        borderRadius: BorderRadius.circular(6),
        child: Container(
          height: 30,
          constraints: const BoxConstraints(minWidth: 200),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            border: Border.all(color: colors.onChromeMuted),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.search, size: 18, color: colors.onChromeMuted),
            const SizedBox(width: 8),
            Text('Search', style: style),
            const SizedBox(width: 24),
            Text('Ctrl+K', style: style),
          ]),
        ),
      ),
    );
  }
}

/// The connection, as one dot on the menu bar (4.5): green when the server
/// and its database answer, amber while checking, red when either is gone.
/// The details -- who, which firm, server, version -- are on hover, which is
/// what phase 1's second status bar spelled out along the bottom of every
/// screen.
class ConnectionDot extends StatelessWidget {
  const ConnectionDot({
    super.key,
    required this.online,
    required this.checking,
    required this.details,
  });

  final bool online;
  final bool checking;
  final String details;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final Color color = online
        ? colors.success
        : checking
            ? colors.warning
            : colors.danger;
    final String state = online
        ? 'Online'
        : checking
            ? 'Connecting'
            : 'Offline';
    return Tooltip(
      message: '$state\n$details',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Container(
            key: const ValueKey('connection-dot'),
            width: 9,
            height: 9,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              border: Border.all(color: colors.onChrome, width: 1),
            ),
          ),
          const SizedBox(width: 6),
          Text(
            state,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: colors.onChromeMuted),
          ),
        ]),
      ),
    );
  }
}

/// CSS `box-shadow: inset 0 -3px 0` on a rounded rectangle: the pill minus
/// itself moved up by [thickness]. What is left is a band along the bottom
/// that follows both lower corners up, as the wireframe draws the area you
/// are in.
class _InsetBar extends CustomPainter {
  const _InsetBar(this.color);

  final Color color;

  static const double radius = 5;
  static const double thickness = 3;

  @override
  void paint(Canvas canvas, Size size) {
    final RRect pill = RRect.fromRectAndRadius(
      Offset.zero & size,
      const Radius.circular(radius),
    );
    final Path band = Path.combine(
      PathOperation.difference,
      Path()..addRRect(pill),
      Path()..addRRect(pill.shift(const Offset(0, -thickness))),
    );
    canvas.drawPath(band, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_InsetBar oldDelegate) => oldDelegate.color != color;
}
