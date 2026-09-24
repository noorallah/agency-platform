import 'dart:async';

import 'package:flutter/material.dart';

import '../core/design/design_tokens.dart';

/// What stands between starting the app and the sign-in screen: is the server
/// there at all?
///
/// On a server PC the app is often opened seconds after Windows starts, while
/// the Agency Platform Server service is still coming up; on any PC the service
/// may have stopped. Either way a sign-in screen that fails on submit is the
/// wrong first thing to see. This asks `/health` every [interval] for up to
/// [timeout], and then says plainly what is wrong, with a way to retry and a
/// way to the logs that say why.
class ServerConnectionGate extends StatefulWidget {
  const ServerConnectionGate({
    super.key,
    required this.probe,
    required this.serverUrl,
    required this.onConnected,
    required this.onContinueAnyway,
    this.onOpenLogs,
    this.interval = const Duration(seconds: 2),
    this.timeout = const Duration(seconds: 60),
    this.probeTimeout = const Duration(seconds: 5),
  });

  /// True when the server answered `/health`.
  final Future<bool> Function() probe;

  /// Shown so that a wrong address is visible as one.
  final String serverUrl;

  final VoidCallback onConnected;

  /// To the sign-in screen regardless, where Application Settings can change
  /// the server address -- the way out when the address itself is wrong.
  final VoidCallback onContinueAnyway;

  final Future<void> Function()? onOpenLogs;

  final Duration interval;
  final Duration timeout;

  /// One probe may take no longer than this; a server that accepts the
  /// connection and never answers must not stall the countdown.
  final Duration probeTimeout;

  @override
  State<ServerConnectionGate> createState() => _ServerConnectionGateState();
}

class _ServerConnectionGateState extends State<ServerConnectionGate> {
  bool _failed = false;
  int _attempt = 0;

  /// Bumped by every run, so a retry abandons the loop it replaced.
  int _generation = 0;

  int get _maxAttempts {
    final int attempts =
        widget.timeout.inMilliseconds ~/ widget.interval.inMilliseconds;
    return attempts < 1 ? 1 : attempts;
  }

  /// False until initState has returned.
  bool _started = false;

  @override
  void initState() {
    super.initState();
    unawaited(_run());
    _started = true;
  }

  @override
  void dispose() {
    _generation++;
    super.dispose();
  }

  Future<bool> _ask() async {
    try {
      return await widget.probe().timeout(
            widget.probeTimeout,
            onTimeout: () => false,
          );
    } on Object {
      return false;
    }
  }

  Future<void> _run() async {
    final int generation = ++_generation;
    for (int attempt = 1; attempt <= _maxAttempts; attempt++) {
      if (!mounted || generation != _generation) return;
      // The first pass starts inside initState, where setState is refused;
      // the state it would set is what the first build reads anyway.
      if (attempt == 1 && !_started) {
        _failed = false;
        _attempt = attempt;
      } else {
        setState(() {
          _failed = false;
          _attempt = attempt;
        });
      }
      if (await _ask()) {
        if (mounted && generation == _generation) widget.onConnected();
        return;
      }
      if (attempt < _maxAttempts) await Future<void>.delayed(widget.interval);
    }
    if (mounted && generation == _generation) setState(() => _failed = true);
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Card(
              shape:
                  const RoundedRectangleBorder(borderRadius: AppRadius.large),
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.xl),
                child: _failed ? _failure(theme) : _connecting(theme),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _connecting(ThemeData theme) => Column(
        key: const ValueKey<String>('server-gate-connecting'),
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: 40,
            height: 40,
            child: CircularProgressIndicator(),
          ),
          const SizedBox(height: AppSpacing.lg),
          Text('Connecting to server…', style: theme.textTheme.titleMedium),
          const SizedBox(height: AppSpacing.sm),
          Text(
            widget.serverUrl,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
            textAlign: TextAlign.center,
            overflow: TextOverflow.ellipsis,
            maxLines: 2,
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Attempt $_attempt of $_maxAttempts',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      );

  Widget _failure(ThemeData theme) => Column(
        key: const ValueKey<String>('server-gate-failed'),
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.cloud_off_outlined,
                  color: theme.colorScheme.error, size: 28),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(
                  'The Agency Platform Server service is not running',
                  style: theme.textTheme.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            'Nothing answered at ${widget.serverUrl} for '
            '${widget.timeout.inSeconds} seconds.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            'On the server PC, open Services and start '
            '"Agency Platform Server", or restart that PC. Its logs say why it '
            'stopped.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              FilledButton.icon(
                onPressed: () => unawaited(_run()),
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
              if (widget.onOpenLogs != null)
                OutlinedButton.icon(
                  onPressed: () => unawaited(widget.onOpenLogs!()),
                  icon: const Icon(Icons.folder_open_outlined),
                  label: const Text('Open logs folder'),
                ),
              TextButton(
                onPressed: widget.onContinueAnyway,
                child: const Text('Continue to sign-in'),
              ),
            ],
          ),
        ],
      );
}
