import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/notifications/notification_service.dart';
import '../../core/security/permission_service.dart';
import '../../models/print_template.dart';

/// How this firm prints one kind of document.
///
/// Opened from beside the Print button, because that is where somebody stands
/// when they discover the copies are wrong. It edits the firm's template for
/// one document type; a firm that has saved nothing sees the platform defaults
/// and the dialog says so, rather than showing empty boxes that look broken.
class PrintSettingsDialog extends StatefulWidget {
  const PrintSettingsDialog({
    super.key,
    required this.api,
    required this.permissions,
    required this.documentType,
    required this.documentLabel,
    this.managePermission = 'PLATFORM_SETTINGS',
  });

  final ApiClient api;
  final PermissionService permissions;

  /// `SALES_INVOICE`, `PURCHASE_ORDER`.
  final String documentType;

  /// What to call it on screen: "sales invoice", "purchase order".
  final String documentLabel;

  /// Reading is anyone who may see the document; changing is this.
  final String managePermission;

  @override
  State<PrintSettingsDialog> createState() => _PrintSettingsDialogState();
}

class _PrintSettingsDialogState extends State<PrintSettingsDialog> {
  final TextEditingController _title = TextEditingController();
  final TextEditingController _bank = TextEditingController();
  final TextEditingController _terms = TextEditingController();
  final TextEditingController _declaration = TextEditingController();
  final TextEditingController _jurisdiction = TextEditingController();
  final TextEditingController _signatory = TextEditingController();
  final TextEditingController _footer = TextEditingController();

  /// One controller per copy, so a firm can name them as it likes.
  List<TextEditingController> _copies = <TextEditingController>[];

  bool _showBank = true;
  bool _showDiscount = true;
  bool _showBatch = false;
  bool _showExpiry = false;
  String _pageSize = 'A4';
  bool _loading = true;
  bool _saving = false;
  bool _isCustomised = false;
  String? _error;

  bool get _mayManage =>
      widget.permissions.hasPermission(widget.managePermission);

  @override
  void initState() {
    super.initState();
    unawaitedLoad();
  }

  void unawaitedLoad() {
    _load();
  }

