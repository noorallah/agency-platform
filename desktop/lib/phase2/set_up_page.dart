import 'package:flutter/material.dart';

import 'menu_layout.dart';

/// Settings, behind the gear (backlog 72, owner-approved 2026-10-04): the
/// firm's settings as before, then SET UP -- the lists the menus carried
/// until the light menu -- and PLATFORM, what the Admin area held. Sections
/// down the left, the chosen one's items as cards, and a search across all of
/// them.
///
/// **It asks the server nothing.** [settings] is the menu catalogue already
/// cut to the permissions held since sign-in ([MenuLayout.visible]); a card
/// opens its screen in a tab, or its dialog, exactly as the menu would.
class SetUpPage extends StatefulWidget {
  const SetUpPage({
    super.key,
    required this.settings,
    required this.onOpen,
    this.section,
    this.onSection,
  });

  /// The sections this person is offered, or null for none.
  final MenuAreaSpec? settings;

  /// The section to show first; the first offered when null or not offered.
  final String? section;
  final ValueChanged<MenuItemSpec> onOpen;

  /// Told the section a person chose, so whoever shows this page can hand it
  /// back as [section]: the page is rebuilt each time its tab is returned
  /// to, and without this it opened on the first section again (D-UI-92).
  final ValueChanged<String>? onSection;

  @override
  State<SetUpPage> createState() => _SetUpPageState();
}

class _SetUpPageState extends State<SetUpPage> {
  final TextEditingController _search = TextEditingController();
  String? _section;

  @override
  void initState() {
    super.initState();
    _section = widget.section;
  }

  @override
  void didUpdateWidget(SetUpPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A link from a drop-down names a section; the page is already open.
    if (widget.section != oldWidget.section && widget.section != null) {
      _section = widget.section;
      _search.clear();
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<MenuGroupSpec> groups = widget.settings?.groups ?? const [];
    if (groups.isEmpty) {
      return Center(
        child: Text(
          'Nothing here for your role.',
          style: theme.textTheme.bodyLarge,
        ),
      );
    }
    final MenuGroupSpec current = groups.firstWhere(
      (group) => group.label == _section,
      orElse: () => groups.first,
    );
    final String query = _search.text.trim().toLowerCase();
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          width: 230,
          // A Material rather than a coloured box: the section tiles paint
          // their highlight on it.
          child: Material(
            color: theme.colorScheme.surfaceContainerLow,
            shape: Border(
              right: BorderSide(color: theme.colorScheme.outlineVariant),
            ),
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                for (final MenuPart part in MenuPart.values)
                  if (groups.any((group) => group.part == part)) ...[
                    _partHeading(context, part),
                    for (final MenuGroupSpec group in groups)
                      if (group.part == part)
                        _sectionTile(
                          context,
                          group,
                          selected: query.isEmpty && group == current,
                        ),
                  ],
              ],
            ),
          ),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420),
                  child: TextField(
                    key: const ValueKey('setup-search'),
                    controller: _search,
                    onChanged: (_) => setState(() {}),
                    decoration: InputDecoration(
                      isDense: true,
                      prefixIcon: const Icon(Icons.search, size: 18),
                      hintText: 'Search settings…',
                      border: const OutlineInputBorder(),
                      suffixIcon: query.isEmpty
                          ? null
                          : IconButton(
                              tooltip: 'Clear',
                              icon: const Icon(Icons.close, size: 18),
                              onPressed: () =>
                                  setState(() => _search.clear()),
                            ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              if (query.isEmpty)
                ..._sectionBody(context, current)
              else
                ..._results(context, groups, query),
            ],
          ),
        ),
      ],
    );
  }

  Widget _partHeading(BuildContext context, MenuPart part) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        part.label.toUpperCase(),
        style: theme.textTheme.labelSmall?.copyWith(
          color: theme.colorScheme.onSurfaceVariant,
          letterSpacing: .9,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  Widget _sectionTile(
    BuildContext context,
    MenuGroupSpec group, {
    required bool selected,
  }) =>
      ListTile(
        key: ValueKey('setup-section-${group.label}'),
        dense: true,
        visualDensity: VisualDensity.compact,
        selected: selected,
        selectedTileColor: Theme.of(context).colorScheme.secondaryContainer,
        title: Text(group.label),
        onTap: () {
          setState(() {
            _section = group.label;
            _search.clear();
          });
          widget.onSection?.call(group.label);
        },
      );

  /// One section: its heading, where it came from, its cards.
  List<Widget> _sectionBody(BuildContext context, MenuGroupSpec group) {
    final ThemeData theme = Theme.of(context);
    return [
      Text(group.label, style: theme.textTheme.titleLarge),
      const SizedBox(height: 4),
      Text(
        '${group.part.note} Each opens in its own tab, or as a window.',
        style: theme.textTheme.bodySmall
            ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
      ),
      const SizedBox(height: 12),
      _cards(context, group.items),
    ];
  }

  /// What the search finds, under the section each item is in.
  List<Widget> _results(
    BuildContext context,
    List<MenuGroupSpec> groups,
    String query,
  ) {
    final ThemeData theme = Theme.of(context);
    bool matches(MenuGroupSpec group, MenuItemSpec item) =>
        item.label.toLowerCase().contains(query) ||
        group.label.toLowerCase().contains(query);
    final List<Widget> found = [
      for (final MenuGroupSpec group in groups)
        if (group.items.any((item) => matches(group, item))) ...[
          Padding(
            padding: const EdgeInsets.only(bottom: 8, top: 4),
            child: Text(
              group.label.toUpperCase(),
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                letterSpacing: .9,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          _cards(context, [
            for (final MenuItemSpec item in group.items)
              if (matches(group, item)) item,
          ]),
          const SizedBox(height: 12),
        ],
    ];
    if (found.isNotEmpty) return found;
    return [
      Text(
        'No setting matches "${_search.text.trim()}".',
        style: theme.textTheme.bodyMedium,
      ),
    ];
  }

  Widget _cards(BuildContext context, List<MenuItemSpec> items) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: [
        for (final MenuItemSpec item in items)
          SizedBox(
            width: 220,
            child: Material(
              color: scheme.surfaceContainerLowest,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: BorderSide(color: scheme.outlineVariant),
              ),
              child: InkWell(
                key: ValueKey('setup-card-${item.path}'),
                borderRadius: BorderRadius.circular(8),
                onTap: () => widget.onOpen(item),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.label,
                        style: theme.textTheme.titleSmall,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        item.isSetting ? 'Opens a window' : 'Opens a screen',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: scheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
