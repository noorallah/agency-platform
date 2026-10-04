import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/batch_serial.dart';
import '../../models/entities.dart';

/// Split typed or pasted text into serial numbers: one per line, trimmed,
/// blanks dropped. A scanner ends each code with Enter, so it lands the same
/// way as a paste.
List<String> parseSerialLines(String text) => [
      for (final String line in text.split(RegExp(r'[\r\n]+')))
        if (line.trim().isNotEmpty) line.trim(),
    ];

/// The serials entered more than once, compared without case as the server
/// does, each named once in the order first repeated.
List<String> repeatedSerials(List<String> serials) {
  final Set<String> seen = <String>{};
  final Set<String> named = <String>{};
  final List<String> repeated = <String>[];
  for (final String serial in serials) {
    final String key = serial.toLowerCase();
    if (!seen.add(key) && named.add(key)) repeated.add(serial);
  }
  return repeated;
}

/// Open the serial numbers of one document line. Returns the list the user
/// accepted, or null when the dialog was dismissed. Nothing is saved here:
/// the document's own save sends the list (PG-10).
///
/// [needed] is the count the line must reach (the completion check counts
/// accepted plus free quantity). With [readOnly] the list is shown as it
/// stands and a tap on a serial loads its trail, for a completed document.
Future<List<String>?> showSerialEntryDialog(
  BuildContext context, {
  required ApiClient api,
  required String title,
  required int needed,
  required List<String> initial,
  String? productId,
  bool readOnly = false,
}) =>
    showDialog<List<String>>(
      context: context,
      builder: (_) => SerialEntryDialog(
        api: api,
        title: title,
        needed: needed,
        initial: initial,
        productId: productId,
        readOnly: readOnly,
      ),
    );

class SerialEntryDialog extends StatefulWidget {
  const SerialEntryDialog({
    super.key,
    required this.api,
    required this.title,
    required this.needed,
    required this.initial,
    this.productId,
    this.readOnly = false,
  });

  final ApiClient api;
  final String title;
  final int needed;
  final List<String> initial;
  final String? productId;
  final bool readOnly;

  @override
  State<SerialEntryDialog> createState() => _SerialEntryDialogState();
}

class _SerialEntryDialogState extends State<SerialEntryDialog> {
  late final TextEditingController _text =
      TextEditingController(text: widget.initial.join('\n'));
  final TextEditingController _prefix = TextEditingController();
  final TextEditingController _start = TextEditingController(text: '1');
  final TextEditingController _count = TextEditingController();
  final TextEditingController _width = TextEditingController(text: '0');
  bool _filling = false;
  String? _error;
  String? _trailFor;
  List<SerialTrailEvent>? _trail;

  @override
  void dispose() {
    _text.dispose();
    _prefix.dispose();
    _start.dispose();
    _count.dispose();
    _width.dispose();
    super.dispose();
  }

  List<String> get _serials => parseSerialLines(_text.text);

