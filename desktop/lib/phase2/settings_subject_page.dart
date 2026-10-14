import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';
import '../models/settings_sections.dart';
import 'menu_layout.dart';
import 'settings_subject.dart';
import 'phase2_scope.dart';

/// One subject of Settings as one screen (backlog 148): a Start here tab that
/// says how far the firm has got, the subject's steps in the order they are
/// set up in, and its checking tools set apart at the end of the strip.
///
/// **It reads the server once.** [loadState] is called when the screen opens
/// and never again -- not per step, not on switching tabs -- until somebody
/// presses Refresh or Retry. Each step's screen is whatever [screenFor]
/// hands back for its item, built the first time its tab is shown and then
/// kept, so a half-typed form survives a look at another tab.
class SettingsSubjectPage extends StatefulWidget {
  const SettingsSubjectPage({
    super.key,
    required this.subject,
    required this.visible,
    required this.loadState,
    required this.screenFor,
    required this.openWindow,
  });

  final SettingsSubject subject;

  /// The section's items this person is offered: a step or a tool that is
  /// not among them gets no tab and no row.
  final List<MenuItemSpec> visible;

  final Future<SettingsSectionState> Function() loadState;

  /// Today's screen for a step that is a screen.
  final Widget Function(MenuItemSpec item) screenFor;

  /// Opens a step that is a window, the way the menu would.
  final void Function(MenuItemSpec item) openWindow;

  @override
  State<SettingsSubjectPage> createState() => _SettingsSubjectPageState();
}

