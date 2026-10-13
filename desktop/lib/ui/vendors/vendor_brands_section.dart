import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/product.dart';

/// The brands a supplier may sell (backlog 129), on the phase 2 supplier
/// record. A purchase order to the supplier offers only these brands'
/// products; with none ticked the supplier is not limited, or takes its
/// company's or its main office's list. Two reads when it opens, one write on
/// Save.
class VendorBrandsSection extends StatefulWidget {
  const VendorBrandsSection({
    super.key,
    required this.api,
    required this.vendorId,
    this.canManage = false,
  });

  final ApiClient api;
  final String vendorId;

  /// `VENDOR_UPDATE`: tick brands and save.
  final bool canManage;

  @override
  State<VendorBrandsSection> createState() => _VendorBrandsSectionState();
}

class _VendorBrandsSectionState extends State<VendorBrandsSection> {
  List<BrandRecord>? _firmBrands;
  VendorBrands? _stored;
  Set<String> _ticked = <String>{};
  String? _error;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  /// Clears the pane first, so a failed read leaves nothing that could be
  /// saved over the supplier's list.
  Future<void> _load() async {
    setState(() {
      _firmBrands = null;
      _stored = null;
      _error = null;
    });
    try {
      final List<BrandRecord> brands = await widget.api.brands();
      final VendorBrands stored = await widget.api.vendorBrands(widget.vendorId);
      if (!mounted) return;
      setState(() {
        _firmBrands = brands;
        _stored = stored;
        _ticked = stored.namedBrandIds.toSet();
      });
    } on Object catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception is ApiException
          ? exception.message
          : 'The brands could not be read.');
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final VendorBrands saved = await widget.api.setVendorBrands(
        widget.vendorId,
        _ticked.toList(),
      );
      if (!mounted) return;
      setState(() {
        _stored = saved;
        _ticked = saved.namedBrandIds.toSet();
        _saving = false;
      });
      NotificationService.show(context, 'Brands saved.',
          kind: AppNotificationKind.success);
    } on Object catch (exception) {
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
          context,
          exception is ApiException
              ? exception.message
              : 'The brands could not be saved.',
          kind: AppNotificationKind.error);
    }
  }

  String _names(List<BrandRecord> brands) =>
      brands.map((brand) => brand.name).join(', ');

  /// What applies when nothing is ticked.
  String _helper(VendorBrands stored) => switch (stored.source) {
        'COMPANY' => 'No brand ticked: the brands of its company are '
            'offered: ${_names(stored.brands)}.',
        'MAIN_OFFICE' => 'No brand ticked: it takes the brands of its main '
            'office, ${stored.sourceVendorName}: ${_names(stored.brands)}.',
        'OWN' => 'Save with no brand ticked to clear this supplier\'s list.',
        _ => 'No brand ticked: every product is offered on this supplier\'s '
            'orders.',
      };

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final TextStyle? note = theme.textTheme.bodySmall?.copyWith(
      color: theme.colorScheme.onSurfaceVariant,
    );
    if (_error != null) {
      return Row(children: [
        Flexible(
          child: Text(_error!,
              key: const ValueKey('vendor-brands-error'),
              style: note?.copyWith(color: theme.colorScheme.error)),
        ),
        TextButton(
          key: const ValueKey('vendor-brands-retry'),
          onPressed: () => unawaited(_load()),
          child: const Text('Try again'),
        ),
      ]);
    }
    final List<BrandRecord>? firm = _firmBrands;
    final VendorBrands? stored = _stored;
    if (firm == null || stored == null) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    final List<BrandRecord> shown = [
      for (final BrandRecord brand in firm)
        if (brand.isActive || stored.namedBrandIds.contains(brand.id)) brand,
    ];
    if (shown.isEmpty) {
      return Text(
        'No brands yet. Add them under Brands.',
        key: const ValueKey('vendor-brands-none'),
        style: note,
      );
    }
    final bool dirty = !(_ticked.length == stored.namedBrandIds.length &&
        _ticked.containsAll(stored.namedBrandIds));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final BrandRecord brand in shown)
          CheckboxListTile(
            key: ValueKey<String>('vendor-brand-${brand.id}'),
            dense: true,
            controlAffinity: ListTileControlAffinity.leading,
            contentPadding: EdgeInsets.zero,
            value: _ticked.contains(brand.id),
            title: Row(children: [
              Flexible(child: Text(brand.name, overflow: TextOverflow.ellipsis)),
              if (brand.principalName.isNotEmpty) ...[
                const SizedBox(width: 10),
                Flexible(
                  child: Text(brand.principalName,
                      overflow: TextOverflow.ellipsis, style: note),
                ),
              ],
            ]),
            onChanged: widget.canManage
                ? (value) => setState(() {
                      if (value == true) {
                        _ticked.add(brand.id);
                      } else {
                        _ticked.remove(brand.id);
                      }
                    })
                : null,
          ),
        if (_ticked.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(_helper(stored),
                key: const ValueKey('vendor-brands-helper'), style: note),
          ),
        if (widget.canManage)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Align(
              alignment: Alignment.centerLeft,
              child: FilledButton(
                key: const ValueKey('vendor-brands-save'),
                onPressed: _saving || !dirty ? null : () => unawaited(_save()),
                child: const Text('Save brands'),
              ),
            ),
          ),
      ],
    );
  }
}
