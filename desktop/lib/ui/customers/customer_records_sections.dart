import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_client.dart';
import '../../core/dialogs/app_dialogs.dart';
import '../../core/design/design_tokens.dart';
import '../../models/customer_records.dart';
import '../../models/entities.dart' show Json;
import '../inventory/stock_evidence_picker.dart';
import '../workspace/desktop_framework.dart';

/// The note shown where a new customer has no record to attach these to yet.
class CustomerRecordsAfterSave extends StatelessWidget {
  const CustomerRecordsAfterSave({super.key, required this.what});

  final String what;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.md),
        child: Text(
          'Save the customer first. $what are kept once the customer exists.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
}

/// The bank accounts held against a customer (MST-4), phase 2 only.
///
/// Reads through [load]; [onSave] is null for somebody without
/// `CUSTOMER_MANAGE_BANK_DETAILS`, which hides the Edit button -- the server
/// refuses the write just the same, and sends such a reader a masked number.
class CustomerBankAccountsSection extends StatefulWidget {
  const CustomerBankAccountsSection({
    super.key,
    required this.load,
    this.onSave,
  });

  final Future<List<CustomerBankAccount>> Function() load;
  final Future<void> Function(List<Json> accounts)? onSave;

  @override
  State<CustomerBankAccountsSection> createState() =>
      _CustomerBankAccountsSectionState();
}

class _CustomerBankAccountsSectionState
    extends State<CustomerBankAccountsSection> {
  List<CustomerBankAccount>? _rows;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  Future<void> _reload() async {
    try {
      final List<CustomerBankAccount> rows = await widget.load();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _error = null;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _rows = const <CustomerBankAccount>[];
        _error = exception.message;
      });
    }
  }

  Future<void> _edit() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => CustomerBankAccountsDialog(
        accounts: _rows ?? const <CustomerBankAccount>[],
        onSave: widget.onSave!,
      ),
    );
    if (saved == true) await _reload();
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<CustomerBankAccount>? rows = _rows;
    final bool anyMasked =
        rows?.any((CustomerBankAccount a) => a.masked) ?? false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.onSave != null)
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton.tonalIcon(
              key: const ValueKey<String>('bank-accounts-edit'),
              onPressed: rows == null ? null : _edit,
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Edit bank accounts'),
            ),
          ),
        if (_error != null)
          Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
        if (rows == null)
          const Center(child: CircularProgressIndicator())
        else if (rows.isEmpty)
          const Text('No bank accounts have been recorded.')
        else
          Card(
            child: Column(
              children: [
                for (final CustomerBankAccount row in rows)
                  ListTile(
                    key: ValueKey<String>('bank-account-${row.id}'),
                    leading: const Icon(Icons.account_balance_outlined),
                    title: Text(
                      '${row.bankName} · ${row.accountNumber}',
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      [
                        row.accountName,
                        if (row.ifsc.isNotEmpty) row.ifsc,
                        if (row.branch.isNotEmpty) row.branch,
                        if (row.upiId.isNotEmpty) row.upiId,
                      ].join(' · '),
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: row.isPrimary ? const Text('Primary') : null,
                  ),
              ],
            ),
          ),
        if (anyMasked)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              'Only someone allowed to change bank details sees the full '
              'number.',
              key: const ValueKey<String>('bank-accounts-masked-note'),
              style: theme.textTheme.bodySmall,
            ),
          ),
      ],
    );
  }
}

class _AccountDraft {
  _AccountDraft([CustomerBankAccount? from])
      : bank = TextEditingController(text: from?.bankName ?? ''),
        holder = TextEditingController(text: from?.accountName ?? ''),
        number = TextEditingController(text: from?.accountNumber ?? ''),
        ifsc = TextEditingController(text: from?.ifsc ?? ''),
        branch = TextEditingController(text: from?.branch ?? ''),
        upi = TextEditingController(text: from?.upiId ?? '');

  final TextEditingController bank;
  final TextEditingController holder;
  final TextEditingController number;
  final TextEditingController ifsc;
  final TextEditingController branch;
  final TextEditingController upi;

  void dispose() {
    for (final TextEditingController c in [
      bank,
      holder,
      number,
      ifsc,
      branch,
      upi,
    ]) {
      c.dispose();
    }
  }