class _SettingsSubjectPageState extends State<SettingsSubjectPage>
    with ReadsAgainWhenShown<SettingsSubjectPage> {
  /// Shown again by the shell: read as Refresh would (D-UI-101).
  @override
  void readAgain() {
    if (!_loading) _read();
  }

  /// The tab on show: null is Start here, otherwise a step's path.
  String? _tab;

  /// The tabs shown so far, whose screens are kept.
  final Set<String> _visited = {};

  SettingsSectionState? _state;
  bool _loading = false;
  bool _failed = false;
  int _reads = 0;

  @override
  void initState() {
    super.initState();
    _loading = true;
    _load();
  }

  /// Refresh and Retry: the one call, made again because somebody asked.
  void _read() {
    setState(() {
      _loading = true;
      _failed = false;
    });
    _load();
  }

  Future<void> _load() async {
    final int read = ++_reads;
    try {
      final SettingsSectionState state = await widget.loadState();
      if (!mounted || read != _reads) return;
      setState(() {
        _state = state;
        _loading = false;
      });
    } catch (_) {
      if (!mounted || read != _reads) return;
      setState(() {
        _state = null;
        _loading = false;
        _failed = true;
      });
    }
  }

  bool _offered(SubjectStep step) =>
      widget.visible.any((item) => item.path == step.path);

  List<SubjectStep> get _steps =>
      widget.subject.steps.where(_offered).toList();

  List<SubjectStep> get _tools =>
      widget.subject.tools.where(_offered).toList();

  void _show(String? path) => setState(() {
        _tab = path;
        if (path != null) _visited.add(path);
      });

  String _tabLabel(SubjectStep step) => step.code == null
      ? '${widget.subject.toolsLabel}: ${step.label}'
      : '${widget.subject.numberOf(step)} ${step.label}';

  @override
  Widget build(BuildContext context) {
    final List<SubjectStep> steps = _steps;
    final List<SubjectStep> tools = _tools;
    final List<SubjectStep> entries = [...steps, ...tools];
    final int index =
        1 + entries.indexWhere((step) => step.path == _tab).clamp(-1, 99);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _strip(context, steps, tools),
        const Divider(height: 1),
        Expanded(
          child: IndexedStack(
            index: index,
            sizing: StackFit.expand,
            children: [
              _startHere(context, steps, tools),
              for (final SubjectStep step in entries)
                _visited.contains(step.path)
                    ? _stepBody(context, step)
                    : const SizedBox.shrink(),
            ],
          ),
        ),
      ],
    );
  }

  /// The tab strip. It scrolls sideways rather than overflow, and on a
  /// window wide enough the tools stand at its right end.
  Widget _strip(
    BuildContext context,
    List<SubjectStep> steps,
    List<SubjectStep> tools,
  ) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerLow,
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          key: const ValueKey('subject-strip'),
          scrollDirection: Axis.horizontal,
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _tabButton(context, null, 'Start here'),
                    for (final SubjectStep step in steps)
                      _tabButton(context, step.path, _tabLabel(step)),
                  ],
                ),
                if (tools.isNotEmpty)
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const SizedBox(width: AppSpacing.xl),
                      for (final SubjectStep tool in tools)
                        _tabButton(context, tool.path, _tabLabel(tool)),
                    ],
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _tabButton(BuildContext context, String? path, String label) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final bool selected = _tab == path;
    return InkWell(
      key: ValueKey('subject-tab-${path ?? 'start'}'),
      onTap: () => _show(path),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm + 2,
        ),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              width: 2,
              color: selected ? scheme.primary : scheme.surfaceContainerLow,
            ),
          ),
        ),
        child: Text(
          label,
          maxLines: 1,
          softWrap: false,
          style: theme.textTheme.labelLarge?.copyWith(
            color: selected ? scheme.primary : scheme.onSurfaceVariant,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
          ),
        ),
      ),
    );
  }

  Widget _startHere(
    BuildContext context,
    List<SubjectStep> steps,
    List<SubjectStep> tools,
  ) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final SettingsSubject subject = widget.subject;
    final SettingsSectionState? state = _state;
    // Counted over the steps this person is shown, so the note never
    // promises a step that has no row.
    final int todo = state == null
        ? 0
        : steps
            .where((step) => state.step(step.code ?? '')?.isTodo ?? false)
            .length;
    final TextStyle? muted =
        theme.textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant);
    return ListView(
      key: const ValueKey('subject-start'),
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xl),
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (_failed) ...[
                    Text(
                      'The states of these steps could not be read.',
                      key: const ValueKey('subject-note'),
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'Every step still opens. Retry to see how far this '
                      'firm has got.',
                      style: muted,
                    ),
                  ] else if (state == null)
                    Text(
                      'Reading how far this firm has got…',
                      key: const ValueKey('subject-note'),
                      style: theme.textTheme.titleMedium,
                    )
                  else if (todo == 0) ...[
                    Text(
                      subject.readyNote,
                      key: const ValueKey('subject-note'),
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(subject.readyDetail, style: muted),
                  ] else ...[
                    Text(
                      todo == 1 ? '1 step to do.' : '$todo steps to do.',
                      key: const ValueKey('subject-note'),
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'Do them in order: each step says what it needs from '
                      'the one before.',
                      style: muted,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            if (_failed)
              OutlinedButton(
                key: const ValueKey('subject-retry'),
                onPressed: _loading ? null : _read,
                child: const Text('Retry'),
              )
            else
              IconButton(
                key: const ValueKey('subject-refresh'),
                tooltip: 'Refresh',
                onPressed: _loading ? null : _read,
                icon: _loading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh, size: 20),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.lg),
        for (final SubjectStep step in steps) ...[
          _stepRow(context, step, state?.step(step.code ?? '')),
          const SizedBox(height: AppSpacing.sm),
        ],
        if (subject.connects.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          Text('How they connect', style: theme.textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          Text(
            subject.connects.join(' → '),
            key: const ValueKey('subject-connects'),
            style: theme.textTheme.bodyMedium,
          ),
        ],
        if (subject.connectsNote.isNotEmpty && tools.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(subject.connectsNote, style: muted),
        ],
        if (tools.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              for (final SubjectStep tool in tools)
                Tooltip(
                  message: tool.summary,
                  child: TextButton(
                    key: ValueKey('subject-open-${tool.path}'),
                    onPressed: () => _show(tool.path),
                    child: Text(_tabLabel(tool)),
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _stepRow(
    BuildContext context,
    SubjectStep step,
    SettingsStepState? state,
  ) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Material(
      key: ValueKey('subject-row-${step.path}'),
      color: scheme.surfaceContainerLowest,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: scheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CircleAvatar(
              radius: 13,
              backgroundColor: scheme.secondaryContainer,
              foregroundColor: scheme.onSecondaryContainer,
              child: Text(
                '${widget.subject.numberOf(step)}',
                style: theme.textTheme.labelMedium,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: AppSpacing.sm,
                    runSpacing: AppSpacing.xs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(step.label, style: theme.textTheme.titleSmall),
                      if (state != null) _chip(context, step, state),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    step.summary,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: scheme.onSurfaceVariant),
                  ),
                  if (state != null && state.detail.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      state.detail,
                      key: ValueKey('subject-detail-${step.code}'),
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            OutlinedButton(
              key: ValueKey('subject-open-${step.path}'),
              onPressed: () => _show(step.path),
              child: const Text('Open'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _chip(
    BuildContext context,
    SubjectStep step,
    SettingsStepState state,
  ) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final AppSemanticColors colors = context.semanticColors;
    final (String label, Color fill, Color ink) = switch (state.state) {
      SettingsStepState.done => ('Done', colors.success, colors.onSuccess),
      SettingsStepState.todo => ('To do', colors.warning, colors.onWarning),
      _ => (
          'Optional',
          scheme.surfaceContainerHighest,
          scheme.onSurfaceVariant,
        ),
    };
    return Container(
      key: ValueKey('subject-chip-${step.code}'),
      padding:
          const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 2),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(color: ink),
      ),
    );
  }

  /// A step's tab: what it is for on top, and beneath it today's screen, or
  /// for a step that is a window the button that opens it.
  Widget _stepBody(BuildContext context, SubjectStep step) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final MenuItemSpec item = step.item;
    final Widget top = Material(
      color: scheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        child: Align(
          alignment: Alignment.centerLeft,
          child: Text(
            step.topLine,
            key: ValueKey('subject-top-${step.path}'),
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: scheme.onSurfaceVariant),
          ),
        ),
      ),
    );
    if (!item.isSetting) {
      return Column(
        key: ValueKey('subject-body-${step.path}'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          top,
          const Divider(height: 1),
          Expanded(child: widget.screenFor(item)),
        ],
      );
    }
    final SettingsStepState? state = _state?.step(step.code ?? '');
    return Column(
      key: ValueKey('subject-body-${step.path}'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        top,
        const Divider(height: 1),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              Text(step.summary, style: theme.textTheme.bodyLarge),
              if (state != null && state.detail.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Now: ${state.detail}',
                  key: ValueKey('subject-window-detail-${step.code}'),
                  style: theme.textTheme.bodyMedium,
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton(
                  key: ValueKey('subject-window-${step.path}'),
                  onPressed: () => widget.openWindow(item),
                  child: Text('Open ${step.label}'),
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Opens as a window. What it says here is as it was when '
                'this screen opened; Refresh on Start here reads it again.',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
