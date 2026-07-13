import 'package:flutter/material.dart';
import 'beat_model.dart';
import 'predict.dart';
import 'theme.dart';
import 'trust.dart';
import 'widgets.dart';

part 'sports/clubs_tab.dart';
part 'sports/elo_tab.dart';
part 'sports/basketball_tab.dart';
part 'sports/nfl_tab.dart';
part 'sports/tennis_tab.dart';

/// Plain-language reasons behind a football/Elo grid prediction.
List<Reason> _gridReasons(String home, String away, GridResult r,
    {List? log, double? eloH, double? eloA, bool neutral = false}) {
  final out = <Reason>[];
  final fav = [r.home, r.draw, r.away].reduce((a, b) => a > b ? a : b);
  final favName = fav == r.home ? home : (fav == r.away ? away : 'A draw');
  out.add(Reason(Icons.emoji_events_outlined,
      '$favName is the most likely outcome at ${pct(fav)}.'));
  if (eloH != null && eloA != null) {
    final gap = (eloH - eloA).abs().round();
    if (gap >= 15) {
      out.add(Reason(Icons.leaderboard_outlined,
          '${eloH >= eloA ? home : away} is rated $gap Elo points higher — the stronger side on paper.'));
    } else {
      out.add(Reason(Icons.leaderboard_outlined,
          'The two sides are closely rated (within $gap Elo points).'));
    }
  }
  out.add(Reason(Icons.sports_soccer_outlined,
      'Expected goals: ${r.lh.toStringAsFixed(2)} for $home, ${r.la.toStringAsFixed(2)} for $away.'));
  if (neutral) {
    out.add(const Reason(
        Icons.flag_outlined, 'Neutral venue — no home advantage applied.'));
  } else {
    out.add(Reason(Icons.home_outlined,
        "Home advantage is built into $home's expected goals."));
  }
  if (log != null) {
    String formLine(String t) {
      final f = teamForm(log, t);
      final w = f.where((x) => x == 'W').length;
      return '$t: ${f.isEmpty ? 'no recent data' : '$w of last ${f.length} won'}';
    }
    out.add(Reason(Icons.trending_up,
        'Recent form — ${formLine(home)}; ${formLine(away)}.'));
  }
  return out;
}

// Country flag + a sensible display order for the league picker.
const _leagueFlag = {
  'E0': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'SP1': '🇪🇸', 'D1': '🇩🇪', 'I1': '🇮🇹', 'F1': '🇫🇷',
  'E1': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'N1': '🇳🇱', 'P1': '🇵🇹', 'SC0': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
  'B1': '🇧🇪', 'T1': '🇹🇷', 'G1': '🇬🇷',
};
const _leagueOrder = [
  'E0', 'SP1', 'D1', 'I1', 'F1', 'E1', 'N1', 'P1', 'SC0', 'B1', 'T1', 'G1',
];

List<String> _names(List teams, [String key = 'name']) =>
    teams.map((t) => t[key] as String).toList()..sort();

Map<String, double> _eloMap(List teams) =>
    {for (final t in teams) t['name'] as String: (t['elo'] as num).toDouble()};

double _d(dynamic v) => (v as num).toDouble();

Widget _matchup(BuildContext c, String h, String a) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        Expanded(
            child: Text(h,
                textAlign: TextAlign.right,
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18))),
        Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: Text('VS', style: TextStyle(color: Theme.of(c).colorScheme.primary))),
        Expanded(
            child: Text(a,
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18))),
      ]),
    );

Widget _card(BuildContext c, List<Widget> children) => Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      ),
    );

Color _muted(BuildContext c) => Theme.of(c).colorScheme.onSurface.withOpacity(.6);

Widget _label(BuildContext c, String t) => Padding(
      padding: const EdgeInsets.only(top: 16, bottom: 6),
      child: Text(t.toUpperCase(),
          style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: _muted(c))),
    );

Widget _outPicker(
        BuildContext c, String label, int value, ValueChanged<int?> onChanged) =>
    Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label.toUpperCase(),
          style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: _muted(c))),
      const SizedBox(height: 4),
      DropdownButton<int>(
        value: value,
        isExpanded: true,
        items: [0, 1, 2, 3]
            .map((i) => DropdownMenuItem(
                value: i, child: Text(i == 0 ? 'Full squad' : '$i key out')))
            .toList(),
        onChanged: onChanged,
      ),
    ]);

Widget _chips(BuildContext c, String title, Map<String, double> m, Color accent) =>
    Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _label(c, title),
      MarketChips(m, accent),
    ]);

List<Widget> _fixturesSection(BuildContext c, List fx, Color accent) =>
    [_label(c, 'Upcoming fixtures'), FixturesList(fx, accent)];

/// Real corners/cards for two teams by cross-referencing their club-league
/// rate history (works for clubs + most UCL teams). Returns null when either
/// team has no such history (e.g. international sides).
({double corners, double cards, Map<String, double> cornerO, Map<String, double> cardO})?
    _footballCounts(Map data, String home, String away) {
  Map? find(String n) {
    for (final lg in (data['leagues'] as Map? ?? const {}).values) {
      for (final t in (lg['teams'] as List)) {
        if (t['name'] == n) return t as Map;
      }
    }
    return null;
  }

  final h = find(home), a = find(away);
  if (h == null || a == null) return null;
  return clubCounts(h, a);
}

/// Corners/cards block — real chips when data exists, else an honest note.
List<Widget> _countsSection(
    BuildContext c, Map data, String home, String away, String sportKey, Color accent) {
  final counts = _footballCounts(data, home, away);
  if (counts != null) {
    return [
      _label(c, 'Corners (proj ${counts.corners.toStringAsFixed(1)})'),
      MarketChips(counts.cornerO, accent),
      _label(c, 'Cards (proj ${counts.cards.toStringAsFixed(1)})'),
      MarketChips(counts.cardO, accent),
    ];
  }
  return [
    _label(c, 'Corners & cards'),
    Text(
        sportKey == 'wc'
            ? "Corner & card stats aren't collected for international teams, "
                "so we don't estimate them here."
            : "Corner & card history isn't available for one of these teams.",
        style: TextStyle(fontSize: 12, color: _muted(c))),
  ];
}

Widget _formBadge(String r) {
  final color = r == 'W'
      ? AppTheme.hi
      : r == 'D'
          ? AppTheme.lo
          : const Color(0xFF6E4A4A);
  return Container(
    width: 22,
    height: 22,
    margin: const EdgeInsets.only(right: 5),
    decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(5)),
    child: Center(
        child: Text(r,
            style: const TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white))),
  );
}

Widget _formRow(BuildContext c, String name, List<String> form) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(
            width: 120,
            child: Text(name,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600))),
        if (form.isEmpty)
          Text('—', style: TextStyle(color: _muted(c)))
        else
          ...form.map(_formBadge),
      ]),
    );

/// Collapsible ranked Elo ratings.
Widget _eloRatings(BuildContext c, List teams) {
  final sorted = [...teams]..sort((a, b) => _d(b['elo']).compareTo(_d(a['elo'])));
  return ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text('Power ratings',
        style: TextStyle(fontSize: 11, letterSpacing: 1.2, color: _muted(c))),
    children: [
      for (var i = 0; i < sorted.length; i++)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(children: [
            SizedBox(width: 28, child: Text('${i + 1}', style: TextStyle(color: _muted(c)))),
            Expanded(child: Text('${sorted[i]['name']}')),
            Text('${_d(sorted[i]['elo']).round()}',
                style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()])),
          ]),
        ),
    ],
  );
}

