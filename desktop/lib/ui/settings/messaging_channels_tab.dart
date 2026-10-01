import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/messaging.dart';
import '../workspace/desktop_framework.dart';

/// What a person reads for each channel code.
const Map<String, String> messagingChannelNames = {
  'EMAIL': 'Email',
  'WHATSAPP': 'WhatsApp',
  'SMS': 'SMS',
};

/// The three channels, each with its provider, health and on/off state.
///
/// A channel is switched on only after a test passes, so "Switch on" stays
/// disabled until its health reads OK.
class MessagingChannelsTab extends StatefulWidget {
  const MessagingChannelsTab({
    super.key,
    required this.api,
    required this.mayChange,
  });

  final ApiClient api;
  final bool mayChange;

  @override
  State<MessagingChannelsTab> createState() => _MessagingChannelsTabState();
}

class _MessagingChannelsTabState extends State<MessagingChannelsTab> {
  List<MessagingChannel> _channels = const [];
  List<MessagingProvider> _providers = const [];
  bool _loading = true;
  String? _loadError;
  String? _error;
  String? _busyChannel;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final List<MessagingProvider> providers =
          await widget.api.messagingProviders();
      final List<MessagingChannel> channels =
          await widget.api.messagingChannels();
      if (!mounted) return;
      setState(() {
        _providers = providers;
        _channels = channels;
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

  void _replace(MessagingChannel channel) {
    _channels = [
      for (final MessagingChannel existing in _channels)
        if (existing.channel == channel.channel) channel else existing,
    ];
  }

  String _providerLabel(MessagingChannel channel) {
    final String? code = channel.provider;
    if (code == null) return 'No account yet';
    for (final MessagingProvider provider in _providers) {
      if (provider.provider == code) return provider.label;
    }
    return code;
  }

  /// Runs one of the channel buttons, shows what the server said, and keeps
  /// the refusal on screen when it refuses.
  Future<void> _run(
    MessagingChannel channel,
    Future<ChannelOutcome> Function() call,
  ) async {
    setState(() {
      _busyChannel = channel.channel;
      _error = null;
    });
    try {
      final ChannelOutcome outcome = await call();
      if (!mounted) return;
      setState(() {
        _replace(outcome.channel);
        _busyChannel = null;
      });
      if (outcome.message.isNotEmpty) {
        NotificationService.show(
          context,
          outcome.message,
          kind: outcome.channel.health == 'NEEDS_ATTENTION'
              ? AppNotificationKind.warning
              : AppNotificationKind.success,
        );
      }
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _busyChannel = null;
        _error = error.message;
      });
    }
  }

  Future<void> _setUp(MessagingChannel channel) async {
    final List<MessagingProvider> options = [
      for (final MessagingProvider provider in _providers)
        if (provider.channel == channel.channel) provider,
    ];
    final ChannelOutcome? saved = await showDialog<ChannelOutcome>(
      context: context,
      builder: (_) => MessagingAccountDialog(
        api: widget.api,
        channel: channel,
        providers: options,
      ),
    );
    if (saved == null || !mounted) return;
    setState(() => _replace(saved.channel));
    if (saved.message.isNotEmpty) {
      NotificationService.show(
        context,
        saved.message,
        kind: AppNotificationKind.success,
      );
    }
  }

  StatusBadgeTone _tone(String health) => switch (health) {
        'OK' => StatusBadgeTone.success,
        'NEEDS_ATTENTION' => StatusBadgeTone.danger,
        'UNTESTED' => StatusBadgeTone.warning,
        _ => StatusBadgeTone.neutral,
      };

  String _healthWords(String health) => switch (health) {
        'OK' => 'Working',
        'NEEDS_ATTENTION' => 'Needs attention',
        'UNTESTED' => 'Not tested yet',
        _ => 'Not set up',
      };

