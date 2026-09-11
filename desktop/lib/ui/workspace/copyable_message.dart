import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// A status or error message the person can select and copy.
///
/// A plain [Text] cannot be selected, so a refusal from the server -- the one
/// thing somebody needs to paste into a bug report or an email -- had to be
/// retyped by hand. Every import dialog shows its messages through this.
class CopyableMessage extends StatelessWidget {
  const CopyableMessage({
    super.key,
    required this.message,
    this.isError = false,
  });

  final String message;

  /// Error messages take the theme's error colour; status messages do not.
  final bool isError;

  Future<void> _copy(BuildContext context) async {
    final ScaffoldMessengerState? messenger = ScaffoldMessenger.maybeOf(context);
    await Clipboard.setData(ClipboardData(text: message));
    messenger?.showSnackBar(
      const SnackBar(
        content: Text('Message copied.'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? style = isError
        ? theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error)
        : theme.textTheme.bodyMedium;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: SelectableText(message, style: style)),
        IconButton(
          tooltip: 'Copy message',
          icon: const Icon(Icons.copy_outlined, size: 18),
          visualDensity: VisualDensity.compact,
          onPressed: () => _copy(context),
        ),
      ],
    );
  }
}
