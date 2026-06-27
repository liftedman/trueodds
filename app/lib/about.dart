import 'package:flutter/material.dart';

/// The honesty layer — how it works, the real track record, and the data.
class AboutTab extends StatelessWidget {
  final Map data;
  final Future<void> Function() onRefresh;
  final VoidCallback onReplayIntro;
  const AboutTab(this.data,
      {required this.onRefresh, required this.onReplayIntro, super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.65);
    final leagues = (data['leagues'] as Map?) ?? {};
    final calib = <Widget>[];
    for (final e in leagues.entries) {
      final c = e.value['calib'];
      if (c == null) continue;
      final m = (c['model_ll'] as num).toDouble();
      final b = (c['book_ll'] as num).toDouble();
      calib.add(Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          Expanded(child: Text(e.value['name'] as String)),
          Text('model ${m.toStringAsFixed(3)}   bookie ${b.toStringAsFixed(3)}',
              style: TextStyle(
                  fontFeatures: const [FontFeature.tabularFigures()],
                  fontSize: 12,
                  color: muted)),
        ]),
      ));
    }

    Widget card(String title, List<Widget> children) => Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title.toUpperCase(),
                      style: TextStyle(
                          fontSize: 11, letterSpacing: 1.3, color: muted)),
                  const SizedBox(height: 10),
                  ...children,
                ]),
          ),
        );

    return RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.all(16),
            children: [
      card('How it works', [
        const Text(
          'Three models, each suited to its sport. Clubs use a Dixon-Coles '
          'expected-goals model; the World Cup, NBA and tennis use Elo ratings '
          '(tennis is surface-aware). Everything is computed on your device '
          'from a snapshot the engine publishes — no guessing server.',
        ),
      ]),
      card('The honest scoreboard', [
        const Text(
          'Out-of-sample, the model lands within ~3% of the bookmaker’s '
          'closing line — good, but consistently behind it.',
        ),
        const SizedBox(height: 12),
        if (calib.isNotEmpty) ...calib,
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            border: Border(
                left: BorderSide(
                    color: Theme.of(context).colorScheme.primary, width: 3)),
            color: Theme.of(context).colorScheme.primary.withOpacity(.08),
          ),
          child: const Text(
            'No betting edge. These are honest probabilities for insight — not '
            'a way to beat the market. High accuracy only appears on easy '
            'markets (e.g. Over 0.5 goals) at tiny odds. Anyone promising ~80% '
            'on match outcomes is selling something.',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ]),
      card('Data sources', [
        Text(
          'football-data.co.uk · understat (xG) · martj42 international results · '
          'NBA stats API · TML-Database (ATP) · football-data.org & TheSportsDB '
          '(fixtures + live scores).',
          style: TextStyle(color: muted),
        ),
        const SizedBox(height: 8),
        Text('Snapshot updated: ${data['__updated'] ?? 'recently'}',
            style: TextStyle(fontSize: 12, color: muted)),
      ]),
      Padding(
        padding: const EdgeInsets.only(top: 4),
        child: OutlinedButton.icon(
          onPressed: onReplayIntro,
          icon: const Icon(Icons.replay_rounded, size: 18),
          label: const Text('Replay intro'),
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(48),
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
      ),
    ]));
  }
}
