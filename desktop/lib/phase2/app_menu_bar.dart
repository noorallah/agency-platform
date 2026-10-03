import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import 'favourites.dart';
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
    required this.areas,
    required this.settings,
    required this.currentPath,
    required this.onOpen,
    required this.onOpenSetUp,
    required this.trailing,
    this.profile,
    this.favourites,
  });

  /// The areas to show, already filtered; an area with nothing allowed is not
  /// in this list at all.
  final List<MenuAreaSpec> areas;

  /// The Settings page's sections, or null when the user may open none --
  /// which hides the gear.
  final MenuAreaSpec? settings;

  /// The router path on screen, which marks its area on the bar.
  final String currentPath;
  final ValueChanged<MenuItemSpec> onOpen;

  /// Opens the Settings page (backlog 72), at the named section or at its
  /// first.
  final ValueChanged<String?> onOpenSetUp;

  /// Search and the firm switcher, right-aligned before the gear.
  final List<Widget> trailing;

  /// Who is signed in: last on the bar, after the gear, as the wireframe.
  final Widget? profile;

  /// The user's starred screens, which every drop-down item can star or
  /// unstar (D-UI-3); null draws no stars.
  final Favourites? favourites;

  static const double height = 44;

  /// The letter that opens each area with Alt, as a Windows menu bar does
  /// (Alt+S for Sell); it is underlined while Alt is held. Not G or K: those
  /// are the command box (4.4).
  static const Map<String, String> accelerators = {
    'home': 'h',
    'sell': 's',
    'buy': 'b',
    'stock': 't',
    'accounts': 'a',
    'masters': 'm',
    'reports': 'r',
  };

  /// [label] with `&` before its Alt letter, as [MenuAcceleratorLabel]
  /// reads it -- "S&tock" underlines the t.
  static String acceleratorLabel(String id, String label) {
    final String? letter = accelerators[id];
    final int at = letter == null ? -1 : label.toLowerCase().indexOf(letter);
    if (at < 0) return label.replaceAll('&', '&&');
    return '${label.substring(0, at)}&${label.substring(at)}';
  }

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final String? currentArea = MenuLayout.areaOf(currentPath)?.id;
    return Material(
      color: colors.chrome,
      child: SizedBox(
        height: height,
        child: Row(children: [
          // The product's name is in the window's title bar (owner,
          // 2026-09-27), so the areas start at the left, Home first.
          const SizedBox(width: 8),
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
          // The gear opens the Settings page in a tab of its own rather than
          // a panel: with the set-up lists and Admin behind it there are too
          // many sections for one drop-down (backlog 72).
          if (settings != null)
            IconButton(
              key: const ValueKey('menu-area-settings'),
              tooltip: 'Settings',
              style: barIconStyle(context),
              onPressed: () => onOpenSetUp(null),
              icon: Icon(Icons.settings_outlined, color: colors.onChrome),
            ),
          if (profile != null) ...[
            const SizedBox(width: 6),
            profile!,
          ],
          const SizedBox(width: 10),
        ]),
      ),
    );
  }

  /// The text of an area on the bar and of an item in its drop-down: the
  /// wireframe's plain weight. A menu button's default is the semi-bold
  /// `labelLarge`, which made every entry read as a heading.
  static TextStyle? menuTextStyle(BuildContext context) =>
      Theme.of(context).textTheme.labelLarge?.copyWith(
            fontWeight: FontWeight.w400,
          );

  /// The areas that fit in [room]; the rest fold into More, from the right
  /// (4.11). An area costs its label as drawn, its padding and its arrow --
  /// measured, not guessed from the letters: a guess generous enough to be
  /// safe folded Reports and Admin away on a laptop where they fitted.
  Widget _areas(BuildContext context, double room, String? currentArea) {
    final AppSemanticColors colors = context.semanticColors;
    final TextStyle? style = menuTextStyle(context);
    final TextScaler scaler = MediaQuery.textScalerOf(context);
    double cost(MenuAreaSpec area) {
      final TextPainter painter = TextPainter(
        text: TextSpan(text: area.label, style: style),
        textDirection: TextDirection.ltr,
        textScaler: scaler,
      )..layout();
      final double arrow = area.items.length == 1 ? 0 : 20;
      return painter.width + 22 + arrow + 4;
    }

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
              menuStyle: panelStyle(context),
              menuChildren: [
                for (final MenuAreaSpec area in folded)
                  SubmenuButton(
                    style: ButtonStyle(
                      textStyle: WidgetStatePropertyAll(menuTextStyle(context)),
                    ),
                    menuStyle: panelStyle(context),
                    menuChildren: [_panel(area)],
                    child: MenuAcceleratorLabel(
                      acceleratorLabel(area.id, area.label),
                    ),
                  ),
              ],
              child: const MenuAcceleratorLabel('M&ore'),
            ),
        ],
      ),
    );
  }

  /// An area's drop-down. Its links to Settings name only the sections this
  /// person is offered there.
  Widget _panel(MenuAreaSpec area) => _AreaPanel(
        area: area,
        onOpen: onOpen,
        favourites: favourites,
        setUp: [
          for (final String section in area.setUp)
            if (settings?.groups.any((group) => group.label == section) ??
                false)
              section,
        ],
        onOpenSetUp: onOpenSetUp,
      );

  Widget _areaButton(BuildContext context, MenuAreaSpec area, bool current) {
    // An area of one screen (Home) opens it rather than a panel of one.
    if (area.items.length == 1) {
      final MenuItemSpec only = area.items.first;
      return MenuItemButton(
        key: ValueKey('menu-area-${area.id}'),
        style: _barButtonStyle(context, current),
        onPressed: () => onOpen(only),
        child: MenuAcceleratorLabel(acceleratorLabel(area.id, area.label)),
      );
    }
    return SubmenuButton(
      key: ValueKey('menu-area-${area.id}'),
      style: _barButtonStyle(context, current),
      menuStyle: panelStyle(context),
      menuChildren: [_panel(area)],
      // "Sell ▾": an area that drops a panel says so, as the wireframe does.
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        MenuAcceleratorLabel(acceleratorLabel(area.id, area.label)),
        const SizedBox(width: 2),
        const Icon(Icons.arrow_drop_down, size: 18),
      ]),
    );
  }

  ButtonStyle _barButtonStyle(BuildContext context, bool current) {
    final AppSemanticColors colors = context.semanticColors;
    return ButtonStyle(
      textStyle: WidgetStatePropertyAll(menuTextStyle(context)),
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

/// One area's drop-down (4.3), as the light menu draws it (backlog 72): the
/// area's daily list, "Returns & notes" opening its short list beside it,
/// and "All ... screens" one click away -- every group side by side, nothing
/// to scroll or expand. An area with no daily list shows every group at once.
class _AreaPanel extends StatefulWidget {
  const _AreaPanel({
    required this.area,
    required this.onOpen,
    required this.setUp,
    required this.onOpenSetUp,
    this.favourites,
  });

  final MenuAreaSpec area;
  final ValueChanged<MenuItemSpec> onOpen;
  final Favourites? favourites;

  /// The Settings sections linked from the foot, already cut to what the
  /// person is offered.
  final List<String> setUp;
  final ValueChanged<String?> onOpenSetUp;

  @override
  State<_AreaPanel> createState() => _AreaPanelState();
}

class _AreaPanelState extends State<_AreaPanel> {
  bool _all = false;
  bool _returns = false;

  @override
  Widget build(BuildContext context) {
    final MenuAreaSpec area = widget.area;
    final bool light = area.daily.isNotEmpty && !_all;
    final List<Widget> columns;
    if (light) {
      columns = [
        for (int i = 0; i < area.daily.length; i++) ...[
          _column(
            context,
            area.daily[i].label,
            [
              for (final String path in area.daily[i].paths)
                if (path == MenuLayout.returnsAndNotes)
                  _returnsToggle(context)
                else if (area.item(path) case final MenuItemSpec item)
                  _item(context, item),
            ],
          ),
          // The short list opens beside the column that names it.
          if (_returns &&
              area.daily[i].paths.contains(MenuLayout.returnsAndNotes))
            _column(
              context,
              'Returns & notes',
              [
                for (final String path in area.shortList)
                  if (area.item(path) case final MenuItemSpec item)
                    _item(context, item),
              ],
              key: const ValueKey('menu-returns-and-notes'),
            ),
        ],
      ];
    } else {
      final bool labelled =
          area.groups.length > 1 || area.groups.first.label != area.label;
      columns = [
        for (final MenuGroupSpec group in area.groups)
          _column(
            context,
            labelled ? group.label : null,
            [for (final MenuItemSpec item in group.items) _item(context, item)],
          ),
      ];
    }
    final List<Widget> foot = [
      if (light)
        _link(
          context,
          key: const ValueKey('menu-show-all'),
          label: 'All ${area.label} screens (${area.items.length})',
          trailing: Icons.chevron_right,
          onPressed: () => setState(() => _all = true),
        ),
      if (_all && area.daily.isNotEmpty)
        _link(
          context,
          key: const ValueKey('menu-show-daily'),
          label: 'Back to daily list',
          leading: Icons.chevron_left,
          onPressed: () => setState(() => _all = false),
        ),
      if (widget.setUp.isNotEmpty) ...[
        const SizedBox(width: 8),
        _caption(context, 'SET UP IN SETTINGS'),
        for (final String section in widget.setUp)
          MenuItemButton(
            key: ValueKey('menu-setup-$section'),
            style: _itemStyle(context, minWidth: 0),
            trailingIcon: const Icon(Icons.chevron_right, size: 16),
            onPressed: () => widget.onOpenSetUp(section),
            child: Text(section),
          ),
      ],
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
      child: IntrinsicWidth(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_all && area.daily.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: _caption(
                    context, 'ALL ${area.label.toUpperCase()} SCREENS'),
              ),
            Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: columns,
            ),
            if (foot.isNotEmpty) ...[
              const Divider(height: 13),
              // A menu button with an icon stretches its label to the width
              // it is given, and a row gives none.
              Row(mainAxisSize: MainAxisSize.min, children: [
                for (final Widget child in foot) IntrinsicWidth(child: child),
              ]),
            ],
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
              child: Text(
                'Ctrl+K finds any screen · Esc closes',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// "Returns & notes ▸": opens the short list beside it and keeps the panel
  /// open, as the wireframe's step 4 does.
  Widget _returnsToggle(BuildContext context) => MenuItemButton(
        key: const ValueKey('menu-returns-toggle'),
        closeOnActivate: false,
        style: _itemStyle(context),
        trailingIcon: Icon(
          _returns ? Icons.chevron_left : Icons.chevron_right,
          size: 18,
        ),
        onPressed: () => setState(() => _returns = !_returns),
        child: const Text('Returns & notes'),
      );

  /// A control of the panel itself, which changes what it shows rather than
  /// opening anything, so the panel stays open.
  Widget _link(
    BuildContext context, {
    required Key key,
    required String label,
    required VoidCallback onPressed,
    IconData? leading,
    IconData? trailing,
  }) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return MenuItemButton(
      key: key,
      closeOnActivate: false,
      style: _itemStyle(context, minWidth: 0).copyWith(
        foregroundColor: WidgetStatePropertyAll(scheme.primary),
        iconColor: WidgetStatePropertyAll(scheme.primary),
      ),
      leadingIcon: leading == null ? null : Icon(leading, size: 16),
      trailingIcon: trailing == null ? null : Icon(trailing, size: 16),
      onPressed: onPressed,
      child: Text(label),
    );
  }

  Widget _caption(BuildContext context, String text) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: Text(
        text,
        // The wireframe's h4: bold, tracked 0.08em.
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
          letterSpacing: .9,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  Widget _column(
    BuildContext context,
    String? label,
    List<Widget> items, {
    Key? key,
  }) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Padding(
      key: key,
      padding: const EdgeInsets.only(right: 16),
      child: IntrinsicWidth(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (label != null)
              Padding(
                // The wireframe: a heading stands at the column's edge and its
                // items one step in (item text 12 px in; the wireframe has 8).
                padding: const EdgeInsets.fromLTRB(0, 4, 12, 6),
                child: Text(
                  label.toUpperCase(),
                  // The wireframe's h4: bold, tracked 0.08em.
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                    letterSpacing: .9,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ...items,
          ],
        ),
      ),
    );
  }

  Widget _item(BuildContext context, MenuItemSpec item) {
    final Widget button = MenuItemButton(
      key: ValueKey('menu-item-${item.path}'),
      style: _itemStyle(context),
      onPressed: () => widget.onOpen(item),
      child: Text(item.label),
    );
    final Favourites? favourites = widget.favourites;
    if (favourites == null) return button;
    return _StarredItem(path: item.path, favourites: favourites, child: button);
  }

  ButtonStyle _itemStyle(BuildContext context, {double minWidth = 160}) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return ButtonStyle(
      textStyle: WidgetStatePropertyAll(AppMenuBar.menuTextStyle(context)),
      minimumSize: WidgetStatePropertyAll(Size(minWidth, 34)),
      // 4.14: a pointed-at item is outlined in the accent, not only tinted --
      // a tint alone is the faint hover D-QA-1 reported.
      shape: WidgetStateProperty.resolveWith((states) => RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(5),
            side: states.contains(WidgetState.hovered) ||
                    states.contains(WidgetState.focused)
                ? BorderSide(color: scheme.primary, width: 1.5)
                : BorderSide.none,
          )),
    );
  }
}

/// A drop-down item with its star (D-UI-3, the wireframe's step 7): a gold
/// star on a favourite, an outline one on any other item while it is pointed
/// at. Clicking the star keeps the panel open -- somebody starring their
/// screens stars several -- and opens nothing.
class _StarredItem extends StatefulWidget {
  const _StarredItem({
    required this.path,
    required this.favourites,
    required this.child,
  });

  final String path;
  final Favourites favourites;
  final Widget child;

  /// The gold of a starred screen, the wireframe's.
  static const Color gold = Color(0xFFE0A100);

  @override
  State<_StarredItem> createState() => _StarredItemState();
}

class _StarredItemState extends State<_StarredItem> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: ListenableBuilder(
          listenable: widget.favourites,
          builder: (context, _) {
            final bool starred = widget.favourites.contains(widget.path);
            return Row(children: [
              Expanded(child: widget.child),
              // The room is kept when no star shows, so the panel does not
              // change width under the pointer.
              SizedBox(
                width: 28,
                child: starred || _hovered
                    ? IconButton(
                        key: ValueKey('menu-star-${widget.path}'),
                        tooltip: starred
                            ? 'Remove from favourites'
                            : 'Add to favourites',
                        iconSize: 16,
                        padding: EdgeInsets.zero,
                        visualDensity: VisualDensity.compact,
                        onPressed: () => widget.favourites.toggle(widget.path),
                        icon: Icon(
                          starred ? Icons.star : Icons.star_border,
                          color: starred
                              ? _StarredItem.gold
                              : Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      )
                    : null,
              ),
            ]);
          },
        ),
      );
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
        // The wireframe's box: filled a shade lighter than the bar, no
        // edge, saying what it does and which keys open it.
        child: Container(
          height: 30,
          constraints: const BoxConstraints(minWidth: 240),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            color: colors.chromeActive,
            borderRadius: BorderRadius.circular(5),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Text('Search or jump to…', style: style),
            const SizedBox(width: 32),
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
    this.onChrome = true,
  });

  /// Drawn on the dark menu bar; false for the light bottom bar.
  final bool onChrome;

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
              border: onChrome
                  ? Border.all(color: colors.onChrome, width: 1)
                  : null,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            // The wireframe says it in lower case, beside the dot.
            state.toLowerCase(),
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: onChrome
                      ? colors.onChromeMuted
                      : Theme.of(context).colorScheme.onSurfaceVariant,
                ),
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

