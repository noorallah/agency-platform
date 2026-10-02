import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/messaging.dart';
import 'messaging_channels_tab.dart';
import 'messaging_events_tab.dart';
import 'messaging_log_tab.dart';

/// Settings > Messaging (backlog 51): whether this firm sends messages at all,
/// through which accounts, for which events, and the log of what was sent.
///
/// Reading needs `SETTINGS_VIEW`; every change needs `SETTINGS_UPDATE`, and
/// the log's Resend needs `DOCUMENT_SEND`. Nothing here sends anything by
/// itself: the master switch and each channel start off.
class MessagingSettingsDialog extends StatelessWidget {
  const MessagingSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
  });

  final ApiClient api;
  final PermissionService permissions;

  @override
  Widget build(BuildContext context) {
    final bool mayChange = permissions.hasPermission('SETTINGS_UPDATE');
    return DefaultTabController(
      length: 4,
      child: AlertDialog(
        icon: const Icon(Icons.forum_outlined),
        title: const Text('Messaging'),
        content: SizedBox(
          width: 920,
          height: 520,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const TabBar(
                tabs: [
                  Tab(text: 'Switch and schedule'),
                  Tab(text: 'Channels'),
                  Tab(text: 'Events'),
                  Tab(text: 'Message log'),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Expanded(
                child: TabBarView(
                  children: [
                    MessagingScheduleTab(api: api, mayChange: mayChange),
                    MessagingChannelsTab(api: api, mayChange: mayChange),
                    MessagingEventsTab(api: api, mayChange: mayChange),
                    MessagingLogTab(
                      api: api,
                      maySend: permissions.hasPermission('DOCUMENT_SEND'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}

/// The master switch and the reminder schedule.
class MessagingScheduleTab extends StatefulWidget {
  const MessagingScheduleTab({
    super.key,
    required this.api,
    required this.mayChange,
  });

  final ApiClient api;
  final bool mayChange;

  @override
  State<MessagingScheduleTab> createState() => _MessagingScheduleTabState();
}

class _MessagingScheduleTabState extends State<MessagingScheduleTab> {
  final TextEditingController _dueSoon = TextEditingController();
  final TextEditingController _overdue = TextEditingController();
  final TextEditingController _stopAfter = TextEditingController(text: '90');
  MessagingSettings? _settings;
  bool _enabled = false;
  bool _loading = true;
  bool _saving = false;
  String? _loadError;
  String? _saveError;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _dueSoon.dispose();
    _overdue.dispose();
    _stopAfter.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final MessagingSettings settings = await widget.api.messagingSettings();
      if (!mounted) return;
      setState(() {
        _settings = settings;
        _enabled = settings.isEnabled;
        _dueSoon.text = '${settings.dueSoonDays}';
        _overdue.text = '${settings.overdueEveryDays}';
        _stopAfter.text = '${settings.overdueStopAfterDays}';
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

  Future<void> _save() async {
    final int? dueSoon = int.tryParse(_dueSoon.text.trim());
    final int? overdue = int.tryParse(_overdue.text.trim());
    final int? stopAfter = int.tryParse(_stopAfter.text.trim());
    if (dueSoon == null || dueSoon < 0 || dueSoon > 60) {
      setState(() => _saveError = 'Days before due must be from 0 to 60.');
      return;
    }
    if (overdue == null || overdue < 1 || overdue > 90) {
      setState(() => _saveError = 'Repeat every must be from 1 to 90 days.');
      return;
    }
    if (stopAfter == null || stopAfter < 1 || stopAfter > 3650) {
      setState(() => _saveError = 'Stop after must be from 1 to 3650 days.');
      return;
    }
    setState(() {
      _saving = true;
      _saveError = null;
    });
    try {
      final MessagingSettings saved = await widget.api.updateMessagingSettings(
        MessagingSettings(
          isEnabled: _enabled,
          dueSoonDays: dueSoon,
          overdueEveryDays: overdue,
          overdueStopAfterDays: stopAfter,
          isConfigured: true,
          canStoreCredentials: _settings?.canStoreCredentials ?? false,
        ),
      );
      if (!mounted) return;
      setState(() {
        _settings = saved;
        _enabled = saved.isEnabled;
        _saving = false;
      });
      NotificationService.show(
        context,
        'Messaging settings saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saveError = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_loadError != null) {
      return Text(
        _loadError!,
        style:
            theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
      );
    }
    final bool editable = widget.mayChange && !_saving;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!(_settings?.canStoreCredentials ?? false))
            Container(
              key: const ValueKey('messaging-key-warning'),
              margin: const EdgeInsets.only(bottom: AppSpacing.md),
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: theme.colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.warning_amber_outlined,
                      size: 18, color: theme.colorScheme.onErrorContainer),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      'Accounts cannot be saved yet: whoever runs the server '
                      'must set AGENCY_MESSAGING_KEY first.',
                      style: TextStyle(color: theme.colorScheme.onErrorContainer),
                    ),
                  ),
                ],
              ),
            ),
          if (_saveError != null)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Text(
                _saveError!,
                key: const ValueKey('messaging-settings-error'),
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            ),
          SwitchListTile(
            key: const ValueKey('messaging-master-switch'),
            contentPadding: EdgeInsets.zero,
            title: const Text('Send messages from this firm'),
            subtitle: const Text(
              'Off means nothing is sent, whatever the channels and events '
              'below say.',
            ),
            value: _enabled,
            onChanged:
                editable ? (value) => setState(() => _enabled = value) : null,
          ),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.md,
            children: [
              SizedBox(
                width: 320,
                child: TextField(
                  key: const ValueKey('messaging-due-soon-days'),
                  controller: _dueSoon,
                  enabled: editable,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Payment due soon: days before due',
                    helperText: '0 to 60',
                  ),
                ),
              ),
              SizedBox(
                width: 320,
                child: TextField(
                  key: const ValueKey('messaging-overdue-days'),
                  controller: _overdue,
                  enabled: editable,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Payment overdue: repeat every n days',
                    helperText: '1 to 90',
                  ),
                ),
              ),
              SizedBox(
                width: 320,
                child: TextField(
                  key: const ValueKey('messaging-overdue-stop-after'),
                  controller: _stopAfter,
                  enabled: editable,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Payment overdue: stop after n days',
                    helperText: 'Older bills are not reminded (1 to 3650)',
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          if (!widget.mayChange)
            Text(
              'Changing messaging needs the update settings permission.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            )
          else
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton(
                key: const ValueKey('messaging-settings-save'),
                onPressed: _saving ? null : () => unawaited(_save()),
                child: Text(_saving ? 'Saving…' : 'Save'),
              ),
            ),
        ],
      ),
    );
  }
}
