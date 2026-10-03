import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/design/design_tokens.dart';
import '../core/preferences/desktop_preferences_service.dart';
import '../models/entities.dart';
import '../ui/workspace/save_in_dialog.dart';
import 'display_dates.dart';

/// A screen My preferences offers as the first one: its router path and what
/// the menu calls it.
typedef FirstScreenChoice = ({String path, String label});

/// What the person changed in My preferences. A null field did not move;
/// [firstScreen] is [MyPreferences.lastScreen] for "the screen I was last on".
class MyPreferencesChange {
  const MyPreferencesChange({
    this.startInFirmId,
    this.firstScreen,
    this.themeMode,
    this.textSize,
    this.dateFormat,
  });

  final String? startInFirmId;
  final String? firstScreen;
  final String? themeMode;
  final AppTextSize? textSize;
  final String? dateFormat;

  bool get isEmpty =>
      startInFirmId == null &&
      firstScreen == null &&
      themeMode == null &&
      textSize == null &&
      dateFormat == null;
}

/// The values My preferences opens with -- all of them already in memory,
/// so opening it asks the server nothing (backlog 72, owner 2026-10-04).
class MyPreferences {
  const MyPreferences({
    required this.startInFirmId,
    required this.firstScreen,
    required this.themeMode,
    required this.textSize,
    required this.dateFormat,
  });

  /// [firstScreen] when the person starts where they left off -- the
  /// default, and how every session opened before there was a choice.
  static const String lastScreen = '';

  /// What `dashboard_layout` keeps the first screen under. In the layout
  /// rather than in `default_landing_page`, which records the last screen
  /// on every move and would overwrite a choice within a click.
  static const String layoutKey = 'first_screen';

  /// The first screen stored in [layout], or [lastScreen].
  static String firstScreenIn(Map<String, dynamic>? layout) {
    final Object? stored = layout?[layoutKey];
    return stored is String ? stored : lastScreen;
  }

  final String? startInFirmId;
  final String firstScreen;
  final String themeMode;
  final AppTextSize textSize;
  final String dateFormat;
}

/// My preferences (backlog 73, step 9 of the branding wireframes): what is
/// the person's own in one place -- the firm they start in, the first
/// screen, theme, text size and date format.
///
/// Opening it costs no request. Saving sends **one** preferences update with
/// only what changed, plus the primary-firm call when Start in firm moved
/// (that is a membership flag, not a preference); text size is this PC's and
/// costs none. The save runs inside the dialog, which stays open with the
/// server's message on a refusal (D-DLG-1).
///
/// Rows per page, drawn on the wireframe, is left out: no screen reads it
/// yet, and a setting that changes nothing is worse than none.
class MyPreferencesDialog extends StatefulWidget {
  const MyPreferencesDialog({
    super.key,
    required this.current,
    required this.firms,
    required this.screens,
    required this.onSave,
    this.offerStartInFirm = true,
  });

  final MyPreferences current;

  /// The firms this person is a member of.
  final List<AssignedFirm> firms;

  /// Whether Start in firm is shown: somebody with one firm has no choice
  /// to make, and a platform administrator always starts in none.
  final bool offerStartInFirm;

  /// The screens this person may open, for First screen.
  final List<FirstScreenChoice> screens;
  final Future<void> Function(MyPreferencesChange change) onSave;

  @override
  State<MyPreferencesDialog> createState() => _MyPreferencesDialogState();
}