/// One look for every control on the right of the bar -- Appearance, the
/// gear, the profile: 30 px tall, 20 px icons, a 5 px-rounded pill that
/// lightens under the pointer, as the wireframe draws them. Three different
/// buttons had three different sizes and paddings (owner, 2026-09-26).
ButtonStyle barIconStyle(BuildContext context) {
  final AppSemanticColors colors = context.semanticColors;
  return ButtonStyle(
    foregroundColor: WidgetStatePropertyAll(colors.onChrome),
    iconColor: WidgetStatePropertyAll(colors.onChrome),
    iconSize: const WidgetStatePropertyAll(20),
    backgroundColor: WidgetStateProperty.resolveWith((states) =>
        states.contains(WidgetState.hovered) ||
                states.contains(WidgetState.focused) ||
                states.contains(WidgetState.pressed)
            ? colors.chromeActive
            : Colors.transparent),
    overlayColor: const WidgetStatePropertyAll(Colors.transparent),
    padding: const WidgetStatePropertyAll(EdgeInsets.zero),
    minimumSize: const WidgetStatePropertyAll(Size(32, 30)),
    maximumSize: const WidgetStatePropertyAll(Size(32, 30)),
    fixedSize: const WidgetStatePropertyAll(Size(32, 30)),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    visualDensity: VisualDensity.compact,
    shape: WidgetStatePropertyAll(
      RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
    ),
  );
}

