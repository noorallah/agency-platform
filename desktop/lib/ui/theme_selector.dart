import 'package:flutter/material.dart';

import '../core/preferences/desktop_preferences_service.dart';
import '../core/theme/theme_manager.dart';

/// Appearance controls: how bright, which accent, and whether to raise contrast.
///
/// This used to be one flat list of five values that meant different things --
/// picking "Blue" silently also picked light, and picking "High Contrast"
/// silently also picked dark. They are three independent choices and are now
/// presented as three.
class ThemeSelector extends StatelessWidget {
  const ThemeSelector({super.key, required this.manager, this.compact = true});

  final ThemeManager manager;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final Widget button = MenuAnchor(
      menuChildren: [
        const _SectionLabel('Appearance'),
        for (final ThemeMode mode in ThemeMode.values)
          MenuItemButton(
            leadingIcon: Icon(
              _modeIcon(mode),
              size: 18,
              color: manager.mode == mode
                  ? Theme.of(context).colorScheme.primary
                  : null,
            ),
            trailingIcon: manager.mode == mode ? const Icon(Icons.check, size: 16) : null,
            onPressed: () => manager.selectMode(mode),
            child: Text(mode.label),
          ),
        const Divider(height: 8),
        const _SectionLabel('Accent'),
        for (final AppPalette palette in AppPalette.values)
          MenuItemButton(
            leadingIcon: _Swatch(color: palette.seed),
            trailingIcon:
                manager.palette == palette ? const Icon(Icons.check, size: 16) : null,
            onPressed: () => manager.selectPalette(palette),
            child: Text(palette.label),
          ),
        const Divider(height: 8),
        const _SectionLabel('Density'),
        for (final GridDensity density in GridDensity.values)
          MenuItemButton(
            leadingIcon: Icon(_densityIcon(density), size: 18),
            trailingIcon:
                manager.density == density ? const Icon(Icons.check, size: 16) : null,
            onPressed: () => manager.selectDensity(density),
            child: Text(_densityLabel(density)),
          ),
        const Divider(height: 8),
        MenuItemButton(
          leadingIcon: const Icon(Icons.contrast, size: 18),
          trailingIcon:
              manager.highContrast ? const Icon(Icons.check, size: 16) : null,
          onPressed: () => manager.setHighContrast(!manager.highContrast),
          child: const Text('Higher contrast'),
        ),
      ],
      builder: (context, controller, child) => IconButton(
        tooltip: 'Appearance',
        icon: const Icon(Icons.palette_outlined),
        onPressed: () =>
            controller.isOpen ? controller.close() : controller.open(),
      ),
    );

    if (compact) return button;
    return InputDecorator(
      decoration: const InputDecoration(labelText: 'Appearance'),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Expanded(child: Text(_summary())),
          button,
        ],
      ),
    );
  }

  String _summary() {
    final String contrast = manager.highContrast ? ', higher contrast' : '';
    return '${manager.mode.label} · ${manager.palette.label}$contrast';
  }

  static String _densityLabel(GridDensity density) => switch (density) {
        GridDensity.compact => 'Compact — more rows',
        GridDensity.comfortable => 'Comfortable',
        GridDensity.spacious => 'Spacious — easier to read',
      };

  static IconData _densityIcon(GridDensity density) => switch (density) {
        GridDensity.compact => Icons.density_small,
        GridDensity.comfortable => Icons.density_medium,
        GridDensity.spacious => Icons.density_large,
      };

  static IconData _modeIcon(ThemeMode mode) => switch (mode) {
        ThemeMode.system => Icons.brightness_auto_outlined,
        ThemeMode.light => Icons.light_mode_outlined,
        ThemeMode.dark => Icons.dark_mode_outlined,
      };
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
        child: Text(text, style: Theme.of(context).textTheme.labelSmall),
      );
}

class _Swatch extends StatelessWidget {
  const _Swatch({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        width: 16,
        height: 16,
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        ),
      );
}
