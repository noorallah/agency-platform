import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/geography.dart';

/// Where something is, chosen from the shared geography masters.
///
/// Four things carry an address on this platform — customers, vendors,
/// branches and warehouses — and until now none of them let anybody pick a
/// place. Vendors, branches and warehouses have the foreign keys and no form;
/// customers have free text and no keys. This is the one control that fills
/// the keys, so the four converge on the same masters instead of on four
/// spellings of "Parrys".
///
/// Cascading, because a flat list of every locality in the country is not a
/// dropdown anybody can use. Each rung loads when its parent is chosen.
class GeoAreaPicker extends StatefulWidget {
  const GeoAreaPicker({
    super.key,
    required this.api,
    required this.value,
    required this.onChanged,
    this.levels = GeoLevel.values,
    this.enabled = true,
  });

  final ApiClient api;

  /// The ids currently chosen, keyed by level. Absent means unset.
  final Map<GeoLevel, String> value;

  final ValueChanged<Map<GeoLevel, String>> onChanged;

  /// Which rungs to show. A route profile only carries city, postal code and
  /// locality; an address carries the whole ladder.
  final List<GeoLevel> levels;

  final bool enabled;

  @override
  State<GeoAreaPicker> createState() => _GeoAreaPickerState();
}

class _GeoAreaPickerState extends State<GeoAreaPicker> {
  final Map<GeoLevel, List<GeoPlaceRecord>> _options =
      <GeoLevel, List<GeoPlaceRecord>>{};
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _loadFrom(widget.levels.first);
  }

  /// Load [level] and every rung beneath it that already has a value.
  ///
  /// Best effort throughout: geography is reference data a platform
  /// administrator maintains, and a firm whose Places are empty should get an
  /// empty dropdown and a saveable form, not an error.
  Future<void> _loadFrom(GeoLevel level) async {
    setState(() => _loading = true);
    GeoLevel? current = level;
    while (current != null && widget.levels.contains(current)) {
      final GeoLevel rung = current;
      final String parentId = _parentIdFor(rung);
      if (rung.parentQuery != null && parentId.isEmpty) break;
      try {
        final List<GeoPlaceRecord> rows =
            await widget.api.geoPlaces(rung, parentId: parentId);
        if (!mounted) return;
        setState(() => _options[rung] = rows);
      } on ApiException {
        if (!mounted) return;
        setState(() => _options[rung] = const <GeoPlaceRecord>[]);
        break;
      }
      if (widget.value[rung]?.isEmpty ?? true) break;
      current = rung.child;
    }
    if (mounted) setState(() => _loading = false);
  }

  String _parentIdFor(GeoLevel level) {
    final GeoLevel? parent = level.parent;
    return parent == null ? '' : (widget.value[parent] ?? '');
  }

  Future<void> _pick(GeoLevel level, String? id) async {
    final Map<GeoLevel, String> next = Map<GeoLevel, String>.from(widget.value);
    next[level] = id ?? '';
    // Everything below a changed rung stops meaning anything.
    for (GeoLevel? below = level.child;
        below != null;
        below = below.child) {
      next.remove(below);
      _options.remove(below);
    }
    widget.onChanged(next);
    if ((id ?? '').isEmpty) {
      setState(() {});
      return;
    }
    final GeoLevel? child = level.child;
    if (child != null && widget.levels.contains(child)) {
      await _loadFrom(child);
    } else {
      setState(() {});
    }
  }

  /// Options for one rung, keeping any stored id that is not in the list.
  ///
  /// `DropdownButtonFormField` asserts when its value matches no item, so a
  /// record pointing at a retired place — or one loaded while geography could
  /// not be read — would otherwise break the whole form. Keeping it also means
  /// saving cannot quietly clear a value nobody could see.
  List<DropdownMenuItem<String>> _items(GeoLevel level) {
    final List<GeoPlaceRecord> rows =
        _options[level] ?? const <GeoPlaceRecord>[];
    final String current = widget.value[level] ?? '';
    return <DropdownMenuItem<String>>[
      const DropdownMenuItem<String>(value: '', child: Text('None')),
      for (final GeoPlaceRecord row in rows)
        DropdownMenuItem<String>(
          value: row.id,
          child: Text(level == GeoLevel.postalCode ? row.code : row.name),
        ),
      if (current.isNotEmpty && !rows.any((row) => row.id == current))
        DropdownMenuItem<String>(
          value: current,
          child: const Text('Currently set (not listed)'),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final GeoLevel level in widget.levels)
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String>(
                isExpanded: true,
                initialValue: widget.value[level] ?? '',
                decoration: InputDecoration(
                  labelText: level.label,
                  helperText: level == widget.levels.first &&
                          (_options[level]?.isEmpty ?? true) &&
                          !_loading
                      ? 'No places defined — a platform administrator '
                          'maintains these under Sales → Places.'
                      : null,
                ),
                // A rung whose parent is unset has nothing to offer, so it is
                // disabled rather than showing an empty list that looks broken.
                onChanged: !widget.enabled ||
                        (level.parent != null &&
                            widget.levels.contains(level.parent) &&
                            _parentIdFor(level).isEmpty)
                    ? null
                    : (id) => _pick(level, id),
                items: _items(level),
              ),
            ),
        ],
      );
}
