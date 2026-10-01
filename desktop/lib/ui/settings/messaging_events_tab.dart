import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/messaging.dart';
import '../workspace/save_in_dialog.dart';
import 'messaging_channels_tab.dart' show messagingChannelNames;

/// Which channels each event goes out on, in the order they are tried.
///
/// The first channel that can reach the customer wins; the others are the
/// fallback. An event with no channel sends nothing.
class MessagingEventsTab extends StatefulWidget {
  const MessagingEventsTab({
    super.key,
    required this.api,
    required this.mayChange,
  });

  final ApiClient api;
  final bool mayChange;

  @override
  State<MessagingEventsTab> createState() => _MessagingEventsTabState();
}

class _MessagingEventsTabState extends State<MessagingEventsTab> {
  List<EventConfig> _configs = const [];
  List<MessagingEvent> _events = const [];
  bool _loading = true;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final List<MessagingEvent> events = await widget.api.messagingEvents();
      final List<EventConfig> configs =
          await widget.api.messagingEventConfigs();
      if (!mounted) return;
      setState(() {
        _events = events;
        _configs = configs;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _loadError = error.message;
        _loading = false;
      });
    }
  }

  MessagingEvent? _eventFor(String code) {
    for (final MessagingEvent event in _events) {
      if (event.code == code) return event;
    }
    return null;
  }

  Future<void> _edit(EventConfig config) async {
    final MessagingEvent? event = _eventFor(config.eventCode);
    if (event == null) return;
    final EventConfig? saved = await showDialog<EventConfig>(
      context: context,
      builder: (_) => MessagingEventDialog(
        api: widget.api,
        config: config,
        event: event,
      ),
    );
    if (saved == null || !mounted) return;
    setState(() {
      _configs = [
        for (final EventConfig existing in _configs)
          if (existing.eventCode == saved.eventCode) saved else existing,
      ];
    });
    NotificationService.show(
      context,
      '${saved.label} saved.',
      kind: AppNotificationKind.success,
    );
  }

  String _route(EventConfig config) {
    if (config.channels.isEmpty) return 'Off';
    return config.channels
        .map((rule) =>
            (messagingChannelNames[rule.channel] ?? rule.channel) +
            (rule.isEnabled ? '' : ' (off)'))
        .join('  →  ');
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_loadError != null) {
      return Text(
        _loadError!,
        style:
            theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
      );
    }
    return ListView(
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: Text(
            'Channels are tried in the order shown; the first that can reach '
            'the customer sends.',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
        for (final EventConfig config in _configs)
          ListTile(
            key: ValueKey('messaging-event-${config.eventCode}'),
            dense: true,
            title: Text(config.label),
            subtitle: Text(
              _route(config),
              key: ValueKey('messaging-event-route-${config.eventCode}'),
            ),
            trailing: TextButton(
              key: ValueKey('messaging-event-edit-${config.eventCode}'),
              onPressed:
                  widget.mayChange ? () => unawaited(_edit(config)) : null,
              child: const Text('Edit'),
            ),
          ),
      ],
    );
  }
}

/// One channel row being edited, with the text boxes it needs.
class _RuleDraft {
  _RuleDraft(EventChannelRule rule)
      : channel = rule.channel,
        isEnabled = rule.isEnabled,
        template = TextEditingController(text: rule.templateName ?? ''),
        language = TextEditingController(
          text: (rule.templateLanguage ?? '').isEmpty
              ? 'en'
              : rule.templateLanguage,
        ),
        subject = TextEditingController(text: rule.subject ?? ''),
        body = TextEditingController(text: rule.body ?? '');

  String channel;
  bool isEnabled;
  final TextEditingController template;
  final TextEditingController language;
  final TextEditingController subject;
  final TextEditingController body;

  void dispose() {
    template.dispose();
    language.dispose();
    subject.dispose();
    body.dispose();
  }

  /// Only the boxes that belong to the channel carry a value; the rest are
  /// sent as null so a channel change leaves nothing stale behind.
  EventChannelRule toRule() {
    String? text(TextEditingController controller) {
      final String value = controller.text.trim();
      return value.isEmpty ? null : value;
    }

    return EventChannelRule(
      channel: channel,
      isEnabled: isEnabled,
      templateName: channel == 'EMAIL' ? null : text(template),
      templateLanguage: channel == 'WHATSAPP' ? text(language) : null,
      subject: channel == 'EMAIL' ? text(subject) : null,
      body: channel == 'EMAIL' ? text(body) : null,
    );
  }
}

/// Edits the channel list of one event. Saving replaces the whole list.
class MessagingEventDialog extends StatefulWidget {
  const MessagingEventDialog({
    super.key,
    required this.api,
    required this.config,
    required this.event,
  });

  final ApiClient api;
  final EventConfig config;
  final MessagingEvent event;

  @override
  State<MessagingEventDialog> createState() => _MessagingEventDialogState();
}