  Json toJson(bool primary) {
    String? optional(TextEditingController c) =>
        c.text.trim().isEmpty ? null : c.text.trim();
    return <String, dynamic>{
      'bank_name': bank.text.trim(),
      'account_name': holder.text.trim(),
      'account_number': number.text.trim(),
      'ifsc': optional(ifsc),
      'branch': optional(branch),
      'upi_id': optional(upi),
      'is_primary': primary,
    };
  }
}

/// Edits the customer's whole list of bank accounts and saves it in one
/// call; stays open with the server's message on a refusal (D-DLG-1).
class CustomerBankAccountsDialog extends StatefulWidget {
  const CustomerBankAccountsDialog({
    super.key,
    required this.accounts,
    required this.onSave,
  });

  final List<CustomerBankAccount> accounts;
  final Future<void> Function(List<Json> accounts) onSave;

  @override
  State<CustomerBankAccountsDialog> createState() =>
      _CustomerBankAccountsDialogState();
}

class _CustomerBankAccountsDialogState extends State<CustomerBankAccountsDialog>
    with SaveInDialog<CustomerBankAccountsDialog> {
  late final List<_AccountDraft> _drafts =
      widget.accounts.map(_AccountDraft.new).toList();
  late int _primary = widget.accounts.indexWhere((a) => a.isPrimary);

  @override
  void dispose() {
    for (final _AccountDraft draft in _drafts) {
      draft.dispose();
    }
    super.dispose();
  }

  void _add() => setState(() => _drafts.add(_AccountDraft()));

  void _remove(int index) {
    setState(() {
      _drafts.removeAt(index).dispose();
      if (_primary == index) {
        _primary = -1;
      } else if (_primary > index) {
        _primary--;
      }
    });
  }

  Widget _field(
    TextEditingController controller,
    String label,
    double width, {
    String? key,
  }) =>
      SizedBox(
        width: width,
        child: TextField(
          key: key == null ? null : ValueKey<String>(key),
          controller: controller,
          decoration: InputDecoration(labelText: label, isDense: true),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Bank accounts'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              if (_drafts.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.md),
                  child: Text('No accounts. Saving now clears the list.'),
                ),
              for (int i = 0; i < _drafts.length; i++)
                Card(
                  key: ValueKey<String>('bank-draft-$i'),
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: AppSpacing.md,
                          runSpacing: AppSpacing.md,
                          children: [
                            _field(_drafts[i].bank, 'Bank', 190,
                                key: 'bank-name-$i'),
                            _field(_drafts[i].holder, 'Account holder', 190,
                                key: 'bank-holder-$i'),
                            _field(_drafts[i].number, 'Account number', 190,
                                key: 'bank-number-$i'),
                            _field(_drafts[i].ifsc, 'IFSC', 140),
                            _field(_drafts[i].branch, 'Branch', 190),
                            _field(_drafts[i].upi, 'UPI id', 190),
                          ],
                        ),
                        const SizedBox(height: AppSpacing.sm),
                        Row(
                          children: [
                            ChoiceChip(
                              key: ValueKey<String>('bank-primary-$i'),
                              label: const Text('Primary account'),
                              selected: _primary == i,
                              onSelected: (_) => setState(() => _primary = i),
                            ),
                            const Spacer(),
                            IconButton(
                              key: ValueKey<String>('bank-remove-$i'),
                              tooltip: 'Remove account',
                              icon: const Icon(Icons.delete_outline),
                              onPressed: saving ? null : () => _remove(i),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  key: const ValueKey<String>('bank-add'),
                  onPressed: saving ? null : _add,
                  icon: const Icon(Icons.add),
                  label: const Text('Add account'),
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
          key: const ValueKey<String>('bank-save'),
          onPressed: saving
              ? null
              : () => saveAndClose<bool>(() async {
                    await widget.onSave(<Json>[
                      for (int i = 0; i < _drafts.length; i++)
                        _drafts[i].toJson(_primary == i),
                    ]);
                    return true;
                  }),
          child: Text(saving ? 'Saving…' : 'Save accounts'),
        ),
      ],
    );
  }
}

/// The files kept with a customer (MST-4), phase 2 only: name, caption and
/// day, with Add files and Remove for somebody who may update the customer.
class CustomerFilesSection extends StatefulWidget {
  const CustomerFilesSection({
    super.key,
    required this.load,
    this.onAdd,
    this.onRemove,
    this.pickFiles,
  });

