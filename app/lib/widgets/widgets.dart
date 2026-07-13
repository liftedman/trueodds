import 'package:flutter/material.dart';
import 'package:sports_model_app/widgets/team_avatar.dart';
import 'package:sports_model_app/widgets/theme.dart';

String pct(double v) => '${(v * 100).round()}%';
String pct1(double v) => '${(v * 100).toStringAsFixed(1)}%';

/// A labelled dropdown.
class Picker extends StatelessWidget {
  final String label;
  final String? value;
  final List<String> items;
  final ValueChanged<String?> onChanged;
  const Picker(this.label, this.value, this.items, this.onChanged, {super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.2,
                color: Theme.of(context).colorScheme.onSurface.withOpacity(.6))),
        const SizedBox(height: 4),
        DropdownButton<String>(
          value: value,
          isExpanded: true,
          // Closed button shows the selection on a single line (no wrap into
          // the underline); the open menu keeps the full names.
          selectedItemBuilder: (context) => items
              .map((s) => Align(
                    alignment: Alignment.centerLeft,
                    child: Text(s,
                        maxLines: 1, overflow: TextOverflow.ellipsis, softWrap: false),
                  ))
              .toList(),
          items: items
              .map((s) => DropdownMenuItem(value: s, child: Text(s)))
              .toList(),
          onChanged: onChanged,
        ),
      ],
    );
  }
}

/// One probability bar (name, fraction, percentage). Leading row is accented.
class ProbBar extends StatelessWidget {
  final String name;
  final double value;
  final bool lead;
  final Color accent;
  const ProbBar(this.name, this.value, this.lead, this.accent, {super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    final track = Theme.of(context).colorScheme.onSurface.withOpacity(.08);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          SizedBox(
              width: 92,
              child: Text(name.toUpperCase(),
                  style: TextStyle(fontSize: 11, letterSpacing: .5, color: muted))),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Container(
                height: 22,
                color: track,
                child: FractionallySizedBox(
                  alignment: Alignment.centerLeft,
                  widthFactor: value.clamp(0.0, 1.0),
                  child: Container(
                    decoration: BoxDecoration(
                      color: accent.withOpacity(lead ? 1.0 : .4),
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                ),
              ),
            ),
          ),
          SizedBox(
              width: 52,
              child: Text(pct1(value),
                  textAlign: TextAlign.right,
                  style: TextStyle(
                      fontFeatures: const [FontFeature.tabularFigures()],
                      fontWeight: lead ? FontWeight.bold : FontWeight.normal,
                      color: lead ? accent : null))),
        ],
      ),
    );
  }
}

/// Market chips; high-probability (>=70%) ones glow with the accent.
class MarketChips extends StatelessWidget {
  final Map<String, double> markets;
  final Color accent;
  const MarketChips(this.markets, this.accent, {super.key});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: markets.entries.map((e) {
        final hot = e.value >= .70;
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
          decoration: BoxDecoration(
            color: hot ? accent.withOpacity(.14) : null,
            border: Border.all(
                color: hot
                    ? accent
                    : Theme.of(context).colorScheme.onSurface.withOpacity(.15)),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(e.key,
                  style: TextStyle(
                      fontSize: 10,
                      color:
                          Theme.of(context).colorScheme.onSurface.withOpacity(.6))),
              Text(pct(e.value),
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: hot ? accent : null)),
            ],
          ),
        );
      }).toList(),
    );
  }
}

/// Upcoming + live fixtures. Handles football (h/d/a) and NBA (home_win) shapes.
class FixturesList extends StatelessWidget {
  final List fixtures;
  final Color accent;
  const FixturesList(this.fixtures, this.accent, {super.key});

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurface.withOpacity(.6);
    if (fixtures.isEmpty) {
      return Text('No upcoming fixtures — off-season or none scheduled yet.',
          style: TextStyle(color: muted));
    }
    final rows = fixtures.take(12).map<Widget>((f) {
      final live = f['live'] == true;
      final score = f['score'];
      // probabilities (football h/d/a) or win% (nba home/away)
      List<Widget> odds;
      if (f.containsKey('home_win')) {
        final hw = (f['home_win'] as num).toDouble();
        final aw = (f['away_win'] as num).toDouble();
        odds = [
          _o('1', pct(hw), hw >= aw, accent),
          _o('2', pct(aw), aw > hw, accent),
        ];
      } else {
        final h = (f['h'] as num).toDouble();
        final d = (f['d'] as num).toDouble();
        final a = (f['a'] as num).toDouble();
        final mx = [h, d, a].reduce((x, y) => x > y ? x : y);
        odds = [
          _o('1', pct(h), h == mx, accent),
          _o('X', pct(d), d == mx, accent),
          _o('2', pct(a), a == mx, accent),
        ];
      }
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // top line: crests + matchup (full width) + time / live
            Row(children: [
              DuoAvatar(f['home'] as String, f['away'] as String, size: 28),
              const SizedBox(width: 10),
              Expanded(
                child: Text('${f['home']}  v  ${f['away']}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14.5)),
              ),
              const SizedBox(width: 8),
              if (live)
                Text('● LIVE${score != null ? '  $score' : ''}',
                    style: const TextStyle(
                        color: Color(0xFFE5484D),
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700))
              else
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('${f['time'] ?? ''}',
                        style: const TextStyle(
                            fontSize: 12, fontWeight: FontWeight.w600)),
                    Text('${f['date'] ?? ''}',
                        style: TextStyle(fontSize: 10, color: muted)),
                  ],
                ),
            ]),
            const SizedBox(height: 8),
            // second line: odds + extras, left-aligned with room to breathe
            Row(children: [
              ...odds,
              const Spacer(),
              if (f['proj'] != null)
                Text('proj ${f['proj']}',
                    style: TextStyle(fontSize: 11, color: muted)),
              if (f['ov'] != null)
                Text('O2.5 ${pct((f['ov'] as num).toDouble())}',
                    style: TextStyle(fontSize: 11, color: muted)),
            ]),
          ],
        ),
      );
    }).toList();
    return Column(
      children: [
        for (var i = 0; i < rows.length; i++) ...[
          rows[i],
          if (i < rows.length - 1) Divider(height: 1, color: Theme.of(context).dividerColor),
        ]
      ],
    );
  }

  Widget _o(String label, String value, bool win, Color accent) => Container(
        margin: const EdgeInsets.only(right: 6),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: win ? accent.withOpacity(.12) : null,
          border: Border.all(color: win ? accent : Colors.grey.withOpacity(.3)),
          borderRadius: BorderRadius.circular(7),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text('$label ',
              style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: win ? accent : Colors.grey)),
          Text(value,
              style: TextStyle(
                  fontSize: 12,
                  fontFeatures: const [FontFeature.tabularFigures()],
                  fontWeight: win ? FontWeight.w700 : FontWeight.normal,
                  color: win ? accent : null)),
        ]),
      );
}

/// A confidence badge from the leading probability.
class ConfidenceBadge extends StatelessWidget {
  final double topProb;
  const ConfidenceBadge(this.topProb, {super.key});

  @override
  Widget build(BuildContext context) {
    final (label, color) = topProb >= .65
        ? ('High confidence', AppTheme.hi)
        : topProb >= .45
            ? ('Medium confidence', AppTheme.med)
            : ('Low confidence — close call', AppTheme.lo);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
          color: color, borderRadius: BorderRadius.circular(999)),
      child: Text(label,
          style: const TextStyle(
              fontSize: 10, fontWeight: FontWeight.w700, color: Colors.black87)),
    );
  }
}
