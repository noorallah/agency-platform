import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../models/entities.dart';
import '../workspace/paged_fetch.dart';

/// Pick the job a person is being hired into.
///
/// The dialog owns everything it builds. A caller that creates a controller,
/// awaits `showDialog` and then disposes it disposes it *mid-animation*, and
/// the field rebuilding during the exit throws "A TextEditingController was
/// used after being disposed" -- written twice in this repo before
/// `askForReason` existed. There is no text field here, but the same rule
/// applies to the future: the dialog loads its own list and holds its own
/// state.
///
/// Returns the chosen template, or null for a dismissal.
Future<UserTemplate?> pickUserTemplate(
  BuildContext context,
  ApiClient api, {
  required String personName,
}) =>
    showDialog<UserTemplate>(
      context: context,
      builder: (_) => _ApplyTemplateDialog(api: api, personName: personName),
    );

class _ApplyTemplateDialog extends StatefulWidget {
  const _ApplyTemplateDialog({required this.api, required this.personName});

  final ApiClient api;
  final String personName;

  @override
  State<_ApplyTemplateDialog> createState() => _ApplyTemplateDialogState();
}

class _ApplyTemplateDialogState extends State<_ApplyTemplateDialog> {
  late Future<List<UserTemplate>> _templates;
  String? _selectedId;

  @override
  void initState() {
    super.initState();
    _templates = fetchAllPages<UserTemplate>(
      (page) => widget.api.userTemplates(page: page, pageSize: 100),
    ).then(
      // An inactive template is one the firm has stopped hiring into. It stays
      // listed on the templates screen, where retiring it is the point; it has
      // no business being offered here.
      (rows) => rows.where((row) => row.isActive).toList(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Apply a job template'),
      // An AlertDialog gives its content unbounded height, so a stretched
      // Column with no width overflows by tens of thousands of pixels instead
      // of laying out. Both dimensions are bounded here on purpose.
      content: SizedBox(
        width: 520,
        height: 380,
        child: FutureBuilder<List<UserTemplate>>(
          future: _templates,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snapshot.hasError) {
              return Center(child: Text('${snapshot.error}'));
            }
            final List<UserTemplate> rows = snapshot.data ?? const [];
            if (rows.isEmpty) {
              return const Center(
                child: Text('No job templates are available.'),
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Whatever ${widget.personName} holds now is replaced by the '
                  "job's roles. You can edit them afterwards like any other "
                  'user.',
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                Expanded(
                  child: ListView.builder(
                    itemCount: rows.length,
                    itemBuilder: (context, index) {
                      final UserTemplate row = rows[index];
                      final bool chosen = row.id == _selectedId;
                      // A selectable ListTile rather than RadioListTile: that
                      // widget's `groupValue`/`onChanged` pair is deprecated
                      // in favour of a RadioGroup ancestor, and one tile is
                      // not worth an ancestor.
                      return ListTile(
                        selected: chosen,
                        onTap: () => setState(() => _selectedId = row.id),
                        leading: Icon(
                          chosen
                              ? Icons.radio_button_checked
                              : Icons.radio_button_unchecked,
                        ),
                        title: Text(row.name),
                        // What the job actually gets. A template chosen by
                        // name alone is a permission decision made blind.
                        subtitle: Text(
                          row.roleCodes.isEmpty
                              ? row.description
                              : row.roleCodes.join(', '),
                        ),
                      );
                    },
                  ),
                ),
              ],
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _selectedId == null ? null : _apply,
          child: const Text('Apply'),
        ),
      ],
    );
  }

  Future<void> _apply() async {
    final List<UserTemplate> rows = await _templates;
    if (!mounted) return;
    Navigator.of(context).pop(
      rows.firstWhere((row) => row.id == _selectedId),
    );
  }
}
