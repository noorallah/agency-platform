import 'package:flutter/material.dart';

import '../core/theme/theme_manager.dart';

class ThemeSelector extends StatelessWidget {
  const ThemeSelector({super.key, required this.manager, this.compact = true});

  final ThemeManager manager;
  final bool compact;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: manager,
        builder: (context, _) => PopupMenuButton<AppTheme>(
          tooltip: 'Choose theme',
          icon: const Icon(Icons.palette_outlined),
          onSelected: (theme) => manager.select(theme),
          itemBuilder: (context) => AppTheme.values
              .map(
                (theme) => CheckedPopupMenuItem(
                  value: theme,
                  checked: manager.current == theme,
                  child: Text(theme.label),
                ),
              )
              .toList(),
          child: compact
              ? null
              : InputDecorator(
                  decoration: const InputDecoration(labelText: 'Theme'),
                  child: Text(manager.current.label),
                ),
        ),
      );
}