class _MessagingEventDialogState extends State<MessagingEventDialog>
    with SaveInDialog<MessagingEventDialog> {
  static const int _maxChannels = 3;
  static const List<String> _all = ['EMAIL', 'WHATSAPP', 'SMS'];

  late final List<_RuleDraft> _drafts = [
    for (final EventChannelRule rule in widget.config.channels)
      _RuleDraft(rule),
  ];

  @override
  void dispose() {
    for (final _RuleDraft draft in _drafts) {
      draft.dispose();
    }
    super.dispose();
  }

  List<String> get _unused => [
        for (final String channel in _all)
          if (!_drafts.any((draft) => draft.channel == channel)) channel,
      ];

  void _add() {
    final List<String> free = _unused;
    if (free.isEmpty || _drafts.length >= _maxChannels) return;
    setState(() => _drafts.add(_RuleDraft(EventChannelRule(
          channel: free.first,
          isEnabled: true,
        ))));
  }

  void _move(int index, int by) {
    final int target = index + by;
    if (target < 0 || target >= _drafts.length) return;
    setState(() {
      final _RuleDraft draft = _drafts.removeAt(index);
      _drafts.insert(target, draft);
    });
  }

  void _remove(int index) {
    setState(() => _drafts.removeAt(index).dispose());
  }

  Future<void> _save() => saveAndClose<EventConfig>(
        () => widget.api.updateMessagingEventConfig(
          widget.config.eventCode,
          [for (final _RuleDraft draft in _drafts) draft.toRule()],
        ),
      );

  String get _variableHelp {
    final List<String> variables = widget.event.variables;
    if (variables.isEmpty) return '';
    return 'Variables in order: ${[
      for (int i = 0; i < variables.length; i++) '{{${i + 1}}} ${variables[i]}',
    ].join(', ')}';
  }

  Widget _rule(BuildContext context, int index) {
    final _RuleDraft draft = _drafts[index];
    final ThemeData theme = Theme.of(context);
    final List<String> choices = [
      draft.channel,
      ..._unused,
    ];
    return Card(
      key: ValueKey('messaging-rule-$index'),
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text('${index + 1}.', style: theme.textTheme.titleSmall),
                const SizedBox(width: AppSpacing.sm),
                SizedBox(
                  width: 180,
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('messaging-rule-channel-$index'),
                    isExpanded: true,
                    initialValue: draft.channel,
                    decoration: const InputDecoration(labelText: 'Channel'),
                    items: [
                      for (final String channel in choices)
                        DropdownMenuItem(
                          value: channel,
                          child: Text(messagingChannelNames[channel] ?? channel),
                        ),
                    ],
                    onChanged: saving
                        ? null
                        : (value) =>
                            setState(() => draft.channel = value ?? draft.channel),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                const Text('On'),
                Switch(
                  key: ValueKey('messaging-rule-enabled-$index'),
                  value: draft.isEnabled,
                  onChanged: saving
                      ? null
                      : (value) => setState(() => draft.isEnabled = value),
                ),
                const Spacer(),
                IconButton(
                  tooltip: 'Try earlier',
                  onPressed: saving || index == 0 ? null : () => _move(index, -1),
                  icon: const Icon(Icons.arrow_upward, size: 18),
                ),
                IconButton(
                  tooltip: 'Try later',
                  onPressed: saving || index == _drafts.length - 1
                      ? null
                      : () => _move(index, 1),
                  icon: const Icon(Icons.arrow_downward, size: 18),
                ),
                IconButton(
                  key: ValueKey('messaging-rule-remove-$index'),
                  tooltip: 'Remove',
                  onPressed: saving ? null : () => _remove(index),
                  icon: const Icon(Icons.close, size: 18),
                ),
              ],
            ),
            if (draft.channel == 'WHATSAPP') ...[
              TextField(
                key: ValueKey('messaging-rule-template-$index'),
                controller: draft.template,
                enabled: !saving,
                decoration: const InputDecoration(
                  labelText: 'Template name',
                  helperText: 'As approved in your WhatsApp account',
                ),
              ),
              TextField(
                key: ValueKey('messaging-rule-language-$index'),
                controller: draft.language,
                enabled: !saving,
                decoration: const InputDecoration(labelText: 'Language'),
              ),
            ],
            if (draft.channel == 'SMS')
              TextField(
                key: ValueKey('messaging-rule-template-$index'),
                controller: draft.template,
                enabled: !saving,
                decoration: const InputDecoration(
                  labelText: 'MSG91 template id',
                  helperText: 'The DLT-approved template id',
                ),
              ),
            if (draft.channel == 'EMAIL') ...[
              TextField(
                key: ValueKey('messaging-rule-subject-$index'),
                controller: draft.subject,
                enabled: !saving,
                decoration: InputDecoration(
                  labelText: 'Subject',
                  helperText: 'Blank uses: ${widget.event.defaultSubject}',
                ),
              ),
              TextField(
                key: ValueKey('messaging-rule-body-$index'),
                controller: draft.body,
                enabled: !saving,
                minLines: 3,
                maxLines: 6,
                decoration: InputDecoration(
                  labelText: 'Body',
                  helperText: 'Blank uses: ${widget.event.defaultBody}',
                  helperMaxLines: 4,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      scrollable: true,
      title: Text(widget.config.label),
      content: SizedBox(
        width: 620,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            Text(
              'Channels are tried in order; the first that can reach the '
              'customer sends. Up to $_maxChannels. No channel means this '
              'event sends nothing.',
              style: theme.textTheme.bodySmall,
            ),
            if (_variableHelp.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.xs),
                child: Text(
                  _variableHelp,
                  key: const ValueKey('messaging-variable-help'),
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            const SizedBox(height: AppSpacing.md),
            for (int i = 0; i < _drafts.length; i++) _rule(context, i),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                key: const ValueKey('messaging-rule-add'),
                onPressed: saving ||
                        _drafts.length >= _maxChannels ||
                        _unused.isEmpty
                    ? null
                    : _add,
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Add a channel'),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('messaging-event-save'),
          onPressed: saving ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }
}