class _MyPreferencesDialogState extends State<MyPreferencesDialog>
    with SaveInDialog<MyPreferencesDialog> {
  late String? _firm = widget.current.startInFirmId;
  late String _firstScreen = widget.current.firstScreen;
  late String _themeMode = widget.current.themeMode;
  late AppTextSize _textSize = widget.current.textSize;
  late String _dateFormat = DisplayDates.formats
          .contains(widget.current.dateFormat)
      ? widget.current.dateFormat
      : DisplayDates.defaultFormat;

  static const Map<String, String> _themes = {
    'light': 'Light',
    'dark': 'Dark',
    'system': 'Follow Windows',
  };

  MyPreferencesChange get _change {
    final MyPreferences was = widget.current;
    return MyPreferencesChange(
      startInFirmId: widget.offerStartInFirm &&
              _firm != null &&
              _firm != was.startInFirmId
          ? _firm
          : null,
      firstScreen: _firstScreen == was.firstScreen ? null : _firstScreen,
      themeMode: _themeMode == was.themeMode ? null : _themeMode,
      textSize: _textSize == was.textSize ? null : _textSize,
      dateFormat: _dateFormat == was.dateFormat ? null : _dateFormat,
    );
  }

  /// Nothing changed closes without a request.
  Future<void> _save() async {
    final MyPreferencesChange change = _change;
    if (change.isEmpty) {
      Navigator.pop(context, false);
      return;
    }
    await saveAndClose<bool>(() async {
      await widget.onSave(change);
      return true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<FirstScreenChoice> screens = [
      (path: MyPreferences.lastScreen, label: 'The screen I was last on'),
      ...widget.screens,
    ];
    // A stored screen this person may no longer open reads as the default.
    final String firstScreen = screens.any((s) => s.path == _firstScreen)
        ? _firstScreen
        : MyPreferences.lastScreen;
    final DateTime today = DateTime.now();
    Widget field(Widget child, String? help) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: help == null
              ? child
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    child,
                    Padding(
                      padding: const EdgeInsets.only(
                          top: AppSpacing.xs, left: AppSpacing.sm),
                      child: Text(help, style: theme.textTheme.bodySmall),
                    ),
                  ],
                ),
        );
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.enter): () {
          if (!saving) _save();
        },
      },
      child: AlertDialog(
        title: const Text('My preferences'),
        content: SizedBox(
          width: 580,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                saveErrorBanner(),
                if (widget.offerStartInFirm)
                  field(
                    DropdownButtonFormField<String>(
                      key: const ValueKey('prefs-start-in-firm'),
                      autofocus: true,
                      isExpanded: true,
                      initialValue: widget.firms.any((f) => f.id == _firm)
                          ? _firm
                          : null,
                      hint: const Text('Not set'),
                      decoration:
                          const InputDecoration(labelText: 'Start in firm'),
                      items: [
                        for (final AssignedFirm firm in widget.firms)
                          DropdownMenuItem(
                            value: firm.id,
                            child: Text(firm.name,
                                overflow: TextOverflow.ellipsis),
                          ),
                      ],
                      onChanged: saving
                          ? null
                          : (value) => setState(() => _firm = value),
                    ),
                    'Lists only the firms you are a member of.',
                  ),
                field(
                  DropdownButtonFormField<String>(
                    key: const ValueKey('prefs-first-screen'),
                    autofocus: !widget.offerStartInFirm,
                    isExpanded: true,
                    menuMaxHeight: 360,
                    initialValue: firstScreen,
                    decoration:
                        const InputDecoration(labelText: 'First screen'),
                    items: [
                      for (final FirstScreenChoice screen in screens)
                        DropdownMenuItem(
                          value: screen.path,
                          child: Text(screen.label,
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) => setState(() =>
                            _firstScreen = value ?? MyPreferences.lastScreen),
                  ),
                  'Only screens your role may open.',
                ),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: field(
                        DropdownButtonFormField<String>(
                          key: const ValueKey('prefs-theme'),
                          isExpanded: true,
                          initialValue: _themes.containsKey(_themeMode)
                              ? _themeMode
                              : 'system',
                          decoration:
                              const InputDecoration(labelText: 'Theme'),
                          items: [
                            for (final MapEntry<String, String> entry
                                in _themes.entries)
                              DropdownMenuItem(
                                value: entry.key,
                                child: Text(entry.value),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (value) => setState(
                                  () => _themeMode = value ?? _themeMode),
                        ),
                        null,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: field(
                        DropdownButtonFormField<AppTextSize>(
                          key: const ValueKey('prefs-text-size'),
                          isExpanded: true,
                          initialValue: _textSize,
                          decoration:
                              const InputDecoration(labelText: 'Text size'),
                          items: [
                            for (final AppTextSize size in AppTextSize.values)
                              DropdownMenuItem(
                                value: size,
                                child: Text(size.label),
                              ),
                          ],
                          onChanged: saving
                              ? null
                              : (value) => setState(
                                  () => _textSize = value ?? _textSize),
                        ),
                        'This PC only.',
                      ),
                    ),
                  ],
                ),
                field(
                  DropdownButtonFormField<String>(
                    key: const ValueKey('prefs-date-format'),
                    isExpanded: true,
                    initialValue: _dateFormat,
                    decoration:
                        const InputDecoration(labelText: 'Date format'),
                    items: [
                      for (final String format in DisplayDates.formats)
                        DropdownMenuItem(
                          value: format,
                          child: Text(
                              '${DisplayDates.write(today, format)}  ·  $format'),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) =>
                            setState(() => _dateFormat = value ?? _dateFormat),
                  ),
                  null,
                ),
                Text(
                  'Yours on every PC you sign in to, except text size. '
                  'Switching firm from the bar is for this session; '
                  'Start in firm is for next time. Your favourites are '
                  'kept with these.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: saving ? null : () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            key: const ValueKey('prefs-save'),
            onPressed: saving ? null : _save,
            child: Text(saving ? 'Saving…' : 'Save'),
          ),
        ],
      ),
    );
  }
}