  Future<void> _fill() async {
    final int? start = int.tryParse(_start.text.trim());
    final int? count = int.tryParse(_count.text.trim());
    final int? width = int.tryParse(_width.text.trim());
    if (start == null || count == null || width == null) {
      setState(() => _error = 'Start, count and width must be whole numbers.');
      return;
    }
    setState(() {
      _filling = true;
      _error = null;
    });
    try {
      final List<String> made = await widget.api.expandSerials(
        prefix: _prefix.text.trim(),
        start: start,
        count: count,
        width: width,
      );
      if (!mounted) return;
      setState(() {
        _text.text = [..._serials, ...made].join('\n');
        _filling = false;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _filling = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _openTrail(String serial) async {
    setState(() {
      _trailFor = serial;
      _trail = null;
      _error = null;
    });
    try {
      final PagedResult<SerialRecord> found = await widget.api.serials(
        search: serial,
        filters: SerialQuery(productId: widget.productId),
      );
      SerialRecord? match;
      for (final SerialRecord item in found.items) {
        if (item.serialNumber.toLowerCase() == serial.toLowerCase()) {
          match = item;
        }
      }
      if (match == null) {
        if (mounted) setState(() => _trail = const []);
        return;
      }
      final List<SerialTrailEvent> events =
          await widget.api.serialTrail(match.id);
      if (mounted) setState(() => _trail = events);
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _trail = const [];
          _error = error.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    final List<String> serials = _serials;
    final List<String> repeated = repeatedSerials(serials);
    final int entered = serials.length;
    final bool right = entered == widget.needed && repeated.isEmpty;
    final Color tone = entered > widget.needed || repeated.isNotEmpty
        ? scheme.error
        : right
            ? scheme.primary
            : scheme.onSurfaceVariant;
    return AlertDialog(
      title: Text(widget.title, overflow: TextOverflow.ellipsis),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                '$entered of ${widget.needed} entered',
                key: const ValueKey('serial-count'),
                style: theme.textTheme.titleSmall?.copyWith(color: tone),
              ),
              if (repeated.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    'Entered twice: ${repeated.join(', ')}',
                    key: const ValueKey('serial-duplicates'),
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: scheme.error),
                  ),
                ),
              const SizedBox(height: 8),
              if (widget.readOnly)
                _readOnlyList(serials)
              else ...[
                TextField(
                  key: const ValueKey('serial-text'),
                  controller: _text,
                  minLines: 6,
                  maxLines: 8,
                  autofocus: true,
                  keyboardType: TextInputType.multiline,
                  onChanged: (_) => setState(() {}),
                  decoration: const InputDecoration(
                    border: OutlineInputBorder(),
                    isDense: true,
                    hintText: 'One serial number per line. Paste a list or '
                        'scan; Enter starts the next.',
                  ),
                ),
                const SizedBox(height: 12),
                Text('Fill a range', style: theme.textTheme.labelLarge),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _small('serial-prefix', 'Prefix', _prefix, 120,
                        number: false),
                    _small('serial-start', 'Start', _start, 72),
                    _small('serial-range-count', 'Count', _count, 72),
                    _small('serial-width', 'Width', _width, 64),
                    OutlinedButton(
                      key: const ValueKey('serial-fill'),
                      onPressed: _filling ? null : () => unawaited(_fill()),
                      child: const Text('Add range'),
                    ),
                  ],
                ),
              ],
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    _error!,
                    key: const ValueKey('serial-error'),
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: scheme.error),
                  ),
                ),
              if (_trailFor != null) _trailBlock(context),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(widget.readOnly ? 'Close' : 'Cancel'),
        ),
        if (!widget.readOnly)
          FilledButton(
            key: const ValueKey('serial-ok'),
            onPressed: () => Navigator.pop(context, _serials),
            child: const Text('OK'),
          ),
      ],
    );
  }

  Widget _small(
    String key,
    String label,
    TextEditingController controller,
    double width, {
    bool number = true,
  }) =>
      SizedBox(
        width: width,
        child: TextField(
          key: ValueKey<String>(key),
          controller: controller,
          keyboardType: number ? TextInputType.number : TextInputType.text,
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            border: const OutlineInputBorder(),
          ),
        ),
      );

  Widget _readOnlyList(List<String> serials) {
    if (serials.isEmpty) return const Text('No serial numbers recorded.');
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 220),
      child: ListView(
        shrinkWrap: true,
        children: [
          for (final String serial in serials)
            ListTile(
              key: ValueKey<String>('serial-row-$serial'),
              dense: true,
              visualDensity: VisualDensity.compact,
              title: Text(serial),
              trailing: const Icon(Icons.history, size: 16),
              onTap: () => unawaited(_openTrail(serial)),
            ),
        ],
      ),
    );
  }

  Widget _trailBlock(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<SerialTrailEvent>? events = _trail;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Trail of $_trailFor', style: theme.textTheme.labelLarge),
          const SizedBox(height: 4),
          if (events == null)
            const LinearProgressIndicator(minHeight: 2)
          else if (events.isEmpty)
            const Text('No documents recorded for this unit.')
          else
            for (final SerialTrailEvent event in events)
              Text(
                '${event.documentType.replaceAll('_', ' ').toLowerCase()}  '
                '${event.documentNumber}  ${event.documentDate}  '
                '${event.partyName}',
                key: const ValueKey('serial-trail-event'),
                style: theme.textTheme.bodySmall,
              ),
        ],
      ),
    );
  }
}
