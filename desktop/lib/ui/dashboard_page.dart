import 'package:flutter/material.dart';

import '../core/api/api_client.dart';
import '../models/entities.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  Json? _data;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final Json response = await widget.api.dashboard();
      if (mounted) {
        setState(() => _data = response);
      }
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() => _error = exception.isForbidden
            ? 'You are not authorized to view the dashboard.'
            : exception.message);
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(_error!),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Try again'),
          ),
        ]),
      );
    }
    final Json data = _data ?? const {};
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Dashboard', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 6),
        const Text('Platform administration at a glance.'),
        const SizedBox(height: 24),
        Wrap(spacing: 16, runSpacing: 16, children: [
          _MetricCard(
            label: 'Firms',
            value: stringValue(data['firms'] ?? '—'),
            icon: Icons.business_outlined,
          ),
          _MetricCard(
            label: 'Users',
            value: stringValue(data['users'] ?? '—'),
            icon: Icons.people_outline,
          ),
          _MetricCard(
            label: 'Roles',
            value: stringValue(data['roles'] ?? '—'),
            icon: Icons.badge_outlined,
          ),
          _MetricCard(
            label: 'Permissions',
            value: stringValue(data['permissions'] ?? '—'),
            icon: Icons.key_outlined,
          ),
        ]),
      ]),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.icon,
  });
  final String label, value;
  final IconData icon;
  @override
  Widget build(BuildContext context) => SizedBox(
        width: 230,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(children: [
              Icon(icon,
                  size: 32, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 16),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(value, style: Theme.of(context).textTheme.headlineSmall),
                Text(label),
              ]),
            ]),
          ),
        ),
      );
}