  final Future<List<CustomerAttachment>> Function() load;

  /// Null hides adding (no `CUSTOMER_UPDATE`).
  final Future<void> Function(List<Json> files)? onAdd;

  /// Null hides removing (no `CUSTOMER_UPDATE`).
  final Future<void> Function(String attachmentId)? onRemove;

  /// Injected by tests; the platform's file chooser otherwise.
  final Future<List<XFile>> Function()? pickFiles;

  @override
  State<CustomerFilesSection> createState() => _CustomerFilesSectionState();
}

class _CustomerFilesSectionState extends State<CustomerFilesSection> {
  List<CustomerAttachment>? _rows;
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_reload());
  }

  Future<void> _reload() async {
    try {
      final List<CustomerAttachment> rows = await widget.load();
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _error = null;
      });
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() {
        _rows = const <CustomerAttachment>[];
        _error = exception.message;
      });
    }
  }

  Future<void> _add() async {
    final bool? saved = await showDialog<bool>(
      context: context,
      builder: (_) => CustomerFilesDialog(
        onAdd: widget.onAdd!,
        pickFiles: widget.pickFiles,
      ),
    );
    if (saved == true) await _reload();
  }

  Future<void> _remove(CustomerAttachment file) async {
    final bool go = await showWorkspaceConfirmDialog(
      context,
      title: 'Remove ${file.fileName}?',
      message: 'The file is taken off this customer. The trail keeps that it '
          'was removed.',
      confirmLabel: 'Remove',
      type: ConfirmationType.delete,
    );
    if (!go || !mounted) return;
    try {
      await widget.onRemove!(file.id);
      await _reload();
    } on ApiException catch (exception) {
      if (!mounted) return;
      setState(() => _error = exception.message);
    }
  }

  String _day(String iso) => iso.length >= 10 ? iso.substring(0, 10) : iso;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final List<CustomerAttachment>? rows = _rows;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (widget.onAdd != null)
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton.tonalIcon(
              key: const ValueKey<String>('customer-files-add'),
              onPressed: rows == null ? null : _add,
              icon: const Icon(Icons.attach_file),
              label: const Text('Add files'),
            ),
          ),
        if (_error != null)
          Text(
            _error!,
            key: const ValueKey<String>('customer-files-error'),
            style: TextStyle(color: theme.colorScheme.error),
          ),
        if (rows == null)
          const Center(child: CircularProgressIndicator())
        else if (rows.isEmpty)
          const Text('No files are kept with this customer.')
        else
          Card(
            child: Column(
              children: [
                for (final CustomerAttachment file in rows)
                  ListTile(
                    key: ValueKey<String>('customer-file-${file.id}'),
                    leading: const Icon(Icons.attach_file),
                    title: Text(file.fileName, overflow: TextOverflow.ellipsis),
                    subtitle: Text(
                      [
                        if ((file.caption ?? '').isNotEmpty) file.caption!,
                        _day(file.createdAt),
                      ].join(' · '),
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: widget.onRemove == null
                        ? null
                        : IconButton(
                            tooltip: 'Remove',
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () => _remove(file),
                          ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

/// Picks files (the STK-9 picker) and keeps them with the customer in one
/// call; stays open with the server's message on a refusal.
class CustomerFilesDialog extends StatefulWidget {
  const CustomerFilesDialog({
    super.key,
    required this.onAdd,
    this.pickFiles,
  });

  final Future<void> Function(List<Json> files) onAdd;
  final Future<List<XFile>> Function()? pickFiles;

  @override
  State<CustomerFilesDialog> createState() => _CustomerFilesDialogState();
}

class _CustomerFilesDialogState extends State<CustomerFilesDialog>
    with SaveInDialog<CustomerFilesDialog> {
  List<Json> _pending = const [];

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add files'),
      content: SizedBox(
        width: 640,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveErrorBanner(),
              StockEvidencePicker(
                pickFiles: widget.pickFiles,
                onChanged: (List<Json> files) =>
                    setState(() => _pending = files),
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
          key: const ValueKey<String>('customer-files-save'),
          onPressed: saving || _pending.isEmpty
              ? null
              : () => saveAndClose<bool>(() async {
                    await widget.onAdd(_pending);
                    return true;
                  }),
          child: Text(saving ? 'Saving…' : 'Save files'),
        ),
      ],
    );
  }
}
