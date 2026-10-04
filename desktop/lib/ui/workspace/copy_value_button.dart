import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// A small copy icon beside a value people paste elsewhere: a document's
/// number, a party's GSTIN, an IRN or an e-way bill number (backlog 83).
///
/// The one widget for it, so every document window copies the same way:
/// one click puts [value] on the clipboard and the icon turns into a tick
/// for a moment to say so -- no snack bar to cover the screen. Nothing is
/// drawn for an empty value.
class CopyValueButton extends StatefulWidget {
  const CopyValueButton({
    super.key,
    required this.value,
    this.what = 'number',
    this.size = 14,
  });

  /// What is copied.
  final String value;

  /// What it is, for the tooltip: "Copy number", "Copy GSTIN".
  final String what;

  /// The icon's size; the button around it stays compact.
  final double size;

  @override
  State<CopyValueButton> createState() => _CopyValueButtonState();
}

class _CopyValueButtonState extends State<CopyValueButton> {
  bool _copied = false;
  Timer? _reset;

  @override
  void dispose() {
    _reset?.cancel();
    super.dispose();
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.value.trim()));
    if (!mounted) return;
    setState(() => _copied = true);
    _reset?.cancel();
    _reset = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.value.trim().isEmpty) return const SizedBox.shrink();
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return IconButton(
      tooltip: _copied ? 'Copied' : 'Copy ${widget.what}',
      onPressed: () => unawaited(_copy()),
      visualDensity: VisualDensity.compact,
      padding: EdgeInsets.zero,
      // No taller than the line it sits on, so a header does not grow.
      constraints: BoxConstraints.tightFor(
        width: widget.size + 10,
        height: widget.size + 4,
      ),
      iconSize: widget.size,
      icon: Icon(
        _copied ? Icons.check : Icons.copy_outlined,
        color: _copied ? scheme.primary : scheme.onSurfaceVariant,
      ),
    );
  }
}