/// The firm on the bar, as the wireframe draws it: the same 30 px as the
/// search box beside it, a thin edge, 5 px corners, the name -- and a ▾ only
/// when there is a firm to switch to.
class FirmOnBar extends StatelessWidget {
  const FirmOnBar({super.key, required this.name, this.onSwitch});

  final String name;

  /// Opens the firm picker; null when there is nothing to switch to.
  final VoidCallback? onSwitch;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors colors = context.semanticColors;
    final Widget box = Container(
      key: const ValueKey('firm-on-bar'),
      height: 30,
      // The wireframe's cap: a long firm name is trimmed rather than pushing
      // menu areas into More.
      constraints: const BoxConstraints(maxWidth: 180),
      padding: EdgeInsets.only(left: 10, right: onSwitch == null ? 10 : 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: colors.onChromeMuted.withValues(alpha: .45)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Flexible(
          child: Text(
            name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: colors.onChrome),
          ),
        ),
        if (onSwitch != null)
          Icon(Icons.arrow_drop_down, size: 18, color: colors.onChrome),
      ]),
    );
    if (onSwitch == null) return Tooltip(message: name, child: box);
    return Tooltip(
      message: 'Switch firm',
      child: InkWell(
        onTap: onSwitch,
        borderRadius: BorderRadius.circular(5),
        hoverColor: colors.chromeActive,
        child: box,
      ),
    );
  }
}

/// The wireframe's drop-down panel: the page's white, a light grey edge, the
/// corners rounded, a soft shadow -- not the framework's default frame, which
/// drew a heavy dark border round every panel.
MenuStyle panelStyle(BuildContext context) {
  final ColorScheme scheme = Theme.of(context).colorScheme;
  return MenuStyle(
    backgroundColor: WidgetStatePropertyAll(scheme.surfaceContainerLowest),
    surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
    elevation: const WidgetStatePropertyAll(6),
    shadowColor: WidgetStatePropertyAll(Colors.black.withValues(alpha: .25)),
    padding: const WidgetStatePropertyAll(EdgeInsets.zero),
    side: WidgetStatePropertyAll(BorderSide(color: scheme.outlineVariant)),
    shape: WidgetStatePropertyAll(
      RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
  );
}
