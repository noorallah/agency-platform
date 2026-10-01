import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/entities.dart';
import '../../models/messaging.dart';
import 'messaging_channels_tab.dart' show messagingChannelNames;

/// Every message the firm has queued, sent or skipped, newest first.
class MessagingLogTab extends StatefulWidget {
  const MessagingLogTab({
    super.key,
    required this.api,
    required this.maySend,
  });

  final ApiClient api;

  /// Resend needs `DOCUMENT_SEND`.
  final bool maySend;

  @override
  State<MessagingLogTab> createState() => _MessagingLogTabState();
}

class _MessagingLogTabState extends State<MessagingLogTab> {
  static const int _pageSize = 20;
  static const List<String> _statuses = [
    'QUEUED',
    'SENDING',
    'SENT',
    'DELIVERED',
    'READ',
    'FAILED',
    'SKIPPED',
  ];

  final TextEditingController _search = TextEditingController();
  List<MessageLogEntry> _rows = const [];
  int _total = 0;
  int _page = 1;
  String _status = '';
  String _channel = '';
  String? _selectedId;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final PagedResult<MessageLogEntry> result =
          await widget.api.messagingMessages(
        page: _page,
        pageSize: _pageSize,
        search: _search.text.trim(),
        status: _status,
        channel: _channel,
      );
      if (!mounted) return;
      setState(() {
        _rows = result.items;
        _total = result.total;
        _selectedId = null;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _rows = const [];
        _error = error.message;
        _loading = false;
      });
    }
  }

  void _filter() {
    _page = 1;
    unawaited(_load());
  }

  Future<void> _resend() async {
    final String? id = _selectedId;
    if (id == null) return;
    try {
      await widget.api.resendMessagingMessage(id);
      if (!mounted) return;
      NotificationService.show(
        context,
        'Queued to send again.',
        kind: AppNotificationKind.success,
      );
      await _load();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    }
  }

  String _when(String iso) {
    final DateTime? parsed = DateTime.tryParse(iso);
    if (parsed == null) return iso;
    final DateTime local = parsed.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  String _words(String code) => code.isEmpty
      ? ''
      : code[0] + code.substring(1).toLowerCase().replaceAll('_', ' ');

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final int pages = _total == 0 ? 1 : ((_total + _pageSize - 1) ~/ _pageSize);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: AppSpacing.md,
          runSpacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 220,
              child: TextField(
                key: const ValueKey('messaging-log-search'),
                controller: _search,
                decoration: const InputDecoration(
                  labelText: 'Search',
                  isDense: true,
                ),
                onSubmitted: (_) => _filter(),
              ),
            ),
            SizedBox(
              width: 160,
              child: DropdownButtonFormField<String>(
                key: const ValueKey('messaging-log-status'),
                isExpanded: true,
                initialValue: _status,
                decoration: const InputDecoration(
                  labelText: 'Status',
                  isDense: true,
                ),
                items: [
                  const DropdownMenuItem(value: '', child: Text('All')),
                  for (final String status in _statuses)
                    DropdownMenuItem(value: status, child: Text(_words(status))),
                ],
                onChanged: (value) {
                  _status = value ?? '';
                  _filter();
                },
              ),
            ),
            SizedBox(
              width: 160,
              child: DropdownButtonFormField<String>(
                key: const ValueKey('messaging-log-channel'),
                isExpanded: true,
                initialValue: _channel,
                decoration: const InputDecoration(
                  labelText: 'Channel',
                  isDense: true,
                ),
                items: [
                  const DropdownMenuItem(value: '', child: Text('All')),
                  for (final MapEntry<String, String> entry
                      in messagingChannelNames.entries)
                    DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                ],
                onChanged: (value) {
                  _channel = value ?? '';
                  _filter();
                },
              ),
            ),
            OutlinedButton(
              onPressed: _loading ? null : () => unawaited(_load()),
              child: const Text('Refresh'),
            ),
            FilledButton(
              key: const ValueKey('messaging-log-resend'),
              onPressed: widget.maySend && _selectedId != null
                  ? () => unawaited(_resend())
                  : null,
              child: const Text('Resend'),
            ),
          ],
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              _error!,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.error),
            ),
          ),
        const SizedBox(height: AppSpacing.sm),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _rows.isEmpty
                  ? Center(
                      child: Text(
                        'No messages yet.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    )
                  : SingleChildScrollView(
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: DataTable(
                          showCheckboxColumn: false,
                          columnSpacing: AppSpacing.lg,
                          columns: const [
                            DataColumn(label: Text('When')),
                            DataColumn(label: Text('Event')),
                            DataColumn(label: Text('Document')),
                            DataColumn(label: Text('Channel')),
                            DataColumn(label: Text('Recipient')),
                            DataColumn(label: Text('Status')),
                            DataColumn(label: Text('Reason')),
                            DataColumn(label: Text('Tries'), numeric: true),
                          ],
                          rows: [
                            for (final MessageLogEntry row in _rows)
                              DataRow(
                                key: ValueKey('messaging-log-row-${row.id}'),
                                selected: row.id == _selectedId,
                                onSelectChanged: (_) =>
                                    setState(() => _selectedId = row.id),
                                cells: [
                                  DataCell(Text(_when(row.createdAt))),
                                  DataCell(Text(_words(row.eventCode))),
                                  DataCell(Text(row.documentNumber ?? '')),
                                  DataCell(Text(
                                    messagingChannelNames[row.channel] ??
                                        row.channel,
                                  )),
                                  DataCell(Text(row.recipient ?? '')),
                                  DataCell(Text(_words(row.status))),
                                  DataCell(ConstrainedBox(
                                    constraints:
                                        const BoxConstraints(maxWidth: 220),
                                    child: Text(
                                      row.reason ?? '',
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  )),
                                  DataCell(Text('${row.attempts}')),
                                ],
                              ),
                          ],
                        ),
                      ),
                    ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Text('Page $_page of $pages  ·  $_total messages'),
            IconButton(
              tooltip: 'Previous page',
              onPressed: _page > 1 && !_loading
                  ? () {
                      _page -= 1;
                      unawaited(_load());
                    }
                  : null,
              icon: const Icon(Icons.chevron_left),
            ),
            IconButton(
              tooltip: 'Next page',
              onPressed: _page < pages && !_loading
                  ? () {
                      _page += 1;
                      unawaited(_load());
                    }
                  : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
      ],
    );
  }
}
