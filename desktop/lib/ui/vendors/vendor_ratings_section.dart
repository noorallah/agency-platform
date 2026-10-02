import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/design/design_tokens.dart';
import '../../models/entities.dart' show Json;
import '../../models/firm_member.dart';
import '../../models/vendor_rating.dart';
import '../workspace/desktop_framework.dart';

/// The note shown where a new supplier has no record to rate yet.
class VendorRatingsAfterSave extends StatelessWidget {
  const VendorRatingsAfterSave({super.key});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.md),
        child: Text(
          'Save the supplier first. Ratings are kept once the supplier exists.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
}

/// What people think of a supplier (BUY-15), phase 2 only. Kept apart from
/// the supplier performance figures, which are measured from documents.
class VendorRatingsSection extends StatefulWidget {
  const VendorRatingsSection({
    super.key,
    required this.load,
    required this.onRate,
    required this.onWithdraw,
    this.loadMembers,
  });

  final Future<VendorRatings> Function() load;
  final Future<void> Function(Json body) onRate;
  final Future<void> Function() onWithdraw;

  /// Maps user ids to names; without it raters read "A colleague".
  final Future<List<FirmMember>> Function()? loadMembers;

  @override
  State<VendorRatingsSection> createState() => _VendorRatingsSectionState();
}

class _VendorRatingsSectionState extends State<VendorRatingsSection> {
  VendorRatings? _data;
  Map<String, String> _names = const <String, String>{};
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
    unawaited(_loadNames());
  }

  Future<void> _loadNames() async {
    final Future<List<FirmMember>> Function()? loader = widget.loadMembers;
    if (loader == null) return;
    try {
      final List<FirmMember> people = await loader();
      if (!mounted) return;
      setState(() => _names = <String, String>{
            for (final FirmMember p in people) p.userId: p.label,
          });
    } on ApiException {
      // Names are a courtesy; the ratings read the same without them.
    }
  }

  Future<void> _reload() async {
    try {
      final VendorRatings data = await widget.load();
      if (!mounted) return;
      setState(() {
        _data = data;
        _error = null;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _data ??= const VendorRatings(
          count: 0,
          averages: <String, String?>{},
          overall: null,
          ratings: <VendorRating>[],
          mine: null,
        );
        _error = exception.message;
      });
    }
  }

  Future<void> _rate() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) =>
          VendorRatingDialog(existing: _data?.mine, onSave: widget.onRate),
    );
    if (saved == true) await _reload();
  }

  Future<void> _withdraw() async {
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Withdraw my rating?',
      message: 'Your scores and remark are taken off this supplier. The trail '
          'keeps that they were withdrawn.',
      confirmLabel: 'Withdraw',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    try {
      await widget.onWithdraw();
      await _reload();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  String _who(VendorRating row) {
    if (row.id == _data?.mine?.id) return 'You';
    return _names[row.ratedBy] ?? 'A colleague';
  }

  String _day(String iso) => iso.length >= 10 ? iso.substring(0, 10) : iso;

  String _scoreWords(VendorRating row) => <String>[
        for (final (String key, String label) in vendorRatingCriteria)
          '$label ${row.scores[key]}',
      ].join(', ');

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final VendorRatings? data = _data;
    final bool rated = data?.mine != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          "People's opinion, kept apart from the supplier performance "
          'figures',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: AppSpacing.sm),
        Wrap(
          spacing: AppSpacing.sm,
          children: [
            FilledButton.tonalIcon(
              key: const ValueKey<String>('ratings-rate'),
              onPressed: data == null ? null : _rate,
              icon: const Icon(Icons.star_outline),
              label: Text(rated ? 'Change my rating' : 'Rate this supplier'),
            ),
            if (rated)
              OutlinedButton.icon(
                key: const ValueKey<String>('ratings-withdraw'),
                onPressed: _withdraw,
                icon: const Icon(Icons.undo),
                label: const Text('Withdraw my rating'),
              ),
          ],
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              _error!,
              key: const ValueKey<String>('ratings-error'),
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ),
        const SizedBox(height: AppSpacing.sm),
        if (data == null)
          const Center(child: CircularProgressIndicator())
        else if (data.count == 0)
          const Text(
            'Nobody has rated this supplier yet.',
            key: ValueKey<String>('ratings-empty'),
          )
        else ...[
          Text(
            '${data.overall ?? '-'} of 5 from ${data.count} '
            '${data.count == 1 ? 'person' : 'people'}',
            key: const ValueKey<String>('ratings-overall'),
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.xs,
            children: [
              for (final (String key, String label) in vendorRatingCriteria)
                Text(
                  '$label ${data.averages[key] ?? '-'}',
                  key: ValueKey<String>('ratings-average-$key'),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Card(
            child: Column(
              children: [
                for (final VendorRating row in data.ratings)
                  ListTile(
                    key: ValueKey<String>('rating-${row.id}'),
                    leading: const Icon(Icons.star_outline),
                    title: Text(
                      '${_who(row)} · ${_day(row.ratedOn)} · '
                      '${_scoreWords(row)}',
                    ),
                    subtitle: row.remark.isEmpty ? null : Text(row.remark),
                  ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// Five 1 to 5 pickers and a remark; stays open with the server's message on
/// a refusal (D-DLG-1).
class VendorRatingDialog extends StatefulWidget {
  const VendorRatingDialog({super.key, this.existing, required this.onSave});

  final VendorRating? existing;
  final Future<void> Function(Json body) onSave;

  @override
  State<VendorRatingDialog> createState() => _VendorRatingDialogState();
}

class _VendorRatingDialogState extends State<VendorRatingDialog>
    with SaveInDialog<VendorRatingDialog> {
  late final Map<String, int?> _scores = <String, int?>{
    for (final (String key, String _) in vendorRatingCriteria)
      key: widget.existing?.scores[key],
  };
  late final TextEditingController _remark =
      TextEditingController(text: widget.existing?.remark ?? '');

  @override
  void dispose() {
    _remark.dispose();
    super.dispose();
  }

  bool get _complete => _scores.values.every((int? v) => v != null && v > 0);

  Json _body() {
    final String remark = _remark.text.trim();
    return <String, dynamic>{
      for (final MapEntry<String, int?> e in _scores.entries) e.key: e.value,
      if (remark.isNotEmpty) 'remark': remark,
    };
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(
        widget.existing == null ? 'Rate this supplier' : 'Change my rating',
      ),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              for (final (String key, String label) in vendorRatingCriteria)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Row(
                    children: [
                      SizedBox(width: 120, child: Text(label)),
                      for (int n = 1; n <= 5; n++)
                        Padding(
                          padding: const EdgeInsets.only(right: 6),
                          child: ChoiceChip(
                            key: ValueKey<String>('rating-$key-$n'),
                            label: Text('$n'),
                            selected: _scores[key] == n,
                            onSelected: saving
                                ? null
                                : (_) => setState(() => _scores[key] = n),
                          ),
                        ),
                    ],
                  ),
                ),
              const Text('1 is poor, 5 is excellent.'),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                key: const ValueKey<String>('rating-remark'),
                controller: _remark,
                maxLength: 1000,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Remark (optional)',
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey<String>('rating-save'),
          onPressed: saving || !_complete
              ? null
              : () => saveAndClose<bool>(() async {
                    await widget.onSave(_body());
                    return true;
                  }),
          child: Text(saving ? 'Saving…' : 'Save rating'),
        ),
      ],
    );
  }
}
