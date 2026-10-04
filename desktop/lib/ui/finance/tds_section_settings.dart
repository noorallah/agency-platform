import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/design/design_tokens.dart';
import '../../core/notifications/notification_service.dart';
import '../../models/entities.dart';
import '../../models/tds.dart';

/// The firm's policy for one of the sections 194C or 194J (PG-5): whether it
/// deducts, the thresholds, and the three rates. Rendered beneath the 194Q
/// settings in the same dialog.
///
/// Saving sends only what moved, because the endpoint is partial: a key left
/// out stays as it is. Section 194J has no single-payment threshold, so the
/// box is not shown for it.
class TdsSectionSettingsCard extends StatefulWidget {
  const TdsSectionSettingsCard({
    super.key,
    required this.api,
    required this.section,
    required this.settings,
    required this.editable,
  });

  final ApiClient api;
  final String section;
  final Json settings;
  final bool editable;

  @override
  State<TdsSectionSettingsCard> createState() => _TdsSectionSettingsCardState();
}

class _TdsSectionSettingsCardState extends State<TdsSectionSettingsCard> {
  late bool _enabled = widget.settings['is_enabled'] == true;
  late final TextEditingController _single = _box('single_threshold_amount');
  late final TextEditingController _annual = _box('annual_threshold_amount');
  late final TextEditingController _rate = _box('rate_percent');
  late final TextEditingController _lower = _box('lower_rate_percent');
  late final TextEditingController _noPan = _box('rate_without_pan_percent');
  bool _saving = false;
  String? _error;
  bool get _hasSingle => widget.section == '194C';

  TextEditingController _box(String key) =>
      TextEditingController(text: '${widget.settings[key] ?? ''}');

  @override
  void dispose() {
    _single.dispose();
    _annual.dispose();
    _rate.dispose();
    _lower.dispose();
    _noPan.dispose();
    super.dispose();
  }

  /// Only the fields whose text differs from what was loaded.
  Json _changes() {
    final Json body = <String, dynamic>{};
    if (_enabled != (widget.settings['is_enabled'] == true)) {
      body['is_enabled'] = _enabled;
    }
    void diff(String key, TextEditingController box) {
      final String loaded = '${widget.settings[key] ?? ''}';
      if (box.text.trim() != loaded) {
        body[key] = box.text.trim().isEmpty ? null : box.text.trim();
      }
    }

    if (_hasSingle) diff('single_threshold_amount', _single);
    diff('annual_threshold_amount', _annual);
    diff('rate_percent', _rate);
    diff('lower_rate_percent', _lower);
    diff('rate_without_pan_percent', _noPan);
    return body;
  }

  Future<void> _save() async {
    final Json body = _changes();
    if (body.isEmpty) {
      setState(() => _error = 'Nothing has changed.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.saveTdsSectionSettings(widget.section, body);
      if (!mounted) return;
      setState(() => _saving = false);
      NotificationService.show(
        context,
        '${widget.section} settings saved.',
        kind: AppNotificationKind.success,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = error.message;
      });
    }
  }

  Widget _field(
    String key,
    String label,
    TextEditingController box, {
    String? helper,
  }) =>
      Padding(
        padding: const EdgeInsets.only(top: AppSpacing.sm),
        child: TextField(
          key: ValueKey('tds${widget.section}-$key'),
          controller: box,
          enabled: widget.editable && !_saving,
          decoration: InputDecoration(labelText: label, helperText: helper),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final bool on = widget.editable && !_saving;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Divider(height: AppSpacing.xl),
        Text(
          '${widget.section} - ${tdsSections[widget.section] ?? ''}',
          style: theme.textTheme.titleSmall,
        ),
        SwitchListTile(
          key: ValueKey('tds${widget.section}-enabled'),
          contentPadding: EdgeInsets.zero,
          title: Text('Deduct ${widget.section}'),
          value: _enabled,
          onChanged: on ? (value) => setState(() => _enabled = value) : null,
        ),
        if (_hasSingle) _field('single', 'Threshold per payment', _single),
        _field('annual', 'Threshold per supplier, per year', _annual),
        _field('rate', 'Rate %', _rate),
        _field(
          'lower',
          'Lower rate % (certificate)',
          _lower,
          helper: 'Only where the supplier holds a lower-deduction '
              'certificate; blank means none.',
        ),
        _field(
          'no-pan',
          'Rate % without a PAN',
          _noPan,
          helper: 'Section 206AA, when the supplier has given none.',
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
        if (widget.editable)
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: FilledButton(
                key: ValueKey('tds${widget.section}-save'),
                onPressed: _saving ? null : _save,
                child: Text('Save ${widget.section}'),
              ),
            ),
          ),
      ],
    );
  }
}