  @override
  void dispose() {
    for (final TextEditingController controller in <TextEditingController>[
      _title,
      _bank,
      _terms,
      _declaration,
      _jurisdiction,
      _signatory,
      _footer,
      ..._copies,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final PrintTemplate template =
          await widget.api.printTemplate(widget.documentType);
      if (!mounted) return;
      setState(() {
        _title.text = template.titleText;
        _bank.text = template.bankDetails;
        _terms.text = template.terms;
        _declaration.text = template.declaration;
        _jurisdiction.text = template.jurisdiction;
        _signatory.text = template.signatoryText;
        _footer.text = template.footerNote;
        _showBank = template.showBankDetails;
        _showDiscount = template.showDiscountColumn;
        _showBatch = template.showBatchColumn;
        _showExpiry = template.showExpiryColumn;
        _pageSize = template.pageSize;
        _copies = [
          for (final String label in template.copyLabels)
            TextEditingController(text: label),
        ];
        _isCustomised = template.isCustomised;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    }
  }

  /// Set how many copies a print run produces.
  ///
  /// Growing takes the conventional label for that position, so the ordinary
  /// three-copy set needs no typing; shrinking drops from the end, and the
  /// labels above it keep whatever the firm called them.
  void _setCopyCount(int count) {
    setState(() {
      while (_copies.length > count) {
        _copies.removeLast().dispose();
      }
      while (_copies.length < count) {
        final int index = _copies.length;
        _copies.add(
          TextEditingController(
            text: index < defaultCopyLabels.length
                ? defaultCopyLabels[index]
                : 'COPY ${index + 1}',
          ),
        );
      }
    });
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.savePrintTemplate(
        widget.documentType,
        PrintTemplate(
          documentType: widget.documentType,
          titleText: _title.text.trim().isEmpty
              ? 'TAX INVOICE'
              : _title.text.trim(),
          showBankDetails: _showBank,
          bankDetails: _bank.text.trim(),
          terms: _terms.text.trim(),
          declaration: _declaration.text.trim(),
          jurisdiction: _jurisdiction.text.trim(),
          signatoryText: _signatory.text.trim(),
          footerNote: _footer.text.trim(),
          showDiscountColumn: _showDiscount,
          showBatchColumn: _showBatch,
          showExpiryColumn: _showExpiry,
          // A copy with no name is not a copy: an empty box would print a
          // blank banner rather than saying which copy the page is.
          copyLabels: [
            for (final TextEditingController copy in _copies)
              if (copy.text.trim().isNotEmpty) copy.text.trim(),
          ],
          pageSize: _pageSize,
        ),
      );
      if (!mounted) return;
      NotificationService.show(
        context,
        'Print settings saved.',
        kind: AppNotificationKind.success,
      );
      Navigator.of(context).pop(true);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return AlertDialog(
      title: Text('Print settings — ${widget.documentLabel}'),
      content: SizedBox(
        width: 560,
        child: _loading
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            : SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (!_isCustomised)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(
                          'This firm has not changed anything yet, so these are '
                          'the platform defaults. Saving makes them the firm\'s own.',
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    _section(theme, 'Copies'),
                    Text(
                      'Each copy prints as its own page set, labelled so the '
                      'reader knows which one they are holding.',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Text('How many copies'),
                        const SizedBox(width: 12),
                        DropdownButton<int>(
                          value: _copies.length,
                          onChanged: _mayManage
                              ? (value) => _setCopyCount(value ?? 0)
                              : null,
                          items: [
                            for (int count = 0; count <= 4; count++)
                              DropdownMenuItem<int>(
                                value: count,
                                child: Text(
                                  count == 0
                                      ? 'One, unlabelled'
                                      : '$count, labelled',
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                    for (int index = 0; index < _copies.length; index++)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: TextField(
                          controller: _copies[index],
                          enabled: _mayManage,
                          decoration: InputDecoration(
                            labelText: 'Copy ${index + 1} label',
                            isDense: true,
                          ),
                        ),
                      ),
                    _section(theme, 'Letterhead'),
                    _field(_title, 'Title on the document'),
                    _field(_signatory, 'Signed for'),
                    _field(_footer, 'Footer note'),
                    _section(theme, 'Payment and terms'),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Show bank details'),
                      value: _showBank,
                      onChanged: _mayManage
                          ? (value) => setState(() => _showBank = value)
                          : null,
                    ),
                    _field(_bank, 'Bank details', lines: 3),
                    _field(_terms, 'Terms', lines: 3),
                    _field(_declaration, 'Declaration', lines: 2),
                    _field(_jurisdiction, 'Jurisdiction'),
                    _section(theme, 'Columns and paper'),
                    _toggle('Discount column', _showDiscount,
                        (value) => setState(() => _showDiscount = value)),
                    _toggle('Batch column', _showBatch,
                        (value) => setState(() => _showBatch = value)),
                    _toggle('Expiry column', _showExpiry,
                        (value) => setState(() => _showExpiry = value)),
                    Row(
                      children: [
                        const Text('Paper'),
                        const SizedBox(width: 12),
                        DropdownButton<String>(
                          value: _pageSize,
                          onChanged: _mayManage
                              ? (value) =>
                                  setState(() => _pageSize = value ?? 'A4')
                              : null,
                          items: const [
                            DropdownMenuItem(value: 'A4', child: Text('A4')),
                            DropdownMenuItem(value: 'A5', child: Text('A5')),
                          ],
                        ),
                      ],
                    ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          _error!,
                          style: theme.textTheme.bodyMedium
                              ?.copyWith(color: theme.colorScheme.error),
                        ),
                      ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Close'),
        ),
        FilledButton(
          onPressed: _mayManage && !_saving && !_loading ? _save : null,
          child: Text(_saving ? 'Saving…' : 'Save'),
        ),
      ],
    );
  }

  Widget _section(ThemeData theme, String label) => Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 6),
        child: Text(label, style: theme.textTheme.titleSmall),
      );

  Widget _field(
    TextEditingController controller,
    String label, {
    int lines = 1,
  }) =>
      Padding(
        padding: const EdgeInsets.only(top: 8),
        child: TextField(
          controller: controller,
          enabled: _mayManage,
          maxLines: lines,
          decoration: InputDecoration(labelText: label, isDense: true),
        ),
      );

  Widget _toggle(String label, bool value, ValueChanged<bool> onChanged) =>
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(label),
        value: value,
        onChanged: _mayManage ? onChanged : null,
      );
}