  String _tested(String? iso) {
    final DateTime? when = iso == null ? null : DateTime.tryParse(iso);
    if (when == null) return 'never';
    final DateTime local = when.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
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
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Text(
                _error!,
                key: const ValueKey('messaging-channel-error'),
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ),
          for (final MessagingChannel channel in _channels)
            _card(context, channel),
        ],
      ),
    );
  }

  Widget _card(BuildContext context, MessagingChannel channel) {
    final ThemeData theme = Theme.of(context);
    final String name = messagingChannelNames[channel.channel] ?? channel.channel;
    final bool busy = _busyChannel == channel.channel;
    final bool may = widget.mayChange && !busy;
    return Card(
      key: ValueKey('messaging-channel-${channel.channel}'),
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(name, style: theme.textTheme.titleMedium),
                const SizedBox(width: AppSpacing.md),
                Text(_providerLabel(channel), style: theme.textTheme.bodyMedium),
                const SizedBox(width: AppSpacing.md),
                StatusBadge(
                  label: _healthWords(channel.health),
                  tone: _tone(channel.health),
                ),
                const Spacer(),
                Text(
                  channel.isEnabled ? 'Switched on' : 'Switched off',
                  key: ValueKey('messaging-channel-state-${channel.channel}'),
                  style: theme.textTheme.labelLarge,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Last tested: ${_tested(channel.lastTestedAt)}',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            if ((channel.lastError ?? '').isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: AppSpacing.xs),
                child: Text(
                  channel.lastError!,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.error),
                ),
              ),
            const SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                OutlinedButton(
                  key: ValueKey('messaging-setup-${channel.channel}'),
                  onPressed: may ? () => unawaited(_setUp(channel)) : null,
                  child: Text(
                    channel.isConfigured ? 'Replace account' : 'Set up',
                  ),
                ),
                OutlinedButton(
                  key: ValueKey('messaging-test-${channel.channel}'),
                  onPressed: may && channel.isConfigured
                      ? () => unawaited(_run(
                            channel,
                            () => widget.api
                                .testMessagingChannel(channel.channel),
                          ))
                      : null,
                  child: const Text('Test'),
                ),
                FilledButton(
                  key: ValueKey('messaging-enable-${channel.channel}'),
                  onPressed: may && !channel.isEnabled && channel.health == 'OK'
                      ? () => unawaited(_run(
                            channel,
                            () => widget.api
                                .enableMessagingChannel(channel.channel),
                          ))
                      : null,
                  child: const Text('Switch on'),
                ),
                OutlinedButton(
                  key: ValueKey('messaging-disable-${channel.channel}'),
                  onPressed: may && channel.isEnabled
                      ? () => unawaited(_run(
                            channel,
                            () => widget.api
                                .disableMessagingChannel(channel.channel),
                          ))
                      : null,
                  child: const Text('Switch off'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// The account form for one channel, drawn from the provider's own field list
/// so a new provider needs no new screen.
///
/// A secret is never prefilled: a saved one says so, and leaving it blank
/// keeps it.
class MessagingAccountDialog extends StatefulWidget {
  const MessagingAccountDialog({
    super.key,
    required this.api,
    required this.channel,
    required this.providers,
  });

  final ApiClient api;
  final MessagingChannel channel;

  /// The providers that can carry this channel.
  final List<MessagingProvider> providers;

  @override
  State<MessagingAccountDialog> createState() => _MessagingAccountDialogState();
}

class _MessagingAccountDialogState extends State<MessagingAccountDialog>
    with SaveInDialog<MessagingAccountDialog> {
  late String _provider = _initialProvider();
  final Map<String, TextEditingController> _controllers = {};
  final Map<String, String> _choices = {};

  String _initialProvider() {
    final String? current = widget.channel.provider;
    for (final MessagingProvider provider in widget.providers) {
      if (provider.provider == current) return provider.provider;
    }
    return widget.providers.isEmpty ? '' : widget.providers.first.provider;
  }

  MessagingProvider? get _selected {
    for (final MessagingProvider provider in widget.providers) {
      if (provider.provider == _provider) return provider;
    }
    return null;
  }

  /// What a field starts with: the saved value for the provider already in
  /// use, else its default. Secrets start empty, always.
  String _initialValue(ProviderField field) {
    if (field.secret) return '';
    if (_provider == widget.channel.provider) {
      final String? saved = widget.channel.settings[field.name];
      if (saved != null) return saved;
    }
    return field.defaultValue ?? '';
  }

  TextEditingController _controllerFor(ProviderField field) =>
      _controllers.putIfAbsent(
        '$_provider/${field.name}',
        () => TextEditingController(text: _initialValue(field)),
      );

  String _choiceFor(ProviderField field) {
    final String key = '$_provider/${field.name}';
    final String value = _choices[key] ?? _initialValue(field);
    return field.choices.contains(value)
        ? value
        : (field.choices.isEmpty ? '' : field.choices.first);
  }

  @override
  void dispose() {
    for (final TextEditingController controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  bool get _secretSaved => _provider == widget.channel.provider;

  Future<void> _save() => saveAndClose<ChannelOutcome>(() async {
        final MessagingProvider? provider = _selected;
        final Map<String, String> settings = <String, String>{};
        for (final ProviderField field
            in provider?.fields ?? const <ProviderField>[]) {
          final String value = field.kind == 'choice'
              ? _choiceFor(field)
              : _controllerFor(field).text.trim();
          // A blank secret means "keep the saved one": leave it out.
          if (field.secret && value.isEmpty) continue;
          settings[field.name] = value;
        }
        return widget.api.saveMessagingChannel(
          widget.channel.channel,
          _provider,
          settings,
        );
      });

  Widget _fieldWidget(ProviderField field) {
    final bool keepsSecret = field.secret &&
        _secretSaved &&
        widget.channel.secretsSet.contains(field.name);
    final String label = field.required ? '${field.label} *' : field.label;
    if (field.kind == 'choice') {
      return DropdownButtonFormField<String>(
        key: ValueKey('messaging-field-${field.name}'),
        isExpanded: true,
        initialValue: _choiceFor(field),
        decoration: InputDecoration(labelText: label, helperText: field.help),
        items: [
          for (final String choice in field.choices)
            DropdownMenuItem(value: choice, child: Text(choice)),
        ],
        onChanged: saving
            ? null
            : (value) => setState(
                  () => _choices['$_provider/${field.name}'] = value ?? '',
                ),
      );
    }
    return TextFormField(
      key: ValueKey('messaging-field-${field.name}'),
      controller: _controllerFor(field),
      enabled: !saving,
      obscureText: field.kind == 'password' || field.secret,
      keyboardType: switch (field.kind) {
        'number' => TextInputType.number,
        'email' => TextInputType.emailAddress,
        _ => TextInputType.text,
      },
      decoration: InputDecoration(
        labelText: label,
        helperText: keepsSecret
            ? 'saved — leave blank to keep'
            : (field.help ?? (field.secret ? 'stored encrypted' : null)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final String name =
        messagingChannelNames[widget.channel.channel] ?? widget.channel.channel;
    final MessagingProvider? provider = _selected;
    return AlertDialog(
      scrollable: true,
      title: Text('$name account'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            saveErrorBanner(),
            if (widget.providers.length > 1) ...[
              DropdownButtonFormField<String>(
                key: const ValueKey('messaging-provider'),
                isExpanded: true,
                initialValue: _provider,
                decoration: const InputDecoration(labelText: 'Provider'),
                items: [
                  for (final MessagingProvider option in widget.providers)
                    DropdownMenuItem(
                      value: option.provider,
                      child: Text(option.label),
                    ),
                ],
                onChanged: saving
                    ? null
                    : (value) => setState(() => _provider = value ?? _provider),
              ),
              const SizedBox(height: AppSpacing.md),
            ] else if (provider != null) ...[
              Text(provider.label,
                  style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: AppSpacing.md),
            ],
            for (final ProviderField field
                in provider?.fields ?? const <ProviderField>[]) ...[
              _fieldWidget(field),
              const SizedBox(height: AppSpacing.md),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: cancelHandler,
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('messaging-account-save'),
          onPressed: saving || provider == null ? null : _save,
          child: Text(saving ? 'Saving…' : 'Save account'),
        ),
      ],
    );
  }
}
